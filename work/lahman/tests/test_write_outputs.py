"""build.write_outputs and ratings.pyr_bytes: the build never replaces or writes through an existing association, and
the ASN lands last. Everything is under pytest's tmp_path; no game file is read."""
import datetime
import os
import types

import pytest

from lahman import build as B, ratings as RT

EXTS = ('ASN', 'PYR', 'PYF', 'DAT')
NEW = {'ASN': b'new asn', 'PYR': b'new pyr', 'PYF': b'new pyf', 'DAT': b'new dat'}
OLD = {'ASN': b'old asn', 'PYR': b'old pyr', 'PYF': b'old pyf', 'DAT': b'old dat'}


@pytest.fixture
def install(tmp_path):
    (tmp_path / 'Assn').mkdir()
    (tmp_path / 'Stats').mkdir()
    return tmp_path


def paths(install, name='16L1927'):
    return {'ASN': install / 'Assn' / (name + '.ASN'), 'PYR': install / 'Assn' / (name + '.PYR'),
            'PYF': install / 'Assn' / (name + '.PYF'), 'DAT': install / 'Stats' / (name + '.DAT')}


def put(install, blobs, name='16L1927'):
    for ext, path in paths(install, name).items():
        path.write_bytes(blobs[ext])


def tree(install):
    return sorted(os.path.relpath(os.path.join(d, f), install) for d, _, fs in os.walk(install) for f in fs)


def fixed_clock(monkeypatch, stamp=(2026, 10, 15, 9, 8, 7)):
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(*stamp)

    monkeypatch.setattr(B, 'datetime', types.SimpleNamespace(datetime=Clock, date=datetime.date))


def test_empty_install_gets_the_four_files_and_no_tmp(install):
    out = B.write_outputs(str(install), '16L1927', NEW)
    assert out == {ext: str(p) for ext, p in paths(install).items()}
    for ext, p in paths(install).items():
        assert p.read_bytes() == NEW[ext]
    assert tree(install) == ['Assn/16L1927.ASN', 'Assn/16L1927.PYF', 'Assn/16L1927.PYR', 'Stats/16L1927.DAT']


@pytest.mark.parametrize('have, first', [(('ASN',), 'ASN'), (('DAT',), 'DAT'), (('PYF', 'DAT'), 'PYF'),
                                         (('DAT', 'PYR'), 'PYR')])
def test_an_existing_target_is_refused_and_nothing_changes(install, have, first):
    for ext in have:
        paths(install)[ext].write_bytes(OLD[ext])
    before = {f: (install / f).read_bytes() for f in tree(install)}
    with pytest.raises(SystemExit) as e:
        B.write_outputs(str(install), '16L1927', NEW)
    assert str(e.value) == '%s already exists; pass --force to replace it (a copy is kept)' % paths(install)[first]
    assert {f: (install / f).read_bytes() for f in tree(install)} == before


def test_force_keeps_a_copy_and_a_second_force_in_the_same_second_gets_a_new_folder(install, monkeypatch):
    fixed_clock(monkeypatch)
    put(install, OLD)
    log = []
    B.write_outputs(str(install), '16L1927', NEW, force=True, log=log.append)
    first = install / 'build-backup' / '16L1927-20261015T090807'
    assert log == ['kept a copy of the existing 16L1927 files in %s' % first]
    assert {f: (first / f).read_bytes() for f in os.listdir(first)} == {'16L1927.' + ext: OLD[ext] for ext in EXTS}
    for ext, p in paths(install).items():
        assert p.read_bytes() == NEW[ext]
    newer = {ext: b'newer ' + ext.encode() for ext in EXTS}
    B.write_outputs(str(install), '16L1927', newer, force=True)
    second = install / 'build-backup' / '16L1927-20261015T090807-2'
    assert {f: (second / f).read_bytes() for f in os.listdir(second)} == {'16L1927.' + ext: NEW[ext] for ext in EXTS}
    B.write_outputs(str(install), '16L1927', NEW, force=True)
    third = install / 'build-backup' / '16L1927-20261015T090807-3'
    assert {f: (third / f).read_bytes() for f in os.listdir(third)} == {'16L1927.' + ext: newer[ext] for ext in EXTS}
    for ext, p in paths(install).items():
        assert p.read_bytes() == NEW[ext]


def test_the_backup_folder_is_named_for_the_upper_case_name(install, monkeypatch):
    fixed_clock(monkeypatch)
    put(install, OLD, '16n1942')
    B.write_outputs(str(install), '16n1942', NEW, force=True)
    assert os.listdir(install / 'build-backup') == ['16N1942-20261015T090807']


def test_force_copies_only_the_files_that_exist(install, monkeypatch):
    fixed_clock(monkeypatch)
    paths(install)['DAT'].write_bytes(OLD['DAT'])
    B.write_outputs(str(install), '16L1927', NEW, force=True)
    folder = install / 'build-backup' / '16L1927-20261015T090807'
    assert os.listdir(folder) == ['16L1927.DAT'] and (folder / '16L1927.DAT').read_bytes() == OLD['DAT']


def test_force_into_an_empty_install_makes_no_backup(install):
    B.write_outputs(str(install), '16L1927', NEW, force=True)
    assert not (install / 'build-backup').exists()


@pytest.mark.parametrize('force', [False, True])
@pytest.mark.parametrize('ext', EXTS)
def test_a_symlink_at_any_target_is_refused_and_its_target_is_untouched(install, tmp_path_factory, ext, force):
    donor = tmp_path_factory.mktemp('donor') / 'real'
    donor.write_bytes(b'donor')
    target = paths(install)[ext]
    os.symlink(donor, target)
    with pytest.raises(SystemExit) as e:
        B.write_outputs(str(install), '16L1927', NEW, force=force)
    assert str(target) in str(e.value)
    assert donor.read_bytes() == b'donor' and os.path.islink(target)
    assert not any(f.endswith('.tmp') for f in tree(install)) and not (install / 'build-backup').exists()
    assert sorted(f for f in tree(install) if not f.endswith(ext)) == []


def test_a_dangling_symlink_is_refused_too(install, tmp_path):
    os.symlink(tmp_path / 'nowhere', paths(install)['PYR'])
    with pytest.raises(SystemExit):
        B.write_outputs(str(install), '16L1927', NEW, force=True)
    assert not (tmp_path / 'nowhere').exists()


@pytest.mark.parametrize('name', ['MLBPA96E', 'mlbpa97', 'MlbPa97', '_Default', '_DEFAULT'])
@pytest.mark.parametrize('force', [False, True])
def test_reserved_names_are_refused(install, name, force):
    with pytest.raises(SystemExit) as e:
        B.write_outputs(str(install), name, NEW, force=force)
    assert str(e.value) == 'refusing to write %s: a reserved association name' % name
    assert tree(install) == []


def test_main_refuses_a_reserved_name_before_any_work(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError('work was started')

    monkeypatch.setattr(B.lahdb, 'connect', boom)
    monkeypatch.setattr(B, 'build', boom)
    for name in ('MLBPA97', 'mlbpa96e', '_default'):
        with pytest.raises(SystemExit) as e:
            B.main(['--year', '1927', '--install', 'nowhere', '--name', name])
        assert e.value.code == 2
    assert 'reserved association name' in capsys.readouterr().err


def test_main_passes_force_to_build(monkeypatch):
    seen = []
    monkeypatch.setattr(B.lahdb, 'connect', lambda db: None)
    monkeypatch.setattr(B.lahdb, 'year_range', lambda con, leagues: (1871, 2025))
    monkeypatch.setattr(B, 'build', lambda *a, **k: seen.append((a, k)))
    for argv, force in ((['--force'], True), ([], False)):
        assert B.main(['--year', '1927', '--install', 'x', '--name', 'MINE'] + argv) == 0
        assert seen[-1][1]['force'] is force


def test_files_land_in_the_order_dat_pyf_pyr_asn(install, monkeypatch):
    order = []
    real = os.replace
    monkeypatch.setattr(os, 'replace', lambda src, dst: (order.append(os.path.basename(dst)), real(src, dst))[1])
    B.write_outputs(str(install), '16L1927', NEW)
    assert order == ['16L1927.DAT', '16L1927.PYF', '16L1927.PYR', '16L1927.ASN']


def test_a_failure_writing_the_pyr_leaves_no_tmp_and_no_asn(install, monkeypatch):
    real = os.replace

    def replace(src, dst):
        if dst.endswith('.PYR'):
            raise OSError('disk full')
        real(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(OSError, match='disk full'):
        B.write_outputs(str(install), '16L1927', NEW)
    assert not paths(install)['ASN'].exists()
    assert not any(f.endswith('.tmp') for f in tree(install))
    assert tree(install) == ['Assn/16L1927.PYF', 'Stats/16L1927.DAT']


def test_a_failure_while_writing_the_bytes_removes_the_tmp(install):
    with pytest.raises(TypeError):
        B.write_outputs(str(install), '16L1927', dict(NEW, PYR='not bytes'))
    assert not any(f.endswith('.tmp') for f in tree(install))
    assert not paths(install)['ASN'].exists()


# ratings.pyr_bytes

def pyr_input(n=2):
    header = bytes([0x6b, 0xe2]) + bytes(range(2, RT.REC))
    return header, [bytes((i * 7 + j) % 256 for j in range(RT.REC)) for i in range(n)]


def old_write_pyr(path, header, recs):
    """write_pyr as it was before pyr_bytes."""
    t, _ = RT.cipher((header[0], header[1]))
    with open(path, 'wb') as fh:
        fh.write(header)
        for r in recs:
            if len(r) != RT.REC:
                raise ValueError('record of %d bytes' % len(r))
            fh.write(bytes(t[b] for b in r))


def test_pyr_bytes_is_what_write_pyr_wrote_before(tmp_path):
    header, recs = pyr_input()
    old_write_pyr(tmp_path / 'old.PYR', header, recs)
    RT.write_pyr(str(tmp_path / 'new.PYR'), header, recs)
    got = RT.pyr_bytes(header, recs)
    assert got == (tmp_path / 'old.PYR').read_bytes() == (tmp_path / 'new.PYR').read_bytes()
    assert len(got) == RT.REC * 3 and got[:RT.REC] == header and got[RT.REC:2 * RT.REC] != recs[0]


def test_pyr_bytes_round_trips_through_read_pyr(tmp_path):
    header, recs = pyr_input()
    (tmp_path / 'x.PYR').write_bytes(RT.pyr_bytes(header, recs))
    assert RT.read_pyr(str(tmp_path / 'x.PYR')) == (header, recs)


@pytest.mark.parametrize('size', [0, RT.REC - 1, RT.REC + 1])
def test_a_wrong_size_record_raises_value_error(tmp_path, size):
    header, recs = pyr_input()
    with pytest.raises(ValueError, match='record of %d bytes' % size):
        RT.pyr_bytes(header, recs + [bytes(size)])
    with pytest.raises(ValueError):
        RT.write_pyr(str(tmp_path / 'x.PYR'), header, recs + [bytes(size)])
