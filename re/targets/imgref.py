"""Referee for image-container codecs (DBM bitmap archives, shell graphics). Claude-owned: GLM must not edit it.

usage: python3 imgref.py <target_dir> <lane_dir> [--files A,B] [-v]      score the lane's codec.py
       python3 imgref.py <target_dir> <lane_dir> --audit <out_dir>         write contact sheets for the visual audit

Contract for <lane_dir>/codec.py (runs in a bwrap jail: no network, no files except its own tempdir):
  python3 codec.py decode in.bin out/   -> out/manifest.json + one raw file per frame
      manifest.json = {"palette": [[r,g,b] x 256] (optional), "frames": [{"w": int, "h": int, "file": "f0000.raw"}, ...],
                       "meta": {... small, free-form ...}}
      each frame file = exactly w*h bytes, one 8-bit palette index per pixel, row-major, top row first.
  python3 codec.py encode out/ in.bin   -> rebuilds the original container from out/ alone.
Per file the referee checks: decode ok; encode(decode(x)) == x byte for byte; an edit to one frame survives
encode+decode and changes nothing else; the frames look like pixel art (expansion and neighbour-equality floors);
out/ holds only manifest.json and the frame files, and manifest.json is small (no raw-byte smuggling).
The files and the PASS rule come from <target_dir>/files.json: {"dir": ..., "primary": [...], "secondary": [...]}.
PASS = every primary file passes every check. Secondary files must round-trip (reported, not gating).
"""
import sys, os, json, shutil, tempfile, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read

MAX_CODEC = 120_000          # bytes; a codec cannot carry the 28 MB of art inside itself
MAX_FRAMES = 200_000
TIMEOUT = 900


def jail(codec, workdir, args):
    return J.jail(codec, workdir, args, max_size=MAX_CODEC, timeout=TIMEOUT)


def load_frames(wd, insize):
    """Validate out/ and return (manifest, [bytes per frame])."""
    names = J.list_dir(wd, 'out')
    man = json.loads(J.read_file(wd, 'out/manifest.json', 64_000 + insize // 50))
    frames = man.get('frames')
    if not isinstance(frames, list) or not frames: fail('manifest has no frames')
    if len(frames) > MAX_FRAMES: fail('too many frames')
    want = {'manifest.json'} | {f.get('file') for f in frames}
    extra = set(names) - want
    if extra: fail(f'out/ holds files not listed as frames: {sorted(extra)[:5]}')
    data, total = [], 0
    for f in frames:
        w, h, fn = f.get('w'), f.get('h'), f.get('file')
        if not (isinstance(w, int) and isinstance(h, int) and 0 < w <= 4096 and 0 < h <= 4096):
            fail(f'bad frame size {w}x{h}')
        if not isinstance(fn, str) or '/' in fn or fn.startswith('.'): fail(f'bad frame file name {fn!r}')
        b = J.read_file(wd, f'out/{fn}', w * h)
        if len(b) != w * h: fail(f'{fn}: {len(b)} bytes, expected {w}x{h}={w * h}')
        data.append(b); total += len(b)
        if total > 64 * insize + (256 << 20): fail('decoded output implausibly large')
    pal = man.get('palette')
    if pal is not None and not (isinstance(pal, list) and len(pal) == 256 and all(
            isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c) for c in pal)):
        fail('palette must be 256 [r,g,b] triples')
    return man, data


def smooth(frames):
    """Fraction of horizontally adjacent equal pixels (sprite art is run-heavy, compressed bytes are not)."""
    eq = n = 0
    for (w, h), b in frames:
        for y in range(0, h, max(1, h // 64)):
            row = b[y * w:(y + 1) * w]
            eq += sum(1 for i in range(1, len(row)) if row[i] == row[i - 1]); n += max(0, len(row) - 1)
    return eq / n if n else 0.0


def check_file(codec, path, verbose):
    src = safe_read(path, 64 << 20)
    res = {'file': os.path.basename(path), 'size': len(src)}
    with tempfile.TemporaryDirectory(prefix='imgref') as td:
        a, b, c = f'{td}/a', f'{td}/b', f'{td}/c'
        for d in (a, b, c): os.mkdir(d)
        with open(f'{a}/in.bin', 'wb') as fh: fh.write(src)
        os.mkdir(f'{a}/out')
        jail(codec, a, ['decode', 'in.bin', 'out'])
        man, data = load_frames(a, len(src))
        dims = [(f['w'], f['h']) for f in man['frames']]
        res['frames'] = len(data)
        res['expansion'] = round(sum(map(len, data)) / len(src), 2)
        res['smooth'] = round(smooth(list(zip(dims, data))), 3)
        # round trip: encode sees only the manifest + frames, copied as plain files
        os.mkdir(f'{b}/out')
        with open(f'{b}/out/manifest.json', 'wb') as fh: fh.write(J.read_file(a, 'out/manifest.json', 64_000 + len(src) // 50))
        for f, d in zip(man['frames'], data):
            with open(f'{b}/out/{f["file"]}', 'wb') as fh: fh.write(d)
        shutil.copytree(f'{b}/out', f'{c}/out')
        jail(codec, b, ['encode', 'out', 'rebuilt.bin'])
        rebuilt = J.read_file(b, 'rebuilt.bin', 64 << 20)
        res['roundtrip'] = rebuilt == src
        if not res['roundtrip'] and verbose:
            i = next((i for i in range(min(len(src), len(rebuilt))) if src[i] != rebuilt[i]), min(len(src), len(rebuilt)))
            print(f'  {res["file"]}: first diff at byte {i} (orig {len(src)} bytes, rebuilt {len(rebuilt)})')
        # edit test: paint a block in the largest frame, encode, decode, compare every frame
        k = max(range(len(data)), key=lambda i: len(data[i]))
        w, h = dims[k]
        ed = bytearray(data[k]); val = (ed[(h // 2) * w + w // 2] + 1) % 256
        for y in range(h // 3, min(h, h // 3 + 4)):
            for x in range(w // 3, min(w, w // 3 + 4)): ed[y * w + x] = val
        with open(f'{c}/out/{man["frames"][k]["file"]}', 'wb') as fh: fh.write(bytes(ed))
        jail(codec, c, ['encode', 'out', 'edited.bin'])
        edited = J.read_file(c, 'edited.bin', 64 << 20)
        os.mkdir(f'{td}/d'); os.mkdir(f'{td}/d/out')
        with open(f'{td}/d/in.bin', 'wb') as fh: fh.write(edited)
        jail(codec, f'{td}/d', ['decode', 'in.bin', 'out'])
        _, data2 = load_frames(f'{td}/d', len(edited))
        res['edit'] = len(data2) == len(data) and data2[k] == bytes(ed) and all(
            data2[i] == data[i] for i in range(len(data)) if i != k)
    res['ok'] = res['roundtrip'] and res['edit'] and res['expansion'] >= 1.0 and res['smooth'] >= 0.35
    return res


def sheet(man, data, out_png, default_pal):
    """Contact sheet of up to 24 frames spread across the file, scaled to fit 1024 px wide."""
    from PIL import Image
    pal = man.get('palette') or default_pal
    flat = [v for c in pal for v in c]
    idx = sorted(set(int(i * (len(data) - 1) / 23) for i in range(24))) if len(data) > 24 else range(len(data))
    tiles = []
    for i in idx:
        f = man['frames'][i]
        im = Image.frombytes('P', (f['w'], f['h']), data[i]); im.putpalette(flat)
        im = im.convert('RGB'); im.thumbnail((240, 240))
        tiles.append(im)
    W, cols = 1024, 4
    rows = (len(tiles) + cols - 1) // cols
    canvas = Image.new('RGB', (W, rows * 250), (255, 0, 255))
    for n, im in enumerate(tiles):
        canvas.paste(im, ((n % cols) * 256 + 4, (n // cols) * 250 + 4))
    canvas.save(out_png)


def riff_pal(path):
    b = open(path, 'rb').read()
    i = b.find(b'data')
    if b[:4] == b'RIFF' and i > 0:
        n = int.from_bytes(b[i + 10:i + 12], 'little')
        return [list(b[i + 12 + 4 * k:i + 15 + 4 * k]) for k in range(min(n, 256))] + [[0, 0, 0]] * (256 - min(n, 256))
    return [[k, k, k] for k in range(256)]


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/codec.py'
    verbose = '-v' in sys.argv
    if '--audit' in sys.argv:
        out = sys.argv[sys.argv.index('--audit') + 1]; os.makedirs(out, exist_ok=True)
        default_pal = riff_pal(cfg['palette']) if cfg.get('palette') else [[k, k, k] for k in range(256)]
        for name in cfg['audit']:
            src = safe_read(f'{cfg["dir"]}/{name}', 64 << 20)
            with tempfile.TemporaryDirectory(prefix='imgref') as td:
                with open(f'{td}/in.bin', 'wb') as fh: fh.write(src)
                os.mkdir(f'{td}/out')
                jail(codec, td, ['decode', 'in.bin', 'out'])
                man, data = load_frames(td, len(src))
                sheet(man, data, f'{out}/{name}.png', default_pal)
            print(f'sheet {name}: {len(data)} frames')
        return
    names = cfg['primary'] + cfg.get('secondary', [])
    if '--files' in sys.argv:
        names = sys.argv[sys.argv.index('--files') + 1].split(',')
    ok_all = True
    for name in names:
        try:
            r = check_file(codec, f'{cfg["dir"]}/{name}', verbose)
        except Exception as e:
            r = {'file': name, 'ok': False, 'error': J.err(e)}
        gating = name in cfg['primary']
        if gating and not r['ok']: ok_all = False
        if not gating and not r.get('roundtrip'): pass  # reported only
        print(('  ' if gating else '  (secondary) ') + json.dumps(r))
    full = '--files' not in sys.argv
    print('PASS' if ok_all and full else ('FAIL' if not ok_all else 'PARTIAL (subset; the driver scores all files)'))
    sys.exit(0 if ok_all and full else 1)


if __name__ == '__main__':
    main()
