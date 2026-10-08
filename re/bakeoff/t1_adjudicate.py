#!/usr/bin/env python3
"""Bake-off tier 1 supplement: blind forced choice on the functions where the models' subsystems disagree.
usage: t1_adjudicate.py SEED   (after t1_label.py run for glm, haiku, sonnet)

The absolute OK/WRONG grader (label_spotcheck.py) is lenient: it accepts any "reasonable reading", so it barely separates
labelers. Here the same grader model (DeepSeek-V4.1-Flash, Hive) sees the function with the same context and the distinct
candidate subsystems in shuffled order with no model names, and picks the best one (or NONE). Each model scores the
functions where its subsystem was picked. Writes adjudicate.tsv next to the labels.
"""
import csv, importlib.machinery, importlib.util, random, sys
sys.path.insert(0, '/home/will/bbpro98/re/bakeoff')
from t1_label import BINS, OUT, ctx, load

SEED = int(sys.argv[1])
D = f'{OUT}{SEED}/'
MS = ('glm', 'haiku', 'sonnet')
L = {m: {(r[0], r[1]): r[2:] for r in csv.reader(open(f'{D}labels_{m}.tsv'), delimiter='\t')} for m in MS}
keys = [k for k in L['glm'] if len({L[m][k][0] for m in MS}) > 1]
data = {B: load(B) for B in BINS}
ld = importlib.machinery.SourceFileLoader('cc', '/home/will/bin/cloud-code')
sp = importlib.util.spec_from_loader('cc', ld)
cc = importlib.util.module_from_spec(sp)
ld.exec_module(cc)
key = cc.load_hive_key()
SYS = ("You adjudicate function labels for a 1998 Win32 baseball game (Sierra FPS Baseball Pro 98), decompiled by Ghidra. "
       "You get one function (body, plus the current labels of its callers and callees) and a few candidate "
       "subsystems. Pick the ONE candidate that best describes what this function does, judged from the body's "
       "strings, API calls and data, then its neighbours. Ghidra MFC names on the game's own code are false matches "
       "(no binary links MFC). Answer NONE only if every candidate is clearly wrong. Output exactly two lines: "
       "CHOICE: <letter or NONE> and REASON: <max 20 words>.")
rng = random.Random(SEED)
out = open(D + 'adjudicate.tsv', 'w')
out.write('binary\taddr\t' + '\t'.join(MS) + '\tchoice\treason\n')
score = {m: 0 for m in MS}
for k in keys:
    cands = sorted({L[m][k][0] for m in MS})
    rng.shuffle(cands)
    letters = 'ABCD'
    user = ctx(k[0], k[1], *data[k[0]]) + '\n\nCandidates:\n' + '\n'.join(f'{letters[i]}. {c}' for i, c in
                                                                          enumerate(cands))
    choice, reason = 'NONE', 'no answer'
    for att in range(3):
        try:
            txt, _ = cc.call_hive(key, 'deepseek/deepseek-v4.1-flash', SYS, user, temperature=0.1, max_tokens=8000,
                                  timeout_s=600)
        except Exception:
            continue
        c = [l.split(':', 1)[1].strip() for l in txt.splitlines() if l.upper().startswith('CHOICE:')]
        r = [l.split(':', 1)[1].strip() for l in txt.splitlines() if l.upper().startswith('REASON:')]
        if c and (c[0][:1] in letters[:len(cands)] or c[0].upper().startswith('NONE')):
            choice = cands[letters.index(c[0][:1])] if c[0][:1] in letters[:len(cands)] else 'NONE'
            reason = r[0] if r else ''
            break
    for m in MS:
        score[m] += L[m][k][0] == choice
    out.write('\t'.join([*k, *(L[m][k][0] for m in MS), choice, reason]) + '\n')
    out.flush()
print('disagreements', len(keys), 'picked:', score)
