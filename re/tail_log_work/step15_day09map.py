#!/usr/bin/env python3
"""Day09 entry map with positional decode from a byte-0 anchor = day_stamp_position - 21 bytes."""
import struct

d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()

allstarts = [x - 21 for x in (0x299c2a, 0x299c43, 0x299c5c, 0x299c75, 0x299c8e,
                              0x299ca7, 0x299cc0, 0x299cd9, 0x299cf2, 0x299d0b,
                              0x299d24, 0x299d3d, 0x299d56, 0x299d6f, 0x299d88, 0x299da1, 0x299dba)]
allstarts = [0x299c15] + allstarts[1:]  # 0x299c2a-21=0x299c15
print('starts:', [hex(x) for x in allstarts])
prev_field = None
for i, st in enumerate(allstarts):
    entry = d9[st:st+25]
    off0 = st & 0xff
    pid = struct.unpack('<H', entry[0:2])[0]
    # tail = entry[2:12] starts 'b5 07' ..., decode by absolute position
    values = {}
    for k in range(2, 12):
        values[off0 + k] = entry[k]
    print(f'{i:2d} {st:06x} b0abs={hex(off0)} {entry.hex(" ")} tail2={entry[2:12].hex(" ")}')
