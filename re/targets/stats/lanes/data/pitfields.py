#!/usr/bin/env python3
"""Per-game pitching rows from box files with context, to name tail fields."""
import sys, glob, collections, os
sys.path.insert(0, '/home/will/bbpro98/re/targets')
import asnref as A
import explore
from explore import DATA, load_names

explore.NAMES.update(load_names())

def games():
    for day in ['day%02d' % i for i in range(1, 10)]:
        prev = {os.path.basename(p) for p in glob.glob(f'{DATA}/day%02d/MLBPA97.H*' % (int(day[4:]) - 1))} if day != 'day01' else set()
        for f in sorted(glob.glob(f'{DATA}/{day}/MLBPA97.H*')):
            if os.path.basename(f) in prev: continue
            rows = list(A.h_tables(open(f, 'rb').read()))
            tid = {}; runs = {}
            for rec, u in rows:
                pid, side = u[2] & 0x7fff, u[2] >> 15
                if pid < 100:
                    tid[side] = pid
                    if rec == 40: runs[pid] = u[3 + 13]
            pits = [(side, u[2] & 0x7fff, list(u[3:])) for rec, u in rows if rec == 70 and (u[2] & 0x7fff) >= 100]
            yield os.path.basename(f), tid, runs, pits

if __name__ == '__main__':
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    n = 0
    for fn, tid, runs, pits in games():
        for side, pid, f in pits:
            if f[want]:
                my = tid[side]; opp = tid[1 - side]
                mr, orr = runs.get(my, 0), runs.get(opp, 0)
                print('%s %s team %2d vs %2d (%d-%d) | G%2d GS%d outs%2d W%d L%d Sv%d | f17=%d f23=%d f24=%d f25=%d f26=%d f27=%d f28=%d f29=%d f30=%d f31=%d' % (
                    fn, explore.NAMES.get(pid, ('?',))[0][:14], my, opp, mr, orr,
                    f[12], f[9], f[18], f[20], f[21], f[22], f[17], f[23], f[24], f[25], f[26], f[27], f[28], f[29], f[30], f[31]))
                n += 1
        if n > 40: break
