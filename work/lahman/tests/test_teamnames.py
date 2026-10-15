import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lahman import build, teamnames  # noqa: E402
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


def _db(tmp_path, rows):
    """Rows go into a tmp SQLite file: lahdb.connect() opens a URI read-only, which :memory: cannot satisfy."""
    db = str(tmp_path / 'db.sqlite')
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT, name TEXT)')
    con.executemany('INSERT INTO teams VALUES (?, ?, ?, ?)', rows)
    con.commit()
    con.close()
    return db


def _con():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT, name TEXT)')
    con.executemany('INSERT INTO teams VALUES (?, ?, ?, ?)', [
        (1871, 'NA', 'BS1', 'Boston Red Stockings'), (1872, 'NA', 'BS1', 'Boston Red Stockings'),
        (1998, 'AL', 'BAL', 'Baltimore Orioles')])
    con.commit()
    return con


def test_missing_years_complete():
    con = _con()
    assert teamnames.missing_years(teamnames.table(con), con) == []


def test_missing_years_incomplete():
    con = _con()
    assert teamnames.missing_years({'1998': {}}, con) == [1871, 1872]
    assert teamnames.missing_years({}, con) == [1871, 1872, 1998]


def test_check_missing(tmp_path, capsys):
    path = str(tmp_path / 'teamnames.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'1998': {'BAL': ['Baltimore Orioles', 'Balt. Orioles']}}, fh)
    db = _db(tmp_path, [(1871, 'NA', 'BS1', 'Boston Red Stockings'), (1872, 'NA', 'BS1', 'Boston Red Stockings'),
                        (1998, 'AL', 'BAL', 'Baltimore Orioles')])
    argv = ['--db', db, '--check', path]
    try:
        teamnames.main(argv)
    except SystemExit as e:
        assert e.code == 1
    assert capsys.readouterr().out.rstrip('\n') == 'teamnames: %s lacks 2 Lahman years: 1871-1872' % path


def test_check_covers(tmp_path, capsys):
    path = str(tmp_path / 'teamnames.json')
    rows = [(1871, 'NA', 'BS1', 'Boston Red Stockings'), (1998, 'AL', 'BAL', 'Baltimore Orioles')]
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({str(y): {} for y, _, _, _ in rows}, fh)
    db = _db(tmp_path, rows)
    argv = ['--db', db, '--check', path]
    assert teamnames.main(argv) == 0
    assert capsys.readouterr().out.rstrip('\n') == 'teamnames: %s covers every Lahman year (1871-1998)' % path


def test_check_unreadable_counts_empty(tmp_path, capsys):
    path = str(tmp_path / 'teamnames.json')
    db = _db(tmp_path, [(1998, 'AL', 'BAL', 'Baltimore Orioles')])
    argv = ['--db', db, '--check', path]
    try:
        teamnames.main(argv)                     # absent file
    except SystemExit as e:
        assert e.code == 1
    assert capsys.readouterr().out.rstrip('\n') == 'teamnames: %s lacks 1 Lahman years: 1998' % path
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('[1, 2]')                       # a JSON array is not an object
    try:
        teamnames.main(argv)
    except SystemExit as e:
        assert e.code == 1


def test_check_ranges(tmp_path, capsys):
    path = str(tmp_path / 'teamnames.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({}, fh)
    db = _db(tmp_path, [(1999, 'AL', 'KCA', 'Kansas City Athletics'), (2024, 'AL', 'SEA', 'Seattle Mariners'),
                        (2025, 'AL', 'SEA', 'Seattle Mariners')])
    try:
        teamnames.main(['--db', db, '--check', path])
    except SystemExit as e:
        assert e.code == 1
    assert capsys.readouterr().out.rstrip('\n') == 'teamnames: %s lacks 3 Lahman years: 1999, 2024-2025' % path


def _build_db(tmp_path, year):
    db = str(tmp_path / 'build.sqlite')
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE teams (yearID INT, lgID TEXT, teamID TEXT, name TEXT, divID TEXT, park TEXT, FRANCHID TEXT)')
    con.execute("INSERT INTO teams VALUES (?, 'AL', 'BAL', 'Baltimore Orioles', 'E', NULL, 'BAL')", (year,))
    con.commit()
    con.close()
    return db


def _build_argv(tmp_path, db, year):
    return ['--year', str(year), '--db', db, '--install', str(tmp_path / 'install'),
            '--templates', str(tmp_path / 'templates'), '--leagues', 'AL']


def test_build_warning_shown(tmp_path, capsys, monkeypatch):
    year = 2025
    calls = []
    monkeypatch.setattr(build, 'build', lambda *args, **kw: calls.append(args))
    db = _build_db(tmp_path, year)
    tbl = str(tmp_path / 'teamnames.json')
    with open(tbl, 'w', encoding='utf-8') as fh:
        json.dump({'2024': {}}, fh)
    monkeypatch.setattr(teamnames, 'OUT', tbl)
    assert build.main(_build_argv(tmp_path, db, year)) == 0
    out = capsys.readouterr().out
    assert 'warning: %s has no %d; League News will show 16-letter team names until work/lahman/teamnames.py is rerun' \
        % (tbl, year) in out
    assert calls == [(year, str(tmp_path / 'install'), db, None)]


def test_build_no_warning(tmp_path, capsys, monkeypatch):
    year = 2025
    calls = []
    monkeypatch.setattr(build, 'build', lambda *args, **kw: calls.append(args))
    db = _build_db(tmp_path, year)
    tbl = str(tmp_path / 'teamnames.json')
    with open(tbl, 'w', encoding='utf-8') as fh:
        json.dump({'2025': {'BAL': ['Baltimore Orioles', 'Balt. Orioles']}}, fh)
    monkeypatch.setattr(teamnames, 'OUT', tbl)
    assert build.main(_build_argv(tmp_path, db, year)) == 0
    assert 'warning' not in capsys.readouterr().out
    assert calls == [(year, str(tmp_path / 'install'), db, None)]


def test_build_no_file_no_warning(tmp_path, capsys, monkeypatch):
    year = 2025
    calls = []
    monkeypatch.setattr(build, 'build', lambda *args, **kw: calls.append(args))
    db = _build_db(tmp_path, year)
    monkeypatch.setattr(teamnames, 'OUT', str(tmp_path / 'absent.json'))
    assert build.main(_build_argv(tmp_path, db, year)) == 0
    assert 'warning' not in capsys.readouterr().out
    assert calls == [(year, str(tmp_path / 'install'), db, None)]
