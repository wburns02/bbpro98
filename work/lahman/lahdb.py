"""Season extraction from the Lahman SQLite database.

Every function takes an open connection from connect(). Results are plain dicts and lists with int counts.
SQL column names come from the constants below; every value is bound with ?.
"""

import sqlite3
from pathlib import Path

BAT_COLS = ('G', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'SB', 'CS', 'BB', 'SO', 'IBB', 'HBP', 'SH', 'SF', 'GIDP')
PIT_COLS = ('W', 'L', 'G', 'GS', 'CG', 'SHO', 'SV', 'IPouts', 'H', 'ER', 'HR', 'BB', 'SO', 'IBB', 'WP', 'HBP', 'BK',
            'BFP', 'GF', 'R')
FLD_COLS = ('G', 'GS', 'InnOuts', 'PO', 'A', 'E', 'DP', 'PB', 'SB', 'CS')
APP_COLS = ('G_all', 'GS', 'G_batting', 'G_p', 'G_c', 'G_1b', 'G_2b', 'G_3b', 'G_ss', 'G_lf', 'G_cf', 'G_rf', 'G_of',
            'G_dh')


# The major leagues. The 2024 and later releases add the Negro Leagues (NEGRO_LEAGUES) and the independent clubs
# (EAS, IND, INT, NAC, WES); a build takes the majors unless it asks for other leagues.
MLB_LEAGUES = ('NA', 'NL', 'AA', 'UA', 'PL', 'AL', 'FL')
NEGRO_LEAGUES = ('NNL', 'ECL', 'ANL', 'EWL', 'NSL', 'NN2', 'NAL')


def connect(path):
    """Open the database read-only."""
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def year_range(con, leagues=MLB_LEAGUES):
    """(first, last) season the database holds for these leagues, or None."""
    marks = ','.join('?' * len(leagues))
    first, last = con.execute('SELECT MIN(yearID), MAX(yearID) FROM teams WHERE lgID IN (%s)' % marks,
                              tuple(leagues)).fetchone()
    return None if first is None else (int(first), int(last))


def teams(con, year, leagues=MLB_LEAGUES):
    marks = ','.join('?' * len(leagues))
    rows = con.execute('''
        SELECT teamID, lgID, divID, franchID, name, park, G, W, L, teamRank
        FROM teams WHERE yearID = ? AND lgID IN (%s)
        ORDER BY COALESCE(lgID, ''), COALESCE(divID, ''), teamID''' % marks, (year,) + tuple(leagues)).fetchall()
    return [
        {'teamID': tid, 'lgID': lg, 'divID': div or '', 'franchID': franch, 'name': name, 'park': park or '',
         'G': int(g or 0), 'W': int(w or 0), 'L': int(l or 0), 'rank': int(rank or 0)}
        for tid, lg, div, franch, name, park, g, w, l, rank in rows]


def managers(con, year):
    rows = con.execute('''
        SELECT m.teamID, m.playerID, COALESCE(p.nameFirst, ''), COALESCE(p.nameLast, ''),
               SUM(COALESCE(m.G, 0)), MIN(COALESCE(m.inseason, 0))
        FROM managers m LEFT JOIN people p ON p.playerID = m.playerID
        WHERE m.yearID = ? GROUP BY m.teamID, m.playerID''', (year,)).fetchall()
    out = {}
    # Most G first; equal G goes to the lowest inseason, then playerID.
    for team, pid, first, last, g, _ in sorted(rows, key=lambda r: (r[0], -r[4], r[5], r[1])):
        out.setdefault(team, {'playerID': pid, 'first': first, 'last': last, 'G': int(g)})
    return out


def roster(con, year):
    rows = con.execute('''
        SELECT teamID, playerID FROM appearances WHERE yearID = ?
        GROUP BY teamID, playerID
        ORDER BY teamID, SUM(COALESCE(G_all, 0)) DESC, playerID''', (year,)).fetchall()
    out = {}
    for team, pid in rows:
        out.setdefault(team, []).append(pid)
    return out


def appearances(con, year):
    rows = con.execute(f'''
        SELECT playerID, teamID, {_sums(APP_COLS)} FROM appearances
        WHERE yearID = ? GROUP BY playerID, teamID''', (year,)).fetchall()
    out = {}
    for pid, team, *vals in rows:
        out.setdefault(pid, {})[team] = _counts(APP_COLS, vals)
    return out


def people(con, ids):
    ids = list(ids)
    out = {}
    for start in range(0, len(ids), 500):  # stay under SQLite's bound-parameter limit
        chunk = ids[start:start + 500]
        marks = ','.join(['?'] * len(chunk))
        rows = con.execute(f'''
            SELECT playerID, nameFirst, nameLast, birthYear, birthMonth, birthDay, bats, throws, debut
            FROM people WHERE playerID IN ({marks})''', chunk).fetchall()
        for pid, first, last, by, bm, bd, bats, throws, debut in rows:
            out[pid] = {
                'first': first or '', 'last': last or '',
                'birth_year': _maybe_int(by), 'birth_month': _maybe_int(bm), 'birth_day': _maybe_int(bd),
                'bats': bats or '', 'throws': throws or '',
                'debut': str(debut)[:10] if debut else '',
            }
    return out


def batting(con, year=None, before=None):
    where, params = _season_filter(year, before)
    rows = con.execute(f'SELECT playerID, {_sums(BAT_COLS)} FROM batting {where} GROUP BY playerID',
                       params).fetchall()
    return {pid: _counts(BAT_COLS, vals) for pid, *vals in rows}


def pitching(con, year=None, before=None):
    where, params = _season_filter(year, before)
    rows = con.execute(f'SELECT playerID, {_sums(PIT_COLS)} FROM pitching {where} GROUP BY playerID',
                       params).fetchall()
    return {pid: _counts(PIT_COLS, vals) for pid, *vals in rows}


def fielding(con, year=None, before=None):
    where, params = _season_filter(year, before)
    rows = con.execute(f'SELECT playerID, POS, {_sums(FLD_COLS)} FROM fielding {where} GROUP BY playerID, POS',
                       params).fetchall()
    out = {}
    for pid, pos, *vals in rows:
        out.setdefault(pid, {})[pos] = _counts(FLD_COLS, vals)
    return out


def seasons_before(con, year):
    rows = con.execute('''
        SELECT playerID, COUNT(DISTINCT yearID) FROM appearances
        WHERE yearID < ? GROUP BY playerID''', (year,)).fetchall()
    return {pid: int(n) for pid, n in rows}


def _sums(cols):
    # Identifiers only: cols are module constants, never caller input.
    return ', '.join(f'SUM(COALESCE("{c}", 0)) AS "{c}"' for c in cols)


def _counts(cols, values):
    return {c: int(v or 0) for c, v in zip(cols, values)}


def _maybe_int(value):
    return None if value is None else int(value)


def _season_filter(year, before):
    """WHERE clause for one season (year) or the career before a season (before); exactly one is required."""
    if (year is None) == (before is None):
        raise ValueError('pass exactly one of year or before')
    if year is not None:
        return 'WHERE yearID = ?', (year,)
    return 'WHERE yearID < ?', (before,)
