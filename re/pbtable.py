import struct,re,sys,collections,csv
I='/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98/'
def load(n):
    d=open(I+n,'rb').read(); pe=struct.unpack_from('<I',d,0x3c)[0]
    ns=struct.unpack_from('<H',d,pe+6)[0]; ohs=struct.unpack_from('<H',d,pe+20)[0]; base=struct.unpack_from('<I',d,pe+52)[0]
    secs=[]; o=pe+24+ohs
    for i in range(ns):
        vs,va,rs,ro=struct.unpack_from('<IIII',d,o+8+i*40); secs.append((va,vs,ro,rs))
    def off(a):
        r=a-base
        for va,vs,ro,rs in secs:
            if va<=r<va+max(vs,rs): return ro+r-va
        raise KeyError(hex(a))
    def u32(a): return struct.unpack_from('<I',d,off(a))[0]
    def s(a):
        o=off(a); e=d.index(b'\0',o); return d[o:e].decode('latin1')
    return u32,s,base
def doc():
    D={}
    for l in open(I+'PBINI.TXT',errors='replace').read().replace('\r','').split('\n'):
        m=re.match(r'^\s*([A-Za-z_]\w*)\s*=\s*(-?\d+)',l)
        if m: D[m.group(1)]=int(m.group(2))
    return D
D=doc()
for B,namptr,tab in [('BBSIM',0x680bb530,0x680bc2d0)]+([(sys.argv[1],int(sys.argv[2],16),int(sys.argv[3],16))] if len(sys.argv)>3 else []):
    u32,s,base=load(B+'.dll'); N=0x368
    t=open(f'/mnt/nvme/bbpro98/index/{B}/_all.c',errors='replace').read()
    use=collections.defaultdict(set)
    for p in re.split(r'^// ==== ',t,flags=re.M)[1:]:
        a=p.split()[0]
        for m in re.finditer(r'DAT_([0-9a-f]{8})',p):
            x=int(m.group(1),16)
            if tab<=x<tab+N*4 and (x-tab)%4==0: use[(x-tab)//4].add(a)
    o=open(f'/mnt/nvme/bbpro98/re/pb_table_{B}.tsv','w'); o.write('idx\tname\tdll_default\tdoc_default\taddr\tn_funcs\tfuncs\n')
    mism=0
    for i in range(N):
        nm=s(namptr+0)  if False else s(u32(namptr+4*i)); dv=struct.unpack('<i',struct.pack('<I',u32(tab+4*i)))[0]
        dd=D.get(nm,''); mism+= (dd!='' and dd!=dv)
        o.write(f"{i}\t{nm}\t{dv}\t{dd}\t{tab+4*i:x}\t{len(use[i])}\t{','.join(sorted(use[i]))}\n")
    print(B,'params',N,'with readers',sum(1 for i in range(N) if use[i]),'doc/default mismatches',mism)
