#!/usr/bin/env python3
"""Dump all day09 entries that appear in the 0x298000-0x29a200 zone: which blocks contain day09-stamped entries (where)?"""
import struct

d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()
d8 = open('/mnt/nvme/bbpro98/re/asnseq/day08/Assn/MLBPA97.ASN','rb').read()
d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
STAMP9 = 0x2fd5
STAMP10 = 0x2fd6

pat9 = struct.pack('<H', STAMP9)
pos = []
i = d9.find(pat9)
while i != -1:
    pos.append(i)
    i = d9.find(pat9, i+1)
print(f'day09: {len(pos)} occurrences of 0x2fd5 in the whole file')
# cluster by sector
for p in pos:
    base = p & ~0x1ff
    print(f'  stamp 0x2fd5 at 0x{p:x} ({hex(p & 0xff)} in sector 0x{base:x})')
