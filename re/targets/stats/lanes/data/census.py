#!/usr/bin/env python3
"""Census: which (scope, member, len) tables exist, and day-to-day deltas keyed by record identity."""
import sys, struct, collections
import explore
from explore import DATA, stat_records, load_names

DAYS = ['day01', 'day02', 'day03', 'day04', 'day05', 'day06', 'day07', 'day08', 'day09']

def load_day(day):
    blob = open(f'{DATA}/{day}/mlbpa97.DAT', 'rb').read()
    _, recs = stat_records(blob)
    # key: (scope, member, pid&0x7fff, len) -> (off, words)
    out = {}
    for off, m, u in recs:
        k = (u[0], m, u[2] & 0x7fff, len(u) * 2)
        out[k] = (off, u)
    return out

def census(day):
    d = load_day(day)
    g = collections.defaultdict(list)
    for (sc, m, pid, ln), (off, u) in d.items():
        g[(sc, m, ln)].append(pid)
    print(f'== {day}: {len(d)} stat records')
    for k in sorted(g):
        sc, m, ln = k
        pids = g[k]
        teams = sum(1 for p in pids if p < 100)
        print(f'  scope {sc:2d} m {m:2d} len {ln:3d}: {len(pids):5d} rows, {teams} team rows')

def pair(dayA, dayB):
    a, b = load_day(dayA), load_day(dayB)
    print(f'== {dayA} -> {dayB}')
    delta_kinds = collections.Counter()
    for k in sorted(set(a) | set(b)):
        ua = a.get(k, (None, None))[1]
        ub = b.get(k, (None, None))[1]
        if ua is None:
            delta_kinds[(k[0], k[1], k[3], 'new')] += 1
        elif ub is None:
            delta_kinds[(k[0], k[1], k[3], 'gone')] += 1
        elif ua != ub:
            delta_kinds[(k[0], k[1], k[3], 'chg')] += 1
    for k in sorted(delta_kinds):
        print('  ', k, delta_kinds[k])

if __name__ == '__main__':
    if sys.argv[1] == 'census':
        for d in DAYS: census(d)
    else:
        pair(sys.argv[1], sys.argv[2])
