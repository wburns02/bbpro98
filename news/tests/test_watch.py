"""watch.Watcher over a fake game directory: gamedata's readers are replaced by dicts, so no game files are needed."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import hive      # noqa: E402
import watch     # noqa: E402

TEAMS = {1: {'tid': 1, 'name': 'Ash', 'abbrev': 'ASH', 'city': 'X', 'stadium': 'Ash Park', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0},
         2: {'tid': 2, 'name': 'Birch', 'abbrev': 'BIR', 'city': 'X', 'stadium': 'Birch Field', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0}}


def game(day, slot, away, home, ar, hr, played=True):
    return {'month': 4, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': 9}


def side(tid, runs, pid):
    return {'tid': tid, 'runs': runs, 'hits': runs,
            'batting': [{'ab': 4, 'h': runs, '2b': 0, '3b': 0, 'hr': 0, 'rbi': runs, 'bb': 0, 'so': 0, 'r': runs,
                         'sb': 0, 'pid': pid}],
            'pitching': [{'outs': 27, 'h': 1, 'r': 1, 'er': 1, 'bb': 0, 'so': 5, 'hr': 0, 'w': int(pid == 100),
                          'l': int(pid == 200), 'sv': 0, 'pid': pid}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    gd = tmp_path / 'game'
    (gd / 'Assn').mkdir(parents=True)
    (gd / 'Stats').mkdir()
    (gd / 'Assn' / '30L1998.ASN').write_bytes(b'asn')
    st = {'games': [game(1, 0, 1, 2, 3, 1), game(2, 0, 2, 1, 0, 5), game(3, 0, 1, 2, 0, 0, played=False)],
          'boxes': {}}

    def boxfile(name, box):
        p = gd / 'Stats' / name
        p.write_bytes(json.dumps(box).encode())
        os.utime(p, (1, 1))                 # settled long ago
        st['boxes'][str(p)] = box

    monkeypatch.setattr(gamedata, 'association', lambda path: {'name': '1998 Test', 'teams': TEAMS,
                                                              'games': [dict(g) for g in st['games']]})
    monkeypatch.setattr(gamedata, 'names', lambda path: {100: 'Al Winner', 200: 'Bo Loser'})
    monkeypatch.setattr(gamedata, 'season_lines', lambda path: {'bat': {}, 'pit': {}})
    monkeypatch.setattr(gamedata, 'boxscore', lambda path: st['boxes'][str(path)])
    st['boxfile'] = boxfile
    return gd, tmp_path / 'data', st


def stories(data):
    d = data / '30L1998' / 'recaps'
    return [json.loads(p.read_text()) for p in sorted(d.iterdir())] if d.is_dir() else []


def test_template_only_run_writes_everything(world):
    gd, data, st = world
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    st['boxfile']('30L1998.H20', {'away': side(2, 0, 200), 'home': side(1, 5, 100)})
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    got = stories(data)
    assert sorted((s['day'], s['source'], s['reason']) for s in got) == [(1, 'template', 'off'), (2, 'template', 'off')]
    assert sorted(os.listdir(data / '30L1998' / 'feed')) == ['04-01.json', '04-02.json']
    meta = json.loads((data / '30L1998' / 'meta.json').read_text())
    assert meta['last_day'] == [4, 2] and meta['standings'][0]['teams'][0]['name'] == 'Ash'
    assert not os.listdir(data / '30L1998' / 'pending')


def test_box_scores_captured_before_the_game_deletes_them(world):
    """The game keeps seven sim days of box scores; one captured on an earlier pass still gets its story after the
    file is gone."""
    gd, data, st = world
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    st['games'][0]['played'] = False                     # association not saved yet: nothing to match
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    w.scan()
    assert stories(data) == [] and len(os.listdir(data / '30L1998' / 'pending')) == 1
    (gd / 'Stats' / '30L1998.H10').unlink()
    st['games'][0]['played'] = True
    (gd / 'Assn' / '30L1998.ASN').write_bytes(b'asn saved')
    os.utime(gd / 'Assn' / '30L1998.ASN', (2, 2))
    w.scan()
    assert [s['day'] for s in stories(data)] == [1]
    assert os.listdir(data / '30L1998' / 'pending') == []


def test_rescan_writes_no_duplicates_and_one_story_per_game(world):
    gd, data, st = world
    box = {'away': side(1, 3, 100), 'home': side(2, 1, 200)}
    st['boxfile']('30L1998.H10', box)
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    w.scan()
    w.seen.clear()
    w.scan()
    assert len(stories(data)) == 1
    # A second box score of the same game (same teams and score) has no unreported game left to be.
    st['boxfile']('30L1998.H11', dict(box, extra=1))
    w.seen.clear()
    w.scan()
    assert len(stories(data)) == 1


def test_model_used_until_the_budget_runs_out(world):
    gd, data, st = world
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    st['boxfile']('30L1998.H20', {'away': side(2, 0, 200), 'home': side(1, 5, 100)})
    budget = hive.Budget(str(data / 'budget.json'), 3, 10 ** 6)
    data.mkdir()
    calls = []

    def complete(system, user, b):
        b.reserve()
        calls.append(user)
        return 'Ash wins\n\nAsh won the game.', {'completion_tokens': 10}

    watch.Watcher(str(gd), str(data), budget, complete, log=lambda s: None).scan()
    cols = [json.loads((data / '30L1998' / 'feed' / f).read_text()) for f in ('04-01.json', '04-02.json')]
    assert [c['source'] for c in cols] == ['glm', 'glm']           # columns go first
    got = sorted((s['day'], s['source'], s.get('reason')) for s in stories(data))
    assert got == [(1, 'template', 'budget'), (2, 'glm', None)]     # newest game gets the last call
    assert len(calls) == 3
