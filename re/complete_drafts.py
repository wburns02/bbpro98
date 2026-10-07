#!/usr/bin/env python3
"""Complete the two truncated spec drafts by drafting the missing decompile
continuation with GLM-Flash, appending it as a CONTINUATION section."""
import re, importlib.machinery, importlib.util
ld = importlib.machinery.SourceFileLoader('cc', '/home/will/bin/cloud-code')
sp = importlib.util.spec_from_loader('cc', ld)
cc = importlib.util.module_from_spec(sp); ld.exec_module(cc)
key = cc.load_hive_key()
t = open('/mnt/nvme/bbpro98/index/FastSim/_all.c', errors='replace').read()
funcs = {}
for p in re.split(r'^// ==== ', t, flags=re.M)[1:]:
    tk = p.split()
    if len(tk) > 1: funcs.setdefault(tk[1], p)
    funcs.setdefault(tk[0], p)
SYS = ("You are finishing a reverse-engineering spec draft of a 1998 baseball sim function. "
"The draft below got truncated partway through its numbered rules. "
"Continue it: read the DECOMPILE, find where the draft's rules stop matching, and write ONLY the remaining rules in the same style "
"(numbered rules continuing the last number, terse, exact offsets/constants/getter calls quoted; use PB[idx] names for FUN_68003170 calls). "
"Output only the continuation rules, nothing else.")
for fn in ['FUN_6803aad7', 'FUN_68040a7e']:
    dp = f'/mnt/nvme/bbpro98/re/spec/{fn}.md'
    draft = open(dp).read()
    cont = draft.rstrip()[-400:]
    user = f"=== DRAFT (truncated; tail shown to locate the stop point) ===\n...{cont}\n=== FULL DECOMPILE {fn} ===\n{funcs[fn]}"
    r, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', SYS, user, temperature=0.1, max_tokens=16000, timeout_s=600)
    if len(r) > 200:
        open(dp, 'a').write('\n\nCONTINUATION (GLM-Flash, covers the decompile after the truncation point; unaudited):\n\n' + r.strip() + '\n')
        print(fn, 'appended', len(r), 'chars')
    else:
        print(fn, 'REFUSED/too-short:', r[:120])
