#!/usr/bin/env python3
import struct

D = '/mnt/nvme/bbpro98/re/asnseq/day'
d9 = open(D+'09/Assn/MLBPA97.ASN','rb').read()
d10 = open(D+'10/Assn/MLBPA97.ASN','rb').read()

def scan(d, stamp, lo, hi, label):
    pat = struct.pack('<H', stamp)
    # find all stamp positions, entry = pos-21; then check id sane
    out = []
    i = d.find(pat, lo)
    while i != -1 and i < hi:
        st = i - 21
        pid = struct.unpack('<H', d[st:st+2])[0]
        out.append((st, pid))
        i = d.find(pat, i+1)
    print(f'== {label}: {len(out)} entries')
    for st, pid in out:
        print(f'{st:06x} id={pid:5d} {d[st:st+25].hex(" ")}')

# day09: alternating stamps to end of pool
scan(d9, 0x2FD5, 0x299c00, 0x299e00, 'day09 0x2FD5 alternation')
# what follows 0x299dba (the last 0x2FD5)?
print()
print('day09 0x299dbb..0x299e1f:')
for o in range(0x299dbb, 0x299e1f, 25):
    pass
print(d9[0x299dbb:0x299dfe].hex(' '))
# is there another stamp later? maybe the alternation continues with 0x2FD5s further
