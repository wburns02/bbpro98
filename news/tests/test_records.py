"""records.py on synthetic archives and a tiny Lahman database: the qualifiers, the season and career tables, the real
bar, the chase lines, and the archive readers. No game file or real Lahman database is read.
"""
import datetime
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import history  # noqa: E402
import recap    # noqa: E402
import records  # noqa: E402


def bat(ab=0, h=0, hr=0, rbi=0, r=0, sb=0, bb=0):
    return {'ab': ab, 'h': h, 'hr': hr, 'rbi': rbi, 'r': r, 'sb': sb, 'bb': bb}


def pit(outs=0, er=0, w=0, so=0, sv=0):
    return {'outs': outs, 'er': er, 'w': w, 'so': so, 'sv': sv}


def year(bats=None, pits=None, teams=None):
    return {'bat': bats or {}, 'pit': pits or {}, 'team': teams or {}}


NAMES = {100: 'Al Winner', 101: 'Bo Loser', 102: 'Cy Young', 103: 'Di Mond', 200: 'Ed Hurler', 201: 'Fy Closer'}


# qualifiers, schedule and games played

@pytest.mark.parametrize('games, expect', [
    (162, (400, 486)), (154, (380, 462)), (81, (200, 243)), (200, (494, 600)), (None, (400, 486)), (0, (400, 486)),
    (True, (400, 486)), ('162', (400, 486)),
])
def test_qualifiers_scale_with_the_schedule_and_default_to_162(games, expect):
    assert records.qualifiers(games) == expect


def test_schedule_length_and_team_games_come_from_the_schedule():
    games = [{'away': 1, 'home': 2, 'played': True}, {'away': 2, 'home': 3, 'played': True},
             {'away': 3, 'home': 1, 'played': False}, {'away': 1, 'home': 2, 'played': False}]
    assoc = {'teams': {1: {}, 2: {}, 3: {}}, 'games': games}
    assert records.schedule_length(assoc) == 3          # 4 games * 2 / 3 teams, rounded
    assert records.team_games(assoc) == {1: 1, 2: 2, 3: 1}
    assert records.schedule_length({'teams': {}, 'games': games}) == 0
    assert records.team_games({}) == {}


# season tables

def test_season_average_needs_the_qualifier_and_scales_with_the_schedule():
    arch = {2030: year(bats={100: bat(ab=400, h=140), 101: bat(ab=399, h=200), 102: bat(ab=100, h=60)})}
    tables = records.season_tables(arch, NAMES)
    assert [(r['name'], r['value']) for r in tables['avg']] == [('Al Winner', 140 / 400)]
    short = records.season_tables(arch, NAMES, season_games=154)         # 380 at bats are enough
    assert [r['name'] for r in short['avg']] == ['Bo Loser', 'Al Winner']
    half = records.season_tables({2030: year(bats={103: bat(ab=200, h=70)})}, NAMES, season_games=81)
    assert [r['name'] for r in half['avg']] == ['Di Mond']


def test_season_era_needs_the_qualifier_lowest_first_and_scales():
    arch = {2030: year(pits={200: pit(outs=600, er=60), 201: pit(outs=486, er=40), 102: pit(outs=485, er=1)})}
    got = records.season_tables(arch, NAMES)['era']
    assert [r['name'] for r in got] == ['Fy Closer', 'Ed Hurler'] and got[0]['value'] == 27 * 40 / 486
    short = records.season_tables(arch, NAMES, season_games=100)        # 300 outs
    assert [r['name'] for r in short['era']] == ['Cy Young', 'Fy Closer', 'Ed Hurler']


def test_season_tables_hold_ten_rows_best_first_with_the_season_team_and_year():
    bats = {100 + i: bat(hr=i + 1) for i in range(12)}
    names = {pid: 'P%03d' % pid for pid in bats}
    arch = {2031: year(bats=bats, teams={111: 'Ash'})}
    rows = records.season_tables(arch, names)['hr']
    assert len(rows) == 10
    assert [r['value'] for r in rows] == list(range(12, 2, -1))
    assert rows[0] == {'pid': 111, 'name': 'P111', 'year': 2031, 'value': 12, 'team': 'Ash'}
    assert rows[1]['team'] == ''


def test_season_ties_break_by_year_then_name_and_era_sorts_ascending():
    arch = {2032: year(bats={100: bat(hr=40), 101: bat(hr=40)}), 2031: year(bats={102: bat(hr=40), 103: bat(hr=39)})}
    rows = records.season_tables(arch, NAMES)['hr']
    assert [(r['year'], r['name']) for r in rows] == [(2031, 'Cy Young'), (2032, 'Al Winner'), (2032, 'Bo Loser'),
                                                      (2031, 'Di Mond')]
    eras = {2033: year(pits={200: pit(outs=600, er=60), 201: pit(outs=600, er=60)}),
            2030: year(pits={102: pit(outs=600, er=60), 103: pit(outs=600, er=50)})}
    rows = records.season_tables(eras, NAMES)['era']
    assert [(r['year'], r['name']) for r in rows] == [(2030, 'Di Mond'), (2030, 'Cy Young'), (2033, 'Ed Hurler'),
                                                      (2033, 'Fy Closer')]


def test_season_tables_skip_team_lines_zero_counts_and_unknown_kinds_and_name_the_unnamed():
    arch = {2030: year(bats={5: bat(hr=999), 100: bat(hr=0, h=3), 150: bat(hr=2)}, pits={200: pit(sv=0, w=1)})}
    tables = records.season_tables(arch, NAMES)
    assert [(r['pid'], r['name']) for r in tables['hr']] == [(150, 'Player 150')]
    assert [r['pid'] for r in tables['h']] == [100] and tables['sv'] == []
    assert set(tables) == set(records.STATS) and len(records.STATS) == 11


# career tables

def test_career_sums_real_and_simulated_seasons_and_counts_them():
    real = {'bat': {100: [dict(year=1995, team='X', stints=1, **{k: 1 for k in history.BAT_KEYS}),
                          dict(year=1996, team='X', stints=1, **{k: 2 for k in history.BAT_KEYS})]}}
    arch = {1997: year(bats={100: dict(bat(hr=10, h=20), g=1)}), 1998: year(bats={100: bat(hr=5, h=3), 101: bat(hr=1)})}
    tables = records.career_tables(arch, NAMES, real, start=1997)
    assert tables['hr'][0] == {'pid': 100, 'name': 'Al Winner', 'value': 1 + 2 + 10 + 5, 'seasons': 4}
    assert tables['hr'][1] == {'pid': 101, 'name': 'Bo Loser', 'value': 1, 'seasons': 1}
    # a real season at or after the start year is not counted (1999); one in a simulated year is replaced by it (1997)
    real['bat'][100] += [dict(year=1997, team='X', stints=1, **{k: 100 for k in history.BAT_KEYS}),
                         dict(year=1999, team='X', stints=1, **{k: 100 for k in history.BAT_KEYS})]
    assert records.career_tables(arch, NAMES, real, start=1997)['hr'][0]['value'] == 18
    assert records.career_tables(arch, NAMES, real, start=None)['hr'][0]['value'] == 118


def test_career_only_counts_players_in_the_pyr_and_without_real_seasons_is_simulated_only():
    arch = {1997: year(bats={100: bat(hr=7), 999: bat(hr=70)})}
    rows = records.career_tables(arch, NAMES)['hr']
    assert [(r['pid'], r['value']) for r in rows] == [(100, 7)]


def test_career_average_and_era_need_their_qualifiers_and_ties_break_by_name():
    arch = {1997: year(bats={100: bat(ab=3000, h=900), 101: bat(ab=2999, h=1500)},
                       pits={200: pit(outs=4500, er=500), 201: pit(outs=4499, er=1)}),
            1998: year(bats={102: bat(ab=3000, h=900)}, pits={102: pit(outs=4500, er=500)})}
    tables = records.career_tables(arch, NAMES)
    assert [r['name'] for r in tables['avg']] == ['Al Winner', 'Cy Young']
    assert [r['name'] for r in tables['era']] == ['Cy Young', 'Ed Hurler']
    assert tables['era'][0]['value'] == 27 * 500 / 4500


# the Lahman parts, on a tiny in-memory database

def bar_db():
    """Batting, Pitching and People with only the columns lahman_bar reads."""
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE Batting (playerID TEXT, yearID INT, AB INT, H INT, HR INT, RBI INT, R INT, SB INT, '
                'BB INT)')
    con.execute('CREATE TABLE Pitching (playerID TEXT, yearID INT, W INT, SO INT, SV INT, IPouts INT, ER INT)')
    con.execute('CREATE TABLE People (playerID TEXT, nameFirst TEXT, nameLast TEXT)')
    con.executemany('INSERT INTO People VALUES (?,?,?)', [
        ('ruthba01', 'Babe', 'Ruth'), ('ableja01', 'Adam', 'Able'), ('duffyhu01', 'Hugh', 'Duffy'),
        ('trade01', 'Tom', 'Trader'), ('bondsba01', 'Barry', 'Bonds'), ('radbocha01', 'Old', 'Hoss'),
        ('leonadu01', 'Dutch', 'Leonard'), ('shorty01', 'Short', 'Stop'), ('closer01', 'Cal', 'Closer'),
        ('newcl01', 'New', 'Closer'), ('livebl01', 'Lou', 'Liveball'), ('livep01', 'Pat', 'Livearm')])
    con.executemany('INSERT INTO Batting VALUES (?,?,?,?,?,?,?,?,?)', [
        ('ruthba01', 1927, 540, 192, 60, 165, 158, 7, 137),
        ('ableja01', 1927, 500, 150, 60, 100, 90, 2, 50),          # ties Ruth on 60 in the same year: name decides
        ('ableja01', 1931, 500, 150, 60, 100, 90, 2, 50),          # a later tie loses to the earlier year
        ('duffyhu01', 1894, 539, 237, 18, 145, 160, 48, 66),       # .4397
        ('shorty01', 1980, 399, 200, 1, 1, 1, 1, 1),               # .501 but under 400 at bats
        ('trade01', 1990, 300, 90, 20, 60, 40, 10, 30),            # two stints sum to 45 home runs and 550 at bats
        ('trade01', 1990, 250, 80, 25, 50, 40, 5, 30),
        ('bondsba01', 2001, 476, 156, 73, 137, 129, 13, 177),      # in the association's years: not real history
        ('livebl01', 1925, 520, 210, 10, 120, 130, 44, 60),        # the live-ball sb and hits leader, .4038
        (None, 1900, None, None, None, None, None, None, None),
    ])
    con.executemany('INSERT INTO Pitching VALUES (?,?,?,?,?,?,?)', [
        ('radbocha01', 1884, 59, 441, 0, 1800, 300),
        ('leonadu01', 1914, 19, 176, 0, 674, 20),                  # 0.80
        ('shorty01', 1950, 1, 10, 0, 315, 5),                      # an ERA of 0.43 on too few outs
        ('livep01', 1931, 31, 200, 0, 800, 70),                    # 2.36
        ('closer01', 1990, 3, 50, 57, 200, 20),
        ('newcl01', 2001, 3, 50, 62, 200, 20),                     # not before 2001
    ])
    con.commit()
    return con


def test_lahman_bar_is_the_best_live_ball_season_before_the_start_year_with_the_qualifiers():
    got = records.lahman_bar(bar_db(), 2001)
    assert got['hr'] == {'value': 60, 'name': 'Adam Able', 'year': 1927, 'source': 'lahman'}
    assert got['h'] == {'value': 210, 'name': 'Lou Liveball', 'year': 1925, 'source': 'lahman'}
    assert got['rbi']['value'] == 165 and got['r']['value'] == 158 and got['bb']['value'] == 137
    assert got['sb'] == {'value': 44, 'name': 'Lou Liveball', 'year': 1925, 'source': 'lahman'}
    assert got['avg']['name'] == 'Lou Liveball' and got['avg']['value'] == 210 / 520
    assert got['w'] == {'value': 31, 'name': 'Pat Livearm', 'year': 1931, 'source': 'lahman'}
    assert got['so'] == {'value': 200, 'name': 'Pat Livearm', 'year': 1931, 'source': 'lahman'}
    assert got['sv'] == {'value': 57, 'name': 'Cal Closer', 'year': 1990, 'source': 'lahman'}
    assert got['era'] == {'value': 27 * 70 / 800, 'name': 'Pat Livearm', 'year': 1931, 'source': 'lahman'}
    assert set(got) == set(records.STATS)


def test_lahman_bar_skips_the_dead_ball_years_unless_the_association_starts_in_them():
    assert records.BAR_FROM == 1920
    assert 'w' not in records.lahman_bar(bar_db(), 1921)                # no pitcher season from 1920 to 1920
    assert records.lahman_bar(bar_db(), 1920)['w'] == {'value': 59, 'name': 'Old Hoss', 'year': 1884,
                                                       'source': 'lahman'}
    assert records.lahman_bar(bar_db(), 1900)['so']['value'] == 441


def test_lahman_bar_sums_stints_and_includes_later_years_only_when_asked():
    con = bar_db()
    con.execute("DELETE FROM Batting WHERE playerID IN ('ruthba01', 'ableja01')")
    got = records.lahman_bar(con, 2001)
    assert got['hr']['value'] == 45 and got['hr']['name'] == 'Tom Trader'
    assert records.lahman_bar(con, 2002)['hr'] == {'value': 73, 'name': 'Barry Bonds', 'year': 2001, 'source': 'lahman'}
    assert records.lahman_bar(con, None)['sv']['value'] == 62
    assert records.lahman_bar(con, 1900)['hr']['name'] == 'Hugh Duffy' and 'sv' not in records.lahman_bar(con, 1900)


def test_lahman_bar_scales_the_qualifiers_to_the_schedule():
    got = records.lahman_bar(bar_db(), 2001, season_games=154)          # 380 at bats: the .501 season qualifies
    assert got['avg']['name'] == 'Short Stop' and got['avg']['value'] == 200 / 399
    got = records.lahman_bar(bar_db(), 2001, season_games=60)           # 180 outs: the 0.43 season qualifies
    assert got['era']['name'] == 'Short Stop'


def test_lahman_bar_without_a_name_row_uses_the_player_id_and_a_missing_table_raises():
    con = bar_db()
    con.execute('DELETE FROM People')
    assert records.lahman_bar(con, 2001)['w']['name'] == 'livep01'
    with pytest.raises(sqlite3.Error):
        records.lahman_bar(sqlite3.connect(':memory:'), 2001)


def test_bar_takes_the_better_of_lahman_and_the_best_simulated_season():
    lahman = records.lahman_bar(bar_db(), 2001)
    arch = {2030: year(bats={100: bat(hr=61, h=100, ab=500), 101: bat(hr=60)},
                       pits={200: pit(outs=600, er=60, w=10), 201: pit(outs=700, er=40, sv=57)})}
    season = records.season_tables(arch, NAMES)
    got = records.bar(lahman, season)
    assert got['hr'] == {'value': 61, 'name': 'Al Winner', 'year': 2030, 'source': 'sim'}
    assert got['sv']['source'] == 'lahman'                      # equal to the real record is not past it
    assert got['era']['source'] == 'sim' and got['era']['value'] == 27 * 40 / 700       # 1.54 beats the real 2.36
    assert got['w']['source'] == 'lahman' and got['avg']['source'] == 'lahman'
    worse = {2030: year(pits={200: pit(outs=600, er=90)})}
    assert records.bar(lahman, records.season_tables(worse, NAMES))['era'] == {
        'value': 27 * 70 / 800, 'name': 'Pat Livearm', 'year': 1931, 'source': 'lahman'}
    low = {2030: year(pits={200: pit(outs=800, er=10)})}
    assert records.bar(lahman, records.season_tables(low, NAMES))['era'] == {
        'value': 27 * 10 / 800, 'name': 'Ed Hurler', 'year': 2030, 'source': 'sim'}


def test_bar_without_lahman_is_the_simulated_best_and_without_either_is_empty():
    arch = {2030: year(bats={100: bat(hr=30)}, pits={200: pit(outs=600, er=60)})}
    got = records.bar({}, records.season_tables(arch, NAMES))
    assert got == {'hr': {'value': 30, 'name': 'Al Winner', 'year': 2030, 'source': 'sim'},
                   'era': {'value': 2.7, 'name': 'Ed Hurler', 'year': 2030, 'source': 'sim'}}
    assert records.bar({}, records.season_tables({}, NAMES)) == {}


def people_db():
    """The tables history.lahman_id and history.real_seasons read, with one person: Al Winner, born 1970-03-04."""
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE people (playerID TEXT, nameFirst TEXT, nameLast TEXT, birthYear INT, birthMonth INT, '
                'birthDay INT)')
    con.execute('CREATE TABLE teams (yearID INT, teamID TEXT, teamIDBR TEXT)')
    con.execute('CREATE TABLE batting (playerID, yearID, stint, teamID, G, AB, R, H, "2B", "3B", HR, RBI, SB, CS, BB, '
                'SO, IBB, HBP, SH, SF, GIDP)')
    con.execute('CREATE TABLE pitching (playerID, yearID, stint, teamID, W, L, G, GS, CG, SHO, SV, IPouts, H, ER, HR, '
                'BB, SO, HBP, BFP, R)')
    con.execute("INSERT INTO people VALUES ('winnal01', 'Al', 'Winner', 1970, 3, 4)")
    con.execute("INSERT INTO people VALUES ('hurleed01', 'Ed', 'Hurler', 1971, 5, 6)")
    con.execute("INSERT INTO batting (playerID, yearID, stint, teamID, G, AB, H, HR) VALUES "
                "('winnal01', 1995, 1, 'ASH', 100, 400, 100, 12)")
    con.execute("INSERT INTO batting (playerID, yearID, stint, teamID, G, AB, H, HR) VALUES "
                "('winnal01', 1997, 1, 'ASH', 100, 400, 100, 99)")
    con.execute("INSERT INTO pitching (playerID, yearID, stint, teamID, W, G, IPouts, ER) VALUES "
                "('hurleed01', 1996, 1, 'ASH', 14, 30, 600, 60)")
    con.commit()
    return con


def test_real_careers_match_people_by_name_and_birth_date_and_stop_before_the_start_year():
    people = {100: ('Al', 'Winner', datetime.date(1970, 3, 4)), 200: ('Ed', 'Hurler', datetime.date(1971, 5, 6)),
              101: ('Bo', 'Loser', datetime.date(1970, 3, 4)), 102: ('Al', 'Winner', None),
              103: ('Al', 'Winner', datetime.date(1999, 1, 1))}
    got = records.real_careers(people_db(), people, before=1997)
    assert sorted(got) == ['bat', 'pit']
    assert [r['year'] for r in got['bat'][100]] == [1995] and got['bat'][100][0]['hr'] == 12
    assert list(got['bat']) == [100] and list(got['pit']) == [200]
    assert got['pit'][200][0]['w'] == 14
    assert [r['year'] for r in records.real_careers(people_db(), people)['bat'][100]] == [1995, 1997]


# the document

def test_document_has_the_whole_shape_and_the_bar_before_any_simulated_season():
    lahman = records.lahman_bar(bar_db(), 2001)
    doc = records.document('30L2001', '2031-10-01T12:00:00', [], {}, NAMES, lahman=lahman)
    assert set(doc) == {'stem', 'updated', 'through', 'years', 'season', 'career', 'bar'}
    assert doc['through'] == 0 and doc['years'] == [] and doc['bar'] == lahman
    assert set(doc['season']) == set(records.STATS) == set(doc['career'])
    assert all(rows == [] for rows in doc['season'].values()) and all(rows == [] for rows in doc['career'].values())
    json.dumps(doc)


def test_document_through_is_the_last_played_year_and_years_are_every_archive():
    arch = {2030: year(bats={100: bat(hr=3)}), 2032: year(bats={100: bat(hr=4)})}
    doc = records.document('X', 'now', [2025, 2030, 2032], arch, NAMES)
    assert doc['through'] == 2032 and doc['years'] == [2025, 2030, 2032]
    assert doc['season']['hr'][0]['value'] == 4 and doc['career']['hr'] == [
        {'pid': 100, 'name': 'Al Winner', 'value': 7, 'seasons': 2}]
    assert doc['bar']['hr']['source'] == 'sim'
    assert json.loads(json.dumps(doc)) == doc


# the archives

def write_archive(data, stem, yr, doc):
    path = history.archive_path(str(data), stem, yr)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc if isinstance(doc, str) else json.dumps(doc))


def test_archived_years_lists_year_files_only_and_read_archives_skips_the_unreadable(tmp_path):
    for yr in (2031, 2030):
        write_archive(tmp_path, '30L2030', yr, {'bat': {'100': {'hr': 3, 'ab': 'x', 'h': True}, 'x': {'hr': 1},
                                                        '101': 5, '²': {'hr': 1}},
                                                'pit': {'200': {'w': 2}}, 'team': {'100': 'Ash', '101': 7}})
    write_archive(tmp_path, '30L2030', 2029, '{"bat": ')
    write_archive(tmp_path, '30L2030', 2028, '[1]')
    (tmp_path / '30L2030' / 'history' / 'seen.json').write_text('{"years": [2030]}')
    (tmp_path / '30L2030' / 'history' / '2027.json.bad').write_text('{}')
    assert records.archived_years(str(tmp_path), '30L2030') == [2028, 2029, 2030, 2031]
    got = records.read_archives(str(tmp_path), '30l2030')
    assert sorted(got) == [2030, 2031]
    assert got[2030]['bat'] == {100: dict(dict.fromkeys(history.BAT_KEYS, 0), hr=3)}
    assert got[2030]['pit'][200]['w'] == 2 and got[2030]['team'] == {100: 'Ash'}
    assert records.archived_years(str(tmp_path), 'NOPE') == [] and records.archived_years(str(tmp_path), '../x') == []
    assert records.archived_years(str(tmp_path), 5) == []


def test_playable_drops_the_seeded_years_before_the_start_year():
    arch = {2024: year(), 2025: year(), 2026: year()}
    assert sorted(records.playable(arch, '30L2025')) == [2025, 2026]
    assert sorted(records.playable(arch, 'MLBPA97')) == [2024, 2025, 2026]
    assert sorted(records.playable(arch, 'MYLEAGUE')) == [2024, 2025, 2026]       # a stem with no start year


# the chase

def lines(bats=None, pits=None):
    return {'bat': bats or {}, 'pit': pits or {}}


BARS = {'hr': {'value': 73, 'name': 'Barry Bonds', 'year': 2001, 'source': 'lahman'},
        'h': {'value': 262, 'name': 'Ichiro Suzuki', 'year': 2004, 'source': 'lahman'},
        'rbi': {'value': 191, 'name': 'Hack Wilson', 'year': 1930, 'source': 'lahman'},
        'sb': {'value': 130, 'name': 'Rickey Henderson', 'year': 1982, 'source': 'lahman'},
        'w': {'value': 59, 'name': 'Old Hoss', 'year': 1884, 'source': 'lahman'},
        'so': {'value': 513, 'name': 'Matt Kilroy', 'year': 1886, 'source': 'lahman'},
        'sv': {'value': 62, 'name': 'Francisco Rodriguez', 'year': 2008, 'source': 'lahman'}}


def run(bats=None, pits=None, games=81, season_games=162, bars=BARS, team_of=None, names=None):
    return records.chase(lines(bats, pits), NAMES if names is None else names,
                         {100: 1, 101: 1, 102: 2, 103: 2, 200: 1, 201: 2} if team_of is None else team_of,
                         {1: games, 2: games}, season_games, bars)


def test_chase_line_wording_for_a_pace_and_for_a_record_already_passed():
    assert run(bats={100: {'hr': 40}}) == [
        'Al Winner has 40 home runs, on pace for 80. The record is 73 (Barry Bonds, 2001).']
    assert run(bats={100: {'hr': 73}}) == ['Al Winner has 73 home runs, past the record of 73 (Barry Bonds, 2001).']
    assert run(pits={200: {'so': 300, 'w': 31, 'sv': 31}}) == [      # closest to the record (highest pace) first
        'Ed Hurler has 300 strikeouts, on pace for 600. The record is 513 (Matt Kilroy, 1886).',
        'Ed Hurler has 31 wins, on pace for 62. The record is 59 (Old Hoss, 1884).',
        'Ed Hurler has 31 saves, on pace for 62. The record is 62 (Francisco Rodriguez, 2008).']


def test_chase_labels():
    for stat, label in records.LABELS.items():
        kind = 'bat' if stat in records.COUNTING['bat'] else 'pit'
        got = records.chase(lines(**{kind[:3] + 's': {100: {stat: BARS[stat]['value']}}}), NAMES, {100: 1}, {1: 162},
                            162, BARS)
        assert got == ['Al Winner has %d %s, past the record of %d (%s, %d).' % (
            BARS[stat]['value'], label, BARS[stat]['value'], BARS[stat]['name'], BARS[stat]['year'])]


def test_chase_needs_two_fifths_of_the_schedule_played():
    assert run(bats={100: {'hr': 30}}, games=64) == []              # 64 of 162 is under 40 percent
    assert len(run(bats={100: {'hr': 30}}, games=65)) == 1          # 65 games is 40.1 percent: pace 75
    assert run(bats={100: {'hr': 30}}, games=0) == []
    assert run(bats={100: {'hr': 30}}, games=65, season_games=0) == []
    assert records.chase(lines({100: {'hr': 40}}), NAMES, {100: 1}, {1: 40}, 100, BARS)       # 40 of 100: exactly 40%
    assert not records.chase(lines({100: {'hr': 40}}), NAMES, {100: 1}, {1: 39}, 100, BARS)


def test_chase_threshold_is_nine_tenths_of_the_bar_on_the_pace():
    # 162 game pace at 81 games doubles the count; 0.9 * 73 = 65.7, so a pace of 66 is a line and 64 is not
    assert len(run(bats={100: {'hr': 33}})) == 1                    # pace 66
    assert run(bats={100: {'hr': 32}}) == []                        # pace 64
    bars = {'hr': {'value': 70, 'name': 'Slugger', 'year': 1999, 'source': 'sim'}}
    assert len(run(bats={100: {'hr': 63}}, games=162, bars=bars)) == 1      # pace 63 is exactly 0.9 * 70
    assert run(bats={100: {'hr': 62}}, games=162, bars=bars) == []
    assert run(bats={100: {'hr': 0}}) == []


def test_chase_pace_is_rounded():
    got = records.chase(lines({100: {'hr': 41}}), NAMES, {100: 1}, {1: 100}, 162, BARS)     # 66.42 rounds to 66
    assert got == ['Al Winner has 41 home runs, on pace for 66. The record is 73 (Barry Bonds, 2001).']
    got = records.chase(lines({100: {'hr': 42}}), NAMES, {100: 1}, {1: 100}, 162, BARS)     # 68.04
    assert 'on pace for 68.' in got[0]


def test_chase_at_most_three_closest_or_furthest_past_first():
    bats = {100: {'hr': 40, 'rbi': 100, 'h': 130}, 101: {'hr': 37, 'sb': 70}, 102: {'hr': 80}}
    got = run(bats=bats, pits={200: {'w': 30}})
    assert got == [
        'Cy Young has 80 home runs, past the record of 73 (Barry Bonds, 2001).',
        'Al Winner has 40 home runs, on pace for 80. The record is 73 (Barry Bonds, 2001).',
        'Bo Loser has 70 stolen bases, on pace for 140. The record is 130 (Rickey Henderson, 1982).']
    # furthest past first, then ties by name
    got = run(bats={100: {'hr': 80}, 101: {'hr': 90}, 102: {'hr': 80}})
    assert [x.split(' has ')[0] for x in got] == ['Bo Loser', 'Al Winner', 'Cy Young']
    assert 'past the record' in got[0]


def test_chase_players_past_the_record_come_before_a_higher_projection():
    bats = {100: {'hr': 73}, 101: {'hr': 41}}                      # 101 projects to 82 but is not there yet
    got = run(bats=bats, games=81)
    assert got[0].startswith('Al Winner has 73') and got[1].startswith('Bo Loser has 41')


def test_chase_ignores_unrostered_players_unusable_bars_and_stats_without_a_bar():
    assert run(bats={100: {'hr': 40}}, team_of={}) == []
    assert run(bats={100: {'hr': 40}}, team_of={100: 9}) == []                    # a team with no games played
    assert run(bats={100: {'hr': 40, 'r': 100, 'bb': 200, 'avg': 1}}, bars={'r': BARS['hr']}) == []
    for bad in ({'value': 0, 'name': 'X', 'year': 1}, {'value': 'x', 'name': 'X', 'year': 1},
                {'value': 73, 'name': 5, 'year': 1}, {'value': 73, 'name': 'X', 'year': 'y'}, 'text', None, {}):
        assert run(bats={100: {'hr': 40}}, bars={'hr': bad}) == []
    assert run(bats={100: {'hr': 40}}, bars=None) == [] and run(bats={100: {'hr': 40}}, bars={}) == []
    assert run(bats={100: {'hr': 40}}, names={}) == [
        'Player 100 has 40 home runs, on pace for 80. The record is 73 (Barry Bonds, 2001).']


def test_chase_lines_pass_numbers_ok_as_facts():
    got = run(bats={100: {'hr': 40}}, names={100: 'Al Winner'})
    text = 'Record watch: ' + ' '.join(got)
    assert recap.numbers_ok(text, {'chase': got})
    assert not recap.numbers_ok(text.replace('80', '81'), {'chase': got})
