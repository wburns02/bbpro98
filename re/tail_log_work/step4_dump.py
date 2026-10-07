#!/usr/bin/env python3
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {}
for i in range(1, 11):
    files[i] = open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read()

def find_stamp(d, stamp, lo=0, hi=None):
    pat = struct.pack('<H', stamp)
    out = []
    i = d.find(pat, lo)
    while i != -1 and (hi is None or i < hi):
        out.append(i)
        i = d.find(pat, i+1)
    return out

d10 = files[10]
print('=== new day10 entries (tail zone 0x29..) ===')
s10 = find_stamp(d10, 0x2FD6, 0x298000)
starts = [p-21 for p in s10]
# handle wrap: sector starts end in 0x1a
def dump_entry(d, off):
    return d[off:off+25].hex(' ')

prev = None
for i, st in enumerate(starts):
    entry = d10[st:st+25]
    stamp = struct.unpack('<H', entry[21:23])[0]
    print(f'{i:3d} {hex(st)} {entry.hex(" ")}')
