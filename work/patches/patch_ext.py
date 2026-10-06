#!/usr/bin/env python3
"""Extension-columns code patch for BBShell.dll (League Statistics screen). usage: patch_ext.py DLL [--ids b0,b1,b2,b3:p0,p1,p2,p3]
Requires the widened SHELL.VOL (build_wide_vol.py --hdrbase 0x1d). Asserts original bytes; refuses if already patched."""
import os,sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); import liveguard
import sys, struct
f=sys.argv[1]
bat=[49,50,57,52]; pit=[262,251,276,277]
if len(sys.argv)>3 and sys.argv[2]=='--ids':
    b,p=sys.argv[3].split(':'); bat=[int(x) for x in b.split(',')]; pit=[int(x) for x in p.split(',')]
d=bytearray(open(f,'rb').read())
BASE=0x68000c00
def fo(va): return va-BASE
def chk(va,old,new):
    o=fo(va); assert bytes(d[o:o+len(old)])==bytes(old),(hex(va),d[o:o+len(old)].hex()); assert len(old)==len(new); d[o:o+len(new)]=new
def call(at,tgt): return b'\xe8'+struct.pack('<i',tgt-(at+5))
CAVE=0x68080480; TAB=0x68080540
o=fo(CAVE); assert set(d[o:o+0x180])<= {0xcc,0}, 'cave not free'
# cave1: slot id lookup for c930
c1=bytes([0x0f,0xbf,0xcd,                 # movsx ecx,bp
 0x83,0xf9,0x0a,                          # cmp ecx,10
 0x7d,0x05,                               # jge ext
 0x8b,0x54,0x8e,0x6c,                     # mov edx,[esi+ecx*4+0x6c]
 0xc3,                                    # ret
 0x8b,0x96,0xe8,0,0,0,                    # ext: mov edx,[esi+0xe8]
 0x8d,0x14,0x92,                          # lea edx,[edx+edx*4]
 0x8d,0x54,0x0a,0xf6,                     # lea edx,[edx+ecx-10]
 0x8b,0x14,0x95])+struct.pack('<I',TAB)+bytes([0xc3])   # mov edx,[TAB+edx*4]; ret
# cave2: header id lookup for cb20 loop. block = param_5 at [esp+0x28] inside the function (+4 for our call)
tail=bytes([0x8b,0x44,0x24,0x2c,          # mov eax,[esp+0x2c]   (block)
 0x8d,0x04,0x80,                          # lea eax,[eax+eax*4]
 0x01,0xd0,                               # add eax,edx
 0x8b,0x04,0x85])+struct.pack('<I',TAB)   # mov eax,[TAB+eax*4]
c2=bytes([0x8b,0x45,0x00,                 # mov eax,[ebp]
 0x83,0xc5,0x04,                          # add ebp,4
 0x8d,0x56,0xe3,                          # lea edx,[esi-0x1d]
 0x83,0xfa,0x03,                          # cmp edx,3
 0x77,len(tail)])+tail+b'\xc3'            # ja done ; ... ; done: ret
C1=CAVE; C2=CAVE+0x40
assert len(c1)<0x40 and len(c2)<0x40
d[fo(C1):fo(C1)+len(c1)]=c1; d[fo(C2):fo(C2)+len(c2)]=c2
# cave3: cell index for the Statistics cell callback FUN_6800ec00: cx = id-9, or id-0x26 for ext ids >= 0x30 (cells 10..13)
C3=CAVE+0x120
c3=bytes([0x66,0x8b,0xcb, 0x66,0x83,0xfb,0x30, 0x72,0x05, 0x66,0x83,0xe9,0x26, 0xc3, 0x66,0x83,0xe9,0x09, 0xc3])
d[fo(C3):fo(C3)+len(c3)]=c3
# cave4: init (enable, set id) the 4 ext body gadgets 0x30..0x33 like the 9..0x12 loop in FUN_6800d300
C4=CAVE+0x140
c4=bytearray([0xbf,0x30,0,0,0])
L=len(c4)
import os
if os.environ.get('C4A','1')=='1': c4+=bytes([0x68,0x40,0xea,0x00,0x68,0x57,0xb9,0x10,0xdd,0x08,0x68]); c4+=call(C4+len(c4),0x680436c0)
if os.environ.get('C4B','1')=='1': c4+=bytes([0x6a,0x00,0x57,0xb9,0x10,0xdd,0x08,0x68]); c4+=call(C4+len(c4),0x68043400)
c4+=bytes([0x47,0x83,0xff,int(os.environ.get('C4N','0x34'),0)]); c4+=bytes([0x7c,(L-(len(c4)+2))&0xff])
c4+=bytes([0x6a,0x00,0x8b,0x46,0x34]); c4+=b'\xe9'+struct.pack('<i',0x6800d3af-(C4+len(c4)+5))
assert len(c4)<0x40
d[fo(C4):fo(C4)+len(c4)]=c4
tab=bat+[0]+pit+[0]
d[fo(TAB):fo(TAB)+40]=struct.pack('<10I',*tab)
# hook FUN_6800d300 after the 9..0x12 init loop: jmp cave4
chk(0x6800d3aa,bytes([0x6a,0x00,0x8b,0x46,0x34]),b'\xe9'+struct.pack('<i',C4-(0x6800d3aa+5)))
# hook c930 slot read: 6805cae2: 0f bf cd 8b 54 8e 6c
chk(0x6805cae2,bytes([0x0f,0xbf,0xcd,0x50,0x8b,0x54,0x8e,0x6c]),call(0x6805cae2,C1)+b'\x50\x90\x90')
chk(0x6805cafb,bytes([0x66,0x83,0xfd,0x0a]),bytes([0x66,0x83,0xfd,0x0e]))   # loop to 14 cells
chk(0x6805cb0b,bytes([0x6a,0x0a]),bytes([0x6a,0x0e]))                        # terminator at cell 14
# hook header loop in cb20: 6805cbe7: 8b 45 00 8b cd 83 c5 04
chk(0x6805cbe7,bytes([0x8b,0x45,0x00,0x8b,0xcd,0x83,0xc5,0x04]),call(0x6805cbe7,C2)+b'\x90\x90\x90')
chk(0x6800ec2c,bytes([0x66,0x8b,0xcb,0x66,0x83,0xe9,0x09]),call(0x6800ec2c,C3)+b'\x90\x90')
# Statistics screen header range 0x13..0x1c -> 0x13..0x20
chk(0x6800d442,bytes([0x6a,0x1c,0x6a,0x13]),bytes([0x6a,0x20,0x6a,0x13]))
pe=struct.unpack('<I',d[0x3c:0x40])[0]; oh=struct.unpack('<H',d[pe+20:pe+22])[0]
so=pe+24+oh   # first section header = .text
assert d[so:so+5]==b'.text'
vs=struct.unpack('<I',d[so+8:so+12])[0]; assert vs in (0x7f46a,0x7f600); d[so+8:so+12]=struct.pack('<I',0x7f600)
open(f,'wb').write(d); print('patched',f,bat,pit)
