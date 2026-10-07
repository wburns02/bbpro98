#!/usr/bin/env python3
"""Follow-on run: (A) post-merge audit the 12 remaining merged drafts,
(B) write v2 superseding rules for FUN_68054d4a_consumer's 2 chunked-audit
corrections, (C) pass-3 audit that v2, (D) local merge of consumer v2 into
the draft body. Phases A-C are Hive; D is local."""
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
TAB = {}
with open('/mnt/nvme/bbpro98/re/pb_table_FastSim.tsv') as f:
    for row in csv.DictReader(f, delimiter='\t'):
        TAB[int(row['idx'])] = row
GETTER = ("VERIFIED CONTEXT (do not re-derive, do not flag): FUN_68003170(idx) is the "
          "PlayBalance getter: it returns *(unsigned int*)(&DAT_6808fde0 + idx*4). "
          "PLAYBALANCE TABLE ROWS for this function (idx -> name, default): ")
def table_rows(draft):
    idxs = {int(h, 16) for h in re.findall(r'0x([0-9a-fA-F]+)', draft) if int(h, 16) in TAB}
    idxs |= {int(r['idx']) for r in TAB.values() if r['name'] in draft}
    if not idxs: return '(none cited)'
    return '; '.join(f"{i} -> {TAB[i]['name']}, default {TAB[i]['dll_default']}" for i in sorted(idxs))

AUD_SYS = ("You audit a reverse-engineering spec draft against the real Ghidra decompile of the same function from a 1998 baseball sim. " + GETTER + "{ROWS}. "
           "A draft claim that cites one of these PlayBalance names/defaults is SUPPORTED when the decompile calls FUN_68003170 with the matching index; the decompile will NEVER show PB names or default numbers inline, so absence of the literal name/number in the decompile is NOT an error. "
           "Flag only: wrong signature or parameter count, wrong branch or loop structure, wrong non-PB constant, wrong call arguments, wrong addresses, getter indices inconsistent with the table rows, or a rule the decompile flatly contradicts. "
           "Output format, nothing else:\nVERDICT: MATCH or MISMATCH or PARTIAL\n then bullet lines 'addr: issue' for every contradicted or unsupported claim, quoting offsets/bytes from the decompile as evidence. Do not praise. If faithful, output VERDICT: MATCH and at most 1 bullet of caveats.")
def hive(sys, user, mt=16000, tries=3):
    for att in range(tries):
        try:
            r, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', sys, user, temperature=0.1, max_tokens=mt, timeout_s=600)
            if 'VERDICT' in r or 'replaces rule' in r: return r
        except Exception: time.sleep(4)
    return None

# ---- Phase A: post-merge audit of merged drafts (skip the 2 already done)
done = {'FUN_68023dd3', 'FUN_68053248'}
merged = []
for p in sorted(glob.glob('/mnt/nvme/bbpro98/re/spec/*.md')):
    fn = os.path.basename(p)[:-3]
    if fn in done or fn == 'FUN_68054d4a_consumer': continue
    if 'CORRECTIONS HISTORY' in open(p).read(): merged.append(fn)
print('postmerge targets', len(merged), flush=True)
def postmerge(fn):
    out = f'/mnt/nvme/bbpro98/re/spec_v2_audit/{fn}.postmerge.txt'
    if os.path.exists(out): return fn, 'cached'
    draft = open(f'/mnt/nvme/bbpro98/re/spec/{fn}.md').read()[:9000]
    core = re.match(r'(FUN_[0-9a-f]+)', fn).group(1)
    if core not in funcs: return fn, 'no-slice'
    r = hive(AUD_SYS.replace('{ROWS}', table_rows(draft)),
             f"=== DRAFT {fn} (post-merge; some rules were rewritten from audit corrections) ===\n{draft}\n=== DECOMPILE {core} ===\n{funcs[core][:22000]}")
    if r: open(out, 'w').write(r); return fn, 'ok'
    return fn, 'fail'
with cf.ThreadPoolExecutor(3) as ex:
    for fn, st in ex.map(postmerge, merged):
        print('postmerge', st, fn, flush=True)

# ---- Phase B: consumer v2 (superseding rules for the 2 chunked-audit corrections)
CV = 'FUN_68054d4a_consumer'
core = 'FUN_68054d4a'
v2out = f'/mnt/nvme/bbpro98/re/spec_v2/{CV}.v2.txt'
if not os.path.exists(v2out):
    draft = open(f'/mnt/nvme/bbpro98/re/spec/{CV}.md').read()[:14000]
    corr = re.search(r'CORRECTIONS \(chunked audit pass 3.*?\n(.*?)$', open(f'/mnt/nvme/bbpro98/re/spec/{CV}.md').read(), flags=re.S).group(1)
    FIX_SYS = ("You fix a reverse-engineering spec draft against the FULL Ghidra decompile of the same function. The draft has a CORRECTIONS section with 2 verified findings. "
               "Verified facts (do not contradict): FUN_680829dc is called with base &DAT_68185a60, not DAT_68097660; the adjustment after FUN_68005b80(0x4000 - local_58, 0x32 - local_bc) is stored as local_40 = (short)iVar2. "
               "Check the SECOND half of the decompile for what really happens to local_58 after the adjustment, and to the rule-4 table DAT_68097660 usage. "
               "Write ONLY corrected versions of the flagged rules (5, 9, and 10 if the evidence requires it), in the draft's own numbered style, quoting exact decompile bytes. Prefix each with the rule id it replaces, e.g. 'replaces rule 5:'. Output only the replacement rules, nothing else. Be terse.")
    r = hive(FIX_SYS, f"=== DRAFT {CV} ===\n{draft}\n=== CORRECTIONS ===\n{corr}\n=== DECOMPILE {core} (FULL) ===\n{funcs[core][:48000]}", mt=32000, tries=3)
    if r and 'replaces rule' in r:
        open(v2out, 'w').write(r); print('consumer v2 ok', flush=True)
    else:
        print('consumer v2 FAIL', flush=True)

# ---- Phase C: pass-3 audit of the consumer v2
v3out = f'/mnt/nvme/bbpro98/re/spec_v2_audit/{CV}.txt'
if os.path.exists(v2out) and not os.path.exists(v3out):
    v2 = open(v2out).read()
    draft = open(f'/mnt/nvme/bbpro98/re/spec/{CV}.md').read()[:9000]
    V2_SYS = ("You verify corrected RE spec rules. A draft had audit CORRECTIONS; RULES v2 claims to supersede the flagged rules. "
              "Check: (a) does each v2 rule resolve the corresponding CORRECTIONS finding, (b) does each v2 rule match the decompile evidence? " + GETTER + table_rows(draft) + ". "
              "Output format, nothing else:\nVERDICT: RESOLVED or PARTIAL or WRONG\nthen bullet lines 'issue' for every v2 rule that fails (a) or (b), quoting decompile bytes. "
              "If all resolve and match: VERDICT: RESOLVED, at most 1 caveat bullet.")
    r = hive(V2_SYS, f"=== CORRECTIONS ===\n(see consumer audit: rule 5 table base is &DAT_68185a60 not DAT_68097660; adjustment stored to local_40 = (short)iVar2)\n=== RULES v2 ({CV}) ===\n{v2}\n=== DECOMPILE {core} (FULL) ===\n{funcs[core][:48000]}", mt=16000)
    if r: open(v3out, 'w').write(r); print('consumer v2 audit:', r.split(chr(10))[0], flush=True)
    else: print('consumer v2 audit FAIL', flush=True)

# ---- Phase D: local merge of consumer v2 into the draft body (only if v2 RESOLVED)
if os.path.exists(v2out) and os.path.exists(v3out):
    verdict = open(v3out).read()
    print('consumer v3 verdict head:', verdict[:40].replace(chr(10), ' | '), flush=True)
    if verdict.startswith('VERDICT: RESOLVED'):
        dp = f'/mnt/nvme/bbpro98/re/spec/{CV}.md'
        already = 'STATUS: audited (chunked pass 3)' in open(dp).read()
        if already:
            print('consumer already merged; skip', flush=True)
            raise SystemExit
        s = open(dp).read()
        # body is everything before the trailing STATUS/CORRECTIONS block
        mcut = re.search(r'\nSTATUS: unaudited', s)
        body = s[:mcut.start()] if mcut else s
        tail = s[mcut.start():] if mcut else ''
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
        out = list(lines)
        used = []
        for b in blocks:
            rid = re.escape(b['id'])
            pat = re.compile(rf'^\s*(?:\*\*)?\s*{rid}(?:\)|\.|\s)\s*')
            start = next((i for i, l in enumerate(lines) if pat.match(l) and lines[i].strip() != ''), None)
            if start is None:
                print(f'  UNLOCATED rule {b["id"]}', flush=True); continue
            nxt = re.compile(r'^(\s*(?:\*\*)?\s*[0-9]+(?:\.[0-9]+)?(?:\)|\.|\s)\s|\*\*|#{1,3} |[A-Z][A-Z ]{3,})')
            end = len(lines)
            for i in range(start + 1, len(lines)):
                if nxt.match(lines[i]): end = i; break
            indent = re.match(r'\s*', lines[start]).group(0)
            newtext = ('\n'.join((indent + tl) if tl else tl for tl in b['text'])).strip('\n')
            out[start:end] = newtext.split('\n')
            used.append(b['id'])
        news = '\n'.join(out).rstrip('\n') + '\n\nSTATUS: audited (chunked pass 3). Rules ' + ','.join(used) + ' rewritten from the audit corrections (v2 merged ' + time.strftime('%Y-%m-%d') + '); pass-3 verdict RESOLVED.\n'
        mc = re.search(r'CORRECTIONS \(chunked audit pass 3.*?\n(.*?)$', tail, flags=re.S)
        if mc:
            news += '\nCORRECTIONS HISTORY (chunked audit pass 3; rules above were rewritten accordingly):\n' + mc.group(1).strip('\n') + '\n'
        open(dp, 'w').write(news)
        print('consumer MERGED rules', ','.join(used), flush=True)
    else:
        print('consumer v2 NOT merged (not RESOLVED)', flush=True)
print('done', flush=True)
