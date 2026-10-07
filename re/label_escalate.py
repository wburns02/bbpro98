#!/usr/bin/env python3
"""Escalation for label_glm FAILED batches. usage: label_escalate.py BINARY STAGE  (STAGE: glm10 | deepseek10 | merge)
Covers by address, not batch index. Writes glm/B/esc_<stage>_NNNN.tsv. 'merge' rebuilds _labels_glm.tsv from every file and lists leftovers."""
import sys,re,csv,os,glob,importlib.machinery,importlib.util,concurrent.futures as cf,time
B,STAGE=sys.argv[1],sys.argv[2]
src=open('/mnt/nvme/bbpro98/re/label_glm.py').read()
D=f'/mnt/nvme/bbpro98/index/{B}/'; C=f'/mnt/nvme/bbpro98/re/glm/{B}/'
ns={}
# reuse SYS/SUB/hints/fmt definitions without running the batch loop
head=src.split("N=40;")[0].replace("B=sys.argv[1]; W=int(sys.argv[2]) if len(sys.argv)>2 else 4","B=%r;W=4"%B)
sys.argv=[sys.argv[0],B]; exec(head,ns)
todo=ns['todo']
def covered():
    s=set()
    for f in glob.glob(C+'*.tsv'):
        for l in open(f):
            p=l.split('\t')
            if len(p)>=5: s.add(p[0].strip())
    return s
if STAGE=='merge':
    s=covered(); left=[a for a in todo if a not in s]
    with open(D+'_labels_glm.tsv','w') as o:
        o.write('addr\tsubsystem\tevidence\tshort_name\tcomment\n')
        for f in sorted(glob.glob(C+'*.tsv')): o.write(open(f).read())
    open(C+'../left_%s.txt'%B,'w').write('\n'.join(left)+'\n')
    print(B,'todo',len(todo),'covered',len(todo)-len(left),'left',len(left)); sys.exit()
model={'glm10':'z-ai/glm-5.3-flash','deepseek10':'deepseek/deepseek-v4.1-flash'}[STAGE]
left=[a for a in todo if a not in covered()]
bs=[left[i:i+10] for i in range(0,len(left),10)]
print(B,STAGE,'left',len(left),'batches',len(bs),flush=True)
def run(i):
    user='\n\n'.join(ns['hints'](a)+'\n// ==== '+ns['fmt'](a,0) for a in bs[i])
    for att in range(2):
        try:
            out,u=ns['cc'].call_hive(ns['key'],model,ns['SYS'],user,temperature=0.1,max_tokens=24000,timeout_s=600)
            ok=[l for l in out.splitlines() if l.count('\t')>=4 and l.split('\t')[0].strip() in bs[i]]
            if ok:
                open(C+f'esc_{STAGE}_{i:04d}.tsv','w').write('\n'.join(ok)+'\n'); return len(ok)
        except Exception as e: time.sleep(5)
    return -1
with cf.ThreadPoolExecutor(4) as ex:
    r=list(ex.map(run,range(len(bs))))
print(B,STAGE,'rows',sum(x for x in r if x>0),'failed',sum(1 for x in r if x<0),flush=True)
