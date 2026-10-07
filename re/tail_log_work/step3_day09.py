#!/usr/bin/env python3
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
d9 = open(D+'09/Assn/MLBPA97.ASN','rb').read()
d10 = open(D+'10/Assn/MLBPA97.ASN','rb').read()

def find_stamp(d, stamp, lo=0, hi=None):
    pat = struct.pack('<H', stamp)
    out = []
    i = d.find(pat, lo)
    while i != -1 and (hi is None or i < hi):
        out.append(i)
        i = d.find(pat, i+1)
    return out

# day09 entries: stamps at 0x299c2a.. every 25 bytes; entries start = stamp-21
s9 = find_stamp(d9, 0x2FD5, 0x298000)
print('day09 candidate entry starts:')
for p in s9:
    st = p - 21
    # consistency: check previous entry start +25 == this (except first of a run)
    print(hex(st), d9[st:st+25].hex(' '))

# Full day09-scan for stamps (whole file) to see if entries elsewhere
all9 = find_stamp(d9, 0x2FD5)
clusters = {}
for p in all9:
    clusters.setdefault(p - 21, []).append(p)
# group consecutive stride-25
runs = []
for st in sorted(clusters):
    if runs and st - runs[-1][1] <= 25:
        runs[-1] = (runs[-1][0], st)
    else:
        runs.append((st, st))
print('day09 day-stamp clusters (whole file, entry starts):')
for a, b in runs:
    print(hex(a), '-', hex(b), 'count', len(clusters[b]))
