"""watch.Watcher over a fake game directory: gamedata's readers are replaced by dicts, so no game files are needed."""
import hashlib
import json
import os
import struct
import sqlite3
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import contracts  # noqa: E402
import draft     # noqa: E402
import fog       # noqa: E402
import gamedata  # noqa: E402
import history   # noqa: E402
import hive      # noqa: E402
import watch     # noqa: E402

TEAMS = {1: {'tid': 1, 'name': 'Ash', 'abbrev': 'ASH', 'city': 'X', 'stadium': 'Ash Park', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [100]},
         2: {'tid': 2, 'name': 'Birch', 'abbrev': 'BIR', 'city': 'X', 'stadium': 'Birch Field', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [200]}}


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
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: {'bat': {}, 'pit': {}})
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


def test_season_preview_once_and_awards_only_after_the_last_game(world):
    gd, data, st = world
    out = data / '30L1998'
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    w.scan()
    prev = json.loads((out / 'preview.json').read_text())
    assert (prev['kind'], prev['source'], prev['reason']) == ('preview', 'template', 'off')
    assert not (out / 'awards.json').exists()                  # game 3 is unplayed
    (out / 'preview.json').write_text('{"kept": true}')
    st['games'][2].update(played=True, away_runs=2, home_runs=1)
    w.seen.clear()
    w.scan()
    assert json.loads((out / 'preview.json').read_text()) == {'kept': True}
    awards = json.loads((out / 'awards.json').read_text())
    assert (awards['kind'], awards['source'], awards['reason']) == ('awards', 'template', 'off')
    assert awards['facts']['leagues'][0]['champions'] == [{'division': 'East', 'team': 'Ash', 'record': '3-0'}]


def test_preview_reads_last_season_and_the_season_is_read_this_season(world, monkeypatch):
    gd, data, st = world
    (gd / 'Stats' / '30L1998.DAT').write_bytes(b'dat')
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')      # names come from the PYR file, when there is one
    calls = []

    def lines(path, scope=1):
        calls.append((os.path.basename(path), scope))
        if scope != 3:
            return {'bat': {}, 'pit': {}}
        return {'bat': {100: {'ab': 120, 'h': 40, 'h2b': 0, 'h3b': 0, 'hr': 12, 'rbi': 50, 'bb': 0, 'so': 0, 'r': 0,
                              'sb': 0}}, 'pit': {}}

    monkeypatch.setattr(gamedata, 'season_lines', lines)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert calls == [('30L1998.DAT', 1), ('30L1998.DAT', 3)]     # this season for the table, last for the preview
    preview = json.loads((data / '30L1998' / 'preview.json').read_text())
    ash = next(t for d in preview['facts']['divisions'] for t in d['teams'] if t['name'] == 'Ash')
    assert ash['hitter'] == {'name': 'Al Winner', 'avg': '.333', 'hr': 12, 'rbi': 50}


def test_no_preview_for_an_association_without_teams(world, monkeypatch):
    gd, data, st = world
    monkeypatch.setattr(gamedata, 'association', lambda path: {'name': '1998 Empty', 'teams': {}, 'games': []})
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert not (data / '30L1998' / 'preview.json').exists()


def test_full_team_names_from_the_data_dir(world):
    gd, data, st = world
    data.mkdir()
    (data / 'teamnames.json').write_text(json.dumps({'1998': {'ASH': ['Ashland Ashes', 'Ash'],
                                                              'BIR': ['Birchwood Birches', 'Bir.']}}))
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    meta = json.loads((data / '30L1998' / 'meta.json').read_text())
    got = {t['name'] for d in meta['standings'] for t in d['teams']}
    assert got == {'Ashland Ashes', 'Birch'}            # Birch is not the stored short form: left alone
    assert stories(data)[0]['headline'].startswith('Ashland Ashes 3')


# Veterans of ten seasons: the public view reads them to within a couple of points (fog.py), so Bo Loser's 97 control
# still grades 80.
SCOUT_PLAYERS = {
    100: {'name': 'Al Winner', 'pos': 'RF', 'bats': 'L', 'throws': 'L', 'born': 1970, 'contact': 90, 'power': 60,
          'speed': 70, 'stamina': 0, 'control': 0, 'strikeout': 0, 'fielding': 50, 'seasons': 10},
    200: {'name': 'Bo Loser', 'pos': 'P', 'bats': '', 'throws': 'R', 'born': None, 'contact': 0, 'power': 0,
          'speed': 0, 'stamina': 69, 'control': 97, 'strikeout': 47, 'fielding': 40, 'seasons': 10},
}


def test_scouting_writes_one_report_per_team_and_a_rescan_writes_nothing(world, monkeypatch):
    gd, data, st = world
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    reads = []

    def players(path):
        reads.append(path)
        return SCOUT_PLAYERS

    monkeypatch.setattr(gamedata, 'players', players)
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    w.scan()
    scout = data / '30L1998' / 'scout'
    assert sorted(os.listdir(scout)) == ['1.json', '2.json']
    ash = json.loads((scout / '1.json').read_text())
    assert (ash['kind'], ash['tid'], ash['abbrev'], ash['team'], ash['source'], ash['reason']) == (
        'scout', 1, 'ASH', 'Ash', 'template', 'off')
    assert ash['facts']['association'] == '1998 Test' and ash['facts']['hitters'][0]['name'] == 'Al Winner'
    assert ash['roster']['hitters'][0]['age'] == 28            # 1998 - 1970
    birch = json.loads((scout / '2.json').read_text())
    assert birch['roster']['pitchers'][0]['control'] == 80 and birch['roster']['pitchers'][0]['name'] == 'Bo Loser'
    (scout / '1.json').write_text('{"kept": true}')
    reads.clear()
    w.seen.clear()
    w.scan()
    assert json.loads((scout / '1.json').read_text()) == {'kept': True}
    assert reads == []                                         # every team has its report: the PYR is not read


def test_scouting_ages_from_the_season_year(world, monkeypatch):
    """A career league keeps its name while its season moves on: the ages come from season_year when it is an int."""
    gd, data, st = world
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    monkeypatch.setattr(gamedata, 'players', lambda path: SCOUT_PLAYERS)
    named(monkeypatch, '1997 Test', season_year=1998)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    ash = json.loads((data / '30L1998' / 'scout' / '1.json').read_text())
    assert ash['roster']['hitters'][0]['age'] == 28            # 1998 - 1970
    assert ash['facts']['association'] == '1997 Test'
    (data / '30L1998' / 'scout' / '1.json').unlink()
    (data / '30L1998' / 'scout' / '2.json').unlink()
    named(monkeypatch, '1997 Test', season_year=None)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    ash = json.loads((data / '30L1998' / 'scout' / '1.json').read_text())
    assert ash['roster']['hitters'][0]['age'] == 27            # year_of('1997 Test')


def test_no_scouting_without_a_pyr(world, monkeypatch):
    gd, data, st = world
    reads = []
    monkeypatch.setattr(gamedata, 'players', lambda path: reads.append(path) or SCOUT_PLAYERS)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert reads == [] and not (data / '30L1998' / 'scout').exists()
    assert (data / '30L1998' / 'preview.json').exists()        # the other season pieces still come


def test_scouting_asks_the_model_for_at_most_scout_calls_a_scan_and_finishes_on_later_scans(world, monkeypatch):
    gd, data, st = world
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    monkeypatch.setattr(gamedata, 'players', lambda path: SCOUT_PLAYERS)
    monkeypatch.setattr(watch, 'SCOUT_CALLS', 1)
    calls = []

    def write(facts, budget, complete):
        calls.append(facts['team'])
        return {'headline': 'Scouting', 'body': 'Report.', 'source': 'glm'}

    monkeypatch.setattr(watch.scout, 'write', write)
    w = watch.Watcher(str(gd), str(data), object(), lambda *a: None, log=lambda s: None)
    monkeypatch.setattr(w, 'columns', lambda *a: None)
    monkeypatch.setattr(w, 'recaps', lambda *a: None)
    monkeypatch.setattr(watch.season, 'write_preview',
                        lambda f, b, c: {'headline': 'h', 'body': 'b', 'source': 'glm'})
    w.scan()
    scout = data / '30L1998' / 'scout'
    assert calls == ['Ash'] and sorted(os.listdir(scout)) == ['1.json']
    w.scan()                                  # nothing changed on disk, but the association is still open
    assert calls == ['Ash', 'Birch'] and sorted(os.listdir(scout)) == ['1.json', '2.json']
    w.scan()
    assert calls == ['Ash', 'Birch'] and '30L1998' not in w.scouting_open


def test_scouting_writes_nothing_once_the_budget_is_spent(world, monkeypatch):
    gd, data, st = world
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    monkeypatch.setattr(gamedata, 'players', lambda path: SCOUT_PLAYERS)
    monkeypatch.setattr(watch.scout, 'write',
                        lambda facts, budget, complete: {'headline': 'x', 'body': 'y', 'source': 'template',
                                                         'reason': 'budget'})
    w = watch.Watcher(str(gd), str(data), object(), lambda *a: None, log=lambda s: None)
    monkeypatch.setattr(w, 'columns', lambda *a: None)
    monkeypatch.setattr(w, 'recaps', lambda *a: None)
    monkeypatch.setattr(watch.season, 'write_preview',
                        lambda f, b, c: {'headline': 'h', 'body': 'b', 'source': 'glm'})
    w.scan()
    assert not (data / '30L1998' / 'scout').exists() and '30L1998' in w.scouting_open


def league_player(name, pos, born):
    """A player as gamedata.players() gives him: the ratings the scouting pages read, all 50."""
    return {'name': name, 'pos': pos, 'born': born, 'bats': 'R', 'throws': 'R', 'contact': 50, 'power': 50,
            'speed': 50, 'stamina': 50, 'control': 50, 'strikeout': 50, 'fielding': 50}


LEAGUE_PLAYERS = {100: league_player('Al Winner', 'RF', 1970), 101: league_player('Joe Old', 'P', 1960),
                  200: league_player('Bo Loser', 'P', 1975), 300: league_player('Pat Smith', 'SS', 1971),
                  400: league_player('Ann Bat', '1B', 1966)}


@pytest.fixture
def league(world, monkeypatch):
    """world, with the rosters, free agents, players and career totals a test changes between scans. The PYR and DAT
    exist, so moves are read; the PYF is written from the free agents by league_scan. Season lines are empty: moves
    reads them only for season milestones, which test_moves covers."""
    gd, data, st = world
    st.update(rosters={1: [100, 101], 2: [200, 400]}, fa={300}, players=dict(LEAGUE_PLAYERS),
              career={'bat': {400: {'hr': 499, 'h': 2100, 'sb': 10}}, 'pit': {101: {'w': 199, 'sv': 0, 'so': 0}}})
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    (gd / 'Stats' / '30L1998.DAT').write_bytes(b'dat')
    monkeypatch.setattr(gamedata, 'association', lambda path: {
        'name': '1998 Test',
        'teams': {tid: dict(t, roster=list(st['rosters'].get(tid, []))) for tid, t in TEAMS.items()},
        'games': [dict(g) for g in st['games']]})
    monkeypatch.setattr(gamedata, 'players', lambda path: dict(st['players']))
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: st['career'] if scope == 2
                        else {'bat': {}, 'pit': {}})
    return gd, data, st


def write_pyf(gd, ids):
    ids = sorted(ids)
    (gd / 'Assn' / '30L1998.PYF').write_bytes(b'PPD:' + struct.pack('<Ih', 0, len(ids))
                                              + struct.pack('<%dH' % len(ids), *ids))


def league_scan(w, gd, st, settled=True):
    write_pyf(gd, st['fa'])
    if settled:                         # moves() waits until the PYR, PYF and DAT have sat SETTLE seconds
        for p in list((gd / 'Assn').glob('30L1998.PY?')) + list((gd / 'Stats').glob('30L1998.DAT')):
            os.utime(p, (1, 1))
    w.seen.clear()
    w.scan()


def test_a_change_to_the_pyf_alone_makes_the_association_due_for_a_scan(league):
    gd, data, st = league
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    league_scan(w, gd, st)
    asn = str(gd / 'Assn' / '30L1998.ASN')
    before = w.signature('30L1998', asn)
    write_pyf(gd, [])
    assert w.signature('30L1998', asn) != before


def moves_log(data):
    return json.loads((data / '30L1998' / 'moves' / 'log.json').read_text())


def move_notes(data):
    d = data / '30L1998' / 'moves' / 'notes'
    return {int(p.stem): json.loads(p.read_text()) for p in d.iterdir()} if d.is_dir() else {}


def test_first_scan_only_takes_the_snapshot(league):
    gd, data, st = league
    league_scan(watch.Watcher(str(gd), str(data), None, None, log=lambda s: None), gd, st)
    mdir = data / '30L1998' / 'moves'
    assert json.loads((mdir / 'last.json').read_text())['year'] == 1998
    assert not (mdir / 'log.json').exists() and not (mdir / 'notes').exists()


def test_moves_between_two_scans_are_logged_and_the_notable_ones_get_notes(league):
    gd, data, st = league
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    league_scan(w, gd, st)
    st.update(fa=set(), rosters={1: [100], 2: [200, 300, 400]})          # Pat Smith signed, Joe Old gone
    st['players'][500] = league_player('Kim New', 'SS', 1977)
    st['rosters'][2].append(500)                                          # a created player
    st['career']['bat'][400]['hr'] = 500                                  # Ann Bat's 500th
    league_scan(w, gd, st)
    log = moves_log(data)
    assert log['count'] == 4
    assert [(e['kind'], e['name'], e['date'], e['year']) for e in log['events']] == [
        ('milestone', 'Ann Bat', 'April 2', 1998), ('new', 'Kim New', 'April 2', 1998),
        ('retired', 'Joe Old', 'April 2', 1998), ('signed', 'Pat Smith', 'April 2', 1998)]
    assert [e.get('note') for e in log['events']] == [0, None, 2, None]
    notes = move_notes(data)
    assert sorted(notes) == [0, 2]
    assert notes[0]['kind'] == 'move' and notes[0]['source'] == 'template' and notes[0]['reason'] == 'off'
    assert notes[0]['headline'] == 'Ann Bat reached 500 career home runs'
    assert notes[0]['event']['note'] == 0 and notes[0]['facts']['association'] == '1998 Test'
    assert notes[2]['headline'] == 'Joe Old retires'

    st.update(fa={100}, rosters={1: [], 2: [200, 300, 500]})             # Al Winner released, Ann Bat retires
    league_scan(w, gd, st)
    log = moves_log(data)
    assert log['count'] == 6                                             # numbers go on from the full log
    assert [(e['kind'], e.get('note')) for e in log['events'][4:]] == [('released', None), ('retired', 5)]
    assert sorted(move_notes(data)) == [0, 2, 5]


def test_the_log_keeps_its_last_events_and_the_count_of_all_of_them(league, monkeypatch):
    gd, data, st = league
    monkeypatch.setattr(watch, 'MOVE_KEEP', 2)
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    league_scan(w, gd, st)
    st['players'][500] = league_player('Kim New', 'SS', 1977)
    st.update(fa=set(), rosters={1: [100], 2: [200, 400, 300, 500]})      # 101 retires; 300 signed; 500 created
    league_scan(w, gd, st)
    log = moves_log(data)
    assert [e['kind'] for e in log['events']] == ['retired', 'signed'] and log['count'] == 3
    assert [e.get('note') for e in log['events']] == [1, None]          # the retirement's note keeps its number
    assert sorted(move_notes(data)) == [1]


def test_model_notes_are_capped_per_scan_and_the_rest_are_backfill(league, monkeypatch):
    gd, data, st = league
    monkeypatch.setattr(watch, 'MOVE_CALLS', 2)
    w = watch.Watcher(str(gd), str(data), object(), lambda *a: None, log=lambda s: None)
    for name in ('columns', 'recaps', 'season_pieces'):
        monkeypatch.setattr(w, name, lambda *a: None)
    asked = []

    def write(facts, budget, complete):
        asked.append(facts['kind'])
        return {'headline': 'A move', 'body': 'The league has a move to note.', 'source': 'glm'}

    monkeypatch.setattr(watch.moves, 'write', write)
    league_scan(w, gd, st)
    st.update(rosters={1: [100], 2: [200]}, fa={300})
    st['career']['bat'][400]['hr'] = 500
    st['career']['pit'][200] = {'w': 160, 'sv': 0, 'so': 0}
    league_scan(w, gd, st)                                              # three notable moves in one scan
    assert asked == ['milestone', 'retired']
    notes = move_notes(data)
    assert [(n, notes[n]['source'], notes[n].get('reason')) for n in sorted(notes)] == [
        (0, 'glm', None), (1, 'glm', None), (2, 'template', 'backfill')]


def test_without_a_model_every_note_is_a_template_off(league):
    gd, data, st = league
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    league_scan(w, gd, st)
    st['career']['bat'][400]['hr'] = 500
    league_scan(w, gd, st)
    assert [(n['source'], n['reason']) for n in move_notes(data).values()] == [('template', 'off')]


@pytest.mark.parametrize('gone', ['30L1998.PYF', '30L1998.PYR'])
def test_no_pyr_or_no_pyf_writes_no_moves(league, gone):
    gd, data, st = league
    league_scan(watch.Watcher(str(gd), str(data), None, None, log=lambda s: None), gd, st)
    (gd / 'Assn' / gone).unlink()
    st['career']['bat'][400]['hr'] = 500
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert not (data / '30L1998' / 'moves' / 'log.json').exists()
    assert json.loads((data / '30L1998' / 'moves' / 'last.json').read_text())['where'] == {
        '100': 1, '101': 1, '200': 2, '300': 0, '400': 2}


def test_a_fresh_pyf_waits_for_a_later_scan(league):
    gd, data, st = league
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    league_scan(w, gd, st, settled=False)            # the PYF was just written: the set may be torn
    assert not (data / '30L1998' / 'moves' / 'last.json').exists()
    league_scan(w, gd, st)
    assert (data / '30L1998' / 'moves' / 'last.json').exists()


def lahman_db(path):
    """A tiny Lahman database: the two teams of the world fixture, 1998, both in the AL."""
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT, divID TEXT, name TEXT, G INT, W INT, L INT, '
                'teamRank INT)')
    con.execute('CREATE TABLE batting (playerID TEXT, yearID INT, teamID TEXT, lgID TEXT, AB INT, H INT, HR INT, '
                'RBI INT, SB INT, BB INT)')
    con.execute('CREATE TABLE pitching (playerID TEXT, yearID INT, teamID TEXT, lgID TEXT, W INT, L INT, SV INT, '
                'IPouts INT, ER INT, SO INT)')
    con.execute('CREATE TABLE people (playerID TEXT, nameFirst TEXT, nameLast TEXT)')
    con.executemany('INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?)',
                    [(1998, 'AL', 'ASH', 'E', 'Ash Gold', 4, 3, 1, 1),
                     (1998, 'AL', 'BIR', 'E', 'Birch Blue', 4, 1, 3, 2)])
    con.commit()
    con.close()
    return str(path)


def named(monkeypatch, name, **over):
    """The world's association under another name, with any other keys given."""
    read = gamedata.association
    monkeypatch.setattr(gamedata, 'association', lambda path: dict(read(path), name=name, **over))


def test_lahman_named_association_gets_a_replay_scorecard(world, monkeypatch, tmp_path):
    gd, data, st = world
    named(monkeypatch, '1998 Major Leagues')
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None, db=lahman_db(tmp_path / 'lahman.sqlite')).scan()
    card = json.loads((data / '30L1998' / 'replay.json').read_text())
    assert card['kind'] == 'replay' and card['year'] == 1998 and card['created']
    assert [t['name'] for t in card['teams']] == ['Ash', 'Birch']
    assert card['teams'][0]['sim'] == {'w': 2, 'l': 0, 'pct': 1.0}
    assert card['teams'][0]['real'] == {'w': 3, 'l': 1, 'pct': 0.75}
    assert card['teams'][0]['wins_diff'] == 1.0
    assert card['played'] == 2.0 and card['scheduled'] == 3.0


def test_stock_named_association_gets_no_scorecard(world, tmp_path):
    gd, data, st = world
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None, db=lahman_db(tmp_path / 'lahman.sqlite')).scan()
    assert (data / '30L1998' / 'meta.json').exists()
    assert not (data / '30L1998' / 'replay.json').exists()


def test_no_database_writes_no_scorecard(world, monkeypatch):
    gd, data, st = world
    named(monkeypatch, '1998 Major Leagues')
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert not (data / '30L1998' / 'replay.json').exists()


def test_broken_database_path_is_logged_and_the_scan_goes_on(world, monkeypatch, tmp_path):
    gd, data, st = world
    named(monkeypatch, '1998 Major Leagues')
    logs = []
    watch.Watcher(str(gd), str(data), None, None, log=logs.append, db=str(tmp_path / 'missing.sqlite')).scan()
    assert any('30L1998 replay' in line for line in logs)
    assert not (data / '30L1998' / 'replay.json').exists()
    assert (data / '30L1998' / 'meta.json').exists()


def test_the_database_is_read_once_per_season(world, monkeypatch, tmp_path):
    gd, data, st = world
    named(monkeypatch, '1998 Major Leagues')
    calls = []
    read = watch.replay.real
    monkeypatch.setattr(watch.replay, 'real', lambda con, year, leagues: calls.append(year) or read(con, year, leagues))
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None, db=lahman_db(tmp_path / 'lahman.sqlite'))
    w.scan()
    w.seen.clear()
    w.scan()
    assert calls == [1998]


def test_a_season_year_equal_to_the_name_writes_the_scorecard(world, monkeypatch, tmp_path):
    gd, data, st = world
    named(monkeypatch, '1998 Major Leagues', season_year=1998)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None, db=lahman_db(tmp_path / 'lahman.sqlite')).scan()
    assert json.loads((data / '30L1998' / 'replay.json').read_text())['year'] == 1998


def test_a_season_year_past_the_name_writes_nothing_and_logs_once(world, monkeypatch, tmp_path):
    gd, data, st = world
    named(monkeypatch, '1998 Major Leagues', season_year=1999)
    logs = []
    w = watch.Watcher(str(gd), str(data), None, None, log=logs.append, db=lahman_db(tmp_path / 'lahman.sqlite'))
    w.scan()
    w.seen.clear()
    w.scan()
    assert not (data / '30L1998' / 'replay.json').exists()
    assert [line for line in logs if 'replay' in line] == ['30L1998 replay: season 1999 is not 1998, skipped']
    assert (data / '30L1998' / 'meta.json').exists()


def test_a_season_that_moved_on_leaves_the_old_scorecard_alone(world, monkeypatch, tmp_path):
    gd, data, st = world
    db = lahman_db(tmp_path / 'lahman.sqlite')
    named(monkeypatch, '1998 Major Leagues', season_year=1998)
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None, db=db)
    w.scan()
    before = (data / '30L1998' / 'replay.json').read_text()
    named(monkeypatch, '1998 Major Leagues', season_year=1999)
    w.seen.clear()
    w.scan()
    assert (data / '30L1998' / 'past' / '1998' / 'replay.json').read_text() == before     # archived at the rollover
    assert not (data / '30L1998' / 'replay.json').exists()                               # and none written for 1999


@pytest.fixture
def salary_table(tmp_path):
    """A salary table with every year at $1M and a ratio by class alone: pre 0.5, arb 1.0, fa 2.0."""
    path = tmp_path / 'salary_table.json'
    ratio = {r: {'pre': [0.5] * 10, 'arb': [1.0] * 10, 'fa': [2.0] * 10} for r in ('bat', 'pit')}
    path.write_text(json.dumps({'source': 'test', 'years': {str(y): 1000000 for y in range(1985, 2017)},
                                'ratio': ratio}), encoding='utf-8')
    return str(path)


@pytest.fixture
def season(league, monkeypatch):
    """league, dated 1998: the league fixture's association has no season year of its own."""
    named(monkeypatch, '1998 Test', season_year=1998)
    return league


def priced(gd, data, table):
    return watch.Watcher(str(gd), str(data), None, None, log=lambda s: None, salary_table=table)


def contract_file(data):
    return json.loads((data / '30L1998' / 'contracts.json').read_text())


def test_the_first_scan_prices_each_rostered_player_and_logs_no_signings(season, salary_table):
    gd, data, st = season
    league_scan(priced(gd, data, salary_table), gd, st)
    c = contract_file(data)
    assert c['kind'] == 'contracts' and c['season_year'] == 1998 and c['created'] and c['events'] == []
    assert sorted(c['contracts']) == ['100', '101', '200', '400']
    assert c['contracts']['100']['salary'] == 2000000 and c['contracts']['200']['salary'] == 500000
    assert [(r['tid'], r['name'], r['players'], r['total']) for r in c['payroll']] == [
        (1, 'Ash', 2, 4000000), (2, 'Birch', 2, 2500000)]


def test_a_signing_counts_down_and_re_signs_when_it_runs_out(season, salary_table, monkeypatch):
    gd, data, st = season
    w = priced(gd, data, salary_table)
    league_scan(w, gd, st)
    st.update(fa=set(), rosters={1: [100, 101, 300], 2: [200, 400]})     # Pat Smith signs with Ash
    league_scan(w, gd, st)
    assert contract_file(data)['events'] == [
        {'kind': 'signed', 'pid': 300, 'name': 'Pat Smith', 'team': 1, 'salary': 1000000, 'years': 1, 'year': 1998}]
    named(monkeypatch, '1998 Test', season_year=1999)
    league_scan(w, gd, st)
    c = contract_file(data)
    assert c['season_year'] == 1999
    assert c['contracts']['100']['left'] == 1 and c['contracts']['400']['left'] == 2   # kept, counting down
    assert [(e['kind'], e['pid']) for e in c['events']] == [
        ('signed', 300), ('re-signed', 101), ('re-signed', 200), ('re-signed', 300)]


def test_a_move_keeps_the_contract_and_a_release_is_logged(season, salary_table):
    gd, data, st = season
    w = priced(gd, data, salary_table)
    league_scan(w, gd, st)
    st.update(rosters={1: [101], 2: [100, 200, 400]})                   # Al Winner moves to Birch
    league_scan(w, gd, st)
    st.update(fa={200}, rosters={1: [101], 2: [100, 400]})              # Bo Loser is released
    league_scan(w, gd, st)
    c = contract_file(data)
    assert c['events'] == [
        {'kind': 'moved', 'pid': 100, 'name': 'Al Winner', 'team': 2, 'salary': 0, 'years': 0, 'year': 1998},
        {'kind': 'released', 'pid': 200, 'name': 'Bo Loser', 'team': None, 'salary': 0, 'years': 0, 'year': 1998}]
    assert c['contracts']['100']['team'] == 2 and c['contracts']['100']['salary'] == 2000000
    assert sorted(c['contracts']) == ['100', '101', '400']


def test_a_fresh_pyr_waits_for_a_settled_set(season, salary_table):
    gd, data, st = season
    w = priced(gd, data, salary_table)
    league_scan(w, gd, st, settled=False)            # the league was just saved: the set may be torn
    assert not (data / '30L1998' / 'contracts.json').exists()
    league_scan(w, gd, st)
    assert (data / '30L1998' / 'contracts.json').exists()


def test_no_pyr_writes_no_contracts(world, salary_table):
    gd, data, st = world
    priced(gd, data, salary_table).scan()
    assert not (data / '30L1998' / 'contracts.json').exists()
    assert (data / '30L1998' / 'meta.json').exists()


@pytest.mark.parametrize('content', [None, '[1, 2]', '{"years": {"1985": 1}}'])
def test_a_missing_or_bad_salary_table_is_logged_once_and_the_rest_is_written(league, tmp_path, content):
    gd, data, st = league
    path = tmp_path / 'table.json'
    if content is not None:
        path.write_text(content, encoding='utf-8')
    logs = []
    w = watch.Watcher(str(gd), str(data), None, None, log=logs.append, salary_table=str(path))
    league_scan(w, gd, st)
    assert len([line for line in logs if line.startswith('contracts:')]) == 1
    assert not (data / '30L1998' / 'contracts.json').exists()
    assert (data / '30L1998' / 'moves' / 'last.json').exists() and (data / '30L1998' / 'meta.json').exists()


def test_the_default_table_is_news_salary_table_next_to_watch(season, salary_table, monkeypatch):
    gd, data, st = season
    monkeypatch.setattr(watch, 'DEFAULT_TABLE', salary_table)
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    assert w.table is not None
    league_scan(w, gd, st)
    assert (data / '30L1998' / 'contracts.json').exists()


def test_a_season_with_no_year_prices_nothing(league, salary_table, monkeypatch):
    gd, data, st = league
    named(monkeypatch, '1998 Test', season_year=None)
    league_scan(priced(gd, data, salary_table), gd, st)
    c = contract_file(data)
    assert c['season_year'] is None and c['contracts'] == {} and c['events'] == []
    assert [(r['tid'], r['players']) for r in c['payroll']] == [(1, 0), (2, 0)]


def season_folder(out, year=1997):
    """An association folder as the watcher leaves it after a season: season files, cross-season files, a meta.json."""
    files = {'meta.json': {'season_year': year}, 'recaps/aa.json': {'key': 'aa'}, 'pending/bb.json': {'key': 'bb'},
             'feed/10-01.json': {}, 'scout/3.json': {}, 'preview.json': {}, 'awards.json': {}, 'replay.json': {},
             'history/1997.json': {}, 'moves/log.json': {}, 'contracts.json': {}, 'notes/1.json': {}}
    for name, obj in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(json.dumps(obj))
    return sorted(files)


def rolling(tmp_path):
    lines = []
    return watch.Watcher(str(tmp_path / 'game'), str(tmp_path / 'data'), None, None, log=lines.append), lines


def test_meta_carries_the_season_year_int_or_none(world, monkeypatch):
    gd, data, st = world
    named(monkeypatch, '1998 Test', season_year=1998)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert json.loads((data / '30L1998' / 'meta.json').read_text())['season_year'] == 1998
    named(monkeypatch, '1998 Test', season_year=True)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert json.loads((data / '30L1998' / 'meta.json').read_text())['season_year'] is None


def test_a_new_season_year_moves_the_seasons_news_to_past_and_copies_meta(tmp_path):
    out = tmp_path / 'data' / 'A'
    files = season_folder(out)
    w, lines = rolling(tmp_path)
    assert w.rollover('A', str(out), {'season_year': 1998}) == '1997'
    assert lines == ['A season 1997 news archived to past/1997']
    past = out / 'past' / '1997'
    for gone in ('recaps', 'pending', 'feed', 'scout', 'preview.json', 'awards.json', 'replay.json'):
        assert not (out / gone).exists() and (past / gone).exists()
    assert (past / 'recaps' / 'aa.json').exists() and (past / 'feed' / '10-01.json').exists()
    assert json.loads((past / 'meta.json').read_text()) == {'season_year': 1997}
    meta = json.loads((out / 'meta.json').read_text())      # the copy in past/ is the old one; this is the new season
    assert (meta['assn'], meta['season_year'], meta['last_day'], meta['played'], meta['stories']) == ('A', 1998, None, 0,
                                                                                                    0)
    stay = [f for f in files if f.split('/')[0] in ('history', 'moves', 'notes', 'contracts.json')]
    assert len(stay) == 4 and all((out / f).exists() for f in stay)


def test_a_second_rollover_into_a_used_name_does_not_overwrite(tmp_path):
    out = tmp_path / 'data' / 'A'
    season_folder(out)
    w, lines = rolling(tmp_path)
    assert w.rollover('A', str(out), {'season_year': 1998}) == '1997'
    assert w.rollover('A', str(out), {'season_year': 1998}) is None       # meta.json already holds 1998
    (out / 'recaps').mkdir()
    (out / 'recaps' / 'cc.json').write_text('{}')
    (out / 'meta.json').write_text(json.dumps({'season_year': 1997}))     # a 1997 backup restored and played again
    assert w.rollover('A', str(out), {'season_year': 1998}) == '1997-2'
    (out / 'meta.json').write_text(json.dumps({'season_year': 1997}))
    assert w.rollover('A', str(out), {'season_year': 1999}) == '1997-3'
    assert (out / 'past' / '1997' / 'recaps' / 'aa.json').exists()
    assert (out / 'past' / '1997-2' / 'recaps' / 'cc.json').exists()
    assert lines[1] == 'A season 1997 news archived to past/1997-2'


@pytest.mark.parametrize('stored,year', [(None, 1998), (1997, None), (1997, 1997), (True, 1998), (1997, True),
                                         ('1997', 1998), (1997, '1998')])
def test_no_rollover_without_two_different_int_years(tmp_path, stored, year):
    out = tmp_path / 'data' / 'A'
    files = season_folder(out)
    meta = {} if stored is None else {'season_year': stored}
    (out / 'meta.json').write_text(json.dumps(meta))
    w, lines = rolling(tmp_path)
    assert w.rollover('A', str(out), {'season_year': year}) is None
    assert lines == [] and not (out / 'past').exists() and all((out / f).exists() for f in files)


def test_no_rollover_without_a_readable_meta(tmp_path):
    out = tmp_path / 'data' / 'A'
    season_folder(out)
    w, lines = rolling(tmp_path)
    (out / 'meta.json').write_text('{not json')
    assert w.rollover('A', str(out), {'season_year': 1998}) is None
    (out / 'meta.json').unlink()
    assert w.rollover('A', str(out), {'season_year': 1998}) is None
    assert lines == [] and not (out / 'past').exists() and (out / 'recaps' / 'aa.json').exists()


def test_a_move_that_fails_leaves_the_rest_in_place_and_raises_for_scan_to_log(tmp_path, monkeypatch):
    out = tmp_path / 'data' / 'A'
    season_folder(out)
    w, lines = rolling(tmp_path)
    real = os.replace

    def replace(src, dst):
        if os.path.basename(src) == 'feed':
            raise OSError('disk')
        real(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(OSError):
        w.rollover('A', str(out), {'season_year': 1998})
    assert (out / 'past' / '.rolling-1997' / 'recaps').exists() and not (out / 'past' / '1997').exists()
    assert (out / 'feed' / '10-01.json').exists()
    assert (out / 'scout').exists() and lines == []


def test_a_scan_in_a_new_season_archives_the_old_and_starts_fresh(world, monkeypatch):
    gd, data, st = world
    out = data / '30L1998'
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    st['boxfile']('30L1998.H20', {'away': side(2, 0, 200), 'home': side(1, 5, 100)})
    lines = []
    named(monkeypatch, '1998 Test', season_year=1997)
    watch.Watcher(str(gd), str(data), None, None, log=lines.append).scan()
    assert len(stories(data)) == 2 and (out / 'preview.json').exists()
    (out / 'preview.json').write_text('{"kept": 1997}')
    (out / 'moves').mkdir(exist_ok=True)
    (out / 'moves' / 'log.json').write_text('{}')
    named(monkeypatch, '1998 Test', season_year=1998)
    w = watch.Watcher(str(gd), str(data), None, None, log=lines.append)
    w.scan()
    assert '30L1998 season 1997 news archived to past/1997' in lines
    assert json.loads((out / 'past' / '1997' / 'preview.json').read_text()) == {'kept': 1997}
    assert json.loads((out / 'preview.json').read_text())['kind'] == 'preview'
    assert len(list((out / 'past' / '1997' / 'recaps').iterdir())) == 2
    assert sorted(os.listdir(out / 'past' / '1997' / 'feed')) == ['04-01.json', '04-02.json']
    assert sorted(os.listdir(out / 'feed')) == ['04-01.json', '04-02.json']      # this season's own columns
    assert (out / 'moves' / 'log.json').exists()
    assert json.loads((out / 'meta.json').read_text())['season_year'] == 1998
    # The same box scores are last season's: neither captured again nor given a story in the new season.
    assert not (out / 'pending').exists() or not os.listdir(out / 'pending')
    assert not (out / 'recaps').exists() or not os.listdir(out / 'recaps')
    w2 = watch.Watcher(str(gd), str(data), None, None, log=lines.append)      # a restart forgets what it captured
    w2.seen.clear()
    w2.scan()
    assert not (out / 'pending').exists() or not os.listdir(out / 'pending')


def test_a_new_season_gets_a_fresh_preview_and_stories_on_the_old_slots(world, monkeypatch):
    gd, data, st = world
    out = data / '30L1998'
    named(monkeypatch, '1998 Test', season_year=1997)
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    archived = [s['key'] for s in stories(data)]
    assert len(archived) == 1
    named(monkeypatch, '1998 Test', season_year=1998)
    st['boxfile']('30L1998.H11', {'away': side(1, 4, 100), 'home': side(2, 2, 200)})     # a new game, same slot
    st['games'][0].update(away_runs=4, home_runs=2)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    got = stories(data)
    assert [s['day'] for s in got] == [1] and got[0]['key'] != archived[0]       # a story on the slot 1997 used
    assert (out / 'preview.json').exists() and (out / 'past' / '1997' / 'preview.json').exists()


def test_an_archived_box_score_is_not_captured_into_pending_again(world):
    gd, data, st = world
    out = data / '30L1998'
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    key = hashlib.sha1((gd / 'Stats' / '30L1998.H10').read_bytes()).hexdigest()[:16]
    (out / 'past' / '1997' / 'recaps').mkdir(parents=True)
    (out / 'past' / '1997' / 'recaps' / (key + '.json')).write_text('{}')
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    w.capture('30L1998')
    assert not (out / 'pending').exists()
    (out / 'past' / '1997' / 'recaps' / (key + '.json')).rename(out / 'past' / '1997' / 'recaps' / 'zz.json')
    (out / 'past' / '1997' / 'pending').mkdir()
    (out / 'past' / '1997' / 'pending' / (key + '.json')).write_text('{}')
    w.capture('30L1998')
    assert not (out / 'pending').exists()
    (out / 'past' / '1997' / 'pending' / (key + '.json')).unlink()
    w.capture('30L1998')
    assert (out / 'pending' / (key + '.json')).exists()


def test_meta_counts_played_games_and_recap_stories(world):
    """meta.json tells the reader the coverage: played games in the association and stories in recaps/."""
    gd, data, st = world
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    st['boxfile']('30L1998.H20', {'away': side(2, 0, 200), 'home': side(1, 5, 100)})
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    meta = json.loads((data / '30L1998' / 'meta.json').read_text())
    assert type(meta['played']) is int and type(meta['stories']) is int
    assert meta['played'] == 2 and meta['stories'] == 2


def test_meta_story_count_covers_older_recaps_and_skips_other_files(world):
    gd, data, st = world
    (data / '30L1998' / 'recaps').mkdir(parents=True)
    (data / '30L1998' / 'recaps' / 'old.json').write_text('{}')
    (data / '30L1998' / 'recaps' / 'note.txt').write_text('')
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    meta = json.loads((data / '30L1998' / 'meta.json').read_text())
    assert meta['stories'] == 1 and type(meta['played']) is int


ROOKIE_PLAYERS = {100: league_player('Al Winner', 'RF', 1970), 200: league_player('Bo Loser', 'P', 1975)}


@pytest.fixture
def rookie_world(world, monkeypatch):
    """world, with a PYR whose players are st['players'] (the two on the rosters), and a pass per season."""
    gd, data, st = world
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    st['players'] = dict(ROOKIE_PLAYERS)
    st['reads'] = []
    st['lines'] = []

    def players(path):
        st['reads'].append(path)
        return dict(st['players'])

    monkeypatch.setattr(gamedata, 'players', players)

    def scan(year):
        named(monkeypatch, '1998 Test', season_year=year)
        w = watch.Watcher(str(gd), str(data), None, None, log=st['lines'].append)
        w.scan()
        return w

    st['scan'] = scan
    return gd, data / '30L1998' / 'rookies', st


def ids_of(players, season=None):
    snap = {'ids': sorted([pid, p['name'], p['born']] for pid, p in players.items())}
    if season is not None:
        snap['season'] = season
    return snap


def test_the_first_pass_ever_writes_ids_and_no_class(rookie_world):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    assert os.listdir(rookies) == ['ids.json']
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(ROOKIE_PLAYERS, 1997)
    assert not [s for s in st['lines'] if 'rookie class' in s]


def test_a_new_season_writes_the_class_of_the_new_players_and_a_rescan_writes_nothing(rookie_world):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)               # a new pid
    st['players'][200] = league_player('Bo Loser Jr', 'P', 1979)                # a reused pid, a new man
    st['scan'](1998)
    assert sorted(os.listdir(rookies)) == ['1998.json', 'ids.json']
    rec = json.loads((rookies / '1998.json').read_text())
    assert (rec['kind'], rec['season'], rec['source'], rec['reason']) == ('rookies', 1998, 'template', 'off')
    assert rec['headline'] == 'The rookie class of 1998' and 'Rick Rookie' in rec['body']
    assert rec['facts']['count'] == 2 and rec['facts']['association'] == '1998 Test'
    assert [(h['pid'], h['age'], h['team']) for h in rec['facts']['hitters']] == [(300, 20, 'free agent')]
    assert [(p['pid'], p['name'], p['team']) for p in rec['facts']['pitchers']] == [(200, 'Bo Loser Jr', 'Birch')]
    assert rec['created']
    assert '30L1998 rookie class 1998: 2 players (template)' in st['lines']
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(st['players'], 1998)
    before = {f: (rookies / f).read_text() for f in os.listdir(rookies)}
    st['lines'].clear()
    st['reads'].clear()
    st['scan'](1998)
    assert {f: (rookies / f).read_text() for f in os.listdir(rookies)} == before
    assert not [s for s in st['lines'] if 'rookie class' in s]
    assert st['reads'] == []                                    # no rollover, ids.json there: the PYR is not read


def test_a_legacy_association_gets_a_baseline_at_its_first_rollover_and_no_class(rookie_world):
    gd, rookies, st = rookie_world
    out = rookies.parent
    out.mkdir(parents=True)
    (out / 'meta.json').write_text(json.dumps({'season_year': 1997}))
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    st['scan'](1998)
    assert (out / 'past' / '1997' / 'meta.json').exists()
    assert os.listdir(rookies) == ['ids.json']
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(st['players'], 1998)
    st['players'][400] = league_player('Next Year', '1B', 1980)
    st['scan'](1999)
    rec = json.loads((rookies / '1999.json').read_text())
    assert [h['pid'] for h in rec['facts']['hitters']] == [400] and rec['facts']['count'] == 1


def test_a_season_with_no_new_players_writes_no_class_but_moves_the_snapshot_on(rookie_world):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    (rookies / 'ids.json').write_text(json.dumps({'ids': [[100, 'Al Winner', 1970]]}))     # 200 was added since
    st['scan'](1998)
    assert sorted(os.listdir(rookies)) == ['1998.json', 'ids.json']
    (rookies / '1998.json').unlink()
    st['players'].pop(200)                                      # nobody new, one gone
    st['scan'](1999)
    assert os.listdir(rookies) == ['ids.json']
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(st['players'], 1999)


def test_an_existing_class_file_is_never_rewritten(rookie_world):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    (rookies / '1998.json').write_text('{"kept": true}')
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    st['scan'](1998)
    assert json.loads((rookies / '1998.json').read_text()) == {'kept': True}
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(st['players'], 1998)


def test_a_malformed_snapshot_at_a_rollover_is_replaced_without_a_class(rookie_world):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    (rookies / 'ids.json').write_text(json.dumps({'ids': 'x'}))
    st['scan'](1998)
    assert os.listdir(rookies) == ['ids.json']
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(st['players'], 1998)


def test_no_pyr_writes_no_rookies_folder(world):
    gd, data, st = world
    w = watch.Watcher(str(gd), str(data), None, None, log=lambda s: None)
    w.scan()
    assert not (data / '30L1998' / 'rookies').exists()


def test_an_empty_pyr_writes_nothing_and_the_class_waits_for_a_read_that_works(rookie_world):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    before = (rookies / 'ids.json').read_text()
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    saved = dict(st['players'])
    st['players'].clear()
    w = st['scan'](1998)                                        # the rollover pass reads a PYR with nobody in it
    assert os.listdir(rookies) == ['ids.json'] and (rookies / 'ids.json').read_text() == before
    st['players'].update(saved)
    w.seen.clear()
    w.scan()
    assert json.loads((rookies / '1998.json').read_text())['facts']['count'] == 1


def test_a_failure_at_the_rollover_is_retried_by_the_next_pass(rookie_world, monkeypatch):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    facts = watch.rookies.class_facts
    broken = {'on': True}

    def class_facts(*args):
        if broken['on']:
            raise OSError('torn')
        return facts(*args)

    monkeypatch.setattr(watch.rookies, 'class_facts', class_facts)
    w = st['scan'](1998)
    assert any('OSError: torn' in s for s in st['lines']) and not (rookies / '1998.json').exists()
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(ROOKIE_PLAYERS, 1997)       # still last season's
    broken['on'] = False
    w.seen.clear()
    w.scan()
    assert json.loads((rookies / '1998.json').read_text())['facts']['count'] == 1
    assert json.loads((rookies / 'ids.json').read_text()) == ids_of(st['players'], 1998)


def test_the_class_goes_to_the_model_when_there_is_one(rookie_world, monkeypatch):
    gd, rookies, st = rookie_world
    st['scan'](1997)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    calls = []

    def write(facts, budget, complete):
        calls.append(facts['count'])
        return {'headline': 'Fresh faces', 'body': 'One new man.', 'source': 'glm'}

    monkeypatch.setattr(watch.rookies, 'write', write)
    named(monkeypatch, '1998 Test', season_year=1998)
    w = watch.Watcher(str(gd), str(rookies.parent.parent), object(), lambda *a: None, log=st['lines'].append)
    monkeypatch.setattr(w, 'columns', lambda *a: None)
    monkeypatch.setattr(w, 'recaps', lambda *a: None)
    monkeypatch.setattr(w, 'scouting', lambda *a: None)
    monkeypatch.setattr(watch.season, 'write_preview', lambda f, b, c: {'headline': 'h', 'body': 'b', 'source': 'glm'})
    w.scan()
    rec = json.loads((rookies / '1998.json').read_text())
    assert calls == [1]
    assert (rec['headline'], rec['source'], rec['kind'], rec['season']) == ('Fresh faces', 'glm', 'rookies', 1998)
    assert '30L1998 rookie class 1998: 1 players (glm)' in st['lines']


FIXED_NOW = 1000000000      # 2001-09-09 01:46:40 UTC
FIXED_NAME = 'rewind-20010909T014640'


def story_file(out, key, month, day):
    (out / 'recaps').mkdir(parents=True, exist_ok=True)
    (out / 'recaps' / (key + '.json')).write_text(json.dumps({'key': key, 'month': month, 'day': day, 'slot': 0}))


def rewinding(tmp_path, monkeypatch, meta=None):
    """An association folder at 04-20 of 1998 with stories and columns on 04-05, 04-10, 04-11 and 04-20, and a Watcher
    whose clock is fixed."""
    out = tmp_path / 'data' / 'A'
    out.mkdir(parents=True)
    (out / 'meta.json').write_text(json.dumps({'season_year': 1998, 'last_day': [4, 20]} if meta is None else meta))
    for key, (month, day) in {'a5': (4, 5), 'a10': (4, 10), 'b11': (4, 11), 'b20': (4, 20)}.items():
        story_file(out, key, month, day)
        (out / 'feed').mkdir(exist_ok=True)
        (out / 'feed' / ('%02d-%02d.json' % (month, day))).write_text('{}')
    for name in ('awards.json', 'preview.json', 'replay.json', 'contracts.json', 'pending/p.json', 'scout/3.json',
                 'history/1998.json', 'moves/log.json', 'notes/1.json'):
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text('{}')
    fixed = time.gmtime(FIXED_NOW)
    monkeypatch.setattr(time, 'gmtime', lambda *a: fixed)
    return out, *rolling(tmp_path)


def played_through(month, day, year=1998):
    return {'season_year': year, 'games': [{'month': 4, 'day': 3, 'played': True},
                                           {'month': month, 'day': day, 'played': True},
                                           {'month': 5, 'day': 1, 'played': False}]}


def test_a_rewind_moves_the_days_after_the_new_last_day_and_the_awards(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch)
    assert w.rewind('A', str(out), played_through(4, 10)) == FIXED_NAME
    dest = out / 'past' / FIXED_NAME
    assert sorted(os.listdir(out / 'recaps')) == ['a10.json', 'a5.json']
    assert sorted(os.listdir(dest / 'recaps')) == ['b11.json', 'b20.json']
    assert sorted(os.listdir(out / 'feed')) == ['04-05.json', '04-10.json']
    assert sorted(os.listdir(dest / 'feed')) == ['04-11.json', '04-20.json']
    assert not (out / 'awards.json').exists() and (dest / 'awards.json').exists()
    assert json.loads((dest / 'meta.json').read_text()) == {'season_year': 1998, 'last_day': [4, 20]}
    assert json.loads((out / 'meta.json').read_text()) == {'season_year': 1998, 'last_day': [4, 10]}
    for stays in ('preview.json', 'replay.json', 'contracts.json', 'pending/p.json', 'scout/3.json',
                  'history/1998.json', 'moves/log.json', 'notes/1.json'):
        assert (out / stays).exists() and not (dest / stays).exists()
    assert sorted(os.listdir(dest)) == ['awards.json', 'feed', 'meta.json', 'recaps']
    assert lines == ['A rewound from 04-20 to 04-10: 2 stories, 2 columns moved to past/' + FIXED_NAME]


def test_a_rewind_to_before_the_first_game_moves_every_dated_story(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch)
    story_file(out, 'undated', 4, 1)
    (out / 'recaps' / 'undated.json').write_text(json.dumps({'key': 'undated', 'slot': 0}))
    (out / 'recaps' / 'broken.json').write_text('{not json')
    (out / 'recaps' / 'strings.json').write_text(json.dumps({'month': '4', 'day': '30'}))
    (out / 'recaps' / 'list.json').write_text('[]')
    (out / 'recaps' / 'note.txt').write_text('x')
    (out / 'feed' / 'other.json').write_text('{}')
    assoc = {'season_year': 1998, 'games': [{'month': 4, 'day': 1, 'played': False}]}
    assert w.rewind('A', str(out), assoc) == FIXED_NAME
    dest = out / 'past' / FIXED_NAME
    assert sorted(os.listdir(dest / 'recaps')) == ['a10.json', 'a5.json', 'b11.json', 'b20.json']
    assert sorted(os.listdir(out / 'recaps')) == ['broken.json', 'list.json', 'note.txt', 'strings.json', 'undated.json']
    assert sorted(os.listdir(out / 'feed')) == ['other.json']
    assert lines == ['A rewound from 04-20 to opening day: 4 stories, 4 columns moved to past/' + FIXED_NAME]


@pytest.mark.parametrize('meta,assoc', [
    ({}, played_through(4, 20)),                                        # same last day
    ({}, played_through(4, 25)),                                        # later
    ({}, played_through(5, 1)),
    ({}, played_through(4, 10, year=1999)),                             # another season: the rollover's
    ({}, played_through(4, 10, year=None)),
    ({}, played_through(4, 10, year=True)),
    ({'season_year': None}, played_through(4, 10)),
    ({'season_year': True}, played_through(4, 10, year=True)),
    ({'season_year': '1998'}, played_through(4, 10)),
    ({'last_day': None}, played_through(4, 10)),
    ({'last_day': [4]}, played_through(4, 10)),
    ({'last_day': [4, 20, 1]}, played_through(4, 10)),
    ({'last_day': ['4', 20]}, played_through(4, 10)),
    ({'last_day': [4, 20.0]}, played_through(4, 10)),
    ({'last_day': [4, True]}, played_through(4, 10)),
    ({'last_day': '04-20'}, played_through(4, 10)),
    ({'last_day': {'month': 4}}, played_through(4, 10)),
])
def test_no_rewind_unless_the_same_season_is_back_before_its_last_day(tmp_path, monkeypatch, meta, assoc):
    out, w, lines = rewinding(tmp_path, monkeypatch, meta=dict({'season_year': 1998, 'last_day': [4, 20]}, **meta))
    before = sorted(str(p) for p in out.rglob('*'))
    assert w.rewind('A', str(out), assoc) is None
    assert lines == [] and not (out / 'past').exists() and sorted(str(p) for p in out.rglob('*')) == before


def test_no_rewind_without_a_last_day_or_a_year_in_meta(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch, meta={'season_year': 1998})
    assert w.rewind('A', str(out), played_through(4, 10)) is None
    (out / 'meta.json').write_text(json.dumps({'last_day': [4, 20]}))
    assert w.rewind('A', str(out), played_through(4, 10)) is None
    assert lines == [] and not (out / 'past').exists() and (out / 'awards.json').exists()


def test_no_rewind_without_a_readable_meta_dict(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch)
    for text in ('{not json', '[4, 20]', 'null'):
        (out / 'meta.json').write_text(text)
        assert w.rewind('A', str(out), played_through(4, 10)) is None
    (out / 'meta.json').unlink()
    assert w.rewind('A', str(out), played_through(4, 10)) is None
    assert lines == [] and not (out / 'past').exists() and (out / 'recaps' / 'b20.json').exists()


def test_a_second_rewind_in_the_same_second_gets_a_numbered_folder(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch)
    resimmed = json.dumps({'season_year': 1998, 'last_day': [4, 20]})     # a pass wrote meta at 04-20 again
    assert w.rewind('A', str(out), played_through(4, 10)) == FIXED_NAME
    story_file(out, 'c15', 4, 15)
    (out / 'meta.json').write_text(resimmed)
    assert w.rewind('A', str(out), played_through(4, 10)) == FIXED_NAME + '-2'
    story_file(out, 'c16', 4, 16)
    (out / 'meta.json').write_text(resimmed)
    assert w.rewind('A', str(out), played_through(4, 10)) == FIXED_NAME + '-3'
    assert sorted(os.listdir(out / 'past' / FIXED_NAME / 'recaps')) == ['b11.json', 'b20.json']
    assert os.listdir(out / 'past' / (FIXED_NAME + '-2') / 'recaps') == ['c15.json']
    assert os.listdir(out / 'past' / (FIXED_NAME + '-3') / 'recaps') == ['c16.json']
    assert lines[1] == 'A rewound from 04-20 to 04-10: 1 stories, 0 columns moved to past/' + FIXED_NAME + '-2'


def test_a_rewind_sets_meta_to_the_new_last_day_so_the_next_pass_does_not_rewind_again(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch)
    assert w.rewind('A', str(out), played_through(4, 10)) == FIXED_NAME
    meta = json.loads((out / 'meta.json').read_text())
    assert meta == {'season_year': 1998, 'last_day': [4, 10]}
    assert json.loads((out / 'past' / FIXED_NAME / 'meta.json').read_text())['last_day'] == [4, 20]
    assert w.rewind('A', str(out), played_through(4, 10)) is None
    assert os.listdir(out / 'past') == [FIXED_NAME] and len(lines) == 1


def test_a_rewind_move_that_fails_leaves_the_rest_for_the_next_pass(tmp_path, monkeypatch):
    out, w, lines = rewinding(tmp_path, monkeypatch)
    real = os.replace

    def replace(src, dst):
        if os.path.basename(src) == '04-20.json':
            raise OSError('disk')
        real(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(OSError):
        w.rewind('A', str(out), played_through(4, 10))
    assert (out / 'past' / FIXED_NAME / 'recaps' / 'b20.json').exists() and (out / 'feed' / '04-20.json').exists()
    assert (out / 'awards.json').exists() and lines == []
    monkeypatch.setattr(os, 'replace', real)
    assert w.rewind('A', str(out), played_through(4, 10)) == FIXED_NAME + '-2'
    assert not (out / 'feed' / '04-20.json').exists() and not (out / 'awards.json').exists()


def test_a_scan_after_a_restore_writes_stories_for_the_re_simmed_days(world, monkeypatch):
    gd, data, st = world
    out = data / '30L1998'
    named(monkeypatch, '1998 Test', season_year=1998)
    st['boxfile']('30L1998.H10', {'away': side(1, 3, 100), 'home': side(2, 1, 200)})
    st['boxfile']('30L1998.H20', {'away': side(2, 0, 200), 'home': side(1, 5, 100)})
    lines = []
    watch.Watcher(str(gd), str(data), None, None, log=lines.append).scan()
    first = {s['day']: s['key'] for s in stories(data)}
    assert sorted(first) == [1, 2] and json.loads((out / 'meta.json').read_text())['last_day'] == [4, 2]
    (out / 'awards.json').write_text('{}')
    st['games'][1].update(played=False, away_runs=0, home_runs=0)           # the backup: day 2 is still to play
    watch.Watcher(str(gd), str(data), None, None, log=lines.append).scan()
    (rewound,) = os.listdir(out / 'past')
    assert rewound.startswith('rewind-') and [s['day'] for s in stories(data)] == [1]
    assert os.listdir(out / 'past' / rewound / 'recaps') == [first[2] + '.json']
    assert os.listdir(out / 'past' / rewound / 'feed') == ['04-02.json'] and (out / 'past' / rewound / 'awards.json').exists()
    assert sorted(os.listdir(out / 'feed')) == ['04-01.json'] and not (out / 'awards.json').exists()
    assert lines[-1].startswith('30L1998 rewound from 04-02 to 04-01: 1 stories, 1 columns moved to past/rewind-')
    assert json.loads((out / 'meta.json').read_text())['last_day'] == [4, 1]
    st['games'][1].update(played=True, away_runs=1, home_runs=2)            # the same day, played out differently
    st['boxfile']('30L1998.H20', {'away': side(2, 1, 200), 'home': side(1, 2, 100)})
    watch.Watcher(str(gd), str(data), None, None, log=lines.append).scan()
    again = {s['day']: s['key'] for s in stories(data)}
    assert sorted(again) == [1, 2] and again[1] == first[1] and again[2] != first[2]
    assert sorted(os.listdir(out / 'feed')) == ['04-01.json', '04-02.json']
    assert os.listdir(out / 'past') == [rewound]                            # one rewind, not one per scan


def test_a_game_folder_with_no_assn_has_no_associations_and_a_pass_does_nothing(tmp_path):
    assert watch.associations(str(tmp_path / 'gone')) == {}
    lines = []
    watch.Watcher(str(tmp_path / 'gone'), str(tmp_path / 'data'), None, None, log=lines.append).scan()
    assert lines == []


def test_main_logs_a_failed_pass_and_keeps_watching(tmp_path, monkeypatch, capsys):
    calls = []

    def scan(self):
        calls.append(1)
        if len(calls) == 1:
            raise FileNotFoundError('AB.H02')
        raise KeyboardInterrupt
    monkeypatch.setattr(watch.Watcher, 'scan', scan)
    monkeypatch.setattr(watch.time, 'sleep', lambda s: None)
    with pytest.raises(KeyboardInterrupt):
        watch.main(['--game', str(tmp_path / 'g'), '--data', str(tmp_path / 'd'), '--no-llm'])
    assert len(calls) == 2 and 'scan failed: FileNotFoundError: AB.H02' in capsys.readouterr().out


def test_main_once_still_raises_a_failed_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(watch.Watcher, 'scan', lambda self: (_ for _ in ()).throw(FileNotFoundError('x')))
    with pytest.raises(FileNotFoundError):
        watch.main(['--game', str(tmp_path / 'g'), '--data', str(tmp_path / 'd'), '--no-llm', '--once'])


def test_scouting_grades_the_public_fog_view_not_the_true_ratings(world, monkeypatch):
    gd, data, st = world
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    unseen = {pid: dict(p, seasons=0) for pid, p in SCOUT_PLAYERS.items()}       # rookies: the widest fog
    before = {pid: dict(p) for pid, p in unseen.items()}
    monkeypatch.setattr(gamedata, 'players', lambda path: unseen)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert unseen == before
    ash = json.loads((data / '30L1998' / 'scout' / '1.json').read_text())
    al = ash['roster']['hitters'][0]
    for key in ('contact', 'power', 'speed', 'fielding'):
        assert al[key] == watch.scout.grade(fog.rating(unseen[100][key], '30L1998', 0, 100, key, 1998, 0))
    assert [al[k] for k in ('contact', 'power', 'speed', 'fielding')] != [
        watch.scout.grade(unseen[100][k]) for k in ('contact', 'power', 'speed', 'fielding')]
    assert (ash['facts']['hitters'][0]['contact'], ash['facts']['hitters'][0]['power']) == (al['contact'], al['power'])
    birch = json.loads((data / '30L1998' / 'scout' / '2.json').read_text())['roster']['pitchers'][0]
    for key in ('control', 'strikeout', 'stamina'):
        assert birch[key] == watch.scout.grade(fog.rating(unseen[200][key], '30L1998', 0, 200, key, 1998, 0))


@pytest.fixture
def draft_world(league, monkeypatch):
    """league (rosters, free agents, players, PYR and PYF, DAT), with a pass per season and a count of the PYR reads
    draft_piece makes (st['draft_reads']; moves and contracts read it too, on every settled pass)."""
    gd, data, st = league
    st['draft_reads'], st['lines'] = [], []
    inside = []
    original = watch.Watcher.draft_piece

    def draft_piece(self, *args):
        inside.append(1)
        try:
            return original(self, *args)
        finally:
            inside.pop()

    def players(path):
        if inside:
            st['draft_reads'].append(path)
        return dict(st['players'])

    monkeypatch.setattr(watch.Watcher, 'draft_piece', draft_piece)
    monkeypatch.setattr(gamedata, 'players', players)

    def scan(year, settled=True):
        named(monkeypatch, '1998 Test', season_year=year)
        w = watch.Watcher(str(gd), str(data), None, None, log=st['lines'].append)
        league_scan(w, gd, st, settled)
        return w

    st['scan'] = scan
    return gd, data / '30L1998', st


def drafted(draft_world):
    """draft_world after the 1997 baseline pass and the 1998 pass that writes the class of 300 (a shortstop on Ash) and
    500 (a pitcher on Birch). Returns (gd, out, st)."""
    gd, out, st = draft_world
    st['scan'](1997)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    st['players'][500] = league_player('Pete Pitcher', 'P', 1979)
    st['rosters'][1].append(300)
    st['rosters'][2].append(500)
    st['fa'].discard(300)
    st['scan'](1998)
    return gd, out, st


def draft_file(out, year=1998):
    return json.loads((out / 'draft' / ('%d.json' % year)).read_text())


def test_the_class_is_drafted_in_the_pass_that_writes_it_and_a_rescan_reads_nothing(draft_world):
    gd, out, st = drafted(draft_world)
    assert sorted(os.listdir(out / 'draft')) == ['1998.json']
    doc = draft_file(out)
    assert (doc['year'], doc['revisit']) == (1998, None) and doc['created']
    assert [(p['pid'], p['name'], p['pos'], p['age'], p['team'], p['tid']) for p in sorted(doc['picks'], key=lambda p: p['pid'])] == [
        (300, 'Rick Rookie', 'SS', 20, 'Ash', 1), (500, 'Pete Pitcher', 'P', 19, 'Birch', 2)]
    for pick in doc['picks']:
        seen = fog.view(st['players'][pick['pid']], '30L1998', 0, 1998, pid=pick['pid'])
        assert pick['grades'] == draft.grades(seen) and pick['value'] == contracts._index(seen)
    assert {t['tid'] for t in doc['teams']} == {1, 2} and all(t['grade'] in 'ABCDF' for t in doc['teams'])
    assert '30L1998 draft 1998: 2 picks' in st['lines']
    before = (out / 'draft' / '1998.json').read_text()
    st['draft_reads'].clear()
    st['lines'].clear()
    st['scan'](1998)
    assert (out / 'draft' / '1998.json').read_text() == before and st['draft_reads'] == []
    assert not [s for s in st['lines'] if 'draft' in s]


def test_the_pyr_is_not_read_for_a_draft_in_a_season_with_nothing_due(draft_world):
    gd, out, st = drafted(draft_world)
    for year in (1999, 2000):                                   # 1998 + 3 is 2001
        st['draft_reads'].clear()
        st['scan'](year)
        assert draft.REVISIT_AFTER == 3 and draft_file(out)['revisit'] is None
        assert st['draft_reads'] == [] and not [s for s in st['lines'] if 'revisited' in s]


def test_an_existing_draft_file_is_never_rewritten_and_an_earlier_class_is_never_drafted_late(draft_world):
    gd, out, st = draft_world
    st['scan'](1997)
    (out / 'rookies').mkdir(exist_ok=True)
    (out / 'rookies' / '1997.json').write_text(json.dumps({'facts': {'hitters': [{'pid': 100}], 'pitchers': []}}))
    st['scan'](1998)
    assert not (out / 'draft').exists()                         # the 1997 class is not this season's
    (out / 'draft').mkdir()
    (out / 'draft' / '1998.json').write_text('{"kept": true}')
    (out / 'rookies' / '1998.json').write_text(json.dumps({'facts': {'hitters': [{'pid': 100}], 'pitchers': []}}))
    st['draft_reads'].clear()
    st['scan'](1998)
    assert json.loads((out / 'draft' / '1998.json').read_text()) == {'kept': True} and st['draft_reads'] == []


def test_no_pyr_and_no_class_write_no_draft(world, monkeypatch):
    gd, data, st = world
    out = data / '30L1998'
    (out / 'rookies').mkdir(parents=True)
    (out / 'rookies' / '1998.json').write_text(json.dumps({'facts': {'hitters': [{'pid': 100}], 'pitchers': []}}))
    named(monkeypatch, '1998 Test', season_year=1998)
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert not (out / 'draft').exists()                          # no PYR: nothing to grade
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')
    monkeypatch.setattr(gamedata, 'players', lambda path: {100: league_player('Al Winner', 'RF', 1970)})
    (out / 'rookies' / '1998.json').unlink()
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    assert not (out / 'draft').exists()                          # a PYR but no class file


def archive(data, year, bat=(), pit=()):
    history.archive_season(str(data), '30L1998', year, {'bat': {pid: {'g': 5} for pid in bat},
                                                       'pit': {pid: {'g': 5} for pid in pit}})


def test_three_seasons_on_the_draft_is_revisited_once_with_true_grades_and_seasons(draft_world):
    gd, out, st = drafted(draft_world)
    data = out.parent
    archive(data, 1997, bat=[300])                                # an earlier man of that pid: not counted
    for y in (1998, 1999, 2000):
        archive(data, y, bat=[300] if y != 1999 else [300, 500], pit=[500] if y == 1999 else [])
    st['players'][300] = dict(st['players'][300], contact=99, power=99, speed=99, fielding=99)    # he grew
    st['rosters'][2].remove(500)                                  # Pete left every roster and is no free agent
    st['draft_reads'].clear()
    st['scan'](2001)
    doc = draft_file(out)
    rev = doc['revisit']
    assert rev['year'] == 2001 and sorted(rev['picks']) == ['300', '500']
    assert rev['picks']['300'] == {'grades': {'contact': 80, 'power': 80, 'speed': 80, 'fielding': 80}, 'seasons': 3,
                                   'value': contracts._index(st['players'][300]) + 6, 'gone': False}
    assert rev['picks']['500'] == {'grades': {}, 'seasons': 1, 'value': 2.0, 'gone': True}
    assert {t['tid'] for t in rev['teams']} == {1, 2} and all(t['grade'] in 'ABCDF' for t in rev['teams'])
    assert [p['pid'] for p in doc['picks']] == [p['pid'] for p in draft_file(out)['picks']]
    assert '30L1998 draft 1998 revisited in 2001: 2 picks' in st['lines']
    before = (out / 'draft' / '1998.json').read_text()
    for year in (2001, 2002):
        st['draft_reads'].clear()
        st['scan'](year)
        assert (out / 'draft' / '1998.json').read_text() == before and st['draft_reads'] == []      # once


def test_a_free_agent_is_not_retired_and_a_draft_found_late_is_revisited_when_it_is_due(draft_world):
    gd, out, st = drafted(draft_world)
    st['rosters'][2].remove(500)
    st['fa'].add(500)                                             # Pete is a free agent now
    st['scan'](2004)                                              # the watcher was off for years: still due
    rev = draft_file(out)['revisit']
    assert rev['year'] == 2004 and rev['picks']['500']['gone'] is False and rev['picks']['500']['seasons'] == 0
    assert rev['picks']['500']['grades'] and rev['picks']['300']['gone'] is False


def test_the_revisit_waits_for_a_settled_pyr_and_pyf_that_can_be_read(draft_world):
    gd, out, st = drafted(draft_world)
    st['scan'](2001, settled=False)
    assert draft_file(out)['revisit'] is None
    pyf = gd / 'Assn' / '30L1998.PYF'
    st['scan'](2001)
    assert draft_file(out)['revisit'] is not None                 # settled now
    (out / 'draft' / '1998.json').write_text(json.dumps(dict(draft_file(out), revisit=None)))
    for broken in (None, b'junk'):
        if broken is None:
            pyf.unlink()
        else:
            pyf.write_bytes(broken)
        os.utime(gd / 'Assn' / '30L1998.PYR', (1, 1))
        if pyf.exists():
            os.utime(pyf, (1, 1))
        st['draft_reads'].clear()
        watch.Watcher(str(gd), str(out.parent), None, None, log=st['lines'].append).scan()
        assert draft_file(out)['revisit'] is None and st['draft_reads'] == []   # a PYF that cannot be read waits


def test_a_malformed_old_draft_file_is_left_alone(draft_world):
    gd, out, st = draft_world
    (out / 'draft').mkdir(parents=True)
    for name, text in (('1990.json', '{"kept": true}'), ('1991.json', '[1]'), ('1992.json', 'junk'),
                       ('1993.json', '{"picks": 1, "teams": [], "revisit": null}'), ('notes.json', '{}')):
        (out / 'draft' / name).write_text(text)
    st['scan'](2001)
    assert sorted(os.listdir(out / 'draft')) == ['1990.json', '1991.json', '1992.json', '1993.json', 'notes.json']
    assert json.loads((out / 'draft' / '1990.json').read_text()) == {'kept': True}
    assert st['draft_reads'] == [] and not any('revisited' in s for s in st['lines'])
