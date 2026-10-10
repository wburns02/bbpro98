"""salarytable: the fit on a small synthetic database. The world has one priced row per role and class in 1986, rows that
must be left out, and salaries outside the years; the medians and cells are worked out by hand in the comments."""
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lahman import salarytable as S  # noqa: E402


def world():
    """Salary year 1986, priced on 1985. Batters (pre, arb, fa) are b1, b2, b3: OPS .498, .854, 1.030. Pitchers (pre, arb,
    fa) are p1, p2, p3: ERA 9.00, 5.40, 2.70. b4 (99 AB) and p4 (89 outs) fall short; u1 has no 1985 games; u5's salary
    is NULL. b1's 1985 is two stints (60 and 40 AB), which make the 100 AB he needs; p1 has G_p at exactly half of G_all.
    Salaries of 1986: 50k, 100k, 200k, 300k, 400k, 500k, 600k, 900k, 1000k, so the median is 400k. 1984 and 2017 are out
    of range."""
    apps = [('b1', 1984, 60, 0), ('b1', 1985, 60, 0), ('b1', 1985, 40, 0)]
    apps += [('b2', y, 150, 0) for y in range(1981, 1986)] + [('b2', 1984, 10, 0)]
    apps += [('b3', y, 150, 0) for y in range(1980, 1986)]
    apps += [('b4', 1985, 100, 0), ('p1', 1984, 40, 40), ('p1', 1985, 40, 20)]
    apps += [('p2', y, 40, 40) for y in range(1981, 1986)] + [('p2', 1984, 5, 5)]
    apps += [('p3', y, 40, 40) for y in range(1980, 1986)] + [('p4', 1985, 40, 40)]
    bat = [('b1', 1985, 60, 12, 2, 0, 1, 3, 0, 0), ('b1', 1985, 40, 8, 1, 0, 0, 2, 0, 0),
           ('b2', 1985, 500, 150, 30, 2, 20, 50, 5, 5), ('b3', 1985, 600, 200, 40, 5, 40, 80, 5, 5),
           ('b4', 1985, 99, 30, 5, 0, 4, 10, 0, 0)]
    pit = [('p1', 1985, 90, 30), ('p2', 1985, 300, 60), ('p3', 1985, 600, 60), ('p4', 1985, 89, 0)]
    sal = [(1986, 'b1', 100000), (1986, 'b2', 300000), (1986, 'b3', 900000), (1986, 'b4', 500000),
           (1986, 'p1', 200000), (1986, 'p2', 400000), (1986, 'p3', 1000000), (1986, 'p4', 600000),
           (1986, 'u1', 50000), (1986, 'u5', None), (1984, 'u2', 9000000), (2017, 'u3', 9000000)]
    return {'apps': apps, 'bat': bat, 'pit': pit, 'sal': sal}


def make_db(path, w):
    """A synthetic Lahman database with the four tables the fit reads, filled from w; returns its path."""
    con = sqlite3.connect(str(path))
    con.executescript('''
        CREATE TABLE appearances (playerID TEXT, yearID INT, G_all INT, G_p INT);
        CREATE TABLE batting (playerID TEXT, yearID INT, AB INT, H INT, "2B" INT, "3B" INT, HR INT, BB INT, HBP INT,
                              SF INT);
        CREATE TABLE pitching (playerID TEXT, yearID INT, IPouts INT, ER INT);
        CREATE TABLE salaries (yearID INT, playerID TEXT, salary INT);
    ''')
    con.executemany('INSERT INTO appearances VALUES (?,?,?,?)', w['apps'])
    con.executemany('INSERT INTO batting VALUES (?,?,?,?,?,?,?,?,?,?)', w['bat'])
    con.executemany('INSERT INTO pitching VALUES (?,?,?,?)', w['pit'])
    con.executemany('INSERT INTO salaries VALUES (?,?,?)', w['sal'])
    con.commit()
    con.close()
    return str(path)


@pytest.fixture
def db(tmp_path):
    return make_db(tmp_path / 'lahman.sqlite', world())


def open_db(path):
    return sqlite3.connect(path)


@pytest.mark.parametrize('years, year, expected', [
    ({1983, 1984, 1985, 1990}, 1986, 3),     # 1990 is after the salary year
    ({1985}, 1986, 1),
    (set(), 1986, 0),
])
def test_service_counts_seasons_before_the_salary_year(years, year, expected):
    assert S.service(years, year) == expected


@pytest.mark.parametrize('service, cls', [(0, 'pre'), (2, 'pre'), (3, 'arb'), (5, 'arb'), (6, 'fa'), (12, 'fa')])
def test_class_from_service(service, cls):
    assert S.class_of(service) == cls


def test_a_season_counts_once_however_many_stints_it_has(db):
    """b2 has a second 1984 row (a stint); he is arbitration by 5 distinct seasons, not by 6 rows."""
    con = open_db(db)
    rows = {r['pid']: r for r in S.priced(con, S.salaries(con))}
    con.close()
    assert rows['b2']['cls'] == 'arb' and rows['p2']['cls'] == 'arb'


@pytest.mark.parametrize('g_all, g_p, expected', [(100, 50, 'pit'), (100, 49, 'bat'), (40, 40, 'pit'), (1, 0, 'bat')])
def test_role_is_pitcher_at_half_his_games(g_all, g_p, expected):
    assert S.role(g_all, g_p) == expected


def test_playing_time_cutoffs_and_roles_of_the_priced_rows(db):
    """b4 (99 AB) and p4 (89 outs) are short; u1 has no games the season before. b1 reaches 100 AB through two stints,
    and p1 (90 outs) is the first pitcher kept by the outs cutoff."""
    con = open_db(db)
    rows = S.priced(con, S.salaries(con))
    con.close()
    assert {r['pid']: (r['role'], r['cls']) for r in rows} == {
        'b1': ('bat', 'pre'), 'b2': ('bat', 'arb'), 'b3': ('bat', 'fa'),
        'p1': ('pit', 'pre'), 'p2': ('pit', 'arb'), 'p3': ('pit', 'fa')}


@pytest.mark.parametrize('rank0, n, expected', [
    (0, 1, 1), (0, 10, 1), (4, 10, 5), (9, 10, 10), (1, 3, 4), (2, 3, 7), (5, 12, 5), (11, 12, 10),
])
def test_decile_formula(rank0, n, expected):
    assert S.decile(rank0, n) == expected


def test_deciles_rank_by_score_within_season_and_role():
    bats = [{'year': 1986, 'role': 'bat', 'pid': 'b%d' % i, 'score': i / 10} for i in range(10)]
    rows = bats + [{'year': 1986, 'role': 'pit', 'pid': 'p', 'score': 5.0}]
    out = {r['pid']: r['decile'] for r in S.deciles(rows)}
    assert [out['b%d' % i] for i in range(10)] == list(range(1, 11))
    assert out['p'] == 1                              # a role of one row is decile 1


def test_a_tie_in_score_goes_to_the_lower_pid():
    rows = [{'year': 1986, 'role': 'bat', 'pid': 'b', 'score': 1.0}, {'year': 1986, 'role': 'bat', 'pid': 'a', 'score': 1.0}]
    out = {r['pid']: r['decile'] for r in S.deciles(rows)}
    assert out == {'a': 1, 'b': 6}


def test_median_per_year_counts_every_salary_row_of_the_year(db):
    """The 1986 median is 400k over the nine rows of 1986 that have a salary, priced or not; the 1984 and 2017 rows
    and the NULL are out."""
    con = open_db(db)
    try:
        assert S.fit(con)['years'] == {'1986': 400000}
    finally:
        con.close()


def test_cells_are_the_median_ratio_and_empty_cells_take_the_nearest_filled_decile(db):
    """Each role and class has one priced row, so each has one filled decile: bat pre 100k/400k in decile 1, bat arb
    300k/400k in decile 4, bat fa 900k/400k in decile 7, and the pitchers at 200k, 400k, 1000k. Deciles below the
    filled one take it (nothing lower is filled, so the higher one, for arb and fa)."""
    con = open_db(db)
    try:
        ratio = S.fit(con)['ratio']
    finally:
        con.close()
    assert ratio['bat']['pre'] == [0.25] * 10
    assert ratio['bat']['arb'] == [0.75] * 10
    assert ratio['bat']['fa'] == [2.25] * 10
    assert ratio['pit']['pre'] == [0.5] * 10
    assert ratio['pit']['arb'] == [1.0] * 10
    assert ratio['pit']['fa'] == [2.5] * 10


@pytest.mark.parametrize('vals, out', [
    ([None, 1, None, None, 2, None, None, None, None, None], [1, 1, 1, 1, 2, 2, 2, 2, 2, 2]),
    ([None, None, 3, None, None, None, None, None, None, None], [3] * 10),
    ([1, None, None, 2, None, None, None, None, None, 5], [1, 1, 1, 2, 2, 2, 2, 2, 2, 5]),
])
def test_fill_takes_the_nearest_lower_filled_value_else_the_higher(vals, out):
    assert S.fill(vals) == out


def test_json_has_the_contract_shape_with_sorted_keys_and_indent_one(db, tmp_path):
    out = tmp_path / 'salary_table.json'
    assert S.main(['--db', db, '--out', str(out)]) is None
    text = out.read_text(encoding='utf-8')
    table = json.loads(text)
    assert set(table) == {'source', 'years', 'ratio'} and table['source'] == S.SOURCE
    assert set(table['ratio']) == {'bat', 'pit'}
    assert all(sorted(table['ratio'][r]) == ['arb', 'fa', 'pre'] for r in ('bat', 'pit'))
    assert all(len(table['ratio'][r][c]) == 10 for r in ('bat', 'pit') for c in ('pre', 'arb', 'fa'))
    assert text.startswith('{\n "ratio": {\n  "bat": {\n   "arb": [\n    0.75,\n')
    assert text.endswith('}\n')


def test_an_existing_out_is_refused_with_status_2_and_left_alone(db, tmp_path):
    out = tmp_path / 'salary_table.json'
    out.write_text('keep', encoding='utf-8')
    with pytest.raises(SystemExit) as exc:
        S.main(['--db', db, '--out', str(out)])
    assert exc.value.code == 2
    assert out.read_text(encoding='utf-8') == 'keep'


def test_a_role_and_class_with_no_priced_row_is_an_error(tmp_path):
    w = world()
    w['pit'] = []                                       # no pitcher has a 1985 line: no pitcher can be priced
    con = open_db(make_db(tmp_path / 'short.sqlite', w))
    try:
        with pytest.raises(ValueError, match='no priced rows for pit'):
            S.fit(con)
    finally:
        con.close()
    assert not os.path.exists(tmp_path / 'short.json')
