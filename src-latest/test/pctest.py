#!/usr/bin/env python3
"""Unit test of the playercard mod's stats-file reader and card text, under Wine. Builds pctest.exe (which includes
src-latest/mods/playercard.c), runs it on game-written stats files and checks every record it picked up against
work/ctree.py (members found by name) and the batting/pitching rates against an independent computation.
usage: python3 pctest.py OUTDIR [STATS.DAT ...]   (needs the zig env at /mnt/nvme/bbpro98/zigenv and wine; the default
files are the work install's stats files; exits 0 with SKIP when none exist)"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(SRC), 'work'))
import ctree  # noqa: E402

ZIG = ['/mnt/nvme/bbpro98/zigenv/bin/python', '-m', 'ziglang', 'cc', '-target', 'x86-windows-gnu', '-O2']
DEFAULT = ['/mnt/nvme/bbpro98/work_install/Stats/mlbpa97.DAT', '/mnt/nvme/bbpro98/work_install/Stats/16L1927.DAT']
ENV = dict(os.environ, WINEPREFIX='/mnt/nvme/bbpro98/hktest_prefix', WINEDEBUG='-all',
           WINEDLLOVERRIDES='mscoree,mshtml=;winedbg.exe=d', DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent', DISPLAY='')
BAT = ('ab', 'h1b', 'h2b', 'h3b', 'hr', 'rbi', 'bb', 'so', 'ibb', 'hbp', 'sh', 'sf', 'g', 'r', 'sb', 'cs', 'gidp')
PIT = BAT + ('gf', 'outs', 'bfp', 'w', 'l', 'sv', 'cg', 'sho', 'qs', 'er')
PERIOD = {0: 'Last 7 days', 1: 'This season', 2: 'Career', 3: 'Last season'}


def expected(path):
    """{pid: {(table, scope): words}} for live bt/pt (scopes 0-3) and ft (career) records, members by name."""
    d = open(path, 'rb').read()
    _, by_mem, members, *_ = ctree.parse(d)
    num = {m['name']: m['num'] for m in members if m['kind'] == 'data'}
    out = {}
    for table, name in (('bat', 'bt.dat'), ('pit', 'pt.dat'), ('fld', 'ft.dat')):
        for r in by_mem.get(num.get(name, -1), []):
            p = d[r.off:r.off + r.pl]
            if p[0] == 0xFF or r.pl < 6 or r.pl % 2:
                continue
            w = struct.unpack_from('<%dH' % (r.pl // 2), p)
            if w[1] != 2 or w[0] > 3 or (table == 'fld' and w[0] != 2):
                continue
            key = (table, w[0])
            assert key not in out.setdefault(w[2], {}), 'duplicate %s line for pid %d in %s' % (key, w[2], path)
            out[w[2]][key] = list(w[3:])
    return out


def pick(exp):
    """A hitter (most career AB), a pitcher (most career outs), a pitcher-only id, and an id with no lines."""
    def car(pid, t, f):
        w = exp[pid].get((t, 2))
        return w[(BAT if t == 'bat' else PIT).index(f)] if w else -1
    players = [p for p in exp if p >= 100]
    hitter = max(players, key=lambda p: car(p, 'bat', 'ab'))
    pitcher = max(players, key=lambda p: car(p, 'pit', 'outs'))
    absent = max(exp) + 1
    return [hitter, pitcher, absent]


def rate(num, den):
    if den <= 0:
        return '  ---'
    v = (num * 1000 + den // 2) // den
    return '%d.%03d' % (v // 1000, v % 1000) if v >= 1000 else ' .%03d' % v


def main():
    out = os.path.abspath(sys.argv[1])
    files = [f for f in (sys.argv[2:] or DEFAULT) if os.path.exists(f)]
    if not files:
        print('SKIP: no stats files')
        return 0
    os.makedirs(out, exist_ok=True)
    subprocess.run(ZIG + ['-I', SRC, '-o', os.path.join(out, 'pctest.exe'), os.path.join(HERE, 'pctest.c'),
                          '-lgdi32', '-luser32'], check=True)
    fails = 0
    checks = 0
    for path in files:
        exp = expected(path)
        pids = pick(exp)
        wpath = 'Z:' + path.replace('/', '\\')
        try:
            r = subprocess.run(['wine', 'pctest.exe', wpath] + [str(p) for p in pids], cwd=out, env=ENV,
                               capture_output=True, text=True, timeout=120)
        finally:
            subprocess.run(['wineserver', '-k'], env=ENV)
        got, txt, rcs, cur = {}, {}, {}, None
        for line in r.stdout.splitlines():
            f = line.split()
            if not f:
                continue
            if f[0] == 'PID':
                cur = int(f[1])
                rcs[cur] = int(f[3])
                got[cur] = {}
                txt[cur] = []
            elif f[0] == 'RAW':
                got[cur][(f[1], int(f[2]))] = [int(x) for x in f[3:]]
            elif f[0] == 'TXT':
                txt[cur].append(line[4:])
        for pid in pids:
            want = exp.get(pid, {})
            checks += 1
            if rcs.get(pid) != 0:
                print('FAIL %s pid %d rc %s' % (os.path.basename(path), pid, rcs.get(pid)))
                fails += 1
                continue
            if got.get(pid) != {k: v[:80] for k, v in want.items()}:
                print('FAIL %s pid %d records differ:\n  got  %s\n  want %s' % (os.path.basename(path), pid,
                                                                             sorted(got.get(pid, {})), sorted(want)))
                fails += 1
            # rates on every batting line the card printed
            for s in range(4):
                w = want.get(('bat', s))
                if not w or not (w[0] + w[6]):
                    continue
                b = dict(zip(BAT, w))
                h = b['h1b'] + b['h2b'] + b['h3b'] + b['hr']
                tb = b['h1b'] + 2 * b['h2b'] + 3 * b['h3b'] + 4 * b['hr']
                tail = '%s %s %s' % (rate(h, b['ab']), rate(h + b['bb'] + b['hbp'], b['ab'] + b['bb'] + b['hbp'] + b['sf']),
                                     rate(tb, b['ab']))
                row = [t for t in txt[pid] if t.startswith(PERIOD[s]) and t.endswith(tail)]
                checks += 1
                if len(row) != 1 or ' %d ' % b['hr'] not in row[0]:
                    print('FAIL %s pid %d bat scope %d: no card row ending %r' % (os.path.basename(path), pid, s, tail))
                    fails += 1
            for s in range(4):
                w = want.get(('pit', s))
                if not w or not w[PIT.index('outs')]:
                    continue
                p = dict(zip(PIT, w))
                outs = p['outs']
                era = (27 * p['er'] * 100 + outs // 2) // outs
                ip = '%d.%d' % (outs // 3, outs % 3)
                row = [t for t in txt[pid] if t.startswith(PERIOD[s]) and ' %s ' % ip in t
                       and t.rstrip().split()[-2] == '%d.%02d' % (era // 100, era % 100)]
                checks += 1
                if len(row) != 1:
                    print('FAIL %s pid %d pit scope %d: no card row with IP %s ERA %d.%02d' %
                          (os.path.basename(path), pid, s, ip, era // 100, era % 100))
                    fails += 1
            if not want and not any('No batting or pitching lines' in t for t in txt[pid]):
                print('FAIL %s pid %d: absent player card lacks the no-lines notice' % (os.path.basename(path), pid))
                fails += 1
        print('%s: pids %s ok' % (os.path.basename(path), pids) if not fails else '%s checked' % path)
        for pid in pids[:1]:
            print('\n'.join('  | ' + t for t in txt.get(pid, [])))
    # unreadable file
    try:
        r = subprocess.run(['wine', 'pctest.exe', 'Z:\\nonexistent\\X.DAT', '123'], cwd=out, env=ENV,
                           capture_output=True, text=True, timeout=120)
    finally:
        subprocess.run(['wineserver', '-k'], env=ENV)
    checks += 1
    if 'PID 123 rc -1' not in r.stdout:
        print('FAIL missing file: %r' % r.stdout[:200])
        fails += 1
    print('%d checks, %d failures' % (checks, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
