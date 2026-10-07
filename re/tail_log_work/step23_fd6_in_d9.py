#!/usr/bin/env python3
"""Confirm: day09 must contain 0x2fd6- stamped entries (Apr 11?) somewhere if day10 has 0x2fd7. Check day9 for 0x2fd6."""
import struct

d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()
pat = struct.pack('<H', 0x2fd6)
pos = []
i = d9.find(pat)
while i != -1:
    pos.append(i)
    i = d9.find(pat, i+1)
print(f'day9: {len(pos)} occurrences of 0x2fd6 in whole file')
for p in pos[:40]:
    st = p - 21
    print(f'{st:06x} (0x{p & 0x1ff:03x} in block) :: {d9[st:st+25].hex(" ")}')
