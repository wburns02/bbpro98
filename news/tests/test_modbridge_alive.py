"""The heartbeat the game reads to tell whether a bridge runs (modbridge.beat, beat_due): the line it writes, a symlink
planted as alive.tmp or alive.txt never written through, housekeeping keeping alive.txt, and the beat cadence.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import modbridge   # noqa: E402

NOW = 1700000000.0


def test_beat_writes_the_unix_time_as_an_int_line(tmp_path):
    modbridge.beat(str(tmp_path), now=NOW)
    assert modbridge.ALIVE == 'alive.txt'
    assert (tmp_path / 'alive.txt').read_bytes() == b'1700000000\n'
    assert os.listdir(tmp_path) == ['alive.txt']        # the temporary file is renamed away


def test_beat_truncates_a_fractional_time_and_defaults_to_now(tmp_path):
    modbridge.beat(str(tmp_path), now=NOW + 0.9)
    assert (tmp_path / 'alive.txt').read_text() == '1700000000\n'
    modbridge.beat(str(tmp_path))
    text = (tmp_path / 'alive.txt').read_text()
    assert text.endswith('\n') and text[:-1].isdigit() and abs(int(text) - os.path.getmtime(tmp_path / 'alive.txt')) < 5


def test_beat_replaces_the_previous_beat(tmp_path):
    modbridge.beat(str(tmp_path), now=NOW)
    modbridge.beat(str(tmp_path), now=NOW + 2)
    assert (tmp_path / 'alive.txt').read_text() == '1700000002\n'


@pytest.mark.parametrize('planted', ['alive.tmp', 'alive.txt'])
def test_a_planted_symlink_is_never_written_through(tmp_path, planted):
    spool = tmp_path / 'spool'
    spool.mkdir()
    victim = tmp_path / 'victim.txt'
    victim.write_text('keep')
    os.symlink(victim, spool / planted)
    modbridge.beat(str(spool), now=NOW)
    assert victim.read_text() == 'keep'
    assert not os.path.islink(spool / 'alive.txt')
    assert (spool / 'alive.txt').read_bytes() == b'1700000000\n'


def test_a_planted_dangling_symlink_is_never_created_through(tmp_path):
    spool = tmp_path / 'spool'
    spool.mkdir()
    target = tmp_path / 'not-yet.txt'
    os.symlink(target, spool / 'alive.tmp')
    modbridge.beat(str(spool), now=NOW)
    assert not target.exists()
    assert (spool / 'alive.txt').read_bytes() == b'1700000000\n'


def test_a_symlinked_spool_is_never_beaten_through(tmp_path):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    os.symlink(elsewhere, tmp_path / 'spool')
    with pytest.raises(OSError):
        modbridge.beat(str(tmp_path / 'spool'), now=NOW)
    assert os.listdir(elsewhere) == []


def test_housekeeping_keeps_alive_txt_however_old(tmp_path):
    modbridge.beat(str(tmp_path), now=NOW)
    os.utime(tmp_path / 'alive.txt', (NOW - 1000, NOW - 1000))
    (tmp_path / 'r00000001.rsp').write_bytes(b'x')
    os.utime(tmp_path / 'r00000001.rsp', (NOW - 1000, NOW - 1000))
    modbridge.housekeep(str(tmp_path), now=NOW + 100 * modbridge.STALE)
    assert os.listdir(tmp_path) == ['alive.txt']


def test_a_beat_is_due_on_the_first_pass_and_every_alive_every():
    assert modbridge.ALIVE_EVERY == 2
    assert modbridge.beat_due(None, now=0.0)
    assert not modbridge.beat_due(100.0, now=100.0)
    assert not modbridge.beat_due(100.0, now=100.0 + modbridge.ALIVE_EVERY - 0.01)
    assert modbridge.beat_due(100.0, now=100.0 + modbridge.ALIVE_EVERY)
    assert modbridge.beat_due(100.0, now=500.0)
