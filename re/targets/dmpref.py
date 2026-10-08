"""Referee for the motion-path file DMP.DAT (BBSIM dmp.cpp / FastSim FDMP.cpp). Claude-owned: GLM must not edit it.

usage: python3 dmpref.py <target_dir> <lane_dir> [-v]         score <lane>/dmp.py on the visible file
       python3 dmpref.py <target_dir> <lane_dir> --holdout     synthetic held-out files (shuffled/resized paths)
       python3 dmpref.py <target_dir> <lane_dir> --audit X     text summary of one decode for the audit

Container (verified by Claude 2026-10-07): u16 n | u32 offsets[n+1] (absolute, last = file length) | n paths.
Path: u16 frames, u16 h1, u16 h2, then frames x 62 bytes (31 s16). The game reads each path into a 0xf86-byte slot
(at most 64 frames) and rejects a file whose n differs from the count it expects (66).

Contract for <lane>/dmp.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 dmp.py decode in.bin out.json
      {"paths": [{"index": i, ...named header fields..., "frames": [{...named frame fields...}, ...]}, ...  n paths],
       ...any other keys...}
      Integer leaves of a path outside "index" and "frames", in key order (depth first), equal h1, h2.
      Integer leaves of a frame, in key order (depth first), equal its 31 s16 words.
  python3 dmp.py encode in.bin edited.json out.bin
      rebuilds the whole file from edited.json (paths may gain or lose frames); encode(x, decode(x)) == x.
Checks: schema and leaf fidelity; at most 25% generic key names (f12, w3, joint7_x is fine only if joints are not
all numbered); round trip; edit test (one frame value +5 changes exactly that s16); resize test (append a frame to
one path, drop a frame from another) read back by the trusted parser with every other path unchanged.
Holdout: the same checks on synthetic files built from the real paths (shuffled order, resized paths, perturbed values).
"""
import sys, os, json, struct, tempfile, random, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read

MAX_CODEC = 200_000
TIMEOUT = 120
FRAME = 62; NW = 31; MAXF = 64
GENERIC = re.compile(r'^(f|w|v|x\d|c|word|col|field|unk|unknown|val|value|s|h|data|joint|j|p|pt|point)_?\d+$', re.I)
isint = lambda v: isinstance(v, int) and not isinstance(v, bool)


def parse(d):
    if len(d) < 6: fail('file too short')
    n = struct.unpack_from('<H', d, 0)[0]
    offs = struct.unpack_from('<%dI' % (n + 1), d, 2)
    if offs[0] != 2 + 4 * (n + 1) or offs[-1] != len(d): fail('trusted parse: bad offset table')
    paths = []
    for i in range(n):
        a, b = offs[i], offs[i + 1]
        cnt, h1, h2 = struct.unpack_from('<3H', d, a)
        if b - a != 6 + FRAME * cnt or cnt > MAXF: fail(f'trusted parse: path {i} size {b - a} != 6 + 62 x {cnt}')
        paths.append((h1, h2, [struct.unpack_from('<%dh' % NW, d, a + 6 + FRAME * k) for k in range(cnt)]))
    return paths


def build(paths):
    body = [struct.pack('<3H', len(fr), h1, h2) + b''.join(struct.pack('<%dh' % NW, *f) for f in fr) for h1, h2, fr in paths]
    offs = [2 + 4 * (len(paths) + 1)]
    for b in body: offs.append(offs[-1] + len(b))
    return struct.pack('<H', len(paths)) + struct.pack('<%dI' % len(offs), *offs) + b''.join(body)


def leaves(x, out):
    if isint(x): out.append(x)
    elif isinstance(x, dict):
        for v in x.values(): leaves(v, out)
    elif isinstance(x, list):
        for v in x: leaves(v, out)
    elif x is not None and not isinstance(x, (str, float, bool)): fail(f'unexpected value {str(x)[:80]}')
    return out


def keys_of(x, out):
    if isinstance(x, dict):
        for k, v in x.items(): out.append(k); keys_of(v, out)
    elif isinstance(x, list):
        for v in x: keys_of(v, out)
    return out


def validate(doc, truth):
    if not isinstance(doc, dict) or not isinstance(doc.get('paths'), list): fail('decode output has no "paths" list')
    if len(doc['paths']) != len(truth): fail(f'{len(doc["paths"])} paths, file has {len(truth)}')
    for i, (p, (h1, h2, fr)) in enumerate(zip(doc['paths'], truth)):
        if not isinstance(p, dict) or p.get('index') != i or not isinstance(p.get('frames'), list):
            fail(f'path {i}: needs "index" == {i} and a "frames" list')
        hv = leaves({k: v for k, v in p.items() if k not in ('index', 'frames')}, [])
        if hv != [h1, h2]: fail(f'path {i}: header leaves {hv[:6]} != [{h1}, {h2}]')
        if len(p['frames']) != len(fr): fail(f'path {i}: {len(p["frames"])} frames, file has {len(fr)}')
        for k, (f, want) in enumerate(zip(p['frames'], fr)):
            if not isinstance(f, dict): fail(f'path {i} frame {k}: not an object')
            got = leaves(f, [])
            if got != list(want): fail(f'path {i} frame {k}: leaves differ from the 31 s16 words')
    ks = keys_of(doc, [])
    distinct = set(ks)
    lazy = [k for k in distinct if GENERIC.match(k) or not k.strip()]
    if len(lazy) > 0.25 * max(1, len(distinct)): fail(f'{len(lazy)}/{len(distinct)} distinct keys are generic, e.g. {sorted(lazy)[:5]}')


def run(codec, args, files, out=None, limit=1 << 22):
    with tempfile.TemporaryDirectory(prefix='dmpref') as td:
        for n, data in files.items():
            with open(f'{td}/{n}', 'wb' if isinstance(data, bytes) else 'w') as fh:
                fh.write(data) if isinstance(data, bytes) else json.dump(data, fh)
        J.jail(codec, td, args, name='dmp.py', max_size=MAX_CODEC, timeout=TIMEOUT)
        return J.read_file(td, out, limit)


def decode(codec, blob):
    return json.loads(run(codec, ['decode', 'in.bin', 'out.json'], {'in.bin': blob}, 'out.json', 64 << 20))


def encode(codec, blob, doc):
    return run(codec, ['encode', 'in.bin', 'edited.json', 'out.bin'], {'in.bin': blob, 'edited.json': doc}, 'out.bin')


def first_leaf_path(f):
    """(container, key) of the first integer leaf of a frame object."""
    if isinstance(f, dict):
        for k, v in f.items():
            if isint(v): return f, k
            if isinstance(v, (dict, list)):
                r = first_leaf_path(v)
                if r: return r
    elif isinstance(f, list):
        for k, v in enumerate(f):
            if isint(v): return f, k
            if isinstance(v, (dict, list)):
                r = first_leaf_path(v)
                if r: return r
    return None


def check_file(codec, blob, edit=True, seed=0):
    truth = parse(blob)
    doc = decode(codec, blob)
    validate(doc, truth)
    if encode(codec, blob, doc) != blob: fail('encode(decode(x)) != x')
    if not edit: return len(truth)
    rnd = random.Random(seed)
    big = [i for i, (_, _, fr) in enumerate(truth) if 2 <= len(fr) < MAXF]
    if len(big) < 2: fail('need two paths with frames for the edit tests')
    # value edit
    i = rnd.choice(big); k = rnd.randrange(len(truth[i][2]))
    ed = json.loads(json.dumps(doc))
    c, key = first_leaf_path(ed['paths'][i]['frames'][k]); c[key] += 5
    out = encode(codec, blob, ed)
    if len(out) != len(blob): fail('edit: file length changed')
    diff = [j for j in range(len(blob)) if blob[j] != out[j]]
    t1 = parse(out)
    want = [list(p) for p in truth]; want[i] = (truth[i][0], truth[i][1], [list(f) for f in truth[i][2]])
    want[i][2][k][0] += 5
    if [(a, b, [list(f) for f in fr]) for a, b, fr in t1] != [(a, b, [list(f) for f in fr]) for a, b, fr in want]:
        fail('edit: the trusted parser does not show exactly the edited value')
    if len(diff) > 2: fail(f'edit: {len(diff)} bytes changed, expected <= 2')
    # resize: append a copy of the last frame (first leaf +1) to path a, drop the first frame of path b
    a, b = rnd.sample(big, 2)
    ed = json.loads(json.dumps(doc))
    nf = json.loads(json.dumps(ed['paths'][a]['frames'][-1])); c, key = first_leaf_path(nf); c[key] += 1
    ed['paths'][a]['frames'].append(nf); del ed['paths'][b]['frames'][0]
    out = encode(codec, blob, ed)
    t2 = parse(out)
    exp = [(h1, h2, [list(f) for f in fr]) for h1, h2, fr in truth]
    last = list(exp[a][2][-1]); last[0] += 1; exp[a][2].append(last); exp[b] = (exp[b][0], exp[b][1], exp[b][2][1:])
    if [(h1, h2, [list(f) for f in fr]) for h1, h2, fr in t2] != exp: fail('resize: trusted parse differs from the edit')
    if out != build([(h1, h2, [tuple(f) for f in fr]) for h1, h2, fr in exp]): fail('resize: file is not the canonical layout')
    validate(decode(codec, out), t2)
    return len(truth)


def synth(blob, seed):
    rnd = random.Random(seed)
    paths = [(h1, h2, [list(f) for f in fr]) for h1, h2, fr in parse(blob)]
    rnd.shuffle(paths)
    out = []
    for h1, h2, fr in paths:
        fr = [[max(-32768, min(32767, v + rnd.randint(-3, 3))) for v in f] for f in fr]
        if fr and rnd.random() < 0.3 and len(fr) < MAXF: fr.append(list(fr[-1]))
        if len(fr) > 1 and rnd.random() < 0.3: fr.pop(0)
        out.append((h1, h2, fr))
    if seed % 2: out = out[:rnd.randint(10, len(out))]
    return build(out)


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/dmp.py'
    blob = safe_read(cfg['file'], 1 << 22)
    if '--audit' in sys.argv:
        doc = decode(codec, blob)
        print('top-level keys:', list(doc)[:30])
        for p in doc.get('paths', [])[:3]:
            print(' path:', json.dumps({k: v for k, v in p.items() if k != 'frames'})[:800])
            for f in p.get('frames', [])[:2]: print('   frame:', json.dumps(f)[:1200])
        print(' other keys:', json.dumps({k: v for k, v in doc.items() if k != 'paths'})[:3000])
        return
    hold = '--holdout' in sys.argv
    ok_all, results = True, []
    base = random.SystemRandom().randrange(1 << 30)   # unpredictable: this file is readable by the lanes
    cases = [(f'synth{s}', synth(blob, base + s), base + s) for s in range(4)] if hold else [('DMP.DAT', blob, 7)]
    for name, data, seed in cases:
        try:
            n = check_file(codec, data, True, seed)
            results.append(dict(file=name, ok=True, **({} if J.QUIET else {'paths': n})))
        except Exception as e:
            ok_all = False
            results.append(dict(file=name, ok=False, **({} if J.QUIET else {'error': J.err(e)})))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
