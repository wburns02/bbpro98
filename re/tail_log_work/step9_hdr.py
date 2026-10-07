#!/usr/bin/env python3
"""Parse one news block: header 29 bytes (ends 0x...1c incl), records 1ffa/d1 => 25/22 bytes, pool tail."""
import struct

def parse_block(d, base):
    assert d[base-6:base-1] == bytes([0xb1,0,0,0,4]), d[base-6:base]
    hdr = d[base:base+29]
    seq_lo, pool_end, pool_rooms, seq_len, cnt = struct.unpack('<4HI', hdr[6:6+4+2+4])
    tot = struct.unpack('<H', hdr[26:28])[0]
    zero = hdr[28]
    rec_start = base + 0x1FA
    print(f'hdr: seq_lo={seq_lo:04x} pool_end={pool_end:04x} rooms={pool_rooms} rec_stride={seq_len} cnt={cnt} tot={tot}')
    off = rec_start
    out = []
    # wipe = ff after header; then records start where wipe differs
    # simple approach: parse while stamp or terminators look sane; use d (previous day) to distinguish
    return hdr

d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()

for base in range(0x298000, 0x2a0000, 512):
    if d10[base-6:base-1] == bytes([0xb1,0,0,0,4]):
        print(f'--- block base=0x{base:x}')
        hdr = parse_block(d10, base)
        # records from base+0x1fa
        off = base + 0x1fa
        # stop at index 0x1e5 = pool
        while off < base + 0x1e5:
            rec = d10[off:off+25]
            pid = struct.unpack('<H', rec[0:2])[0]
            ch12, ch13 = rec[12], rec[13]
            status = struct.unpack('<H', rec[19:21])[0]
            ref = struct.unpack('<I', rec[14:18])[0]
            date = struct.unpack('<H', rec[21:23])[0]
            tail = rec[2:12]
            if ch13 == 0xff:
                b13 = 'ff'
            else:
                b13 = f'{ch13:02x}'
            print(f'+{off-base-0x1fa:03x} id={pid:5d} tail={tail.hex(" ")} c12={ch12:02x} c13={b13} status={status:04x} ref={ref:06x} date={date:04x}')
            off += 25
        print(f' pool: {d10[base+0x1e5:base+0x1fa].hex(" ")}')
