"""Holdouts for what writes the user's game folder (work/patches: bytepatch.py, liveguard.py, install_live.sh,
revert_live.sh, mods_button.py) and for release packaging (tools/build_release.sh, release/). Every run happens in a
scratch directory: the installer scripts are copied with their hardcoded live paths rewritten to the scratch folder, and
the release script runs in a scratch git repo with a stub compiler. Nothing here touches the real game, a Wine prefix,
the network or zig."""
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest

from conftest import REPO

PATCHES = os.path.join(REPO, 'work', 'patches')
LIVE = os.path.realpath(os.path.expanduser('~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98'))
DEBUG_MODS = {'pitchtrace', 'seed', 'simtrace'}          # probes that are built by hand and never shipped


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)


# bytepatch.py and liveguard.py

def check_bytepatch_writes_only_the_asserted_bytes(tmp_path):
    """Guards: a patcher that writes when the old bytes are not what it expects (a different EXE or DLL build), one that
    inserts or drops bytes (length mismatch), and one that touches bytes outside the patch."""
    dll = tmp_path / 'x.dll'
    original = bytes(range(64))
    dll.write_bytes(original)
    script = os.path.join(PATCHES, 'bytepatch.py')
    ok = run([sys.executable, script, str(dll), '10', '10 11'.replace(' ', ''), 'aabb'])
    assert ok.returncode == 0, ok.stderr
    patched = dll.read_bytes()
    assert patched[:0x10] == original[:0x10] and patched[0x10:0x12] == b'\xaa\xbb' and patched[0x12:] == original[0x12:]
    assert len(patched) == len(original)
    before = dll.read_bytes()
    wrong = run([sys.executable, script, str(dll), '10', '1011', 'ccdd'])        # old bytes no longer match
    assert wrong.returncode != 0 and 'mismatch' in wrong.stderr
    assert dll.read_bytes() == before
    longer = run([sys.executable, script, str(dll), '20', '2021', 'aabbcc'])     # would insert a byte
    assert longer.returncode != 0
    assert dll.read_bytes() == before
    shorter = run([sys.executable, script, str(dll), '20', '2021', 'aa'])
    assert shorter.returncode != 0
    assert dll.read_bytes() == before


def test_patch_tools_write_only_asserted_bytes_and_never_the_live_install(tmp_path):
    """Guards: the byte patcher and the live install guard."""
    (tmp_path / 'p').mkdir()
    check_bytepatch_writes_only_the_asserted_bytes(tmp_path / 'p')
    check_liveguard_refuses_a_path_inside_the_live_install()


def check_liveguard_refuses_a_path_inside_the_live_install():
    """Guards: a patch tool that edits the live game install directly (the work copy is the only allowed target)."""
    target = os.path.join(LIVE, '__holdout_never_exists__.dll')
    for tool in ('bytepatch.py',):
        res = run([sys.executable, os.path.join(PATCHES, tool), target, '0', '00', '01'])
        assert res.returncode != 0 and 'REFUSED' in (res.stderr + res.stdout), tool
    assert not os.path.exists(target)
    ok = run([sys.executable, '-c', 'import sys; sys.argv=["x", "/tmp/not-the-game"]; sys.path.insert(0, %r); '
              'import liveguard; print("fine")' % PATCHES])
    assert ok.returncode == 0 and 'fine' in ok.stdout


# install_live.sh and revert_live.sh, run against a scratch "live" folder

PGREP_STUB = """#!/bin/sh
# stands in for pgrep: no game running unless a pids file sits beside it
if [ -f "$0.pids" ]; then cat "$0.pids"; exit 0; fi
exit 1
"""


def env_for(scripts, **extra):
    """The environment for an installer run: the stub pgrep first on PATH, so a real running game never matters."""
    return dict(os.environ, PATH=str(scripts / 'bin') + os.pathsep + os.environ['PATH'], **extra)


@pytest.fixture
def scratch(tmp_path):
    """(scripts dir, live dir, backup dir, vol, dll, env): the two installer scripts with their LIVE/B/V/D line pointed
    at the scratch folder, a live game folder holding the pristine files, and a backup of them."""
    live, back, build, scripts = (tmp_path / n for n in ('live', 'backup', 'build', 'scripts'))
    for d in (live, back, build, scripts, live / 'Sshell'):
        d.mkdir(parents=True, exist_ok=True)
    files = {'BBShell.dll': b'pristine-shell', 'SHELL.VOL': b'pristine-vol', 'bbfix.dll': b'pristine-fix'}
    for name, data in files.items():
        (live / name).write_bytes(data)
        (back / name).write_bytes(data)
    vol = build / 'SHELL_wide6.VOL'
    vol.write_bytes(b'wide-vol')
    dll = build / 'bbfix.dll'
    dll.write_bytes(b'new-bbfix')
    for name in ('install_live.sh', 'revert_live.sh'):
        text = open(os.path.join(PATCHES, name)).read()
        new, n = re.subn(r'(?m)^LIVE=.*$', 'LIVE=%s; B=%s; V=%s; D=%s' % (live, back, vol, dll), text, count=1)
        assert n == 1, '%s no longer starts with a LIVE=... line; update this holdout' % name
        assert '/home/will' not in new.replace(str(tmp_path), ''), 'a live path survived the rewrite in ' + name
        (scripts / name).write_text(new)
    shutil.copy(os.path.join(PATCHES, 'mods_button.py'), scripts / 'mods_button.py')
    (scripts / 'bin').mkdir()
    (scripts / 'bin' / 'pgrep').write_text(PGREP_STUB)
    (scripts / 'bin' / 'pgrep').chmod(0o755)
    return scripts, live, back, files


def live_state(live):
    return {str(p.relative_to(live)): p.read_bytes() for p in sorted(live.rglob('*')) if p.is_file()}


def check_installer_refuses_a_modified_shell_or_missing_mod_and_writes_nothing(scratch):
    """Guards: installing over a BBShell.dll that is not the pristine one, and a half install when a listed mod file does
    not exist (the files must be checked before the first copy)."""
    scripts, live, back, files = scratch
    mod = scratch[0].parent / 'real_mod.dll'
    mod.write_bytes(b'mod')
    before = live_state(live)
    res = run(['bash', str(scripts / 'install_live.sh')], env=env_for(scripts, MODS=str(scratch[0].parent / 'nope.dll')))
    assert res.returncode == 4 and 'REFUSED' in res.stdout
    assert live_state(live) == before
    (live / 'BBShell.dll').write_bytes(b'someone patched this')
    before = live_state(live)
    res = run(['bash', str(scripts / 'install_live.sh')], env=env_for(scripts, MODS=str(mod)))
    assert res.returncode == 3 and 'not pristine' in res.stdout
    assert live_state(live) == before


def test_installer_refuses_unsafe_states_and_writes_nothing(scratch):
    """Guards: a changed shell DLL, a missing mod file, and a game running in the live prefix."""
    check_installer_refuses_a_modified_shell_or_missing_mod_and_writes_nothing(scratch)
    scratch[1].joinpath('BBShell.dll').write_bytes(scratch[3]['BBShell.dll'])
    check_installer_refuses_while_a_game_runs_in_the_live_prefix(scratch)


def check_installer_refuses_while_a_game_runs_in_the_live_prefix(scratch):
    """Guards: installing over files the running live game has open (a game in a scratch prefix must not block it)."""
    scripts, live, back, files = scratch
    before = live_state(live)
    live_prefix = os.path.expanduser('~/.bbpro98_prefix')
    sleeper = subprocess.Popen(['sleep', '60'], env=dict(os.environ, WINEPREFIX=live_prefix))
    other = subprocess.Popen(['sleep', '60'], env=dict(os.environ, WINEPREFIX=str(scripts.parent / 'scratch_prefix')))
    try:
        (scripts / 'bin' / 'pgrep.pids').write_text('%d\n' % sleeper.pid)
        res = run(['bash', str(scripts / 'install_live.sh')], env=env_for(scripts))
        assert res.returncode == 2 and 'live game running' in res.stdout
        assert live_state(live) == before
        (scripts / 'bin' / 'pgrep.pids').write_text('%d\n' % other.pid)
        res = run(['bash', str(scripts / 'install_live.sh')], env=env_for(scripts))
        assert res.returncode == 0 and 'installed' in res.stdout
    finally:
        for proc in (sleeper, other):
            proc.kill()
            proc.wait()


def test_install_then_revert_round_trips_and_reinstall_is_idempotent(scratch):
    """Guards: an install that edits BBShell.dll on disk (hooks live in memory only), a mod list written wrong, a second
    install that stacks a duplicate [mods] section, and a revert that leaves anything but the pristine files."""
    scripts, live, back, files = scratch
    mods = scratch[0].parent / 'mods_src'
    mods.mkdir()
    for name in ('aging.dll', 'rookies.dll'):
        (mods / name).write_bytes(b'mod-' + name.encode())
    env = env_for(scripts, MODS='%s %s' % (mods / 'aging.dll', mods / 'rookies.dll'))
    first = run(['bash', str(scripts / 'install_live.sh')], env=env)
    assert first.returncode == 0 and 'installed' in first.stdout, first.stdout + first.stderr
    assert (live / 'BBShell.dll').read_bytes() == files['BBShell.dll']
    assert (live / 'bbfix.dll').read_bytes() == b'new-bbfix' and (live / 'SHELL.VOL').read_bytes() == b'wide-vol'
    assert (live / 'mods' / 'aging.dll').read_bytes() == b'mod-aging.dll'
    ini = (live / 'bbfix.ini').read_text()
    assert '[widen]' in ini and 'enable=1' in ini
    assert ini.count('[mods]') == 1 and 'load=mods\\aging.dll,mods\\rookies.dll' in ini
    state = live_state(live)
    again = run(['bash', str(scripts / 'install_live.sh')], env=env)
    assert again.returncode == 0 and live_state(live) == state
    res = run(['bash', str(scripts / 'revert_live.sh')], env=env_for(scripts))
    assert res.returncode == 0 and 'reverted' in res.stdout
    for name, data in files.items():
        assert (live / name).read_bytes() == data, name
    assert not (live / 'bbfix.ini').exists()


# mods_button.py

def test_mods_button_is_repeatable_keeps_originals_and_refuses_unknown_art(tmp_path):
    """Guards: a relabel that destroys the original button art (.orig), compounds on a second run instead of composing
    from the originals, or paints over art that is not the stock button."""
    from PIL import Image
    pal = [(i * 7) % 256 for i in range(768)]
    art = tmp_path / 'Sshell'
    art.mkdir()

    def bmp(name, size, seed):
        im = Image.new('P', size)
        im.putpalette(pal)
        im.putdata([(x * 31 + seed * 17 + (i // size[0])) % 200 for i, x in enumerate(range(size[0] * size[1]))])
        im.save(art / name)

    for k, state in enumerate(('NORM', 'HI', 'SEL')):
        bmp('WEB%s.BMP' % state, (144, 33), k + 1)
        bmp('LM%s.BMP' % state, (144, 33), k + 4)
        bmp('EXHB%s.BMP' % state, (144, 33), k + 7)
        bmp('BUTN%s.BMP' % state, (270, 33), k + 10)
    originals = {s: (art / ('WEB%s.BMP' % s)).read_bytes() for s in ('NORM', 'HI', 'SEL')}
    script = os.path.join(PATCHES, 'mods_button.py')
    first = run([sys.executable, script, str(art)])
    assert first.returncode == 0, first.stderr
    after = {s: (art / ('WEB%s.BMP' % s)).read_bytes() for s in originals}
    for s in originals:
        assert (art / ('WEB%s.BMP.orig' % s)).read_bytes() == originals[s]
        assert after[s] != originals[s]
    second = run([sys.executable, script, str(art)])
    assert second.returncode == 0
    for s in originals:
        assert (art / ('WEB%s.BMP' % s)).read_bytes() == after[s]                 # same result, composed from .orig
        assert (art / ('WEB%s.BMP.orig' % s)).read_bytes() == originals[s]
    # art that is not the stock button (wrong palette) is refused before anything is overwritten
    other = tmp_path / 'other'
    shutil.copytree(art, other)
    for p in other.glob('*.orig'):
        p.unlink()
    for s in ('NORM', 'HI', 'SEL'):
        im = Image.open(other / ('LM%s.BMP' % s))
        im.putpalette([255 - v for v in pal])
        im.save(other / ('LM%s.BMP' % s))
    keep = {p.name: p.read_bytes() for p in other.iterdir() if p.name.startswith('WEB') and p.name.endswith('.BMP')}
    bad = run([sys.executable, script, str(other)])
    assert bad.returncode != 0 and 'stock button art' in (bad.stderr + bad.stdout)
    assert {p.name: p.read_bytes() for p in other.iterdir() if p.name.startswith('WEB') and p.name.endswith('.BMP')} == keep


# tools/build_release.sh and release/

STUB_COMPILER = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
if a[:2] == ['-m', 'ziglang']:
    out = a[a.index('-o') + 1]
    with open(out, 'wb') as fh:
        fh.write(b'stub:' + os.path.basename(out).encode())
    base = os.path.splitext(out)[0]
    for ext in ('.pdb', '.lib'):
        open(base + ext, 'wb').write(b'debris')
    sys.exit(0)
os.execv(sys.executable, [sys.executable] + a)
'''


def git(repo, *args):
    return run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false',
                '-C', str(repo)] + list(args))


@pytest.fixture
def fake_repo(tmp_path):
    """A scratch git repo shaped like this one (tools/, release/, src-latest placeholders), tagged v9.9.9, plus a stub
    python that stands in for `python -m ziglang cc` and writes an empty-ish binary plus .pdb/.lib debris."""
    repo = tmp_path / 'repo'
    (repo / 'tools').mkdir(parents=True)
    shutil.copy(os.path.join(REPO, 'tools', 'build_release.sh'), repo / 'tools' / 'build_release.sh')
    shutil.copytree(os.path.join(REPO, 'release'), repo / 'release')
    (repo / 'src-latest' / 'mods').mkdir(parents=True)
    for name in ('bbfix.c', 'bblaunch.c'):
        (repo / 'src-latest' / name).write_text('// stub\n')
    for name in os.listdir(os.path.join(REPO, 'src-latest', 'mods')):
        if name.endswith('.c'):
            (repo / 'src-latest' / 'mods' / name).write_text('// stub\n')
    stub = tmp_path / 'stubpy'
    stub.write_text(STUB_COMPILER)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    assert git(repo, 'init', '-q').returncode == 0
    git(repo, 'add', '-A')
    assert git(repo, 'commit', '-q', '-m', 'init').returncode == 0
    assert git(repo, 'tag', 'v9.9.9').returncode == 0
    return repo, str(stub)


def build(repo, stub, out):
    return run(['bash', str(repo / 'tools' / 'build_release.sh'), str(out), stub])


def shipped_mods():
    """Every mod source in the repo except the hand-built debug probes: what a release is expected to contain."""
    names = {n[:-2] for n in os.listdir(os.path.join(REPO, 'src-latest', 'mods')) if n.endswith('.c')}
    return names - DEBUG_MODS


def check_build_release_refuses_an_output_folder_inside_the_repo(fake_repo):
    """Guards: binaries and zips landing inside the (public) repo tree, where one `git add -A` would commit them."""
    repo, stub = fake_repo
    res = build(repo, stub, repo / 'dist')
    assert res.returncode == 2 and 'outside the repo' in res.stderr
    assert [p for p in (repo / 'dist').rglob('*') if p.is_file()] == []
    assert git(repo, 'status', '--porcelain').stdout.strip() == ''


def check_release_zip_has_exactly_the_shipped_files_with_true_checksums(fake_repo, tmp_path):
    """Guards: a debug probe (simtrace, pitchtrace, seed) or compiler debris (.pdb, .lib) shipping in the zip, a built mod
    missing from it, stale files from an earlier build surviving in the stage folder, wrong or missing checksums, and
    a version in the file name that is not the git tag."""
    repo, stub = fake_repo
    out = tmp_path / 'dist'
    (out / 'stage').mkdir(parents=True)
    (out / 'stage' / 'left_over.dll').write_bytes(b'stale')
    res = build(repo, stub, out)
    assert res.returncode == 0, res.stderr
    zpath = res.stdout.strip().splitlines()[-1]
    assert os.path.basename(zpath) == 'bbfix-v9.9.9.zip'
    with zipfile.ZipFile(zpath) as z:
        names = {n.lstrip('./') for n in z.namelist() if not n.endswith('/')}
        data = {n.lstrip('./'): z.read(n) for n in z.namelist() if not n.endswith('/')}
    expected = {'bbfix.dll', 'bblaunch.exe', 'bbfix.ini.sample', 'README.txt', 'SHA256SUMS.txt'}
    expected |= {'mods/%s.dll' % m for m in shipped_mods()}
    assert names == expected, sorted(names ^ expected)
    sums = {}
    for line in data['SHA256SUMS.txt'].decode().splitlines():
        digest, _, path = line.partition('  ')
        sums[path.lstrip('./')] = digest
    sums.pop('SHA256SUMS.txt', None)            # its own line is the known bug pinned by the xfail test below
    assert set(sums) == expected - {'SHA256SUMS.txt'}
    for path, digest in sums.items():
        assert hashlib.sha256(data[path]).hexdigest() == digest, path
    # a modified tree is not passed off as the tag
    (repo / 'release' / 'README.txt').write_text('changed\n')
    dirty = build(repo, stub, tmp_path / 'dist2')
    assert dirty.returncode == 0 and os.path.basename(dirty.stdout.strip().splitlines()[-1]) == 'bbfix-v9.9.9-dirty.zip'


@pytest.mark.xfail(strict=True, reason='BUG: tools/build_release.sh redirects find|xargs sha256sum into SHA256SUMS.txt inside '
                   'the folder it is scanning, so the file lists itself with a hash that can never match and '
                   '`sha256sum -c SHA256SUMS.txt` ends FAILED (also in the v1.0.2 draft zip). Remove this marker when fixed.')
def test_shipped_sha256sums_verify_with_sha256sum_c(fake_repo, tmp_path):
    """Guards: a user checking the download with the checksum file the zip ships.

    The bug is a race (the redirect creates SHA256SUMS.txt while find is scanning), so one build can come out
    clean by luck. Build five times and require every one to verify, so the strict xfail does not flip at random."""
    repo, stub = fake_repo
    for i in range(5):
        res = build(repo, stub, tmp_path / f'dist{i}')
        assert res.returncode == 0, res.stderr
        unpacked = tmp_path / f'unpacked{i}'
        with zipfile.ZipFile(res.stdout.strip().splitlines()[-1]) as z:
            z.extractall(unpacked)
        check = run(['sha256sum', '-c', 'SHA256SUMS.txt'], cwd=str(unpacked))
        assert check.returncode == 0, check.stdout


def test_release_packaging_ships_exactly_the_documented_files(fake_repo, tmp_path):
    """Guards: output inside the repo, stray or missing files in the zip, version naming, and the shipped docs."""
    check_build_release_refuses_an_output_folder_inside_the_repo(fake_repo)
    check_release_zip_has_exactly_the_shipped_files_with_true_checksums(fake_repo, tmp_path)
    check_release_docs_and_sample_ini_match_what_the_zip_ships()


def check_release_docs_and_sample_ini_match_what_the_zip_ships():
    """Guards: a mod that is built but undocumented or missing from the sample ini, a sample ini that loads a DLL the zip
    does not contain (the game would log a failed load on every start), and a shipped mod that no longer checks the
    mod API version (it would load into a bbfix.dll with an incompatible hook table)."""
    shipped = shipped_mods()
    ini = open(os.path.join(REPO, 'release', 'bbfix.ini.sample'), encoding='latin-1').read()
    loads = re.findall(r'(?m)^load=(.*)$', ini)
    assert len(loads) == 1
    listed = {m for m in re.findall(r'mods\\([A-Za-z0-9_]+)\.dll', loads[0])}
    assert listed and listed <= shipped, sorted(listed - shipped)
    readme = open(os.path.join(REPO, 'release', 'README.txt'), encoding='latin-1').read()
    for mod in sorted(shipped):
        assert 'mods\\%s.dll' % mod in readme, '%s is shipped but release/README.txt does not describe it' % mod
    script = open(os.path.join(REPO, 'tools', 'build_release.sh')).read()
    for m in re.search(r'(?m)^for m in (.*); do$', script).group(1).split():
        assert m in shipped, '%s is built into the release but is a debug probe or has no source' % m
    for mod in sorted(shipped):
        src = open(os.path.join(REPO, 'src-latest', 'mods', mod + '.c'), encoding='latin-1').read()
        assert 'BBMOD_API_VERSION' in src, mod
    assert shipped <= set(re.search(r'(?m)^for m in (.*); do$', script).group(1).split()), \
        'a mod with a source file is not in build_release.sh and so is not in the zip'
