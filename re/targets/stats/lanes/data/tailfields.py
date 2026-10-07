#!/usr/bin/env python3
"""Targeted queries on per-game pitching tail fields."""
import sys, glob, collections, os
sys.path.insert(0, '/home/will/bbpro98/re/targets')
import asnref as A
import explore
from explore import DATA, load_names
from pitfields import games

def all_games():
    for fn, tid, runs, pits in games():
        sides = collections.defaultdict(int)
        for side, pid, f in pits:
            starter = sides[side] == 0
            sides[side] += 1
            my, opp = tid[side], tid[1 - side]
            yield fn, side, pid, starter, my, opp, runs.get(my, 0), runs.get(opp, 0), f

def rows(field, extra=''):
    n = 0
    for fn, side, pid, starter, my, opp, mr, orr, f in all_games():
        if f[field]:
            print('%s %s starter%d %2d-%2d outs%2d er%2d W%d L%d Sv%d | f23=%d f24=%d f25=%d f17=%d f27=%d f29=%d f30=%d' % (
                fn, explore.NAMES.get(pid, ('?',))[0][:12], starter, mr, orr, f[18], f[26], f[20], f[21], f[22],
                f[23], f[24], f[25], f[17], f[27], f[29], f[30]))
            n += 1
            if n >= int(sys.argv[2] if len(sys.argv) > 2 else 25): break

def rel17():
    n = tot = 0
    for fn, side, pid, starter, my, opp, mr, orr, f in all_games():
        if not starter:
            tot += 1
            if not f[17]:
                n += 1
                print('reliever WITHOUT f17: %s %s %2d-%2d outs%2d er%2d W%d L%d Sv%d f29=%d f30=%d' % (
                    fn, explore.NAMES.get(pid, ('?',))[0][:12], mr, orr, f[18], f[26], f[20], f[21], f[22], f[29], f[30]))
                if n > 15: break
    print('reliever games seen:', tot)

if __name__ == '__main__':
    q = sys.argv[1]
    if q == 'f23': rows(23)
    elif q == 'f24': rows(24)
    elif q == 'f25': rows(25)
    elif q == 'rel17': rel17()
