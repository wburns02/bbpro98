#!/usr/bin/env python3
"""Parse news blocks using tail markers: last 25 bytes of each block = record 24; blocks whose last record ends '00 00 <stamp> 0b 00' with room structure."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}

# Marker: last record of block at base+0x1e6 .. the extra (0x0685b1) 6 bytes = '00 04 05 06 85 b1'
# Actually last record starts at 0x1e6: 22 bytes -> 0x1fc; then bytes 0x1fc-0x200 = ?
# The tail bytes: '...04 00 00 <stamp> 0b 00' - the last real record ends at 0x1fc; the 4 bytes leftover
# Let me just parse header at base+29 with fields read as observed:
# hdr[0:2]=seq_lo, [2:4]=cnt, [4:6]=freeform??, [6:10]=seq_lo2, [10:14]=pool_end, [14:16]=rooms, [16:20]=stride, [20:24]=cnt, [26:28]=tot, [28]=pad
def hdr_of(d, base):
    hdr = d[base+29:base+29+37]
    return hdr

for day in (8, 9, 10):
    d = files[day]
    print(f'===== day{day} headers =====')
    for base in range(0x298000, 0x2a0000, 512):
        last = d[base+0x1e6:base+0x1fb]
        hdr = hdr_of(d, base)
        seq_lo, cnt, pad = struct.unpack('<HHB', hdr[0:5])
        seq_lo2, pool_end, rooms = struct.unpack('<HIH', hdr[5:13])
        stride, cnt2 = struct.unpack('<IH', hdr[13:19])
        tot = struct.unpack('<H', hdr[25:27])[0]
        # check
        print(f'base=0x{base:x} hdr0={seq_lo:04x} cnt={cnt:3d} seq_hi={seq_lo2:04x} pool_end={pool_end:04x} rooms={rooms} stride={stride} cnt2={cnt2} tot={tot:02x}')
    print()
    if day == 8:
        break
