"""seasonloop.health() and the progress / waiting lines that carry it: lanestat's ticks and newest are stubbed, so no
process, no /proc and no real sleep is involved."""
import datetime
import json
import os
import sys
import time

from PIL import Image
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lanestat    # noqa: E402
import seasonloop  # noqa: E402


class _Lane:
    """A lane's ingame module as health() sees it: WORK, and game_pids when pids is not None."""
    def __init__(self, work, pids=None):
        self.WORK = str(work)
        self.keys, self.clicks = [], []
        if pids is not None:
            self.game_pids = lambda: pids

    def x(self, *a):
        self.keys.append(a)

    def click(self, *a):
        self.clicks.append(a)


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(time, 'sleep', lambda s: calls.append(s))
    return calls


def _ticks(monkeypatch, readings):
    """lanestat.ticks answers each pid's readings in order: {pid: [first, second, ...]}."""
    monkeypatch.setattr(lanestat, 'ticks', lambda pid: readings[pid].pop(0))


def _newest(monkeypatch, age):
    """lanestat.newest finds a file written `age` seconds ago (no file when age is None)."""
    monkeypatch.setattr(lanestat, 'newest', lambda dirs: (None, None) if age is None else ('f', time.time() - age))


def test_no_game_pids_attribute_is_no_game_and_never_sleeps(tmp_path, sleeps):
    got = seasonloop.health(_Lane(tmp_path))
    assert (got['verdict'], got['dticks']) == ('no_game', None)
    assert sleeps == []


def test_cpu_ticks_gained_is_working(tmp_path, monkeypatch, sleeps):
    _ticks(monkeypatch, {7: [100, 150]})
    _newest(monkeypatch, None)
    got = seasonloop.health(_Lane(tmp_path, [7]), secs=3.0)
    assert (got['verdict'], got['dticks']) == ('working', 50)
    assert sleeps == [3.0]


def test_a_recent_assn_write_is_working_without_ticks(tmp_path, monkeypatch, sleeps):
    _ticks(monkeypatch, {7: [100, 100]})
    _newest(monkeypatch, 10)
    got = seasonloop.health(_Lane(tmp_path, [7]))
    assert (got['verdict'], got['dticks']) == ('working', 0)
    assert 9 <= got['write_age_s'] <= 11


def test_old_files_and_no_trace_are_stale_paint_on_the_busy_box_else_idle(tmp_path, monkeypatch, sleeps):
    _newest(monkeypatch, 1000)
    _ticks(monkeypatch, {7: [100, 100]})
    got = seasonloop.health(_Lane(tmp_path, [7]), scr='busy')
    assert got['verdict'] == 'stale_paint' and got['trace_age_s'] is None and got['write_age_s'] >= 999
    _ticks(monkeypatch, {7: [100, 100]})
    assert seasonloop.health(_Lane(tmp_path, [7]))['verdict'] == 'idle'


def test_ticks_that_went_backwards_or_vanished_count_zero(tmp_path, monkeypatch, sleeps):
    _ticks(monkeypatch, {7: [100, 40], 8: [5, None], 9: [None, 30]})
    _newest(monkeypatch, None)
    assert seasonloop.health(_Lane(tmp_path, [7, 8, 9]))['dticks'] == 30


def test_trace_age_comes_from_the_last_stamped_line(tmp_path, monkeypatch, sleeps):
    _ticks(monkeypatch, {7: [100, 100]})
    stamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    (tmp_path / 'bbtrace.log').write_text(f'00:00:01.000 old\n{stamp} sim step\n')
    got = seasonloop.health(_Lane(tmp_path, [7]))
    assert got['trace_age_s'] in (0, 1)
    assert got['verdict'] == 'working'


def test_game_pids_raising_gives_an_error_verdict(tmp_path, sleeps):
    h = _Lane(tmp_path)
    def boom():
        raise RuntimeError('no wine')
    h.game_pids = boom
    assert seasonloop.health(h) == {'verdict': 'error', 'error': 'RuntimeError'}


def _lines(out):
    return [json.loads(line) for line in out.splitlines() if line.strip()]


@pytest.fixture
def _fake_time(monkeypatch):
    """seasonloop.time.time advanced 300 s per call: with PROGRESS 600, every second call is a progress line due."""
    tick = [0]
    def clock():
        tick[0] += 300
        return tick[0]
    monkeypatch.setattr(seasonloop.time, 'time', clock)
    return tick


def test_season_progress_line_carries_the_verdict(tmp_path, monkeypatch, capsys, sleeps, _fake_time):
    assn = tmp_path / 'Assn'
    assn.mkdir()
    (assn / 'TEST.ASN').write_bytes(b'a')
    monkeypatch.setattr(seasonloop, 'played', lambda asn: (0, 100))
    monkeypatch.setattr(seasonloop, 'sim', lambda h, shots: True)
    monkeypatch.setattr(seasonloop, 'QUIET', 2000)         # the round outlasts PROGRESS on the fake clock
    for name in ('settle', 'look'):
        monkeypatch.setattr(seasonloop, name, lambda *a, **k: None)
    monkeypatch.setattr(seasonloop, '_diff', lambda *a: 100.0)
    monkeypatch.setattr(seasonloop, 'on_assn_data', lambda png: False)
    assert seasonloop.season(_Lane(tmp_path), str(tmp_path), 'TEST', 10 ** 9) is False
    progress = [l for l in _lines(capsys.readouterr().out) if 'progress' in l]
    assert progress and progress[0]['verdict'] == 'no_game'
    assert {'dticks', 'write_age_s', 'trace_age_s'} <= set(progress[0])


def test_postseason_waiting_line_over_another_screen_carries_the_verdict(tmp_path, monkeypatch, capsys, sleeps,
                                                                         _fake_time):
    shade = {'other': 50, 'busy': 100, 'complete': 200}      # a look is a 4x4 png whose grey level names the screen
    screens = ['other', 'other', 'complete']

    def look(h, png):
        Image.new('L', (4, 4), shade[screens.pop(0) if screens else 'complete']).save(png)

    def grey(png):
        return Image.open(png).getpixel((0, 0))
    monkeypatch.setattr(seasonloop, 'look', look)
    monkeypatch.setattr(seasonloop, '_same', lambda a, b: grey(a) == grey(b))
    monkeypatch.setattr(seasonloop, '_other_mtimes', lambda asn: {})
    monkeypatch.setattr(seasonloop, '_diff', lambda png, ref, box: 0.0 if ref == 'f_update.png' and grey(png) == 100
                        else 100.0)
    monkeypatch.setattr(seasonloop, 'notice', lambda png: 'complete' if grey(png) == 200 else None)
    assert seasonloop.postseason(_Lane(tmp_path), str(tmp_path), 10 ** 12) is True
    waiting = [l for l in _lines(capsys.readouterr().out) if l.get('postseason') == 'waiting']
    assert waiting and waiting[0]['screen'] == 'other' and waiting[0]['verdict'] == 'no_game'
    assert {'dticks', 'write_age_s', 'trace_age_s'} <= set(waiting[0])
