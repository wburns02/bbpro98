#!/usr/bin/env python3
"""Box score helpers + team row inspection."""
import sys, struct, glob, collections, os
import explore
from explore import DATA, stat_records, load_names
import asnref as A

def box_files(day, prev=None):
    have = lambda d: {os.path.basename(p) for p in glob.glob(f'{d}/MLBPA97.H*')} if d else set()
    return sorted(f'{day}/{f}' for f in have(f'{DATA}/{day}') - (have(prev) if prev else set()))

def box_rows_for(day, prev=None):
    """(rec_len, pid) -> summed words[3:] across the day's new box files, plus per-file detail."""
    tot = {}
    detail = collections.defaultdict(list)
    for f in box_files(day, prev):
        for rec, u in A.h_tables(open(f, 'rb').read()):
            pid = u[2] & 0x7fff
            key = (rec, pid)
            row = tot.setdefault(key, [0] * (len(u) - 3))
            for i in range(len(row)):
                if i < len(u) - 3: row[i] += u[3 + i]
            detail[key].append((os.path.basename(f), list(u[3:])))
    return tot, detail

def team_tables(day):
    blob = open(f'{DATA}/{day}/mlbpa97.DAT', 'rb').read()
    _, recs = stat_records(blob)
    out = {}
    for off, m, u in recs:
        if u[2] & 0x7fff < 100:
            out[(u[0], m, u[2] & 0x7fff, len(u) * 2)] = (off, list(u))
    return out

if __name__ == '__main__':
    day = sys.argv[1] if len(sys.argv) > 1 else 'day01'
    prev = {'day02': 'day01', 'day03': 'day02'}.get(day)
    tot, detail = box_rows_for(f'{DATA}/{day}', f'{DATA}/{prev}' if prev else None)
    tt = team_tables(day)
    print('== team stat rows for', day)
    for k in sorted(tt):
        sc, m, pid, ln = k
        off, u = tt[k]
        print(f'  scope {sc:2d} m {m:2d} team {pid:2d} len {ln:3d} off {off}: {u[3:]}')
    print('== box rows (40/70) for teams')
    for (rec, pid), row in sorted(tot.items()):
        if pid < 100 and rec in (40, 70):
            print(f'  box rec {rec} team {pid:2d}: {row}')
