#!/usr/bin/env python3
"""Merge pass-2 audit verdicts into work/BBSIM_SPEC.md audit column.
Idempotent: re-running refreshes cells with newer verdicts."""
import re, glob, os

SPEC = '/home/will/bbpro98/work/BBSIM_SPEC.md'
AUD = '/mnt/nvme/bbpro98/re/spec_audit'
s = open(SPEC).read()

def verdict_for(addr):
    for suf in ['', '_part1']:
        p = f'{AUD}/FUN_{addr}{suf}.txt'
        if os.path.exists(p):
            m = re.search(r'VERDICT:\s*(\w+)', open(p).read())
            if m:
                tag = f'FUN_{addr}{suf}'
                cell = {'MATCH': 'MATCH (audit pass 2)',
                        'PARTIAL': f'PARTIAL (pass 2, see re/spec_audit/{tag}.txt)',
                        'MISMATCH': f'MISMATCH (pass 2, see re/spec_audit/{tag}.txt)'}.get(m.group(1))
                if cell:
                    return cell
    return None

n = 0
for m in re.finditer(r'^\| ([0-9a-f]{8}) \|([^|]*)\|([^|]*)\|([^|]*)\|$', s, flags=re.M):
    addr, mod, pb, audit = m.groups()
    v = verdict_for(addr)
    if v and v != audit.strip():
        s = s[:m.start(4)] + f' {v} ' + s[m.end(4):]
        n += 1

# chunked function header: replace garbage params count
s = s.replace('FUN_68044cbd (112 params): draft only, part 1 audited',
              'FUN_68044cbd (this,2 args; the old "112 params" header counted PB-getter calls): '
              'draft in 2 chunks, see audit for part 1')
open(SPEC, 'w').write(s)
print(f'{n} audit cells updated')
