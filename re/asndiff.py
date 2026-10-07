#!/usr/bin/env python3
"""Classify ASN byte diffs across the three PB arms.
D_null = offsets where armA != armA2 (seed noise). D_tr = armB != armA (treatment).
Clusters = maximal runs of D_tr with gaps < 64. Writes re/asn_clusters.tsv."""
import struct

def rd(p): return open(p, 'rb').read()
A = rd('/mnt/nvme/bbpro98/re/pbexp/armA/Assn/MLBPA97.ASN')
A2 = rd('/mnt/nvme/bbpro98/re/pbexp/armA2/Assn/MLBPA97.ASN')
B = rd('/mnt/nvme/bbpro98/re/pbexp/armB/Assn/MLBPA97.ASN')
n = min(len(A), len(A2), len(B))
dn = {i for i in range(n) if A[i] != A2[i]}
dt = {i for i in range(n) if B[i] != A[i]}
print(f'null bytes {len(dn)}, treatment bytes {len(dt)}, overlap {len(dn & dt)}')

# cluster on treatment offsets
cl = []
for i in sorted(dt):
    if cl and i - cl[-1][1] < 64: cl[-1][1] = i
    else: cl.append([i, i])
rows = []
for s, e in cl:
    in_null = sum(1 for i in range(s, e + 1) if i in dn)
    va, va2, vb = A[s:e+1], A2[s:e+1], B[s:e+1]
    rows.append((s, e - s + 1, in_null,
                 va[:8].hex(), va2[:8].hex(), vb[:8].hex()))
with open('/mnt/nvme/bbpro98/re/asn_clusters.tsv', 'w') as f:
    f.write('start\tlen\tnull_overlap\thexA\thexA2\thexB\n')
    for r in rows:
        f.write('\t'.join(str(x) for x in r) + '\n')
print(f'{len(rows)} treatment clusters; '
      f'{sum(1 for r in rows if r[2])} overlap null, '
      f'{sum(1 for r in rows if not r[2])} treatment-only')
for r in rows[:15]:
    print(r[0], 'len', r[1], 'null_ov', r[2], 'A', r[3], 'B', r[5])
