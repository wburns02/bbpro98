#!/usr/bin/env python3
"""Dump raw header bytes 29..69 for each valid block."""
import struct

d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()
d8 = open('/mnt/nvme/bbpro98/re/asnseq/day08/Assn/MLBPA97.ASN','rb').read()

for base in range(0x298000, 0x29a000, 512):
    hdr8 = d8[base+29:base+29+42]
    hdr9 = d9[base+29:base+29+42]
    hdr10 = d10[base+29:base+29+42]
    print(f'--- base=0x{base:x}')
    print(' d8 :', hdr8.hex(' '))
    print(' d9 :', hdr9.hex(' '))
    print(' d10:', hdr10.hex(' '))
