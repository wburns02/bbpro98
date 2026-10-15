#!/usr/bin/env python3
"""Full team names for the news sidecar, from the Lahman database.

    python3 work/lahman/teamnames.py [--db DB] [--out /mnt/nvme/bbpro98/teamnames.json]
    python3 work/lahman/teamnames.py --check /mnt/nvme/bbpro98/teamnames.json

build.py stores a team's name cut to the game's 16 characters ('Balt. Orioles', 'New Haven Elm Ci'). This writes
{year: {teamID: [full, short]}}, short being exactly what build.team_name stores, so news/teamnames.py can put the
full name back on teams of a Lahman-built association (abbrev = teamID) whose stored name is still that short form.
A teamID used twice in one year is left out: the abbreviation alone cannot tell the two apart.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lahman import lahdb                      # noqa: E402
from lahman.build import DB, team_name        # noqa: E402

OUT = '/mnt/nvme/bbpro98/teamnames.json'


def table(con):
    seen, out = {}, {}
    for year, tid, name in con.execute('SELECT yearID, teamID, name FROM teams ORDER BY yearID, teamID'):
        key = (str(year), tid)
        seen[key] = seen.get(key, 0) + 1
        out.setdefault(str(year), {})[tid] = [name, team_name(name)]
    for (year, tid), n in seen.items():
        if n > 1:
            del out[year][tid]
    return out


def missing_years(tbl, con):
    """Years with rows in con's teams table that str(year) is not a key of tbl, sorted."""
    db_years = {str(year) for year, in con.execute('SELECT DISTINCT yearID FROM teams')}
    return sorted(int(y) for y in db_years if y not in tbl)


def ranges(years):
    """[1871, 1872, 1875, 1999] -> '1871-1872, 1875, 1999'."""
    out, i = [], 0
    while i < len(years):
        j = i
        while j + 1 < len(years) and years[j + 1] == years[j] + 1:
            j += 1
        out.append(str(years[i]) if j == i else '%d-%d' % (years[i], years[j]))
        i = j + 1
    return ', '.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--db', default=DB)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--check', help='report Lahman years PATH lacks instead of writing it')
    a = ap.parse_args(argv)
    con = lahdb.connect(a.db)
    if a.check:
        try:
            with open(a.check, encoding='utf-8') as fh:
                tbl = json.load(fh)
        except (OSError, ValueError):
            tbl = {}
        if not isinstance(tbl, dict):
            tbl = {}
        missing = missing_years(tbl, con)
        if missing:
            print('teamnames: %s lacks %d Lahman years: %s' % (a.check, len(missing), ranges(missing)))
            raise SystemExit(1)
        rows = list(con.execute('SELECT MIN(yearID), MAX(yearID) FROM teams'))
        print('teamnames: %s covers every Lahman year (%s-%s)' % (a.check, rows[0][0], rows[0][1]))
        return 0
    t = table(con)
    tmp = a.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(t, fh, indent=0, sort_keys=True)
    os.replace(tmp, a.out)
    print('%s: %d seasons, %d teams' % (a.out, len(t), sum(len(v) for v in t.values())))


if __name__ == '__main__':
    main()
