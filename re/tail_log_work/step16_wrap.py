#!/usr/bin/env python3
"""Decode affected-fieldwow for each record (day08-10): handle the 0x1a wraparound case where
record start = sector_start = (day_stamp_pos - 21) but affected fields are at day_stamp_pos - 0x18..+1."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}

def entry_record(d, day_stamp_pos):
    """Return the record's day_stamp position and its subject/affected/ref/status fields, using:
    idle/claims/game_ref glyphs: id = entry bytes 0-1 at day_stamp_pos-21"""
    st = day_stamp_pos - 21
    entry = d[st:st+25]
    # check: id misaligned
    pid = struct.unpack('<H', entry[0:2])[0]
    # recompute pid from entry bytes as day_stamp_pos-2-2 (news refs use day_stamp_pos-relative id misalign)
    # try to find a PYR id in bytes day_stamp_pos-23..day_stamp_pos-21 or -21..-19
    pid_alt1 = struct.unpack('<H', d[day_stamp_pos-21:day_stamp_pos-19])[0]
    pid_alt2 = struct.unpack('<H', d[day_stamp_pos-23:day_stamp_pos-21])[0]
    return pid, entry

# The day10 wraparound example: 0x29a215. The "idle/claim" pair 0x1d4 a1 06 / 0x1d8 dd 08 were idle fields in the entry.
d10 = files[10]
# wraparound at 0x29a215: DAY stamp at 0x29a22a; pack it
for pos in (0x29a22a,):
    st = pos - 21
    print(hex(pos), 'entry at', hex(st), ':', d10[st:st+25].hex(' '))
    # the affected/idle bytes at pos-0x18..pos-0x1a
    print('  affected bytes at pos-0x18:', d10[pos-0x18:pos-0x14].hex(' '))
    # what day_stamp_pos-23 gives
    print('  bytes at pos-23:', d10[pos-23:pos-19].hex(' '))
