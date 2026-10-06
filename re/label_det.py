#!/usr/bin/env python3
"""Deterministic labeling pass. usage: label_det.py BINARY  -> index/BINARY/_labels_det.tsv
Evidence: SRC_ASSERT (function itself references a source filename string), PROPAGATED (all callers share one module),
API (calls Win32/MFC API), MFC (Ghidra FID/name), TINY. Everything else left unlabeled for the GLM pass."""
import re,sys,csv,collections,json
B=sys.argv[1]; D=f'/mnt/nvme/bbpro98/index/{B}/'
t=open(D+'_all.c',errors='replace').read()
funcs={}
for p in re.split(r'^// ==== ',t,flags=re.M)[1:]:
    a=p.split()[0]; funcs[a]=p
rows={}
for r in list(csv.reader(open(D+'_functions.tsv'),delimiter='\t'))[1:]:
    rows[r[0]]=dict(name=r[1],size=int(r[2]),callers=[x for x in r[3].split(',') if x],callees=[x for x in r[4].split(',') if x])
lab={}
def mod_of(fn):
    return re.sub(r'^(BBSim|FastSim|Graphics|TSpace|Utility|Fps_ct)_','',fn).rsplit('.',1)[0].lower().lstrip('f') if False else fn
srcre=re.compile(r's___?([A-Za-z0-9_]+?)_(cpp|c)_[0-9a-f]{8}')
for a,p in funcs.items():
    m=srcre.findall(p)
    if m:
        mods=collections.Counter(x[0] for x in m)
        lab[a]=(mods.most_common(1)[0][0],'SRC_ASSERT')
# propagate callers->callee
for it in range(6):
    ch=0
    for a,r in rows.items():
        if a in lab or not r['callers']: continue
        ms={lab[c][0] for c in r['callers'] if c in lab}
        if len(ms)==1 and all(c in lab for c in r['callers']):
            lab[a]=(next(iter(ms)),'PROPAGATED'); ch+=1
    if not ch: break
apis=re.compile(r'\b(CreateFile[AW]|ReadFile|WriteFile|SetFilePointer|fopen|fread|fwrite|RegOpenKey\w*|RegQueryValue\w*|GetPrivateProfile\w*|CreateWindow\w*|SendMessage\w*|SendDlgItem\w*|DialogBox\w*|BitBlt|StretchBlt|SelectObject|TextOut\w*|DrawText\w*|Direct\w+|waveOut\w*|mci\w*|timeGetTime|rand|srand|malloc|free)\(')
out=open(D+'_labels_det.tsv','w'); out.write('addr\tname\tmodule\tevidence\tapis\n')
cnt=collections.Counter()
for a,r in rows.items():
    p=funcs.get(a,'')
    ap=sorted(set(apis.findall(p)))
    m,e=lab.get(a,('','' ))
    if not e and r['name'].startswith('FID_conflict') or (not e and not r['name'].startswith('FUN_')): m,e=('MFC_LIB','FID_NAME')
    if not e and r['size']<12: m,e=('TINY','SIZE')
    cnt[e or 'NONE']+=1
    out.write(f"{a}\t{r['name']}\t{m}\t{e}\t{','.join(ap)}\n")
print(B,dict(cnt),'total',len(rows))
