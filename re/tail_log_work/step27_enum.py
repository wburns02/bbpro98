#!/usr/bin/env python3
"""Full enumeration of news blocks day10: every block base, stamp list at +0x2a+25k, plus the last record.
Also decode all fields for the day10 0x2fd6/0x2fd7 entries."""
import struct

d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()

for base in range(0x298000, 0x2a0000, 512):
    stamps = []
    for k in range(0, 19):
        sp = base + 0x2a + 25*k
        stamp = struct.unpack('<H', d10[sp:sp+2])[0]
        if 0x2fd0 <= stamp <= 0x2fd8:
            stamps.append((k, hex(stamp), sp))
    if stamps:
        print(f'block 0x{base:x}: {len(stamps)} stamped records: {[(k, s) for k, s, _ in stamps]}')
        changed = sum(1 for _, _, sp in stamps if d9[sp-21:sp+4] != d10[sp-21:sp+4])
        print(f'   changed vs day9: {changed}/{len(stamps)}')
