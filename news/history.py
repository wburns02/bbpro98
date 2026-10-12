"""The player card's Career tab: one player's seasons by year, from the real major league seasons in the Lahman
database and the seasons the game simulated. lahman_id finds the player; real_seasons reads his Lahman seasons from a
connection open_db made read-only. archive_season and sim_seasons keep and read the sim seasons, one JSON file per year
under <data>/<STEM>/history. merge joins the two into rows, totals sums rows, and start_year gives the first season an
association simulates. Standard library only; every value reaches SQL as a parameter.
"""
import json
import os
import re
import sqlite3
import urllib.parse

DEFAULT_DB = '/mnt/nvme/bbpro98/lahman2025/lahman2025.sqlite'
BAT_KEYS = ('g', 'ab', 'r', 'h', 'h2b', 'h3b', 'hr', 'rbi', 'bb', 'so', 'sb', 'hbp', 'sf')
PIT_KEYS = ('g', 'w', 'l', 'sv', 'outs', 'h', 'er', 'bb', 'so', 'hr')
# The Lahman column behind each line key. These names are fixed in this file, never taken from a caller.
BAT_COLUMNS = {'g': 'G', 'ab': 'AB', 'r': 'R', 'h': 'H', 'h2b': '"2B"', 'h3b': '"3B"', 'hr': 'HR', 'rbi': 'RBI',
               'bb': 'BB', 'so': 'SO', 'sb': 'SB', 'hbp': 'HBP', 'sf': 'SF'}
PIT_COLUMNS = {'g': 'G', 'w': 'W', 'l': 'L', 'sv': 'SV', 'outs': 'IPouts', 'h': 'H', 'er': 'ER', 'bb': 'BB',
               'so': 'SO', 'hr': 'HR'}
STEM_RE = re.compile(r'[A-Za-z0-9]{1,8}')
SIM_FILE_RE = re.compile(r'[0-9]{4}\.json')
LEAGUE_STEM_RE = re.compile(r'[0-9]{2}[LN]([0-9]{4})', re.IGNORECASE)
FIXED_STARTS = {'MLBPA97': 1997, 'MLBPA96E': 1997}


def find_db(env=None):
    """The Lahman database to read: the BBPRO98_LAHMAN file in env (default os.environ) when that is a file, else
    DEFAULT_DB when it is a file, else None."""
    env = os.environ if env is None else env
    path = env.get('BBPRO98_LAHMAN')
    if path and os.path.isfile(path):
        return path
    if os.path.isfile(DEFAULT_DB):
        return DEFAULT_DB
    return None


def open_db(path):
    """A read-only connection to the Lahman database at path: a write raises sqlite3.OperationalError."""
    return sqlite3.connect('file:%s?mode=ro' % urllib.parse.quote(path), uri=True)


def _fold(name):
    """A name as it is compared: NULL is '', surrounding space is dropped, case is folded."""
    return (name or '').strip().casefold()


def _int(value):
    """value as an int. NULL, '' and anything that is not a number count as 0."""
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def lahman_id(conn, first, last, born):
    """The playerID of the person named first last and born on born (a date), or None. Names compare case-insensitively
    after strip. An exact name match is tried first; failing that, a last name that starts with last (the game cuts
    names) and a first name that starts with the first three letters of first (any first name when first is '').
    The stage that matches must give exactly one person: none or several give None."""
    first, last = _fold(first), _fold(last)
    if not last:
        return None
    rows = conn.execute('SELECT playerID, nameFirst, nameLast FROM people'
                        ' WHERE birthYear = ? AND birthMonth = ? AND birthDay = ?',
                        (born.year, born.month, born.day)).fetchall()
    people = [(pid, _fold(given), _fold(family)) for pid, given, family in rows]
    exact = [pid for pid, given, family in people if given == first and family == last]
    found = exact or [pid for pid, given, family in people
                      if family.startswith(last) and given.startswith(first[:3])]
    return found[0] if len(found) == 1 else None


def _keys(kind):
    """The line keys of kind, 'bat' or 'pit'. Any other kind is a ValueError."""
    if kind == 'bat':
        return BAT_KEYS
    if kind == 'pit':
        return PIT_KEYS
    raise ValueError('kind must be bat or pit, not %r' % (kind,))


def real_seasons(conn, player_id, kind, before=None):
    """The player's Lahman seasons of kind ('bat' or 'pit'), one per year with his stints summed, ascending. Only years
    below before when it is set. A season is {'year', 'team', 'stints', then every key of BAT_KEYS or PIT_KEYS}. team is
    the year's teams.teamIDBR (else its teamID), or '<stints>TM' when he had more than one stint. NULL and '' values
    count as 0, and a year whose values are all 0 is kept."""
    keys = _keys(kind)
    table, columns = ('batting', BAT_COLUMNS) if kind == 'bat' else ('pitching', PIT_COLUMNS)
    sql = 'SELECT yearID, stint, teamID, %s FROM %s WHERE playerID = ?' % (
        ', '.join(columns[key] for key in keys), table)
    params = [player_id]
    if before is not None:
        sql += ' AND yearID < ?'
        params.append(before)
    rows = conn.execute(sql + ' ORDER BY yearID, stint', params).fetchall()
    if not rows:
        return []
    years = [_int(row[0]) for row in rows]
    labels = {}
    for year, team_id, team_br in conn.execute(
            'SELECT yearID, teamID, teamIDBR FROM teams WHERE yearID BETWEEN ? AND ?', (min(years), max(years))):
        if team_br:
            labels.setdefault((_int(year), team_id), team_br)
    by_year = {}
    for row in rows:
        by_year.setdefault(_int(row[0]), []).append(row)
    seasons = []
    for year in sorted(by_year):
        group = by_year[year]
        stints = len(group)
        team_id = group[0][2]
        season = {'year': year,
                  'team': '%dTM' % stints if stints > 1 else labels.get((year, team_id)) or (team_id or ''),
                  'stints': stints}
        for i, key in enumerate(keys):
            season[key] = sum(_int(row[3 + i]) for row in group)
        seasons.append(season)
    return seasons


def archive_path(data_dir, stem, year):
    """The history file of season year for association stem: <data_dir>/<STEM>/history/<year>.json."""
    return os.path.join(data_dir, stem.upper(), 'history', '%d.json' % year)


def _keep(line, keys):
    """line's value for each of keys as an int. A missing key, or a value that is not an int (bool included), is 0."""
    out = {}
    for key in keys:
        value = line.get(key)
        out[key] = value if isinstance(value, int) and not isinstance(value, bool) else 0
    return out


def archive_season(data_dir, stem, year, lines, teams=None):
    """Write season year of association stem, once. lines is {'bat': {pid: line}, 'pit': {pid: line}} and teams
    (optional) is {pid: team label}. A season already on disk is left alone and False is returned; otherwise the file
    is written through <file>.tmp and os.replace, and True is returned. A stem that is not 1 to 8 letters or digits, or
    a year outside 1800..3000, is a ValueError."""
    if not isinstance(stem, str) or STEM_RE.fullmatch(stem) is None:
        raise ValueError('stem must be 1 to 8 letters or digits, not %r' % (stem,))
    if not isinstance(year, int) or not 1800 <= year <= 3000:
        raise ValueError('year must be 1800 to 3000, not %r' % (year,))
    path = archive_path(data_dir, stem, year)
    if os.path.exists(path):
        return False
    doc = {'year': year,
           'bat': {str(pid): _keep(line, BAT_KEYS) for pid, line in lines.get('bat', {}).items()},
           'pit': {str(pid): _keep(line, PIT_KEYS) for pid, line in lines.get('pit', {}).items()},
           'team': {str(pid): label for pid, label in (teams or {}).items()}}
    text = json.dumps(doc)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return True


def sim_seasons(data_dir, stem, pid, kind):
    """The seasons the game simulated for pid: one per archived year in which he has a line of kind ('bat' or 'pit'),
    ascending, as {'year', 'team', then the line's keys}. Unreadable or malformed files are skipped. A missing history
    folder, or a stem that is not a valid one, gives []."""
    keys = _keys(kind)
    if not isinstance(stem, str) or STEM_RE.fullmatch(stem) is None:
        return []
    folder = os.path.join(data_dir, stem.upper(), 'history')
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    seasons = []
    for name in names:
        if SIM_FILE_RE.fullmatch(name) is None:
            continue
        try:
            with open(os.path.join(folder, name), encoding='utf-8') as f:
                doc = json.load(f)
            line = doc[kind][str(pid)]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(line, dict):
            continue
        teams = doc.get('team')
        team = teams.get(str(pid)) if isinstance(teams, dict) else None
        seasons.append(dict(year=int(name[:4]), team=team if isinstance(team, str) else '', **_keep(line, keys)))
    return seasons


def merge(real, sim, start=None):
    """The rows of a career: the real seasons before start (all of them when start is None), and the sim seasons. A
    year that has a sim row keeps only that row. Every row is a copy with 'sim': False (real) or True (sim), sorted by
    year."""
    sim_years = {row['year'] for row in sim}
    kept = [dict(row, sim=False) for row in real
            if (start is None or row['year'] < start) and row['year'] not in sim_years]
    kept += [dict(row, sim=True) for row in sim]
    return sorted(kept, key=lambda row: row['year'])


def totals(rows, kind):
    """The sum of every key of kind's line ('bat' or 'pit') over rows, plus 'seasons': the number of rows."""
    out = {key: sum(row.get(key, 0) for row in rows) for key in _keys(kind)}
    out['seasons'] = len(rows)
    return out


def start_year(stem, season_year=None):
    """The first season an association simulates, so the real seasons before it are history. A stem like '30L2025' or
    '28N1998' gives that year, 'MLBPA97' and 'MLBPA96E' give 1997, and any other stem gives season_year."""
    league = LEAGUE_STEM_RE.fullmatch(stem)
    if league:
        return int(league.group(1))
    return FIXED_STARTS.get(stem.upper(), season_year)
