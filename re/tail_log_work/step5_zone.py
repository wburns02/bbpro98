#!/usr/bin/env python3
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
d9 = open(D+'09/Assn/MLBPA97.ASN','rb').read()
d10 = open(D+'10/Assn/MLBPA97.ASN','rb').read()

def hexd(d, a, b, label):
    print(label)
    for off in range(a, b, 16):
        row = d[off:off+16]
        mark = ' *' if d9[off:off+16] != d10[off:off+16] else ''
        print(f'{off:06x}  {row.hex(" ")}{mark}')

hexd(d9, 0x29a400, 0x29a800, '--- day09 0x29a400-0x29a800 (* = differs from day10)')
print()
hexd(d10, 0x29a400, 0x29a800, '--- day10 0x29a400-0x29a800')
