#!/usr/bin/env python3
"""Check the 0x2fd7-stamped entries in the tail zone 0x29a400..0x29a7ff (day10: Apr 11 game day).
These are separate: 0x29a41a-21=0x29a405; 0x29a442-21=0x29a42d..."""
import struct

d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
pat = struct.pack('<H', 0x2fd7)
pos = []
i = d10.find(pat, 0x298000)
while i != -1:
    pos.append(i)
    i = d10.find(pat, i+1)
print('0x2fd7 stamps (tail):', [hex(p) for p in pos])
allstarts = sorted(set(p-21 for p in pos))
for st in allstarts:
    print(f'{st:06x} :: {d10[st:st+25].hex(" ")}')
