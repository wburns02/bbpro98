#!/usr/bin/env python3
"""Analyze the per-day ASN sequence (asnseq/dayNN/Assn/MLBPA97.ASN).
1) churn regions: byte ranges that ever differ across consecutive days
2) arithmetic fields: positions whose u16 LE value increments by a constant
   across all 10 snapshots (head pointers, dates, counters)
Writes re/asnseq/analysis.tsv + prints summary."""
import glob, os, struct

files = sorted(glob.glob('/mnt/nvme/bbpro98/re/asnseq/day*/Assn/MLBPA97.ASN'))
snaps = [open(f, 'rb').read() for f in files]
print(f'{len(snaps)} snapshots, sizes { {len(s) for s in snaps} }')
n = min(map(len, snaps))

# 1) churn regions over consecutive pairs, gap<16
churn = []
for a, b in zip(snaps, snaps[1:]):
    diffs = (i for i in range(n) if a[i] != b[i])
    for i in diffs:
        if churn and i - churn[-1][1] < 16: churn[-1][1] = max(churn[-1][1], i)
        else: churn.append([i, i])
tot = sum(e - s + 1 for s, e in churn)
print(f'{len(churn)} churn regions, {tot} bytes total')
big = sorted(churn, key=lambda r: r[1] - r[0], reverse=True)[:12]
for s, e in big:
    print(f'  region {s:#x}..{e:#x} len {e-s+1}')

# 2) constant-delta u16 fields across all snapshots
hits = []
for off in range(0, n - 2, 2):
    vals = [struct.unpack_from('<H', s, off)[0] for s in snaps]
    d = {vals[i+1] - vals[i] for i in range(len(vals) - 1)}
    if len(d) == 1:
        delta = d.pop()
        if delta != 0:
            hits.append((off, delta, vals))
print(f'{len(hits)} constant-delta u16 fields')
with open('/mnt/nvme/bbpro98/re/asnseq/analysis.tsv', 'w') as f:
    f.write('off\tdelta\tvalues\n')
    for off, delta, vals in hits:
        f.write(f'{off:#x}\t{delta}\t{",".join(map(str, vals))}\n')
        if off < 0x10000:
            print(f'  {off:#08x} +{delta} {vals[:4]}...')
