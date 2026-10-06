import re,sys,collections
b=sys.argv[1]
t=open(f'/mnt/nvme/bbpro98/index/{b}/_all.c',errors='replace').read()
parts=re.split(r'^// ==== ',t,flags=re.M)[1:]
fm=collections.defaultdict(list)
for p in parts:
    addr=p.split()[0]
    for m in re.finditer(r's___?([A-Za-z0-9_]+?)_(cpp|c|h)_[0-9a-f]{8}',p):
        fm[m.group(1)+'.'+m.group(2)].append(addr)
for f,a in sorted(fm.items(),key=lambda x:-len(set(x[1]))):
    print(f,len(set(a)),min(a),max(a))
