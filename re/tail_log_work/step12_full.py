#!/usr/bin/env python3
"""Full parse: for day9, day10: for each block with a stamp tail, parse seq of 25B records until 0x1e6."""
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
files = {i: open(D+f'{i:02d}/Assn/MLBPA97.ASN','rb').read() for i in range(1, 11)}

STAMP_LO = {day: (47 << 8) | (213 + day - 1) for day in range(1, 11)}

def parse(d, day, lo=0x298000, hi=0x2a0000):
    stamp = STAMP_LO[day]
    stamp_b = struct.pack('<H', stamp)
    out = []
    for base in range(lo, hi, 512):
        last = d[base+0x1e6:base+0x1fb]
        # tail form: xx xx xx xx xx STAMP_LO(b?) 0b 00 ...
        if last[-4:-2] != stamp_b:
            continue
        hdr = d[base+29:base+51]
        seq = []
        off = base + 0x1fa
        while off < base + 0x1e6:
            rec = d[off:off+25]
            if len(rec) < 25:
                break
            pid = struct.unpack('<H', rec[0:2])[0]
            st = struct.unpack('<H', rec[19:21])[0]
            ref = struct.unpack('<I', rec[14:18])[0]
            dt = struct.unpack('<H', rec[21:23])[0]
            seq.append((pid, rec[2:12].hex(' '), rec[12:14].hex(' '), st, ref, dt))
            off += 25
        if seq:
            out.append((base, hdr.hex(' '), seq))
    return out

for day in (9, 10):
    print(f'================ day{day} ================')
    for base, hdr, seq in parse(files[day], day):
        print(f'-- block 0x{base:x} hdr(29..50)={hdr}')
        for pid, t, c, st, ref, dt in seq:
            print(f'   id={pid:5d} tail={t} code={c} status={st:04x} ref={ref:06x} date={dt:04x}')
