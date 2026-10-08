import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from lahman import lahdb

SCHEMA = '''
CREATE TABLE teams (yearID INTEGER, lgID TEXT, divID TEXT, teamID TEXT, franchID TEXT, name TEXT, park TEXT,
    G INTEGER, W INTEGER, L INTEGER, teamRank INTEGER);
CREATE TABLE managers (playerID TEXT, yearID INTEGER, teamID TEXT, inseason INTEGER, G INTEGER);
CREATE TABLE appearances (yearID INTEGER, teamID TEXT, playerID TEXT, G_all INTEGER, GS INTEGER,
    G_batting INTEGER, G_p INTEGER, G_c INTEGER, G_1b INTEGER, G_2b INTEGER, G_3b INTEGER, G_ss INTEGER,
    G_lf INTEGER, G_cf INTEGER, G_rf INTEGER, G_of INTEGER, G_dh INTEGER);
CREATE TABLE people (playerID TEXT PRIMARY KEY, nameFirst TEXT, nameLast TEXT, birthYear INTEGER,
    birthMonth INTEGER, birthDay INTEGER, bats TEXT, throws TEXT, debut TEXT);
CREATE TABLE batting (playerID TEXT, yearID INTEGER, G INTEGER, AB INTEGER, R INTEGER, H INTEGER, "2B" INTEGER,
    "3B" INTEGER, HR INTEGER, RBI INTEGER, SB INTEGER, CS INTEGER, BB INTEGER, SO INTEGER, IBB INTEGER,
    HBP INTEGER, SH INTEGER, SF INTEGER, GIDP INTEGER);
CREATE TABLE pitching (playerID TEXT, yearID INTEGER, W INTEGER, L INTEGER, G INTEGER, GS INTEGER, CG INTEGER,
    SHO INTEGER, SV INTEGER, IPouts INTEGER, H INTEGER, ER INTEGER, HR INTEGER, BB INTEGER, SO INTEGER,
    IBB INTEGER, WP INTEGER, HBP INTEGER, BK INTEGER, BFP INTEGER, GF INTEGER, R INTEGER);
CREATE TABLE fielding (playerID TEXT, yearID INTEGER, POS TEXT, G INTEGER, GS INTEGER, InnOuts INTEGER,
    PO INTEGER, A INTEGER, E INTEGER, DP INTEGER, PB INTEGER, SB INTEGER, CS INTEGER);
'''

# Rows list only the columns they set; anything left out is NULL.
TEAMS = [
    {'yearID': 1990, 'lgID': 'AL', 'divID': 'E', 'teamID': 'BOS', 'franchID': 'BOS', 'name': 'Red Sox',
     'park': 'Fenway', 'G': 162, 'W': 88, 'L': 74, 'teamRank': 2},
    {'yearID': 1990, 'lgID': 'AL', 'divID': None, 'teamID': 'MIL', 'franchID': 'MIL', 'name': 'Brewers',
     'park': None, 'G': 162, 'W': 74, 'L': 88, 'teamRank': 6},
    {'yearID': 1990, 'lgID': 'NL', 'divID': 'E', 'teamID': 'NYN', 'franchID': 'NYM', 'name': 'Mets',
     'park': 'Shea', 'G': 162, 'W': 91, 'L': 71},
    {'yearID': 1990, 'lgID': 'NL', 'divID': 'W', 'teamID': 'LAN', 'franchID': 'LAD', 'name': 'Dodgers',
     'park': 'Dodger Stadium', 'G': 162, 'W': 86, 'L': 76, 'teamRank': 3},
    {'yearID': 1991, 'lgID': 'AL', 'divID': 'E', 'teamID': 'BOS', 'franchID': 'BOS', 'name': 'Red Sox',
     'park': 'Fenway', 'G': 162, 'W': 84, 'L': 78, 'teamRank': 4},
]

MANAGERS = [
    {'playerID': 'delta01', 'yearID': 1990, 'teamID': 'BOS', 'inseason': 1, 'G': 60},
    {'playerID': 'delta01', 'yearID': 1990, 'teamID': 'BOS', 'inseason': 2, 'G': 40},
    {'playerID': 'gamma01', 'yearID': 1990, 'teamID': 'BOS', 'inseason': 1, 'G': 62},
    {'playerID': 'zeta01', 'yearID': 1990, 'teamID': 'MIL', 'inseason': 2, 'G': 50},
    {'playerID': 'eps01', 'yearID': 1990, 'teamID': 'MIL', 'inseason': 1, 'G': 50},
    {'playerID': 'kappa01', 'yearID': 1990, 'teamID': 'NYN', 'inseason': 1, 'G': None},
    {'playerID': 'gamma01', 'yearID': 1989, 'teamID': 'BOS', 'inseason': 1, 'G': 150},
]

APPEARANCES = [
    {'yearID': 1990, 'teamID': 'BOS', 'playerID': 'alpha01', 'G_all': 60, 'GS': 58, 'G_batting': 60, 'G_ss': 60},
    {'yearID': 1990, 'teamID': 'MIL', 'playerID': 'alpha01', 'G_all': 20, 'G_batting': 20, 'G_2b': 20},
    {'yearID': 1990, 'teamID': 'BOS', 'playerID': 'bert01', 'G_all': 60, 'G_batting': 60, 'G_lf': 60},
    {'yearID': 1990, 'teamID': 'BOS', 'playerID': 'beta01', 'G_all': 35, 'GS': 30, 'G_p': 35},
    {'yearID': 1990, 'teamID': 'MIL', 'playerID': 'gamma01', 'G_all': 1, 'G_batting': 1},
    {'yearID': 1989, 'teamID': 'BOS', 'playerID': 'alpha01', 'G_all': 100, 'GS': 95, 'G_batting': 100, 'G_ss': 100},
    {'yearID': 1988, 'teamID': 'BOS', 'playerID': 'beta01', 'G_all': 10, 'GS': 8, 'G_p': 10},
]

PEOPLE = [
    {'playerID': 'alpha01', 'nameFirst': 'Al', 'nameLast': 'Alpha', 'birthYear': 1965, 'birthMonth': 3,
     'birthDay': 14, 'bats': 'L', 'throws': 'R', 'debut': '1988-04-05'},
    {'playerID': 'beta01', 'nameFirst': 'Bea', 'nameLast': 'Beta', 'throws': 'L'},
    {'playerID': 'gamma01', 'nameLast': 'Gamma', 'birthYear': 1970, 'birthMonth': 1, 'birthDay': 2, 'bats': 'R',
     'debut': '1990-09-01'},
    {'playerID': 'delta01', 'nameFirst': 'Dan', 'nameLast': 'Delta', 'birthYear': 1960, 'birthMonth': 12,
     'birthDay': 31, 'bats': 'B', 'throws': 'B', 'debut': '1982-06-15'},
]

BATTING = [
    {'playerID': 'alpha01', 'yearID': 1990, 'G': 60, 'AB': 200, 'R': 30, 'H': 60, '2B': 10, '3B': 1, 'HR': 5,
     'RBI': None, 'SB': 4, 'CS': 1, 'BB': 20, 'SO': 30, 'IBB': 0, 'HBP': 2, 'SH': 0, 'SF': 1, 'GIDP': 3},
    {'playerID': 'alpha01', 'yearID': 1990, 'G': 20, 'AB': 50, 'R': 5, 'H': 15, '2B': 2, '3B': 0, 'HR': 1,
     'RBI': 9, 'SB': 0, 'CS': 0, 'BB': 6, 'SO': 8, 'IBB': None, 'HBP': None, 'SH': 0, 'SF': 0, 'GIDP': 1},
    {'playerID': 'alpha01', 'yearID': 1989, 'G': 100, 'AB': 300, 'H': 90, 'HR': 10},
    {'playerID': 'beta01', 'yearID': 1990, 'G': 3, 'AB': 6, 'H': 1},
    {'playerID': 'gamma01', 'yearID': 1990, 'G': 1},
]

PITCHING = [
    {'playerID': 'beta01', 'yearID': 1990, 'W': 10, 'L': 5, 'G': 30, 'GS': 30, 'CG': 3, 'SHO': 1, 'SV': 0,
     'IPouts': 600, 'H': 200, 'ER': 80, 'HR': 20, 'BB': 50, 'SO': 150, 'IBB': 2, 'WP': 4, 'HBP': 3, 'BK': 0,
     'BFP': 800, 'GF': 0, 'R': 90},
    {'playerID': 'beta01', 'yearID': 1990, 'W': 2, 'L': 1, 'G': 5, 'GS': 0, 'SV': 1, 'IPouts': 45, 'ER': 5,
     'SO': 9},
    {'playerID': 'beta01', 'yearID': 1988, 'W': 3, 'L': 3, 'G': 10, 'GS': 8, 'IPouts': 240},
]

FIELDING = [
    {'playerID': 'alpha01', 'yearID': 1990, 'POS': 'SS', 'G': 60, 'GS': 58, 'InnOuts': 1560, 'PO': 100, 'A': 200,
     'E': 10, 'DP': 40, 'SB': 0, 'CS': 0},
    {'playerID': 'alpha01', 'yearID': 1990, 'POS': 'SS', 'G': 20, 'GS': 2, 'InnOuts': 500, 'PO': 30, 'A': 60,
     'E': 2, 'DP': 10},
    {'playerID': 'alpha01', 'yearID': 1990, 'POS': '2B', 'G': 5, 'GS': 5, 'InnOuts': 135, 'PO': 8, 'A': 12,
     'E': 0, 'DP': 2},
    {'playerID': 'alpha01', 'yearID': 1989, 'POS': 'SS', 'G': 100, 'GS': 98, 'InnOuts': 2500, 'PO': 200,
     'A': 350, 'E': 15, 'DP': 70},
    {'playerID': 'beta01', 'yearID': 1990, 'POS': 'P', 'G': 35, 'GS': 30, 'InnOuts': 645, 'PO': 4, 'A': 20,
     'E': 1, 'DP': 0},
    {'playerID': 'beta01', 'yearID': 1988, 'POS': 'P', 'G': 10, 'GS': 8, 'InnOuts': 240, 'PO': 2, 'A': 9, 'E': 0},
]


def _insert(db, table, rows):
    for row in rows:
        names = ', '.join(f'"{c}"' for c in row)
        marks = ', '.join(['?'] * len(row))
        db.execute(f'INSERT INTO {table} ({names}) VALUES ({marks})', tuple(row.values()))


def _zeros(cols, **counts):
    return {c: counts.get(c, 0) for c in cols}


@pytest.fixture
def con():
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    for table, rows in [('teams', TEAMS), ('managers', MANAGERS), ('appearances', APPEARANCES),
                        ('people', PEOPLE), ('batting', BATTING), ('pitching', PITCHING),
                        ('fielding', FIELDING)]:
        _insert(db, table, rows)
    yield db
    db.close()


def test_teams_one_year_sorted_with_null_defaults(con):
    out = lahdb.teams(con, 1990)
    assert [(t['lgID'], t['divID'], t['teamID']) for t in out] == [
        ('AL', '', 'MIL'), ('AL', 'E', 'BOS'), ('NL', 'E', 'NYN'), ('NL', 'W', 'LAN')]
    assert out[0] == {'teamID': 'MIL', 'lgID': 'AL', 'divID': '', 'franchID': 'MIL', 'name': 'Brewers',
                      'park': '', 'G': 162, 'W': 74, 'L': 88, 'rank': 6}
    assert out[2]['rank'] == 0  # NULL Rank
    assert lahdb.teams(con, 1991) == [{'teamID': 'BOS', 'lgID': 'AL', 'divID': 'E', 'franchID': 'BOS',
                                       'name': 'Red Sox', 'park': 'Fenway', 'G': 162, 'W': 84, 'L': 78,
                                       'rank': 4}]


def test_managers_most_g_summed_per_player_tie_to_lowest_inseason(con):
    out = lahdb.managers(con, 1990)
    assert out['BOS'] == {'playerID': 'delta01', 'first': 'Dan', 'last': 'Delta', 'G': 100}
    # zeta01 and eps01 both have 50 G; eps01 has the lower inseason
    assert out['MIL'] == {'playerID': 'eps01', 'first': '', 'last': '', 'G': 50}
    assert out['NYN'] == {'playerID': 'kappa01', 'first': '', 'last': '', 'G': 0}
    assert set(out) == {'BOS', 'MIL', 'NYN'}


def test_roster_by_g_all_then_player_id(con):
    assert lahdb.roster(con, 1990) == {
        'BOS': ['alpha01', 'bert01', 'beta01'],
        'MIL': ['alpha01', 'gamma01'],
    }


def test_appearances_per_team_with_null_counts_as_zero(con):
    out = lahdb.appearances(con, 1990)
    assert out['alpha01']['BOS'] == _zeros(lahdb.APP_COLS, G_all=60, GS=58, G_batting=60, G_ss=60)
    assert out['alpha01']['MIL'] == _zeros(lahdb.APP_COLS, G_all=20, G_batting=20, G_2b=20)
    assert set(out) == {'alpha01', 'bert01', 'beta01', 'gamma01'}
    assert lahdb.appearances(con, 1988) == {'beta01': {'BOS': _zeros(lahdb.APP_COLS, G_all=10, GS=8, G_p=10)}}


def test_people_defaults_and_missing_ids(con):
    out = lahdb.people(con, ['alpha01', 'beta01', 'gamma01', 'nobody01'])
    assert out['alpha01'] == {'first': 'Al', 'last': 'Alpha', 'birth_year': 1965, 'birth_month': 3,
                              'birth_day': 14, 'bats': 'L', 'throws': 'R', 'debut': '1988-04-05'}
    assert out['beta01'] == {'first': 'Bea', 'last': 'Beta', 'birth_year': None, 'birth_month': None,
                             'birth_day': None, 'bats': '', 'throws': 'L', 'debut': ''}
    assert out['gamma01']['first'] == ''
    assert out['gamma01']['throws'] == ''
    assert 'nobody01' not in out
    assert lahdb.people(con, []) == {}


def test_people_chunks_long_id_lists(con):
    ids = ['alpha01'] * 1200 + ['delta01']
    assert set(lahdb.people(con, ids)) == {'alpha01', 'delta01'}


def test_batting_one_season_sums_stints_and_nulls(con):
    out = lahdb.batting(con, year=1990)
    assert out['alpha01'] == {'G': 80, 'AB': 250, 'R': 35, 'H': 75, '2B': 12, '3B': 1, 'HR': 6, 'RBI': 9,
                              'SB': 4, 'CS': 1, 'BB': 26, 'SO': 38, 'IBB': 0, 'HBP': 2, 'SH': 0, 'SF': 1,
                              'GIDP': 4}
    assert out['gamma01'] == _zeros(lahdb.BAT_COLS, G=1)
    assert set(out) == {'alpha01', 'beta01', 'gamma01'}


def test_batting_before_is_career_through_prior_season(con):
    out = lahdb.batting(con, before=1990)
    assert out == {'alpha01': _zeros(lahdb.BAT_COLS, G=100, AB=300, H=90, HR=10)}


def test_batting_neither_raises(con):
    with pytest.raises(ValueError):
        lahdb.batting(con)


def test_batting_both_raises(con):
    with pytest.raises(ValueError):
        lahdb.batting(con, year=1990, before=1991)


def test_pitching_one_season_sums_stints(con):
    out = lahdb.pitching(con, year=1990)
    assert out == {'beta01': {'W': 12, 'L': 6, 'G': 35, 'GS': 30, 'CG': 3, 'SHO': 1, 'SV': 1, 'IPouts': 645,
                              'H': 200, 'ER': 85, 'HR': 20, 'BB': 50, 'SO': 159, 'IBB': 2, 'WP': 4, 'HBP': 3,
                              'BK': 0, 'BFP': 800, 'GF': 0, 'R': 90}}


def test_pitching_before_and_neither(con):
    assert lahdb.pitching(con, before=1990) == {
        'beta01': _zeros(lahdb.PIT_COLS, W=3, L=3, G=10, GS=8, IPouts=240)}
    with pytest.raises(ValueError):
        lahdb.pitching(con)


def test_pitching_both_raises(con):
    with pytest.raises(ValueError):
        lahdb.pitching(con, year=1990, before=1991)


def test_fielding_year_keys_by_pos_and_sums_stints(con):
    out = lahdb.fielding(con, year=1990)
    assert out['alpha01']['SS'] == _zeros(lahdb.FLD_COLS, G=80, GS=60, InnOuts=2060, PO=130, A=260, E=12,
                                          DP=50)
    assert out['alpha01']['2B'] == _zeros(lahdb.FLD_COLS, G=5, GS=5, InnOuts=135, PO=8, A=12, E=0, DP=2)
    assert out['beta01'] == {'P': _zeros(lahdb.FLD_COLS, G=35, GS=30, InnOuts=645, PO=4, A=20, E=1, DP=0)}
    assert set(out) == {'alpha01', 'beta01'}


def test_fielding_before_is_career_through_prior_season(con):
    out = lahdb.fielding(con, before=1990)
    assert out['alpha01'] == {'SS': _zeros(lahdb.FLD_COLS, G=100, GS=98, InnOuts=2500, PO=200, A=350, E=15,
                                           DP=70)}
    assert out['beta01'] == {'P': _zeros(lahdb.FLD_COLS, G=10, GS=8, InnOuts=240, PO=2, A=9, E=0)}


def test_fielding_needs_exactly_one_of_year_or_before(con):
    with pytest.raises(ValueError):
        lahdb.fielding(con, year=1990, before=1991)
    with pytest.raises(ValueError):
        lahdb.fielding(con)


def test_seasons_before_counts_distinct_years(con):
    assert lahdb.seasons_before(con, 1990) == {'alpha01': 1, 'beta01': 1}
    # alpha01 has two 1990 rows (two teams); they count as one season
    assert lahdb.seasons_before(con, 1991) == {'alpha01': 2, 'beta01': 2, 'bert01': 1, 'gamma01': 1}


def test_every_result_is_json_serializable(con):
    results = [
        lahdb.teams(con, 1990), lahdb.managers(con, 1990), lahdb.roster(con, 1990),
        lahdb.appearances(con, 1990), lahdb.people(con, ['alpha01', 'beta01']),
        lahdb.batting(con, year=1990), lahdb.pitching(con, before=1991), lahdb.fielding(con, year=1990),
        lahdb.seasons_before(con, 1991),
    ]
    json.dumps(results)


def test_connect_is_read_only():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'lahman test.sqlite'  # the space checks path quoting in the URI
        make = sqlite3.connect(path)
        make.execute('CREATE TABLE teams (yearID INTEGER, teamID TEXT)')
        make.execute("INSERT INTO teams VALUES (1990, 'BOS')")
        make.commit()
        make.close()

        ro = lahdb.connect(path)
        try:
            assert ro.execute('SELECT teamID FROM teams').fetchall() == [('BOS',)]
            with pytest.raises(sqlite3.OperationalError):
                ro.execute("INSERT INTO teams VALUES (1991, 'NYN')")
        finally:
            ro.close()


REAL_DB = Path('/mnt/nvme/tlrb2/lahman/lahmansbaseballdb.sqlite')


@pytest.mark.skipif(not REAL_DB.exists(), reason='Lahman database not present')
def test_real_database_schema():
    """The synthetic schema above must match the real one: run every reader once against it."""
    real = lahdb.connect(REAL_DB)
    try:
        t = lahdb.teams(real, 1927)
        assert len(t) == 16 and {x['rank'] for x in t} == set(range(1, 9))
        assert lahdb.managers(real, 1927)['NYA']['playerID'] == 'huggimi01'
        assert 'ruthba01' in lahdb.roster(real, 1927)['NYA']
        assert lahdb.appearances(real, 1927)['ruthba01']['NYA']['G_all'] == 151
        assert lahdb.people(real, ['ruthba01'])['ruthba01']['bats'] == 'L'
        assert lahdb.batting(real, year=1927)['ruthba01']['HR'] == 60
        assert lahdb.pitching(real, before=1927)['ruthba01']['W'] == 92
        assert 'OF' in lahdb.fielding(real, year=1927)['ruthba01']
        assert lahdb.seasons_before(real, 1927)['ruthba01'] == 13
    finally:
        real.close()
