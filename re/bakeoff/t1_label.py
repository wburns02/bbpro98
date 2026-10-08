#!/usr/bin/env python3
"""Bake-off tier 1 (2026-10-08): the label_refine.py labeling task, same prompt and per-function context, run by several
models on one fresh sample; then graded by the unchanged label_spotcheck.py.

usage: t1_label.py sample SEED N            -> /mnt/nvme/bbpro98/bakeoff/t1/<SEED>/sample.tsv
       t1_label.py run SEED MODEL           MODEL = glm | haiku | sonnet (writes labels_<MODEL>.tsv + cost_<MODEL>.json)
       t1_label.py shadow SEED MODEL        builds shadow/<MODEL>/{BBSIM,BBShell}/ for the grader (MODEL = prod for the
                                            current production labels)

The sample pool is every BBSIM + BBShell function whose current label came from a model (source glm | refine): det,
STUB and post-pass rows are rule-made and never reach a model, so they would only dilute the comparison. Each function
goes with its body and the CURRENT labels of its callers and callees (exactly what label_refine.py's ctx() shows); its
own label is never shown. The grader sees the model's label in a shadow _functions_labeled.tsv whose source column is
'bake' for the sampled rows, selected with SPOT_FILTER='^bake'.
"""
import csv, importlib.machinery, importlib.util, json, os, random, re, subprocess, sys, time

BINS = ('BBSIM', 'BBShell')
OUT = '/mnt/nvme/bbpro98/bakeoff/t1/'
JAIL = '/home/will/bbpro98/re/bakeoff/claude_jail.sh'
CLAUDE = {'haiku': 'claude-haiku-5-5', 'sonnet': 'claude-sonnet-5-5'}
SUB = ('CRT MATH IO_FILE IO_REGISTRY STRUCT_INIT SIM_PITCH SIM_SWING SIM_FIELD SIM_BASE SIM_INJURY SIM_FATIGUE '
       'SIM_LINEUP SIM_GAME SIM_STATS SIM_UMPIRE SIM_AI RATING SEASON UI_MAIN UI_STATS UI_LINEUP UI_DIALOG UI_RENDER '
       'GDI WIN32 MFC_LIB AUDIO ANIM CAMERA STUB UTIL UNKNOWN').split()
EVID = ('CONFIRMED', 'STRING_XREF', 'XREF_CONFIDENT', 'PATTERN_GUESS', 'UNKNOWN')
# verbatim from label_refine.py
SYS = ("You label functions decompiled by Ghidra from a 1998 Win32 baseball sim (Sierra FPS Baseball Pro 98). "
       "Output ONLY TSV rows, one per input function, no prose: addr<TAB>subsystem<TAB>evidence<TAB>short_name"
       "<TAB>comment. subsystem is one of: " + ' '.join(SUB) + ". evidence is one of STRING_XREF (a string "
       "literal or named API in the body supports it), XREF_CONFIDENT (the labelled callers/callees or the body's "
       "API calls clearly imply it), PATTERN_GUESS (shape only). IO_REGISTRY is the Windows registry and INI/config (cfgGetInt, GetPrivateProfile*, "
       "Reg*); c-tree ISAM database calls (ADDREC, NXTSET, OPNIFIL ...) are IO_FILE. Each function comes with the current labels of "
       "its callers and callees: use them. Pick the most likely subsystem even when the evidence is only "
       "PATTERN_GUESS; UNKNOWN only when nothing at all points anywhere. Tiny wrappers take the subsystem of what "
       "they wrap. short_name lower_snake_case or empty; comment max 12 words, factual, naming the callee, string "
       "or neighbour label that supports it. Never invent. MFC names Ghidra put on this game's own code are FALSE "
       "matches (CSplitterWnd, IsTracking, CMiniDockFrameWnd, CControlBar, CFrameWnd, CWnd, CDialog, _AFX_*, "
       "AfxXxx, OnClose, EnableStackedTabs ...): never use them as evidence, judge by what the code does with "
       "the data. A neighbour label that itself rests on such a name is weak.")


def rows(path):
    return [r for r in csv.reader(open(path, errors='replace'), delimiter='\t')][1:]


def load(B):
    D = f'/mnt/nvme/bbpro98/index/{B}/'
    funcs = {r[0]: r for r in rows(D + '_functions.tsv')}
    lab = {r[0]: r for r in rows(D + '_functions_labeled.tsv')}
    text = open(D + '_all.c', errors='replace').read()
    body = {p.split()[0]: p for p in re.split(r'^// ==== ', text, flags=re.M)[1:]}
    return funcs, lab, body


def ctx(B, a, funcs, lab, body):  # label_refine.py ctx(), with cur = the current labeled table
    f = funcs[a]

    def nb(x):
        s = lab.get(x)
        if not s or s[2] in ('', 'UNKNOWN'):
            return f'{x} ?'
        nm = funcs[x][1] if not funcs[x][1].startswith('FUN_') else ''
        return f'{x} {s[2]}{" " + s[4] if s[4] else ""}{" " + nm if nm else ""}'
    callers = [c for c in f[3].split(',') if c in funcs][:8]
    callees = [c for c in f[4].split(',') if c in funcs][:10]
    b = '\n'.join(body.get(a, a).split('\n')[:70])[:3500]
    return (f'// callers: {"; ".join(map(nb, callers)) or "none"}\n// callees: '
            f'{"; ".join(map(nb, callees)) or "none"}\n// ==== {b}')


def sample(seed, n):
    pool = []
    for B in BINS:
        _, lab, _ = load(B)
        pool += [(B, a) for a, r in lab.items() if r[6] in ('glm', 'refine')]
    pool.sort()
    s = random.Random(seed).sample(pool, n)
    d = f'{OUT}{seed}/'
    os.makedirs(d, exist_ok=True)
    with open(d + 'sample.tsv', 'w') as o:
        o.write(''.join(f'{B}\t{a}\n' for B, a in s))
    print(len(pool), 'in pool; wrote', d + 'sample.tsv')


def call_claude(model, user):
    t0 = time.time()
    p = subprocess.run([JAIL, CLAUDE[model], '-', '--system-prompt', SYS, '--tools', '', '--output-format', 'json'],
                       input=user, capture_output=True, text=True, timeout=1800)
    d = json.loads(p.stdout)
    u = d['modelUsage'][CLAUDE[model]]
    return d['result'], {'in': u['inputTokens'] + u['cacheReadInputTokens'] + u['cacheCreationInputTokens'],
                         'out': u['outputTokens'], 'list_usd': u['costUSD'], 'secs': time.time() - t0}


def call_glm(user):
    ld = importlib.machinery.SourceFileLoader('cc', '/home/will/bin/cloud-code')
    sp = importlib.util.spec_from_loader('cc', ld)
    cc = importlib.util.module_from_spec(sp)
    ld.exec_module(cc)
    t0 = time.time()
    out, u = cc.call_hive(cc.load_hive_key(), 'z-ai/glm-5.3-flash', SYS, user, temperature=0.1, max_tokens=24000,
                          timeout_s=600)
    i, o = u.get('prompt_tokens', 0), u.get('completion_tokens', 0)
    return out, {'in': i, 'out': o, 'usd': i * 0.05e-6 + o * 0.17e-6, 'secs': time.time() - t0}


def run(seed, model):
    d = f'{OUT}{seed}/'
    smp = [l.split() for l in open(d + 'sample.tsv')]
    data = {B: load(B) for B in BINS}
    got, costs = {}, []
    # batches of 20 like label_refine.py; one binary per batch so addresses are unambiguous
    batches = []
    for B in BINS:
        xs = [a for b, a in smp if b == B]
        batches += [(B, xs[i:i + 20]) for i in range(0, len(xs), 20)]
    for B, xs in batches:
        user = '\n\n'.join(ctx(B, a, *data[B]) for a in xs)
        for att in range(3):
            try:
                out, c = call_glm(user) if model == 'glm' else call_claude(model, user)
            except Exception as e:
                print('error', model, B, e, file=sys.stderr)
                time.sleep(5)
                continue
            c['attempt'] = att
            costs.append(c)
            ok = {}
            for l in out.splitlines():
                p = [x.strip() for x in l.split('\t')]
                if len(p) >= 5 and p[0].lower().replace('0x', '').replace('fun_', '') in xs:
                    ok[p[0].lower().replace('0x', '').replace('fun_', '')] = p[1:5]
            if len(ok) >= len(xs) * 0.8:
                got.update({(B, a): v for a, v in ok.items()})
                break
        print(model, B, xs[0], len([a for a in xs if (B, a) in got]), '/', len(xs), flush=True)
    with open(f'{d}labels_{model}.tsv', 'w') as o:
        for B, a in smp:
            v = got.get((B, a), ['UNKNOWN', 'UNKNOWN', '', 'no answer'])
            o.write('\t'.join([B, a] + v) + '\n')
    json.dump(costs, open(f'{d}cost_{model}.json', 'w'), indent=1)
    print(model, 'answered', len(got), 'of', len(smp), 'secs', round(sum(c['secs'] for c in costs)))


def shadow(seed, model):
    d = f'{OUT}{seed}/'
    smp = {(l.split()[0], l.split()[1]) for l in open(d + 'sample.tsv')}
    new = {}
    if model != 'prod':
        for l in open(f'{d}labels_{model}.tsv'):
            p = l.rstrip('\n').split('\t')
            new[(p[0], p[1])] = p[2:6]
    for B in BINS:
        S = f'{d}shadow/{model}/{B}/'
        os.makedirs(S, exist_ok=True)
        src = f'/mnt/nvme/bbpro98/index/{B}/'
        for f in ('_functions.tsv', '_all.c'):
            if not os.path.lexists(S + f):
                os.symlink(src + f, S + f)
        with open(src + '_functions_labeled.tsv', errors='replace') as i, open(S + '_functions_labeled.tsv', 'w') as o:
            for n, l in enumerate(i):
                p = l.rstrip('\n').split('\t')
                if n and (B, p[0]) in smp:
                    if model != 'prod':
                        sub, ev, nm, cm = (new[(B, p[0])] + ['', '', '', ''])[:4]
                        p[2:6] = [sub if sub in SUB else 'UNKNOWN', ev if ev in EVID else 'UNKNOWN', nm,
                                  cm.replace('\t', ' ')]
                    p[6] = 'bake'
                o.write('\t'.join(p) + '\n')
    print(d + 'shadow/' + model)


if __name__ == '__main__':
    cmd, seed = sys.argv[1], int(sys.argv[2])
    if cmd == 'sample':
        sample(seed, int(sys.argv[3]))
    elif cmd == 'run':
        run(seed, sys.argv[3])
    elif cmd == 'shadow':
        shadow(seed, sys.argv[3])
