#!/usr/bin/env python3
"""Watch a game directory and write the news: one story per box score the game leaves in Stats/, one 'Around the
league' column per played date, and each association's standings and leaders. server.py shows what this writes.

    python3 news/watch.py --game /path/to/BBPRO_98 --data /path/to/news-data [--once] [--no-llm]

Data layout (server.py reads it):
    <data>/budget.json, <data>/limits.json            hive.Budget state and its limits
    <data>/teamnames.json                              full Lahman team names (optional; news/teamnames.py)
    <data>/<ASSN>/meta.json                            name, last_day, standings, leaders, updated
    <data>/<ASSN>/recaps/<key>.json                    key = first 16 hex chars of the box score file's sha1
    <data>/<ASSN>/feed/<MM>-<DD>.json                  one column per played date
    <data>/<ASSN>/preview.json, awards.json            season preview (once), season awards (once all games are played)
    <data>/<ASSN>/scout/<tid>.json                     one scouting report per team (once)
    <data>/<ASSN>/moves/log.json, notes/<n>.json       roster moves and milestones, newest last; a note per notable one
    <data>/<ASSN>/moves/last.json                      the snapshot the next scan diffs against
    <data>/<ASSN>/contracts.json                       contracts and payrolls, priced from news/salary_table.json
    <data>/<ASSN>/replay.json                          the season against its Lahman namesake (with --db; replay.py)

The game files are only read. A box score is matched to its schedule game by teams and final score (gamedata); one
that matches nothing yet (the association not saved since the game) is retried on later scans. Stories go to the
model while the daily budget lasts and fall back to the template after that (recap.write / feed.write).
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contracts  # noqa: E402
import feed      # noqa: E402
import gamedata  # noqa: E402
import hive      # noqa: E402
import moves     # noqa: E402
import recap     # noqa: E402
import replay    # noqa: E402
import scout     # noqa: E402
import season    # noqa: E402
import teamnames  # noqa: E402

SETTLE = 5            # seconds a game file must sit unchanged before it is read
LLM_DAYS = 3          # columns for the newest dates go to the model; older dates get the template
SCOUT_CALLS = 3       # scouting reports asked of the model per scan, so a backfill never holds up box scores
MOVE_CALLS = 3        # transaction notes asked of the model per scan; the rest of a scan's notes get the template
MOVE_KEEP = 3000      # events kept in moves/log.json
DEFAULT_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'salary_table.json')


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding='utf-8') as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def associations(game_dir):
    """{stem: ASN path} for every association in Assn/ except the game's _DEFAULT files."""
    assn_dir = os.path.join(game_dir, 'Assn')
    out = {}
    for f in os.listdir(assn_dir):
        stem, ext = os.path.splitext(f)
        if ext.upper() == '.ASN' and not stem.startswith('_') and re.fullmatch(r'[A-Za-z0-9]{1,8}', stem):
            out[stem.upper()] = os.path.join(assn_dir, f)
    return out


def through(assoc, month, day):
    """assoc with every game after (month, day) treated as unplayed: the standings as they stood that night."""
    games = [g if (g['month'], g['day']) <= (month, day) else dict(g, played=False, away_runs=0, home_runs=0)
             for g in assoc['games']]
    return dict(assoc, games=games)


def _llm_or_template(write, facts, budget, complete):
    if complete is None:
        return None
    return write(facts, budget, complete)


class Watcher:
    def __init__(self, game_dir, data_dir, budget, complete, log=print, db=None, salary_table=None):
        self.game, self.data, self.budget, self.complete, self.log = game_dir, data_dir, budget, complete, log
        self.db = db            # the Lahman database, opened read-only; None leaves out the replay scorecard
        self.seen = {}          # stem -> signature of its game files at the last full pass
        self.waiting = set()    # box score keys already logged as unmatched
        self.captured = {}      # stem -> box score keys already in pending/ or recaps/
        self.scout_left = SCOUT_CALLS   # model scouting reports left in this scan
        self.move_left = MOVE_CALLS     # model transaction notes left in this scan
        self.scouting_open = set()      # stems with teams still waiting for a scouting report
        self.real_seasons = {}  # (year, leagues) -> replay.real(): the database is read once per season
        self.off_season = set() # stems whose season_year is not the year their name gives: logged once
        self.names = teamnames.load(os.path.join(data_dir, 'teamnames.json'))   # full Lahman names; {} without it
        try:    # the salary table the contracts are priced from; without it the contracts piece is skipped
            self.table = contracts.load_table(DEFAULT_TABLE if salary_table is None else salary_table)
        except (OSError, ValueError) as e:
            self.table = None
            self.log('contracts: no usable salary table (%s); contracts are skipped' % e)

    def signature(self, stem, asn_path):
        stats, assn = os.path.join(self.game, 'Stats'), os.path.dirname(asn_path)
        files = [asn_path] + [os.path.join(stats, f) for f in os.listdir(stats) if f.upper().startswith(stem + '.')]
        files += [p for p in (gamedata.find(assn, stem + '.PYR'), gamedata.find(assn, stem + '.PYF')) if p]   # moves
        sig = []
        for p in sorted(files):
            try:
                st = os.stat(p)
            except OSError:
                continue
            sig.append((os.path.basename(p), st.st_mtime_ns, st.st_size))
        return tuple(sig)

    def scan(self):
        self.scout_left = SCOUT_CALLS
        self.move_left = MOVE_CALLS
        for stem, asn_path in sorted(associations(self.game).items()):
            try:
                sig = self.signature(stem, asn_path)
                if self.seen.get(stem) == sig and stem not in self.scouting_open:
                    continue
                self.association(stem, asn_path)
                # Files younger than SETTLE were left for later; only a settled set may be skipped next time.
                if time.time() - max((m for _, m, _ in sig), default=0) / 1e9 >= SETTLE:
                    self.seen[stem] = sig
            except Exception as e:      # one bad association (a file mid-write) must not stop the others
                self.log('%s: %s: %s' % (stem, type(e).__name__, e))

    def association(self, stem, asn_path):
        stats_dir = os.path.join(self.game, 'Stats')
        out = os.path.join(self.data, stem)
        assoc = teamnames.apply(gamedata.association(asn_path), self.names)
        pyr = gamedata.find(os.path.join(self.game, 'Assn'), stem + '.PYR')
        names = gamedata.names(pyr) if pyr else {}
        dat = gamedata.find(stats_dir, stem + '.DAT')
        season = gamedata.season_lines(dat) if dat else {'bat': {}, 'pit': {}}
        self.capture(stem)
        self.columns(out, assoc, names, season)      # first: a few calls a day, and the page leads with them
        self.recaps(stem, out, assoc, names, stats_dir)
        played = sum(1 for g in assoc['games'] if g['played'])
        teams_played = played * 2 / len(assoc['teams']) if assoc['teams'] else 0.0
        last = feed.last_day(assoc)
        write_json(os.path.join(out, 'meta.json'), {
            'assn': stem, 'name': assoc['name'], 'updated': now_iso(), 'last_day': list(last) if last else None,
            'standings': feed.standings(assoc), 'leaders': feed.leaders(season, names, teams_played)})
        self.season_pieces(out, assoc, names, dat, pyr)
        self.moves(out, assoc, pyr, dat)
        self.contracts_piece(out, assoc, pyr, dat)
        self.replay_piece(out, assoc, names, season)

    def contracts_piece(self, out, assoc, pyr, dat):
        """The contracts and payrolls (contracts.py), after moves: each rostered player's contract, ticked down at each
        season rollover, and every team's payroll, written to contracts.json. Needs the PYR, the salary table and some
        teams; no model. Waits while the PYR, the PYF beside it or the DAT is younger than SETTLE, as moves does."""
        if self.table is None or pyr is None or not assoc['teams']:
            return
        pyf = gamedata.find(os.path.dirname(pyr), os.path.splitext(os.path.basename(pyr))[0] + '.PYF')
        if time.time() - max(os.stat(p).st_mtime for p in (pyr, pyf, dat) if p) < SETTLE:
            return      # a torn set would price contracts from a half-saved league; the next scan retries
        path = os.path.join(out, 'contracts.json')
        prev = read_json(path)
        if prev is not None and (prev.get('kind') != 'contracts' or 'season_year' not in prev
                                 or not isinstance(prev.get('contracts'), dict)
                                 or not isinstance(prev.get('events'), list)):
            prev = None
        found = replay.season_of(assoc['name'])
        pay = contracts.NEGRO_PAY if found is not None and found[1] == replay.NEGRO_LEAGUES else 1.0
        state = contracts.update(prev, assoc, gamedata.players(pyr), assoc.get('season_year'), self.table, pay)
        write_json(path, dict(state, kind='contracts', payroll=contracts.payroll(state['contracts'], assoc['teams']),
                              created=now_iso()))

    def replay_piece(self, out, assoc, names, season):
        """The replay scorecard, written on every pass of a Lahman-named association while a database is given: this
        season's standings and leaders against the real season of the same name. A sqlite error is logged and
        skipped."""
        found = replay.season_of(assoc['name'])
        if self.db is None or found is None:
            return
        stem = os.path.basename(out)
        sim_year = assoc.get('season_year')
        if type(sim_year) is int and sim_year != found[0]:
            if stem not in self.off_season:
                self.off_season.add(stem)
                self.log('%s replay: season %d is not %d, skipped' % (stem, sim_year, found[0]))
            return
        try:
            if found not in self.real_seasons:
                self.real_seasons[found] = self.read_real(*found)
            card = replay.scorecard(assoc, season, names, self.real_seasons[found])
        except sqlite3.Error as e:
            self.log('%s replay: %s' % (stem, e))
            return
        write_json(os.path.join(out, 'replay.json'), dict(card, kind='replay', year=found[0], created=now_iso()))

    def read_real(self, year, leagues):
        con = sqlite3.connect(pathlib.Path(self.db).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            return replay.real(con, year, leagues)
        finally:
            con.close()

    def season_pieces(self, out, assoc, names, dat, pyr=None):
        """The season preview (once per association), once every game is played the season awards, and the scouting
        reports (once per team)."""
        stem = os.path.basename(out)
        if assoc['teams'] and not os.path.exists(os.path.join(out, 'preview.json')):
            last = gamedata.season_lines(dat, scope=3) if dat else {'bat': {}, 'pit': {}}
            facts = season.preview_facts(assoc, last, names)
            piece = _llm_or_template(season.write_preview, facts, self.budget, self.complete)
            if piece is None:
                piece = dict(season.preview_template(facts), source='template', reason='off')
            write_json(os.path.join(out, 'preview.json'), dict(piece, kind='preview', facts=facts, created=now_iso()))
            self.log('%s preview (%s)' % (stem, piece['source']))
        if season.complete(assoc) and not os.path.exists(os.path.join(out, 'awards.json')):
            lines = gamedata.season_lines(dat) if dat else {'bat': {}, 'pit': {}}
            facts = season.awards_facts(assoc, lines, names)
            piece = _llm_or_template(season.write_awards, facts, self.budget, self.complete)
            if piece is None:
                piece = dict(season.awards_template(facts), source='template', reason='off')
            write_json(os.path.join(out, 'awards.json'), dict(piece, kind='awards', facts=facts, created=now_iso()))
            self.log('%s awards (%s)' % (stem, piece['source']))
        self.scouting(out, assoc, pyr, dat)

    def scouting(self, out, assoc, pyr, dat):
        """One scouting report per team, written once: the team's best hitters and pitchers graded from the PYR ratings,
        with last season's numbers where they qualify. Reads no game file while every team already has its report.
        With the model on, at most SCOUT_CALLS reports a scan, and none once the day's budget is spent (a template
        written then would stand for good); the association stays open for the next scans until every team has one."""
        stem = os.path.basename(out)
        if not assoc['teams'] or pyr is None:
            return
        todo = [tid for tid in sorted(assoc['teams'])
                if not os.path.exists(os.path.join(out, 'scout', '%d.json' % tid))]
        if not todo:
            return
        players = gamedata.players(pyr)
        last = gamedata.season_lines(dat, scope=3) if dat else {'bat': {}, 'pit': {}}
        year = scout.year_of(assoc['name'])
        for tid in todo:
            if self.complete is not None and self.scout_left <= 0:
                self.scouting_open.add(stem)
                return
            team = assoc['teams'][tid]
            facts = scout.team_facts(assoc, tid, players, last, year)
            if self.complete is not None:
                self.scout_left -= 1
            piece = _llm_or_template(scout.write, facts, self.budget, self.complete)
            if piece is not None and piece.get('reason') == 'budget':
                self.scouting_open.add(stem)
                return
            if piece is None:
                piece = dict(scout.template(facts), source='template', reason='off')
            write_json(os.path.join(out, 'scout', '%d.json' % tid),
                       dict(piece, kind='scout', tid=tid, abbrev=team['abbrev'], team=team['name'], facts=facts,
                            roster=scout.roster(assoc, tid, players, year), created=now_iso()))
            self.log('%s scout %s (%s)' % (stem, team['abbrev'], piece['source']))
        self.scouting_open.discard(stem)

    def moves(self, out, assoc, pyr, dat):
        """Roster moves and milestones since the last scan (moves.py). The current snapshot is diffed against last.json;
        the events go to the end of log.json, which keeps MOVE_KEEP and counts every event ever logged, so a note's
        number never changes; each notable event gets a note; then the snapshot becomes last.json. Nothing is written
        without the PYR, the PYF beside it (the free agents) or the stats (DAT), or while one is younger than SETTLE."""
        if pyr is None or dat is None:
            return
        pyf = gamedata.find(os.path.dirname(pyr), os.path.splitext(os.path.basename(pyr))[0] + '.PYF')
        if pyf is None:
            return
        if time.time() - max(os.stat(p).st_mtime for p in (pyr, pyf, dat)) < SETTLE:
            return      # a torn set (PYR saved, PYF not yet) would log moves that never happened; the next scan retries
        stem = os.path.basename(out)
        mdir = os.path.join(out, 'moves')
        cur = moves.snapshot(assoc, gamedata.players(pyr), gamedata.free_agents(pyf),
                             gamedata.season_lines(dat, scope=2), gamedata.season_lines(dat, scope=1))
        date = moves.date_text(feed.last_day(assoc))
        prev = read_json(os.path.join(mdir, 'last.json'))
        same = prev is not None and prev.get('year') == cur['year']
        events = moves.diff(prev, cur, assoc['teams'], same_season=same)
        log_path = os.path.join(mdir, 'log.json')
        log = read_json(log_path) or {}
        old = log.get('events')
        kept = [e for e in old if isinstance(e, dict)] if isinstance(old, list) else []
        count = log.get('count') if type(log.get('count')) is int else len(kept)
        for n, ev in enumerate(events, count):
            ev.update(date=date, year=cur['year'])
            if moves.notable(ev, cur):
                ev['note'] = n
        if events:
            write_json(log_path, {'events': (kept + events)[-MOVE_KEEP:], 'count': count + len(events)})
            self.log('%s moves: %d' % (stem, len(events)))
        for ev in events:
            if 'note' not in ev:
                continue
            facts = moves.facts(ev, assoc['name'], date, cur['career'].get(str(ev['pid'])))
            if self.complete is None:
                piece = dict(moves.template(facts), source='template', reason='off')
            elif self.move_left > 0:
                self.move_left -= 1
                piece = moves.write(facts, self.budget, self.complete)
            else:
                piece = dict(moves.template(facts), source='template', reason='backfill')
            write_json(os.path.join(mdir, 'notes', '%d.json' % ev['note']),
                       dict(piece, kind='move', event=ev, facts=facts, created=now_iso()))
            self.log('%s move: %s %s (%s)' % (stem, ev['kind'], ev['name'], piece['source']))
        write_json(os.path.join(mdir, 'last.json'), dict(cur, date=date))

    def capture(self, stem):
        """Copy every new box score of this association into <data>/<ASSN>/pending/ as parsed JSON. The game keeps
        only the last seven sim days of box scores (Stats/<ASSN>.H<day><game>, the oldest day deleted as each new one
        is written), so this runs before every story the model is asked for, and a long sim loses nothing."""
        stats_dir = os.path.join(self.game, 'Stats')
        out = os.path.join(self.data, stem)
        for path in gamedata.box_files(stats_dir, stem):
            try:
                if time.time() - os.path.getmtime(path) < SETTLE:
                    continue
                with open(path, 'rb') as fh:
                    key = hashlib.sha1(fh.read()).hexdigest()[:16]
                if key in self.captured.setdefault(stem, set()):
                    continue
                if not (os.path.exists(os.path.join(out, 'recaps', key + '.json'))
                        or os.path.exists(os.path.join(out, 'pending', key + '.json'))):
                    box = gamedata.boxscore(path)
                    if box['away']['tid'] is None or box['home']['tid'] is None:
                        continue
                    write_json(os.path.join(out, 'pending', key + '.json'),
                               {'key': key, 'file': os.path.basename(path), 'mtime': os.path.getmtime(path),
                                'box': box})
                self.captured[stem].add(key)
            except OSError:
                continue            # deleted or replaced while being read: the next pass sees its successor

    def recaps(self, stem, out, assoc, names, stats_dir):
        rdir, pdir = os.path.join(out, 'recaps'), os.path.join(out, 'pending')
        used = set()
        if os.path.isdir(rdir):
            for f in os.listdir(rdir):
                r = read_json(os.path.join(rdir, f)) if f.endswith('.json') else None
                if r and all(k in r for k in ('month', 'day', 'slot')):
                    used.add((r['month'], r['day'], r['slot']))
        self.capture(stem)
        pending = []
        for f in os.listdir(pdir) if os.path.isdir(pdir) else []:
            p = read_json(os.path.join(pdir, f)) if f.endswith('.json') else None
            if p and isinstance(p.get('box'), dict):
                pending.append(p)
        pending.sort(key=lambda p: (p.get('mtime', 0), p.get('file', '')), reverse=True)   # newest games first
        for p in pending:
            key, box = p['key'], p['box']
            cands = [g for g in recap.in_order(gamedata.match_game(assoc, box))
                     if (g['month'], g['day'], g['slot']) not in used]
            if not cands:
                if key not in self.waiting:
                    self.waiting.add(key)
                    self.log('%s: %s matches no unreported played game yet' % (stem, p['file']))
                continue
            game = cands[-1]
            facts = recap.game_facts(assoc, box, game, names)
            story = _llm_or_template(recap.write, facts, self.budget, self.complete)
            if story is None:
                story = dict(recap.template(facts), source='template', reason='off')
            write_json(os.path.join(rdir, key + '.json'),
                       dict(story, key=key, assn=stem, month=game['month'], day=game['day'], slot=game['slot'],
                            file=p['file'], facts=facts, created=now_iso()))
            os.remove(os.path.join(pdir, key + '.json'))
            used.add((game['month'], game['day'], game['slot']))
            self.log('%s: %s %s -> %s (%s)' % (stem, facts['date'], p['file'], key, story['source']))
            if story['source'] == 'glm':
                self.capture(stem)      # a model call takes seconds; grab what the game wrote meanwhile

    def columns(self, out, assoc, names, season):
        days = sorted({(g['month'], g['day']) for g in assoc['games'] if g['played']})
        recent = set(days[-LLM_DAYS:])
        empty = {'bat': {}, 'pit': {}}
        for month, day in days:
            dest = os.path.join(out, 'feed', '%02d-%02d.json' % (month, day))
            old = read_json(dest)
            last = (month, day) == days[-1]
            facts = feed.day_facts(through(assoc, month, day), season if last else empty, names, month, day)
            if old and old.get('facts', {}).get('results') == facts['results']:
                continue            # written, and no game of that date has been added since
            column = None
            if (month, day) in recent:
                column = _llm_or_template(feed.write, facts, self.budget, self.complete)
            if column is None:
                column = dict(feed.template(facts), source='template', reason='backfill' if self.complete else 'off')
            write_json(dest, dict(column, month=month, day=day, date=facts['date'], facts=facts, created=now_iso()))
            self.log('column %s %s (%s)' % (os.path.basename(out), facts['date'], column['source']))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--game', default=os.environ.get('BBNEWS_GAME'), help='the game directory (holds Assn/, Stats/)')
    ap.add_argument('--data', default=os.environ.get('BBNEWS_DATA'), help='where the news is written')
    ap.add_argument('--interval', type=float, default=20.0)
    ap.add_argument('--calls', type=int, default=int(os.environ.get('BBNEWS_CALLS', 1000)), help='model calls a day')
    ap.add_argument('--tokens', type=int, default=int(os.environ.get('BBNEWS_TOKENS', 3000000)),
                    help='model output tokens a day')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--no-llm', action='store_true', help='template stories only')
    ap.add_argument('--db', default=None, help='the Lahman database, opened read-only: adds the replay scorecard')
    a = ap.parse_args(argv)
    if not a.game or not a.data:
        ap.error('--game and --data (or BBNEWS_GAME / BBNEWS_DATA) are required')
    os.makedirs(a.data, exist_ok=True)
    write_json(os.path.join(a.data, 'limits.json'), {'calls_per_day': a.calls, 'tokens_per_day': a.tokens})
    budget = hive.Budget(os.path.join(a.data, 'budget.json'), a.calls, a.tokens)
    w = Watcher(a.game, a.data, budget, None if a.no_llm else hive.complete, log=lambda s: print(s, flush=True),
                db=a.db)
    while True:
        w.scan()
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == '__main__':
    main()
