import re,collections,csv
P='/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98/PBINI.TXT'
keys=[]; cur=None; desc=collections.defaultdict(list); 
for l in open(P,errors='replace').read().replace('\r','').split('\n'):
    m=re.match(r'^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(-?\d+)\s*(;.*)?$',l)
    if m: keys.append((m.group(1),int(m.group(2)))); cur=m.group(1)
    elif l.startswith(';') and cur: desc[cur].append(l.lstrip('; ').strip())
print('keys',len(keys),'unique',len({k for k,_ in keys}))
out=open('/mnt/nvme/bbpro98/re/pb_params.tsv','w'); out.write('key\tdefault\tbin\tfunc_addrs\tn_funcs\n')
for B in ['BBSIM','FastSim']:
    t=open(f'/mnt/nvme/bbpro98/index/{B}/_all.c',errors='replace').read()
    fn={}
    for p in re.split(r'^// ==== ',t,flags=re.M)[1:]:
        a=p.split()[0]
        for m in re.finditer(r's_([A-Za-z0-9_]+?)_[0-9a-f]{8}\b',p): fn.setdefault(m.group(1).lower(),set()).add(a)
    hit=0
    for k,v in keys:
        f=fn.get(k.lower(),set())
        if f: hit+=1
        out.write(f"{k}\t{v}\t{B}\t{','.join(sorted(f))}\t{len(f)}\n")
    print(B,'keys with a reading function:',hit,'of',len(keys))
