#!/usr/bin/env python3
"""Same-size geometry edit of the Statistics screen columns in SHELL.VOL (DIAL.REQ block 13).
usage: narrow_cols.py SHELL.VOL [namew] [colw]   (asserts; refuses if already patched)"""
import os,sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); import liveguard
import sys, struct
f=sys.argv[1]; namew=int(sys.argv[2],0) if len(sys.argv)>2 else 0x60; colw=int(sys.argv[3],0) if len(sys.argv)>3 else 0x2a
d=bytearray(open(f,'rb').read())
lo=0xf4703+0x7374; hi=lo+1218
def pat(b): 
    i=d.find(bytes(b),lo,hi); assert i>=0 and d.find(bytes(b),i+1,hi)<0, b.hex(); return i
x0=0x30+namew
# name body + header
i=pat(b'\x03\x08\x0a\x00\x30\x00\x6e\x00\xa8\x00'); d[i+8:i+10]=struct.pack('<H',namew)
i=pat(b'\x12\x04\x14\x00\x30\x00\x60\x00\xa8\x00'); d[i+8:i+10]=struct.pack('<H',namew)
for n in range(8):
    x=x0+n*colw
    i=pat(bytes([4,8,0x0b+n,0])+struct.pack('<H',0xd7+49*n)+b'\x6e\x00\x32\x00'); d[i+4:i+6]=struct.pack('<H',x); d[i+8:i+10]=struct.pack('<H',colw)
    i=pat(bytes([0x13,4,0x15+n,0])+struct.pack('<H',0xd7+49*n)+b'\x60\x00\x32\x00'); d[i+4:i+6]=struct.pack('<H',x); d[i+8:i+10]=struct.pack('<H',colw)
open(f,'wb').write(d); print('ok')
