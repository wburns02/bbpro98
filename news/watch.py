#!/usr/bin/env python3
"""Watch a game directory and write the news: one story per box score the game leaves in Stats/, one 'Around the
league' column per played date, and each association's standings and leaders. server.py shows what this writes.

    python3 news/watch.py --game /path/to/BBPRO_98 --data /path/to/news-data [--once] [--no-llm]

Data layout (server.py reads it):
    <data>/budget.json, <data>/limits.json            hive.Budget state and its limits
    <data>/teamnames.json                              full Lahman team names (optional; news/teamnames.py)
    <data>/<ASSN>/meta.json                            name, season_year, last_day, played, stories, standings, leaders, updated
    <data>/<ASSN>/recaps/<key>.json                    key = first 16 hex chars of the box score file's sha1
    <data>/<ASSN>/feed/<MM>-<DD>.json                  one column per played date
    <data>/<ASSN>/preview.json, awards.json            season preview (once), season awards (once all games are played)
    <data>/<ASSN>/scout/<tid>.json                     one scouting report per team (once)
    <data>/<ASSN>/rookies/<YEAR>.json, ids.json        a season's rookie class (once); the snapshot it is diffed against
    <data>/<ASSN>/draft/<YEAR>.json                    the class as the public scouts saw it, team grades (once), revisited
                                                       three seasons later (once, draft.py)
    <data>/<ASSN>/moves/log.json, notes/<n>.json       roster moves and milestones, newest last; a note per notable one
    <data>/<ASSN>/moves/last.json                      the snapshot the next scan diffs against
    <data>/<ASSN>/contracts.json                       contracts and payrolls, priced from news/salary_table.json
    <data>/<ASSN>/hof.json, hof/<YEAR>-<PID>.json      the Hall of Fame (once a season year) and an induction story each
    <data>/<ASSN>/records.json                         the record book and its bar (records.py)
    <data>/<ASSN>/replay.json                          the season against its Lahman namesake (with --db; replay.py)
    <data>/<ASSN>/follow.json                          the players followed from the player card (written by the bridge)
    <data>/<ASSN>/player/<PID>.json                    a followed player's game log, columns and page data (myplayer.py)
    <data>/<ASSN>/past/<YEAR>/                         the last seasons' news, moved there at each rollover

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
import shutil
import sqlite3
import stat
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arc        # noqa: E402
import bracket    # noqa: E402
import contracts  # noqa: E402
import draft      # noqa: E402
import feed      # noqa: E402
import focus     # noqa: E402
import fog        # noqa: E402
import gamedata  # noqa: E402
import history   # noqa: E402
import hof       # noqa: E402
import hive      # noqa: E402
import moves     # noqa: E402
import myplayer  # noqa: E402
import recap     # noqa: E402
import records   # noqa: E402
import replay    # noqa: E402
import rookies   # noqa: E402
import scout     # noqa: E402
import season    # noqa: E402
import teamnames  # noqa: E402

SETTLE = 5            # seconds a game file must sit unchanged before it is read
LLM_DAYS = 3          # columns for the newest dates go to the model; older dates get the template
SCOUT_CALLS = 3       # scouting reports asked of the model per scan, so a backfill never holds up box scores
MOVE_CALLS = 3        # transaction notes asked of the model per scan; the rest of a scan's notes get the template
HOF_CALLS = 3         # induction stories asked of the model per scan; the rest wait for a later scan
FOLLOW_CALLS = myplayer.FOLLOW_CALLS    # weekly columns on followed players asked of the model per scan; the rest wait
MOVE_KEEP = 3000      # events kept in moves/log.json
MOVE_CATCHUP = 20     # missing notes of this season written per pass, after an interrupted pass left some out
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


def year_of(value):
    """The season year when it is an int (a bool is not one), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def story_count(out):
    """How many *.json files <out>/recaps holds: one story per box score the watcher turned into one."""
    try:
        return sum(1 for f in os.listdir(os.path.join(out, 'recaps')) if f.endswith('.json'))
    except OSError:
        return 0


# What a season leaves in <data>/<ASSN>/ that the next season starts without; the rest (history/, moves/,
# contracts.json, notes/, hof.json, hof/) spans seasons.
SEASON_ENTRIES = ('recaps', 'pending', 'feed', 'scout', 'preview.json', 'awards.json', 'replay.json',
                  'postseason.json')


def associations(game_dir):
    """{stem: ASN path} for every association in Assn/ except the game's _DEFAULT files; {} when Assn/ cannot be read
    (a game folder moved or an unmounted drive), so a watcher pass or a bridge page finds no association instead of
    failing."""
    assn_dir = os.path.join(game_dir, 'Assn')
    out = {}
    try:
        names = os.listdir(assn_dir)
    except OSError:
        return out
    for f in names:
        stem, ext = os.path.splitext(f)
        if ext.upper() == '.ASN' and not stem.startswith('_') and re.fullmatch(r'[A-Za-z0-9]{1,8}', stem):
            out[stem.upper()] = os.path.join(assn_dir, f)
    return out


def through(assoc, month, day):
    """assoc with every game after (month, day) treated as unplayed: the standings as they stood that night."""
    games = [g if (g['month'], g['day']) <= (month, day) else dict(g, played=False, away_runs=0, home_runs=0)
             for g in assoc['games']]
    return dict(assoc, games=games)


def identities(pyr_path):
    """{pid: (first, last, born)} for every named player (id from 100) of a PYR file: the two name fields as the game
    stores them and the birth date, None when the serial is not a date. history.lahman_id matches on these."""
    out = {}
    for rec in gamedata._records(pyr_path):
        pid = rec[0] | rec[1] << 8
        first, last = gamedata.cstr(rec[30:47]).strip(), gamedata.cstr(rec[47:64]).strip()
        if pid < 100 or not (first or last):
            continue
        try:
            born = datetime.date.fromordinal(struct.unpack_from('<I', rec, gamedata.P_BORN)[0] - 365)
        except (ValueError, OverflowError):
            born = None
        out[pid] = (first, last, born)
    return out


def _llm_or_template(write, facts, budget, complete):
    if complete is None:
        return None
    return write(facts, budget, complete)


def _postseason(asn_path):
    """(bracket, schedule) of the postseason in one ASN file; (None, []) without a path or when it cannot be read."""
    if asn_path is None:
        return None, []
    try:
        return gamedata.postseason(asn_path), gamedata.postseason_schedule(asn_path)
    except Exception:       # association() read this file already: what fails here is not a postseason shape
        return None, []


class Watcher:
    def __init__(self, game_dir, data_dir, budget, complete, log=print, db=None, salary_table=None):
        self.game, self.data, self.budget, self.complete, self.log = game_dir, data_dir, budget, complete, log
        self.db = db            # the Lahman database, opened read-only; None leaves out the replay scorecard
        self.seen = {}          # stem -> signature of its game files at the last full pass
        self.waiting = set()    # box score keys already logged as unmatched
        self.captured = {}      # stem -> box score keys already in pending/ or recaps/
        self.scout_left = SCOUT_CALLS   # model scouting reports left in this scan
        self.move_left = MOVE_CALLS     # model transaction notes left in this scan
        self.hof_left = HOF_CALLS       # model induction stories left in this scan
        self.follow_left = FOLLOW_CALLS     # model weekly columns on followed players left in this scan
        self.scouting_open = set()      # stems with teams still waiting for a scouting report
        self.hof_open = set()           # stems with inductees still waiting for a story
        self.follow_open = set()        # stems with a followed player's weekly column still waiting for the model
        self.hof_bad = set()            # stems whose hof.json does not parse: logged once, never overwritten
        self.real_seasons = {}  # (year, leagues) -> replay.real(): the database is read once per season
        self.off_season = set() # stems whose season_year is not the year their name gives: logged once
        self.rookies_due = set()    # stems that rolled into a new season whose rookie class is not written yet
        self.league_cache = {}  # stem -> (key, league()'s value): the PYR is read again only when a file or the year changes
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
        self.hof_left = HOF_CALLS
        self.follow_left = FOLLOW_CALLS
        for stem, asn_path in sorted(associations(self.game).items()):
            try:
                sig = self.signature(stem, asn_path)
                if (self.seen.get(stem) == sig and stem not in self.scouting_open and stem not in self.hof_open
                        and stem not in self.follow_open):
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
        if self.rollover(stem, out, assoc) is not None:
            self.rookies_due.add(stem)
        self.rewind(stem, out, assoc)
        self.capture(stem)
        self.columns(out, assoc, names, season, asn_path)      # first: a few calls a day, and the page leads with them
        self.recaps(stem, out, assoc, names, stats_dir, asn_path)
        played = sum(1 for g in assoc['games'] if g['played'])
        teams_played = played * 2 / len(assoc['teams']) if assoc['teams'] else 0.0
        last = feed.last_day(assoc)
        write_json(os.path.join(out, 'meta.json'), {
            'assn': stem, 'name': assoc['name'], 'season_year': year_of(assoc.get('season_year')),
            'updated': now_iso(), 'last_day': list(last) if last else None,
            'standings': feed.standings(assoc), 'leaders': feed.leaders(season, names, teams_played),
            'played': sum(1 for g in assoc['games'] if g['played']), 'stories': story_count(out),
            'league': self.league(stem, asn_path, pyr, year_of(assoc.get('season_year')))})
        self.season_pieces(out, assoc, names, dat, pyr)
        self.postseason_piece(out, assoc, asn_path)
        self.history_piece(assoc, stem, dat)
        self.hof_piece(out, assoc, stem, pyr)
        self.records_piece(out, assoc, names, pyr)
        self.moves(out, assoc, pyr, dat)
        self.contracts_piece(out, assoc, pyr, dat)
        self.follow_piece(out, assoc, season, pyr)
        self.replay_piece(out, assoc, names, season)
        self.rookie_class(out, assoc, pyr)
        self.draft_piece(out, assoc, pyr)

    def league(self, stem, asn_path, pyr_path, year):
        """The league's age make-up for meta.json: {'year', 'rostered', 'mean_age', 'le25', 'ge33', 'fa'}, or None
        without a PYR or a season year, or when gamedata.demographics() cannot read the files. Cached per stem on the
        year and the (mtime, size) of the ASN, PYR and PYF, a bad file included, so a pass that changed none of them
        reads nothing."""
        if pyr_path is None or year is None:
            return None
        pyf = gamedata.find(os.path.join(self.game, 'Assn'), stem + '.PYF')
        try:
            stats = [os.stat(p) if p else None for p in (asn_path, pyr_path, pyf)]
        except OSError:
            return None
        key = (year,) + tuple((st.st_mtime_ns, st.st_size) if st else None for st in stats)
        cached = self.league_cache.get(stem)
        if cached and cached[0] == key:
            return cached[1]
        try:
            d = gamedata.demographics(asn_path, pyr_path, pyf, year)
            value = {k: d[k] for k in ('year', 'rostered', 'mean_age', 'le25', 'ge33', 'fa')}
        except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error):  # a torn PYR, not just a missing one
            value = None
        self.league_cache[stem] = (key, value)
        return value

    def rollover(self, stem, out, assoc):
        """A career association plays many seasons under one stem. When meta.json holds the last season's year and the
        association is now in another, the season's news moves to <out>/past/<year>/ (-2, -3 ... for a name already
        taken; meta.json is copied, the rest moved) and the new season starts as a new association. Returns that
        folder's name, or None when nothing rolled over: no meta.json, no year in it (written before this), no year
        in the association, or the same year. An OSError part way propagates to scan(), which logs it; what was not
        moved stays, and the next pass tries again. The move is staged in the hidden <out>/past/.rolling-<year>/ and
        renamed to its final name only at the end, so a failed pass leaves no half season under a season name and the
        next pass reuses the stage and finishes into the same folder. Once archived, meta.json is rewritten at once with
        the new year (no last day yet), so a pass that fails later never archives the new season a second time."""
        meta = read_json(os.path.join(out, 'meta.json'))
        stored, year = year_of(meta.get('season_year')) if meta else None, year_of(assoc.get('season_year'))
        if stored is None or year is None or stored == year:
            return None
        stage = os.path.join(out, 'past', '.rolling-%d' % stored)
        os.makedirs(stage, exist_ok=True)
        shutil.copyfile(os.path.join(out, 'meta.json'), os.path.join(stage, 'meta.json'))
        for entry in SEASON_ENTRIES:
            if os.path.lexists(os.path.join(out, entry)):
                os.replace(os.path.join(out, entry), os.path.join(stage, entry))
        name, n = str(stored), 1
        while os.path.exists(os.path.join(out, 'past', name)):
            n += 1
            name = '%d-%d' % (stored, n)
        os.replace(stage, os.path.join(out, 'past', name))
        # The new season's meta.json now, not at the end of the pass: a later step that raises would otherwise leave
        # the old year in place, and the next pass would archive again (past/<year>-2, with this season's stories).
        write_json(os.path.join(out, 'meta.json'), {'assn': stem, 'name': assoc.get('name'), 'season_year': year,
                                                    'updated': now_iso(), 'last_day': None, 'played': 0,
                                                    'stories': 0})
        self.log('%s season %d news archived to past/%s' % (stem, stored, name))
        return name

    def rewind(self, stem, out, assoc):
        """A restored ASN backup puts the association back in time inside one season. When meta.json holds the same
        season year and a last_day later than the association's own (or the association has played nothing), the
        abandoned days' stories (recaps/ with a month and day after the new last day), columns (feed/<MM>-<DD>.json)
        and awards.json move to <out>/past/rewind-<UTC YYYYmmddTHHMMSS>/ (-2, -3 ... for a name already taken;
        meta.json is copied), so the re-simmed games get stories again. Everything else stays. Returns that folder's
        name, or None when there was no rewind. An OSError part way propagates to scan(), which logs it; what was not
        moved stays, and the next pass tries again."""
        meta = read_json(os.path.join(out, 'meta.json'))
        if not isinstance(meta, dict):
            return None
        year, old = year_of(meta.get('season_year')), meta.get('last_day')
        if year is None or year != year_of(assoc.get('season_year')):
            return None
        if not (isinstance(old, list) and len(old) == 2 and all(type(v) is int for v in old)):
            return None
        now = feed.last_day(assoc)
        if now is not None and not tuple(now) < tuple(old):
            return None
        after = lambda month, day: now is None or (month, day) > tuple(now)
        base = 'rewind-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime())
        name, n = base, 1
        while os.path.exists(os.path.join(out, 'past', name)):
            n += 1
            name = '%s-%d' % (base, n)
        dest = os.path.join(out, 'past', name)
        os.makedirs(dest)
        shutil.copyfile(os.path.join(out, 'meta.json'), os.path.join(dest, 'meta.json'))
        stories = columns = 0
        rdir, fdir = os.path.join(out, 'recaps'), os.path.join(out, 'feed')
        for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
            r = read_json(os.path.join(rdir, f)) if f.endswith('.json') else None
            if isinstance(r, dict) and type(r.get('month')) is int and type(r.get('day')) is int \
                    and after(r['month'], r['day']):
                os.makedirs(os.path.join(dest, 'recaps'), exist_ok=True)
                os.replace(os.path.join(rdir, f), os.path.join(dest, 'recaps', f))
                stories += 1
        for f in sorted(os.listdir(fdir)) if os.path.isdir(fdir) else []:
            m = re.fullmatch(r'([0-9]{2})-([0-9]{2})\.json', f)
            if m and after(int(m.group(1)), int(m.group(2))):
                os.makedirs(os.path.join(dest, 'feed'), exist_ok=True)
                os.replace(os.path.join(fdir, f), os.path.join(dest, 'feed', f))
                columns += 1
        if os.path.lexists(os.path.join(out, 'awards.json')):
            os.replace(os.path.join(out, 'awards.json'), os.path.join(dest, 'awards.json'))
        # meta.json now says the new last day, so a pass that fails before association() rewrites it does not rewind
        # again (one empty past/rewind-* folder per pass)
        write_json(os.path.join(out, 'meta.json'), dict(meta, last_day=list(now) if now is not None else None))
        self.log('%s rewound from %02d-%02d to %s: %d stories, %d columns moved to past/%s' % (
            stem, old[0], old[1], 'opening day' if now is None else '%02d-%02d' % tuple(now), stories, columns, name))
        return name

    def archived(self, out):
        """Keys of the box scores whose stories (or captures) a rollover moved to <out>/past/*/."""
        keys = set()
        for sub in ('recaps', 'pending'):
            for path in pathlib.Path(out, 'past').glob('*/' + sub + '/*.json'):
                keys.add(path.stem)
        return keys

    def history_piece(self, assoc, stem, dat):
        """Archives each simulated season's lines for the player card's Career tab (history.py), once per season: this
        season when every game is played (the rosters then are the season's own), else last season, but only when some
        game of the season was seen being played, so a rollover that moved the date on without the game rewriting the
        stats never archives a stock line as a sim season. Each player's team is the one whose roster holds him at the
        time."""
        year = assoc.get('season_year')
        if dat is None or type(year) is not int or not assoc['teams']:
            return
        games = assoc.get('games') or []
        played = year if any(g.get('played') for g in games) else None
        if played is not None and history.mark_seen(self.data, stem, year):
            self.log('%s history %d seen' % (stem, year))
        teams = {pid: t['name'] for t in assoc['teams'].values() for pid in t['roster']}
        for scope, y in ((1, year), (3, year - 1)):
            if scope == 1 and not season.complete(assoc):
                continue
            if scope == 3 and y not in history.seen_years(self.data, stem):
                continue
            if os.path.exists(history.archive_path(self.data, stem, y)):
                continue
            lines = gamedata.season_lines(dat, scope)
            if any(line.get('g') for kind in lines.values() for line in kind.values()):
                if history.archive_season(self.data, stem, y, lines, teams if scope == 1 else None):
                    self.log('%s history %d archived' % (stem, y))

    def hof_piece(self, out, assoc, stem, pyr):
        """The Hall of Fame (hof.py), once per season year: when hof.json is missing or holds an earlier year's ballot
        and a history archive exists, this season year's ballot is held and hof.json written (an association with no
        history, a real-only one, writes nothing). Then every inductee without a story gets one in
        hof/<year>-<pid>.json: the model's while this scan has HOF_CALLS left (the rest wait for later scans, the stem
        staying in hof_open), the template when there is no model. A hof.json that does not parse is left alone and
        logged once. A read that fails (a torn PYR or PYF, a bad Lahman file) is logged and the ballot tried again on
        the next pass; the pieces after this one still run."""
        path = os.path.join(out, 'hof.json')
        old = read_json(path)
        if old is None and os.path.lexists(path):
            if stem not in self.hof_bad:
                self.hof_bad.add(stem)
                self.log('%s hof: hof.json does not parse, left alone' % stem)
            return
        year = year_of(assoc.get('season_year'))
        try:
            if year is not None and pyr is not None and hof.due(old, year):
                new = self.hof_ballot(stem, assoc, pyr, old, year)
                if new is not None:
                    write_json(path, new)
                    self.log('%s hof %d: %d inducted, %d on the ballot' % (
                        stem, year, sum(1 for e in new['inducted'] if e.get('year') == year), len(new['ballot'])))
                    old = new
            if old is not None:
                self.hof_stories(out, assoc, old)
        except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error, sqlite3.Error) as e:
            self.log('%s hof: %s: %s' % (stem, type(e).__name__, e))

    def hof_ballot(self, stem, assoc, pyr, old, year):
        """hof.run's hof dict for the ballot of season year, or None when it cannot be held yet: no history archive or
        no teams, no PYF beside the PYR, or the PYR or PYF younger than SETTLE (a retired player is one no roster and
        not the free-agent list holds, so a half-saved set would retire free agents). A retired player's last line is
        his last archived season, so only players with one in the window are looked up in the Lahman database (when
        there is one: none, or a failing one, leaves their real seasons out) and read from the PYR for the lookup."""
        if not hof.archive_years(self.data, stem) or not assoc['teams']:
            return None
        pyf = gamedata.find(os.path.dirname(pyr), os.path.splitext(os.path.basename(pyr))[0] + '.PYF')
        if pyf is None or time.time() - max(os.stat(p).st_mtime for p in (pyr, pyf)) < SETTLE:
            return None
        free = gamedata.free_agents(pyf)
        index = hof.sim_index(self.data, stem)
        rostered = {pid for t in assoc['teams'].values() for pid in t['roster']}
        players = gamedata.players(pyr)
        found = {}
        for pid, p in players.items():
            if pid in rostered or pid in free:
                continue
            rows = history.drop_seeded(index[hof.kind_of(p['pos'])].get(pid, []), stem)
            if rows and hof.MIN_WAIT <= year - rows[-1]['year'] <= hof.MAX_WAIT:
                found[pid] = rows
        who = {}
        for rec in gamedata._records(pyr) if found else ():
            pid = rec[0] | rec[1] << 8
            if pid in found:
                try:
                    born = datetime.date.fromordinal(struct.unpack_from('<I', rec, gamedata.P_BORN)[0] - 365)
                except (ValueError, OverflowError):
                    born = None
                who[pid] = (gamedata.cstr(rec[30:47]), gamedata.cstr(rec[47:64]), born)
        start, conn, careers = history.start_year(stem, year), self.hof_db(), []
        try:
            for pid in sorted(found):
                first, last, born = who[pid]
                kind, real = hof.kind_of(players[pid]['pos']), []
                if conn is not None and born is not None:
                    try:
                        lid = history.lahman_id(conn, first, last, born)
                        real = history.real_seasons(conn, lid, kind, before=start) if lid else []
                    except sqlite3.Error:
                        real = []
                careers.append({'pid': pid, 'name': players[pid]['name'], 'pos': players[pid]['pos'], 'gone': True,
                                'rows': history.merge(real, found[pid], start)})
        finally:
            if conn is not None:
                conn.close()
        return hof.run(old, year, careers, stem, now_iso())

    def hof_db(self):
        """A read-only connection to the Lahman database (the --db file, else history.find_db), or None without one."""
        path = self.db if self.db and os.path.isfile(self.db) else history.find_db()
        if not path:
            return None
        try:
            return history.open_db(path)
        except sqlite3.Error:
            return None

    def hof_stories(self, out, assoc, doc):
        """The induction story of each inductee in doc (an hof dict) that has none, written to hof/<year>-<pid>.json,
        then hof.json with each story key set. With the model on, at most HOF_CALLS stories a scan and none once the
        day's budget is spent (a template written then would stand for good); the stem stays in hof_open until every
        inductee has one. A story file already on disk (hof.json not updated after it) is only linked. An entry without
        the fields a story is built from is left alone."""
        stem, entries = os.path.basename(out), doc.get('inducted')
        todo = [e for e in entries if isinstance(e, dict) and e.get('story') is None and type(e.get('pid')) is int
                and type(e.get('year')) is int] if isinstance(entries, list) else []
        changed = False
        for e in todo:
            key = hof.story_key(e['year'], e['pid'])
            dest = os.path.join(out, 'hof', key + '.json')
            if not os.path.exists(dest):
                try:
                    facts = hof.story_facts(e, assoc['name'])
                except (KeyError, TypeError):
                    continue
                if self.complete is not None and self.hof_left <= 0:
                    self.hof_open.add(stem)
                    break
                if self.complete is not None:
                    self.hof_left -= 1
                piece = _llm_or_template(hof.write, facts, self.budget, self.complete)
                if piece is not None and piece.get('reason') == 'budget':
                    self.hof_open.add(stem)
                    break
                if piece is None:
                    piece = dict(hof.template(facts), source='template', reason='off')
                write_json(dest, dict(piece, kind='hof', pid=e['pid'], year=e['year'], name=e['name'], facts=facts,
                                      created=now_iso()))
                self.log('%s hof story %s (%s)' % (stem, e['name'], piece['source']))
            e['story'] = key
            changed = True
        else:
            self.hof_open.discard(stem)
        if changed:
            write_json(os.path.join(out, 'hof.json'), doc)
    def records_piece(self, out, assoc, names, pyr):
        """The record book (records.py) in records.json: the best single seasons and careers of the archived seasons
        and the bar a chase is measured against (the best Lahman season before the association's start year, or a
        simulated season that beat it). Rebuilt only when the set of archived years differs from the 'years' the file
        holds, which the first pass without a file also counts as; a pass in between lists one folder and reads
        nothing. Needs the PYR (the names). The Lahman database is --db, else history.find_db; without one, or when it
        cannot be read (logged), the book is simulated seasons only. Nothing is written while no season is archived
        and there is no bar either. A failure is logged and does not stop the other pieces."""
        stem = os.path.basename(out)
        if pyr is None:
            return
        try:
            years = records.archived_years(self.data, stem)
            path = os.path.join(out, 'records.json')
            prev = read_json(path)
            if prev is not None and prev.get('years') == years:
                return
            season_year = year_of(assoc.get('season_year'))
            start = history.start_year(stem, season_year)
            played = records.playable(records.read_archives(self.data, stem), stem)
            games = records.schedule_length(assoc) or None
            lahman, real = {}, {}
            db = self.db if self.db and os.path.isfile(self.db) else history.find_db()
            if db and start is not None:
                try:
                    conn = history.open_db(db)
                    try:
                        lahman = records.lahman_bar(conn, start, games)
                        if played:      # careers are only worth the lookups once a season is archived
                            people = identities(pyr)
                            real = records.real_careers(conn, {p: people[p] for p in names if p in people}, start)
                    finally:
                        conn.close()
                except sqlite3.Error as e:
                    self.log('%s records: %s' % (stem, e))
                    lahman, real = {}, {}
            doc = records.document(stem, now_iso(), years, played, names, real, lahman, games, start)
            if not played and not doc['bar']:
                return
            write_json(path, doc)
            self.log('%s records through %d (%d years archived)' % (stem, doc['through'], len(years)))
        except Exception as e:      # the record book is extra: a bad file or database must not stop the pieces after it
            self.log('%s records: %s: %s' % (stem, type(e).__name__, e))

    def chase_lines(self, out, assoc, names, season):
        """records.chase for this season's lines against the bar in records.json: [] without the file or its 'bar'."""
        bars = (read_json(os.path.join(out, 'records.json')) or {}).get('bar')
        if not isinstance(bars, dict):
            return []
        team_of = {pid: tid for tid, t in assoc['teams'].items() for pid in t['roster']}
        return records.chase(season, names, team_of, records.team_games(assoc), records.schedule_length(assoc), bars)

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

    def births(self, stem):
        """{pid: birth serial} from the association's PYR, or None without one or when it cannot be read."""
        try:
            pyr = gamedata.find(os.path.join(self.game, 'Assn'), stem + '.PYR')
            return focus.births(pyr) if pyr else None
        except (OSError, ValueError, struct.error):
            return None

    def following(self, stem, out):
        """{pid: birth} for the players follow.json names, without those the PYR contradicts (myplayer.matching: an id a
        new player reused). {} without the file or any player; the PYR is read only when someone is followed, and one
        that cannot be read drops nobody."""
        follows = myplayer.followed(read_json(os.path.join(out, 'follow.json')))
        return myplayer.matching(follows, self.births(stem)) if follows else {}

    def player_page(self, out, pid, name, year):
        """The page data of pid for the season `year`: player/<pid>.json, or a new page when there is none (or it does
        not parse). A file of another season is moved to player/<pid>-<its year>.json first (-2, -3 ... for a name
        already taken), so a new season starts with no games and no columns."""
        path = os.path.join(out, 'player', '%d.json' % pid)
        page = read_json(path)
        if page is None:
            return myplayer.new_page(pid, name, year)
        if myplayer.rolled(page, year):
            base, n = os.path.join(out, 'player', '%d-%d' % (pid, page['season_year'])), 1
            dest = base + '.json'
            while os.path.exists(dest):
                n += 1
                dest = '%s-%d.json' % (base, n)
            os.replace(path, dest)
            return myplayer.new_page(pid, name, year)
        for key in ('games', 'columns'):
            if not isinstance(page.get(key), list):
                page[key] = []
        page.update(pid=pid, name=name)
        if year is not None:
            page['season_year'] = year
        return page

    def save_player(self, out, page):
        """Writes the page data to player/<pid>.json with 'updated' set, unless the file already holds the same page
        apart from that. True when it wrote."""
        page = json.loads(json.dumps(page))
        path = os.path.join(out, 'player', '%d.json' % page['pid'])
        old = read_json(path)
        bare = lambda d: {k: v for k, v in d.items() if k != 'updated'}
        if old is not None and bare(old) == bare(page):
            return False
        write_json(path, dict(page, updated=now_iso()))
        return True

    def log_games(self, out, assoc, names, box, game, follows):
        """Adds one matched regular-season game to the log of each followed player (follows is {pid: birth}) who has
        a batting or pitching line in its box score (myplayer.game_line). A game a log already has, by (month, day,
        slot), is not added again."""
        abbrevs = {tid: t['abbrev'] for tid, t in assoc['teams'].items()}
        year = year_of(assoc.get('season_year'))
        for pid in follows:
            line = myplayer.game_line(box, game, pid, abbrevs)
            if line is None:
                continue
            page = self.player_page(out, pid, recap.name_of(names, pid), year)
            games = myplayer.append_game(page['games'], line)
            if games != page['games']:
                page['games'] = games
                self.save_player(out, page)

    def focus_entries(self):
        """focus.parse of <game>/Mods/focus.txt: [] when Mods or the file is missing, Mods is a symlink or the file is
        not a regular file. At most focus.MAX_FILE bytes are read. Read only; the bridge writes the file."""
        mods = os.path.join(self.game, 'Mods')
        path = os.path.join(mods, 'focus.txt')
        try:
            if os.path.islink(mods) or not stat.S_ISREG(os.lstat(path).st_mode):
                return []
            with open(path, 'rb') as fh:
                return focus.parse(fh.read(focus.MAX_FILE).decode('latin-1'))
        except OSError:
            return []

    def career_totals(self, stem, pid, kind, line, year, who, conn):
        """history.totals (plus 'kind') over a player's seasons, or None when he has none: his real seasons before the
        association's start year (when conn, the Lahman database, finds him by `who`, (first, last, born)), the
        archived simulated seasons, and this season's `line` unless that season is archived already."""
        start, real = history.start_year(stem, year), []
        if conn is not None and who is not None and who[2] is not None:
            try:
                lid = history.lahman_id(conn, *who)
                real = history.real_seasons(conn, lid, kind, before=start) if lid else []
            except sqlite3.Error:
                real = []
        sim = history.drop_seeded(history.sim_seasons(self.data, stem, pid, kind), stem)
        keys = history.BAT_KEYS if kind == 'bat' else history.PIT_KEYS
        if line and line.get('g') and year is not None and not any(r['year'] == year for r in sim):
            sim.append(dict({k: line.get(k, 0) for k in keys}, year=year, team=''))
        rows = history.merge(real, sim, start)
        return dict(history.totals(rows, kind), kind=kind) if rows else None

    def weekly_column(self, stem, page, games, facts):
        """Adds the weekly column over `games` (myplayer.window) to page['columns']: the model's while this scan has
        FOLLOW_CALLS left, else it waits (the stem stays in follow_open), and so does a spent budget; the template when
        there is no model or the model does not give a column that passes recap.numbers_ok."""
        if self.complete is not None and self.follow_left <= 0:
            self.follow_open.add(stem)
            return
        if self.complete is not None:
            self.follow_left -= 1
        piece = _llm_or_template(myplayer.write, facts, self.budget, self.complete)
        if piece is not None and piece.get('reason') == 'budget':
            self.follow_open.add(stem)
            return
        if piece is None:
            piece = dict(myplayer.template(facts), source='template', reason='off')
        page['columns'].append(myplayer.column(piece, facts, games))
        self.log('%s follow column %s (%s)' % (stem, facts['name'], piece['source']))

    def follow_piece(self, out, assoc, lines, pyr):
        """My Player (myplayer.py): the page data of each followed player present in the PYR, written to
        player/<pid>.json after the game log recaps() keeps in it. A follow whose birth serial no longer matches the PYR
        is skipped. The page gets his team, position, age, this season's lines, his career totals (history, plus his
        real seasons when the Lahman database finds him), his contract, the offseason focus as a training plan
        (focus.txt, read only), the arc hint and his moves-log events newest first. When WEEK or more games are logged
        after the last column's date a weekly column over them is added (weekly_column). Nothing is read or written
        without a follow.json that names players."""
        stem = os.path.basename(out)
        self.follow_open.discard(stem)
        follows = myplayer.followed(read_json(os.path.join(out, 'follow.json')))
        if not follows or pyr is None:
            return
        try:
            births, players = focus.births(pyr), gamedata.players(pyr)
        except (OSError, ValueError, struct.error) as e:
            self.log('%s follow: %s: %s' % (stem, type(e).__name__, e))
            return
        live = [pid for pid in myplayer.matching(follows, births) if pid in players]
        if not live:
            return
        year, entries = year_of(assoc.get('season_year')), self.focus_entries()
        events = (read_json(os.path.join(out, 'moves', 'log.json')) or {}).get('events')
        book = (read_json(os.path.join(out, 'contracts.json')) or {}).get('contracts')
        tally = recap.tally(assoc['games'])
        rosters = {pid: tid for tid, t in assoc['teams'].items() for pid in t['roster']}
        conn = self.hof_db()
        try:
            who = identities(pyr) if conn is not None else {}
        except (OSError, ValueError, struct.error):
            who = {}
        try:
            free = gamedata.free_agents(gamedata.find(os.path.dirname(pyr), stem + '.PYF'))
        except (OSError, ValueError, TypeError):
            free = None         # no readable PYF: a player on no roster is not called free or retired
        try:
            for pid in live:
                p, tid = players[pid], rosters.get(pid)
                page = self.player_page(out, pid, p['name'], year)
                kind = 'pit' if p['pos'] == 'P' else 'bat'
                season_line = {k: lines[k].get(pid) for k in ('bat', 'pit')}
                if tid is not None:
                    team = assoc['teams'][tid]['name']
                else:
                    team = '' if free is None else 'Free agent' if pid in free else 'Retired'
                contract = book.get(str(pid)) if isinstance(book, dict) else None
                page.update(
                    pos=p['pos'], team=team, season=season_line,
                    age=year - p['born'] if year is not None and p['born'] is not None else None,
                    career=self.career_totals(stem, pid, kind, season_line[kind], year, who.get(pid), conn),
                    contract=contract if isinstance(contract, dict) else None,
                    plan=myplayer.plan_text(focus.find(entries, pid, births[pid])),
                    arc=arc.player_hint(pid, births[pid], year),
                    milestones=myplayer.milestones(events if isinstance(events, list) else [], pid))
                games = myplayer.window(page['games'], page['columns'])
                if games:
                    w, l = tally.get(tid, (0, 0))
                    facts = myplayer.week_facts(p['name'], games, season_line, {'w': w, 'l': l})
                    self.weekly_column(stem, page, games, facts)
                self.save_player(out, page)
        finally:
            if conn is not None:
                conn.close()

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

    def postseason_piece(self, out, assoc, asn_path):
        """The postseason page's file (bracket.py): a template while the bracket is being played, and once it is
        complete with a champion, the model's wrap (bracket.write) with the template as the fallback. The ASN's bracket
        is this season's while its games are on the schedule (written to <out>), else it is last season's, still there
        after a rollover (written to past/<year - 1>/, and only when that folder exists). Nothing is written before a
        game is played or when the file already holds the same facts, so a new game rewrites it and a quiet pass does
        not (one ask of the model, whatever it came back with)."""
        try:
            b = gamedata.postseason(asn_path)
        except Exception:   # OSError, ValueError, or a file it cannot index (torn): the other pieces still run
            return
        year = year_of(assoc.get('season_year'))
        if b is None or year is None:
            return
        target, dest = (year, out) if b['current'] else (year - 1, os.path.join(out, 'past', str(year - 1)))
        if not b['current'] and not os.path.isdir(dest):
            return
        f = json.loads(json.dumps(bracket.facts(assoc, b, target)))
        path = os.path.join(dest, 'postseason.json')
        if not bracket.played(f) or (read_json(path) or {}).get('facts') == f:
            return
        if f['complete'] and f['champion']:
            story = _llm_or_template(bracket.write, f, self.budget, self.complete)
            if story is None:
                story = dict(bracket.template(f), source='template', reason='off')
        else:
            story = dict(bracket.template(f), source='template')
        write_json(path, dict(story, kind='postseason', facts=f, created=now_iso()))
        self.log('%s postseason %d (%d games) (%s)' % (
            os.path.basename(out), target,
            sum(len(s['games']) for r in f['rounds'] for s in r['series']), story['source']))

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
        try:
            births = focus.births(pyr)          # the birth serials the scouting hint reads; without them, no hint
        except (OSError, ValueError):
            births = None
        last = gamedata.season_lines(dat, scope=3) if dat else {'bat': {}, 'pit': {}}
        year = assoc.get('season_year')
        if type(year) is not int:
            year = scout.year_of(assoc['name'])
        public = lambda p, pid: fog.view(p, stem, 0, year, pid=pid)     # what the newspaper's scouts see
        for tid in todo:
            if self.complete is not None and self.scout_left <= 0:
                self.scouting_open.add(stem)
                return
            team = assoc['teams'][tid]
            facts = scout.team_facts(assoc, tid, players, last, year, public)
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
                            roster=scout.roster(assoc, tid, players, year, births, public), created=now_iso()))
            self.log('%s scout %s (%s)' % (stem, team['abbrev'], piece['source']))
        self.scouting_open.discard(stem)

    def rookie_class(self, out, assoc, pyr):
        """The rookie class (rookies.py), written once per season. rookies/ids.json holds the players of the season last
        seen. Without it the PYR is read once as the baseline, and no class is written. At a rollover (the stem is in
        rookies_due, kept until this succeeds, or the snapshot records another season than this one, which survives a
        restart) the players new since that snapshot are the class, written to rookies/<season_year>.json unless that
        file exists, and the snapshot becomes the new season's. Other passes do not read the PYR. Nothing is written
        for an empty PYR, which would make every player of the next season new."""
        stem = os.path.basename(out)
        if pyr is None:
            return
        path = os.path.join(out, 'rookies', 'ids.json')
        prev = read_json(path)
        year = year_of(assoc.get('season_year'))
        due = stem in self.rookies_due or (isinstance(prev, dict) and year_of(prev.get('season')) is not None
                                           and year is not None and prev['season'] != year)
        if prev is not None and not due:
            return
        players = gamedata.players(pyr)
        if not players:
            return
        dest = os.path.join(out, 'rookies', '%s.json' % year)
        pids = rookies.newcomers(players, prev) if due else []
        if pids and year is not None and not os.path.exists(dest):
            facts = rookies.class_facts(assoc, players, pids, year)
            piece = _llm_or_template(rookies.write, facts, self.budget, self.complete)
            if piece is None:
                piece = dict(rookies.template(facts), source='template', reason='off')
            write_json(dest, dict(piece, kind='rookies', season=year, facts=facts, created=now_iso()))
            self.log('%s rookie class %d: %d players (%s)' % (stem, year, len(pids), piece['source']))
        write_json(path, rookies.snapshot(players, year))
        self.rookies_due.discard(stem)

    def draft_piece(self, out, assoc, pyr):
        """The draft room (draft.py), no model. Once a season's rookie class is written (rookies/<season_year>.json) and
        draft/<season_year>.json is not, the class is written there as the public scouts saw it, with the team grades.
        Three seasons on or later (the season year >= the draft's + 3) a draft without a revisit gets one, once: the true
        grades now, the sim seasons played (history archives) and the regraded teams. A class of an earlier season is
        never drafted late. Only the folder listing and the older draft files are read unless there is something to
        write; the PYR is read only then. The revisit waits for a PYR and PYF that have sat SETTLE seconds and a
        readable PYF (without it a free agent would be called retired, for good)."""
        stem = os.path.basename(out)
        year = year_of(assoc.get('season_year'))
        if pyr is None or year is None or not assoc['teams']:
            return
        folder = os.path.join(out, 'draft')
        rookie_file = os.path.join(out, 'rookies', '%d.json' % year)
        new = os.path.exists(rookie_file) and not os.path.exists(os.path.join(folder, '%d.json' % year))
        due = self.revisits_due(folder, year)
        free = None
        if due:
            pyf = gamedata.find(os.path.dirname(pyr), os.path.splitext(os.path.basename(pyr))[0] + '.PYF')
            try:
                if pyf is not None and time.time() - max(os.stat(p).st_mtime for p in (pyr, pyf)) >= SETTLE:
                    free = gamedata.free_agents(pyf)
            except (OSError, ValueError):
                pass
            if free is None:
                due = []    # a torn or missing PYF/PYR pair would call a free agent retired, for good: retry next scan
        if not new and not due:
            return
        players = gamedata.players(pyr)
        if not players:
            return
        rosters = season._players(assoc)
        if new:
            pids = draft.class_pids(read_json(rookie_file))
            doc = draft.build(year, stem, pids, players, rosters, {tid: t['name'] for tid, t in assoc['teams'].items()})
            if doc['picks']:
                write_json(os.path.join(folder, '%d.json' % year), dict(doc, created=now_iso()))
                self.log('%s draft %d: %d picks' % (stem, year, len(doc['picks'])))
        if not due:
            return
        retired = set(players) - {pid for pids in rosters.values() for pid in pids} - free
        archives = self.archives(stem, min(y for y, _ in due))
        for y, doc in due:
            pids = [pick['pid'] for pick in doc['picks']]
            rev = draft.revisit(doc, year, players, retired, draft.seasons_played(archives, pids, y))
            write_json(os.path.join(folder, '%d.json' % y), dict(doc, revisit=rev))
            self.log('%s draft %d revisited in %d: %d picks' % (stem, y, year, len(pids)))

    def revisits_due(self, folder, year):
        """[(draft year, draft)], oldest first, for each draft/<YYYY>.json that is REVISIT_AFTER seasons or more older than
        `year`, holds picks and teams, and has no revisit yet. The folder is only listed, and a file is read only when
        its name makes it old enough."""
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return []
        due = []
        for name in names:
            if re.fullmatch(r'[0-9]{4}\.json', name) and int(name[:4]) + draft.REVISIT_AFTER <= year:
                doc = read_json(os.path.join(folder, name))
                if doc and doc.get('revisit') is None and isinstance(doc.get('picks'), list) \
                        and isinstance(doc.get('teams'), list):
                    due.append((int(name[:4]), doc))
        return due

    def archives(self, stem, since):
        """[(year, doc)] for each readable history archive (history/<YYYY>.json) of year `since` or later, oldest first."""
        folder = os.path.dirname(history.archive_path(self.data, stem, since))
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return []
        found = ((int(n[:4]), read_json(os.path.join(folder, n))) for n in names if history.SIM_FILE_RE.fullmatch(n))
        return [(y, doc) for y, doc in found if y >= since and doc is not None]

    def moves(self, out, assoc, pyr, dat):
        """Roster moves and milestones since the last scan (moves.py). The current snapshot is diffed against last.json;
        the events go to the end of log.json, which keeps MOVE_KEEP and counts every event ever logged, so a note's
        number never changes; then the snapshot becomes last.json, before any note is written, so a pass that stops
        on a failed note write never logs its events again. Each notable event gets a note; a note of this season that
        is still missing from an earlier pass is written on a later one (at most MOVE_CATCHUP a pass). Nothing is
        written without the PYR, the PYF beside it (the free agents) or the stats (DAT), or while one is younger than
        SETTLE."""
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
            kept = (kept + events)[-MOVE_KEEP:]
            write_json(log_path, {'events': kept, 'count': count + len(events)})
            self.log('%s moves: %d' % (stem, len(events)))
        write_json(os.path.join(mdir, 'last.json'), dict(cur, date=date))
        for ev in events:
            if 'note' in ev:
                self._move_note(mdir, stem, assoc, cur, ev, date)
        left = MOVE_CATCHUP
        for ev in kept:
            if left <= 0:
                break
            if (type(ev.get('note')) is not int or ev.get('year') != cur['year']
                    or any(k not in ev for k in ('pid', 'kind', 'name'))
                    or os.path.exists(os.path.join(mdir, 'notes', '%d.json' % ev['note']))):
                continue
            try:
                self._move_note(mdir, stem, assoc, cur, ev, ev.get('date') or date)
            except (KeyError, TypeError):
                continue        # a logged event without the fields a note is built from is left alone
            left -= 1

    def _move_note(self, mdir, stem, assoc, cur, ev, date):
        """Write the note of one logged event to moves/notes/<note>.json: the model's while this scan has calls left,
        else the template."""
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

    def capture(self, stem):
        """Copy every new box score of this association into <data>/<ASSN>/pending/ as parsed JSON. The game keeps
        only the last seven sim days of box scores (Stats/<ASSN>.H<day><game>, the oldest day deleted as each new one
        is written), so this runs before every story the model is asked for, and a long sim loses nothing. A box
        score already archived under past/ is not captured again."""
        stats_dir = os.path.join(self.game, 'Stats')
        out = os.path.join(self.data, stem)
        past = self.archived(out)       # read once a pass, not once a box score
        for path in gamedata.box_files(stats_dir, stem):
            try:
                if time.time() - os.path.getmtime(path) < SETTLE:
                    continue
                with open(path, 'rb') as fh:
                    key = hashlib.sha1(fh.read()).hexdigest()[:16]
                if key in self.captured.setdefault(stem, set()) or key in past:
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

    def recaps(self, stem, out, assoc, names, stats_dir, asn_path=None):
        rdir, pdir = os.path.join(out, 'recaps'), os.path.join(out, 'pending')
        used, post_used = set(), set()
        follows = self.following(stem, out)      # {} unless players are followed (follow.json)
        if os.path.isdir(rdir):
            for f in os.listdir(rdir):
                r = read_json(os.path.join(rdir, f)) if f.endswith('.json') else None
                if r and all(k in r for k in ('month', 'day', 'slot')):
                    used.add((r['month'], r['day'], r['slot']))
                if r and isinstance(r.get('post'), dict) and all(k in r['post'] for k in ('round', 'series', 'game')):
                    post_used.add((r['post']['round'], r['post']['series'], r['post']['game']))
        self.capture(stem)
        pending = []
        for f in os.listdir(pdir) if os.path.isdir(pdir) else []:
            p = read_json(os.path.join(pdir, f)) if f.endswith('.json') else None
            if p and isinstance(p.get('box'), dict):
                pending.append(p)
        pending.sort(key=lambda p: (p.get('mtime', 0), p.get('file', '')), reverse=True)   # newest games first
        post = None     # (bracket, postseason schedule), read the first time a box fits no regular-season game
        for p in pending:
            key, box = p['key'], p['box']
            cands = [g for g in recap.in_order(gamedata.match_game(assoc, box))
                     if (g['month'], g['day'], g['slot']) not in used]
            if not cands:
                if post is None:
                    post = _postseason(asn_path)
                bracket, sched = post
                hit = recap.match_post(bracket, box, post_used) if bracket is not None else None
                if hit is None:
                    if key not in self.waiting:
                        self.waiting.add(key)
                        self.log('%s: %s matches no unreported played game yet' % (stem, p['file']))
                    continue
                rnd, si, gi = hit
                score = (box['away']['tid'], box['home']['tid'], box['away']['runs'], box['home']['runs'])
                g = next((x for x in sched if x['played'] and (x['away'], x['home'], x['away_runs'], x['home_runs'])
                          == score and (x['month'], x['day'], x['slot']) not in used), None)
                facts = recap.post_facts(assoc, box, bracket, rnd, si, gi, names, g)
                story = _llm_or_template(recap.post_write, facts, self.budget, self.complete)
                if story is None:
                    story = dict(recap.post_template(facts), source='template', reason='off')
                if g:
                    when = (g['month'], g['day'], g['slot'])
                else:       # no schedule record: sort after the regular season, in bracket order
                    last = max(((x['month'], x['day']) for x in assoc['games'] if x['played']), default=(0, 0))
                    when = last + (100 + 50 * (rnd - 1) + 8 * si + gi,)
                write_json(os.path.join(rdir, key + '.json'),
                           dict(story, key=key, assn=stem, month=when[0], day=when[1], slot=when[2], file=p['file'],
                                facts=facts, post={'round': rnd, 'series': si, 'game': gi}, created=now_iso()))
                os.remove(os.path.join(pdir, key + '.json'))
                post_used.add(hit)
                if g:
                    used.add(when)
                self.log('%s: %s %s -> %s (%s)' % (stem, facts['date'] or facts['round'], p['file'], key,
                                                    story['source']))
                if story['source'] == 'glm':
                    self.capture(stem)
                continue
            game = cands[-1]
            if follows:
                self.log_games(out, assoc, names, box, game, follows)
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

    def columns(self, out, assoc, names, season, asn_path=None, chase=None):
        """One 'Around the league' column per played date (and per postseason date). The last regular season date's
        facts carry the season lines and the chase lines (facts['chase']): chase, or when it is None the lines
        chase_lines finds against records.json. Earlier dates have no 'chase' key."""
        days = sorted({(g['month'], g['day']) for g in assoc['games'] if g['played']})
        bracket, sched = _postseason(asn_path) if asn_path is not None else (None, [])
        post_days = sorted({(g['month'], g['day']) for g in sched if g.get('played') and 'month' in g and 'day' in g}
                           - set(days))
        recent = set(sorted(days + post_days)[-LLM_DAYS:])
        empty = {'bat': {}, 'pit': {}}
        for month, day in days:
            dest = os.path.join(out, 'feed', '%02d-%02d.json' % (month, day))
            old = read_json(dest)
            last = (month, day) == days[-1]
            if last and chase is None:
                chase = self.chase_lines(out, assoc, names, season)
            facts = feed.day_facts(through(assoc, month, day), season if last else empty, names, month, day,
                                   chase if last else None)
            if old and old.get('facts', {}).get('results') == facts['results']:
                continue            # written, and no game of that date has been added since
            column = None
            if (month, day) in recent:
                column = _llm_or_template(feed.write, facts, self.budget, self.complete)
            if column is None:
                column = dict(feed.template(facts), source='template', reason='backfill' if self.complete else 'off')
            write_json(dest, dict(column, month=month, day=day, date=facts['date'], facts=facts, created=now_iso()))
            self.log('column %s %s (%s)' % (os.path.basename(out), facts['date'], column['source']))
        for month, day in post_days:
            dest = os.path.join(out, 'feed', '%02d-%02d.json' % (month, day))
            old = read_json(dest)
            facts = feed.post_day_facts(assoc, bracket, sched, month, day)
            if old and old.get('facts', {}).get('results') == facts['results']:
                continue
            column = None
            if (month, day) in recent:
                column = _llm_or_template(feed.post_write, facts, self.budget, self.complete)
            if column is None:
                column = dict(feed.post_template(facts), source='template',
                              reason='backfill' if self.complete else 'off')
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
        try:
            w.scan()
        except Exception as e:      # one bad pass (a file vanishing mid-read) must not end a watcher left running
            if a.once:
                raise
            print('scan failed: %s: %s' % (type(e).__name__, e), flush=True)
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == '__main__':
    main()
