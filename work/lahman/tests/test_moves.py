"""moves.py on an in-memory Lahman (stints, moves_for, first_team), and build.py's side of --moves: the MOV document
(mov_doc), its writer (write_moves) and the argument. No game files or Lahman database needed."""
import inspect
import json
import os
import sqlite3

import pytest

from lahman import build as B, lahdb, moves as M, teamnames

APP_SQL = ', '.join('%s INTEGER' % c for c in lahdb.APP_COLS)


def make_db(team_lg=True, app_lg=True):
    """An in-memory Lahman with only the columns moves.py and lahdb.appearances read; lgID lives in teams and in
    appearances unless left out."""
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE teams (yearID INTEGER, %s teamID TEXT, G INTEGER)' % ('lgID TEXT,' if team_lg else ''))
    con.execute('CREATE TABLE appearances (yearID INTEGER, teamID TEXT, %s playerID TEXT, %s)'
                % ('lgID TEXT,' if app_lg else '', APP_SQL))
    con.execute('CREATE TABLE batting (playerID TEXT, yearID INTEGER, stint INTEGER, teamID TEXT)')
    con.execute('CREATE TABLE pitching (playerID TEXT, yearID INTEGER, stint INTEGER, teamID TEXT)')
    return con


def team(con, year, tid, lg, games=100, team_lg=True):
    if team_lg:
        con.execute('INSERT INTO teams (yearID, lgID, teamID, G) VALUES (?, ?, ?, ?)', (year, lg, tid, games))
    else:
        con.execute('INSERT INTO teams (yearID, teamID, G) VALUES (?, ?, ?)', (year, tid, games))


def appear(con, year, pid, tid, lg, g_all, app_lg=True):
    if app_lg:
        con.execute('INSERT INTO appearances (yearID, teamID, lgID, playerID, G_all) VALUES (?, ?, ?, ?, ?)',
                    (year, tid, lg, pid, g_all))
    else:
        con.execute('INSERT INTO appearances (yearID, teamID, playerID, G_all) VALUES (?, ?, ?, ?)',
                    (year, tid, pid, g_all))


def bat(con, year, pid, tid, stint):
    con.execute('INSERT INTO batting VALUES (?, ?, ?, ?)', (pid, year, stint, tid))


def pit(con, year, pid, tid, stint):
    con.execute('INSERT INTO pitching VALUES (?, ?, ?, ?)', (pid, year, stint, tid))


# stints

def season():
    con = make_db()
    for tid, lg in (('AAA', 'AL'), ('BBB', 'AL'), ('CCC', 'NL'), ('MIN', 'XX')):
        team(con, 1977, tid, lg)
        appear(con, 1977, 'p', tid, lg, 10)
        appear(con, 1977, 'q', tid, lg, 10)
        appear(con, 1977, 'r', tid, lg, 10)
        appear(con, 1977, 's', tid, lg, 10)
    return con


def test_stints_are_in_stint_number_order():
    con = season()
    bat(con, 1977, 'p', 'BBB', 1)
    bat(con, 1977, 'p', 'AAA', 2)
    bat(con, 1977, 'p', 'CCC', 3)
    assert M.stints(con, 1977, ('AL', 'NL')) == {'p': ['BBB', 'AAA', 'CCC']}


def test_a_team_takes_its_lowest_stint_number_from_batting_or_pitching():
    con = season()
    bat(con, 1977, 'p', 'AAA', 2)
    pit(con, 1977, 'p', 'AAA', 1)                       # pitching has AAA first: AAA is stint 1
    pit(con, 1977, 'p', 'BBB', 2)
    pit(con, 1977, 'q', 'CCC', 1)                       # a pitcher seen only in pitching
    bat(con, 1977, 'q', 'AAA', 2)
    assert M.stints(con, 1977, ('AL', 'NL')) == {'p': ['AAA', 'BBB'], 'q': ['CCC', 'AAA']}


def test_a_player_back_on_his_first_team_counts_each_team_once():
    con = season()
    for stint, tid in ((1, 'AAA'), (2, 'BBB'), (3, 'AAA')):
        bat(con, 1977, 'p', tid, stint)
    assert M.stints(con, 1977, ('AL',)) == {'p': ['AAA', 'BBB']}


def test_single_team_players_are_left_out():
    con = season()
    bat(con, 1977, 'p', 'AAA', 1)
    bat(con, 1977, 'p', 'AAA', 2)                       # two stints, one team
    bat(con, 1977, 'q', 'BBB', 1)
    assert M.stints(con, 1977, ('AL', 'NL')) == {}


def test_a_team_outside_the_leagues_does_not_count():
    con = season()
    bat(con, 1977, 'p', 'AAA', 1)
    bat(con, 1977, 'p', 'CCC', 2)                       # NL, not asked for: p has one team left
    bat(con, 1977, 'q', 'MIN', 1)
    bat(con, 1977, 'q', 'BBB', 2)
    bat(con, 1977, 'q', 'AAA', 3)
    bat(con, 1977, 'r', 'AAA', 1)
    bat(con, 1977, 'r', 'BBB', 2)
    assert M.stints(con, 1977, ('AL',)) == {'q': ['BBB', 'AAA'], 'r': ['AAA', 'BBB']}


def test_other_years_are_ignored_and_players_come_in_id_order():
    con = season()
    for pid in ('s', 'p'):
        bat(con, 1977, pid, 'AAA', 1)
        bat(con, 1977, pid, 'BBB', 2)
    bat(con, 1976, 'q', 'AAA', 1)
    bat(con, 1976, 'q', 'BBB', 2)
    assert list(M.stints(con, 1977, ('AL',))) == ['p', 's']


@pytest.mark.parametrize('team_lg, app_lg', [(True, False), (False, True), (True, True)])
def test_the_leagues_come_from_whichever_table_has_the_lgid(team_lg, app_lg):
    con = make_db(team_lg, app_lg)
    for tid, lg in (('AAA', 'AL'), ('BBB', 'AL'), ('CCC', 'NL')):
        team(con, 1977, tid, lg, team_lg=team_lg)
        appear(con, 1977, 'p', tid, lg, 10, app_lg=app_lg)
        bat(con, 1977, 'p', tid, 'ABC'.index(tid[0]) + 1)
    assert M.stints(con, 1977, ('AL',)) == {'p': ['AAA', 'BBB']}


# moves_for

def test_at_is_the_games_through_the_from_team_over_its_schedule():
    app = {'p': {'A': {'G_all': 40}, 'B': {'G_all': 30}, 'C': {'G_all': 20}}}
    got = M.moves_for({'p': ['A', 'B', 'C']}, app, {'A': 100, 'B': 140, 'C': 150})
    assert got == [{'player': 'p', 'from': 'A', 'to': 'B', 'at': 0.4},
                   {'player': 'p', 'from': 'B', 'to': 'C', 'at': 0.5}]      # (40 + 30) / 140


def test_at_is_rounded_to_three_places():
    app = {'p': {'A': {'G_all': 1}, 'B': {'G_all': 1}}}
    assert M.moves_for({'p': ['A', 'B']}, app, {'A': 3})[0]['at'] == 0.333


def test_at_is_held_between_five_and_ninety_five_percent():
    app = {'lo': {'A': {'G_all': 1}}, 'five': {'A': {'G_all': 5}}, 'six': {'A': {'G_all': 6}},
           'p95': {'A': {'G_all': 95}}, 'p96': {'A': {'G_all': 96}}, 'over': {'A': {'G_all': 150}}}
    stint_map = {pid: ['A', 'B'] for pid in app}
    got = {m['player']: m['at'] for m in M.moves_for(stint_map, app, {'A': 100})}
    assert got == {'lo': 0.05, 'five': 0.05, 'six': 0.06, 'p95': 0.95, 'p96': 0.95, 'over': 0.95}


def test_a_missing_appearance_counts_as_no_games_and_a_team_without_games_is_skipped():
    stint_map = {'p': ['A', 'B', 'C'], 'q': ['A', 'B']}
    app = {'p': {'B': {'G_all': 50}}}                  # nothing for p at A, nothing at all for q
    got = M.moves_for(stint_map, app, {'A': 100, 'B': 0})
    assert got == [{'player': 'p', 'from': 'A', 'to': 'B', 'at': 0.05},
                   {'player': 'q', 'from': 'A', 'to': 'B', 'at': 0.05}]


def test_moves_are_sorted_by_at_then_player_then_from():
    app = {'b': {'X': {'G_all': 50}, 'Y': {'G_all': 10}}, 'a': {'X': {'G_all': 50}}, 'c': {'Z': {'G_all': 20}}}
    stint_map = {'b': ['X', 'Y'], 'a': ['X', 'Y'], 'c': ['Z', 'Y']}
    got = M.moves_for(stint_map, app, {'X': 100, 'Z': 100})
    assert [(m['at'], m['player'], m['from']) for m in got] == [(0.2, 'c', 'Z'), (0.5, 'a', 'X'), (0.5, 'b', 'X')]


def test_first_team_is_the_stint_one_team():
    assert M.first_team({'p': ['B', 'A'], 'q': ['C', 'D', 'E']}) == {'p': 'B', 'q': 'C'}


# build.py: the MOV document

KEY = {'AAA': 1, 'BBB': 2, 'CCC': 3}               # association teams; 'ZZZ' is not in it
ID = {'p': 101, 'q': 102, 'r': 103}
NAMES = {'p': 'Pat Doe', 'q': 'Quin Roe'}


def mov(moves, stint_map, listed=None):
    listed = {1: {101, 102, 103}, 2: set(), 3: set()} if listed is None else listed
    return B.mov_doc(1977, moves, stint_map, KEY, ID, listed, NAMES)


def mv(pid, frm, to, at):
    return {'player': pid, 'from': frm, 'to': to, 'at': at}


def test_the_document_names_the_game_ids_and_team_keys():
    doc, written, dropped = mov([mv('p', 'AAA', 'BBB', 0.4)], {'p': ['AAA', 'BBB']})
    assert doc == {'kind': 'moves', 'year': 1977, 'moves': [{'pid': 101, 'name': 'Pat Doe', 'from': 1, 'to': 2,
                                                              'at': 0.4}]}
    assert (written, dropped) == (1, 0)


def test_a_player_without_a_name_is_named_by_his_lahman_id():
    doc, _, _ = mov([mv('r', 'AAA', 'BBB', 0.4)], {'r': ['AAA', 'BBB']})
    assert doc['moves'][0]['name'] == 'r'


def test_moves_off_the_association_are_dropped():
    moves = [mv('p', 'AAA', 'ZZZ', 0.4), mv('q', 'ZZZ', 'BBB', 0.4), mv('r', 'AAA', 'CCC', 0.6)]
    stints = {'p': ['AAA', 'ZZZ'], 'q': ['ZZZ', 'BBB'], 'r': ['AAA', 'CCC']}
    doc, written, dropped = mov(moves, stints)
    assert [m['pid'] for m in doc['moves']] == [103] and (written, dropped) == (1, 2)


def test_a_player_not_on_the_from_teams_active_or_reserve_list_is_dropped():
    listed = {1: {102}, 2: set(), 3: set()}
    doc, written, dropped = mov([mv('p', 'AAA', 'BBB', 0.4), mv('q', 'AAA', 'BBB', 0.5)],
                                {'p': ['AAA', 'BBB'], 'q': ['AAA', 'BBB']}, listed)
    assert [m['pid'] for m in doc['moves']] == [102] and (written, dropped) == (1, 1)


def test_a_later_move_follows_the_earlier_one():
    stints = {'p': ['AAA', 'BBB', 'CCC']}
    moves = [mv('p', 'AAA', 'BBB', 0.3), mv('p', 'BBB', 'CCC', 0.7)]
    doc, written, dropped = mov(moves, stints)                 # p is listed at AAA only: the second move is kept
    assert [(m['from'], m['to']) for m in doc['moves']] == [(1, 2), (2, 3)] and (written, dropped) == (2, 0)
    doc, written, dropped = mov(moves, stints, {1: set(), 2: {101}, 3: set()})     # first dropped: second dropped
    assert doc['moves'] == [] and (written, dropped) == (0, 2)
    doc, written, dropped = mov([moves[0], mv('p', 'BBB', 'ZZZ', 0.7)], {'p': ['AAA', 'BBB', 'ZZZ']})
    assert [(m['from'], m['to']) for m in doc['moves']] == [(1, 2)] and (written, dropped) == (1, 1)


def test_a_dropped_first_move_drops_the_chain_even_when_the_later_teams_are_in():
    stints = {'p': ['ZZZ', 'AAA', 'BBB']}
    doc, written, dropped = mov([mv('p', 'ZZZ', 'AAA', 0.2), mv('p', 'AAA', 'BBB', 0.6)], stints)
    assert doc['moves'] == [] and (written, dropped) == (0, 2)


def test_moves_are_in_play_order_and_a_chain_never_runs_backwards():
    stints = {'p': ['AAA', 'BBB', 'CCC'], 'q': ['AAA', 'BBB']}
    moves = [mv('p', 'AAA', 'BBB', 0.6), mv('p', 'BBB', 'CCC', 0.4),       # the second would come first
             mv('q', 'AAA', 'BBB', 0.5)]
    doc, _, _ = mov(moves, stints)
    assert [(m['pid'], m['from'], m['at']) for m in doc['moves']] == [(102, 1, 0.5), (101, 1, 0.6), (101, 2, 0.6)]


def test_equal_times_keep_a_players_stint_order():
    stints = {'p': ['CCC', 'BBB', 'AAA']}
    moves = [mv('p', 'BBB', 'AAA', 0.95), mv('p', 'CCC', 'BBB', 0.95)]
    doc, _, _ = mov(moves, stints, {1: set(), 2: set(), 3: {101}})
    assert [(m['from'], m['to']) for m in doc['moves']] == [(3, 2), (2, 1)]


def test_the_document_is_json_and_does_not_change_the_input():
    moves = [mv('p', 'AAA', 'BBB', 0.4)]
    doc, _, _ = mov(moves, {'p': ['AAA', 'BBB']})
    assert json.loads(json.dumps(doc)) == doc and moves == [mv('p', 'AAA', 'BBB', 0.4)]


# build.py: the writer and the argument

def test_write_moves_writes_json_beside_the_association(tmp_path):
    (tmp_path / 'Assn').mkdir()
    doc = {'kind': 'moves', 'year': 1977, 'moves': []}
    path = B.write_moves(str(tmp_path), '16L1977', doc)
    assert path == str(tmp_path / 'Assn' / '16L1977.MOV')
    assert json.loads((tmp_path / 'Assn' / '16L1977.MOV').read_text()) == doc
    assert os.listdir(tmp_path / 'Assn') == ['16L1977.MOV']
    B.write_moves(str(tmp_path), '16L1977', dict(doc, year=1978))
    assert json.loads((tmp_path / 'Assn' / '16L1977.MOV').read_text())['year'] == 1978


def test_write_moves_refuses_a_symlink_and_a_stray_tmp(tmp_path):
    (tmp_path / 'Assn').mkdir()
    target = tmp_path / 'elsewhere'
    target.write_text('keep')
    os.symlink(target, tmp_path / 'Assn' / 'X.MOV')
    with pytest.raises(SystemExit):
        B.write_moves(str(tmp_path), 'X', {})
    assert target.read_text() == 'keep'
    (tmp_path / 'Assn' / 'X.MOV').unlink()
    (tmp_path / 'Assn' / 'X.MOV.tmp').write_text('stray')
    with pytest.raises(FileExistsError):
        B.write_moves(str(tmp_path), 'X', {})
    assert (tmp_path / 'Assn' / 'X.MOV.tmp').read_text() == 'stray'


def argv(tmp_path, *extra):
    db = tmp_path / 'm.sqlite'
    if not db.exists():
        con = sqlite3.connect(db)
        con.execute('CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT)')
        con.execute("INSERT INTO teams VALUES (1977, 'AL', 'BAL')")
        con.commit()
        con.close()
    return ['--year', '1977', '--db', str(db), '--install', str(tmp_path / 'install'), '--leagues', 'AL', *extra]


@pytest.mark.parametrize('extra, want', [((), False), (('--moves',), True)])
def test_the_moves_option_reaches_build_and_defaults_off(tmp_path, monkeypatch, extra, want):
    calls = []
    monkeypatch.setattr(B, 'build', lambda *args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(teamnames, 'OUT', str(tmp_path / 'absent.json'))
    assert B.main(argv(tmp_path, *extra)) == 0
    (args, kw), = calls
    assert kw['moves'] is want and args[:2] == (1977, str(tmp_path / 'install'))


def test_build_takes_moves_off_by_default():
    assert inspect.signature(B.build).parameters['moves'].default is False
