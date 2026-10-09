#!/usr/bin/env python3
"""Full team names for the news sidecar, from the Lahman database.

    python3 work/lahman/teamnames.py [--db DB] [--out /mnt/nvme/bbpro98/teamnames.json]

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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--db', default=DB)
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args()
    t = table(lahdb.connect(a.db))
    tmp = a.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(t, fh, indent=0, sort_keys=True)
    os.replace(tmp, a.out)
    print('%s: %d seasons, %d teams' % (a.out, len(t), sum(len(v) for v in t.values())))


if __name__ == '__main__':
    main()
