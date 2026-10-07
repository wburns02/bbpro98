#!/usr/bin/env python3
"""Fix tier: for each PARTIAL-audited draft, have GLM-Flash write superseding
rules that apply the audit corrections, appended as RULES v2 sections."""
import re, os, glob, importlib.machinery, importlib.util, concurrent.futures as cf, time
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
SYS = ("You fix a reverse-engineering spec draft. The draft has a CORRECTIONS section listing exact findings "
"(each contradicts a specific rule, quoting decompile bytes as evidence). "
"Write ONLY the corrected versions of the flagged rules, in the draft's own numbered-rule style, "
"matching the evidence quotes exactly (offsets, constants, FUN_ calls). Prefix each with the original rule id it replaces, "
"e.g. 'replaces rule 4:'. Output only the replacement rules, nothing else. Be terse.")
def fix(path):
    fn = os.path.basename(path)[:-3]
    out = f'/mnt/nvme/bbpro98/re/spec_v2/{fn}.v2.txt'
    if os.path.exists(out): return fn, 'cached'
    draft = open(path).read()
    m = re.search(r'CORRECTIONS \(audit pass 2.*?\n(.*?)\n$', draft, flags=re.S)
    if not m: return fn, 'no-corrections'
    corr = m.group(1)
    core = re.match(r'(FUN_[0-9a-f]+)', fn).group(1)
    if core not in funcs: return fn, 'no-slice'
    user = f"=== DRAFT {fn} (rules to fix are those named in CORRECTIONS) ===\n{draft[:9000]}\n=== CORRECTIONS ===\n{corr}\n=== DECOMPILE {core} ===\n{funcs[core][:22000]}"
    for att in range(2):
        try:
            r, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', SYS, user, temperature=0.1, max_tokens=16000, timeout_s=600)
            if 'replaces rule' in r or len(r) > 150:
                open(out, 'w').write(r); return fn, 'ok'
        except Exception: time.sleep(4)
    return fn, 'fail'
os.makedirs('/mnt/nvme/bbpro98/re/spec_v2', exist_ok=True)
targets = []
for apath in sorted(glob.glob('/mnt/nvme/bbpro98/re/spec_audit/FUN_*.txt')):
    if open(apath).read().startswith('VERDICT: PARTIAL'):
        dp = f"/mnt/nvme/bbpro98/re/spec/{os.path.basename(apath)[:-4]}.md"
        if os.path.exists(dp): targets.append(dp)
print('targets', len(targets), flush=True)
with cf.ThreadPoolExecutor(3) as ex:
    for fn, st in ex.map(fix, targets):
        print(st, fn, flush=True)
