#!/usr/bin/env python3
"""The salary table the contracts sidecar prices from (news/contracts.py): what a player was paid, as a multiple of his
league's median salary that year, fitted on the Lahman salaries of 1985 to 2016.

    python3 work/lahman/salarytable.py --db <lahman.sqlite> --out news/salary_table.json

Each salary row is priced by the player's line the season before: a batter by OPS (at least 100 AB), a pitcher by ERA
(at least 90 outs). He is a pitcher when he pitched in at least half his games. Service is the number of seasons before
the salary's with any appearance, and it sets the class (pre, arb, fa). The decile ranks him among the priced rows of
his season and role. A cell is the median of salary over that season's median salary; an empty cell takes the nearest
lower filled decile, else the nearest higher. The database is opened read-only; an existing --out is never overwritten.
"""
import argparse
import json
import os
import sqlite3
import statistics
import sys

FIRST, LAST = 1985, 2016
SOURCE = 'Lahman salaries 1985-2016 (SABR, CC BY-SA 3.0)'
MIN_AB = 100        # a batter is priced on a season with at least this many at-bats
MIN_OUTS = 90       # a pitcher on at least this many outs (30 innings)
DECILES = 10
ROLES = ('bat', 'pit')
CLASSES = ('pre', 'arb', 'fa')
BAT_COLS = ('AB', 'H', '2B', '3B', 'HR', 'BB', 'HBP', 'SF')


def connect(path):
    """The database, opened read-only."""
    return sqlite3.connect('file:%s?mode=ro' % path, uri=True)


def tables(con):
    """(apps, bat, pit) keyed by (playerID, yearID). Stints of one season are summed and NULL counts are 0: apps[k] is
    (G_all, G_p), bat[k] the counts of BAT_COLS, pit[k] {'outs', 'er'}."""
    apps = {(p, y): (ga, gp) for p, y, ga, gp in con.execute(
        'SELECT playerID, yearID, SUM(COALESCE(G_all, 0)), SUM(COALESCE(G_p, 0)) FROM appearances '
        'GROUP BY playerID, yearID')}
    bat = {(p, y): dict(zip(BAT_COLS, vals)) for p, y, *vals in con.execute(
        'SELECT playerID, yearID, SUM(COALESCE(AB, 0)), SUM(COALESCE(H, 0)), SUM(COALESCE("2B", 0)), '
        'SUM(COALESCE("3B", 0)), SUM(COALESCE(HR, 0)), SUM(COALESCE(BB, 0)), SUM(COALESCE(HBP, 0)), '
        'SUM(COALESCE(SF, 0)) FROM batting GROUP BY playerID, yearID')}
    pit = {(p, y): {'outs': outs, 'er': er} for p, y, outs, er in con.execute(
        'SELECT playerID, yearID, SUM(COALESCE(IPouts, 0)), SUM(COALESCE(ER, 0)) FROM pitching '
        'GROUP BY playerID, yearID')}
    return apps, bat, pit


def salaries(con):
    """(yearID, playerID, salary) for every salary row of FIRST to LAST that has a salary."""
    return con.execute('SELECT yearID, playerID, salary FROM salaries WHERE yearID BETWEEN ? AND ? '
                       'AND salary IS NOT NULL ORDER BY yearID, playerID', (FIRST, LAST)).fetchall()


def ops(line):
    """On-base plus slugging: OBP = (H+BB+HBP)/(AB+BB+HBP+SF), SLG = total bases / AB."""
    obp = (line['H'] + line['BB'] + line['HBP']) / (line['AB'] + line['BB'] + line['HBP'] + line['SF'])
    slg = (line['H'] + line['2B'] + 2 * line['3B'] + 3 * line['HR']) / line['AB']
    return obp + slg


def era(line):
    """Earned runs per nine innings: 27 * ER / outs."""
    return 27 * line['er'] / line['outs']


def role(g_all, g_p):
    """'pit' when pitching games are at least half of all games, else 'bat'."""
    return 'pit' if 2 * g_p >= g_all else 'bat'


def service(years, year):
    """Seasons before year in which the player has an appearances row; years is the set of his seasons."""
    return sum(1 for y in years if y < year)


def class_of(service_years):
    return 'pre' if service_years < 3 else 'arb' if service_years < 6 else 'fa'


def priced(con, sal):
    """The salary rows that can be priced, as dicts: pid, year, role, cls, score (higher is better: OPS for a batter,
    minus ERA for a pitcher) and salary. A row is left out when its player has no games the season before, or too few
    at-bats or outs there."""
    apps, bat, pit = tables(con)
    seasons = {}
    for p, y in apps:
        seasons.setdefault(p, set()).add(y)
    rows = []
    for year, p, salary in sal:
        prev = apps.get((p, year - 1))
        if prev is None or prev[0] == 0:
            continue
        r = role(*prev)
        if r == 'bat':
            line = bat.get((p, year - 1))
            if line is None or line['AB'] < MIN_AB:
                continue
            score = ops(line)
        else:
            line = pit.get((p, year - 1))
            if line is None or line['outs'] < MIN_OUTS:
                continue
            score = -era(line)
        rows.append({'year': year, 'pid': p, 'role': r, 'cls': class_of(service(seasons[p], year)),
                     'score': score, 'salary': salary})
    return rows


def decile(rank0, n):
    """1..10 from a 0-based rank counted from the worst of n rows: min(10, 1 + int(10 * rank0 / n))."""
    return min(DECILES, 1 + DECILES * rank0 // n)


def deciles(rows):
    """Adds 'decile' to each row: its rank by score among the rows of its season and role, ties to the lower pid."""
    groups = {}
    for row in rows:
        groups.setdefault((row['year'], row['role']), []).append(row)
    for group in groups.values():
        group.sort(key=lambda row: (row['score'], row['pid']))
        for rank0, row in enumerate(group):
            row['decile'] = decile(rank0, len(group))
    return rows


def fill(vals):
    """Empty cells (None) take the nearest lower filled value, else the nearest higher one."""
    out = []
    for i, v in enumerate(vals):
        if v is None:
            lower = [x for x in vals[:i] if x is not None]
            higher = [x for x in vals[i + 1:] if x is not None]
            v = lower[-1] if lower else higher[0]
        out.append(v)
    return out


def medians(sal):
    """{year: median salary} over every salary row of the year, priced or not."""
    by_year = {}
    for year, _, salary in sal:
        by_year.setdefault(year, []).append(salary)
    return {year: statistics.median(v) for year, v in sorted(by_year.items())}


def means(sal):
    """{year: mean salary, to the dollar} over every salary row of the year."""
    by_year = {}
    for year, _, salary in sal:
        by_year.setdefault(year, []).append(salary)
    return {year: round(statistics.mean(v)) for year, v in sorted(by_year.items())}


def fit(con):
    """The salary table from an open database: {'source', 'years', 'means', 'ratio'}. years holds each season's median
    salary, which the ratio cells are relative to, and means its mean salary, the level contracts.py prices a league
    to. ValueError when a role and class has no
    priced row at all, since its cells could not be filled."""
    sal = salaries(con)
    med = medians(sal)
    rows = deciles(priced(con, sal))
    cells = {(r, c): [[] for _ in range(DECILES)] for r in ROLES for c in CLASSES}
    for row in rows:
        cells[row['role'], row['cls']][row['decile'] - 1].append(row['salary'] / med[row['year']])
    ratio = {r: {} for r in ROLES}
    for (r, c), values in cells.items():
        cell = [round(statistics.median(v), 3) if v else None for v in values]
        if all(x is None for x in cell):
            raise ValueError('no priced rows for %s %s' % (r, c))
        ratio[r][c] = fill(cell)
    return {'source': SOURCE, 'years': {str(y): m for y, m in med.items()},
            'means': {str(y): m for y, m in means(sal).items()}, 'ratio': ratio}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--db', required=True, help='the Lahman database, opened read-only')
    ap.add_argument('--out', required=True, help='the salary table to write; an existing file is never overwritten')
    a = ap.parse_args(argv)
    if os.path.exists(a.out):
        ap.error('%s exists; not overwriting it' % a.out)
    try:
        con = connect(a.db)
        try:
            table = fit(con)
        finally:
            con.close()
    except (ValueError, sqlite3.Error) as e:
        sys.exit('salarytable: %s' % e)
    text = json.dumps(table, indent=1, sort_keys=True) + '\n'
    try:
        with open(a.out, 'x', encoding='utf-8') as fh:
            fh.write(text)
    except FileExistsError:
        ap.error('%s exists; not overwriting it' % a.out)
    print('%s: %d seasons' % (a.out, len(table['years'])))


if __name__ == '__main__':
    main()
