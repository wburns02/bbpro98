#!/usr/bin/env python3
"""FINAL MODEL TEST: news blocks = 512B sectors. Layout: +0x15 = first record; 25-byte records stride 25;
'00 12 <ptr16>' head record at +0x15 (ptr = next/prev block addr >>8 for SOME record class); pool at +0x1e5.
Verify record start +0x15 for every stamp: stamp-%+0x2a should be multiple of 25 within blocks base+512k."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}

for day in (8, 9, 10):
    d = files[day]
    ok = 0; bad = []
    for base in range(0x298000, 0x2a0000, 512):
        for k in range(0, 19):
            sp = base + 0x2a + 25*k
            stamp = struct.unpack('<H', d[sp:sp+2])[0]
            if stamp in range(0x2fd0, 0x2fda) and (stamp & 0xff) in range(0xb, 0x11):
                pass
    # simpler: collect stamps at +0x2a+25k
    entry_count = 0
    for base in range(0x298000, 0x2a0000, 512):
        for k in range(0, 19):
            sp = base + 0x2a + 25*k
            st = sp - 21
            stamp = struct.unpack('<H', d[sp:sp+2])[0]
            nxt = struct.unpack('<H', d[sp+2:sp+4])[0]
            if stamp >> 8 in (0x2e, 0x2f, 0x30, 0x31) and (stamp & 0xff) < 0x20:
                # looks like a date stamp; check 0b 00 follows
                if d[sp+2:sp+4] == b'\x0b\x00' or d[sp+24] == 0:
                    entry_count += 1
    print(f'day{day}: {entry_count} date-stamped records at +0x2a+25k')
