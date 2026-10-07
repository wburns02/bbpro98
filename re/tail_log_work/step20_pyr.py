#!/usr/bin/env python3
"""Identify the SMA event: 0x1973 has events on Apr 7 (0x27e2xx) and Apr 10/11 (0x299c..299e)."""
import struct

d10 = open('/mnt/nvme/bbpro98/re/asnseq/day10/Assn/MLBPA97.ASN','rb').read()

# PYR dump
import subprocess
def dump_pyr(path, rec):
    return subprocess.run(['python3', '/home/will/bbpro98/BBPRO98_package/research/dump_pyr.py', path, '--rec', str(rec)],
                          capture_output=True, text=True).stdout

PYR = '/mnt/nvme/bbpro98/work_install/Assn/MLBPA97.PYR'
for pid in (1973, 2276, 881, 534, 833, 371, 1660):
    print(f'--- pid {pid}:', dump_pyr(PYR, pid-100).strip()[:300])
