#!/usr/bin/env python3
"""Diff day tails, locate date stamps 0x2FD5/0x2FD6, dump entries."""
import struct, sys

D = '/mnt/nvme/bbpro98/re/asnseq/day'
d9 = open(D+'09/Assn/MLBPA97.ASN','rb').read()
d10 = open(D+'10/Assn/MLBPA97.ASN','rb').read()
print('sizes', len(d9), len(d10))

# find changed ranges vs previous day
def changed_ranges(a, b):
    ranges = []
    i = 0
    n = len(a)
    while i < n:
        if a[i] != b[i]:
            s = i
            while i < n and a[i] != b[i]:
                i += 1
            ranges.append((s, i-1))
        else:
            i += 1
    # merge close ranges
    merged = []
    for s, e in ranges:
        if merged and s - merged[-1][1] <= 8:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged

r109 = changed_ranges(d9, d10)
print('d9->d10 changed ranges:', [(hex(s), hex(e), e-s+1) for s, e in r109])
r89 = None
