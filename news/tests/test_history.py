"""history.py: lahman_id, real_seasons and open_db on a tiny Lahman database built under tmp_path, find_db, the sim
season files (archive_season, sim_seasons), and merge, totals and start_year. No game file or real Lahman database
is read.
"""
import datetime
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import history      # noqa: E402

SCHEMA = (
    'CREATE TABLE people (playerID TEXT, nameFirst TEXT, nameLast TEXT, birthYear INT, birthMonth INT, birthDay INT)',
    'CREATE TABLE teams (yearID INT, teamID TEXT, teamIDBR TEXT)',
    'CREATE TABLE batting (playerID, yearID, stint, teamID, G, AB, R, H, "2B", "3B", HR, RBI, SB, CS, BB, SO, IBB, '
    'HBP, SH, SF, GIDP)',
    'CREATE TABLE pitching (playerID, yearID, stint, teamID, W, L, G, GS, CG, SHO, SV, IPouts, H, ER, HR, BB, SO, '
    'HBP, BFP, R)',
)
PEOPLE = [
    ('smithjo01', 'John', 'Smith', 1970, 3, 4),
    ('smithjo02', 'John', 'Smith', 1975, 6, 7),
    ('longch01', 'Christopher', 'Longlastnamesson', 1968, 9, 9),
    ('doubdan01', 'Dan', 'Doublestint', 1960, 1, 1),
    ('nullpat01', 'Pat', 'Nulls', 1950, 5, 5),
]
TEAMS = [
    (1995, 'NYA', 'NYY'), (1996, 'NYA', 'NYY'),
    (1961, 'NYA', 'NYY'), (1961, 'BOS', 'BOS'),
    (1975, 'LAN', ''),      # no teamIDBR: the label falls back to the teamID
]
BATTING = [
    ('smithjo01', 1995, 1, 'NYA', 150, 500, 80, 150, 30, 2, 20, 90, 10, 3, 60, 100, 2, 3, 0, 4, 12),
    ('smithjo01', 1996, 1, 'NYA', 140, 480, 70, 130, 25, 1, 18, 80, 8, 2, 55, 95, 1, 2, 0, 3, 10),
    ('doubdan01', 1961, 1, 'NYA', 50, 100, 10, 20, 3, 1, 2, 9, 0, 0, 8, 15, 0, 0, 0, 1, 2),
    ('doubdan01', 1961, 2, 'BOS', 30, 60, 5, 10, 2, 0, 1, 4, 0, 0, 4, 9, 0, 0, 0, 0, 1),
]
PITCHING = [
    ('nullpat01', 1975, 1, 'LAN', None, '', 30, None, 0, None, '', None, 40, None, 5, 10, 20, None, None, None),
    ('nullpat01', 1976, 1, 'LAN') + (0,) * 16,
]


def build_db(path):
    """A Lahman database at path with the four tables and the rows above."""
    conn = sqlite3.connect(str(path))
    for statement in SCHEMA:
        conn.execute(statement)
    conn.executemany('INSERT INTO people VALUES (?, ?, ?, ?, ?, ?)', PEOPLE)
    conn.executemany('INSERT INTO teams VALUES (?, ?, ?)', TEAMS)
    conn.executemany('INSERT INTO batting VALUES (%s)' % ', '.join('?' * 21), BATTING)
    conn.executemany('INSERT INTO pitching VALUES (%s)' % ', '.join('?' * 20), PITCHING)
    conn.commit()
    conn.close()
    return str(path)


def add_rows(db_path, table, rows):
    """Adds rows to a table of the fixture database, for the candidates a test needs on top of the base data."""
    conn = sqlite3.connect(db_path)
    conn.executemany('INSERT INTO %s VALUES (%s)' % (table, ', '.join('?' * len(rows[0]))), rows)
    conn.commit()
    conn.close()


def zeros(keys, **values):
    """A line with every key of keys: the given values, 0 where none is given."""
    out = dict.fromkeys(keys, 0)
    out.update(values)
    return out


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_text(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


@pytest.fixture
def db_path(tmp_path):
    return build_db(tmp_path / 'lahman.sqlite')


@pytest.fixture
def conn(db_path):
    connection = history.open_db(db_path)
    yield connection
    connection.close()


# lahman_id

def test_lahman_id_needs_the_name_and_the_birth_date(conn):
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1975, 6, 7)) == 'smithjo02'
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1970, 3, 4)) == 'smithjo01'
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1990, 1, 1)) is None


def test_lahman_id_exact_match_beats_a_prefix_match(db_path, conn):
    add_rows(db_path, 'people', [('smithers01', 'Johnny', 'Smithers', 1970, 3, 4)])
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1970, 3, 4)) == 'smithjo01'


def test_lahman_id_several_candidates_give_none(db_path, conn):
    add_rows(db_path, 'people', [('smithjo03', 'John', 'Smith', 1970, 3, 4)])
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1970, 3, 4)) is None      # two exact matches
    add_rows(db_path, 'people', [('smithers01', 'Johnny', 'Smithers', 1980, 1, 2)])
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1980, 1, 2)) == 'smithers01'
    add_rows(db_path, 'people', [('smithson01', 'Johan', 'Smithson', 1980, 1, 2)])
    assert history.lahman_id(conn, 'John', 'Smith', datetime.date(1980, 1, 2)) is None      # two prefix matches


def test_lahman_id_fallback_takes_a_cut_last_name_and_three_letters_of_the_first(conn):
    born = datetime.date(1968, 9, 9)
    assert history.lahman_id(conn, 'Christopher', 'Longlastnamesso', born) == 'longch01'
    assert history.lahman_id(conn, 'Chris', 'Longlastnamesso', born) == 'longch01'
    assert history.lahman_id(conn, 'Kit', 'Longlastnamesso', born) is None
    assert history.lahman_id(conn, 'Christopher', 'Longlastnamesso', datetime.date(1968, 9, 10)) is None


def test_lahman_id_empty_or_missing_first_name_matches_any_first(conn):
    assert history.lahman_id(conn, '', 'Longlastnamesso', datetime.date(1968, 9, 9)) == 'longch01'
    assert history.lahman_id(conn, None, 'Smith', datetime.date(1975, 6, 7)) == 'smithjo02'


def test_lahman_id_ignores_case_and_surrounding_space(conn):
    assert history.lahman_id(conn, '  JOHN ', ' smith\t', datetime.date(1975, 6, 7)) == 'smithjo02'
    assert history.lahman_id(conn, 'christopher', 'LONGLASTNAMESSO ', datetime.date(1968, 9, 9)) == 'longch01'


def test_lahman_id_with_no_last_name_is_none(conn):
    assert history.lahman_id(conn, 'John', '', datetime.date(1975, 6, 7)) is None
    assert history.lahman_id(conn, 'John', None, datetime.date(1975, 6, 7)) is None


# real_seasons

def test_real_seasons_maps_each_year_to_the_game_keys(conn):
    seasons = history.real_seasons(conn, 'smithjo01', 'bat')
    assert [season['year'] for season in seasons] == [1995, 1996]
    assert seasons[0] == {'year': 1995, 'team': 'NYY', 'stints': 1,
                          'g': 150, 'ab': 500, 'r': 80, 'h': 150, 'h2b': 30, 'h3b': 2, 'hr': 20, 'rbi': 90,
                          'bb': 60, 'so': 100, 'sb': 10, 'hbp': 3, 'sf': 4}


def test_real_seasons_sums_stints_and_labels_two_teams_2tm(conn):
    [season] = history.real_seasons(conn, 'doubdan01', 'bat')
    assert season['team'] == '2TM' and season['stints'] == 2
    assert {key: season[key] for key in history.BAT_KEYS} == zeros(
        history.BAT_KEYS, g=80, ab=160, r=15, h=30, h2b=5, h3b=1, hr=3, rbi=13, bb=12, so=24, sf=1)


def test_real_seasons_falls_back_to_teamid_without_a_teamidbr(conn):
    seasons = history.real_seasons(conn, 'nullpat01', 'pit')
    assert [(season['year'], season['team']) for season in seasons] == [(1975, 'LAN'), (1976, 'LAN')]


def test_real_seasons_before_keeps_only_earlier_years(conn):
    assert [season['year'] for season in history.real_seasons(conn, 'smithjo01', 'bat', before=1996)] == [1995]
    assert history.real_seasons(conn, 'smithjo01', 'bat', before=1995) == []


def test_real_seasons_counts_null_and_empty_as_zero_and_keeps_all_zero_years(conn):
    seasons = history.real_seasons(conn, 'nullpat01', 'pit')
    assert seasons[0] == dict(year=1975, team='LAN', stints=1,
                              **zeros(history.PIT_KEYS, g=30, h=40, bb=10, so=20, hr=5))
    assert seasons[1] == dict(year=1976, team='LAN', stints=1, **zeros(history.PIT_KEYS))


def test_real_seasons_pit_reads_pitching_and_a_bad_kind_raises(conn):
    assert [season['year'] for season in history.real_seasons(conn, 'nullpat01', 'pit')] == [1975, 1976]
    assert history.real_seasons(conn, 'nullpat01', 'bat') == []
    with pytest.raises(ValueError):
        history.real_seasons(conn, 'nullpat01', 'x')


# open_db and find_db

def test_open_db_is_read_only(conn):
    assert conn.execute('SELECT COUNT(*) FROM people').fetchone() == (len(PEOPLE),)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO people VALUES ('x', 'A', 'B', 1, 1, 1)")


def test_open_db_takes_a_path_with_uri_characters(tmp_path):
    conn = history.open_db(build_db(tmp_path / 'odd #name?.sqlite'))
    assert conn.execute('SELECT COUNT(*) FROM people').fetchone() == (len(PEOPLE),)
    conn.close()


def test_find_db_takes_the_env_file_then_the_default(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'DEFAULT_DB', db_path)
    assert history.find_db({'BBPRO98_LAHMAN': db_path}) == db_path
    assert history.find_db({'BBPRO98_LAHMAN': str(tmp_path / 'missing.sqlite')}) == db_path
    assert history.find_db({}) == db_path


def test_find_db_is_none_when_neither_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'DEFAULT_DB', str(tmp_path / 'nope.sqlite'))
    assert history.find_db({}) is None
    assert history.find_db({'BBPRO98_LAHMAN': str(tmp_path)}) is None      # a directory is not a file


# archive_season and sim_seasons

def test_archive_season_writes_once_and_leaves_no_tmp(tmp_path):
    data = str(tmp_path)
    assert history.archive_season(data, 'abc1', 1997, {'bat': {205: {'g': 3}}}) is True
    path = history.archive_path(data, 'abc1', 1997)
    assert path == os.path.join(data, 'ABC1', 'history', '1997.json')
    with open(path, 'rb') as f:
        first = f.read()
    assert history.archive_season(data, 'abc1', 1997, {'bat': {205: {'g': 99}}}, {205: 'LAN'}) is False
    with open(path, 'rb') as f:
        assert f.read() == first
    assert os.listdir(os.path.dirname(path)) == ['1997.json']


def test_archive_season_keeps_only_the_line_keys_as_ints(tmp_path):
    lines = {'bat': {205: {'g': 3, 'ab': 'x', 'junk': 9, 'h': True, 'sf': 2}}, 'pit': {206: {'w': 4, 'outs': 90}}}
    history.archive_season(str(tmp_path), 'abc1', 1997, lines, {205: 'NYY'})
    assert read_json(history.archive_path(str(tmp_path), 'abc1', 1997)) == {
        'year': 1997,
        'bat': {'205': zeros(history.BAT_KEYS, g=3, sf=2)},
        'pit': {'206': zeros(history.PIT_KEYS, w=4, outs=90)},
        'team': {'205': 'NYY'}}


def test_archive_season_rejects_a_bad_stem_or_year(tmp_path):
    for stem, year in (('../x', 1997), ('abcdefghi', 1997), ('', 1997), ('a/b', 1997), ('abc1', 99), ('abc1', 3001)):
        with pytest.raises(ValueError):
            history.archive_season(str(tmp_path), stem, year, {})
    assert os.listdir(str(tmp_path)) == []


def test_sim_seasons_reads_back_each_year_the_pid_has_a_line(tmp_path):
    data = str(tmp_path)
    assert history.sim_seasons(data, 'abc1', 205, 'bat') == []
    history.archive_season(data, 'abc1', 1999, {'bat': {205: {'g': 7}}})
    history.archive_season(data, 'abc1', 1997, {'bat': {205: {'g': 3, 'h': 5}, 206: {'g': 9}}}, {205: 'NYY'})
    history.archive_season(data, 'abc1', 1998, {'pit': {205: {'w': 2}}})
    assert history.sim_seasons(data, 'abc1', 205, 'bat') == [
        dict(year=1997, team='NYY', **zeros(history.BAT_KEYS, g=3, h=5)),
        dict(year=1999, team='', **zeros(history.BAT_KEYS, g=7))]
    assert history.sim_seasons(data, 'abc1', 205, 'pit') == [dict(year=1998, team='', **zeros(history.PIT_KEYS, w=2))]


def test_sim_seasons_skips_malformed_files_and_names_that_are_not_years(tmp_path):
    data = str(tmp_path)
    history.archive_season(data, 'abc1', 1997, {'bat': {205: {'g': 3}}})
    folder = os.path.join(data, 'ABC1', 'history')
    write_text(os.path.join(folder, '1998.json'), '{"bat": ')
    write_text(os.path.join(folder, '1999.json'), '[1, 2]')
    write_text(os.path.join(folder, 'notes.json'), json.dumps({'year': 2000, 'bat': {'205': {'g': 1}}}))
    assert history.sim_seasons(data, 'abc1', 205, 'bat') == [dict(year=1997, team='', **zeros(history.BAT_KEYS, g=3))]


# merge, totals and start_year

def season(year, team='NYY'):
    return {'year': year, 'team': team, 'g': 1}


def test_merge_drops_real_seasons_from_start_on():
    rows = history.merge([season(1995), season(1996), season(1997)], [season(1998, 'LAN')], start=1996)
    assert rows == [dict(season(1995), sim=False), dict(season(1998, 'LAN'), sim=True)]


def test_merge_sim_row_wins_a_shared_year_and_sorts_by_year():
    real = [season(1997)]
    rows = history.merge(real, [season(1997, 'LAN'), season(1996, 'BOS')])
    assert rows == [dict(season(1996, 'BOS'), sim=True), dict(season(1997, 'LAN'), sim=True)]
    assert real == [season(1997)]      # the inputs are not changed


def test_totals_sums_each_key_and_counts_the_seasons():
    rows = [dict(year=1995, team='NYY', stints=1, **zeros(history.BAT_KEYS, g=150, h=150, hr=20)),
            dict(year=1996, team='NYY', stints=1, **zeros(history.BAT_KEYS, g=140, h=130, hr=18))]
    assert history.totals(rows, 'bat') == dict(zeros(history.BAT_KEYS, g=290, h=280, hr=38), seasons=2)
    assert history.totals([], 'pit') == dict(zeros(history.PIT_KEYS), seasons=0)


def test_start_year_reads_the_league_stem_year():
    assert history.start_year('30L2025') == 2025
    assert history.start_year('28n1998', 2010) == 1998


def test_start_year_is_fixed_for_mlbpa_and_season_year_for_other_stems():
    assert history.start_year('MLBPA97') == 1997
    assert history.start_year('mlbpa96e') == 1997
    assert history.start_year('CUSTOM1', 2003) == 2003
    assert history.start_year('CUSTOM1') is None
