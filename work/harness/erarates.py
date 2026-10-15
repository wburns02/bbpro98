#!/usr/bin/env python3
"""Compare a simulated season's league batting rates with the real Lahman season.

    python3 work/harness/erarates.py DAT --year Y [--leagues AL,NL] [--db PATH] [--tol 0.10] [--json]

DAT is a Stats .DAT file the game wrote (season scope, player ids >= 100). Prints one line per rate, for example
`BA  sim .2710  real .2650  x1.02`, and exits 0 when BA, HR/AB and BB/AB are all within --tol of the real season, 1
when one is not, 2 on bad input (missing file or database, no Lahman teams that year). The Lahman database is opened
read only. The game's modules (news/gamedata) are imported only when a DAT is read, never at import time.
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.parse

DB = '/mnt/nvme/bbpro98/lahman2025/lahman2025.sqlite'
NEWS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'news')
RATES = ('BA', 'HR/AB', 'BB/AB', 'SO/AB')
CHECKED = ('BA', 'HR/AB', 'BB/AB')            # SO is NULL in old Lahman years, so it is shown but not judged
SIM_KEYS = ('ab', 'h', 'hr', 'bb', 'so', 'r', 'g')
EPS = 1e-9                                    # a ratio exactly on the tolerance passes


def sim_totals(lines):
    """{'ab','h','hr','bb','so','r','g'} summed over lines['bat'] (gamedata.season_lines output) for player ids >= 100;
    a missing field counts 0."""
    out = dict.fromkeys(SIM_KEYS, 0)
    for pid, line in (lines.get('bat') or {}).items():
        if pid >= 100:
            for k in SIM_KEYS:
                out[k] += line.get(k) or 0
    return out


def real_totals(con, year, leagues=None):
    """Sums of AB, H, HR, BB, SO, R, G over the Lahman Teams rows of `year` (lgID in `leagues` when given), as the same
    keys sim_totals has plus 'so_known'. SO is NULL in old years: it counts 0 and so_known is False when any row has
    none. No rows for the year gives zeros and so_known False."""
    sql = 'SELECT SUM(AB), SUM(H), SUM(HR), SUM(BB), SUM(SO), SUM(R), SUM(G), COUNT(*), COUNT(SO) FROM Teams WHERE yearID = ?'
    args = [year]
    if leagues:
        sql += ' AND lgID IN (%s)' % ','.join('?' * len(leagues))
        args += list(leagues)
    row = con.execute(sql, args).fetchone()
    out = {k: int(v or 0) for k, v in zip(SIM_KEYS, row[:7])}
    out['so_known'] = bool(row[7]) and row[8] == row[7]
    return out


def rates(t):
    """{'BA': h/ab, 'HR/AB': hr/ab, 'BB/AB': bb/ab, 'SO/AB': so/ab} of a totals dict; every rate None when ab is 0.
    SO/AB is None too when the totals say so_known False (the strikeouts were never recorded)."""
    ab = t.get('ab') or 0
    if ab <= 0:
        return dict.fromkeys(RATES)
    out = {'BA': (t.get('h') or 0) / ab, 'HR/AB': (t.get('hr') or 0) / ab, 'BB/AB': (t.get('bb') or 0) / ab,
           'SO/AB': (t.get('so') or 0) / ab}
    if t.get('so_known') is False:
        out['SO/AB'] = None
    return out


def compare(sim, real):
    """{rate name: {'sim': x, 'real': y, 'ratio': x / y or None}}. sim and real are rates() dicts (or totals dicts,
    which are converted); the ratio is None when either side is None or y is 0."""
    sim, real = (rates(d) if 'ab' in d else d for d in (sim, real))
    out = {}
    for name in RATES:
        x, y = sim.get(name), real.get(name)
        out[name] = {'sim': x, 'real': y, 'ratio': x / y if x is not None and y else None}
    return out


def within(cmp, tol=0.10, names=CHECKED):
    """(ok, misses): a named rate misses when its ratio is None, absent, or further than tol from 1."""
    misses = []
    for name in names:
        r = (cmp.get(name) or {}).get('ratio')
        if r is None or abs(r - 1.0) > tol + EPS:
            misses.append(name)
    return not misses, misses


def open_db(path):
    """The Lahman database, read only."""
    return sqlite3.connect('file:%s?mode=ro' % urllib.parse.quote(os.path.abspath(path)), uri=True)


def load_lines(dat):
    """gamedata.season_lines(dat), imported on first use from news/ (the game's readers stay out of import time)."""
    if NEWS not in sys.path:
        sys.path.insert(0, NEWS)
    import gamedata
    return gamedata.season_lines(dat)


def fmt_rate(x):
    """A rate as .2710 (no leading zero), n/a for None."""
    if x is None:
        return 'n/a'
    s = '%.4f' % x
    return s[1:] if s.startswith('0.') else s


def render(cmp):
    """One line per rate: `BA  sim .2710  real .2650  x1.02`."""
    out = []
    for name in RATES:
        c = cmp[name]
        out.append('%s  sim %s  real %s  %s' % (name, fmt_rate(c['sim']), fmt_rate(c['real']),
                                                'x%.2f' % c['ratio'] if c['ratio'] is not None else 'n/a'))
    return '\n'.join(out)


def main(argv=None, load=load_lines, connect=open_db):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('dat', help='Stats .DAT file of the simulated season')
    ap.add_argument('--year', type=int, required=True, help='Lahman season to compare with')
    ap.add_argument('--leagues', help='comma-separated Lahman lgIDs (default every league that year)')
    ap.add_argument('--db', default=DB)
    ap.add_argument('--tol', type=float, default=0.10, help='allowed distance of each ratio from 1 (default 0.10)')
    ap.add_argument('--json', action='store_true', help='print one JSON object instead of the lines')
    a = ap.parse_args(argv)
    leagues = tuple(x for x in (a.leagues or '').upper().split(',') if x) or None
    if a.tol < 0:
        ap.error('--tol: must not be negative')
    if not os.path.isfile(a.dat):
        print('erarates: %s: no such file' % a.dat, file=sys.stderr)
        return 2
    try:
        sim = sim_totals(load(a.dat))
        con = connect(a.db)
        real = real_totals(con, a.year, leagues)
    except (OSError, ValueError, KeyError, IndexError, TypeError, sqlite3.Error) as e:
        print('erarates: %s' % (str(e) or type(e).__name__), file=sys.stderr)
        return 2
    if not real['ab']:
        print('erarates: no Lahman teams for %d%s' % (a.year, ' in ' + ','.join(leagues) if leagues else ''),
              file=sys.stderr)
        return 2
    cmp = compare(rates(sim), rates(real))
    ok, misses = within(cmp, a.tol)
    if a.json:
        print(json.dumps({'year': a.year, 'sim': sim, 'real': real, 'compare': cmp, 'tol': a.tol, 'ok': ok,
                          'misses': misses}))
    else:
        print(render(cmp))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
