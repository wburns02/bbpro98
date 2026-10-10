"""load_csv: a CSV release into the old SQL edition's schema, on a tiny synthetic reference and release."""
import sqlite3

import pytest

from lahman import load_csv as L

REF = '''
CREATE TABLE leagues (lgID TEXT NOT NULL, league TEXT, active TEXT);
CREATE TABLE divisions (ID INTEGER PRIMARY KEY, divID TEXT, lgID TEXT, division TEXT);
CREATE TABLE people (playerID TEXT, birthYear INT, birthMonth INT, birthDay INT, birth_date TEXT,
                     deathYear INT, deathMonth INT, deathDay INT, death_date TEXT, debut TEXT, finalGame TEXT,
                     debut_date TEXT, finalgame_date TEXT);
CREATE TABLE teams (ID INTEGER, yearID INT, lgID TEXT, teamID TEXT, divID TEXT, div_ID INT, teamRank INT);
CREATE TABLE batting (ID INTEGER, playerID TEXT, yearID INT, teamID TEXT, team_ID INT, G INT, G_batting INT);
CREATE TABLE appearances (ID INTEGER, playerID TEXT, yearID INT, teamID TEXT, team_ID INT, G_batting INT);
CREATE UNIQUE INDEX people_key ON people (playerID);
'''

CSV = {
    'People.csv': 'ID,playerID,birthYear,birthMonth,birthDay,deathYear,deathMonth,deathDay,debut,finalGame\n'
                  '1,smithjo01,1990,7,4,,,,2012-04-05 00:00:00,2025-09-28 00:00:00\n'
                  '2,gibsojo01,1911,12,21,1947,1,20,1930-07-31,1946-09-08\n',
    'Teams.csv': 'yearID,lgID,teamID,divID,Rank\n2025,AL,NYA,E,1\n1942,NN2,HG,,2\n',
    'Batting.csv': 'playerID,yearID,teamID,G\nsmithjo01,2025,NYA,150\ngibsojo01,1942,HG,60\n',
    'Appearances.csv': 'playerID,yearID,teamID,G_batting\nsmithjo01,2025,NYA,148\ngibsojo01,1942,HG,58\n',
}


@pytest.fixture
def ref(tmp_path):
    p = tmp_path / 'ref.sqlite'
    con = sqlite3.connect(str(p))
    con.executescript(REF)
    con.execute("INSERT INTO leagues VALUES ('AL', 'American League', 'Y')")
    con.execute("INSERT INTO divisions VALUES (7, 'E', 'AL', 'East')")
    con.commit()
    con.close()
    return p


def release(tmp_path, files=CSV):
    d = tmp_path / 'csv'
    d.mkdir()
    for name, text in files.items():
        (d / name).write_text(text)
    return d


def test_load_fills_derived_columns(tmp_path, ref):
    out = tmp_path / 'new.sqlite'
    counts = L.load(release(tmp_path), ref, out, log=lambda s: None)
    assert counts['people'] == 2 and counts['batting'] == 2 and counts['leagues'] == 1
    con = sqlite3.connect(str(out))
    assert con.execute("SELECT teamRank, ID, div_ID FROM teams WHERE teamID = 'NYA'").fetchone() == (1, 1, 7)
    team_ids = dict(con.execute('SELECT teamID, team_ID FROM batting'))
    assert team_ids == {'NYA': 1, 'HG': 2}
    assert dict(con.execute('SELECT playerID, G_batting FROM batting')) == {'smithjo01': 148, 'gibsojo01': 58}
    assert con.execute("SELECT birth_date, death_date, debut_date FROM people WHERE playerID = 'gibsojo01'"
                       ).fetchone() == ('1911-12-21', '1947-01-20', '1930-07-31')
    assert con.execute("SELECT death_date FROM people WHERE playerID = 'smithjo01'").fetchone() == (None,)
    leagues = dict(con.execute('SELECT lgID, active FROM leagues'))
    assert leagues['AL'] == 'Y' and leagues['NN2'] == 'N' and set(L.EXTRA_LEAGUES) <= set(leagues)
    assert not out.with_name(out.name + '.part').exists()


def test_refuses_existing_output(tmp_path, ref):
    out = tmp_path / 'new.sqlite'
    out.write_text('keep me')
    with pytest.raises(SystemExit):
        L.load(release(tmp_path), ref, out, log=lambda s: None)
    assert out.read_text() == 'keep me'


def test_unknown_column_and_missing_table_are_errors(tmp_path, ref):
    bad = dict(CSV, **{'Batting.csv': 'playerID,yearID,teamID,G,DROP_ME\nx,2025,NYA,1,2\n'})
    with pytest.raises(SystemExit, match='DROP_ME'):
        L.load(release(tmp_path, bad), ref, tmp_path / 'a.sqlite', log=lambda s: None)
    missing = {k: v for k, v in CSV.items() if k != 'Appearances.csv'}
    (tmp_path / 'csv2').mkdir()
    for name, text in missing.items():
        (tmp_path / 'csv2' / name).write_text(text)
    with pytest.raises(SystemExit, match='appearances'):
        L.load(tmp_path / 'csv2', ref, tmp_path / 'b.sqlite', log=lambda s: None)
    assert not (tmp_path / 'b.sqlite').exists()


def test_broken_unique_index_kept_without_constraint(tmp_path, ref):
    dup = dict(CSV, **{'People.csv': CSV['People.csv'] + '3,smithjo01,1990,7,4,,,,,\n'})
    logs = []
    L.load(release(tmp_path, dup), ref, tmp_path / 'c.sqlite', log=logs.append)
    con = sqlite3.connect(str(tmp_path / 'c.sqlite'))
    assert con.execute("SELECT sql FROM sqlite_master WHERE name = 'people_key'").fetchone()[0].startswith(
        'CREATE INDEX')
    assert any('people_key' in s for s in logs)
