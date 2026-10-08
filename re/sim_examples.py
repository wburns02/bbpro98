#!/usr/bin/env python3
"""Worked examples for work/SIM_LOGIC_MODEL.md: N records per traced function, picked for distinct results, each one
replayed by its re/sim_model.py model (only passing records are shown). usage: sim_examples.py simtrace.bin [N] [FN ...]
Prints markdown: per function, the record header (this, stack argument, return value) and its events in call order."""
import collections, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_model as sm
from simtrace_dump import NAMES, records, fmt_ev

SKIP = {'catch_adj', 'stamina', 'fatigue'}   # table load / covered by the fatigue section's own example


def fmt(e):
    """fmt_ev with values past 16 bits in hex (getters returning a byte or short leave garbage in the upper bits)"""
    s = fmt_ev(e)
    if abs(e[5]) > 0xffff and s.endswith(f'={e[5]}'): s = s[:-len(str(e[5]))] + f'{e[5] & 0xffffffff:#x}'
    return s


def model_of(name):
    return getattr(sm, 'model_' + name, None)


def main():
    path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    only = set(sys.argv[3:])
    seen = collections.defaultdict(set)
    picked = collections.defaultdict(list)
    pending = {}
    for r in records(path):
        sm.link(r, pending)
        name = NAMES[r['fn']]
        f = model_of(name)
        if not f or name in SKIP or (only and name not in only) or r['over'] or len(picked[name]) >= n: continue
        key = r['ret'] & 0xffff if name != 'lead' else bytes(r['post'][0x16:0x19])
        if key in seen[name] or not r['ev']: continue
        if sm.guard(f, r) is not None: continue
        seen[name].add(key)
        picked[name].append(r)
    for name, rs in picked.items():
        print(f'### {name} ({len(rs)} examples)\n\n```')
        for r in rs:
            print(f"#{r['i']} this={r['self']:#x} arg={r['arg']:#x} ret={r['ret']:#x}")
            ev = ' '.join(fmt(e) for e in sm.Tape(r).ev)
            while ev:
                cut = ev.rfind(' ', 0, 112) if len(ev) > 112 else len(ev)
                cut = cut if cut > 0 else len(ev)
                print('    ' + ev[:cut]); ev = ev[cut:].lstrip()
        print('```\n')


if __name__ == '__main__':
    main()
