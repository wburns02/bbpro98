"""Ground-truth oracle for the per-game Stats/MLBPA97.Hxx decoder.

usage: python3 check_hdecode.py <decoder.py> [--days 2-7] [-v]   (days 8-10 = holdout, scored by the driver only)

Contract for <decoder.py>: `python3 <decoder.py> <path-to-Hxx>` prints one JSON object:
  {"batters":  [{"pid": int, "ab": int, "h": int, "hr": int, "rbi": int, "bb": int, "so": int, "r": int, "sb": int}, ...],
   "pitchers": [{"pid": int, "outs": int, "bf": int, "h": int, "hr": int, "bb": int, "so": int, "r": int}, ...]}   # pitchers optional
Every player who appeared in the game must be listed once per team side (a player in both lists is fine).

Truth: for snapshot day D, the per-player change in Stats/mlbpa97.DAT scope-1 season lines between day D-1 and D,
summed over all H files that are new or changed on day D (one H file per game). Team-total rows are excluded.
Snapshots: /mnt/nvme/bbpro98/re/asnseq/dayNN (read only). This file is the referee: do not edit it.
The decoder runs in a bwrap jail: no network, no filesystem except /usr and a tempdir holding hdecode.py + game.bin.
"""
import sys, os, json, hashlib, subprocess, collections, tempfile, shutil
sys.path[:0] = ['/home/will/bbpro98/work']
from lib import load

SNAP = '/mnt/nvme/bbpro98/re/asnseq'
# stats-line columns (work/NOTES_stats_format.md); h is derived = 1B+2B+3B+HR
BAT = {'ab': 0, 'hr': 4, 'rbi': 5, 'bb': 6, 'so': 7, 'r': 13, 'sb': 14}
PIT = {'hr': 4, 'bb': 6, 'so': 7, 'r': 13, 'outs': 18, 'bf': 19}


def lines(day):
    bat, pit, teams = {}, {}, set()
    for _pos, _rn, _off, u in load(f'{SNAP}/{day}/Stats/mlbpa97.DAT'):
        n = len(u) * 2
        if u[0] == 16 and n == 40: teams.add(u[2])
        if u[0] != 1: continue
        if n == 40: bat[u[2]] = u[3:]
        elif n == 70: pit[u[2]] = u[3:]
    return bat, pit, teams


def stat(c, cols, k):
    return c[1] + c[2] + c[3] + c[4] if k == 'h' else c[cols[k]]


def delta(cur, prev, cols, keys, skip):
    out = {}
    for p, c in cur.items():
        if p in skip: continue
        o = prev.get(p)
        d = {k: stat(c, cols, k) - (stat(o, cols, k) if o else 0) for k in keys}
        if any(d.values()): out[p] = d
    return out


def hfiles(day):
    d = f'{SNAP}/{day}/Stats'
    return {f: hashlib.md5(open(f'{d}/{f}', 'rb').read()).hexdigest() for f in os.listdir(d) if '.H' in f.upper()}


def run_jailed(dec, td):
    """Run the decoder with only /usr and td visible, no network, empty env."""
    st = os.lstat(dec)
    if not __import__('stat').S_ISREG(st.st_mode) or st.st_size > 2_000_000:
        raise ValueError(f'{dec}: not a regular file under 2 MB')
    shutil.copyfile(dec, f'{td}/hdecode.py', follow_symlinks=False)
    cmd = ['bwrap', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
           '--symlink', 'usr/bin', '/bin', '--proc', '/proc', '--dev', '/dev', '--bind', td, '/w', '--chdir', '/w',
           '--unshare-all', '--die-with-parent', '--clearenv', '--setenv', 'PATH', '/usr/bin',
           '/usr/bin/python3', '-I', 'hdecode.py', 'game.bin']
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def sample(dec, path):
    """--sample <H file>: print the jailed decoder's raw output for one file (used by the audit)."""
    with tempfile.TemporaryDirectory() as td:
        shutil.copyfile(path, f'{td}/game.bin'); r = run_jailed(dec, td)
    print(r.stdout[:3000]); print('STDERR:', r.stderr[-500:])


def main():
    dec = sys.argv[1]; verbose = '-v' in sys.argv
    if '--sample' in sys.argv:
        return sample(dec, sys.argv[sys.argv.index('--sample') + 1])
    lo, hi = 2, 7
    if '--days' in sys.argv:
        lo, hi = map(int, sys.argv[sys.argv.index('--days') + 1].split('-'))
    bkeys = ['ab', 'h', 'hr', 'rbi', 'bb', 'so', 'r', 'sb']
    pkeys = ['outs', 'bf', 'h', 'hr', 'bb', 'so', 'r']
    tot = {'bat': collections.Counter(), 'pit': collections.Counter()}
    errors = 0
    for i in range(lo, hi + 1):
        prev, cur = f'day{i-1:02d}', f'day{i:02d}'
        b0, p0, _ = lines(prev); b1, p1, teams = lines(cur)
        tb = delta(b1, b0, BAT, bkeys, teams); tp = delta(p1, p0, PIT, pkeys, teams)
        h0, h1 = hfiles(prev), hfiles(cur)
        new = sorted(f for f in h1 if h0.get(f) != h1[f])
        db, dp = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
        for f in new:
            try:
                with tempfile.TemporaryDirectory() as td:  # anonymous copy: the decoder must not learn day/game from the path
                    shutil.copy(f'{SNAP}/{cur}/Stats/{f}', f'{td}/game.bin')
                    r = run_jailed(dec, td)
                js = json.loads(r.stdout)
            except Exception as e:
                errors += 1; print(f'{cur} {f}: decoder failed: {e} {r.stderr[-300:] if "r" in dir() else ""}'); continue
            for row in js.get('batters', []):
                for k in bkeys: db[int(row['pid'])][k] += int(row.get(k, 0))
            for row in js.get('pitchers', []):
                for k in pkeys: dp[int(row['pid'])][k] += int(row.get(k, 0))
        for kind, truth, got, keys in (('bat', tb, db, bkeys), ('pit', tp, dp, pkeys)):
            if kind == 'pit' and not got: continue
            t = tot[kind]
            for p in set(truth) | set(got):
                tr, gt = truth.get(p), got.get(p)
                if tr is None: t['extra'] += 1; verbose and print(f'{cur} {kind} extra pid {p} {dict(gt)}'); continue
                if gt is None: t['missing'] += 1; verbose and print(f'{cur} {kind} missing pid {p} {tr}'); continue
                t['players'] += 1
                for k in keys:
                    t['cells'] += 1
                    if tr[k] == gt[k]: t['ok'] += 1; t['ok_' + k] += 1
                    else: verbose and print(f'{cur} {kind} pid {p} {k}: truth {tr[k]} got {gt[k]}')
                    t['n_' + k] += 1
        print(f'{cur}: {len(new)} games, truth batters {len(tb)}, pitchers {len(tp)}')
    for kind, keys in (('bat', bkeys), ('pit', pkeys)):
        t = tot[kind]
        if not t['cells']: print(f'{kind}: not decoded'); continue
        per = ' '.join(f"{k}={t['ok_' + k] / t['n_' + k]:.3f}" for k in keys)
        print(f"{kind}: cell accuracy {t['ok'] / t['cells']:.4f} | matched players {t['players']} missing {t['missing']} extra {t['extra']} | {per}")
    b = tot['bat']
    ok = b['cells'] and b['ok'] / b['cells'] >= 0.99 and b['missing'] + b['extra'] <= 0.01 * max(b['players'], 1) and not errors
    print('PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
