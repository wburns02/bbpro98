#!/usr/bin/env python3
"""Pass-3: audit each RULES v2 section (does it resolve the CORRECTIONS and
match the decompile?) + chunked audit of FUN_68054d4a_consumer."""
import re, os, glob, csv, importlib.machinery, importlib.util, concurrent.futures as cf, time
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

V2_SYS = ("You verify corrected RE spec rules. A draft had audit CORRECTIONS; RULES v2 claims to supersede the flagged rules. "
"Check: (a) does each v2 rule resolve the corresponding CORRECTIONS finding, (b) does each v2 rule match the decompile evidence? "
"Output format, nothing else:\nVERDICT: RESOLVED or PARTIAL or WRONG\nthen bullet lines 'issue' for every v2 rule that fails (a) or (b), quoting decompile bytes. "
"If all resolve and match: VERDICT: RESOLVED, at most 1 caveat bullet.")
def v2_job(path):
    fn = os.path.basename(path).replace('.v2.txt', '')
    out = f'/mnt/nvme/bbpro98/re/spec_v2_audit/{fn}.txt'
    if os.path.exists(out): return fn, 'cached'
    dp = f'/mnt/nvme/bbpro98/re/spec/{fn}.md'
    draft = open(dp).read()
    v2 = open(path).read()
    mc = re.search(r'CORRECTIONS \(audit pass 2.*?\n(.*?)(?=\nRULES v2|$)', draft, flags=re.S)
    corr = mc.group(1) if mc else '(corrections section missing)'
    core = re.match(r'(FUN_[0-9a-f]+)', fn).group(1)
    if core not in funcs: return fn, 'no-slice'
    user = f"=== CORRECTIONS ===\n{corr}\n=== RULES v2 ({fn}) ===\n{v2}\n=== DECOMPILE {core} ===\n{funcs[core][:24000]}"
    for att in range(3):
        try:
            r, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', V2_SYS, user, temperature=0.1, max_tokens=16000, timeout_s=600)
            if 'VERDICT' in r:
                open(out, 'w').write(r); return fn, 'ok'
        except Exception: time.sleep(4)
    return fn, 'fail'

CONS_SYS = ("You audit a RE spec draft fragment against HALF of a large Ghidra decompile of the same 1998 baseball-sim function. "
"VERIFIED: FUN_68003170(idx) is the PlayBalance getter: *(unsigned int*)(&DAT_6808fde0 + idx*4); the decompile never shows PB names/defaults inline. "
"Verify only the draft rules whose behavior appears in THIS half. Output format, nothing else:\nVERDICT: MATCH or PARTIAL or MISMATCH\nthen bullets 'addr: issue' for contradicted claims, quoting offsets/bytes. At most 3 bullets. Be terse.")
def cons_job():
    out = '/mnt/nvme/bbpro98/re/spec_audit/FUN_68054d4a_consumer.txt'
    if os.path.exists(out): return 'consumer', 'cached'
    fn = 'FUN_68054d4a_consumer'
    core = 'FUN_68054d4a'
    if core not in funcs: return 'consumer', 'no-slice'
    draft = open(f'/mnt/nvme/bbpro98/re/spec/{fn}.md').read()[:12000]
    src = funcs[core]
    lines = src.split('\n')
    half = len(lines) // 2
    # split at a section boundary if possible
    cut = half
    for j in range(half, min(half + 60, len(lines))):
        if lines[j].startswith('// ===='): cut = j; break
    parts = {'c1': '\n'.join(lines[:cut]), 'c2': '\n'.join(lines[cut:])}
    verdicts = []
    for tag, sl in parts.items():
        pout = f'/mnt/nvme/bbpro98/re/spec_audit/{fn}_{tag}.txt'
        if os.path.exists(pout):
            verdicts.append(open(pout).read()); continue
        for att in range(3):
            try:
                r, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', CONS_SYS, f"=== DRAFT {fn} ===\n{draft}\n=== DECOMPILE {core} ({tag}) ===\n{sl[:24000]}", temperature=0.1, max_tokens=16000, timeout_s=600)
                if 'VERDICT' in r:
                    open(pout, 'w').write(r); verdicts.append(r); break
            except Exception: time.sleep(4)
        else:
            verdicts.append('VERDICT: UNAUDITED (chunk failed)')
    v = 'MISMATCH' if any('MISMATCH' in x for x in verdicts) else ('PARTIAL' if any('PARTIAL' in x for x in verdicts) else ('MATCH' if all('MATCH' in x for x in verdicts) else 'UNAUDITED'))
    open(out, 'w').write(f"VERDICT: {v}\n\n" + '\n\n'.join(verdicts))
    return 'consumer', v.lower()

os.makedirs('/mnt/nvme/bbpro98/re/spec_v2_audit', exist_ok=True)
targets = sorted(glob.glob('/mnt/nvme/bbpro98/re/spec_v2/*.v2.txt'))
print('v2 targets', len(targets), flush=True)
with cf.ThreadPoolExecutor(3) as ex:
    for fn, st in ex.map(v2_job, targets):
        print('v2', st, fn, flush=True)
print('consumer', cons_job(), flush=True)
