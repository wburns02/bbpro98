import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lahman import teamnames  # noqa: E402
from lahman.build import team_name  # noqa: E402


def test_table():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT, name TEXT)')
    con.executemany('INSERT INTO teams VALUES (?, ?, ?, ?)', [
        (1998, 'AL', 'BAL', 'Baltimore Orioles'), (1998, 'AL', 'NYA', 'New York Yankees'),
        (1875, 'NA', 'NH1', 'New Haven Elm Citys'), (1884, 'AA', 'WAS', 'Washington Nationals'),
        (1884, 'UA', 'WAS', 'Washington Nationals')])
    t = teamnames.table(con)
    assert t['1998'] == {'BAL': ['Baltimore Orioles', 'Balt. Orioles'], 'NYA': ['New York Yankees', 'New York Yankees']}
    assert t['1875']['NH1'] == ['New Haven Elm Citys', team_name('New Haven Elm Citys')]
    assert t['1884'] == {}                       # a teamID used twice in a year is ambiguous
