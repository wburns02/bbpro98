#!/usr/bin/env python3
"""The 0x2fd7 clusters are the news log entries for April 12 (day11 sim)! The 0x2fd6 stamp = April 11 news.
No wait: (era<<8)|day = 0x2fd6 = 12246: era 47 day 214. 0x2fd7 = day 215 = Apr 12.
Verify against day10 changes: 0x2fd7 entries at 0x29a4xx changed on day10 (they did)."""
import struct

d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN','rb').read()
d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()
# Are the 0x2fd7 entries present in day9?
for st in (0x29a42e, 0x29a447, 0x29a615):
    same = d9[st:st+25] == d10[st:st+25]
    print(f'{st:06x} day9==day10: {same}; day9={d9[st:st+25].hex(" ")}')
