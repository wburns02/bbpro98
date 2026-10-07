#!/usr/bin/env python3
"""Tier 3 drafts: per FastSim PB-consuming function, annotate getter calls with param names/defaults, ask GLM-Flash for a rule description. -> re/spec/FUN_<addr>.md (resumable)."""
import re,csv,os,sys,importlib.machinery,importlib.util,concurrent.futures as cf,time,collections
ld=importlib.machinery.SourceFileLoader('cc','/home/will/bin/cloud-code'); sp=importlib.util.spec_from_loader('cc',ld); cc=importlib.util.module_from_spec(sp); ld.exec_module(cc)
key=cc.load_hive_key()
D='/mnt/nvme/bbpro98/index/FastSim/'; O='/mnt/nvme/bbpro98/re/spec/'
pb={}; byfn=collections.defaultdict(list)
for r in csv.reader(open('/home/will/bbpro98/work/pb_table_FastSim.tsv'),delimiter='\t'):
    if r[0]=='idx': continue
    pb[int(r[0])]=(r[1],r[2])
    for f in r[6].split(','):
        if f: byfn[f].append(int(r[0]))
t=open(D+'_all.c',errors='replace').read()
funcs={p.split()[0]:p for p in re.split(r'^// ==== ',t,flags=re.M)[1:]}
lab={}
try:
    for r in csv.reader(open(D+'_labels_det.tsv'),delimiter='\t'): lab[r[0]]=r[2]
except Exception: pass
def annotate(body):
    return re.sub(r'FUN_68003170\((0x[0-9a-fA-F]+|\d+)\)',lambda m:'PB[%s]'%(pb.get(int(m.group(1),0),('?',''))[0]),body)
SYS=("You document the decision logic of one function from a 1998 baseball simulation (Sierra FPS Baseball Pro 98), decompiled by Ghidra. PB[name] is a tunable balance parameter read from a table; its default is listed. "
"Write a spec: 1) PURPOSE (one sentence), 2) INPUTS (struct fields or args that matter, as you can infer, mark guesses), 3) RULES (numbered, plain language, with the exact formulas and thresholds, naming each PB parameter used), 4) OUTPUT/SIDE EFFECTS, 5) UNCERTAIN (what you could not determine). "
"Never invent behavior not in the code. Be terse. No preamble.")
def run(a):
    f=O+f'FUN_{a}.md'
    if os.path.exists(f): return 0
    body=annotate(funcs[a])[:16000]
    ps=sorted(byfn[a]); pl='\n'.join(f'{pb[i][0]} default={pb[i][1]}' for i in ps[:150])
    user=f"Function {a}, source module {lab.get(a,'?')}.\nParameters it reads:\n{pl}\n\nDecompile:\n{body}"
    for _ in range(2):
        try:
            out,u=cc.call_hive(key,'z-ai/glm-5.3-flash',SYS,user,temperature=0.1,max_tokens=24000,timeout_s=900)
            if len(out)>200: open(f,'w').write(f'# FUN_{a} ({lab.get(a,"?")}) params={len(ps)}\n\nDRAFT (GLM-Flash, unaudited)\n\n'+out+'\n'); return 1
        except Exception as e: time.sleep(5)
    return -1
order=sorted(byfn,key=lambda a:-len(byfn[a]))
print(len(order),'functions',flush=True)
with cf.ThreadPoolExecutor(4) as ex:
    r=list(ex.map(run,order))
print('done',sum(1 for x in r if x>0),'failed',sum(1 for x in r if x<0),flush=True)
