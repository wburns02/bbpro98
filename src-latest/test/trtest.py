#!/usr/bin/env python3
"""Test of the bbtrace.log size cap (bbfix.ini [trace] max_mb) under Wine. Builds bbfix.dll, a mod that logs N lines of
about 400 characters and a runner, then runs three cases, each in its own folder with its own bbfix.ini:
rotation at max_mb=1, no rotation at max_mb=0, and the 64 MB default (no [trace] section); a fourth case blocks the
rename (bbtrace.1.log is a folder) and checks no line is lost.
usage: python3 trtest.py OUTDIR      (OUTDIR is created; needs zig env at /mnt/nvme/bbpro98/zigenv and wine; SKIP without)"""
import os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.dirname(HERE)
ZIGPY = '/mnt/nvme/bbpro98/zigenv/bin/python'
ZIG = [ZIGPY, '-m', 'ziglang', 'cc', '-target', 'x86-windows-gnu', '-O2']
PREFIX = '/mnt/nvme/bbpro98/hktest_prefix'
if not shutil.which('wine') or not os.path.exists(ZIGPY):
    print('SKIP: wine or the zig env (/mnt/nvme/bbpro98/zigenv) is missing'); sys.exit(0)
out = os.path.abspath(sys.argv[1]); os.makedirs(out, exist_ok=True)

def cc(*args):
    subprocess.run(ZIG + list(args), check=True)

cc('-shared', '-o', f'{out}/bbfix.dll', f'{SRC}/bbfix.c', '-Wno-incompatible-pointer-types', '-lpsapi')
cc('-shared', '-I', SRC, '-o', f'{out}/trmod.dll', f'{HERE}/trtest_mod.c')
cc('-o', f'{out}/trrun.exe', f'{HERE}/trrun.c')

env = dict(os.environ, WINEPREFIX=PREFIX, WINEDEBUG='-all', WINEDLLOVERRIDES='mscoree,mshtml=;winedbg.exe=d',
           DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent', DISPLAY='')
fails = []

def check(name, ok, why=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  ({why})'))
    if not ok: fails.append(name)

def run_case(name, lines, max_mb, pre=None):
    d = f'{out}/{name}'; shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    if pre: pre(d)
    for f in ('bbfix.dll', 'trmod.dll', 'trrun.exe'): shutil.copy(f'{out}/{f}', d)
    with open(f'{d}/bbfix.ini', 'w') as fh:
        fh.write(f'[mods]\r\nload=trmod.dll\r\n[trtest]\r\nlines={lines}\r\n')
        if max_mb is not None: fh.write(f'[trace]\r\nmax_mb={max_mb}\r\n')
    try:
        r = subprocess.run(['wine', 'trrun.exe'], cwd=d, env=env, capture_output=True, text=True, timeout=120)
    finally:
        subprocess.run(['wineserver', '-k'], env=env)
    check(f'{name}: runner exits 0 and prints ok', r.returncode == 0 and r.stdout.strip() == 'ok', f'rc={r.returncode} {r.stdout!r}')
    return d

def read(path):
    return open(path, errors='replace').read() if os.path.exists(path) else None

def indexes(text):
    return [int(m) for m in re.findall(r'MOD    TRL(\d{5}) ', text or '')]

N = 6000; MIB = 1048576
d = run_case('tr_rot', N, 1)
cur, old = read(f'{d}/bbtrace.log'), read(f'{d}/bbtrace.1.log')
check('rot: bbtrace.log and bbtrace.1.log both exist', cur is not None and old is not None)
for f in ('bbtrace.log', 'bbtrace.1.log'):
    sz = os.path.getsize(f'{d}/{f}') if os.path.exists(f'{d}/{f}') else -1
    check(f'rot: {f} <= 1 MiB + 1000 bytes', 0 < sz <= MIB + 1000, f'size {sz}')
check('rot: bbtrace.log first line is "TRACE  rotated #2"', 'TRACE  rotated #2' in (cur or '\n').split('\n', 1)[0], (cur or '').split('\n', 1)[0])
check('rot: bbtrace.1.log first line is "TRACE  rotated #1"', 'TRACE  rotated #1' in (old or '\n').split('\n', 1)[0], (old or '').split('\n', 1)[0])
check(f'rot: last mod line TRL{N - 1:05d} is in bbtrace.log', N - 1 in indexes(cur), f'last in file: {indexes(cur)[-1:]}')
check('rot: no line is split across the two files', (old or '').endswith('\n') and (cur or '').endswith('\n'))

d = run_case('tr_nolimit', N, 0)
cur = read(f'{d}/bbtrace.log')
check('nolimit: no bbtrace.1.log', not os.path.exists(f'{d}/bbtrace.1.log'))
check('nolimit: bbtrace.log > 2 MB', cur is not None and len(cur) > 2 * 1000 * 1000, f'size {len(cur or "")}')
check('nolimit: bbtrace.log holds every line', indexes(cur) == list(range(N)), f'{len(indexes(cur))} lines')
check('nolimit: no rotation header', 'rotated #' not in (cur or ''))

d = run_case('tr_default', 100, None)
cur = read(f'{d}/bbtrace.log')
check('default: no bbtrace.1.log', not os.path.exists(f'{d}/bbtrace.1.log'))
check('default: "action trace started" line present', 'action trace started' in (cur or ''))
check('default: bbtrace.log holds all 100 lines', indexes(cur) == list(range(100)), f'{len(indexes(cur))} lines')

def block(d):
    os.makedirs(f'{d}/bbtrace.1.log'); open(f'{d}/bbtrace.1.log/keep', 'w').close()

d = run_case('tr_blocked', N, 1, block)
cur = read(f'{d}/bbtrace.log')
check('blocked: bbtrace.1.log is still the folder', os.path.isdir(f'{d}/bbtrace.1.log'))
check('blocked: "rotation off" line present', 'rotation off' in (cur or ''))
check('blocked: bbtrace.log holds every line', indexes(cur) == list(range(N)), f'{len(indexes(cur))} lines')
check('blocked: action trace start kept', 'action trace started' in (cur or ''))

print('FAIL' if fails else 'PASS')
sys.exit(1 if fails else 0)
