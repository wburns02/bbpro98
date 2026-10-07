#!/usr/bin/env python3
"""Fix tier for the 3 remaining annotation-only PARTIAL drafts (0a7ad, 3aad7,
44cbd): GLM writes v2 superseding rules, pass-3 audits them, then a CORRECTED
local merge (bottom-up span application so earlier replacements cannot shift
later spans; number prefixes preserved)."""
import re, os, importlib.machinery, importlib.util, time

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

TARGETS = ['FUN_6800a7ad', 'FUN_6803aad7', 'FUN_68044cbd']
FIX_SYS = ("You fix a reverse-engineering spec draft. The draft has a CORRECTIONS section listing exact findings "
           "(each contradicts a specific rule, quoting decompile bytes as evidence). "
           "Write ONLY the corrected versions of the flagged rules, in the draft's own numbered-rule style, "
           "matching the evidence quotes exactly (offsets, constants, FUN_ calls). Prefix each with the original rule id it replaces, "
           "e.g. 'replaces rule 4:'. Output only the replacement rules, nothing else. Be terse.")
V2_SYS = ("You verify corrected RE spec rules. A draft had audit CORRECTIONS; RULES v2 claims to supersede the flagged rules. "
          "Check: (a) does each v2 rule resolve the corresponding CORRECTIONS finding, (b) does each v2 rule match the decompile evidence? "
          "Output format, nothing else:\nVERDICT: RESOLVED or PARTIAL or WRONG\nthen bullet lines 'issue' for every v2 rule that fails (a) or (b), quoting decompile bytes. "
          "If all resolve and match: VERDICT: RESOLVED, at most 1 caveat bullet.")

def hive(sys, user, mt):
    for att in range(3):
        try:
            r, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', sys, user, temperature=0.1, max_tokens=mt, timeout_s=600)
            if 'VERDICT' in r or 'replaces rule' in r: return r
        except Exception: time.sleep(4)
    return None

for fn in TARGETS:
    v2out = f'/mnt/nvme/bbpro98/re/spec_v2/{fn}.v2.txt'
    dp = f'/mnt/nvme/bbpro98/re/spec/{fn}.md'
    core = fn
    if core not in funcs:
        print(fn, 'no-slice'); continue
    draft = open(dp).read()
    if not os.path.exists(v2out):
        mc = re.search(r'CORRECTIONS \(audit pass 2.*?\n(.*?)(?=\n\S|\nRULES v2|\nSTATUS|$)', draft, flags=re.S)
        if not mc:
            print(fn, 'no-corrections'); continue
        r = hive(FIX_SYS, f"=== DRAFT {fn} (rules to fix are those named in CORRECTIONS) ===\n{draft[:9000]}\n=== CORRECTIONS ===\n{mc.group(1)}\n=== DECOMPILE {core} ===\n{funcs[core][:30000]}", 32000)
        if r and 'replaces rule' in r:
            open(v2out, 'w').write(r); print(fn, 'v2 ok', flush=True)
        else:
            print(fn, 'v2 FAIL', flush=True); continue
    v3out = f'/mnt/nvme/bbpro98/re/spec_v2_audit/{fn}.txt'
    if not os.path.exists(v3out):
        r = hive(V2_SYS, f"=== CORRECTIONS ===\nsee {fn} audit\n=== RULES v2 ({fn}) ===\n{open(v2out).read()}\n=== DECOMPILE {core} ===\n{funcs[core][:48000]}", 32000)
        if r:
            open(v3out, 'w').write(r); print(fn, 'v2 audit:', r.split(chr(10))[0], flush=True)
        else:
            print(fn, 'v2 audit FAIL', flush=True); continue
    verdict = open(v3out).read()
    if not verdict.startswith('VERDICT: RESOLVED'):
        print(fn, 'NOT merged (', verdict.split(chr(10))[0], ')'); continue
    # corrected merge: bottom-up span application, preserve number prefixes
    body, _, appendix = draft.partition('\nRULES v2 (corrections applied')
    v2 = open(v2out).read()
    blocks = []
    cur = None
    for line in v2.split('\n'):
        m = re.match(r'\s*replaces (?:rule )?([0-9]+(?:\.[0-9]+)?)\s*:\s*(.*)', line)
        if m:
            cur = {'id': m.group(1), 'text': [m.group(2)]}
            blocks.append(cur)
        elif cur is not None and line.strip():
            cur['text'].append(line)
    lines = body.split('\n')
    nxt = re.compile(r'^(\s*(?:\*\*)?\s*[0-9]+(?:\.[0-9]+)?(?:\)|\.|\s)\s|\*\*|#{1,3} |[A-Z][A-Z ]{3,})')
    spans = []
    for b in blocks:
        rid = re.escape(b['id'])
        pat = re.compile(rf'^\s*(?:\*\*)?\s*{rid}(?:\)|\.|\s)\s*')
        start = next((i for i, l in enumerate(lines) if pat.match(l) and lines[i].strip() != ''), None)
        if start is None:
            print(f'  UNLOCATED rule {b["id"]} in {fn}', flush=True); continue
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if nxt.match(lines[i]): end = i; break
        spans.append((start, end, b))
    used = []
    for start, end, b in sorted(spans, key=lambda s: -s[0]):   # bottom-up
        indent = re.match(r'\s*', lines[start]).group(0)
        num = re.match(r'((?:\*\*)?\s*[0-9]+(?:\.[0-9]+)?[\)\.]\s*)', lines[start])
        prefix = num.group(1) if num else ''
        first = b['text'][0]
        if prefix and not re.match(r'^\s*[0-9]+', first):
            b = dict(b, text=[prefix + first] + b['text'][1:])
        newtext = ('\n'.join((indent + tl) if tl else tl for tl in b['text'])).strip('\n')
        lines[start:end] = newtext.split('\n')
        used.append(b['id'])
    if not used:
        print(fn, 'nothing located'); continue
    news = '\n'.join(lines).rstrip('\n') + '\n\nCORRECTIONS HISTORY (audit pass 2 findings; rules above were rewritten accordingly):\n'
    mc2 = re.search(r'CORRECTIONS \(audit pass 2.*?\n(.*?)(?=\n\S|\nRULES v2|$)', body, flags=re.S)
    hist = mc2.group(1).strip('\n') if mc2 else '(corrections block not found)'
    news += hist + '\n'
    open(dp, 'w').write(news)
    print(fn, 'MERGED rules', ','.join(used), flush=True)
print('done', flush=True)
