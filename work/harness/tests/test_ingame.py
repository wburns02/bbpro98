"""ingame's state save and restore (listing, is_state, save_state, restore_state, norm) on a fake work copy."""
import os
import shutil
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingame  # noqa: E402

MIB = 4 << 20


@pytest.fixture
def fake(tmp_path, monkeypatch):
    work = tmp_path / 'work'

    def put(rel, data):
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'wb') as fh:
            fh.write(data)
        return p

    monkeypatch.setattr(ingame, 'WORK', str(work))
    work.mkdir()
    assert os.path.realpath(ingame.WORK).startswith(str(tmp_path))
    assert not os.path.realpath(ingame.WORK).startswith('/mnt/nvme')
    put('BBPRO.INI', b'ini\n')                       # top-level small: state
    with open(work / 'BOUND.EXACT', 'wb') as fh:     # exactly 4 MiB: not state
        fh.seek(MIB - 1)
        fh.write(b'\0')
    assert (work / 'BOUND.EXACT').stat().st_size == MIB
    put('BOUND.LESS', b'\0' * (MIB - 1))             # one byte less: state
    with open(work / 'BIG.BIN', 'wb') as fh:         # 5 MB top-level, sparse: not state
        fh.seek(5 << 20)
        fh.write(b'\0')
    for rel in ('Assn/X.ASN', 'Stats/X.DAT', 'StatSets/S.SS', 'Archive/A.AR',
                'tapes/T.TP', 'hilights/H.HL'):
        put(rel, rel.encode())
    put('Data/big.bin', b'\0' * 1024)                # non-state subdir
    put('Data/small.txt', b'hello\n')
    return work


STATE_RELS = ('BBPRO.INI', 'BOUND.LESS', 'Assn/X.ASN', 'Stats/X.DAT', 'StatSets/S.SS',
              'Archive/A.AR', 'tapes/T.TP', 'hilights/H.HL')


def test_is_state_top_level_small(fake):
    assert ingame.is_state('BBPRO.INI', 4)


def test_is_state_boundary_exact_and_below(fake):
    assert not ingame.is_state('BOUND.EXACT', MIB)
    assert ingame.is_state('BOUND.LESS', MIB - 1)


def test_is_state_top_level_5mb_not_state(fake):
    assert not ingame.is_state('BIG.BIN', 5 << 20)


@pytest.mark.parametrize('rel', ['Assn/X.ASN', 'Stats/X.DAT', 'StatSets/S.SS',
                                 'Archive/A.AR', 'tapes/T.TP', 'hilights/H.HL'])
def test_is_state_state_dirs_members(fake, rel):
    assert ingame.is_state(rel, 1 << 30)


def test_is_state_nested_non_state(fake):
    assert not ingame.is_state(os.path.join('Data', 'big.bin'), 1024)


def test_is_state_nested_file_in_state_dir_any_size(fake):
    assert ingame.is_state(os.path.join('Stats', 'HUGE.DAT'), 1 << 30)


def test_save_state_copies_only_state_files_and_returns_listing(fake, tmp_path):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    copied = {os.path.relpath(p, dst) for p in dst.rglob('*') if p.is_file()}
    assert copied == set(STATE_RELS)
    assert 'Data/big.bin' not in copied and 'BIG.BIN' not in copied
    assert set(before) == {rel for rel, _ in
                           [('BBPRO.INI', 0), ('BOUND.EXACT', 0), ('BOUND.LESS', 0), ('BIG.BIN', 0),
                            ('Assn/X.ASN', 0), ('Stats/X.DAT', 0), ('StatSets/S.SS', 0),
                            ('Archive/A.AR', 0), ('tapes/T.TP', 0), ('hilights/H.HL', 0),
                            ('Data/big.bin', 0), ('Data/small.txt', 0)]}
    assert set(ingame.listing()) == set(before)
    assert before['BBPRO.INI'][0] == (dst / 'BBPRO.INI').stat().st_size


def test_restore_state_removes_new_files(fake, tmp_path, capsys):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    (fake / 'Assn' / 'NEW.ASN').write_bytes(b'new')
    (fake / 'Data' / 'NEW.DAT').write_bytes(b'new')
    assert ingame.restore_state(str(dst), before, []) is True
    assert not (fake / 'Assn' / 'NEW.ASN').exists()
    assert not (fake / 'Data' / 'NEW.DAT').exists()
    out = capsys.readouterr().out
    assert 'removed new file Assn/NEW.ASN' in out
    assert 'removed new file Data/NEW.DAT' in out


def test_restore_state_restores_changed_state_files_byte_for_byte(fake, tmp_path):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    (fake / 'Assn' / 'X.ASN').write_bytes(b'changed')
    (fake / 'BBPRO.INI').write_bytes(b'changed too')
    assert ingame.restore_state(str(dst), before, []) is True
    assert (fake / 'Assn' / 'X.ASN').read_bytes() == b'Assn/X.ASN'
    assert (fake / 'BBPRO.INI').read_bytes() == b'ini\n'
    assert ingame.listing() == before


def test_restore_state_leaves_installed_paths_alone(fake, tmp_path):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    (fake / 'BBPRO.INI').write_bytes(b'edit still installed')
    (fake / 'Stats' / 'X.DAT').write_bytes(b'also installed')
    assert ingame.restore_state(str(dst), before, ['BBPRO.INI', 'Stats/X.DAT']) is True
    assert (fake / 'BBPRO.INI').read_bytes() == b'edit still installed'
    assert (fake / 'Stats' / 'X.DAT').read_bytes() == b'also installed'


def test_restore_state_reports_changed_non_state_and_returns_false(fake, tmp_path, capsys):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    (fake / 'Data' / 'small.txt').write_bytes(b'clobbered\n')
    assert ingame.restore_state(str(dst), before, []) is False
    assert (fake / 'Data' / 'small.txt').read_bytes() == b'clobbered\n'
    out = capsys.readouterr().out
    assert 'CHANGED (not restorable): Data/small.txt' in out
    assert 'restored state file' not in out
    assert 'removed new file' not in out


def test_restore_state_returns_true_when_nothing_changed(fake, tmp_path, capsys):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    assert ingame.listing() == before
    assert ingame.restore_state(str(dst), before, []) is True
    assert capsys.readouterr().out == ''


def test_restore_state_mtime_only_change_is_restored_and_clean(fake, tmp_path, capsys):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    p = fake / 'Assn' / 'X.ASN'
    p.write_bytes(p.read_bytes())
    os.utime(p, ns=(before['Assn/X.ASN'][1] + 1_000_000, before['Assn/X.ASN'][1] + 1_000_000))
    assert ingame.listing()['Assn/X.ASN'] != before['Assn/X.ASN']
    assert p.stat().st_size == before['Assn/X.ASN'][0]
    assert ingame.restore_state(str(dst), before, []) is True
    assert ingame.listing() == before
    assert 'restored state file Assn/X.ASN' in capsys.readouterr().out


def test_restore_state_removed_state_file_is_restored(fake, tmp_path):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    (fake / 'tapes' / 'T.TP').unlink()
    assert ingame.restore_state(str(dst), before, []) is True
    assert (fake / 'tapes' / 'T.TP').read_bytes() == b'tapes/T.TP'
    assert ingame.listing() == before


def test_full_round_trip_like_a_run(fake, tmp_path):
    dst = tmp_path / 'save'
    before = ingame.save_state(str(dst))
    (fake / 'BBPRO.INI').write_bytes(b'rewritten')
    before_ns = before['Assn/X.ASN'][1]
    p = fake / 'Assn' / 'X.ASN'
    p.write_bytes(b'touched')
    os.utime(p, ns=(before_ns + 2, before_ns + 2))
    (fake / 'game.sav').write_bytes(b'leftover')
    (fake / 'Data' / 'big.bin').write_bytes(b'\x01' * 1024)
    assert ingame.restore_state(str(dst), before, ['BBPRO.INI']) is False
    assert (fake / 'BBPRO.INI').read_bytes() == b'rewritten'
    assert (fake / 'Assn' / 'X.ASN').read_bytes() == b'Assn/X.ASN'
    assert not (fake / 'game.sav').exists()
    assert (fake / 'Data' / 'big.bin').read_bytes() == b'\x01' * 1024


def test_norm_collapses_whitespace_and_lowercases(fake):
    assert ingame.norm('  THE   Game\n\t is\tOver  ') == 'the game is over'
    assert ingame.norm('NO CHANGES') == 'no changes'
    assert ingame.norm('') == ''
    assert ingame.norm('\n \t \n') == ''


def test_state_dirs_contract(fake):
    assert ingame.STATE_DIRS == ('Assn', 'Archive', 'Stats', 'StatSets', 'tapes', 'hilights')
