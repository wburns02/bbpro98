#!/usr/bin/env python3
"""Measure: scope-0 window size, pitcher field semantics, catcher fielding fields."""
import sys, struct, glob, collections, os
sys.path.insert(0, '/home/will/bbpro98/re/targets')
sys.path.insert(0, '/home/will/bbpro98/work')
import explore
from explore import DATA, stat_records, load_names

explore.NAMES.update(load_names())
DAYS = ['day%02d' % i for i in range(1, 10)]

def load_day(day):
    blob = open(f'{DATA}/{day}/mlbpa97.DAT', 'rb').read()
    _, recs = stat_records(blob)
    out = {}
    for off, m, u in recs:
        out[(u[0], m, u[2] & 0x7fff, len(u) * 2)] = (off, u)
    return out

def nm(pid): return explore.NAMES.get(pid, ('?%d' % pid,))[0]

if __name__ == '__main__':
    which = sys.argv[1]
    if which == 'window':
        # Griffey scope 0/1 bat line per day
        prev = None
        for day in DAYS:
            d = load_day(day)
            for sc in (0, 1):
                r = d.get((sc, 6, 1162, 40))
                if r:
                    off, u = r
                    print(day, 'scope', sc, 'G=%d ab=%d hr=%d r=%d' % (u[3 + 12], u[3], u[3 + 4], u[3 + 13]), list(u[3:]))
                else:
                    print(day, 'scope', sc, 'no line')
    elif which == 'pitfields':
        # aggregate box rec-70 rows day01..09 per pid, compare to day09 scope-1 line
        import asnref as A
        seen = set()
        tot = collections.defaultdict(lambda: [0] * 32)
        for i, day in enumerate(DAYS):
            prevf = {os.path.basename(p) for p in glob.glob(f'{DATA}/{DAYS[i-1]}/MLBPA97.H*')} if i else set()
            for f in sorted(glob.glob(f'{DATA}/{day}/MLBPA97.H*')):
                if os.path.basename(f) in prevf: continue
                for rec, u in A.h_tables(open(f, 'rb').read()):
                    if rec == 70:
                        pid = u[2] & 0x7fff
                        for j in range(32): tot[pid][j] += u[3 + j]
        d = load_day('day09')
        print('%-22s %s' % ('field', 'pid: boxsum vs season (mismatches only)'))
        for j in range(32):
            mism = []
            for pid, s in tot.items():
                r = d.get((1, 28, pid, 70))
                if not r: continue
                v = r[1][3 + j]
                if v != s[j]: mism.append((pid, s[j], v))
            print('f%-2d %-14s mismatches: %d %s' % (j, ['', ''][j < 2] or '', len(mism), mism[:6]))
    elif which == 'pitcher_sample':
        d = load_day('day09')
        # show full 32-field season lines for a few pitchers with nonzero late fields
        shown = 0
        for (sc, m, pid, ln), (off, u) in d.items():
            if (sc, m, ln) == (1, 28, 70):
                f = list(u[3:])
                if any(f[22:]) or f[17]:
                    print('%-20s' % nm(pid), f)
                    shown += 1
                    if shown > 12: break
