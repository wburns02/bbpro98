"""Dump the ASN news-pool 25-byte records per the RE_FINDINGS layout, all snapshot days, with player names."""
import sys, os
sys.path.insert(0, '/home/will/bbpro98/work'); import bbstats
SNAP = '/mnt/nvme/bbpro98/re/asnseq'
nm = bbstats.names(f'{SNAP}/day10/Assn/MLBPA97.PYR')
for day in sorted(d for d in os.listdir(SNAP) if d.startswith('day') and os.path.isdir(f'{SNAP}/{d}')):
    b = open(f'{SNAP}/{day}/Assn/MLBPA97.ASN', 'rb').read()
    print(f'## {day}')
    for blk in range(0x27E000, min(0x29A800, len(b)), 0x200):
        h = b[blk:blk + 29]
        if not any(h): continue
        ptr = int.from_bytes(h[2:4], 'little')
        for k in range(19):
            o = blk + 0x15 + 25 * k; r = b[o:o + 25]
            if len(r) < 25 or not any(r): continue
            pid = int.from_bytes(r[0:2], 'little'); rel = int.from_bytes(r[7:9], 'little')
            if pid not in nm and k: continue
            print(f'{day} blk={blk:#x} ptr={ptr:#06x} k={k:2d} pid={pid:5d} {nm.get(pid,"?")[:20]:20s} flag={r[6]:02x} rel={rel:5d} {nm.get(rel,"?")[:16]:16s} ev={r[13]:02x} p24={int.from_bytes(r[14:17],"little"):#08x} date={r[21]}/{r[22]} c23={r[23]:02x} c24={r[24]:02x} raw={r.hex()}')
