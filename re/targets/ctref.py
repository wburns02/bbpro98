"""Referee for the c-tree Plus file codec (ASN, Stats DAT, .eos, SCHEDTMP). Claude-owned: GLM must not edit it.

usage: python3 ctref.py <target_dir> <lane_dir> [--files A,B] [-v]     score the lane's codec.py on the primary files
       python3 ctref.py <target_dir> <lane_dir> --holdout                same checks on files the lane never sees
       python3 ctref.py <target_dir> <lane_dir> --audit <out_dir>        text summary of a dump for the audit

Contract for <lane_dir>/codec.py (runs in a bwrap jail: no network, no files except its own tempdir). Mirrors the
c-tree API the game uses (FPS_CT.dll: RWTREC / ADDREC / DELREC), working on the original file:
  python3 codec.py dump in.bin out.json
      {"members": [{"name": str, "kind": "data" | "index" | "other", "data": <member idx, index members only>}, ...],
       "records": [{"m": member idx, "off": payload file offset, "len": payload bytes, "del": bool}, ...],
       "index":   [{"m": index member idx, "koff": file offset of the stored key bytes, "klen": int,
                    "rec": "off" of the record this entry points to}, ...]   # per index member, in key order
       "meta": {... small ...}}
  python3 codec.py apply in.bin edits.json out.bin
      edits = [{"op": "rewrite", "rec": off, "data": hex}, {"op": "add", "m": member idx, "data": hex},
               {"op": "delete", "rec": off}]   ("rec" = a record "off" from dump(in.bin); applied in list order)
      apply with [] must reproduce in.bin exactly. Edits must keep every index and the free space consistent.
Checks per file (identity of records is by content, so records may move):
  dump: every record's bytes are read from the file at the reported offset; records do not overlap; every FA FA
  record the referee's own scanner finds is reported; index entries' key bytes are read at "koff"; each index points
  only at active records of its data member, once each, in nondecreasing key order, and covers >= 98% of them.
  apply: [] is the identity; same-length rewrite, grown rewrite, add, delete and a combined edit list each produce a
  file whose dump passes the same checks and whose active records equal the expected multiset.
"""
import sys, os, json, stat, shutil, subprocess, tempfile, struct, collections

MAX_CODEC = 150_000
TIMEOUT = 900


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


def scan(d):
    """Independent FA FA variable-length record scanner (work/parse_stats.py): payload offsets and lengths."""
    out, i, n = [], 0, len(d)
    while i < n - 20:
        if d[i] == 0xfa and d[i + 1] == 0xfa:
            tot, pl = struct.unpack_from('<II', d, i + 2)
            if tot == pl + 18 and 0 < pl < 2000 and i + 18 + pl <= n:
                out.append((i + 18, pl)); i += 18 + pl; continue
        i += 1
    return out


class Ctx:
    def __init__(self, codec, td):
        self.codec, self.td, self.k = codec, td, 0

    def wdir(self):
        self.k += 1; w = f'{self.td}/w{self.k}'; os.mkdir(w); return w

    def dump(self, blob):
        w = self.wdir()
        with open(f'{w}/in.bin', 'wb') as fh: fh.write(blob)
        jail(self.codec, w, ['dump', 'in.bin', 'out.json'])
        return json.loads(safe_read(f'{w}/out.json', 40 * len(blob) + (4 << 20)))

    def apply(self, blob, edits):
        w = self.wdir()
        with open(f'{w}/in.bin', 'wb') as fh: fh.write(blob)
        with open(f'{w}/edits.json', 'w') as fh: json.dump(edits, fh)
        jail(self.codec, w, ['apply', 'in.bin', 'edits.json', 'out.bin'])
        return safe_read(f'{w}/out.bin', 4 * len(blob) + (16 << 20))


def check_dump(src, dm, need_scan=True):
    """Validate one dump against the raw bytes. Returns (active records as {off: (m, bytes)}, index stats)."""
    mem = dm.get('members'); recs = dm.get('records'); idx = dm.get('index')
    if not (isinstance(mem, list) and isinstance(recs, list) and isinstance(idx, list)): fail('dump lacks members/records/index')
    if not recs: fail('no records')
    n = len(src); spans = []; active = {}; allrec = {}
    for r in recs:
        m, off, ln, dl = r.get('m'), r.get('off'), r.get('len'), r.get('del')
        if not (isinstance(m, int) and 0 <= m < len(mem) and isinstance(off, int) and isinstance(ln, int)
                and isinstance(dl, bool) and 0 <= off and 0 < ln and off + ln <= n):
            fail(f'bad record {r}')
        spans.append((off, off + ln)); allrec[off] = (m, ln)
        if not dl: active[off] = (m, src[off:off + ln])
    spans.sort()
    for (a, b), (c, _) in zip(spans, spans[1:]):
        if c < b: fail(f'records overlap at {a}..{b} / {c}')
    if need_scan:
        sc = scan(src)
        missing = [(o, l) for o, l in sc if allrec.get(o, (None, None))[1] != l]
        if len(missing) > len(sc) // 200: fail(f'{len(missing)}/{len(sc)} scanner records not reported, e.g. {missing[:3]}')
    per = collections.defaultdict(list)
    for e in idx:
        m, ko, kl, rec = e.get('m'), e.get('koff'), e.get('klen'), e.get('rec')
        if not (isinstance(m, int) and 0 <= m < len(mem) and mem[m].get('kind') == 'index' and isinstance(ko, int)
                and isinstance(kl, int) and 0 < kl <= 512 and 0 <= ko and ko + kl <= n and isinstance(rec, int)):
            fail(f'bad index entry {e}')
        per[m].append((src[ko:ko + kl], rec))
    if not per: fail('no index entries')
    stats = {}
    for m, ents in per.items():
        dmi = mem[m].get('data')
        if not isinstance(dmi, int) or not (0 <= dmi < len(mem)) or mem[dmi].get('kind') != 'data':
            fail(f'index member {m} has no data member')
        targets = [r for _, r in ents]
        if len(set(targets)) != len(targets): fail(f'index {m} points at a record twice')
        for k, r in ents:
            if r not in active or active[r][0] != dmi: fail(f'index {m} points at {r}, not an active record of member {dmi}')
        keys = [k for k, _ in ents]
        if any(b < a for a, b in zip(keys, keys[1:])): fail(f'index {m} keys not in nondecreasing order')
        have = sum(1 for v in active.values() if v[0] == dmi)
        if len(ents) < 0.98 * have: fail(f'index {m} covers {len(ents)}/{have} active records of member {dmi}')
        stats[m] = len(ents)
    return active, stats


def multiset(active):
    return collections.Counter((m, b) for m, b in active.values())


def check_file(ctx, path, verbose):
    src = safe_read(path, 64 << 20)
    res = {'file': os.path.basename(path), 'size': len(src)}
    dm = ctx.dump(src)
    active, stats = check_dump(src, dm)
    names = [m.get('name') for m in dm['members']]
    res['members'] = len(names); res['active'] = len(active); res['indexes'] = len(stats)
    res['identity'] = ctx.apply(src, []) == src
    # the data member with the most active records, and two records in it
    cnt = collections.Counter(m for m, _ in active.values())
    dmi = cnt.most_common(1)[0][0]
    offs = sorted(o for o, (m, _) in active.items() if m == dmi)
    ra, rb = offs[len(offs) // 2], offs[len(offs) // 3]
    A, B = active[ra][1], active[rb][1]
    A1 = bytearray(A); A1[len(A) // 2] = (A1[len(A) // 2] + 1) & 0xff; A1 = bytes(A1)
    N = bytes(x ^ 0x5a for x in A)
    base = multiset(active)
    cases = {
        'rewrite': ([{'op': 'rewrite', 'rec': ra, 'data': A1.hex()}], {(dmi, A): -1, (dmi, A1): 1}),
        'grow': ([{'op': 'rewrite', 'rec': ra, 'data': (A + bytes(9)).hex()}], {(dmi, A): -1, (dmi, A + bytes(9)): 1}),
        'add': ([{'op': 'add', 'm': dmi, 'data': N.hex()}], {(dmi, N): 1}),
        'delete': ([{'op': 'delete', 'rec': rb}], {(dmi, B): -1}),
        'combined': ([{'op': 'rewrite', 'rec': ra, 'data': (A1 + bytes(13)).hex()}, {'op': 'add', 'm': dmi, 'data': N.hex()},
                      {'op': 'delete', 'rec': rb}], {(dmi, A): -1, (dmi, A1 + bytes(13)): 1, (dmi, N): 1, (dmi, B): -1}),
    }
    for name, (edits, delta) in cases.items():
        try:
            out = ctx.apply(src, edits)
            dm2 = ctx.dump(out)
            act2, st2 = check_dump(out, dm2, need_scan=False)
            if [m.get('name') for m in dm2['members']] != names: fail('member list changed')
            want = base.copy()
            for k, v in delta.items(): want[k] += v
            want = +want
            if multiset(act2) != want: fail('active records differ from the expected set')
            if set(st2) != set(stats): fail('index members changed')
            dn = sum(delta.values())
            for m, c in stats.items():
                if dm['members'][m].get('data') == dmi and st2[m] != c + dn: fail(f'index {m}: {st2[m]} entries, want {c + dn}')
            res[name] = True
        except Exception as e:
            res[name] = False
            if verbose: print(f'  {res["file"]} {name}: {str(e)[:300]}')
    res['ok'] = res['identity'] and all(res[c] for c in cases)
    return res


def run(ctx, paths, gating_set, verbose):
    ok_all = True
    for path in paths:
        try:
            r = check_file(ctx, path, verbose)
        except Exception as e:
            r = {'file': os.path.basename(path), 'ok': False, 'error': str(e)[:300]}
        if path in gating_set and not r['ok']: ok_all = False
        print(('  ' if path in gating_set else '  (secondary) ') + json.dumps(r))
    return ok_all


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/codec.py'
    verbose = '-v' in sys.argv
    with tempfile.TemporaryDirectory(prefix='ctref') as td:
        ctx = Ctx(codec, td)
        if '--audit' in sys.argv:
            for path in cfg['audit']:
                src = safe_read(path, 64 << 20); dm = ctx.dump(src)
                print(f'== {os.path.basename(path)} ({len(src)} bytes)')
                for i, m in enumerate(dm.get('members', [])[:60]): print(f'member {i}: {json.dumps(m)[:200]}')
                recs = [r for r in dm.get('records', []) if not r.get('del')]
                print(f'{len(recs)} active records, {len(dm.get("index", []))} index entries; sample:')
                for r in recs[::max(1, len(recs) // 12)][:12]:
                    print(f'  m={r["m"]} off={r["off"]} len={r["len"]} {src[r["off"]:r["off"] + min(r["len"], 24)].hex()}')
                ix = dm.get('index', [])
                for e in ix[::max(1, len(ix) // 8)][:8]:
                    print(f'  index m={e["m"]} key={src[e["koff"]:e["koff"] + e["klen"]].hex()} -> {e["rec"]}')
                print('meta:', json.dumps(dm.get('meta'))[:1500])
            return
        if '--holdout' in sys.argv:
            ok = run(ctx, cfg['holdout'], set(cfg['holdout']), verbose)
            print('PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)
        paths = cfg['primary'] + cfg.get('secondary', [])
        if '--files' in sys.argv:
            want = sys.argv[sys.argv.index('--files') + 1].split(',')
            paths = [p for p in paths if os.path.basename(p) in want]
        ok = run(ctx, paths, set(cfg['primary']), verbose)
    full = '--files' not in sys.argv
    print('PASS' if ok and full else ('FAIL' if not ok else 'PARTIAL (subset; the driver scores all files)'))
    sys.exit(0 if ok and full else 1)


if __name__ == '__main__':
    main()
