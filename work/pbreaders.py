import re,csv,collections,sys
B,tab=sys.argv[1],sys.argv[2]
t=open(f'/mnt/nvme/bbpro98/index/{B}/_all.c',errors='replace').read()
parts=re.split(r'^// ==== ',t,flags=re.M)[1:]
g=[p.split()[0] for p in parts if f'(&DAT_{tab} + param_1 * 4)' in p and 'return' in p]; print(B,'getter',g)
G=g[0]; gm=collections.defaultdict(set); callers=set()
for p in parts:
    a=p.split()[0]
    for m in re.finditer(r'FUN_'+G+r'\(\s*(0x[0-9a-f]+|\d+)\s*\)',p): callers.add(a); gm[int(m.group(1),0)].add(a)
rows=list(csv.reader(open(f'pb_table_{B}.tsv'),delimiter='\t'))
o=open(f'pb_table_{B}.tsv','w'); w=csv.writer(o,delimiter='\t',lineterminator='\n'); w.writerow(rows[0])
for r in rows[1:]:
    f=sorted(gm.get(int(r[0]),[])); r[5]=str(len(f)); r[6]=','.join(f); w.writerow(r)
print('callers',len(callers),'params mapped',len(gm))
