"""Reader for FPS Baseball Pro '98 season snapshots. usage: bbstats.py <snapdir> bat|pit [N]"""
import sys, struct, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, '/home/will/bbpro98/BBPRO98_package/research')
sys.path.insert(0, '/home/will/bbpro98/BBPRO98_package/mods')
from lib import load
import dump_pyr as D

def names(pyr):
    d, recs, inv = D.load(pyr); out = {}
    for r in recs:
        p = D.decode(r, inv); pid = p[0] | p[1] << 8
        out[pid] = (D.cstr(p[30:47]) + ' ' + D.cstr(p[47:64])).strip()
    return out

def lines(snap, scope=1):
    """returns {'bat':{id:cols}, 'pit':{id:cols}} for given scope (1=last season, 2=career)"""
    bat, pit = {}, {}
    for pos, rn, off, u in load(os.path.join(snap, 'Stats/mlbpa97.DAT')):
        if u[0] != scope: continue
        if len(u) == 40 // 2 * 2 and False: pass
        n = len(u) * 2
        if n == 40: bat[u[2]] = u[3:]
        elif n == 70: pit[u[2]] = u[3:]
    return bat, pit

if __name__ == '__main__':
    snap, kind = sys.argv[1], sys.argv[2]; top = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    nm = names(os.path.join(snap, 'Assn/MLBPA97.PYR'))
    bat, pit = lines(snap)
    if kind == 'bat':
        rows = []
        for i, c in bat.items():
            ab, s, d, t, hr, rbi, bb, so = c[:8]; h = s + d + t + hr
            if ab >= 300: rows.append((h / ab, i, ab, h, hr, rbi))
        for a, i, ab, h, hr, rbi in sorted(rows, reverse=True)[:top]:
            print('%-24s AB %4d H %3d HR %2d RBI %3d AVG %.3f' % (nm.get(i, i), ab, h, hr, rbi, a))
    else:
        rows = []
        for i, c in pit.items():
            outs, er = c[18], c[26]
            if outs >= 450: rows.append((27 * er / outs, i, outs, c[20], c[21]))
        for e, i, outs, w, l in sorted(rows)[:top]:
            print('%-24s %d-%d IP %d.%d ERA %.2f' % (nm.get(i, i), w, l, outs // 3, outs % 3, e))
