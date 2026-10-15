"""Tests for lanestat.py (pure helpers; no game, Wine, xdotool or ImageMagick)."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'harness'))
import lanestat  # noqa: E402


def make(p, data=b'x'):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as fh:
        fh.write(data * 1024 if isinstance(data, int) else data)
    return p


# ---- ticks -----------------------------------------------------------------

def test_ticks_fake_proc_with_parens(tmp_path):
    pid = tmp_path / '4242'
    pid.mkdir()
    cmd = b'(Baseball (weekend) 97) R 1 2 3 4 5 6 7 8 9 10 700 300 0 0'
    (pid / 'stat').write_bytes(cmd)
    assert lanestat.ticks(4242, proc=str(tmp_path)) == 1000


def test_ticks_pid_gone(tmp_path):
    assert lanestat.ticks(999999, proc=str(tmp_path)) is None


# ---- newest ----------------------------------------------------------------

def test_newest_skips_missing_dir(tmp_path):
    make(str(tmp_path / 'Assn' / 'a.ASN'))
    os.utime(str(tmp_path / 'Assn' / 'a.ASN'), (100, 100))
    make(str(tmp_path / 'Stats' / 's.HOF'))
    os.utime(str(tmp_path / 'Stats' / 's.HOF'), (200, 200))
    p, m = lanestat.newest([str(tmp_path / 'nope'), str(tmp_path / 'Assn'), str(tmp_path / 'Stats')])
    assert p.endswith('s.HOF') and m == 200


def test_newest_none_when_all_missing(tmp_path):
    assert lanestat.newest([str(tmp_path / 'nope')]) == (None, None)


def test_newest_ignores_subdirs_and_links(tmp_path):
    os.makedirs(str(tmp_path / 'Assn' / 'sub'))
    make(str(tmp_path / 'Assn' / 'real.ASN'))
    os.symlink(str(tmp_path / 'Assn' / 'real.ASN'), str(tmp_path / 'Assn' / 'link.ASN'))
    p, _ = lanestat.newest([str(tmp_path / 'Assn')])
    assert p.endswith('real.ASN')


# ---- last_trace ------------------------------------------------------------

TRACE = (b'20:20:20.100 [0130] FILEW  open ShelPcx8\\Shell01.pcx -> FAILED err=3 (by msvcrt.dll+0x332d1)\n'
         b'20:32:57.137 [0138] CRTFDS in_use=5\n'
         b'20:32:57.137 [0138] HANDLES process=0 ...\n')


def _write_trace(tmp_path, body):
    p = str(tmp_path / 'bbtrace.log')
    with open(p, 'wb') as fh:
        fh.write(b'\n' * (3 * 1024 * 1024))
        fh.write(body)
    return p


def test_last_trace_skips_periodic(tmp_path):
    p = _write_trace(tmp_path, TRACE)
    assert lanestat.last_trace(p) == '20:20:20.100 [0130] FILEW  open ShelPcx8\\Shell01.pcx -> FAILED err=3 (by msvcrt.dll+0x332d1)'


def test_last_trace_reads_only_tail(tmp_path, monkeypatch):
    p = _write_trace(tmp_path, b'20:00:00.001 [0001] NOTE hello\n')
    with open(p, 'rb') as fh:
        assert fh.seek(0, 2) > 3 * 1024 * 1024
    bound = []
    real_open = open

    def bounded(fn, *a, **k):
        f = real_open(fn, *a, **k)

        class W:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                f.close()

            def __getattr__(self, name):
                return getattr(f, name)

            def read(self, *a, **k):
                bound.append(a[0] if a and isinstance(a[0], int) else 0)
                return f.read(*a, **k)
        return W()

    monkeypatch.setattr('builtins.open', bounded)
    assert lanestat.last_trace(p, tail=1000) == '20:00:00.001 [0001] NOTE hello'
    assert bound and max(bound) <= 1000


def test_last_trace_missing(tmp_path):
    with pytest.raises(OSError):
        lanestat.last_trace(str(tmp_path / 'none.log'))


# ---- screen ----------------------------------------------------------------

def test_screen(monkeypatch, tmp_path):
    png = str(tmp_path / 'x.png')
    calls = []

    def order(busy=False, champ=False, sched=False, assn=False, notice=None):
        def go(*a):
            name = a[0]
            calls.append(name)
            table = {'busy': busy, 'champ': champ, 'sched': sched, 'assn': assn}
            return table[name] if name in table else notice
        return go

    def set_sl(busy=False, champ=False, sched=False, assn=False, notice=None):
        f = order(busy, champ, sched, assn, notice)
        monkeypatch.setattr(lanestat.seasonloop, 'busy', lambda p: f('busy'))
        monkeypatch.setattr(lanestat.seasonloop, 'on_champ', lambda p: f('champ'))
        monkeypatch.setattr(lanestat.seasonloop, 'on_sched', lambda p: f('sched'))
        monkeypatch.setattr(lanestat.seasonloop, 'on_assn_data', lambda p: f('assn'))
        monkeypatch.setattr(lanestat.seasonloop, 'notice', lambda p: notice)

    set_sl(busy=True)
    assert lanestat.screen(png) == 'busy'
    set_sl(champ=True)
    assert lanestat.screen(png) == 'champ'
    set_sl(sched=True)
    assert lanestat.screen(png) == 'sched'
    set_sl(assn=True)
    assert lanestat.screen(png) == 'assn'
    set_sl(notice='fa')
    assert lanestat.screen(png) == 'fa'
    set_sl(notice='spring')
    assert lanestat.screen(png) == 'spring'
    set_sl()
    assert lanestat.screen(png) == 'other'


# ---- verdict ---------------------------------------------------------------

def test_verdict_no_game():
    assert lanestat.verdict(None, None, None, 'other') == 'no_game'
    assert lanestat.verdict(None, 1, 1, 'busy') == 'no_game'


def test_verdict_working_by_ticks():
    assert lanestat.verdict(21, None, None, 'other') == 'working'


def test_verdict_working_by_write():
    assert lanestat.verdict(0, 60, None, 'other') == 'working'


def test_verdict_working_by_trace():
    assert lanestat.verdict(0, None, 10, 'other') == 'working'


def test_verdict_stale_paint():
    assert lanestat.verdict(0, None, None, 'busy') == 'stale_paint'


def test_verdict_idle():
    assert lanestat.verdict(0, None, None, 'other') == 'idle'
    assert lanestat.verdict(0, None, None, 'sched') == 'idle'


def test_verdict_none_ages_count_old():
    assert lanestat.verdict(0, None, None, 'busy') == 'stale_paint'
    assert lanestat.verdict(0, None, None, 'assn') == 'idle'
