"""The rookie class survives a restart: ids.json records the season it was taken in, so a new Watcher after a failed
rollover pass still finds the class due. The fixtures are test_watch.py's (a fake game directory, gamedata replaced)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import rookies   # noqa: E402
import watch     # noqa: E402

TEAMS = {1: {'tid': 1, 'name': 'Ash', 'abbrev': 'ASH', 'city': 'X', 'stadium': 'Ash Park', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [100]},
         2: {'tid': 2, 'name': 'Birch', 'abbrev': 'BIR', 'city': 'X', 'stadium': 'Birch Field', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [200]}}


def game(day, slot, away, home, ar, hr, played=True):
    return {'month': 4, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': 9}


@pytest.fixture
def world(tmp_path, monkeypatch):
    gd = tmp_path / 'game'
    (gd / 'Assn').mkdir(parents=True)
    (gd / 'Stats').mkdir()
    (gd / 'Assn' / '30L1998.ASN').write_bytes(b'asn')
    st = {'games': [game(1, 0, 1, 2, 3, 1), game(2, 0, 2, 1, 0, 5), game(3, 0, 1, 2, 0, 0, played=False)],
          'boxes': {}}
    monkeypatch.setattr(gamedata, 'association', lambda path: {'name': '1998 Test', 'teams': TEAMS,
                                                              'games': [dict(g) for g in st['games']]})
    monkeypatch.setattr(gamedata, 'names', lambda path: {100: 'Al Winner', 200: 'Bo Loser'})
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: {'bat': {}, 'pit': {}})
    monkeypatch.setattr(gamedata, 'boxscore', lambda path: st['boxes'][str(path)])
    return gd, tmp_path / 'data', st


def named(monkeypatch, name, **over):
    """The world's association under another name, with any other keys given."""
    read = gamedata.association
    monkeypatch.setattr(gamedata, 'association', lambda path: dict(read(path), name=name, **over))


def league_player(name, pos, born):
    """A player as gamedata.players() gives him: the ratings the scouting pages read, all 50."""
    return {'name': name, 'pos': pos, 'born': born, 'bats': 'R', 'throws': 'R', 'contact': 50, 'power': 50,
            'speed': 50, 'stamina': 50, 'control': 50, 'strikeout': 50, 'fielding': 50}


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


def ids(rookies_dir):
    return json.loads((rookies_dir / 'ids.json').read_text())


def breaking(monkeypatch):
    """class_facts raising OSError until the returned switch is turned off."""
    facts = watch.rookies.class_facts
    broken = {'on': True}

    def class_facts(*args):
        if broken['on']:
            raise OSError('torn')
        return facts(*args)

    monkeypatch.setattr(watch.rookies, 'class_facts', class_facts)
    return broken


def test_the_snapshot_records_its_season_and_a_rescan_reads_no_pyr(rookie_world):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    assert ids(rookies_dir) == {'ids': ids_of(ROOKIE_PLAYERS)['ids'], 'season': 1997}
    st['reads'].clear()
    st['scan'](1997)
    assert st['reads'] == []


def test_a_restart_after_a_failed_rollover_pass_still_writes_the_class(rookie_world, monkeypatch):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    broken = breaking(monkeypatch)
    st['scan'](1998)
    assert any('OSError: torn' in s for s in st['lines']) and not (rookies_dir / '1998.json').exists()
    assert ids(rookies_dir) == ids_of(ROOKIE_PLAYERS, 1997)                 # still last season's
    broken['on'] = False
    st['scan'](1998)                                            # a new Watcher: rookies_due starts empty
    rec = json.loads((rookies_dir / '1998.json').read_text())
    assert rec['facts']['count'] == 1 and [h['pid'] for h in rec['facts']['hitters']] == [300]
    assert ids(rookies_dir) == ids_of(st['players'], 1998)
    before = {f: (rookies_dir / f).read_text() for f in os.listdir(rookies_dir)}
    st['reads'].clear()
    st['scan'](1998)                                            # and once written it is not due again
    assert st['reads'] == []
    assert {f: (rookies_dir / f).read_text() for f in os.listdir(rookies_dir)} == before


def test_a_legacy_snapshot_with_no_rollover_writes_no_class_and_reads_no_pyr(rookie_world):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    legacy = json.dumps({'ids': [[100, 'Al Winner', 1970]]})
    (rookies_dir / 'ids.json').write_text(legacy)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    st['reads'].clear()
    st['scan'](1997)
    assert os.listdir(rookies_dir) == ['ids.json'] and (rookies_dir / 'ids.json').read_text() == legacy
    assert st['reads'] == []


@pytest.mark.parametrize('season', [True, '1997', None])
def test_a_snapshot_season_that_is_not_an_int_counts_as_no_season(rookie_world, season):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    stale = json.dumps({'ids': [[100, 'Al Winner', 1970]], 'season': season})
    (rookies_dir / 'ids.json').write_text(stale)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    st['reads'].clear()
    st['scan'](1997)                                            # a restart in the same season: no rollover
    assert st['reads'] == []
    assert os.listdir(rookies_dir) == ['ids.json'] and (rookies_dir / 'ids.json').read_text() == stale


def test_an_int_season_other_than_this_one_is_what_makes_the_class_due(rookie_world):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    (rookies_dir / 'ids.json').write_text(json.dumps({'ids': [[100, 'Al Winner', 1970]], 'season': 1996}))
    st['scan'](1997)
    assert json.loads((rookies_dir / '1997.json').read_text())['facts']['count'] == 1
    assert ids(rookies_dir) == ids_of(st['players'], 1997)


def test_an_empty_pyr_after_a_restart_writes_nothing_and_the_class_waits(rookie_world, monkeypatch):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    broken = breaking(monkeypatch)
    st['scan'](1998)
    broken['on'] = False
    saved = dict(st['players'])
    st['players'].clear()
    st['scan'](1998)                                            # restarted onto a PYR with nobody in it
    assert os.listdir(rookies_dir) == ['ids.json'] and ids(rookies_dir) == ids_of(ROOKIE_PLAYERS, 1997)
    st['players'].update(saved)
    st['scan'](1998)
    assert json.loads((rookies_dir / '1998.json').read_text())['facts']['count'] == 1


def test_a_restart_never_rewrites_an_existing_class_file(rookie_world, monkeypatch):
    gd, rookies_dir, st = rookie_world
    st['scan'](1997)
    (rookies_dir / '1998.json').write_text('{"kept": true}')
    st['players'][300] = league_player('Rick Rookie', 'SS', 1978)
    broken = breaking(monkeypatch)
    st['scan'](1998)                                            # the file exists, so class_facts is never reached
    assert not any('OSError' in s for s in st['lines'])
    assert json.loads((rookies_dir / '1998.json').read_text()) == {'kept': True}
    assert ids(rookies_dir) == ids_of(st['players'], 1998)
