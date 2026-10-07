#!/usr/bin/env python3
"""Full parse: blocks whose byte at +0x1e9 is a day stamp low byte 0x2e/0x2f (0x2e/0x2f << 8 | 0x0b)"""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}

# entry tail form at end of block: b0.. = '... 04 00 00 <stamp> 0b 00 <byte24>' with stamp at 0x1e9+21-25=?
# Simplest: blocks with stamp at +0x1e9+26? Actually look for the pattern: d[base+0x1e6:base+0x1eb] == '00 04 05 06 85'
MARK = bytes([0, 4, 5, 6, 0x85])
for day in range(8, 11):
    d = files[day]
    print(f'===== day{day} blocks with 85b1 pool end:')
    for base in range(0x298000, 0x2a0000, 512):
        if d[base+0x1e6:base+0x1eb] == MARK:
            # stamp at +0x1eb
            st = struct.unpack('<H', d[base+0x1eb:base+0x1ed])[0]
            print(f'  base=0x{base:x} stamp=0x{st:04x} pooltail={d[base+0x1ed:base+0x1f1].hex(" ")} rec24={d[base+0x1f1:base+0x200].hex(" ")}')
