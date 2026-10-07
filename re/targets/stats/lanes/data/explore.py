#!/usr/bin/env python3
"""Exploration harness for mlbpa97.DAT stat records. Uses work/ctree.py for container parsing."""
import sys, os, struct, glob, collections, json
sys.path.insert(0, '/home/will/bbpro98/work')
sys.path.insert(0, '/home/will/bbpro98/re/targets')
import ctree
import ctref

DATA = '/mnt/nvme/bbpro98/targets_data/stats'

def trusted_records(blob):
    """Same as asnref.trusted_records but without the jail (local exploration)."""
    dm = ctree.do_dump(blob)
    act, _ = ctref.check_dump(blob, dm, need_scan=False)
    return dm, act

def stat_records(blob):
    dm, act = trusted_records(blob)
    out = []
    for off, (m, p) in sorted(act.items()):
        if len(p) in (22, 36, 40, 70, 150):
            u = struct.unpack('<%dH' % (len(p) // 2), p)
            if u[0] in (0, 1, 2, 3, 16, 17) and u[1] == 2:
                out.append((off, m, u))
    return dm, out

def groups(recs):
    g = collections.Counter((u[0], len(u) * 2) for _, _, u in recs)
    return g

sys.path.insert(0, '/home/will/bbpro98/BBPRO98_package/research')
import dump_pyr as D

PYR = '/home/will/bbpro98/BBPRO98_package/game/Assn/MLBPA97.PYR'

def load_names(day=None):
    d, recs, inv = D.load(PYR)
    out = {}
    for r in recs:
        p = D.decode(r, inv)
        pid = p[0] | p[1] << 8
        out[pid] = (D.cstr(p[30:47]) + ' ' + D.cstr(p[47:64])).strip() + ' p%d' % p[68]
    return out

NAMES = {}

def nm(pid):
    return NAMES.get(pid, ('?%d' % pid, ''))[0]

def dump_player(day, pid):
    blob = open(f'{DATA}/{day}/mlbpa97.DAT', 'rb').read()
    _, recs = stat_records(blob)
    for off, m, u in recs:
        if u[2] & 0x7fff == pid:
            print('off %8d m %2d len %3d scope %2d w2 %5x' % (off, m, len(u) * 2, u[0], u[2]),
                  list(u[3:]))

if __name__ == '__main__':
    for day in ['day01', 'day02', 'day05', 'day09']:
        blob = open(f'{DATA}/{day}/mlbpa97.DAT', 'rb').read()
        dm, recs = stat_records(blob)
        print(day, 'stat records:', len(recs))
        for k, n in sorted(groups(recs).items()):
            print('   scope %2d len %3d : %5d' % (k[0], k[1], n))
    for f in ['base/mlbpa96e.dat', 'base/_DEFAULT.DAT']:
        blob = open(f'{DATA}/{f}', 'rb').read()
        dm, recs = stat_records(blob)
        print(f, 'stat records:', len(recs))
        for k, n in sorted(groups(recs).items()):
            print('   scope %2d len %3d : %5d' % (k[0], k[1], n))
