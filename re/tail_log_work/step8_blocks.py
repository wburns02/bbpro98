#!/usr/bin/env python3
"""Parse all 10 days' news sequences: find contiguous record runs between pool markers 0x...0685b1..0x...00 00 STAMP.
Decode type bytes via a table for every record: id(2) tail(10) status(2) ref(4) date(2) 0b 00.
Type bytes = bytes 12,13 (embedded in tail); last 4 of tail = id2."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}

# SMA markers = last 6 bytes of the 512-byte block: b1 00 00 00 04 (idx 29) / b1 00 00 00 04 (idx 30)
def blocks(d):
    return [d[o:o+512] for o in range(0x298000, 0x2a0000, 512)]

MARKER = bytes([0xb1, 0, 0, 0, 4])

for day in (8, 9, 10):
    d = files[day]
    print(f'===== day{day} =====')
    for bi, blk in enumerate(blocks(d)):
        if blk[-11:-6] != MARKER or blk[-6:-4] != MARKER:
            print(f' block{bi} @0x{0x298000+bi*512:x}: no marker (tail: {blk[-32:].hex(" ")})')
            continue
        print(f' block{bi} @0x{0x298000+bi*512:x}: SMA tail {blk[-17:].hex(" ")}')
        # records: 01ffa at pool start
        start = bi*512 + 0x1FA
        off = start
        while off < bi*512 + 0x1FA:
            rec = blk[off-bi*512:off-bi*512+25]
            pid = struct.unpack('<H', rec[0:2])[0]
            typ = rec[12:14].hex(' ')
            b13 = rec[13]
            status = struct.unpack('<H', rec[19:21])[0]
            ref = struct.unpack('<I', rec[14:18])[0]
            date = struct.unpack('<H', rec[21:23])[0]
            print(f'  +{off-bi*512:03x} id={pid:5d} tail={rec[2:12].hex(" ")} typ={typ} b13={b13:02x} status={status:04x} ref={ref:06x} date={date:04x}')
            off += 25
