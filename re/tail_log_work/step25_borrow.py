#!/usr/bin/env python3
"""Verify entry borrowing hypothesis: the day9 0x2fd6 entry at 0x299e15 (idle 00 11 00 a9 01, code=01 ref=75 4e 03)
   should decode with the PREVIOUS entry's fields: 0x4a9d1 = 4d 01 00 00 00 00 ff -> subject idle/claims glyph."""
import struct

d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()
# the day9 0x2fd6 entry at 0x299e15 = idle reference to 0x4e75
# found a day9 0x2fd6 entry at 0x299e15: let me check whether the record 25 bytes back is 0x4a9d1
off = 0x299e15 - 25
print('prev entry:', hex(off), d9[off:off+25].hex(' '))
EOF_MARKER = None
