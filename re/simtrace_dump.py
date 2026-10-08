#!/usr/bin/env python3
"""Dump simtrace.bin records (src-latest/mods/simtrace.c). usage: simtrace_dump.py FILE [FN] [N] [SKIP]"""
import ast, mmap, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simtrace_probes import PROBES

NAMES = ['steal', 'pickoff', 'pitchout', 'offman', 'catch', 'catch_adj', 'fatigue', 'stamina', 'inj_check',
         'inj_type', 'pitch', 'hit_run', 'sacrifice', 'squeeze', 'def_mgr', 'def_strategy', 'def_ratings', 'positioning',
         'replace_p', 'relief_chk', 'relief_pick', 'throw_speed', 'launch', 'lead', 'runner_ai', 'find_fielder', 'throw']


def probe_map(path):
    """Probe ids are list indices of the simtrace_probes.py the trace was built with: when a copy of it sits next to the
    trace, map its ids onto the current PROBES (appending any getter the current list lacks), else ids pass through."""
    side = os.path.join(os.path.dirname(os.path.abspath(path)), 'simtrace_probes.py')
    if not os.path.exists(side): return None
    ns = {l.split('=', 1)[0].strip(): ast.literal_eval(l.split('=', 1)[1]) for l in open(side) if l[:1].isalpha()}
    cur = {p[0]: i for i, p in enumerate(PROBES)}
    m = []
    for p in ns['PROBES']:
        if p[0] not in cur: cur[p[0]] = len(PROBES); PROBES.append(tuple(p))
        m.append(cur[p[0]])
    return m


def records(path):
    pm = probe_map(path)
    f = open(path, 'rb')
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    X = 16 if len(m) % 4504 == 0 and len(m) % 4492 else 4   # v2 records carry 4 extra fields (4504 bytes), v1 one
    H = 376 + X + 32
    R = H + 16 * 255
    for i in range(len(m) // R):
        b = m[i * R:(i + 1) * R]
        fn, dep, n, over = b[0], b[1], b[2], b[3]
        self_, arg, ret, rm0, rm1, ri0, ri1 = struct.unpack_from('<7I', b, 4)
        ev = [struct.unpack_from('<BBHiii', b, H + 16 * j) for j in range(n)]
        if pm: ev = [(e[0], pm[e[1]]) + e[2:] if e[0] in (88, 89) else e for e in ev]   # X / Y events
        yield dict(i=i, fn=fn, depth=dep, over=over, self=self_, arg=arg, ret=ret, rm0=rm0, rm1=rm1, ri0=ri0, ri1=ri1,
                   game=b[32:112], mflags=b[112:120], obj=b[120:376], xf=b[376:376 + X].ljust(16, b'\0'),
                   post=b[376 + X:H], ev=ev)


def fmt_ev(e):
    t, g, idx, a, b_, r = e
    t = chr(t)
    if t == 'P': return f'PB[{idx}]={r}'
    if t == 'S': return f'speed({a:#x})={r}'
    if t == 'R': return f'{t}{g}({a},{b_})={r}'
    if t in 'GHK': return f'{t}[{a & 0xffff:x}:{idx}]={r}'
    if t == 'F': return f'F[{a & 0xffff:x}]={r}'
    if t == 'W': return f'W[{a & 0xffff:x}]:={idx}'
    if t == 'X': return f'X{g}[{PROBES[g][0]:x}]({a & 0xffffffff:x}{"," + str(b_) if PROBES[g][1] else ""}{"," + str(idx) if PROBES[g][1] > 1 else ""})={r}'
    if t == 'Y': return f'Y{g}{{'
    if t == 'Z': return f'Z<{NAMES[g]}>'
    return f'{t}{g}({a})={r}' + (f'@{b_ & 0xffffffff:x}' if g == 0 else '')


if __name__ == '__main__':
    path = sys.argv[1]
    fn = int(sys.argv[2]) if len(sys.argv) > 2 else None
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    skip = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    for r in records(path):
        if fn is not None and r['fn'] != fn: continue
        if skip: skip -= 1; continue
        print(f"#{r['i']} {NAMES[r['fn']]} d{r['depth']} this={r['self']:#x} arg={r['arg']:#x} ret={r['ret']:#x} "
              f"rm {r['rm0']:#x}->{r['rm1']:#x} ri {r['ri0']:#x}->{r['ri1']:#x} over={r['over']}")
        print('   ', ' '.join(fmt_ev(e) for e in r['ev']))
        n -= 1
        if not n: break
