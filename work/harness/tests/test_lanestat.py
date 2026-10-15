"""Tests for lanestat.py (pure helpers; no game, Wine, xdotool or ImageMagick)."""
import json
import os
import sys
import time
from pathlib import Path

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


# ---- status ----------------------------------------------------------------

class _Ingame:
    WORK = str(Path('/does/not/exist'))

    @staticmethod
    def game_pids():
        return ['77']

    @staticmethod
    def shot(png):
        pass


def test_status_one_shot_keys(monkeypatch):
    monkeypatch.setitem(sys.modules, 'ingame', _Ingame)
    sleeps = []
    monkeypatch.setattr(time, 'sleep', lambda s: sleeps.append(s))
    fake = {'n': 0}

    def fake_ticks(pid, proc='/proc'):
        fake['n'] += 1
        return 100 if fake['n'] == 1 else 300

    monkeypatch.setattr(lanestat, 'ticks', fake_ticks)
    s = lanestat.status('2', secs=0.1, no_shot=True)
    assert sorted(s) == ['dticks', 'lane', 'newest', 'pids', 'screen', 'trace', 'verdict']
    assert s['lane'] == '2'
    assert s['pids'] == ['77']
    assert s['dticks'] == 200 and s['verdict'] == 'working'
    assert s['newest'] == {'path': None, 'age_s': None}
    assert s['trace'] == {'line': None, 'age_s': None}
    assert s['screen'] is None
    assert os.environ['BBLANE'] == '2' and sleeps == [0.1]


def test_main_one_shot_output_unchanged(monkeypatch, capsys):
    class _None:
        WORK = str(Path('/does/not/exist'))

        @staticmethod
        def game_pids():
            return []

        @staticmethod
        def shot(png):
            pass

    monkeypatch.setitem(sys.modules, 'ingame', _None)
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    monkeypatch.setattr(lanestat, 'ticks', lambda pid, proc='/proc': 5)
    assert lanestat.main(['--lane', '2', '--no-shot']) == 0
    obj = json.loads(capsys.readouterr().out)
    assert sorted(obj) == sorted(['lane', 'pids', 'dticks', 'newest', 'trace', 'screen', 'verdict'])
    assert obj['verdict'] == 'no_game'


# ---- watch -----------------------------------------------------------------

def fake_clock_log(seq, out_lines, fake_time):
    def status_fn(lane, secs, shot, no_shot):
        out_lines.append(('call', seq[0][0] if seq else '?'))
        s = {'verdict': seq[0][1], 'newest': {'path': seq[0][2], 'age_s': None}}
        del seq[0]
        return s

    def slp(_):
        pass

    return status_fn, slp


def run_watch(seq, heartbeat=100.0, limit=None, start=1000.0):
    """Drive watch with per-call (verdict, path) steps; each step advances the fake clock 1 s."""
    lines = []
    it = list(seq)

    def status_fn(lane, secs, shot, no_shot):
        v, p = it.pop(0)
        return {'verdict': v, 'newest': {'path': p, 'age_s': None}}

    fake = {'now': start}

    def clock():
        return fake['now']

    def slp(_):
        fake['now'] += 1.0

    rc = lanestat.watch('1', 1, secs=0.1, no_shot=True, heartbeat=heartbeat,
                        status_fn=status_fn, out=lines.append, clock=clock, sleep=slp, limit=len(seq))
    return rc, [json.loads(x) for x in lines]


def test_watch_first_change_path_heartbeat_unchanged():
    # 202 calls, 1 s apart: heartbeats at 1100 and 1200, nothing beyond.
    rc, lines = run_watch([('working', '/a')] * 202, heartbeat=100.0)
    assert rc == 0
    assert [x['why'] for x in lines] == ['first'] + ['heartbeat'] * 2
    assert 't' in lines[0] and lines[0]['verdict'] == 'working'


def test_watch_change_on_verdict_and_on_path():
    rc, lines = run_watch([('working', '/a'), ('idle', '/a'), ('idle', '/b')])
    assert rc == 0
    assert [x['why'] for x in lines] == ['first', 'change', 'change']
    assert lines[1]['verdict'] == 'idle' and lines[2]['newest']['path'] == '/b'


def test_watch_no_emit_for_unchanged_inside_heartbeat():
    rc, lines = run_watch([('working', '/a')] * 10, heartbeat=100.0)
    assert rc == 0
    assert [x['why'] for x in lines] == ['first']


def test_watch_limit_stops_after_n_calls():
    calls = []

    def status_fn(lane, secs, shot, no_shot):
        calls.append(1)
        return {'verdict': 'working', 'newest': {'path': '/a', 'age_s': None}}

    rc = lanestat.watch('1', 1, status_fn=status_fn, out=lambda s: None, clock=time.time,
                        sleep=lambda _: None, limit=3)
    assert rc == 0 and len(calls) == 3


def test_watch_keyboard_interrupt_returns_0_quietly():
    calls = []

    def status_fn(lane, secs, shot, no_shot):
        calls.append(1)
        return {'verdict': 'working', 'newest': {'path': '/a', 'age_s': None}}

    def slp(_):
        raise KeyboardInterrupt

    rc = lanestat.watch('1', 1, status_fn=status_fn, out=lambda s: None, clock=time.time, sleep=slp)
    assert rc == 0 and len(calls) == 1


# ---- flag parsing ----------------------------------------------------------

def test_watch_flag_with_shot_exits_2():
    with pytest.raises(SystemExit) as e:
        lanestat.main(['--watch', '5', '--shot', '/tmp/x.png'])
    assert e.value.code == 2


def test_watch_zero_exits_2():
    with pytest.raises(SystemExit) as e:
        lanestat.main(['--watch', '0'])
    assert e.value.code == 2


def test_heartbeat_negative_exits_2():
    with pytest.raises(SystemExit) as e:
        lanestat.main(['--watch', '5', '--heartbeat', '-1'])
    assert e.value.code == 2


def test_trace_age_a_stamp_just_ahead_of_now_is_fresh():
    import datetime
    now = datetime.datetime(2026, 10, 15, 12, 0, 0)
    assert lanestat.trace_age('12:00:01.250 HANDLES', now=now) == 0.0
    assert lanestat.trace_age('11:59:50.000 x', now=now) == 10.0
    assert lanestat.trace_age('12:10:00.000 x', now=now) == 86400.0 - 600.0
