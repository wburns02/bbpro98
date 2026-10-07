import re,sys
sys.argv=['x']; src=open('/mnt/nvme/bbpro98/re/spec_draft.py').read().split("order=sorted")[0]
exec(src)
# map init-loaded globals -> PB names from every function with 'DAT_x = FUN_68003170(n)' pairs
g={}
for a,b in funcs.items():
    for m in re.finditer(r'_?DAT_([0-9a-f]{8}) = FUN_68003170\((0x[0-9a-f]+|\d+)\);',b):
        g[m.group(1)]=pb.get(int(m.group(2),0),('?',''))[0]
print(len(g),'globals mapped',flush=True)
def ann2(body):
    body=annotate(body)
    return re.sub(r'_?DAT_([0-9a-f]{8})',lambda m:('PBG[%s]'%g[m.group(1)]) if m.group(1) in g else m.group(0),body)
TARGETS=['68054d4a']
SYS2=SYS.replace("PB[name] is a tunable balance parameter read from a table; its default is listed.","PB[name] is a tunable balance parameter read from a table. PBG[name] is a global that was loaded from that parameter at startup, so it holds the tunable's value.")
def one(a):
    body=ann2(funcs[a]).split('\n')
    chunks=[ '\n'.join(body[i:i+110]) for i in range(0,len(body),110)]
    outs=[]
    for k,c in enumerate(chunks):
        user=f"Function {a} part {k+1}/{len(chunks)} (variables carry over). Decompile:\n{c[:14000]}"
        r='FAILED'
        for _ in range(3):
            try:
                out,u=cc.call_hive(key,'z-ai/glm-5.3-flash',SYS2,user,temperature=0.1,max_tokens=24000,timeout_s=900)
                if len(out)>200: r=out; break
            except Exception as e: time.sleep(5)
        outs.append(r)
    open(O+f'FUN_{a}_consumer.md','w').write(f'# FUN_{a} consumer of init-loaded PB globals\n\nDRAFT (GLM-Flash, unaudited)\n\n'+'\n\n=====\n\n'.join(outs)+'\n'); return a,[len(x) for x in outs]
with cf.ThreadPoolExecutor(3) as ex:
    for r in ex.map(one,TARGETS): print(r,flush=True)
