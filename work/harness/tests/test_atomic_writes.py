"""atomicfile.write_atomic and the patch tools that rewrite game files with it (synthetic files only).

A hard link to the target is the witness: a write in place changes both names, a replace leaves the old inode alone."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WORK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORK))
import atomicfile  # noqa: E402
import volcodec  # noqa: E402


def test_write_atomic_keeps_mode_and_symlinks_and_leaves_no_temp(tmp_path):
    f = tmp_path / 'BBShell.dll'
    f.write_bytes(b'old')
    f.chmod(0o755)
    link = tmp_path / 'link.dll'
    link.symlink_to(f)
    atomicfile.write_atomic(str(link), b'new')
    assert link.is_symlink() and f.read_bytes() == b'new' and (f.stat().st_mode & 0o777) == 0o755
    atomicfile.write_atomic(str(tmp_path / 'fresh.bin'), b'x')
    assert (tmp_path / 'fresh.bin').read_bytes() == b'x'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['BBShell.dll', 'fresh.bin', 'link.dll']


def test_write_atomic_failure_keeps_the_old_file(tmp_path, monkeypatch):
    f = tmp_path / 'SHELL.VOL'
    f.write_bytes(b'old')

    def boom(fd):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(atomicfile.os, 'fsync', boom)
    with pytest.raises(OSError):
        atomicfile.write_atomic(str(f), b'new bytes')
    assert f.read_bytes() == b'old' and [p.name for p in tmp_path.iterdir()] == ['SHELL.VOL']


def test_bytepatch_replaces_the_file_instead_of_writing_it_in_place(tmp_path):
    dll = tmp_path / 'BBShell.dll'
    dll.write_bytes(bytes(range(32)))
    twin = tmp_path / 'twin.dll'
    os.link(dll, twin)
    r = subprocess.run([sys.executable, str(WORK / 'patches' / 'bytepatch.py'), str(dll), '4', '0405', 'aabb'],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert dll.read_bytes()[4:6] == b'\xaa\xbb' and twin.read_bytes() == bytes(range(32))


def test_volcodec_pack_replaces_the_archive(tmp_path):
    (tmp_path / 'a.bin').write_bytes(b'hello world' * 20)
    (tmp_path / 'manifest.json').write_text(json.dumps({'entries': [{'name': 'A.TXT', 'file': 'a.bin'}], 'meta': {}}))
    out = tmp_path / 'SHELL.VOL'
    out.write_bytes(b'old archive')
    twin = tmp_path / 'twin.vol'
    os.link(out, twin)
    volcodec.pack(str(tmp_path), str(out))
    assert twin.read_bytes() == b'old archive' and out.read_bytes()[:4] == volcodec.MAGIC
    back = tmp_path / 'back'
    back.mkdir()
    volcodec.unpack(str(out), str(back))
    entry = json.loads((back / 'manifest.json').read_text())['entries'][0]
    assert (back / entry['file']).read_bytes() == b'hello world' * 20


def _art(d):
    Image = pytest.importorskip('PIL.Image')
    pal = list(range(256)) * 3
    for state in ('NORM', 'HI', 'SEL'):
        for name, w, ink in (('WEB', 144, 5), ('LM', 144, 9), ('EXHB', 144, 10), ('BUTN', 300, 11)):
            im = Image.new('P', (w, 33), ink)
            im.putpalette(pal)
            im.save(d / ('%s%s.BMP' % (name, state)))


def test_mods_button_replaces_the_art_and_keeps_a_whole_original(tmp_path):
    _art(tmp_path)
    web = tmp_path / 'WEBNORM.BMP'
    before = web.read_bytes()
    twin = tmp_path / 'twin.bmp'
    os.link(web, twin)
    r = subprocess.run([sys.executable, str(WORK / 'patches' / 'mods_button.py'), str(tmp_path)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert web.read_bytes() != before, 'the synthetic art must compose to new bytes or the twin proves nothing'
    assert (tmp_path / 'WEBNORM.BMP.orig').read_bytes() == before and twin.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.name.endswith('.tmp')]


@pytest.mark.parametrize('tool', ['bytepatch.py', 'narrow_cols.py', 'patch_ext.py', 'mods_button.py'])
def test_patch_tools_never_open_their_target_for_writing(tool):
    src = (WORK / 'patches' / tool).read_text()
    assert "'wb')" not in src and '"wb")' not in src and '.save(web)' not in src and 'write_atomic' in src


def test_patch_ext_refuses_a_dll_too_short_for_the_cave(tmp_path):
    """An empty slice passes the cave-free check, so a short file must be refused by length first."""
    dll = tmp_path / 'BBShell.dll'
    dll.write_bytes(bytes(0x80480 - 0xc00))
    before = dll.read_bytes()
    r = subprocess.run([sys.executable, str(WORK / 'patches' / 'patch_ext.py'), str(dll)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and 'too short' in r.stderr, r.stderr
    assert dll.read_bytes() == before
