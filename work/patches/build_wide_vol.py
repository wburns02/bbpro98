#!/usr/bin/env python3
"""Build a widened SHELL.VOL from the pristine one.
usage: build_wide_vol.py PRISTINE_VOL OUT_VOL [--namew 0x60] [--colw 0x26] [--extra 4] [--labels A,B,C,D]
Edits DIAL.REQ block 13 (League Statistics): narrows Name + 8 stat columns, appends EXTRA body+header gadgets,
fixes GAD len/count, the DIAL.REQ IDX table, and VOL directory offsets."""
import os,sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); import liveguard
import sys, struct, re, argparse
ap=argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('dst')
ap.add_argument('--namew',type=lambda s:int(s,0),default=0x60); ap.add_argument('--colw',type=lambda s:int(s,0),default=0x26)
ap.add_argument('--last',type=int,default=10); ap.add_argument('--extra',type=int,default=4); ap.add_argument('--bodybase',type=lambda s:int(s,0),default=0x1e); ap.add_argument('--hdrbase',type=lambda s:int(s,0),default=0x28); ap.add_argument('--labels',default='EX1,EX2,EX3,EX4,EX5,EX6')
a=ap.parse_args()
d=bytearray(open(a.src,'rb').read())
m=re.search(rb'DIAL\.REQ\x00',bytes(d[:600])); dir_pos=m.start()-4
dial_dir=struct.unpack('<I',d[dir_pos:dir_pos+4])[0]; assert dial_dir==0xf46fa, hex(dial_dir)
base=dial_dir+9; assert d[base:base+4]==b'IDX:'
assert struct.unpack('<I',d[base+8:base+12])[0]==36
idx=list(struct.unpack('<36I',d[base+12:base+156]))
B13=0x7374; assert B13 in idx
blk0=base+B13; assert d[blk0:blk0+4]==b'REQ:'
src=d  # original VOL (read only from here)
d=bytearray(src[blk0:blk0+1218]); blk=0   # private copy of block 13; edited, then appended at the end of DIAL.REQ so no existing block moves
g=blk+58; assert d[g:g+4]==b'GAD:'
assert struct.unpack('<I',d[g+4:g+8])[0]==0x478 and struct.unpack('<H',d[g+8:g+10])[0]==29
lo,hi=blk,blk+1218
def pat(b):
    b=bytes(b); i=d.find(b,lo,hi); assert i>=0 and d.find(b,i+1,hi)<0, b.hex(); return i
x0=0x30+a.namew
i=pat(b'\x03\x08\x0a\x00\x30\x00\x6e\x00\xa8\x00'); d[i+8:i+10]=struct.pack('<H',a.namew); d[i+0x18:i+0x1a]=struct.pack('<H',a.namew)
i=pat(b'\x12\x04\x14\x00\x30\x00\x60\x00\xa8\x00'); d[i+8:i+10]=struct.pack('<H',a.namew)
for n in range(8):
    x=x0+n*a.colw
    i=pat(bytes([4,8,0x0b+n,0])+struct.pack('<H',0xd7+49*n)+b'\x6e\x00\x32\x00'); assert d[i+0x18:i+0x1a]==b'\x32\x00'
    d[i+4:i+6]=struct.pack('<H',x); d[i+8:i+10]=struct.pack('<H',a.colw); d[i+0x18:i+0x1a]=struct.pack('<H',a.colw)
    i=pat(bytes([0x13,4,0x15+n,0])+struct.pack('<H',0xd7+49*n)+b'\x60\x00\x32\x00'); d[i+4:i+6]=struct.pack('<H',x); d[i+8:i+10]=struct.pack('<H',a.colw)
E=a.extra; labels=a.labels.split(',')
NB=[a.bodybase+k for k in range(E)]; NH=[a.hdrbase+k for k in range(E)]
for nid in NB+NH: assert d.find(bytes([4,8,nid,0]),lo,hi)<0 and d.find(bytes([0x13,4,nid,0]),lo,hi)<0
xs=[x0+(8+k)*a.colw for k in range(E)]; assert xs[-1]+a.colw<=0x267+0x0d, 'overflow panel'
def body(k): return struct.pack('<BB13H',4,8,NB[k],xs[k],0x6e,a.colw,0x14a,0x40,4,(0x12 if k==0 else NB[k-1]),4,1,0xc,a.colw,0xb)
def head(k): return struct.pack('<BB10H',0x13,4,NH[k],xs[k],0x60,a.colw,0xf,0x50,4,(NH[k+1] if k+1<E else 0x13),0,1)+b'\x02\x00'+labels[k].ljust(6)[:6].encode()+b'\x00'
assert len(body(0))==28 and len(head(0))==31
# header 0x1c now links to first new header (was 0x13)
i=pat(b'\x13\x04\x1c\x00'); assert d[i+0x10:i+0x12]==b'\x13\x00'; d[i+0x10:i+0x12]=struct.pack('<H',NH[0])
# insertion points (record boundaries)
pb=pat(b'\x0d\x04\x04\x00\x08\x00\xbe\x01')      # status bar record: insert bodies before it
ph=pat(b'\x09\x04\x05\x00\x0d\x00\x60\x00\x67\x02')  # panel record: insert headers before it
assert pb<ph
nb=b''.join(body(k) for k in range(E)); nh=b''.join(head(k) for k in range(E))
d[ph:ph]=nh; d[pb:pb]=nb
add=len(nb)+len(nh)
struct.pack_into('<I',d,g+4,0x478+add); struct.pack_into('<H',d,g+8,29+2*E)
newblk=bytes(d); d=src   # back to the whole VOL
# VOL directory: shift offsets of files located after DIAL.REQ
# DIAL.REQ block starts must stay below ~0xfe9x (a block at 0xfec2 or 0x1021b failed to load: 64K-style seek limit; proven by E1/E5/wide4).
# So growth is paid for by moving the biggest block (idx10, New Association, 2470 B) to the END; every start then ends up lower than before.
names=[(mm.start(),mm.group(1)) for mm in re.finditer(rb'([A-Z0-9_]+\.[A-Z]{3})\x00',bytes(d[:0x238]))]
nxt=[struct.unpack('<I',d[pos-4:pos])[0] for pos,nm in names if nm==b'HAT.PCX']; assert len(nxt)==1
dial_end=nxt[0]; end_rel=dial_end-base
order0=sorted(range(36),key=lambda k:idx[k]); assert order0==list(range(36)) or True
size={}
for j,k in enumerate(order0): size[k]=(idx[order0[j+1]] if j+1<36 else end_rel)-idx[k]
assert size[13]==1218 and idx[order0[0]]==0x9c
bl={k:bytes(d[base+idx[k]:base+idx[k]+size[k]]) for k in range(36)}; bl[13]=newblk
MOVE=a.last; order=[k for k in order0 if k!=MOVE]+[MOVE]
pos=0x9c; nidx=list(idx)
for k in order: nidx[k]=pos; pos+=len(bl[k])
assert max(nidx)<0xfe00, hex(max(nidx))
hdr=bytes(d[base:base+12])+struct.pack('<36I',*nidx)
new_dial=bytes(d[dial_dir:base])+hdr+b''.join(bl[k] for k in order)
add=len(new_dial)-(dial_end-dial_dir); assert add==len(newblk)-1218
d[dial_dir:dial_end]=new_dial
n=0
for p,nm in names:
    o=struct.unpack('<I',d[p-4:p])[0]
    if o>dial_dir: struct.pack_into('<I',d,p-4,o+add); n+=1
o=struct.unpack('<I',d[0x234:0x238])[0]; assert o==0x1236c7, hex(o)
struct.pack_into('<I',d,0x234,o+add); n+=1
print('offsets shifted',n,'grew',add,'max block start',hex(max(nidx)),'moved last:',MOVE)
open(a.dst,'wb').write(d)
