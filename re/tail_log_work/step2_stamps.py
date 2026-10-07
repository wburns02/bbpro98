#!/usr/bin/env python3
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
d8 = open(D+'08/Assn/MLBPA97.ASN','rb').read()
d9 = open(D+'09/Assn/MLBPA97.ASN','rb').read()
d10 = open(D+'10/Assn/MLBPA97.ASN','rb').read()

# changed sector-start offsets (ends in 0x1a) that are record anchors
def anchors(a, b, lo, hi):
    return [i for i in range(lo, hi) if a[i] != b[i] and (i & 0xff) == 0x1a]

# 1. find all occurrences of date stamp bytes in tails
def find_stamp(d, stamp):
    pat = struct.pack('<H', stamp)
    out = []
    i = d.find(pat, 0x290000)
    while i != -1:
        out.append(i)
        i = d.find(pat, i+1)
    return out

s9 = [i for i in find_stamp(d9, 0x2FD5) if i >= 0x298000]
s10 = [i for i in find_stamp(d10, 0x2FD6) if i >= 0x298000]
print('day10 0x2FD6 stamp positions (tail):', len(s10))
print([hex(x) for x in s10])
print('day09 0x2FD5 stamp positions (tail):', len(s9))
print([hex(x) for x in s9])
print()
# sector anchors changed d9->d10 in tail
print('d9->d10 anchors in 0x298000-0x2A0000:', [hex(x) for x in anchors(d9, d10, 0x298000, 0x2A0000)])
# day08->09 anchors: find d9 tail changed range
print('d8->d9 anchors in 0x298000-0x2A0000:', [hex(x) for x in anchors(d8, d9, 0x298000, 0x2A0000)])
