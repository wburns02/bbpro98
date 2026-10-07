#!/usr/bin/env python3
"""Full dump of ALL day10 stamped (0x2fd6) entries anywhere in file, grouped by block+cluster."""
import struct

d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()

pat = struct.pack('<H', 0x2fd6)
pos = []
i = d10.find(pat, 0x160000)
while i != -1:
    pos.append(i)
    i = d10.find(pat, i+1)

# group into clusters by consecutive stride-25 (allowing wrap restart at 0x1a)
clusters = []
for p in pos:
    st = p - 21
    if clusters and (st - clusters[-1][-1]) % 512 <= 25 and st - clusters[-1][-1] > 0 and st - clusters[-1][-1] <= 25:
        clusters[-1].append(st)
    elif clusters and ((st & 0xff) == 0x15) and ((st - clusters[-1][-1]) >= -0x14 or (st - clusters[-1][-1]) < 0x20):
        clusters[-1].append(st)
    else:
        clusters.append([st])
for c in clusters:
    print(f'--- cluster 0x{c[0]:x}..0x{c[-1]:x} ({len(c)} entries)')
    for st in c:
        changed = d9[st:st+25] != d10[st:st+25]
        # new: check whether the block changed day9->day10
        print(f'{st:06x} {"NEW" if changed else "old"} :: {d10[st:st+25].hex(" ")}')
