"""replay.py over a tiny Lahman-shaped SQLite database and hand-made season dicts: no game files, no real database."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import replay  # noqa: E402

SCHEMA = (
    'CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT, divID TEXT, name TEXT, G INT, W INT, L INT, teamRank INT)',
    'CREATE TABLE batting (playerID TEXT, yearID INT, teamID TEXT, lgID TEXT, AB INT, H INT, HR INT, RBI INT, SB INT, '
    'BB INT)',
    'CREATE TABLE pitching (playerID TEXT, yearID INT, teamID TEXT, lgID TEXT, W INT, L INT, SV INT, IPouts INT, '
    'ER INT, SO INT)',
    'CREATE TABLE people (playerID TEXT, nameFirst TEXT, nameLast TEXT)',
)


def lahman(tmp_path, teams=(), bat=(), pit=(), people=()):
    """A Lahman-shaped database with only the tables and columns replay reads, opened read-only as the watcher does."""
    path = tmp_path / 'lahman.sqlite'
    con = sqlite3.connect(path)
    for stmt in SCHEMA:
        con.execute(stmt)
    con.executemany('INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?)', teams)
    con.executemany('INSERT INTO batting VALUES (?,?,?,?,?,?,?,?,?,?)', bat)
    con.executemany('INSERT INTO pitching VALUES (?,?,?,?,?,?,?,?,?,?)', pit)
    con.executemany('INSERT INTO people VALUES (?,?,?)', people)
    con.commit()
    con.close()
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def team_row(tid, lg, w, l, g=None, name=None, year=1998):
    return (year, lg, tid, 'E', name or tid, g or w + l, w, l, 1)


def bat_row(pid, lg, ab, h=0, hr=0, rbi=0, sb=0, bb=0, tid='NYA', year=1998):
    return (pid, year, tid, lg, ab, h, hr, rbi, sb, bb)


def pit_row(pid, lg, w=0, l=0, sv=0, outs=0, er=0, so=0, tid='NYA', year=1998):
    return (pid, year, tid, lg, w, l, sv, outs, er, so)


def game(away, home, ar, hr, played=True):
    return {'month': 4, 'day': 1, 'slot': 0, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': 9}


def record(tid, wins, losses, opp=9):
    """Wins and losses for tid, every game at home against opp (a team the scorecard does not know)."""
    return [game(opp, tid, 1, 2) for _ in range(wins)] + [game(opp, tid, 2, 1) for _ in range(losses)]


def team(tid, name, abbrev, lg='AL'):
    return {'tid': tid, 'name': name, 'abbrev': abbrev, 'league': lg, 'division': 'East', 'w': 0, 'l': 0, 'roster': []}


def assoc_of(teams, games):
    return {'name': '1998 Major Leagues', 'teams': {t['tid']: t for t in teams}, 'games': games}


def real_team(name, lg, w, l, g=None):
    return {'name': name, 'lg': lg, 'div': 'E', 'g': g or w + l, 'w': w, 'l': l}


def bline(ab, h, hr=0, rbi=0, sb=0):
    return {'ab': ab, 'h': h, 'hr': hr, 'rbi': rbi, 'sb': sb}


def pline(outs, er=0, w=0, sv=0, so=0):
    return {'outs': outs, 'er': er, 'w': w, 'sv': sv, 'so': so}


def test_season_of_reads_both_league_sets_and_nothing_else():
    assert replay.season_of('1998 Major Leagues') == (1998, replay.MLB_LEAGUES)
    assert replay.season_of('1942 Negro Leagues') == (1942, replay.NEGRO_LEAGUES)
    for name in ('MLBPA97', '1997 Player Association', 'Major Leagues', '98 Major Leagues', '1998 Major Leagues ',
                 '1998 Major Leagues\n', '1998 minor leagues', '1998 Major Leagues Extra', '', None):
        assert replay.season_of(name) is None


def test_real_sums_stints_in_the_league_set_and_keys_teams_by_three_letters(tmp_path):
    con = lahman(
        tmp_path,
        teams=[team_row('NYA', 'AL', 114, 48, g=162, name='New York Yankees'), team_row('CLE1', 'AL', 89, 73, g=162),
               team_row('XXX', 'PCL', 1, 1), team_row('NYA', 'AL', 1, 1, year=1997)],
        bat=[bat_row('ruthba01', 'NL', 100, 30, 5, 20, 0, 10), bat_row('ruthba01', 'AA', 50, 20, 3, 8, 0, 5),
             bat_row('ruthba01', 'PCL', 999, 999), bat_row('ruthba01', 'NL', 999, 999, year=1997)],
        people=[('ruthba01', 'Babe', 'Ruth')],
        pit=[pit_row('ruthba01', 'AA', w=1, outs=30, er=2, so=4)])
    real = replay.real(con, 1998, replay.MLB_LEAGUES)
    assert sorted(real['teams']) == ['CLE', 'NYA']
    assert real['teams']['NYA'] == {'name': 'New York Yankees', 'lg': 'AL', 'div': 'E', 'g': 162, 'w': 114, 'l': 48}
    assert real['bat'] == {'Babe Ruth': {'ab': 150, 'h': 50, 'hr': 8, 'rbi': 28, 'sb': 0, 'bb': 15, 'lg': 'NL'}}
    assert real['pit'] == {'Babe Ruth': {'w': 1, 'l': 0, 'sv': 0, 'outs': 30, 'er': 2, 'so': 4, 'lg': 'AA'}}


def test_real_cuts_names_to_the_pyr_width_and_keeps_the_busier_of_two_with_one_name(tmp_path):
    con = lahman(
        tmp_path,
        bat=[bat_row('smitjo01', 'NL', 300, hr=10), bat_row('smitjo02', 'NL', 500, hr=2),
             bat_row('ellisp01', 'NL', 10)],
        pit=[pit_row('deeted01', 'NL', outs=90), pit_row('deeted02', 'NL', outs=300)],
        people=[('smitjo01', 'John', 'Smith'), ('smitjo02', 'John', 'Smith'),
                ('ellisp01', 'Bartholomew-Jonathan', 'Ellis-Pennington-Jr'), ('deeted01', 'Ted', 'Dale'),
                ('deeted02', 'Ted', 'Dale')])
    real = replay.real(con, 1998, replay.MLB_LEAGUES)
    assert real['bat']['John Smith'] == {'ab': 500, 'h': 0, 'hr': 2, 'rbi': 0, 'sb': 0, 'bb': 0, 'lg': 'NL'}
    assert real['bat']['Bartholomew-Jona Ellis-Pennington']['ab'] == 10
    assert real['pit']['Ted Dale']['outs'] == 300


def test_real_is_read_only(tmp_path):
    con = lahman(tmp_path, bat=[bat_row('a', 'NL', 1)], people=[('a', 'A', 'B')])
    with pytest.raises(sqlite3.OperationalError):
        con.execute('DELETE FROM batting')


def test_scorecard_matches_teams_by_abbrev_and_names_the_fillers():
    assoc = assoc_of([team(1, 'Alpha', 'NYA'), team(2, 'Beta', 'BOS'), team(3, 'Filler Team 1', 'FT1')],
                     record(1, 7, 3) + record(2, 5, 5) + record(3, 4, 6))
    real = {'teams': {'NYA': real_team('New York Yankees', 'AL', 6, 4, 10),
                      'BOS': real_team('Boston Red Sox', 'AL', 5, 5, 10)}, 'bat': {}, 'pit': {}}
    card = replay.scorecard(assoc, {'bat': {}, 'pit': {}}, {}, real)
    assert [t['name'] for t in card['teams']] == ['Alpha', 'Beta']
    alpha = card['teams'][0]
    assert alpha['lg'] == 'AL' and alpha['real'] == {'w': 6, 'l': 4, 'pct': 0.6}
    assert alpha['sim'] == {'w': 7, 'l': 3, 'pct': 0.7}
    assert alpha['diff'] == pytest.approx(0.1) and alpha['wins_diff'] == 1.0
    assert card['teams'][1]['wins_diff'] == 0.0
    assert card['unmatched'] == ['Filler Team 1']


def test_rank_correlation_with_ties_and_gap_for_a_league_of_four():
    assoc = assoc_of([team(1, 'Alpha', 'AAA'), team(2, 'Beta', 'BBB'), team(3, 'Gamma', 'CCC'),
                      team(4, 'Delta', 'DDD')],
                     record(1, 7, 3) + record(2, 6, 4) + record(3, 5, 5) + record(4, 4, 6))
    real = {'teams': {'AAA': real_team('Alpha', 'AL', 6, 4, 10), 'BBB': real_team('Beta', 'AL', 5, 5, 10),
                      'CCC': real_team('Gamma', 'AL', 5, 5, 10), 'DDD': real_team('Delta', 'AL', 4, 6, 10),
                      'CHC': real_team('Cubs', 'NL', 90, 72, 162)},
            'bat': {}, 'pit': {}}
    card = replay.scorecard(assoc, {'bat': {}, 'pit': {}}, {}, real)
    al = card['leagues']['AL']
    # Real ranks 4, 2.5, 2.5, 1 against sim ranks 4, 3, 2, 1: Pearson on the ranks is 4.5 / sqrt(4.5 * 5).
    assert al['rank_corr'] == 0.949
    assert al['mean_abs_diff'] == 0.05
    assert al['real_best'] == 'Alpha' and al['sim_best'] == 'Alpha'
    assert card['leagues']['NL'] == {'rank_corr': None, 'mean_abs_diff': None, 'real_best': None, 'sim_best': None}


def test_rank_correlation_needs_three_teams_and_ties_on_the_best_go_by_name():
    assoc = assoc_of([team(1, 'Zeta', 'ZZZ'), team(2, 'Alpha', 'AAA')], record(1, 6, 4) + record(2, 6, 4))
    real = {'teams': {'ZZZ': real_team('Zeta', 'AL', 6, 4, 10), 'AAA': real_team('Alpha', 'AL', 6, 4, 10)},
            'bat': {}, 'pit': {}}
    card = replay.scorecard(assoc, {'bat': {}, 'pit': {}}, {}, real)
    assert card['leagues']['AL']['rank_corr'] is None
    assert card['leagues']['AL']['real_best'] == 'Alpha' and card['leagues']['AL']['sim_best'] == 'Alpha'


def test_a_team_with_no_decided_game_has_no_pct_and_stays_out_of_the_league_figures():
    assoc = assoc_of([team(1, 'Alpha', 'AAA'), team(2, 'Beta', 'BBB')], record(1, 7, 3))
    real = {'teams': {'AAA': real_team('Alpha', 'AL', 6, 4, 10), 'BBB': real_team('Beta', 'AL', 5, 5, 10)},
            'bat': {}, 'pit': {}}
    card = replay.scorecard(assoc, {'bat': {}, 'pit': {}}, {}, real)
    beta = card['teams'][1]
    assert beta['name'] == 'Beta' and beta['sim'] == {'w': 0, 'l': 0, 'pct': None}
    assert beta['diff'] is None and beta['wins_diff'] is None
    assert card['leagues']['AL']['mean_abs_diff'] == pytest.approx(0.1)
    assert card['leagues']['AL']['sim_best'] == 'Alpha'


def test_qualifiers_leaders_and_players_on_both_sides():
    games = record(1, 5, 5, opp=2) + [game(2, 1, 0, 0, played=False)]
    assoc = assoc_of([team(1, 'Alpha', 'AAA'), team(2, 'Beta', 'BBB')], games)
    names = {101: 'Ann Lo', 102: 'Bo Ok', 103: 'Cy Hi', 104: 'Zed Zero', 201: 'Dee Short', 202: 'Eve Long',
             203: 'Fay Mid'}
    sim = {'bat': {101: bline(26, 13), 102: bline(27, 9), 103: bline(100, 40, hr=5), 104: bline(100, 10, hr=0)},
           'pit': {201: pline(29), 202: pline(30, er=10), 203: pline(90, er=27)}}
    real = {'teams': {'LAD': real_team('Los Angeles', 'NL', 90, 72, 162)},
            'bat': {'Ann Lo': {'ab': 437, 'h': 200, 'hr': 0, 'rbi': 0, 'sb': 0, 'bb': 0, 'lg': 'NL'},
                    'Bo Ok': {'ab': 438, 'h': 130, 'hr': 0, 'rbi': 0, 'sb': 0, 'bb': 0, 'lg': 'NL'}},
            'pit': {'Dee Short': {'w': 0, 'l': 0, 'sv': 0, 'outs': 485, 'er': 0, 'so': 0, 'lg': 'NL'},
                    'Eve Long': {'w': 0, 'l': 0, 'sv': 0, 'outs': 486, 'er': 100, 'so': 0, 'lg': 'NL'},
                    'Ghost Pitch': {'w': 0, 'l': 0, 'sv': 0, 'outs': 486, 'er': 50, 'so': 0, 'lg': 'NL'}}}
    card = replay.scorecard(assoc, sim, names, real)
    assert card['played'] == 10.0 and card['scheduled'] == 11.0
    assert card['leaders']['AVG']['sim'] == [['Cy Hi', 0.4], ['Bo Ok', 0.333], ['Zed Zero', 0.1]]
    assert card['leaders']['AVG']['real'] == [['Bo Ok', 0.297]]
    assert card['leaders']['HR']['sim'] == [['Cy Hi', 5]] and card['leaders']['HR']['real'] == []
    assert card['leaders']['ERA']['sim'] == [['Fay Mid', 8.1], ['Eve Long', 9.0]]
    assert card['leaders']['ERA']['real'] == [['Ghost Pitch', 2.78], ['Eve Long', 5.56]]
    assert card['players'] == [{'stat': 'AVG', 'name': 'Bo Ok', 'real': 0.297, 'sim': 0.333},
                               {'stat': 'ERA', 'name': 'Eve Long', 'real': 5.56, 'sim': 9.0}]


def test_real_lines_without_a_league_use_the_max_team_games_of_all_real_teams():
    """real_data built by hand has no 'lg' on its lines: an unknown or missing league falls back to the max G over
    all real teams (162 here, not the AL's 100)."""
    assoc = assoc_of([team(1, 'Alpha', 'AAA'), team(2, 'Beta', 'BBB')], record(1, 5, 5, opp=2))
    real = {'teams': {'LAD': real_team('Los Angeles', 'NL', 90, 72, 162),
                      'NYA': real_team('New York', 'AL', 60, 40, 100)},
            'bat': {'Ann Lo': {'ab': 437, 'h': 200, 'hr': 0, 'rbi': 0, 'sb': 0, 'bb': 0, 'lg': 'XXX'},
                    'Bo Ok': {'ab': 438, 'h': 130, 'hr': 0, 'rbi': 0, 'sb': 0, 'bb': 0}},
            'pit': {'Dee Short': {'w': 0, 'l': 0, 'sv': 0, 'outs': 485, 'er': 0, 'so': 0},
                    'Eve Long': {'w': 0, 'l': 0, 'sv': 0, 'outs': 486, 'er': 100, 'so': 0}}}
    card = replay.scorecard(assoc, {'bat': {}, 'pit': {}}, {}, real)
    assert card['leaders']['AVG']['real'] == [['Bo Ok', 0.297]]
    assert card['leaders']['ERA']['real'] == [['Eve Long', 5.56]]
    assert card['leaders']['HR']['real'] == []


def test_leaders_are_the_top_five_with_counting_zeros_left_out():
    assoc = assoc_of([team(1, 'Alpha', 'AAA'), team(2, 'Beta', 'BBB')], record(1, 5, 5, opp=2))
    names = {100 + i: 'Hitter %d' % i for i in range(1, 8)}
    sim = {'bat': {100 + i: bline(100, 30, hr=i) for i in range(1, 8)}, 'pit': {}}
    card = replay.scorecard(assoc, sim, names, {'teams': {}, 'bat': {}, 'pit': {}})
    assert card['leaders']['HR']['sim'] == [['Hitter 7', 7], ['Hitter 6', 6], ['Hitter 5', 5], ['Hitter 4', 4],
                                            ['Hitter 3', 3]]
    assert card['leaders']['SB']['sim'] == []
    assert card['unmatched'] == ['Alpha', 'Beta']
