#!/usr/bin/env python3
"""Dump ALL day09 stamped entries (both clusters, wrap handling), and day10 0x27e6xx cluster (wrap form)."""
import struct

d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()
d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()

def stamps(d, stamp):
    pat = struct.pack('<H', stamp)
    out = []
    i = d.find(pat)
    while i != -1:
        out.append(i)
        i = d.find(pat, i+1)
    return out

print('=== day09 cluster 0x27e2xx (NOT new on day09, from day08) ===')
for p in stamps(d9, 0x2fd5):
    if 0x27e000 <= p < 0x280000:
        st = p - 21
        print(f'{st:06x} abs={p & 0xff:02x} :: {d9[st:st+25].hex(" ")}')

print()
print('=== day10 cluster 0x27e6xx (not changed vs day09? verify) ===')
for p in stamps(d10, 0x2fd6):
    if 0x27e000 <= p < 0x280000:
        st = p - 21
        print(f'{st:06x} abs={p & 0xff:02x} :: {d10[st:st+25].hex(" ")}')

print()
# is the 0x27e2xx cluster in day10 changed?
print('0x27e2a1 day8 vs day9 vs day10 identical?',
      open('/mnt/nvme/bbpro98/re/asnseq/day08/Assn/MLBPA97.ASN','rb').read()[0x27e2a1-21:0x27e2a1-21+25].hex(' ') ==
      d9[0x27e2a1-21:0x27e2a1-21+25].hex(' ') ==
      d10[0x27e2a1-21:0x27e2a1-21+25].hex(' '))
print('so 0x27e2xx cluster = a previous date (Apr 6-7), persisted.')
