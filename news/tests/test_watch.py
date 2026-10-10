"""watch.Watcher over a fake game directory: gamedata's readers are replaced by dicts, so no game files are needed."""
import json
import os
import struct
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
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


SCOUT_PLAYERS = {
    100: {'name': 'Al Winner', 'pos': 'RF', 'bats': 'L', 'throws': 'L', 'born': 1970, 'contact': 90, 'power': 60,
          'speed': 70, 'stamina': 0, 'control': 0, 'strikeout': 0, 'fielding': 50},
    200: {'name': 'Bo Loser', 'pos': 'P', 'bats': '', 'throws': 'R', 'born': None, 'contact': 0, 'power': 0,
          'speed': 0, 'stamina': 69, 'control': 97, 'strikeout': 47, 'fielding': 40},
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
    assert (data / '30L1998' / 'replay.json').read_text() == before
