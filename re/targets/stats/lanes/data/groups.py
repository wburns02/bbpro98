#!/usr/bin/env python3
"""Match box-file team split groups to stat-file member tables across days."""
import sys, struct, glob, collections, os
sys.path.insert(0, '/home/will/bbpro98/re/targets')
sys.path.insert(0, '/home/will/bbpro98/work')
import asnref as A, explore, league as L
from explore import DATA, stat_records, load_names

explore.NAMES.update(load_names())

def box_groups(hfile, rec_len):
    """Contiguous runs of rec_len rows -> list of {pid: row} (side folded into pid key (side,pid))."""
    groups, cur, last_i = [], {}, None
    for i, (rec, u) in enumerate(A.h_tables(open(hfile, 'rb').read())):
        if rec == rec_len:
            if last_i is not None and i != last_i + 1:
                groups.append(cur); cur = {}
            cur[(u[2] >> 15, u[2] & 0x7fff)] = list(u[3:])
            last_i = i
        # treat any other record type as a separator
    if cur: groups.append(cur)
    return groups

def team_tables(day):
    blob = open(f'{DATA}/{day}/mlbpa97.DAT', 'rb').read()
    _, recs = stat_records(blob)
    out = {}
    for off, m, u in recs:
        if u[2] & 0x7fff < 100 and len(u) * 2 in (22, 36):
            out.setdefault((u[0], m, u[2] & 0x7fff), []).append(list(u[3:]))
    return out

def main(day):
    dd = f'{DATA}/{day}'
    tt = team_tables(day)
    doc = L.build_json(L.parse_container(open(f'{dd}/MLBPA97.ASN', 'rb').read()))
    played = [g for g in doc['games'] if g['played']]
    homes = {g['home'] for g in played}
    for f in sorted(glob.glob(f'{dd}/MLBPA97.H*')):
        g22 = box_groups(f, 22)
        g36 = box_groups(f, 36)
        # team rows per group
        t22 = [[(k, row) for k, row in gr.items() if k[1] < 100] for gr in g22]
        t36 = [[(k, row) for k, row in gr.items() if k[1] < 100] for gr in g36]
        print(os.path.basename(f), 'g22 groups:', [len(x) for x in t22], 'g36 groups:', [len(x) for x in t36])
        for gi, rows in enumerate(t22):
            for (side, tid), row in rows:
                matches = [m for (sc, m, pid), rl in tt.items() if pid == tid and row in rl]
                print(f'   22 g{gi} side{side} team {tid:2d} {"HOME" if tid in homes else "away"} {row} -> members {matches}')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'day01')
