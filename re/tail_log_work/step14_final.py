#!/usr/bin/env python3
"""Final parse: block marker = bytes +0x1e0..0x1e5 == b1 00 00 00 04 00 (idx 29/30 cluster ends +0x1e5? actually 85 b1 = cluster-1 end at 0x1e5)."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}
STAMP = {day: (47 << 8) | (213 + day - 1) for day in range(1, 11)}

# check marker: bytes +0x1e5 == 'b1 00 00 00 04 00'
MARK = bytes([0xb1, 0, 0, 0, 4, 0])

for day in range(8, 11):
    d = files[day]
    print(f'===== day{day} news blocks:')
    for base in range(0x298000, 0x2a0000, 512):
        if d[base+0x1e5:base+0x1eb] != MARK:
            continue
        st = struct.unpack('<H', d[base+0x1eb:base+0x1ed])[0]
        print(f'  base=0x{base:x} stamp=0x{st:04x} expect=0x{STAMP[day]:04x}')
        # header at +29: 19 bytes
        hdr = d[base+29:base+51]
        print(f'    hdr: {hdr.hex(" ")}')
        # records from +0x1fa to +0x1e6
        off = base + 0x1fa
        while off < base + 0x1e6:
            rec = d[off:off+25]
            pid = struct.unpack('<H', rec[0:2])[0]
            stat = struct.unpack('<H', rec[19:21])[0]
            ref = struct.unpack('<I', rec[14:18])[0]
            dt = struct.unpack('<H', rec[21:23])[0]
            print(f'    +{off-base-0x1fa:03x} id={pid:5d} tail={rec[2:12].hex(" ")} code={rec[12:14].hex(" ")} stat={stat:04x} ref={ref:06x} date={dt:04x}')
            off += 25
        print(f'    next_block_last_rec: {d[base+0x1e6:base+0x200].hex(" ")}')
