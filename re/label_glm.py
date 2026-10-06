#!/usr/bin/env python3
"""GLM-Flash residue labeling. usage: label_glm.py BINARY [workers]  -> index/BINARY/_labels_glm.tsv (resumable, per-batch cache)."""
import sys,re,csv,json,os,importlib.machinery,importlib.util,concurrent.futures as cf,time
B=sys.argv[1]; W=int(sys.argv[2]) if len(sys.argv)>2 else 4
ld=importlib.machinery.SourceFileLoader('cc','/home/will/bin/cloud-code'); sp=importlib.util.spec_from_loader('cc',ld); cc=importlib.util.module_from_spec(sp); ld.exec_module(cc)
key=cc.load_hive_key()
D=f'/mnt/nvme/bbpro98/index/{B}/'; C=f'/mnt/nvme/bbpro98/re/glm/{B}/'; os.makedirs(C,exist_ok=True)
t=open(D+'_all.c',errors='replace').read(); funcs={p.split()[0]:p for p in re.split(r'^// ==== ',t,flags=re.M)[1:]}
det={r[0]:r for r in list(csv.reader(open(D+'_labels_det.tsv'),delimiter='\t'))[1:]}
todo=[a for a,r in det.items() if not r[3]]
SUB="CRT MATH IO_FILE IO_REGISTRY STRUCT_INIT SIM_PITCH SIM_SWING SIM_FIELD SIM_BASE SIM_INJURY SIM_FATIGUE SIM_LINEUP SIM_GAME SIM_STATS SIM_UMPIRE SIM_AI RATING SEASON UI_MAIN UI_STATS UI_LINEUP UI_DIALOG UI_RENDER GDI WIN32 MFC_LIB AUDIO ANIM CAMERA UNKNOWN".split()
SYS=("You label functions decompiled by Ghidra from a 1998 Win32 baseball sim (Sierra FPS Baseball Pro 98). Output ONLY TSV rows, one per input function, no prose: "
"addr<TAB>subsystem<TAB>evidence<TAB>short_name<TAB>comment. subsystem is one of: "+" ".join(SUB)+". evidence is one of STRING_XREF (a string literal or named callee supports it), XREF_CONFIDENT (callees/callers clearly imply it), PATTERN_GUESS (shape only), UNKNOWN. "
"short_name is lower_snake_case or empty if you cannot name it honestly. comment max 12 words, factual, mention the string/callee that supports it. Never invent. If unsure use UNKNOWN. Hint lines give the source-file module of known callers and callees.")
def hint(a):
    r=det[a]; return ''
def fmt(a,rowinfo):
    p=funcs[a].split('\n'); body='\n'.join(p[:70])
    return body[:3500]
rows={r[0]:r for r in list(csv.reader(open(D+'_functions.tsv'),delimiter='\t'))[1:]}
def hints(a):
    r=rows[a]; cs=sorted({det[c][2] for c in r[3].split(',') if c in det and det[c][2]})
    ce=sorted({det[c][2] for c in r[4].split(',') if c in det and det[c][2]})
    return f"// hint callers_modules={cs[:6]} callees_modules={ce[:6]}"
N=40; batches=[todo[i:i+N] for i in range(0,len(todo),N)]
def run(i):
    f=C+f'b{i:04d}.tsv'
    if os.path.exists(f): return i,0
    user='\n\n'.join(hints(a)+'\n// ==== '+fmt(a,0) for a in batches[i])
    for att in range(3):
        try:
            out,u=cc.call_hive(key,'z-ai/glm-5.3-flash',SYS,user,temperature=0.1,max_tokens=24000,timeout_s=600)
            ok=[l for l in out.splitlines() if l.count('\t')>=4]
            if len(ok)>=len(batches[i])*0.8:
                open(f,'w').write('\n'.join(ok)+'\n'); return i,u.get('completion_tokens',0)
        except Exception as e: time.sleep(5)
    return i,-1
print(B,'batches',len(batches),flush=True)
run(0)  # warm the cache, then fan out
with cf.ThreadPoolExecutor(W) as ex:
    bad=0
    for i,n in ex.map(run,range(len(batches))):
        if n<0: bad+=1; print('FAILED batch',i,flush=True)
print(B,'done failed',bad,flush=True)
with open(D+'_labels_glm.tsv','w') as o:
    o.write('addr\tsubsystem\tevidence\tshort_name\tcomment\n')
    for i in range(len(batches)):
        f=C+f'b{i:04d}.tsv'
        if os.path.exists(f): o.write(open(f).read())
