import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import teamnames  # noqa: E402

TABLE = {'1998': {'BAL': ['Baltimore Orioles', 'Balt. Orioles'], 'NYA': ['New York Yankees', 'New York Yankees']},
         '1875': {'BS1': ['Boston Red Stockings', 'Red Stockings'], 'SL1': ['St. Louis Red Stockings', 'Red Stockings']}}


def assoc(name, *teams):
    return {'name': name, 'games': [],
            'teams': {i + 1: {'tid': i + 1, 'abbrev': a, 'name': n} for i, (a, n) in enumerate(teams)}}


def names(a):
    return [t['name'] for t in a['teams'].values()]


def test_short_name_replaced_by_year_and_abbrev():
    a = assoc('1998 Major Leagues', ('BAL', 'Balt. Orioles'), ('NYA', 'New York Yankees'))
    assert names(teamnames.apply(a, TABLE)) == ['Baltimore Orioles', 'New York Yankees']
    assert names(a) == ['Balt. Orioles', 'New York Yankees']          # input untouched


def test_same_nickname_split_by_abbrev():
    a = assoc('1875 Major Leagues', ('BS1', 'Red Stockings'), ('SL1', 'Red Stockings'))
    assert names(teamnames.apply(a, TABLE)) == ['Boston Red Stockings', 'St. Louis Red Stockings']


def test_left_alone():
    stock = assoc('MLBPA 1996', ('BAL', 'Balt. Orioles'))
    renamed = assoc('1998 Major Leagues', ('BAL', 'Orioles of Maryland'))
    other_year = assoc('1997 Major Leagues', ('BAL', 'Balt. Orioles'))
    no_abbrev = assoc('1998 Major Leagues', ('XXX', 'Balt. Orioles'))
    year_in_text = assoc('19987 League', ('BAL', 'Balt. Orioles'))
    for a in (stock, renamed, other_year, no_abbrev, year_in_text):
        assert names(teamnames.apply(a, TABLE)) == names(a)
    assert teamnames.apply(stock, {}) == stock


def test_bad_table_entries_ignored():
    a = assoc('1998 Major Leagues', ('BAL', 'Balt. Orioles'))
    for bad in ({'1998': []}, {'1998': {'BAL': 'Baltimore'}}, {'1998': {'BAL': ['', 'Balt. Orioles']}},
                {'1998': {'BAL': ['Baltimore Orioles']}}, {'1998': {'BAL': [1, 'Balt. Orioles']}}):
        assert names(teamnames.apply(a, bad)) == ['Balt. Orioles']


def test_load(tmp_path):
    p = tmp_path / 'teamnames.json'
    assert teamnames.load(str(p)) == {}
    p.write_text('[1, 2]')
    assert teamnames.load(str(p)) == {}
    p.write_text('{not json')
    assert teamnames.load(str(p)) == {}
    p.write_text(json.dumps(TABLE))
    assert teamnames.load(str(p)) == TABLE
