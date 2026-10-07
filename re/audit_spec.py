#!/usr/bin/env python3
"""GLM-Flash audits each re/spec draft against its FastSim decompile slice.
usage: audit_spec.py  -> re/spec_audit/FUN_<addr>.txt (MATCH|MISMATCH verdict + specifics). Resumable."""
import os,re,glob,importlib.machinery,importlib.util,concurrent.futures as cf,time
ld=importlib.machinery.SourceFileLoader('cc','/home/will/bin/cloud-code'); sp=importlib.util.spec_from_loader('cc',ld); cc=importlib.util.module_from_spec(sp); ld.exec_module(cc)
key=cc.load_hive_key()
t=open('/mnt/nvme/bbpro98/index/FastSim/_all.c',errors='replace').read()
funcs={}
for p in re.split(r'^// ==== ',t,flags=re.M)[1:]:
    tk=p.split()
    if len(tk)>1: funcs.setdefault(tk[1],p)
    funcs.setdefault(tk[0],p)
SYS=("You audit a reverse-engineering spec draft against the real Ghidra decompile of the same function from a 1998 baseball sim. "
"Output format, nothing else:\nVERDICT: MATCH or MISMATCH or PARTIAL\n then bullet lines 'addr: issue' for every claim in the draft that the decompile contradicts or cannot support (wrong constant, wrong branch, wrong array size, invented field). "
"Quote offsets/bytes from the decompile as evidence. Do not praise. If the draft is faithful, output VERDICT: MATCH and at most 1 bullet of caveats.")
def run(path):
    out=path.replace('/spec/','/spec_audit/').replace('.md','.txt')
    if os.path.exists(out): return path,'cached'
    name=os.path.basename(path).replace('.md','')
    m=re.match(r'(FUN_[0-9a-f]+)',name)
    if not m or m.group(1) not in funcs: return path,'no-slice'
    src=funcs[m.group(1)][:22000]
    draft=open(path).read()[:9000]
    user=f"=== DRAFT {name} ===\n{draft}\n=== DECOMPILE {m.group(1)} ===\n{src}"
    for att in range(3):
        try:
            r,u=cc.call_hive(key,'z-ai/glm-5.3-flash',SYS,user,temperature=0.1,max_tokens=8000,timeout_s=420)
            if 'VERDICT' in r:
                open(out,'w').write(r); return path,'ok'
        except Exception: time.sleep(4)
    return path,'fail'
os.makedirs('/mnt/nvme/bbpro98/re/spec_audit',exist_ok=True)
files=sorted(glob.glob('/mnt/nvme/bbpro98/re/spec/FUN_*.md'))
print('files',len(files),flush=True)
with cf.ThreadPoolExecutor(3) as ex:
    for p,st in ex.map(run,files):
        print(st,os.path.basename(p),flush=True)
