#!/usr/bin/env python3
"""Full build: parse every entry in day10 (and day09/day08 spreadsheets) and dump all fields with wrap handling.
Sector-start wrap: record field data may not start at byte 0 of the entry."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}
STAMP = {day: (47 << 8) | (213 + day - 1) for day in range(1, 11)}

def sector_wrap_anchor(stamp_pos):
    """The 25-byte record for the entry with stamp at stamp_pos: if stamp_pos&0xff in 0x1a.. (wrap):
    the fields start at 0x1a of the previous sector and overflow. Check."""
    st = stamp_pos - 21
    return st

# For day10: at wraparound the stamp_pos is 0x...2a; the entry starts at 0x...15-25...
# The tail_log_work decode: sector-start = (stamp_pos - 21) & 0xff, wrap = (stamp_pos - 21) & 0xff == 0x15
# We handle sectors where entry start <= stamp_pos; otherwise the entry is split.
# For day10 spans: check wrap entries = those where (stamp_pos & 0xff) <= 0x15+25?
# All day10 entries: list stamp positions
d10 = files[10]

# For each day10 stamp: entry start = stamp - 21; record any that straddle sector boundary.
all_stamp_pos = []
i = d10.find(struct.pack('<H', 0x2FD6), 0x298000)
while i != -1:
    all_stamp_pos.append(i)
    i = d10.find(struct.pack('<H', 0x2FD6), i+1)

wraps = [p for p in all_stamp_pos if (p & 0xff) < 0x18 and (p & 0xff) >= 0x1a - 21 + 5]
print('wrap stamp positions:', [hex(p) for p in wraps if 0x9e1a <= (p - 21) <= 0xa7ff])

# How to decode the wrap entry: header (14 bytes Subject/Affected) live in the previous sector.
# The volume we have: the wrap entry at 0x29a215 has the stamp at 0x29a22a (stamp_pos - 0x15).
# Byte map at wrap: fields wrap around the 512-byte sector: aff bytes prev sector 0x1f4..0x1fa
for p in [0x29a22a]:
    st = p - 21
    secoff = st & ~0xff
    print('wrap entry at', hex(st), 'sector', hex(secoff))
    print('  sector bytes 0x1f4..0x200:', d10[secoff+0x1f4:secoff+0x200].hex(' '))
    print('  entry bytes:', d10[st:st+25].hex(' '))
