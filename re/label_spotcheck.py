#!/usr/bin/env python3
"""M1-M3 label spot check. usage: label_spotcheck.py N SEED BINARY [BINARY ...]

Samples N functions at random (seeded, pooled over the binaries' _functions_labeled.tsv) and has a holdout grader of a
different model family from the labeler (DeepSeek-V4.1-Flash on Hive; the labels come from det rules + GLM-Flash) judge
each label against the decompiled body and the labels of its callers and callees: OK, WRONG (the body or neighbours
clearly contradict the subsystem) or UNSURE. Writes /mnt/nvme/bbpro98/re/spotcheck/<seed>.tsv and prints the gate
numbers: evidence XREF_CONFIDENT or better >= 80% and WRONG < 5% of the sample. WRONG rows are for Claude to read.
"""
import csv, importlib.machinery, importlib.util, os, random, re, sys, time

N, SEED, BINS = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
STRONG = ('CONFIRMED', 'STRING_XREF', 'XREF_CONFIDENT')
OUT = '/mnt/nvme/bbpro98/re/spotcheck/'
os.makedirs(OUT, exist_ok=True)


def rows(path):
    return [r for r in csv.reader(open(path, errors='replace'), delimiter='\t')][1:]


lab, funcs, body = {}, {}, {}
for B in BINS:
    D = f'/mnt/nvme/bbpro98/index/{B}/'
    for r in rows(D + '_functions_labeled.tsv'):
        lab[(B, r[0])] = r
    for r in rows(D + '_functions.tsv'):
        funcs[(B, r[0])] = r
    text = open(D + '_all.c', errors='replace').read()
    for p in re.split(r'^// ==== ', text, flags=re.M)[1:]:
        body[(B, p.split()[0])] = p

# SPOT_FILTER (diagnostics only, never for the gate): sample only labels whose source+comment match this regex
FILT = os.environ.get('SPOT_FILTER')
pool = sorted(k for k in lab if not FILT or re.search(FILT, lab[k][6] + ' ' + lab[k][5]))
sample = random.Random(SEED).sample(pool, min(N, len(pool)))
N = len(sample)


def ctx(k):
    B, a = k
    f = funcs.get(k)

    def nb(x):
        r = lab.get((B, x))
        return f'{x} {r[2]} {r[4]}'.strip() if r else f'{x} ?'
    callers = [c for c in (f[3].split(',') if f else []) if (B, c) in lab][:8]
    callees = [c for c in (f[4].split(',') if f else []) if (B, c) in lab][:10]
    r = lab[k]
    b = '\n'.join(body.get(k, a).split('\n')[:60])[:3000]
    return (f'// function {a} in {B}\n// LABEL subsystem={r[2]} evidence={r[3]} short_name={r[4]} comment={r[5]}\n'
            f'// callers: {"; ".join(map(nb, callers)) or "none"}\n// callees: {"; ".join(map(nb, callees)) or "none"}'
            f'\n// ==== {b}')


SYS = ("You audit function labels for a 1998 Win32 baseball game (Sierra FPS Baseball Pro 98), decompiled by Ghidra. "
       "Subsystems: CRT MATH IO_FILE IO_REGISTRY STRUCT_INIT SIM_PITCH SIM_SWING SIM_FIELD SIM_BASE SIM_INJURY "
       "SIM_FATIGUE SIM_LINEUP SIM_GAME SIM_STATS SIM_UMPIRE SIM_AI RATING SEASON UI_MAIN UI_STATS UI_LINEUP UI_DIALOG "
       "UI_RENDER GDI WIN32 MFC_LIB AUDIO ANIM CAMERA STUB UTIL. For each function decide whether its LABEL "
       "subsystem is consistent with the body (strings, API calls, data it touches) and with its callers/callees. "
       "Answer WRONG only when something concrete contradicts it (say what, and the subsystem it should be). Answer "
       "OK when the label fits or is a reasonable reading. UNSURE when the body gives too little to judge. Ghidra "
       "MFC names on the game's own code (CSplitterWnd, IsTracking, CMiniDockFrameWnd, CWnd ...) are false matches: no "
       "binary links MFC, so never propose MFC_LIB; judge such a function by its body. "
       "Output ONLY TSV rows, one per function: addr<TAB>OK|WRONG|UNSURE<TAB>reason (max 20 words).")

ld = importlib.machinery.SourceFileLoader('cc', '/home/will/bin/cloud-code')
sp = importlib.util.spec_from_loader('cc', ld)
cc = importlib.util.module_from_spec(sp)
ld.exec_module(cc)
key = cc.load_hive_key()

res = {}
for i in range(0, N, 10):
    batch = sample[i:i + 10]
    user = '\n\n'.join(ctx(k) for k in batch)
    for att in range(3):
        try:
            out, _ = cc.call_hive(key, 'deepseek/deepseek-v4.1-flash', SYS, user, temperature=0.1, max_tokens=16000,
                                  timeout_s=600)
        except Exception as e:
            print('hive error', e, file=sys.stderr)
            time.sleep(5)
            continue
        got = {}
        for l in out.splitlines():
            p = [x.strip() for x in l.split('\t')]
            if len(p) >= 2 and p[1] in ('OK', 'WRONG', 'UNSURE'):
                for k in batch:
                    if k[1] == p[0].lower().replace('0x', '').replace('fun_', ''):
                        got[k] = (p[1], p[2] if len(p) > 2 else '')
        if len(got) == len(batch):
            res.update(got)
            break
    else:
        res.update({k: ('UNSURE', 'grader gave no usable answer') for k in batch if k not in res})

with open(f'{OUT}{SEED}.tsv', 'w') as o:
    o.write('binary\taddr\tsubsystem\tevidence\tshort_name\tverdict\treason\n')
    for k in sample:
        r = lab[k]
        o.write('\t'.join([k[0], k[1], r[2], r[3], r[4], *res[k]]) + '\n')
strong = sum(1 for k in sample if lab[k][3] in STRONG)
v = {x: sum(1 for k in sample if res[k][0] == x) for x in ('OK', 'WRONG', 'UNSURE')}
print(f'sample {N} (seed {SEED}, {" ".join(BINS)}): evidence XREF_CONFIDENT or better {strong} ({strong / N:.0%}); '
      f'grader {v}; WRONG {v["WRONG"] / N:.0%}')
for k in sample:
    if res[k][0] == 'WRONG':
        print('  WRONG', k[0], k[1], lab[k][2], lab[k][4], '|', res[k][1])
