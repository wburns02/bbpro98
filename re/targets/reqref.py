"""Referee for the shell UI layout files MENU.REQ / DIAL.REQ (requesters = screens and dialogs, gadgets = controls).
Claude-owned: GLM must not edit it.

usage: python3 reqref.py <target_dir> <lane_dir> [-v]         score <lane>/req.py on the visible files
       python3 reqref.py <target_dir> <lane_dir> --holdout     synthetic files built from the real requesters
       python3 reqref.py <target_dir> <lane_dir> --audit X     text summary of each decode for the audit

Container (verified by Claude 2026-10-07 on all 114 requesters of both files):
  "IDX:" u32 (4 + 4n) | u32 n | u32 idx[n]          idx[0] = first requester, idx[k] = requester k-1 + 8
  n-1 requesters, back to back:  "REQ:" u32 (0x80000000 | len) {
      "REQ:" u32 hlen  header: u16 id, s16 x, y, w, h, then requester fields and the title
      "GAD:" u32 glen  u16 count, then count gadget records:
          u8 type, u8 class, u16 id, s16 x, y, w, h (y can be negative), then class 4: 12 more bytes + a NUL-terminated label;
          class 1 / 2: 14 more bytes; class 8: 16 more bytes }
  then the tail bytes (a single NUL in the shipped files), kept as is.

Contract for <lane>/req.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 req.py decode in.bin out.json
      {"requesters": [{"index": i, "id": .., "x": .., "y": .., "w": .., "h": .., ...named header fields...,
                       "gadgets": [{"id": .., "x": .., "y": .., "w": .., "h": .., "label": "..." (class 4 only),
                                    ...named fields...}, ...]}, ...], ...any other keys...}
      List order is file order. Keys starting with "_" are DERIVED (lengths, counts, offsets) and recomputed by the
      encoder; every other leaf is content.
  python3 req.py encode in.bin edited.json out.bin
      rebuilds the whole file from edited.json (gadgets may be added, removed or edited, labels may change length);
      encode(x, decode(x)) == x.
Checks: schema against the trusted parse; every printable string of the requester headers is in the decoded content; byte-dump
budget and generic-name cap; round trip; edits checked by the trusted parser (move a requester, move/resize a gadget,
relabel a gadget, add a copy of a gadget with a new id, delete a gadget); the output must be the canonical layout.
Holdout: the same checks on synthetic files built from the real requesters of both files (shuffled, mixed, resized,
relabelled, perturbed).
"""
import sys, os, json, struct, tempfile, random, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read

MAX_CODEC = 300_000
TIMEOUT = 120
FIXED = {1: 26, 2: 26, 4: 24, 8: 28}
GENERIC = re.compile(r'^(f|w|b|c|v|word|byte|col|field|unk|unknown|val|value|s|data|item|entry|x|u|param|arg|p)_?[0-9a-f]+$', re.I)
HEXLIKE = re.compile(r'^[0-9a-fA-F]{33,}$|^[A-Za-z0-9+/=]{48,}$')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
PRINT = re.compile(rb'[\x20-\x7e]{4,}\x00')
isint = lambda v: isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------- trusted parser / builder

def parse_gadgets(d, a, b):
    if b - a < 2: fail('trusted parse: GAD section too short')
    n = struct.unpack_from('<H', d, a)[0]; p = a + 2; recs = []
    for _ in range(n):
        if p + 12 > b: fail('trusted parse: gadget runs past its section')
        cls = d[p + 1]
        if cls not in FIXED: fail(f'trusted parse: unknown gadget class {cls} at {p}')
        q = p + FIXED[cls]
        if cls == 4:
            e = d.find(b'\0', q, b)
            if e < 0: fail('trusted parse: unterminated gadget label')
            q = e + 1
        if q > b: fail('trusted parse: gadget runs past its section')
        recs.append(bytes(d[p:q])); p = q
    if p != b: fail(f'trusted parse: GAD section has {b - p} bytes after {n} gadgets')
    return recs


def parse(d):
    if len(d) < 12 or d[:4] != b'IDX:': fail('trusted parse: no IDX header')
    ln, n = struct.unpack_from('<II', d, 4)
    if ln != 4 + 4 * n or 12 + 4 * n > len(d): fail('trusted parse: bad IDX length')
    idx = struct.unpack_from('<%dI' % n, d, 12)
    a = 12 + 4 * n; reqs = []; tops = []
    while a + 8 <= len(d) and d[a:a + 4] == b'REQ:':
        L = struct.unpack_from('<I', d, a + 4)[0]
        if not L >> 31: fail(f'trusted parse: requester at {a} is not a container')
        L &= 0x7fffffff; end = a + 8 + L
        if end > len(d) or d[a + 8:a + 12] != b'REQ:': fail(f'trusted parse: bad requester at {a}')
        hl = struct.unpack_from('<I', d, a + 12)[0]; g = a + 16 + hl
        if hl < 10 or g + 8 > end or d[g:g + 4] != b'GAD:': fail(f'trusted parse: bad requester header at {a}')
        gl = struct.unpack_from('<I', d, g + 4)[0]
        if g + 8 + gl != end: fail(f'trusted parse: GAD length mismatch at {a}')
        reqs.append((bytes(d[a + 16:g]), parse_gadgets(d, g + 8, end))); tops.append(a); a = end
    if not reqs: fail('trusted parse: no requesters')
    want = [tops[0]] + [t + 8 for t in tops]
    if list(idx) != want: fail('trusted parse: IDX table does not match the requesters')
    return reqs, bytes(d[a:])


def build(reqs, tail):
    blocks = []
    for hdr, recs in reqs:
        gad = struct.pack('<H', len(recs)) + b''.join(recs)
        body = b'REQ:' + struct.pack('<I', len(hdr)) + hdr + b'GAD:' + struct.pack('<I', len(gad)) + gad
        blocks.append(b'REQ:' + struct.pack('<I', 0x80000000 | len(body)) + body)
    n = len(blocks) + 1; a = 12 + 4 * n; tops = []
    for b in blocks: tops.append(a); a += len(b)
    idx = [tops[0]] + [t + 8 for t in tops]
    return b'IDX:' + struct.pack('<II', 4 + 4 * n, n) + struct.pack('<%dI' % n, *idx) + b''.join(blocks) + tail


def g_fields(rec):
    t, cls = rec[0], rec[1]
    gid, x, y, w, h = struct.unpack_from('<H4h', rec, 2)
    lab = rec[24:-1].decode('latin1') if cls == 4 else None
    return gid, x, y, w, h, lab


def g_set(rec, gid=None, x=None, y=None, w=None, h=None, lab=None):
    r = bytearray(rec)
    for off, v in ((2, gid), (4, x), (6, y), (8, w), (10, h)):
        if v is not None: struct.pack_into('<H' if off == 2 else '<h', r, off, v)
    if lab is not None: r = r[:24] + lab.encode('latin1') + b'\0'
    return bytes(r)


def r_set(hdr, x=None, y=None):
    h = bytearray(hdr)
    if x is not None: struct.pack_into('<h', h, 2, x)
    if y is not None: struct.pack_into('<h', h, 4, y)
    return bytes(h)


# ---------------------------------------------------------------- jail

def run(codec, args, files, out, limit):
    with tempfile.TemporaryDirectory(prefix='reqref') as td:
        for n, data in files.items():
            with open(f'{td}/{n}', 'wb' if isinstance(data, bytes) else 'w') as fh:
                fh.write(data) if isinstance(data, bytes) else json.dump(data, fh)
        J.jail(codec, td, args, name='req.py', max_size=MAX_CODEC, timeout=TIMEOUT)
        return J.read_file(td, out, limit)


def decode(codec, blob):
    return json.loads(run(codec, ['decode', 'in.bin', 'out.json'], {'in.bin': blob}, 'out.json', 64 << 20))


def encode(codec, blob, doc):
    return run(codec, ['encode', 'in.bin', 'edited.json', 'out.bin'], {'in.bin': blob, 'edited.json': doc},
               'out.bin', 4 * len(blob) + (1 << 20))


# ---------------------------------------------------------------- validation

def content(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            if not (isinstance(k, str) and k.startswith('_')): yield from content(v, path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from content(v, path + (i,))
    else:
        yield path, x


def keys_of(x, out):
    if isinstance(x, dict):
        for k, v in x.items(): out.add(k); keys_of(v, out)
    elif isinstance(x, list):
        for v in x: keys_of(v, out)
    return out


def dumps_budget(x):
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


def validate(blob, doc, truth):
    reqs, _ = truth
    if not isinstance(doc, dict) or not isinstance(doc.get('requesters'), list): fail('decode output has no "requesters" list')
    R = doc['requesters']
    if len(R) != len(reqs): fail(f'{len(R)} requesters, file has {len(reqs)}')
    for i, (r, (hdr, recs)) in enumerate(zip(R, reqs)):
        if not isinstance(r, dict) or r.get('index') != i or not isinstance(r.get('gadgets'), list):
            fail(f'requester {i}: needs "index" == {i} and a "gadgets" list')
        want = dict(zip(('id', 'x', 'y', 'w', 'h'), struct.unpack_from('<H4h', hdr, 0)))
        for k, v in want.items():
            if r.get(k) != v: fail(f'requester {i}: "{k}" is {r.get(k)!r}, file has {v}')
        if len(r['gadgets']) != len(recs): fail(f'requester {i}: {len(r["gadgets"])} gadgets, file has {len(recs)}')
        for k, (g, rec) in enumerate(zip(r['gadgets'], recs)):
            if not isinstance(g, dict): fail(f'requester {i} gadget {k}: not an object')
            gid, x, y, w, h, lab = g_fields(rec)
            for key, v in (('id', gid), ('x', x), ('y', y), ('w', w), ('h', h)):
                if g.get(key) != v: fail(f'requester {i} gadget {k}: "{key}" is {g.get(key)!r}, file has {v}')
            if lab is not None and g.get('label') != lab:
                fail(f'requester {i} gadget {k}: "label" is {g.get("label")!r}, file has {lab!r}')
    strs = [v for _, v in content(doc) if isinstance(v, str)]
    allstr = '\x00'.join(strs)
    found = [m.group()[:-1].decode('latin1') for hdr, _ in reqs for m in PRINT.finditer(hdr)]
    missing = [s for s in found if s not in allstr]
    if missing: fail(f'{len(missing)} strings of the file are not in the decoded content, e.g. {missing[:3]}')
    d = dumps_budget(doc)
    if d > 0.25 * len(blob): fail(f'{d} bytes are kept as raw byte lists/hex strings (budget {len(blob) // 4})')
    ks = keys_of(doc, set())
    lazy = [k for k in ks if isinstance(k, str) and (GENERIC.match(k.lstrip('_')) or not k.strip())]
    if len(lazy) > 0.25 * max(1, len(ks)) and len(lazy) > 2:
        fail(f'{len(lazy)}/{len(ks)} distinct keys are generic, e.g. {sorted(lazy)[:5]}')


def expect(codec, blob, ed, want_reqs, tail, what):
    out = encode(codec, blob, ed)
    got = parse(out)
    if got[0] != want_reqs:
        bad = next((i for i, (a, b) in enumerate(zip(got[0], want_reqs)) if a != b), min(len(got[0]), len(want_reqs)))
        fail(f'{what}: the trusted parser shows a different file (first difference in requester {bad})')
    if out != build(want_reqs, tail): fail(f'{what}: output is not the canonical layout')
    back = decode(codec, out)
    validate(out, back, got)
    if encode(codec, out, back) != out: fail(f'{what}: decode/encode not stable on the edited file')
    return out


def edit_tests(codec, blob, doc, truth, seed):
    rnd = random.Random(seed)
    reqs, tail = truth
    R = [list(r) for r in reqs]
    has = [i for i, (_, recs) in enumerate(reqs) if len(recs) >= 2]
    labelled = [(i, k) for i, (_, recs) in enumerate(reqs) for k, rec in enumerate(recs) if rec[1] == 4]
    if len(has) < 2 or not labelled: fail('need requesters with gadgets for the edit tests')
    cp = lambda: json.loads(json.dumps(doc))
    # 1. move one requester and move/resize one gadget of another
    i, j = rnd.sample(has, 2); k = rnd.randrange(len(reqs[j][1]))
    ed = cp(); r = ed['requesters'][i]; r['x'] += 5; r['y'] += 4
    g = ed['requesters'][j]['gadgets'][k]; g['x'] += 7; g['y'] += 3; g['w'] += 2; g['h'] += 1
    want = [(h, list(rs)) for h, rs in reqs]
    hx, hy = struct.unpack_from('<hh', reqs[i][0], 2); want[i] = (r_set(want[i][0], hx + 5, hy + 4), want[i][1])
    gid, x, y, w, h, _ = g_fields(reqs[j][1][k]); want[j][1][k] = g_set(reqs[j][1][k], None, x + 7, y + 3, w + 2, h + 1)
    out = expect(codec, blob, ed, want, tail, 'move')
    if len(out) != len(blob): fail('move: file length changed')
    # 2. relabel two gadgets (longer and shorter)
    picks = rnd.sample(labelled, min(2, len(labelled)))
    ed = cp(); want = [(h, list(rs)) for h, rs in reqs]
    for n, (i, k) in enumerate(picks):
        lab = g_fields(reqs[i][1][k])[5]; new = (lab + ' Qz') if n == 0 else lab[:max(0, len(lab) // 2)]
        ed['requesters'][i]['gadgets'][k]['label'] = new; want[i][1][k] = g_set(want[i][1][k], lab=new)
    expect(codec, blob, ed, want, tail, 'relabel')
    # 3. add a copy of a labelled gadget (new id, moved, new label) to one requester, delete a gadget of another
    i, k = rnd.choice(labelled); s = rnd.choice([x for x in has if x != i])
    ed = cp(); want = [(h, list(rs)) for h, rs in reqs]
    nid = max(g_fields(rec)[0] for rec in reqs[i][1]) + 1
    g = json.loads(json.dumps(ed['requesters'][i]['gadgets'][k])); g['id'] = nid; g['x'] += 10; g['label'] = 'Added Qz'
    for key in [key for key in g if isinstance(key, str) and key.startswith('_')]: del g[key]
    ed['requesters'][i]['gadgets'].append(g)
    _, x, _, _, _, _ = g_fields(reqs[i][1][k]); want[i][1].append(g_set(reqs[i][1][k], nid, x + 10, lab='Added Qz'))
    d = rnd.randrange(len(reqs[s][1])); del ed['requesters'][s]['gadgets'][d]; del want[s][1][d]
    expect(codec, blob, ed, want, tail, 'add/delete')


def synth(pool, seed):
    """A valid REQ file from real requesters (both files mixed), shuffled and perturbed by the trusted builder."""
    rnd = random.Random(seed)
    reqs = rnd.sample(pool, rnd.randint(12, min(40, len(pool))))
    out = []
    for hdr, recs in reqs:
        recs = list(recs)
        hdr = r_set(hdr, *(min(600, v + rnd.randint(0, 9)) for v in struct.unpack_from('<hh', hdr, 2)))
        for k in range(len(recs)):
            gid, x, y, w, h, lab = g_fields(recs[k])
            recs[k] = g_set(recs[k], None, x + rnd.randint(0, 5), y + rnd.randint(0, 5), w, h + rnd.randint(0, 2),
                            None if lab is None or rnd.random() < 0.6 else (lab[::-1] if rnd.random() < 0.5 else lab + ' Hx'))
        if len(recs) > 2 and rnd.random() < 0.4: del recs[rnd.randrange(len(recs))]
        if recs and rnd.random() < 0.4: recs.append(recs[rnd.randrange(len(recs))])
        out.append((hdr, recs))
    return build(out, b'\0' if seed % 2 else b'')


def check(codec, blob, seed, edits=True):
    truth = parse(blob)
    doc = decode(codec, blob)
    validate(blob, doc, truth)
    if encode(codec, blob, doc) != blob: fail('encode(decode(x)) != x')
    if edits: edit_tests(codec, blob, doc, truth, seed)
    return len(truth[0])


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/req.py'
    blobs = {n: safe_read(f'{cfg["dir"]}/{n}', 4 << 20) for n in cfg['files']}
    if '--audit' in sys.argv:
        for name, blob in blobs.items():
            doc = decode(codec, blob)
            print(f'== {name}: top-level keys {list(doc)[:20]}')
            for r in doc.get('requesters', [])[:3]:
                print(' requester:', json.dumps({k: v for k, v in r.items() if k != 'gadgets'})[:900])
                for g in r.get('gadgets', [])[:4]: print('   gadget:', json.dumps(g)[:500])
            print(' other keys:', json.dumps({k: v for k, v in doc.items() if k != 'requesters'})[:1500])
        return
    hold = '--holdout' in sys.argv
    if hold:
        pool = [r for b in blobs.values() for r in parse(b)[0]]
        base = random.SystemRandom().randrange(1 << 30)   # unpredictable: this file is readable by the lanes
        cases = [(f'synth{s}', synth(pool, base + s), base + s) for s in range(4)]
    else:
        cases = [(n, b, 17 + i) for i, (n, b) in enumerate(blobs.items())]
    ok_all, results = True, []
    for name, data, seed in cases:
        try:
            n = check(codec, data, seed)
            results.append(dict(file=name, ok=True, **({} if J.QUIET else {'requesters': n})))
        except Exception as e:
            ok_all = False
            results.append(dict(file=name, ok=False, **({} if J.QUIET else {'error': J.err(e)})))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
