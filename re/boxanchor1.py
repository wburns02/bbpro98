#!/usr/bin/env python3
"""Anchor the ASN tail log against the April 11 box score (ATL at FLA, 0-4).
Known box facts: ATL totals AB30 R0 H4 RBI0 BB3 SO7; FLA AB29 R4 H8 RBI3 BB6 SO4;
FLA innings: 3rd=3, 4th=1; FLA CF Lindsey 3-1-1-0-1-0; C Johnson 3-0-2-1-1-0 (2B);
ATL SS Price 3-0-1-0-0-0 (2B); FLA 1B 4-0-1-1-0-2."""
d9 = open('/mnt/nvme/bbpro98/re/asnseq/day09/Assn/MLBPA97.ASN', 'rb').read()
d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN', 'rb').read()
assert len(d9) == len(d10), (len(d9), len(d10))
n = len(d9)
TAIL0 = n - 0x8000
def findall(buf, pat, lo=0, hi=None):
    hi = hi or len(buf)
    out, i = [], lo
    while True:
        j = buf.find(pat, i, hi)
        if j < 0: break
        out.append(j); i = j + 1
    return out
pats = {
 'ATL_totals[30,0,4,0,3,7]': bytes([30, 0, 4, 0, 3, 7]),
 'FLA_totals[29,4,8,3,6,4]': bytes([29, 4, 8, 3, 6, 4]),
 'inning_FLA[0,0,3,1,0,0,0,0]': bytes([0, 0, 3, 1, 0, 0, 0, 0]),
 'Lindsey[3,1,1,0,1,0]': bytes([3, 1, 1, 0, 1, 0]),
 'johnson[3,0,2,1,1,0]': bytes([3, 0, 2, 1, 1, 0]),
 'runs02u16': bytes([4, 0, 0, 0]),
}
print('tail region', hex(TAIL0), '-', hex(n))
for k, p in pats.items():
    hits_t = findall(d10, p, TAIL0)
    hits_all = findall(d10, p)
    print(f'{k}: tail hits {[hex(h) for h in hits_t]} (whole-file {len(hits_all)})')
# diff extent in tail
diffs = [i for i in range(TAIL0, n) if d9[i] != d10[i]]
if diffs:
    print('tail diff range:', hex(diffs[0]), '-', hex(diffs[-1]), 'ndiff', len(diffs))
# day record boundaries: sector starts ending 0x1a that changed
starts = [i for i in range(TAIL0, n, 1) if (i & 0xff) == 0x1a and d9[i:i+1] != d10[i:i+1]]
print('0x1a-start changes:', [hex(s) for s in starts[:20]])
