"""Referee for the DAT entries of the shell VOL archives (string tables, name generator, weather, menus, ...).
Claude-owned: GLM must not edit it.

usage: python3 voldatref.py <target_dir> <lane_dir> [-v]         score <lane>/voldat.py on the target's files
       python3 voldatref.py <target_dir> <lane_dir> --holdout     files.json "holdout" files if listed (else the same
                                                                   files), unseen random edits (more of them)
       python3 voldatref.py <target_dir> <lane_dir> --audit X     text summary of each decode for the audit

Contract for <lane>/voldat.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 voldat.py decode NAME in.bin out.json     NAME = the entry name, e.g. ASNEWS.DAT (pick the layout by it)
  python3 voldat.py encode NAME in.bin edited.json out.bin
      decode: any JSON object that names what the data is. Values under keys starting with "_" are DERIVED
      (counts, offsets, sizes, padding the encoder recomputes or needs for a lossless rebuild); every other leaf is
      CONTENT and must be editable.
      encode: rebuild the file from edited.json (in.bin may be read for nothing but preserving "_" data the JSON
      carries anyway); encode(x, decode(x)) == x byte for byte.
files.json: {"dir", "files", optional "holdout" (unseen files for --holdout), optional "coverage" (fnmatch patterns of
the files the coverage check applies to; default all)}.
Checks per file:
  - coverage: every run of >= 4 printable characters ending at a NUL in the file appears inside some decoded string
  - no byte dumps: int lists of > 8 items all within 0..255, hex/base64-like strings > 32 chars and control
    characters inside strings (derived "_" data included) count against a budget of 25% of the file size
  - at most 25% of the distinct keys are generic (f12, field3, unk7, ...)
  - round trip
  - edit test: K random content strings get "Qz" appended (they must then be stored in the file, verified by a
    trusted scan for the new bytes) and K random content ints that are not 0 get +1; the decode of the edited file must
    equal the edited JSON on every content leaf, and decoding then re-encoding it must be stable.
"""
import sys, os, json, tempfile, random, re, fnmatch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read

MAX_CODEC = 300_000
TIMEOUT = 120
GENERIC = re.compile(r'^(f|w|b|c|v|word|byte|col|field|unk|unknown|val|value|s|data|item|entry|x)_?[0-9a-f]+$', re.I)
HEXLIKE = re.compile(r'^[0-9a-fA-F]{33,}$|^[A-Za-z0-9+/=]{48,}$')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
PRINT = re.compile(rb'[\x20-\x7e]{4,}\x00')
isint = lambda v: isinstance(v, int) and not isinstance(v, bool)


def run(codec, args, files, out, limit):
    with tempfile.TemporaryDirectory(prefix='voldatref') as td:
        for n, data in files.items():
            with open(f'{td}/{n}', 'wb' if isinstance(data, bytes) else 'w') as fh:
                fh.write(data) if isinstance(data, bytes) else json.dump(data, fh)
        J.jail(codec, td, args, name='voldat.py', max_size=MAX_CODEC, timeout=TIMEOUT)
        return J.read_file(td, out, limit)


def decode(codec, name, blob):
    return json.loads(run(codec, ['decode', name, 'in.bin', 'out.json'], {'in.bin': blob}, 'out.json', 64 << 20))


def encode(codec, name, blob, doc):
    return run(codec, ['encode', name, 'in.bin', 'edited.json', 'out.bin'], {'in.bin': blob, 'edited.json': doc},
               'out.bin', 8 * len(blob) + (1 << 20))


def content(x, path=()):
    """Yield (path, value) for content leaves (keys starting with '_' are skipped)."""
    if isinstance(x, dict):
        for k, v in x.items():
            if not (isinstance(k, str) and k.startswith('_')): yield from content(v, path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from content(v, path + (i,))
    else:
        yield path, x


def get(doc, path):
    for p in path: doc = doc[p]
    return doc


def put(doc, path, v):
    for p in path[:-1]: doc = doc[p]
    doc[path[-1]] = v


def keys_of(x, out):
    if isinstance(x, dict):
        for k, v in x.items(): out.add(k); keys_of(v, out)
    elif isinstance(x, list):
        for v in x: keys_of(v, out)
    return out


def dumps_budget(x):
    """Bytes kept opaque anywhere in the JSON (derived "_" data included): int lists of > 8 items all within 0..255,
    hex/base64-like strings, control characters inside strings."""
    n = 0
    def walk(y):
        nonlocal n
        if isinstance(y, dict):
            for v in y.values(): walk(v)
        elif isinstance(y, list):
            if len(y) > 8 and all(isint(v) and 0 <= v <= 255 for v in y): n += len(y)
            else:
                for v in y: walk(v)
        elif isinstance(y, str):
            if HEXLIKE.match(y): n += len(y) // 2
            else: n += len(CTRL.findall(y))
    walk(x)
    return n


def validate(name, blob, doc, coverage=True):
    if not isinstance(doc, dict) or not doc: fail(f'{name}: decode output must be a non-empty JSON object')
    strs = [v for _, v in content(doc) if isinstance(v, str)]
    allstr = '\x00'.join(strs)
    missing = []
    for m in (PRINT.finditer(blob) if coverage else ()):
        s = m.group()[:-1].decode('latin1')
        if s not in allstr: missing.append(s)
    if missing: fail(f'{name}: {len(missing)} strings of the file are not in the decoded content, e.g. {missing[:3]}')
    d = dumps_budget(doc)
    if d > 0.25 * len(blob): fail(f'{name}: {d} bytes are kept as raw byte lists/hex strings (budget {len(blob) // 4})')
    ks = keys_of(doc, set())
    lazy = [k for k in ks if isinstance(k, str) and (GENERIC.match(k.lstrip('_')) or not k.strip())]
    if len(lazy) > 0.25 * max(1, len(ks)) and len(lazy) > 2:
        fail(f'{name}: {len(lazy)}/{len(ks)} distinct keys are generic, e.g. {sorted(lazy)[:5]}')


def edit_test(codec, name, blob, doc, seed, k):
    rnd = random.Random(seed)
    leaves = list(content(doc))
    strs = [(p, v) for p, v in leaves if isinstance(v, str) and len(v) >= 3 and v.isprintable()]
    ints = [(p, v) for p, v in leaves if isint(v) and 0 < v < 30000]
    if not strs and not ints: fail(f'{name}: no editable content leaves')
    ed = json.loads(json.dumps(doc))
    picks_s = rnd.sample(strs, min(k, len(strs))); picks_i = rnd.sample(ints, min(k, len(ints)))
    for p, v in picks_s: put(ed, p, v + 'Qz')
    for p, v in picks_i: put(ed, p, v + 1)
    out = encode(codec, name, blob, ed)
    for p, v in picks_s:
        if (v + 'Qz').encode('latin1') not in out: fail(f'{name}: edited string {v + "Qz"!r} is not stored in the file')
    back = decode(codec, name, out)
    for p, _ in picks_s + picks_i:
        try: got = get(back, p)
        except (KeyError, IndexError, TypeError): fail(f'{name}: edited leaf {list(p)} missing after re-decode')
        if got != get(ed, p): fail(f'{name}: leaf {list(p)} decodes as {got!r}, edited to {get(ed, p)!r}')
    want = dict(content(ed)); got = dict(content(back))
    if want != got:
        diff = [p for p in set(want) | set(got) if want.get(p) != got.get(p)]
        fail(f'{name}: {len(diff)} content leaves differ after the edit, e.g. {list(diff[0])}')
    if encode(codec, name, out, back) != out: fail(f'{name}: decode/encode not stable on the edited file')


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/voldat.py'
    if '--audit' in sys.argv:
        for name in cfg['files']:
            doc = decode(codec, name, safe_read(f'{cfg["dir"]}/{name}', 4 << 20))
            print(f'== {name}:', json.dumps(doc)[:1500])
        return
    hold = '--holdout' in sys.argv
    ok_all, results = True, []
    for i, name in enumerate(cfg.get('holdout', cfg['files']) if hold else cfg['files']):
        try:
            blob = safe_read(f'{cfg["dir"]}/{name}', 4 << 20)
            doc = decode(codec, name, blob)
            validate(name, blob, doc, any(fnmatch.fnmatch(name, p) for p in cfg.get('coverage', ['*'])))
            if encode(codec, name, blob, doc) != blob: fail(f'{name}: encode(decode(x)) != x')
            for r in range(3 if hold else 1):
                edit_test(codec, name, blob, doc, (9000 if hold else 100) + 31 * i + r, 6 if hold else 3)
            results.append(dict(file=name, ok=True))
        except Exception as e:
            ok_all = False
            results.append(dict(file=name, ok=False, **({} if J.QUIET else {'error': J.err(e)})))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
