"""Referee for archive-container codecs (VOL archives and similar). Claude-owned: GLM must not edit it.

usage: python3 arcref.py <target_dir> <lane_dir> [--files A,B] [-v]     score the lane's codec.py
       python3 arcref.py <target_dir> <lane_dir> --audit <out_dir>       write a text listing for the audit

Contract for <lane_dir>/codec.py (runs in a bwrap jail: no network, no files except its own tempdir):
  python3 codec.py unpack in.bin out/   -> out/manifest.json + one file per archive entry
      manifest.json = {"entries": [{"name": "Misc\\GLENW.PCX", "file": "e0000.bin"}, ...], "meta": {... small ...}}
      "name" is the entry's full path inside the archive as stored (directory parts joined with a backslash);
      each entry file holds exactly that entry's bytes.
  python3 codec.py pack out/ in.bin     -> rebuilds the archive from out/ alone, for ANY entry sizes.
Per file the referee checks: unpack ok; pack(unpack(x)) == x byte for byte; entries cover >= 95% of the file;
at least min_entries entries (files.json, counted from the directory); every entry's base name occurs in the file; typed entries carry their magic (PCX 0x0A, WAV RIFF, BMP BM);
resizing one entry and deleting another survives pack+unpack with every other entry unchanged.
<target_dir>/files.json = {"primary": [abs paths], "secondary": [abs paths], "audit": [abs paths]}.
"""
import sys, os, json, stat, shutil, subprocess, tempfile

MAX_CODEC = 120_000
MAX_ENTRIES = 100_000
TIMEOUT = 900
MAGIC = {'PCX': (b'\x0a',), 'WAV': (b'RIFF',), 'BMP': (b'BM',)}


def fail(msg):
    raise ValueError(msg)


def safe_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode): fail(f'{os.path.basename(path)}: not a regular file')
        if st.st_size > limit: fail(f'{os.path.basename(path)}: {st.st_size} bytes exceeds limit {limit}')
        chunks = []
        while True:
            b = os.read(fd, 1 << 20)
            if not b: break
            chunks.append(b)
        return b''.join(chunks)
    finally:
        os.close(fd)


def jail(codec, workdir, args):
    st = os.lstat(codec)
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CODEC:
        fail(f'codec.py must be a regular file under {MAX_CODEC} bytes')
    shutil.copyfile(codec, f'{workdir}/codec.py', follow_symlinks=False)
    cmd = ['bwrap', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
           '--symlink', 'usr/bin', '/bin', '--proc', '/proc', '--dev', '/dev', '--bind', workdir, '/w', '--chdir', '/w',
           '--unshare-all', '--die-with-parent', '--clearenv', '--setenv', 'PATH', '/usr/bin',
           '/usr/bin/prlimit', '--fsize=268435456', '--as=6442450944', '--',
           '/usr/bin/python3', '-I', 'codec.py'] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode: fail(f'codec.py {args[0]} exit {r.returncode}: {r.stderr.strip()[-400:]}')
    return r


def load_entries(outdir, insize):
    names = os.listdir(outdir)
    man = json.loads(safe_read(f'{outdir}/manifest.json', 64_000 + insize // 100))
    ents = man.get('entries')
    if not isinstance(ents, list) or not ents: fail('manifest has no entries')
    if len(ents) > MAX_ENTRIES: fail('too many entries')
    files = [e.get('file') for e in ents]
    if len(set(files)) != len(files): fail('entry files not unique')
    extra = set(names) - {'manifest.json'} - set(files)
    if extra: fail(f'out/ holds files not listed as entries: {sorted(extra)[:5]}')
    data = []
    for e in ents:
        n, fn = e.get('name'), e.get('file')
        if not (isinstance(n, str) and n and all(32 <= ord(c) < 127 for c in n)): fail(f'bad entry name {n!r}')
        if not isinstance(fn, str) or '/' in fn or fn.startswith('.') or fn == 'manifest.json': fail(f'bad file {fn!r}')
        data.append(safe_read(f'{outdir}/{fn}', 64 << 20))
    return man, data


def unpack(codec, td, tag, blob):
    w = f'{td}/{tag}'; os.mkdir(w); os.mkdir(f'{w}/out')
    with open(f'{w}/in.bin', 'wb') as fh: fh.write(blob)
    jail(codec, w, ['unpack', 'in.bin', 'out'])
    return load_entries(f'{w}/out', len(blob))


def pack(codec, td, tag, man, data):
    w = f'{td}/{tag}'; os.mkdir(w); os.mkdir(f'{w}/out')
    with open(f'{w}/out/manifest.json', 'w') as fh: json.dump(man, fh)
    for e, d in zip(man['entries'], data):
        with open(f'{w}/out/{e["file"]}', 'wb') as fh: fh.write(d)
    jail(codec, w, ['pack', 'out', 'packed.bin'])
    return safe_read(f'{w}/packed.bin', 256 << 20)


def check_file(codec, path, verbose, min_entries=1):
    src = safe_read(path, 64 << 20)
    res = {'file': os.path.basename(path), 'size': len(src)}
    with tempfile.TemporaryDirectory(prefix='arcref') as td:
        man, data = unpack(codec, td, 'a', src)
        names = [e['name'] for e in man['entries']]
        res['entries'] = len(data)
        res['coverage'] = round(sum(map(len, data)) / len(src), 3)
        res['names_unique'] = len(set(n.lower() for n in names)) == len(names)
        res['names_in_file'] = all(n.split('\\')[-1].encode() in src for n in names)
        typed = [(n, d) for n, d in zip(names, data) if n.rsplit('.', 1)[-1].upper() in MAGIC]
        good = sum(1 for n, d in typed if any(d.startswith(m) for m in MAGIC[n.rsplit('.', 1)[-1].upper()]))
        res['magic'] = f'{good}/{len(typed)}'
        rebuilt = pack(codec, td, 'b', man, data)
        res['roundtrip'] = rebuilt == src
        if not res['roundtrip'] and verbose:
            i = next((i for i in range(min(len(src), len(rebuilt))) if src[i] != rebuilt[i]), min(len(src), len(rebuilt)))
            print(f'  {res["file"]}: first diff at byte {i} (orig {len(src)}, rebuilt {len(rebuilt)})')
        # edit: grow the largest entry by 1037 bytes, delete the smallest (if >= 2 entries), then compare
        k = max(range(len(data)), key=lambda i: len(data[i]))
        new_k = data[k] + bytes((i * 7) & 0xff for i in range(1037))
        drop = min((i for i in range(len(data)) if i != k), key=lambda i: len(data[i]), default=None)
        keep = [i for i in range(len(data)) if i != drop]
        man2 = dict(man); man2['entries'] = [man['entries'][i] for i in keep]
        data2 = [new_k if i == k else data[i] for i in keep]
        edited = pack(codec, td, 'c', man2, data2)
        man3, data3 = unpack(codec, td, 'd', edited)
        res['edit'] = ([e['name'] for e in man3['entries']] == [e['name'] for e in man2['entries']] and data3 == data2)
    res['ok'] = (res['roundtrip'] and res['edit'] and res['coverage'] >= 0.95 and res['names_unique'] and len(data) >= min_entries
                 and res['names_in_file'] and good == len(typed))
    return res


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/codec.py'
    if '--audit' in sys.argv:
        out = sys.argv[sys.argv.index('--audit') + 1]; os.makedirs(out, exist_ok=True)
        for path in cfg['audit']:
            src = safe_read(path, 64 << 20)
            with tempfile.TemporaryDirectory(prefix='arcref') as td:
                man, data = unpack(codec, td, 'a', src)
            print(f'== {os.path.basename(path)}: {len(data)} entries')
            for e, d in list(zip(man['entries'], data))[:400]:
                print(f'{e["name"]:<40} {len(d):>9}  {d[:16].hex()}')
        return
    paths = cfg['primary'] + cfg.get('secondary', [])
    if '--files' in sys.argv:
        want = sys.argv[sys.argv.index('--files') + 1].split(',')
        paths = [p for p in paths if os.path.basename(p) in want]
    ok_all = True
    for path in paths:
        try:
            r = check_file(codec, path, '-v' in sys.argv, cfg.get('min_entries', {}).get(os.path.basename(path), 1))
        except Exception as e:
            r = {'file': os.path.basename(path), 'ok': False, 'error': str(e)[:300]}
        gating = path in cfg['primary']
        if gating and not r['ok']: ok_all = False
        print(('  ' if gating else '  (secondary) ') + json.dumps(r))
    full = '--files' not in sys.argv
    print('PASS' if ok_all and full else ('FAIL' if not ok_all else 'PARTIAL (subset; the driver scores all files)'))
    sys.exit(0 if ok_all and full else 1)


if __name__ == '__main__':
    main()
