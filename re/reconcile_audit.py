#!/usr/bin/env python3
"""Reconcile GLM audit verdicts against the proven PB-getter identity.

FUN_68003170(idx) = *(u32*)(&DAT_6808fde0 + idx*4)  (verified 2026-10-07;
pb_table addr == 0x6808fde0 + idx*4 for sampled rows). A decompile never
shows PB names or defaults inline; it shows getter calls. So audit bullets
that call draft PB names/defaults "invented"/"unsupported" are false
positives when the draft's claims match pb_table_FastSim.tsv at those
indices. Everything else stays flagged for brain review.

Writes /mnt/nvme/bbpro98/re/spec_audit/RECONCILE.md
"""
import re, glob, os, csv

TAB = {}
with open('/mnt/nvme/bbpro98/re/pb_table_FastSim.tsv') as f:
    for row in csv.DictReader(f, delimiter='\t'):
        TAB[int(row['idx'])] = row

FP_MARKERS = ('invented', 'appear nowhere', 'no naming evidence',
              'cannot be supported', 'opaque', 'no PB symbol',
              'no constant appears', 'not supported', 'no evidence')

def draft_pb_claims(draft):
    """{name: (idx, default)} the draft asserts via getter indices or names."""
    claims = {}
    for m in re.finditer(r'0x([0-9a-fA-F]+)', draft):
        idx = int(m.group(1), 16)
        if idx in TAB:
            claims[TAB[idx]['name']] = idx
    for row in TAB.values():
        if row['name'] in draft:
            claims[row['name']] = int(row['idx'])
    return claims

def hexrefs(line):
    return {int(h, 16) for h in re.findall(r'0x([0-9a-fA-F]+)', line)}

rows = []
for apath in sorted(glob.glob('/mnt/nvme/bbpro98/re/spec_audit/FUN_*.txt')):
    fn = os.path.basename(apath)[:-4]
    dpath = f'/mnt/nvme/bbpro98/re/spec/{fn}.md'
    if not os.path.exists(dpath):
        rows.append((fn, '?', 0, 0, 'no draft')); continue
    audit = open(apath).read()
    verdict = re.search(r'VERDICT:\s*(\w+)', audit)
    verdict = verdict.group(1) if verdict else '?'
    bullets = [l.strip('- ').strip() for l in audit.splitlines()
               if l.startswith('- ') and l.strip('- ').strip()]
    if not bullets:
        rows.append((fn, verdict, 0, 0, '')); continue
    draft = open(dpath).read()
    claims = draft_pb_claims(draft)
    fp, real = [], []
    for b in bullets:
        low = b.lower()
        idxs = {i for i in hexrefs(b) if i in TAB}
        is_fp = any(m in low for m in FP_MARKERS)
        if is_fp and idxs and all(str(i) or True for i in idxs):
            # false positive iff every table-resolved index the bullet cites
            # has its name (and cited default) matching the draft claims
            ok = True
            for i in idxs:
                name = TAB[i]['name']
                if name not in claims:
                    ok = False
                else:
                    dm = re.search(re.escape(name) + r'[^0-9]{0,40}?(-?\d+)', draft)
                    if dm and dm.group(1) != TAB[i]['dll_default']:
                        ok = False
            if ok:
                fp.append(b); continue
        real.append(b)
    rows.append((fn, verdict, len(bullets), len(fp),
                 '; '.join(x[:160] for x in real)))

out = ['# Audit reconciliation (2026-10-07)', '',
       'Getter identity verified: FUN_68003170(idx) = *(u32*)(&DAT_6808fde0 + idx*4);',
       'pb_table addr column == base + idx*4 (checked idx 771: 0x680909ec - 0x6808fde0 = 0xC0C = 771*4).',
       'Bullets flagged FP cite indices whose names and defaults match pb_table_FastSim.tsv.',
       '', '| function | audit | bullets | FP | remaining |', '|---|---|---|---|---|']
n_fp = n_real = 0
for fn, v, nb, nfp, rest in rows:
    n_fp += nfp; n_real += nb - nfp
    out.append(f'| {fn} | {v} | {nb} | {nfp} | {rest[:200] or "none"} |')
out += ['', f'Totals: {sum(nb for _,_,nb,_,_ in rows)} bullets, {n_fp} false positives, {n_real} still to review', '']
for fn, v, nb, nfp, rest in rows:
    if rest:
        out += [f'## {fn} ({v})'] + [f'- {rest}'] + ['']
open('/mnt/nvme/bbpro98/re/spec_audit/RECONCILE.md', 'w').write('\n'.join(out))
print(f'{len(rows)} audited, {n_fp} FP, {n_real} remaining')
for fn, v, nb, nfp, rest in rows:
    if rest: print('REVIEW', fn, v)
