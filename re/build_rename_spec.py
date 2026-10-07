#!/usr/bin/env python3
"""build_rename_spec.py BINARY... -> re/rename_spec_<tag>.py for gh.sh batch. Only XREF_CONFIDENT/STRING_XREF labels with a name; drops labels whose support is FID-noise (IsTracking, _AFX_CONTROLPOS, CSplitterWnd).
Names are SUBSYS_short_name; collisions get _<addr>. PATTERN_GUESS/UNKNOWN are never renamed."""
import sys,re,collections,json,os
EXT={'Baseball':'exe'}
NOISE=re.compile(r'IsTracking|_AFX_|CSplitterWnd|CControlBar',re.I)
out=[];stats={}
for B in sys.argv[1:]:
    D=f'/mnt/nvme/bbpro98/index/{B}/'; fn=B+'.'+EXT.get(B,'dll')
    cur={l.split('\t')[0]:l.split('\t')[1] for l in open(D+'_functions.tsv').read().splitlines()[1:]}
    rows=[l.split('\t') for l in open(D+'_labels_glm.tsv').read().splitlines()[1:]]
    seen=set(); n=0; skipped=collections.Counter()
    for r in rows:
        if len(r)<5: skipped['short']+=1; continue
        a,sub,ev,nm,cm=[x.strip() for x in r[:5]]
        if ev.upper() not in ('XREF_CONFIDENT','STRING_XREF'): skipped['grade']+=1; continue
        if not nm or not re.fullmatch(r'[a-z][a-z0-9_]{2,60}',nm): skipped['name']+=1; continue
        if NOISE.search(cm): skipped['noise']+=1; continue
        if a not in cur or not cur[a].startswith('FUN_'): skipped['notdefault']+=1; continue
        new=f'{sub}_{nm}' if sub not in ('UNKNOWN','') else nm
        if new in seen: new+='_'+a
        seen.add(new); out.append((fn,int(a,16),new)); n+=1
    stats[B]=(n,dict(skipped))
tag='_'.join(sys.argv[1:])
open(f'/mnt/nvme/bbpro98/re/rename_spec_{tag}.py','w').write('RENAMES='+json.dumps(out)+'\nLABELS=[]\nSTRUCT_BINARIES=[]\ndef STRUCTS(b,p): pass\n')
print(json.dumps(stats))
