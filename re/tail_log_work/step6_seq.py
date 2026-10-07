#!/usr/bin/env python3
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
d9 = open(D+'09/Assn/MLBPA97.ASN','rb').read()
d10 = open(D+'10/Assn/MLBPA97.ASN','rb').read()

# Sequence structure hypothesis:
# header(29 bytes at 0x...1a) then records of 25 bytes: id(2) ... tail(10) = 00 [b1 b2 b3] xx xx/ff date(2) 0b 00
# Check all new day09 and day10 sequences.
def check(start, end, d, label):
    print(f'== {label} 0x{start:x}-0x{end:x}')
    off = start
    while off < end:
        rec = d[off:off+25]
        b = rec.hex(' ')
        date = struct.unpack('<H', rec[21:23])[0]
        print(f'{off:06x} {b} date={date:04x}')
        off += 25

print('--- day10 new seq A (0x299e1a+) ---')
check(0x299e1a, 0x299fca, d10, 'A')
