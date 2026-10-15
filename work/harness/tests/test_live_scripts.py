"""install_live.sh, revert_live.sh and probe_screen.sh, on scratch copies pointed at a temp tree (never the live game)."""
import os
import re
import subprocess
from pathlib import Path

import pytest

PATCHES = Path(__file__).resolve().parents[2] / 'patches'


def scratch(tmp_path, name, live, backup, vol=None, dll=None):
    """The script with its path line aimed at tmp_path and its running-game guard matching nothing."""
    text = (PATCHES / name).read_text()
    paths = 'LIVE=%s; B=%s' % (live, backup)
    if vol:
        paths += '; V=%s; D=%s' % (vol, dll)
    text, n = re.subn(r'^LIVE=.*$', lambda m: paths, text, count=1, flags=re.M)
    assert n == 1
    text = text.replace("Sierra.BBPRO_98.(bblaunch|Baseball)", 'bbpro98-test-no-such-proces[s]')
    assert 'BBPRO_98.(bblaunch' not in text and '/.bbpro98_prefix/drive_c' not in text
    p = tmp_path / name
    p.write_text(text)
    return p


@pytest.fixture
def tree(tmp_path):
    live, backup, build = tmp_path / 'live', tmp_path / 'backup', tmp_path / 'build'
    for d in (live, backup, build):
        d.mkdir()
    for f, data in (('BBShell.dll', b'shell'), ('bbfix.dll', b'old fix'), ('SHELL.VOL', b'old vol')):
        (live / f).write_bytes(data)
    for f, data in (('BBShell.dll', b'shell'), ('bbfix.dll', b'pristine fix'), ('SHELL.VOL', b'pristine vol')):
        (backup / f).write_bytes(data)
    (build / 'bbfix.dll').write_bytes(b'new fix')
    (build / 'SHELL_wide6.VOL').write_bytes(b'new vol')
    (build / 'aging.dll').write_bytes(b'aging')
    return live, backup, build


def run(script, env=None, args=()):
    e = dict(os.environ, MODS='')
    e.update(env or {})
    return subprocess.run(['bash', str(script), *args], capture_output=True, text=True, env=e, timeout=60)


def snapshot(d):
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob('*')) if p.is_file()}


def test_install_puts_every_file_in_place(tmp_path, tree):
    live, backup, build = tree
    s = scratch(tmp_path, 'install_live.sh', live, backup, build / 'SHELL_wide6.VOL', build / 'bbfix.dll')
    r = run(s, {'MODS': str(build / 'aging.dll')})
    assert r.returncode == 0 and 'installed' in r.stdout, r.stdout + r.stderr
    assert (live / 'bbfix.dll').read_bytes() == b'new fix' and (live / 'SHELL.VOL').read_bytes() == b'new vol'
    assert (live / 'mods' / 'aging.dll').read_bytes() == b'aging'
    assert 'load=mods\\aging.dll' in (live / 'bbfix.ini').read_text()
    assert not list(live.rglob('*.new'))


def test_install_with_a_missing_source_changes_nothing(tmp_path, tree):
    live, backup, build = tree
    before = snapshot(live)
    s = scratch(tmp_path, 'install_live.sh', live, backup, build / 'gone.VOL', build / 'bbfix.dll')
    r = run(s)
    assert r.returncode == 5 and 'REFUSED' in r.stdout
    assert snapshot(live) == before


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads a mode 000 file')
def test_install_that_fails_mid_copy_leaves_the_old_install(tmp_path, tree):
    live, backup, build = tree
    before = snapshot(live)
    (build / 'SHELL_wide6.VOL').chmod(0)
    s = scratch(tmp_path, 'install_live.sh', live, backup, build / 'SHELL_wide6.VOL', build / 'bbfix.dll')
    r = run(s)
    assert r.returncode == 1 and 'unchanged' in r.stdout
    assert snapshot(live) == before


def test_revert_restores_all_three_and_drops_the_ini(tmp_path, tree):
    live, backup, _ = tree
    (live / 'bbfix.ini').write_text('[widen]\n')
    r = run(scratch(tmp_path, 'revert_live.sh', live, backup))
    assert r.returncode == 0 and 'reverted' in r.stdout
    assert snapshot(live) == snapshot(backup)


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads a mode 000 file')
def test_revert_that_cannot_read_a_backup_changes_nothing(tmp_path, tree):
    live, backup, _ = tree
    (live / 'bbfix.ini').write_text('[widen]\n')
    before = snapshot(live)
    (backup / 'BBShell.dll').chmod(0)
    r = run(scratch(tmp_path, 'revert_live.sh', live, backup))
    assert r.returncode == 1 and 'unchanged' in r.stdout
    assert snapshot(live) == before


def test_revert_with_a_missing_backup_changes_nothing(tmp_path, tree):
    live, backup, _ = tree
    before = snapshot(live)
    (backup / 'SHELL.VOL').unlink()
    r = run(scratch(tmp_path, 'revert_live.sh', live, backup))
    assert r.returncode == 5 and snapshot(live) == before


@pytest.mark.parametrize('args', [(), ('shot', '1', '2', '3'), ('a;b', '1', '2', '3', '4'),
                                  ('shot', '1', '2', '3', '$(id)'), ('shot', '1', '2', '3', '4 5')])
def test_probe_screen_rejects_bad_arguments_before_touching_anything(args):
    # Only argument sets the script refuses: a valid one would restart the work copy's game.
    r = run(PATCHES / 'probe_screen.sh', args=args)
    assert r.returncode == 2 and 'usage' in r.stdout
