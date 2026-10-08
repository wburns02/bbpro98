#!/usr/bin/env python3
"""Unit test of the bbfix.dll mod hook engine (roadmap #9) under Wine. Builds bbfix.dll, a synthetic target DLL with
hand-assembled prologs, three test mods and a runner, then checks every hook kind on a normally loaded and a relocated
copy, plus the refusals (wrong expect bytes, base-relocation overlap).
usage: python3 hktest.py OUTDIR      (OUTDIR is created; needs zig env at /mnt/nvme/bbpro98/zigenv and wine)"""
import os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.dirname(HERE)
ZIG = ['/mnt/nvme/bbpro98/zigenv/bin/python', '-m', 'ziglang', 'cc', '-target', 'x86-windows-gnu', '-O2']
out = os.path.abspath(sys.argv[1]); os.makedirs(out, exist_ok=True)

def cc(*args):
    subprocess.run(ZIG + list(args), check=True)

cc('-shared', '-o', f'{out}/bbfix.dll', f'{SRC}/bbfix.c', '-Wno-incompatible-pointer-types', '-lpsapi')
cc('-shared', '-o', f'{out}/hktarget.dll', f'{HERE}/hktarget.c', '-Wl,--image-base=0x10000000')
shutil.copy(f'{out}/hktarget.dll', f'{out}/hkreloc.dll')
for i, n in enumerate(['hkgood', 'hkbad', 'hkrel']):
    cc('-shared', f'-DWHICH={i}', '-I', SRC, '-o', f'{out}/{n}.dll', f'{HERE}/hktest_mod.c')
cc('-o', f'{out}/hkrun.exe', f'{HERE}/hkrun.c')

import struct
def pe_exports(path):
    """{name: VA at the preferred base} from the export directory, plus ImageBase."""
    d = open(path, 'rb').read(); pe = struct.unpack_from('<I', d, 0x3c)[0]
    base = struct.unpack_from('<I', d, pe + 0x34)[0]; nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = struct.unpack_from('<H', d, pe + 0x14)[0]; secs = pe + 0x18 + opt
    def off(rva):
        for i in range(nsec):
            vs, va_, rs, ro = struct.unpack_from('<IIII', d, secs + 40 * i + 8)
            if va_ <= rva < va_ + max(vs, rs): return rva - va_ + ro
        raise ValueError(hex(rva))
    erva = struct.unpack_from('<I', d, pe + 0x78)[0]; e = off(erva)
    nfun, nname, af, an, ao = struct.unpack_from('<IIIII', d, e + 0x14)
    res = {}
    for i in range(nname):
        nrva = struct.unpack_from('<I', d, off(an) + 4 * i)[0]; o = off(nrva); name = d[o:d.index(b'\0', o)].decode()
        ordi = struct.unpack_from('<H', d, off(ao) + 2 * i)[0]
        res[name] = base + struct.unpack_from('<I', d, off(af) + 4 * ordi)[0]
    return res
va = pe_exports(f'{out}/hktarget.dll')
need = ['f_add', 'f_call', 'f_call2', 'f_mid', 'f_mid_site', 'f_mid_alt', 'f_patch', 'f_bad', 'f_rel', 'helper5']
missing = [k for k in need if k not in va]
if missing: sys.exit(f'export parse failed: {missing}')
# g_val: the absolute operand of f_rel's mov eax,[g_val] (a1 imm32), read from the file
d = open(f'{out}/hktarget.dll', 'rb').read()
code = subprocess.run(['i686-w64-mingw32-objdump', '-d', f'--start-address={va["f_rel"]:#x}', f'--stop-address={va["f_rel"] + 5:#x}',
                       f'{out}/hktarget.dll'], capture_output=True, text=True).stdout
m = re.search(r'\ba1 ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2})', code)
if not m: sys.exit('f_rel is not mov eax,[abs]:\n' + code)
va['g_val'] = int(''.join(reversed(m.groups())), 16)
with open(f'{out}/bbfix.ini', 'w') as fh:
    fh.write('[mods]\r\nload=hkgood.dll,hkbad.dll,hkrel.dll\r\n[hktest]\r\n')
    for k, v in va.items(): fh.write(f'{k}={v}\r\n')

env = dict(os.environ, WINEPREFIX='/mnt/nvme/bbpro98/hktest_prefix', WINEDEBUG='-all', WINEDLLOVERRIDES='mscoree,mshtml=;winedbg.exe=d',
           DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent', DISPLAY='')
try:
    r = subprocess.run(['wine', 'hkrun.exe'], cwd=out, env=env, capture_output=True, text=True, timeout=60)
finally:
    subprocess.run(['wineserver', '-k'], env=env)
got = {}
for line in r.stdout.splitlines():
    p = line.split()
    if len(p) == 3 and p[1] != 'base': got[(p[0], p[1])] = int(p[2])
print(r.stdout.strip())
trace = open(f'{out}/bbtrace.log', errors='replace').read() if os.path.exists(f'{out}/bbtrace.log') else ''
print('\n'.join(l for l in trace.splitlines() if 'MOD ' in l))
want = {'f_add': 500, 'f_call': 21, 'f_call2': 25, 'f_mid41': 42, 'f_mid5': 1006, 'f_mid77': 999, 'f_patch': 4, 'f_bad': 11, 'f_rel': 7}
fails = [f'{m} {k}: got {got.get((m, k))} want {v}' for m in ('hktarget.dll', 'hkreloc.dll') for k, v in want.items()
         if got.get((m, k)) != v]
bases = re.findall(r'(hk\w+\.dll) base (\w+)', r.stdout)
if len(bases) == 2 and bases[0][1] == bases[1][1]: fails.append('hkreloc.dll was not relocated')
for m in ('hktarget.dll', 'hkreloc.dll'):
    if not re.search(rf'hkgood.dll: applied 5 hooks to {m}', trace): fails.append(f'no "applied 5 hooks" for {m}')
    if not re.search(rf'hkbad.dll: NOT applied to {m} .*bytes differ', trace): fails.append(f'bad-expect refusal missing for {m}')
    if not re.search(rf'hkrel.dll: NOT applied to {m} .*overlaps a base relocation', trace): fails.append(f'reloc refusal missing for {m}')
print('\n'.join(fails) if fails else '', 'FAIL' if fails else 'PASS')
sys.exit(1 if fails else 0)
