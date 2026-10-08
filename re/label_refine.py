#!/usr/bin/env python3
"""Second labeling pass + merge (M1-M3). usage: label_refine.py BINARY [workers] [--merge-only]

Merges index/B/_labels_det.tsv (module + evidence from asserts, FID names, propagation) and _labels_glm.tsv (first GLM
pass) into one label per function, then re-asks GLM-Flash (Hive) for every weak one: subsystem missing or UNKNOWN,
evidence PATTERN_GUESS / UNKNOWN / malformed, or a TINY det row. Each weak function goes with its body and the current
labels of its callers and callees, so the second pass can use what the first pass learned about the neighbours.
Batches are cached in re/glm/B/refine/ (resumable). Writes index/B/_functions_labeled.tsv:
addr, name, subsystem, evidence, short_name, comment, source (det | glm | refine).
"""
import collections, csv, os, re, sys, time, concurrent.futures as cf, importlib.machinery, importlib.util

B = sys.argv[1]
W = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 6
MERGE_ONLY = '--merge-only' in sys.argv
D = f'/mnt/nvme/bbpro98/index/{B}/'
C = f'/mnt/nvme/bbpro98/re/glm/{B}/refine/'
os.makedirs(C, exist_ok=True)

SUB = ('CRT MATH IO_FILE IO_REGISTRY STRUCT_INIT SIM_PITCH SIM_SWING SIM_FIELD SIM_BASE SIM_INJURY SIM_FATIGUE '
       'SIM_LINEUP SIM_GAME SIM_STATS SIM_UMPIRE SIM_AI RATING SEASON UI_MAIN UI_STATS UI_LINEUP UI_DIALOG UI_RENDER '
       'GDI WIN32 MFC_LIB AUDIO ANIM CAMERA STUB UTIL UNKNOWN').split()
EVID = ('CONFIRMED', 'STRING_XREF', 'XREF_CONFIDENT', 'PATTERN_GUESS', 'UNKNOWN')
STRONG = ('CONFIRMED', 'STRING_XREF', 'XREF_CONFIDENT')
EV_FIX = {'XCONF': 'XREF_CONFIDENT', 'XCONFIDENT': 'XREF_CONFIDENT', 'XREF_CONFident': 'XREF_CONFIDENT',
          'STRING_Xref': 'STRING_XREF', 'STRING_XRF': 'STRING_XREF'}
DET_EV = {'FID_NAME': 'CONFIRMED', 'SRC_ASSERT': 'STRING_XREF', 'PROPAGATED': 'XREF_CONFIDENT', 'SIZE': 'PATTERN_GUESS'}
# source module (from assert paths) -> subsystem; FastSim's F-prefixed 8.3 names map to the same modules
MOD_SUB = {
    'Act': 'SIM_FIELD', 'Cover': 'SIM_FIELD', 'Field': 'SIM_FIELD', 'Fielder': 'SIM_FIELD', 'Throw': 'SIM_FIELD',
    'Tag': 'SIM_FIELD', 'Catcher': 'SIM_FIELD', 'Ball': 'SIM_FIELD', 'Projecti': 'SIM_FIELD', 'Selected': 'SIM_FIELD',
    'Runner': 'SIM_BASE', 'Runners2': 'SIM_BASE', 'Batter2d': 'SIM_SWING', 'Bpi': 'UI_LINEUP', 'Arcade': 'SIM_GAME',
    'Game': 'SIM_GAME', 'Gameset': 'SIM_GAME', 'Event': 'SIM_GAME', 'Events': 'SIM_GAME', 'Status': 'SIM_GAME',
    'Realism': 'SIM_GAME', 'precip': 'SIM_GAME', 'Earnedr': 'SIM_STATS', 'Escore': 'SIM_STATS', 'Injury': 'SIM_INJURY',
    'Roster': 'SIM_LINEUP', 'Players2': 'SIM_LINEUP', 'Player': 'SIM_LINEUP', 'Person': 'STRUCT_INIT',
    'Actor': 'STRUCT_INIT', 'Umpire': 'SIM_UMPIRE', 'Umpires2': 'SIM_UMPIRE', 'Cams': 'CAMERA', 'Vcr': 'CAMERA',
    'Dbm': 'ANIM', 'Anim': 'ANIM', 'Hranim': 'ANIM', 'Hrbackgr': 'ANIM', 'dmp': 'ANIM', 'Sync': 'ANIM',
    'Smodel': 'UI_RENDER', 'Scorebrd': 'UI_RENDER', 'Stadium': 'UI_RENDER', 'Sound': 'AUDIO'}
F83 = {'FGAME': 'Game', 'FRUNNER': 'Runner', 'FARCADE': 'Arcade', 'fbattr2d': 'Batter2d', 'FROSTER': 'Roster',
       'FCAMS': 'Cams', 'FTHROW': 'Throw', 'FDBM': 'Dbm', 'FSYNC': 'Sync', 'FEARNEDR': 'Earnedr', 'FGAMESET': 'Gameset',
       'FACT': 'Act', 'FFIELDER': 'Fielder', 'FFIELD': 'Field', 'FEVENT': 'Event', 'FSMODEL': 'Smodel',
       'FRUNNRS2': 'Runners2', 'FHRANIM': 'Hranim', 'FEVENTS': 'Events', 'FTAG': 'Tag', 'FINJURY': 'Injury',
       'FBALL': 'Ball', 'FANIM': 'Anim', 'FPLAYRS2': 'Players2', 'FDMP': 'dmp', 'FSELECTD': 'Selected',
       'FCOVER': 'Cover', 'FUMPIRS2': 'Umpires2', 'FESCORE': 'Escore', 'FUMPIRE': 'Umpire', 'FSCORBRD': 'Scorebrd',
       'FREALISM': 'Realism', 'FPROJCTI': 'Projecti', 'FCATCHER': 'Catcher', 'FSTADIUM': 'Stadium',
       'FPLAYER': 'Player', 'FPERSON': 'Person', 'FACTOR': 'Actor'}


def det_subsystem(module):
    if module == 'MFC_LIB':
        return 'MFC_LIB'
    if module in ('Utility_Vblock', 'Utility_Decoder'):
        return 'UTIL'  # memory block allocator, LZ decoder
    if module == 'Utility_Sfx':
        return 'AUDIO'
    if module.startswith(('Utility_', 'Fps_ct_')):
        return 'IO_FILE'
    if module.startswith(('Graphics_', 'TSpace_')):
        return 'UI_RENDER'
    m = module.split('_', 1)[1] if '_' in module else module
    return MOD_SUB.get(F83.get(m, m))


def rows(path):
    return [r for r in csv.reader(open(path, errors='replace'), delimiter='\t')][1:]


funcs = {r[0]: r for r in rows(D + '_functions.tsv')}
det = {r[0]: r for r in rows(D + '_labels_det.tsv')}
glm = {}
for r in rows(D + '_labels_glm.tsv') if os.path.exists(D + '_labels_glm.tsv') else []:
    if r and r[0] in funcs:
        glm[r[0]] = r


FID = re.compile(r'Splitter|IsTracking|MiniDock|ControlBar|FrameWnd|CWnd|CDialog|_AFX|Afx[A-Z]|OnClose|StackedTabs|'
                 r'CPropertySheet|CView|CDocument|CWinApp|COleDispatch', re.I)

# No binary links MFC (no MFC4x import, no AfxWinMain): the det pass put every non-FUN_ name under MFC_LIB, which mixes
# CRT routines Ghidra's FID recognised, the DLLs' own exports (cfgGetInt, palSetColor, RunSim, c-tree ISAM ...) and
# MFC names falsely matched onto game code. Sort the names; the false matches carry no evidence (spot checks 2/3).
CRT_NAME = re.compile(r"^(FID_conflict:)?(_?\$E\d*|`(scalar|vector)_deleting_destructor'|`eh_vector_\w+'|"
                      r"`vector_constructor_iterator'|__ArrayUnwind|entry|__CRT_INIT@\d*|__onexit|_atexit|"
                      r"__setdefaultprecision|_strncpy|setSBCS|__setmbcp|__setenvp|__setargv|___sbh_\w+|__NMSG_WRITE|"
                      r"__nh_malloc|_malloc|_free|__ioterm|__ioinit|__initterm|___initmbctable|__heap_\w+|getSystemCP|"
                      r"__FF_MSGBANNER|__exit|doexit|___crt\w+|_CPtoLCID|__cinit|__cexit|__callnewh|__amsg_exit|delbuf|"
                      r"parse_cmdline|~messages_base|~strstreambuf|~_Timevec)$")
CTREE_NAMES = set('CLISAM INTISAM OPNISAM CREDAT CREIFIL CREIDX OPNIFIL OPNFIL DELFIL CLSFIL CLIFIL ADDREC EQLREC GTEREC '
                  'GETFIL RWTREC DELREC FRSREC NXTREC LSTREC PRVREC FRSSET LSTSET NXTSET PRVSET BATSET ADDRES GETRES '
                  'DELRES AVLFILNUM LKISAM TFRMKEY DATENT RRDREC REDREC WRTREC NEWREC RBLSUP RBLIFIL'.split())
EXPORT_SUB = [(re.compile(r'^cfg[A-Z]'), 'IO_REGISTRY'), (re.compile(r'^pal[A-Z_]'), 'GDI'), (re.compile(r'^wpl[A-Z]'), 'WIN32'),
              (re.compile(r'^(GetText\w+|ReallyCreateFont|CreateMatchingFont|GetAverageCharWidth)$'), 'GDI'),
              (re.compile(r'^(implode|explode|crc|crc32)$'), 'UTIL'), (re.compile(r'^Run[A-Z]'), 'UI_MAIN'),
              (re.compile(r'^DllMain$'), 'WIN32')]


def name_sub(n):
    if CRT_NAME.match(n):
        return 'CRT'
    if n in CTREE_NAMES:
        return 'IO_FILE'
    for r, s in EXPORT_SUB:
        if r.match(n):
            return s


def nc(name, comment):
    """GLM sometimes swaps the short_name and comment columns"""
    if ' ' in name and re.fullmatch(r'[a-z0-9_]+', comment):
        return comment, name
    return name, comment


def first_label(a):
    """(subsystem, evidence, short_name, comment, source) from det or the first GLM pass; None fields when unusable."""
    d = det.get(a)
    if d and d[3] == 'FID_NAME' and d[2] == 'MFC_LIB':
        s = name_sub(funcs[a][1])
        if s:
            return s, 'CONFIRMED', '', f'name {funcs[a][1]}', 'det'
        d = None
    if d and d[3] and d[2] != 'TINY':
        sub = det_subsystem(d[2])
        if sub:
            return sub, DET_EV.get(d[3], 'PATTERN_GUESS'), '', f'module {d[2]}', 'det'
    g = glm.get(a)
    if g and len(g) >= 5:
        sub, ev = g[1].strip(), EV_FIX.get(g[2].strip(), g[2].strip())
        if sub in SUB and ev in EVID:
            return (sub, ev) + nc(g[3].strip(), g[4].strip()) + ('glm',)
    return None, None, '', '', 'none'


cur = {a: first_label(a) for a in funcs}

text = open(D + '_all.c', errors='replace').read()
body = {p.split()[0]: p for p in re.split(r'^// ==== ', text, flags=re.M)[1:]}
# a body that is only "return;" / "return <const>;" (vtable slots and dead code, mostly no xrefs) is a STUB: the
# decompile itself is the evidence, nothing for GLM to guess
STUB_RE = re.compile(r'\n\{\s*return(\s+(-?(0x)?[0-9a-f]+|\(\w+\)\s*-?(0x)?[0-9a-f]+))?;\s*\}\s*$', re.I)
for a in funcs:
    m = STUB_RE.search(body.get(a, ''))
    if m:
        cur[a] = ('STUB', 'CONFIRMED', 'stub' if not m.group(1) else 'return_const',
                  'body is only ' + ('return' if not m.group(1) else 'return ' + m.group(2)), 'det')




def weak(a):
    sub, ev, name, comment, src = cur[a]
    return bool(sub in (None, 'UNKNOWN') or ev not in STRONG or (src == 'glm' and FID.search(name + ' ' + comment)))


ref_cache = {}
for f in sorted(os.listdir(C)):
    for l in open(C + f, errors='replace'):
        p = [x.strip() for x in l.rstrip('\n').split('\t')]
        if len(p) >= 5 and p[0] in funcs and p[1] in SUB and EV_FIX.get(p[2], p[2]) in EVID:
            ref_cache[p[0]] = (p[1], EV_FIX.get(p[2], p[2])) + nc(p[3], p[4]) + ('refine',)


def better(new, old):
    rank = {e: i for i, e in enumerate(EVID)}
    if old[0] in (None, 'UNKNOWN'):
        return new[0] != 'UNKNOWN' or old[0] is None
    return new[0] != 'UNKNOWN' and rank[new[1]] < rank.get(old[1], 9)


for a, lab in ref_cache.items():
    if cur[a][0] != 'STUB' and better(lab, cur[a]):
        cur[a] = lab

if not MERGE_ONLY:
    ld = importlib.machinery.SourceFileLoader('cc', '/home/will/bin/cloud-code')
    sp = importlib.util.spec_from_loader('cc', ld)
    cc = importlib.util.module_from_spec(sp)
    ld.exec_module(cc)
    key = cc.load_hive_key()
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

    def ctx(a):
        f = funcs[a]

        def lab(x):
            s = cur.get(x)
            if not s or not s[0]:
                return f'{x} ?'
            nm = funcs[x][1] if not funcs[x][1].startswith('FUN_') else ''
            return f'{x} {s[0]}{" " + s[2] if s[2] else ""}{" " + nm if nm else ""}'
        callers = [c for c in f[3].split(',') if c in funcs][:8]
        callees = [c for c in f[4].split(',') if c in funcs][:10]
        b = '\n'.join(body.get(a, a).split('\n')[:70])[:3500]
        return (f'// callers: {"; ".join(map(lab, callers)) or "none"}\n// callees: '
                f'{"; ".join(map(lab, callees)) or "none"}\n// ==== {b}')

    todo = [a for a in funcs if weak(a) and a not in ref_cache]
    N = 20
    batches = [todo[i:i + N] for i in range(0, len(todo), N)]
    print(B, 'weak', sum(map(weak, funcs)), 'todo', len(todo), 'batches', len(batches), flush=True)

    def run(i):
        f = C + f'r{i:04d}_{batches[i][0]}.tsv'
        if os.path.exists(f):
            return 0
        user = '\n\n'.join(ctx(a) for a in batches[i])
        for att in range(3):
            try:
                out, u = cc.call_hive(key, 'z-ai/glm-5.3-flash', SYS, user, temperature=0.1, max_tokens=24000,
                                      timeout_s=600)
                ok = [l for l in out.splitlines() if l.count('\t') >= 4 and l.split('\t')[0].strip() in batches[i]]
                if len(ok) >= len(batches[i]) * 0.8:
                    open(f, 'w').write('\n'.join(ok) + '\n')
                    return len(ok)
            except Exception:
                time.sleep(5)
        return -1

    with cf.ThreadPoolExecutor(W) as ex:
        res = list(ex.map(run, range(len(batches))))
    print(B, 'failed batches', sum(1 for r in res if r < 0), flush=True)
    os.execv(sys.executable, [sys.executable, __file__, B, '--merge-only'])

# residual pass for what is still UNKNOWN: take the subsystem of the callers (unanimous = XREF_CONFIDENT, majority =
# PATTERN_GUESS), repeated until nothing changes; a small helper whose callers give no majority is UTIL (PATTERN_GUESS)
callers = {a: re.findall(r'[0-9a-f]{8}', (re.search(r'callers=\[([^\]]*)\]', body.get(a, '').split('\n', 1)[0]) or
                                         re.match('', '')).group(1) or '') for a in funcs}
changed = True
while changed:
    changed = False
    for a in funcs:
        if cur[a][0] not in (None, 'UNKNOWN'):
            continue
        subs = collections.Counter(cur[c][0] for c in callers[a]
                                   if c in cur and cur[c][0] not in (None, 'UNKNOWN', 'STUB', 'UTIL'))
        if subs:
            top, k = subs.most_common(1)[0]
            if k * 2 > sum(subs.values()):
                ev = 'XREF_CONFIDENT' if k == sum(subs.values()) else 'PATTERN_GUESS'
                cur[a] = (top, ev, cur[a][2], f'callers: {dict(subs)}; ' + cur[a][3], 'callers')
                changed = True
for a in funcs:
    if cur[a][0] in (None, 'UNKNOWN') and body.get(a, '').count('\n') <= 40:
        cur[a] = ('UTIL', 'PATTERN_GUESS', cur[a][2], 'small helper, callers give no majority subsystem; ' + cur[a][3], 'callers')

# c-tree ISAM calls (the game's database, Faircom c-tree) are file I/O, not registry/config: GLM put its wrappers
# under IO_REGISTRY throughout (spot check seed 1)
CTREE_RE = re.compile(r'\b(CLISAM|INTISAM|OPNISAM|CREDAT|CREIFIL|CREIDX|OPNIFIL|OPNFIL|DELFIL|CLSFIL|CLIFIL|ADDREC|'
                      r'EQLREC|GTEREC|GETFIL|RWTREC|DELREC|FRSREC|NXTREC|LSTREC|PRVREC|FRSSET|LSTSET|NXTSET|PRVSET|'
                      r'BATSET|ADDRES|GETRES|DELRES|AVLFILNUM|LKISAM|TFRMKEY|DATENT|RRDREC|REDREC|WRTREC|NEWREC)\(')
for a in funcs:
    if cur[a][0] == 'IO_REGISTRY' and CTREE_RE.search(body.get(a, '')):
        cur[a] = ('IO_FILE', 'STRING_XREF', cur[a][2], 'c-tree ISAM call; ' + cur[a][3], cur[a][4])
ctree = {a for a in funcs if cur[a][3].startswith('c-tree ISAM call')}
for a in funcs:
    if cur[a][0] == 'IO_REGISTRY' and set(funcs[a][4].split(',')) & ctree:
        cur[a] = ('IO_FILE', 'XREF_CONFIDENT', cur[a][2], 'wraps a c-tree ISAM call; ' + cur[a][3], cur[a][4])

# neighbour post-pass (spot checks 2/3, 2026-10-08): the WRONG rows were wrappers labelled apart from what they wrap,
# ctor/dtor/operator-new helpers under CRT/MFC_LIB, IO_REGISTRY on code with no registry/INI call, and MFC_LIB (no
# binary links MFC, so GLM's MFC_LIB is always a false match)
GENERIC = (None, 'UNKNOWN', 'STUB', 'UTIL', 'CRT', 'MFC_LIB')
size = {a: int(funcs[a][2]) if funcs[a][2].isdigit() else 0 for a in funcs}
callee = {a: [c for c in dict.fromkeys(funcs[a][4].split(',')) if c in funcs and c != a] for a in funcs}
caller = {a: [c for c in dict.fromkeys(funcs[a][3].split(',')) if c in funcs and c != a] for a in funcs}
pinned = lambda a: cur[a][4] == 'det' and cur[a][1] in ('CONFIRMED', 'STRING_XREF')
# a label from the function's source module (assert path, or propagated between asserts of one .cpp) beats a guess
# from its neighbours (spot check seed 8: FFIELD and Game functions re-voted to SIM_GAME / CRT)
modpin = lambda a: cur[a][4] == 'det' and cur[a][0] not in GENERIC and orig[a].startswith('module ')
REG_RE = re.compile(r'\b(Reg[A-Z]\w*|\w*PrivateProfile\w*|GetProfile\w*|WriteProfile\w*|cfg[A-Z]\w*)\(')


def votes(xs):
    return collections.Counter(cur[c][0] for c in xs if cur[c][0] not in GENERIC)


def top(cnt):
    m = cnt.most_common(2)
    if m and (len(m) == 1 or m[0][1] > m[1][1]):
        return m[0][0], 'XREF_CONFIDENT' if len(cnt) == 1 else 'PATTERN_GUESS'
    return None, None


orig = {a: cur[a][3] for a in funcs}


def setl(a, sub, ev, why):
    cur[a] = (sub, ev, cur[a][2], why + '; ' + orig[a], 'post')


for a in funcs:
    nm = cur[a][2]
    if pinned(a) or not nm:
        continue
    if re.search(r'op(erator)?_?(new|delete)|checked_(new|delete|free)|^(new|delete)(_l?\d+)?$', nm):
        setl(a, 'CRT', 'XREF_CONFIDENT', 'operator new/delete helper')
    elif re.search(r'ctor|dtor|destructor|constructor', nm) and cur[a][0] in ('CRT', 'MFC_LIB'):
        s, ev = top(votes(callee[a]))
        setl(a, s or 'STRUCT_INIT', ev or 'PATTERN_GUESS', 'object ctor/dtor')

# a small body whose only calls are C library routines is CRT when it registers an atexit handler or sits between CRT
# functions; a game function that only memsets or strcats keeps its label (spot check seed 8)
order = sorted(funcs, key=lambda x: int(x, 16))
nbr = {a: (order[i - 1] if i else None, order[i + 1] if i + 1 < len(order) else None) for i, a in enumerate(order)}
CRT_CALLS = set('_atexit atexit memmove memcpy memset memcmp strcpy strncpy strlen strcat strncat strcmp strncmp _strcmpi '
                '_stricmp _strnicmp strchr strrchr strstr free malloc calloc realloc _free _malloc operator_new '
                'operator_delete'.split())
CALL_RE = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
for a in funcs:
    if pinned(a) or cur[a][0] == 'CRT' or size[a] > 128:
        continue
    b = body.get(a, '').split('{', 1)[-1]
    calls = {c for c in CALL_RE.findall(b) if c not in ('if', 'while', 'for', 'switch', 'return', 'sizeof')}
    if calls and calls <= CRT_CALLS and not modpin(a) and (
            calls & {'_atexit', 'atexit'} or all(n and cur[n][0] == 'CRT' for n in nbr[a])):
        setl(a, 'CRT', 'STRING_XREF', 'only calls ' + ','.join(sorted(calls)))

for a in funcs:
    # c-tree ISAM calls in a small body: the function is file I/O whatever module it sits in
    if not pinned(a) and cur[a][0] != 'IO_FILE' and size[a] <= 200 and CTREE_RE.search(body.get(a, '')):
        setl(a, 'IO_FILE', 'STRING_XREF', 'c-tree ISAM call')
    # IO_REGISTRY with no registry/INI call in the body, among file-I/O neighbours, is IO_FILE
    elif cur[a][0] == 'IO_REGISTRY' and not pinned(a) and not REG_RE.search(body.get(a, '')):
        v = votes(callee[a] + caller[a])
        if v and v.most_common(1)[0][0] == 'IO_FILE' and 'IO_REGISTRY' not in v:
            setl(a, 'IO_FILE', 'XREF_CONFIDENT', f'no registry call, neighbours {dict(v)}')

# GDI must rest on a real GDI/WinG/palette call somewhere down its callees: GLM put the Upstats/FastSim record-object
# family (realize_resource, validate_handle, gdi_obj_dtor) under GDI on the name alone
GDI_API = re.compile(r'\b(WinG\w+|\w*BitBlt|\w*DIB\w*|CreateCompatible\w+|DeleteObject|SelectObject|\w*Palette\w*|'
                     r'CreateFont\w*|GetTextMetrics\w*|GetTextExtent\w*|TextOut\w*|GetDeviceCaps|GetDC|ReleaseDC|'
                     r'CreateSolidBrush|CreatePen|pal[A-Z]\w*|GetStockObject|SetTextColor|SetBkColor|SetBkMode)\b')
grounded = {a for a in funcs if cur[a][0] == 'GDI' and (cur[a][3].startswith('name ') or GDI_API.search(body.get(a, '')))}
grow = True
while grow:
    grow = False
    for a in funcs:
        if a not in grounded and cur[a][0] == 'GDI' and set(callee[a]) & grounded:
            grounded.add(a)
            grow = True
for a in funcs:
    if cur[a][0] == 'GDI' and a not in grounded and not pinned(a):
        v = collections.Counter(cur[c][0] for c in callee[a] + caller[a] if cur[c][0] not in GENERIC + ('GDI',))
        sub, ev = top(v)
        setl(a, sub or ('STRUCT_INIT' if re.search('ctor|dtor', cur[a][2]) else 'UTIL'), ev or 'PATTERN_GUESS',
             'no GDI call below it' + (f', neighbours {dict(v)}' if v else ''))

# WIN32 likewise must rest on an imported API call (a called name that is not one of the binary's own functions);
# a small body that only calls imports takes the subsystem of those imports; an SEH-frame-only funclet is CRT
INTERNAL = {funcs[x][1] for x in funcs}
HELPER = re.compile(r'^(CONCAT\d+|SUB\d+|ZEXT\d+|SEXT\d+|CARRY\d|SCARRY\d|SBORROW\d|POPCOUNT|LOCK|UNLOCK|halt\w*)$')
KW = ('if', 'while', 'for', 'switch', 'return', 'sizeof')


def calls_of(a):
    return {c for c in CALL_RE.findall(body.get(a, '').split('{', 1)[-1]) if c not in KW and not HELPER.match(c)}


GAME_EXPORTS = set()
for X in ('FPS_Ctrl', 'FPS_CT', 'FPS_DCL', 'FPS_Pal', 'BBCfg', 'IC_Cfg', 'ODASL'):
    if os.path.exists(f'/mnt/nvme/bbpro98/index/{X}/_functions.tsv'):
        GAME_EXPORTS |= {r[1] for r in rows(f'/mnt/nvme/bbpro98/index/{X}/_functions.tsv') if not r[1].startswith('FUN_')}


def api_sub(names):
    if any(n.startswith('FID_conflict') for n in names):
        return None
    if names & CTREE_NAMES:
        return 'IO_FILE'
    subs = {name_sub(n) for n in names}
    if len(subs) == 1 and None not in subs:
        return subs.pop()
    if 'Iostream_init' in names:
        return 'CRT'
    if names & GAME_EXPORTS:
        return None
    if all(GDI_API.fullmatch(n) for n in names):
        return 'GDI'
    if all(re.match(r'Reg[A-Z]|\w*PrivateProfile', n) for n in names):
        return 'IO_REGISTRY'
    if all(re.search(r'File|Directory|_l?open|_l?read|_l?write|_l?close|_lseek', n) for n in names):
        return 'IO_FILE'
    if all(n[0].isupper() for n in names):
        return 'WIN32'


grounded = {a for a in funcs if cur[a][0] == 'WIN32' and (cur[a][3].startswith('name ') or
                                                          any(c[0].isupper() for c in calls_of(a) - INTERNAL))}
grow = True
while grow:
    grow = False
    for a in funcs:
        if a not in grounded and cur[a][0] == 'WIN32' and set(callee[a]) & grounded:
            grounded.add(a)
            grow = True
for a in funcs:
    if pinned(a):
        continue
    cs = calls_of(a)
    if not cs and size[a] <= 32 and 'unaff_FS_OFFSET' in body.get(a, '') and cur[a][0] != 'CRT':
        setl(a, 'CRT', 'STRING_XREF', 'SEH frame restore only')
    elif (cs and size[a] <= 96 and not cs & INTERNAL and cur[a][0] != (api_sub(cs) or cur[a][0])
          and not (api_sub(cs) == 'WIN32' and cur[a][0].startswith('UI_'))):
        setl(a, api_sub(cs), 'STRING_XREF', 'only calls ' + ','.join(sorted(cs)))
    elif cur[a][0] == 'WIN32' and a not in grounded:
        v = collections.Counter(cur[c][0] for c in callee[a] + caller[a] if cur[c][0] not in GENERIC + ('WIN32',))
        sub, ev = top(v)
        setl(a, sub or 'UTIL', ev or 'PATTERN_GUESS', 'no Win32 call below it' + (f', neighbours {dict(v)}' if v else ''))

changed, rounds = True, 0
while changed and rounds < 10:
    changed, rounds = False, rounds + 1
    for a in funcs:
        if pinned(a) or modpin(a):
            continue
        ce = [c for c in callee[a] if cur[c][0] not in (None, 'UNKNOWN', 'STUB')]
        s = {cur[c][0] for c in ce}
        new = None
        # small wrapper: takes the subsystem its callees unanimously share; a wrapper of CRT takes its callers' unanimous
        # subsystem, or CRT itself when it has no callers (static init), else UTIL
        if size[a] <= 64 and 1 <= len(callee[a]) <= 3 and len(s) == 1 and len(ce) == len(callee[a]):
            sub = s.pop()
            eh = all(re.search(r'eh_|unwind|_eh_vector|seh', cur[c][2] + funcs[c][1], re.I) for c in ce)
            if sub == 'CRT' and eh:
                pass  # compiler-generated EH unwind funclet: CRT, not its parent's subsystem (seed 100 split on these)
            elif sub in ('UTIL', 'MFC_LIB', 'CRT'):
                cs = votes(caller[a])
                if not caller[a]:
                    sub = 'CRT' if sub == 'CRT' else 'UTIL'  # vtable-only thunks over UTIL stay UTIL
                elif len(cs) == 1:
                    sub = next(iter(cs))
                elif sub == 'CRT' and cur[a][0] not in GENERIC:
                    sub = cur[a][0]  # a game getter over strcpy keeps its own label (spot check seed 11)
                elif sub != 'CRT':
                    sub = 'UTIL'
            new = (sub, 'XREF_CONFIDENT', 'wrapper of ' + cur[ce[0]][0])
        # a guessed label whose 2+ non-generic callees agree on another subsystem
        elif cur[a][1] in ('PATTERN_GUESS', 'UNKNOWN', None) or cur[a][4] == 'callers':
            v = votes(callee[a])
            if len(v) == 1 and sum(v.values()) >= 2:
                new = (next(iter(v)), 'XREF_CONFIDENT', f'callees {dict(v)}')
        # MFC_LIB is never right here: neighbour plurality, else UTIL
        if not new and cur[a][0] == 'MFC_LIB':
            sub, ev = top(votes(callee[a]) + votes(caller[a]))
            new = (sub, ev, 'MFC false match, neighbours') if sub else (
                'CRT' if ce and {cur[c][0] for c in ce} == {'CRT'} else 'UTIL', 'PATTERN_GUESS', 'MFC false match')
        if new and new[0] != cur[a][0]:
            setl(a, *new)
            changed = True

with open(D + '_functions_labeled.tsv', 'w') as o:
    o.write('addr\tname\tsubsystem\tevidence\tshort_name\tcomment\tsource\n')
    for a, f in funcs.items():
        s = cur[a]
        o.write('\t'.join([a, f[1], s[0] or 'UNKNOWN', s[1] or 'UNKNOWN', s[2], s[3].replace('\t', ' '), s[4]]) + '\n')
n = len(funcs)
unk = sum(1 for a in funcs if cur[a][0] in (None, 'UNKNOWN'))
strong = sum(1 for a in funcs if cur[a][1] in STRONG)
print(f'{B}: {n} functions, subsystem UNKNOWN {unk}, evidence XREF_CONFIDENT or better {strong} ({strong / n:.0%})')
