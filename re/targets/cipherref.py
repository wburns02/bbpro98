"""Referee for the byte-substitution table generator (PYR / ASN / H-file cipher). Claude-owned: GLM must not edit it.

usage: python3 cipherref.py <target_dir> <lane_dir> [-v]      score <lane>/gen.py on the visible data
       python3 cipherref.py <target_dir> <lane_dir> --holdout   same checks on H files the lane never sees
       python3 cipherref.py <target_dir> <lane_dir> --audit X   text sample for the audit

Contract: `python3 gen.py SEED` (SEED = the two seed bytes as stored, 4 hex digits, e.g. f5dc) prints the 256-entry
forward table plain->stored as 512 hex digits on one line. gen.py runs in a jail with nothing but /usr.
Checks: every output is a permutation; gen(f5dc) equals the table recovered from the shipped PYR files (exact);
for every H file, decoding the 2696-byte blob after its 2-byte seed with gen(seed) maps the blob's dominant byte to
0x00 and yields >= 80% zero bytes (the blob is mostly zero padding). Reported, not gating: how many non-zero byte
positions decode to the same value across >= 90% of files (structure that only a right full table produces).
"""
import sys, os, json, glob, tempfile, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail

MAX_GEN = 30_000


def jail_many(gen, seeds):
    out = {}
    with tempfile.TemporaryDirectory(prefix='cipherref') as td:
        for s in seeds:
            r = J.jail(gen, td, [s], name='gen.py', max_size=MAX_GEN, timeout=60, mem='2G', writable=False)
            try:
                t = bytes.fromhex(r.stdout.strip())
            except ValueError:
                fail(f'gen.py {s}: output is not hex')
            if len(t) != 256 or len(set(t)) != 256: fail(f'gen.py {s}: not a 256-byte permutation')
            out[s] = t
    return out


def pyr_table(paths):
    """Forward table from a PYR whose record i has id 100+i (BBPRO98_package/research/dump_pyr.py)."""
    fwd = {}
    for p in paths:
        d = open(p, 'rb').read()
        for i in range((len(d) - 192) // 192):
            r = d[192 + 192 * i:194 + 192 * i]; pid = 100 + i
            fwd[pid & 255] = r[0]; fwd[pid >> 8] = r[1]
    if len(fwd) != 256: fail('PYR table incomplete')
    return bytes(fwd[i] for i in range(256))


def blobs(paths):
    out = []
    for p in paths:
        b = open(p, 'rb').read()
        if b[:2] == b'\x02\x65' and b[6:8] == b'\x8a\x0a': out.append((os.path.basename(os.path.dirname(os.path.dirname(p))) + '/' + os.path.basename(p), b[8:10].hex(), b[10:10 + 2696]))
    return out


def score(tabs, bl):
    good, dec = 0, []
    for name, seed, blob in bl:
        inv = [0] * 256
        for x, y in enumerate(tabs[seed]): inv[y] = x
        p = bytes(inv[c] for c in blob); dec.append(p)
        dom = collections.Counter(blob).most_common(1)[0][0]
        if inv[dom] == 0 and p.count(0) >= 0.8 * len(p): good += 1
    agree = 0
    if dec:
        for i in range(len(dec[0])):
            v, c = collections.Counter(p[i] for p in dec).most_common(1)[0]
            if v != 0 and c >= 0.9 * len(dec): agree += 1
    return good, agree, dec


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    gen = f'{lane}/gen.py'
    hold = '--holdout' in sys.argv
    hpaths = sorted(set(p for g in cfg['holdout' if hold else 'hfiles'] for p in glob.glob(g)))
    bl = blobs(hpaths)
    if hold:  # only seeds the lane has never seen
        seen = {s for _, s, _ in blobs(sorted(set(p for g in cfg['hfiles'] for p in glob.glob(g))))}
        uniq = {}
        for n, s, b in bl:
            if s not in seen and s not in uniq: uniq[s] = (n, s, b)
        bl = list(uniq.values())
    try:
        tabs = jail_many(gen, sorted({'f5dc'} | {s for _, s, _ in bl}))
    except Exception as e:
        print(f'  error: {J.err(e)}'); print('FAIL'); sys.exit(1)
    exact = tabs['f5dc'] == pyr_table(cfg['pyr'])
    good, agree, dec = score(tabs, bl)
    if '--audit' in sys.argv:
        print(f'gen(f5dc) == PYR table: {exact}')
        for (n, s, _), p in list(zip(bl, dec))[:6]:
            nz = [(i, p[i]) for i in range(len(p)) if p[i]][:40]
            print(f'{n} seed {s}: {p.count(0)}/{len(p)} zero; first non-zero (pos, byte): {nz}')
        return
    ok = exact and bl and good >= 0.97 * len(bl)
    if not hold: print(json.dumps({'f5dc_exact': exact, 'h_files': len(bl), 'h_zero_ok': good, 'nonzero_agree_positions': agree}))
    if '-v' in sys.argv and not exact:
        t = pyr_table(cfg['pyr']); print('  f5dc mismatches at', [i for i in range(256) if tabs['f5dc'][i] != t[i]][:30])
    print('PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
