"""The draft room for the news sidecar: a season's rookie class as the league's scouts saw it (fogged public grades, see
fog.py), which teams it fills a need for, a letter grade for each team's haul, and the same grades revisited three seasons
later against what the players became. Pure functions over plain dicts (gamedata.players() entries, season._players()
rosters, history archives); watch.draft_piece reads the files and writes <data>/<ASSN>/draft/<year>.json, server.py shows it.
"""
import statistics

import contracts
import fog
import rookies
import scout

HITTER_KEYS = ('contact', 'power', 'speed', 'fielding')     # the grades a pick shows: a hitter's ...
PITCHER_KEYS = ('control', 'strikeout', 'stamina')          # ... and a pitcher's
NEED_POSITIONS = scout.POSITION_ORDER   # C, 1B, 2B, 3B, SS, LF, CF, RF: a team needs a position it has no one at ...
NEED_BELOW = 45                         # ... graded at least this (mean grade), and arms ...
ARMS_WANTED = 11                        # ... when fewer than this many pitchers grade at least NEED_BELOW
BANDS = ((1.0, 'A'), (0.33, 'B'), (-0.33, 'C'), (-1.0, 'D'))    # (lowest z, grade); below the last is F
REVISIT_AFTER = 3                       # seasons after the draft the picks are looked at again
SEASON_VALUE = 2                        # index points a played sim season adds to a pick's value on revisit


def grades(player):
    """The 20-80 grades of a player on the page: contact, power, speed and fielding for a hitter, control, strikeout and
    stamina for a pitcher (position P). A rating that is None grades None."""
    keys = PITCHER_KEYS if player['pos'] == 'P' else HITTER_KEYS
    return {k: scout.grade(player[k]) for k in keys}


def _score(player):
    """The mean of a player's shown grades (a None is left out); 0.0 when there are none."""
    got = [g for g in grades(player).values() if g is not None]
    return sum(got) / len(got) if got else 0.0


def team_needs(players):
    """The needs of a team whose rostered players (fogged entries) are `players`: each of C, 1B, 2B, 3B, SS, LF, CF, RF
    whose best player, by the mean of contact, power, speed and fielding grades, is below NEED_BELOW (a position with no
    one is a need), in that order, then 'P' when fewer than ARMS_WANTED pitchers have a mean control, strikeout and
    stamina grade of NEED_BELOW or better."""
    needs = [pos for pos in NEED_POSITIONS
             if max((_score(p) for p in players if p['pos'] == pos), default=0.0) < NEED_BELOW]
    if sum(1 for p in players if p['pos'] == 'P' and _score(p) >= NEED_BELOW) < ARMS_WANTED:
        needs.append('P')
    return needs


def letters(values):
    """{key: 'A'..'F'} from {key: total}: the z score of each total among all of them (population sd) in BANDS, z >= 1 an
    A, z >= 0.33 a B, z >= -0.33 a C, z >= -1 a D, else F. One total, or all equal, is a C for every key."""
    if len(values) < 2:
        return {k: 'C' for k in values}
    mean, spread = statistics.fmean(values.values()), statistics.pstdev(values.values())
    out = {}
    for k, v in values.items():
        z = (v - mean) / spread if spread else 0.0
        out[k] = next((g for floor, g in BANDS if z >= floor), 'F')
    return out


def class_pids(rec):
    """The pids of a rookies/<year>.json record, hitters then pitchers: the ints under facts. [] for a record that has no
    facts or lists."""
    facts = rec.get('facts') if isinstance(rec, dict) else None
    rows = []
    for kind in ('hitters', 'pitchers'):
        if isinstance(facts, dict) and isinstance(facts.get(kind), list):
            rows += facts[kind]
    return [r['pid'] for r in rows if isinstance(r, dict) and type(r.get('pid')) is int]


def build(year, assn, pids, players, rosters, names):
    """The draft of `year` for association `assn`: {'year', 'picks', 'teams', 'revisit': None}. pids are the class
    (those not in `players` are skipped), players the PYR's true entries, rosters {tid: [pid]} as season._players() gives
    them (the picks are on them already), names {tid: team name}. Everything shown is the public fogged view of that year
    (fog.view, viewer 0): a pick's grades, its value (contracts._index of the fogged player) and its team's needs, which
    are read off the roster without the picks, so a pick can fill one. A pick is a free agent (tid None) when no roster
    lists him. Picks are best value first, then name; a team is listed for each team with a pick, best total first, and its
    grade is among those teams."""
    pickset = {pid for pid in pids if pid in players}
    team_of = {pid: tid for tid, ps in rosters.items() for pid in ps}

    def seen(pid):
        return fog.view(players[pid], assn, 0, year, pid=pid)

    needs = {}
    picks = []
    for pid in sorted(pickset):
        p, f = players[pid], seen(pid)
        tid = team_of.get(pid)
        if tid is not None and tid not in needs:
            needs[tid] = team_needs([seen(i) for i in rosters[tid] if i in players and i not in pickset])
        picks.append({'pid': pid, 'name': p['name'], 'pos': f['pos'],
                      'age': year - p['born'] if type(p['born']) is int else None,
                      'team': names.get(tid, '') if tid is not None else rookies.FREE_AGENT, 'tid': tid,
                      'grades': grades(f), 'value': float(contracts._index(f)),
                      'need': tid is not None and f['pos'] in needs[tid]})
    picks.sort(key=lambda r: (-r['value'], r['name'], r['pid']))
    return {'year': year, 'picks': picks, 'teams': _teams(picks, needs, names), 'revisit': None}


def _teams(picks, needs, names):
    """The team rows of a draft: {'tid', 'name', 'picks', 'value', 'grade', 'needs'} for each tid with a pick, best
    total first (then tid)."""
    total, count = {}, {}
    for r in picks:
        if r['tid'] is not None:
            total[r['tid']] = total.get(r['tid'], 0.0) + r['value']
            count[r['tid']] = count.get(r['tid'], 0) + 1
    grade = letters(total)
    rows = [{'tid': tid, 'name': names.get(tid, ''), 'picks': count[tid], 'value': total[tid], 'grade': grade[tid],
             'needs': needs[tid]} for tid in total]
    return sorted(rows, key=lambda t: (-t['value'], t['tid']))


def seasons_played(archives, pids, since):
    """{pid: n} for each of pids: how many of the archives, [(year, doc)] as history.archive_season wrote them, of a year
    since `since` or later hold a 'bat' or 'pit' line for him. A season counts once even with both lines."""
    out = dict.fromkeys(pids, 0)
    for year, doc in archives:
        if year < since:
            continue
        lines = [doc.get(kind) for kind in ('bat', 'pit')]
        for pid in pids:
            if any(isinstance(ln, dict) and isinstance(ln.get(str(pid)), dict) for ln in lines):
                out[pid] += 1
    return out


def revisit(doc, year, players, retired, seasons):
    """The revisit of a draft `doc` made in season `year`: {'year', 'teams', 'picks'}. players are the PYR's true entries
    now, retired the pids that are in the PYR but on no roster and in no free agent list, seasons {pid: sim seasons
    played}. Each pick (by str(pid)) gets its true grades now, its seasons, and a value of contracts._index of the true
    player plus SEASON_VALUE for each season played; a pick gone from the PYR or retired has no grades, a value of
    SEASON_VALUE per season, and gone True. Each team row of the draft is regraded on the sum of its own picks' new values,
    among the same teams, best first."""
    picks, value = {}, {}
    for pick in doc['picks']:
        pid, n = pick['pid'], seasons.get(pick['pid'], 0)
        p = players.get(pid)
        gone = p is None or pid in retired
        v = float(SEASON_VALUE * n) if gone else float(contracts._index(p) + SEASON_VALUE * n)
        picks[str(pid)] = {'grades': {} if gone else grades(p), 'seasons': n, 'value': v, 'gone': gone}
        if pick['tid'] is not None:
            value[pick['tid']] = value.get(pick['tid'], 0.0) + v
    names = {t['tid']: t['name'] for t in doc['teams']}
    grade = letters({tid: value.get(tid, 0.0) for tid in names})
    teams = [{'tid': tid, 'name': names[tid], 'grade': grade[tid], 'value': value.get(tid, 0.0)} for tid in names]
    return {'year': year, 'teams': sorted(teams, key=lambda t: (-t['value'], t['tid'])), 'picks': picks}
