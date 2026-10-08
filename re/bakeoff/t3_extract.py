#!/usr/bin/env python3
"""Bake-off tier 3 data: the st8 runner_ai records (FUN_6804faa1, simtrace target 24) as self-contained JSON lines,
split in trace order: the first half is the lanes' dev set, the second half the holdout they never see.

usage: t3_extract.py [NAME [TAG]]   NAME a simtrace target (default runner_ai), TAG the target dir name (default t3rai)
       -> /mnt/nvme/bbpro98/targets_data/TAG/records.jsonl, /mnt/nvme/bbpro98/targets_holdout/TAG/...

Each line: i (record index in st8), fn, depth, self, arg, ret, rm0, rm1, ri0, ri1, game / mflags / obj / xf / post (hex),
ev = [[type, gen, idx, a, b, r, va], ...] where type is the event letter and va the probed getter's address for X / Y
events (probe ids are mapped through the trace's own simtrace_probes.py sidecar, so the file needs no probe table).
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from simtrace_dump import NAMES, records
from simtrace_probes import PROBES

SRC = '/mnt/nvme/bbpro98/re/hookab/st8/simtrace.bin'
NAME = sys.argv[1] if len(sys.argv) > 1 else 'runner_ai'
TAG = sys.argv[2] if len(sys.argv) > 2 else 't3rai'
FN = NAMES.index(NAME)
OUT = {'dev': f'/mnt/nvme/bbpro98/targets_data/{TAG}', 'holdout': f'/mnt/nvme/bbpro98/targets_holdout/{TAG}'}


def row(r):
    ev = [[chr(e[0]), e[1], e[2], e[3], e[4], e[5], PROBES[e[1]][0] if chr(e[0]) in 'XY' else 0] for e in r['ev']]
    d = {k: r[k] for k in ('i', 'fn', 'depth', 'over', 'self', 'arg', 'ret', 'rm0', 'rm1', 'ri0', 'ri1')}
    d.update({k: bytes(r[k]).hex() for k in ('game', 'mflags', 'obj', 'xf', 'post')})
    d['ev'] = ev
    return d


rs = [row(r) for r in records(SRC) if r['fn'] == FN]
assert rs and not any(r['over'] for r in rs), f'{NAME} records overflowed'
h = len(rs) // 2
for part, sel in (('dev', rs[:h]), ('holdout', rs[h:])):
    os.makedirs(OUT[part], exist_ok=True)
    with open(OUT[part] + '/records.jsonl', 'w') as o:
        for d in sel: o.write(json.dumps(d, separators=(',', ':')) + '\n')
    print(part, len(sel), OUT[part] + '/records.jsonl')
