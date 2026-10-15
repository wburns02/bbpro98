"""The record book of an association: the best single seasons and careers its simulated years produced, the bar they
are measured against (the best real season in the Lahman database before the association began, or a simulated season
that beat it), and the 'chase' lines for this season's players who are on pace for a record. Pure functions over dicts;
the only file readers are archived_years and read_archives, and the only database readers are lahman_bar and
real_careers, which take an open connection. watch.py writes <data>/<STEM>/records.json from these (document) and
reads its 'bar' back for the daily column (chase); server.py shows the file. Standard library only.
"""
import json
import os
import re
from fractions import Fraction

import history

SEASON_GAMES = 162      # the schedule length the qualifiers are written for
MIN_AB, MIN_OUTS = 400, 486             # a season's batting average and ERA qualifiers at SEASON_GAMES
MIN_CAREER_AB, MIN_CAREER_OUTS = 3000, 4500
TOP = 10
BAT_STATS = ('hr', 'h', 'rbi', 'r', 'sb', 'bb', 'avg')
PIT_STATS = ('w', 'so', 'sv', 'era')
STATS = BAT_STATS + PIT_STATS
COUNTING = {'bat': ('hr', 'h', 'rbi', 'sb'), 'pit': ('w', 'so', 'sv')}      # the stats a chase line can name
LABELS = {'hr': 'home runs', 'h': 'hits', 'rbi': 'RBI', 'sb': 'stolen bases', 'w': 'wins', 'so': 'strikeouts',
          'sv': 'saves'}
CHASE_FROM = (2, 5)     # a team must have played this fraction of the schedule before its players are chased
CHASE_NEAR = (9, 10)    # a pace at this fraction of the bar, or better, is a chase line
CHASE_MAX = 3
PID_RE = re.compile(r'[0-9]{1,9}')


def kind_of(stat):
    """'bat' or 'pit': the kind of line a stat in STATS is read from."""
    return 'bat' if stat in BAT_STATS else 'pit'


def _int(value):
    """value when it is an int (bool excluded), else 0."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def qualifiers(season_games=None):
    """(at bats, outs) a player needs in one season for a batting average or an ERA: 400 and 486 for a 162 game
    schedule, both scaled by season_games / 162 and rounded. A season_games that is not a positive int counts as 162."""
    games = season_games if type(season_games) is int and season_games > 0 else SEASON_GAMES
    return round(MIN_AB * games / SEASON_GAMES), round(MIN_OUTS * games / SEASON_GAMES)


def schedule_length(assoc):
    """The regular season's games per team: the scheduled games times two over the teams, rounded. 0 without teams."""
    teams = assoc.get('teams') or {}
    return round(len(assoc.get('games') or []) * 2 / len(teams)) if teams else 0


def team_games(assoc):
    """{tid: games played so far} from the schedule."""
    out = {}
    for g in assoc.get('games') or []:
        if g.get('played'):
            for side in ('away', 'home'):
                out[g[side]] = out.get(g[side], 0) + 1
    return out


def stat_value(stat, line, min_ab=MIN_AB, min_outs=MIN_OUTS):
    """The value of stat (one of STATS) in a season line: h / ab for avg, 27 * er / outs for era, the count for the
    rest. None when the line does not count: a count of 0, or an avg or era under its qualifier."""
    if stat == 'avg':
        ab = _int(line.get('ab'))
        return _int(line.get('h')) / ab if ab > 0 and ab >= min_ab else None
    if stat == 'era':
        outs = _int(line.get('outs'))
        return 27 * _int(line.get('er')) / outs if outs > 0 and outs >= min_outs else None
    value = _int(line.get(stat))
    return value if value > 0 else None


def better(stat, a, b):
    """True when value a is strictly better than b for stat: higher, except for era, where lower is better."""
    return a < b if stat == 'era' else a > b


def _rank(rows, stat):
    """The TOP best rows, best first; ties break by year (earlier first), then name, then pid."""
    sign = 1 if stat == 'era' else -1
    return sorted(rows, key=lambda r: (sign * r['value'], r.get('year', 0), r['name'], r['pid']))[:TOP]


def _name(names, pid):
    return names.get(pid) or 'Player %d' % pid


def archived_years(data_dir, stem):
    """The years that have a history archive (<data_dir>/<STEM>/history/<year>.json), ascending. A stem that is not a
    valid one, or a missing folder, gives []. File names only: nothing is opened."""
    if not isinstance(stem, str) or history.STEM_RE.fullmatch(stem) is None:
        return []
    try:
        names = os.listdir(os.path.join(data_dir, stem.upper(), 'history'))
    except OSError:
        return []
    return sorted(int(n[:4]) for n in names if history.SIM_FILE_RE.fullmatch(n))


def read_archives(data_dir, stem):
    """{year: {'bat': {pid: line}, 'pit': {pid: line}, 'team': {pid: label}}} for every readable archive, read as
    history.sim_seasons reads one: an unreadable or malformed file is skipped, a line value that is not an int is 0.
    Every id is an int; keys that are not numbers are dropped. Team lines (ids under 100) are kept as written."""
    out = {}
    for year in archived_years(data_dir, stem):
        try:
            with open(history.archive_path(data_dir, stem, year), encoding='utf-8') as f:
                doc = json.load(f)
        except (OSError, ValueError, RecursionError):
            continue
        if not isinstance(doc, dict):
            continue
        season = {}
        for kind, keys in (('bat', history.BAT_KEYS), ('pit', history.PIT_KEYS)):
            lines = doc.get(kind) if isinstance(doc.get(kind), dict) else {}
            season[kind] = {int(pid): {k: _int(line.get(k)) for k in keys} for pid, line in lines.items()
                            if PID_RE.fullmatch(str(pid)) and isinstance(line, dict)}
        teams = doc.get('team') if isinstance(doc.get('team'), dict) else {}
        season['team'] = {int(pid): label for pid, label in teams.items()
                          if PID_RE.fullmatch(str(pid)) and isinstance(label, str)}
        out[year] = season
    return out


def playable(archives, stem):
    """archives without the seasons history.drop_seeded drops for stem: the years before the start year the stem
    names, which are the build's copy of a real season and not one the game played."""
    keep = {row['year'] for row in history.drop_seeded([{'year': y} for y in archives], stem)}
    return {y: a for y, a in archives.items() if y in keep}


def season_tables(archives, names, season_games=None):
    """{stat: top TOP rows} of single seasons for every stat in STATS, each row {'pid', 'name', 'year', 'value',
    'team'}; [] for a stat nobody has. Only players (ids from 100) count. The batting average and ERA need the
    qualifiers(season_games). Best first (era lowest first); ties break by year, then name."""
    min_ab, min_outs = qualifiers(season_games)
    out = {}
    for stat in STATS:
        kind, rows = kind_of(stat), []
        for year, arch in archives.items():
            for pid, line in arch.get(kind, {}).items():
                value = stat_value(stat, line, min_ab, min_outs) if pid >= 100 else None
                if value is not None:
                    rows.append({'pid': pid, 'name': _name(names, pid), 'year': year, 'value': value,
                                 'team': arch.get('team', {}).get(pid) or ''})
        out[stat] = _rank(rows, stat)
    return out


def career_tables(archives, names, real=None, start=None):
    """{stat: top TOP rows} of careers for every stat in STATS, each row {'pid', 'name', 'value', 'seasons'}. A career
    is history.merge(real seasons, simulated seasons, start) summed by history.totals, for every player in names (the
    PYR's players). real is {'bat': {pid: seasons}, 'pit': {pid: seasons}} as real_careers gives it (none by default);
    archives are the simulated years, seeded ones already dropped. A career batting average needs MIN_CAREER_AB at
    bats and a career ERA MIN_CAREER_OUTS outs. Best first (era lowest first); ties break by name."""
    real = real or {}
    tables = {stat: [] for stat in STATS}
    for kind, stats in (('bat', BAT_STATS), ('pit', PIT_STATS)):
        for pid in names:
            sim = [dict(arch[kind][pid], year=year, team='') for year, arch in sorted(archives.items())
                   if pid in arch.get(kind, {})]
            rows = history.merge(real.get(kind, {}).get(pid, []), sim, start)
            if not rows:
                continue
            total = history.totals(rows, kind)
            for stat in stats:
                if stat == 'avg':
                    value = total['h'] / total['ab'] if total['ab'] >= MIN_CAREER_AB else None
                elif stat == 'era':
                    value = 27 * total['er'] / total['outs'] if total['outs'] >= MIN_CAREER_OUTS else None
                else:
                    value = total[stat] if total[stat] > 0 else None
                if value is not None:
                    tables[stat].append({'pid': pid, 'name': _name(names, pid), 'value': value,
                                         'seasons': total['seasons']})
    return {stat: _rank(rows, stat) for stat, rows in tables.items()}


def _num(value):
    """value as an int; NULL and anything that is not a number count as 0 (a SUM over NULLs is NULL)."""
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def lahman_bar(conn, before, season_games=None):
    """The best real single season of each stat in STATS among the Lahman seasons of years below before (all years
    when before is None), as {stat: {'value', 'name', 'year', 'source': 'lahman'}}; a stat nobody has is left out. A
    season sums a player's stints in the year and is judged by the same qualifiers(season_games) as a simulated one.
    Only the Batting, Pitching and People tables and the columns playerID, yearID, AB, H, HR, RBI, R, SB, BB, W, SO,
    SV, IPouts, ER, nameFirst and nameLast are read. A tie goes to the earlier year, then the name. sqlite3.Error
    propagates (a database without those tables)."""
    min_ab, min_outs = qualifiers(season_games)
    limit = 9999 if before is None else before
    best = {}       # stat -> [value, [(year, playerID)]]

    def offer(stat, value, year, pid):
        if value is None:
            return
        cur = best.get(stat)
        if cur is None or better(stat, value, cur[0]):
            best[stat] = [value, [(year, pid)]]
        elif value == cur[0]:
            cur[1].append((year, pid))

    bat = 'SELECT playerID, yearID, SUM(AB), SUM(H), SUM(HR), SUM(RBI), SUM(R), SUM(SB), SUM(BB) FROM Batting' \
          ' WHERE yearID < ? GROUP BY playerID, yearID'
    for pid, year, ab, h, hr, rbi, r, sb, bb in conn.execute(bat, (limit,)):
        line = dict(zip(('ab', 'h', 'hr', 'rbi', 'r', 'sb', 'bb'), map(_num, (ab, h, hr, rbi, r, sb, bb))))
        for stat in BAT_STATS:
            offer(stat, stat_value(stat, line, min_ab, min_outs), _num(year), pid)
    pit = 'SELECT playerID, yearID, SUM(W), SUM(SO), SUM(SV), SUM(IPouts), SUM(ER) FROM Pitching' \
          ' WHERE yearID < ? GROUP BY playerID, yearID'
    for pid, year, w, so, sv, outs, er in conn.execute(pit, (limit,)):
        line = dict(zip(('w', 'so', 'sv', 'outs', 'er'), map(_num, (w, so, sv, outs, er))))
        for stat in PIT_STATS:
            offer(stat, stat_value(stat, line, min_ab, min_outs), _num(year), pid)
    out = {}
    for stat, (value, held) in best.items():
        named = []
        for year, pid in held:
            row = conn.execute('SELECT nameFirst, nameLast FROM People WHERE playerID = ?', (pid,)).fetchone()
            named.append((year, ' '.join(x.strip() for x in (row or ()) if x and x.strip()) or str(pid), pid))
        year, name, _ = min(named)
        out[stat] = {'value': value, 'name': name, 'year': year, 'source': 'lahman'}
    return out


def real_careers(conn, people, before=None):
    """The real seasons of the players the Lahman database knows: {'bat': {pid: seasons}, 'pit': {pid: seasons}}, the
    seasons history.real_seasons gives for years below before. people is {pid: (first, last, born date or None)};
    history.lahman_id finds each, and a player without a birth date or a single match is left out, as is a kind he
    has no seasons of. sqlite3.Error propagates."""
    out = {'bat': {}, 'pit': {}}
    for pid, (first, last, born) in people.items():
        lid = history.lahman_id(conn, first, last, born) if born is not None else None
        if lid is None:
            continue
        for kind in out:
            rows = history.real_seasons(conn, lid, kind, before=before)
            if rows:
                out[kind][pid] = rows
    return out


def bar(lahman, season):
    """{stat: {'value', 'name', 'year', 'source'}}: for each stat the better of the Lahman entry (lahman_bar's
    output, source 'lahman') and the best simulated season (season_tables' first row, source 'sim'). The simulated
    season must be strictly better to take the bar; era is better lower. A stat with neither is left out."""
    out = {}
    for stat in STATS:
        pick = lahman.get(stat)
        rows = season.get(stat) or []
        if rows and (pick is None or better(stat, rows[0]['value'], pick['value'])):
            top = rows[0]
            pick = {'value': top['value'], 'name': top['name'], 'year': top['year'], 'source': 'sim'}
        if pick is not None:
            out[stat] = dict(pick)
    return out


def document(stem, updated, years, archives, names, real=None, lahman=None, season_games=None, start=None):
    """The records.json object. years is every archived year (archived_years), archives the played ones
    (playable); 'through' is the last of those, 0 when there are none. With no played year the career tables are
    empty: the book fills in after the first simulated season, but the bar can already come from lahman."""
    season = season_tables(archives, names, season_games)
    career = career_tables(archives, names, real, start) if archives else {stat: [] for stat in STATS}
    return {'stem': stem, 'updated': updated, 'through': max(archives, default=0), 'years': sorted(years),
            'season': season, 'career': career, 'bar': bar(lahman or {}, season)}


def _bar_of(bars, stat):
    """(value, name, year) of the bar for stat when it is a usable entry (a positive int value, a text name, an int
    year), else None."""
    entry = bars.get(stat) if isinstance(bars, dict) else None
    if not isinstance(entry, dict):
        return None
    value, name, year = entry.get('value'), entry.get('name'), entry.get('year')
    if _int(value) <= 0 or not isinstance(name, str) or _int(year) == 0:
        return None
    return value, name, year


def chase(lines, names, team_of, team_games, season_games, bars):
    """Up to CHASE_MAX sentences about players on pace for a season record. lines is this season's gamedata.season_lines
    output, team_of {pid: tid}, team_games {tid: games played}, season_games the schedule length per team, bars the
    records.json 'bar'. Only the counting stats (hr, h, rbi, sb, w, so, sv) of players whose team has played at least
    CHASE_FROM of the schedule. pace = round(value * season_games / team_games). A line when the pace is at least
    CHASE_NEAR of the bar, or the value is already at the bar ('past the record'). Players past the record come first,
    furthest past first; then the closest pace to the bar. Ties break by name."""
    if type(season_games) is not int or season_games <= 0:
        return []
    found = []
    for kind, stats in COUNTING.items():
        for pid, line in (lines.get(kind) or {}).items():
            tid = team_of.get(pid)
            played = team_games.get(tid, 0) if tid is not None else 0
            if played <= 0 or played * CHASE_FROM[1] < season_games * CHASE_FROM[0]:
                continue
            name = _name(names, pid)
            for stat in stats:
                held, value = _bar_of(bars, stat), _int(line.get(stat))
                if held is None or value <= 0:
                    continue
                top, holder, year = held
                pace = round(value * season_games / played)
                past = value >= top
                if not past and pace * CHASE_NEAR[1] < top * CHASE_NEAR[0]:
                    continue
                if past:
                    text = '%s has %d %s, past the record of %d (%s, %d).' % (name, value, LABELS[stat], top, holder,
                                                                              year)
                else:
                    text = '%s has %d %s, on pace for %d. The record is %d (%s, %d).' % (
                        name, value, LABELS[stat], pace, top, holder, year)
                found.append(((not past, -Fraction(value if past else pace, top), name, stat, pid), text))
    return [text for _, text in sorted(found)[:CHASE_MAX]]
