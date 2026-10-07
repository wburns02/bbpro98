#!/usr/bin/env python3
"""Pass-2 audit: same as audit_spec.py but teaches the PB-getter identity and
injects the pb_table rows cited by each draft, so 'invented name/default'
false positives vanish. Writes re/spec_audit/FUN_<addr>.txt. Resumable."""
import os,re,glob,csv,importlib.machinery,importlib.util,concurrent.futures as cf,time
ld=importlib.machinery.SourceFileLoader('cc','/home/will/bin/cloud-code'); sp=importlib.util.spec_from_loader('cc',ld); cc=importlib.util.module_from_spec(sp); ld.exec_module(cc)
key=cc.load_hive_key()
t=open('/mnt/nvme/bbpro98/index/FastSim/_all.c',errors='replace').read()
funcs={}
for p in re.split(r'^// ==== ',t,flags=re.M)[1:]:
    tk=p.split()
    if len(tk)>1: funcs.setdefault(tk[1],p)
    funcs.setdefault(tk[0],p)
TAB={}
with open('/mnt/nvme/bbpro98/re/pb_table_FastSim.tsv') as f:
    for row in csv.DictReader(f,delimiter='\t'):
        TAB[int(row['idx'])]=row
GETTER=("VERIFIED CONTEXT (do not re-derive, do not flag): FUN_68003170(idx) is the "
"PlayBalance getter: it returns *(unsigned int*)(&DAT_6808fde0 + idx*4). "
"PLAYBALANCE TABLE ROWS for this function (idx -> name, default):")
SYS=("You audit a reverse-engineering spec draft against the real Ghidra decompile of the same function from a 1998 baseball sim. "+GETTER+" {ROWS}. "
"A draft claim that cites one of these PlayBalance names/defaults is SUPPORTED when the decompile calls FUN_68003170 with the matching index; the decompile will NEVER show PB names or default numbers inline, so absence of the literal name/number in the decompile is NOT an error. "
"Flag only: wrong signature or parameter count, wrong branch or loop structure, wrong non-PB constant, wrong call arguments, wrong addresses, getter indices inconsistent with the table rows, or a rule the decompile flatly contradicts. "
"Output format, nothing else:\nVERDICT: MATCH or MISMATCH or PARTIAL\n then bullet lines 'addr: issue' for every contradicted or unsupported claim, quoting offsets/bytes from the decompile as evidence. Do not praise. If faithful, output VERDICT: MATCH and at most 1 bullet of caveats.")
def table_rows(draft):
    idxs={int(h,16) for h in re.findall(r'0x([0-9a-fA-F]+)',draft) if int(h,16) in TAB}
    idxs|={int(r['idx']) for r in TAB.values() if r['name'] in draft}
    if not idxs: return '(none cited)'
    return '; '.join(f"{i} -> {TAB[i]['name']}, default {TAB[i]['dll_default']}" for i in sorted(idxs))
def run(path):
    out=path.replace('/spec/','/spec_audit/').replace('.md','.txt')
    if os.path.exists(out): return path,'cached'
    name=os.path.basename(path).replace('.md','')
    m=re.match(r'(FUN_[0-9a-f]+)',name)
    if not m or m.group(1) not in funcs: return path,'no-slice'
    src=funcs[m.group(1)][:22000]
    draft=open(path).read()[:9000]
    sys=SYS.replace('{ROWS}',table_rows(draft))
    user=f"=== DRAFT {name} ===\n{draft}\n=== DECOMPILE {m.group(1)} ===\n{src}"
    for att in range(3):
        try:
            r,u=cc.call_hive(key,'z-ai/glm-5.3-flash',sys,user,temperature=0.1,max_tokens=16000,timeout_s=600)
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
