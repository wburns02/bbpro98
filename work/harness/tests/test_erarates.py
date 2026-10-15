"""Tests for erarates.py: synthetic season lines and an in-memory Lahman Teams table; no game, DAT file or database."""
import json
import os
import sqlite3
import subprocess
import sys

import pytest

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HARNESS)
import erarates  # noqa: E402


def bat(ab, h, hr=0, bb=0, so=0, r=0, g=100):
    return dict(ab=ab, h=h, hr=hr, bb=bb, so=so, r=r, g=g)


def teams_db(rows):
    """In-memory Teams table; rows are (yearID, lgID, AB, H, HR, BB, SO, R, G)."""
    con = sqlite3.connect(':memory:')
    con.execute('create table Teams (yearID int, lgID text, AB int, H int, HR int, BB int, SO int, R int, G int)')
    con.executemany('insert into Teams values (?,?,?,?,?,?,?,?,?)', rows)
    return con


REAL = [(1996, 'AL', 5000, 1325, 150, 450, 800, 700, 162), (1996, 'NL', 5000, 1325, 150, 450, 900, 650, 162),
        (1995, 'AL', 4000, 1000, 100, 300, None, 500, 144)]


# ---- totals ------------------------------------------------------------------

def test_sim_totals_sums_players_only():
    lines = {'bat': {5: bat(999, 999), 99: bat(999, 999), 100: bat(100, 30, 4, 10, 20, 15, 50),
                     101: bat(200, 50, 6, 20, 40, 25, 60)}, 'pit': {100: {'ab': 1}}}
    assert erarates.sim_totals(lines) == {'ab': 300, 'h': 80, 'hr': 10, 'bb': 30, 'so': 60, 'r': 40, 'g': 110}
    assert erarates.sim_totals({'bat': {}, 'pit': {}}) == dict.fromkeys(erarates.SIM_KEYS, 0)
    assert erarates.sim_totals({'bat': {100: {'ab': 4}}})['h'] == 0


def test_real_totals_sums_and_filters_leagues():
    con = teams_db(REAL)
    both = erarates.real_totals(con, 1996)
    assert both == {'ab': 10000, 'h': 2650, 'hr': 300, 'bb': 900, 'so': 1700, 'r': 1350, 'g': 324, 'so_known': True}
    al = erarates.real_totals(con, 1996, ('AL',))
    assert al['ab'] == 5000 and al['so'] == 800
    assert erarates.real_totals(con, 1996, ['AL', 'NL'])['ab'] == 10000


def test_real_totals_null_so_counts_zero_and_is_marked():
    t = erarates.real_totals(teams_db(REAL), 1995)
    assert t['so'] == 0 and t['so_known'] is False and t['ab'] == 4000
    assert erarates.rates(t)['SO/AB'] is None and erarates.rates(t)['BA'] == 0.25


def test_real_totals_no_rows():
    t = erarates.real_totals(teams_db(REAL), 1850)
    assert t['ab'] == 0 and t['so_known'] is False


# ---- rates, compare, within -------------------------------------------------

def test_rates():
    r = erarates.rates({'ab': 1000, 'h': 270, 'hr': 30, 'bb': 90, 'so': 160})
    assert r == {'BA': 0.27, 'HR/AB': 0.03, 'BB/AB': 0.09, 'SO/AB': 0.16}
    assert erarates.rates({'ab': 0, 'h': 5}) == dict.fromkeys(('BA', 'HR/AB', 'BB/AB', 'SO/AB'))


def test_compare_ratio_and_none():
    sim = {'BA': 0.27, 'HR/AB': 0.03, 'BB/AB': None, 'SO/AB': 0.16}
    real = {'BA': 0.25, 'HR/AB': 0.0, 'BB/AB': 0.09, 'SO/AB': 0.16}
    c = erarates.compare(sim, real)
    assert c['BA'] == {'sim': 0.27, 'real': 0.25, 'ratio': pytest.approx(1.08)}
    assert c['HR/AB']['ratio'] is None                      # real 0: no ratio
    assert c['BB/AB']['ratio'] is None                      # sim None
    assert c['SO/AB']['ratio'] == 1.0
    assert erarates.compare({'ab': 100, 'h': 25}, {'ab': 100, 'h': 20})['BA']['ratio'] == 1.25   # totals work too


def ratios(ba, hr, bb):
    return {n: {'sim': 1, 'real': 1, 'ratio': r} for n, r in (('BA', ba), ('HR/AB', hr), ('BB/AB', bb))}


def test_within():
    assert erarates.within(ratios(1.0, 1.05, 0.95)) == (True, [])
    assert erarates.within(ratios(1.10, 0.90, 1.0)) == (True, [])               # on the tolerance passes
    assert erarates.within(ratios(1.11, 1.0, 0.85)) == (False, ['BA', 'BB/AB'])
    assert erarates.within(ratios(1.0, None, 1.0)) == (False, ['HR/AB'])        # None is a miss
    assert erarates.within(ratios(1.0, 1.0, 1.0), names=('BA', 'SO/AB')) == (False, ['SO/AB'])   # absent is a miss
    assert erarates.within(ratios(1.2, 1.0, 1.0), tol=0.25) == (True, [])
    assert erarates.within(ratios(1.2, 1.0, 1.0), tol=0.25, names=()) == (True, [])


# ---- CLI ---------------------------------------------------------------------

def run(tmp_path, capsys, sim_lines, rows=REAL, extra=(), year='1996'):
    dat = tmp_path / 'S.DAT'
    dat.write_bytes(b'x')
    seen = []

    def load(path):
        seen.append(path)
        return sim_lines
    code = erarates.main([str(dat), '--year', year, '--db', 'unused'] + list(extra), load=load,
                         connect=lambda path: teams_db(rows))
    assert seen == [str(dat)]
    return code, capsys.readouterr()


def sim_for(ba, hr=0.03, bb=0.09, so=0.16, ab=10000):
    return {'bat': {100: bat(ab, round(ab * ba), round(ab * hr), round(ab * bb), round(ab * so))}, 'pit': {}}


def test_cli_prints_a_line_per_rate_and_exits_0(tmp_path, capsys):
    code, cap = run(tmp_path, capsys, sim_for(0.2710))
    assert code == 0
    lines = cap.out.splitlines()
    assert lines[0] == 'BA  sim .2710  real .2650  x1.02'
    assert [x.split()[0] for x in lines] == ['BA', 'HR/AB', 'BB/AB', 'SO/AB']
    assert lines[1] == 'HR/AB  sim .0300  real .0300  x1.00'


def test_cli_exit_1_when_a_rate_misses(tmp_path, capsys):
    code, cap = run(tmp_path, capsys, sim_for(0.30))
    assert code == 1 and 'x1.13' in cap.out
    code, cap = run(tmp_path, capsys, sim_for(0.30), extra=['--tol', '0.2'])
    assert code == 0


def test_cli_leagues_filter(tmp_path, capsys):
    rows = [(1996, 'AL', 5000, 1500, 150, 450, 800, 700, 162), (1996, 'NL', 5000, 1000, 150, 450, 900, 650, 162)]
    code, cap = run(tmp_path, capsys, sim_for(0.30), rows=rows, extra=['--leagues', 'al'])
    assert code == 0 and cap.out.startswith('BA  sim .3000  real .3000  x1.00')
    code, cap = run(tmp_path, capsys, sim_for(0.30), rows=rows)
    assert code == 1


def test_cli_json(tmp_path, capsys):
    code, cap = run(tmp_path, capsys, sim_for(0.30), extra=['--json'])
    obj = json.loads(cap.out)
    assert code == 1 and obj['ok'] is False and obj['misses'] == ['BA']
    assert obj['sim']['ab'] == 10000 and obj['real']['ab'] == 10000
    assert obj['compare']['BA']['ratio'] == pytest.approx(0.30 / 0.265)


def test_cli_unknown_so_prints_na_and_is_not_judged(tmp_path, capsys):
    code, cap = run(tmp_path, capsys, sim_for(0.25, hr=0.025, bb=0.075, so=0.16), year='1995')
    assert code == 0
    assert cap.out.splitlines()[3] == 'SO/AB  sim .1600  real n/a  n/a'


def test_cli_none_ratio_is_a_miss(tmp_path, capsys):
    rows = [(1996, 'AL', 5000, 1325, 0, 450, 800, 700, 162)]     # no real home runs: HR/AB ratio is None
    code, cap = run(tmp_path, capsys, sim_for(0.265), rows=rows)
    assert code == 1


def test_cli_bad_input_exits_2(tmp_path, capsys):
    code, cap = run(tmp_path, capsys, sim_for(0.265), year='1850')                 # no Lahman teams that year
    assert code == 2 and 'no Lahman teams' in cap.err
    assert erarates.main([str(tmp_path / 'missing.DAT'), '--year', '1996']) == 2
    with pytest.raises(SystemExit) as e:
        erarates.main([str(tmp_path / 'x.DAT')])                                   # --year is required
    assert e.value.code == 2
    dat = tmp_path / 'S.DAT'
    dat.write_bytes(b'x')

    def boom(path):
        raise ValueError('torn file')
    assert erarates.main([str(dat), '--year', '1996'], load=boom) == 2
    assert 'torn file' in capsys.readouterr().err
    assert erarates.main([str(dat), '--year', '1996', '--db', str(tmp_path / 'absent.sqlite')],
                         load=lambda p: sim_for(0.265)) == 2                       # read only: absent is an error


def test_open_db_is_read_only(tmp_path):
    p = tmp_path / 'l.sqlite'
    con = sqlite3.connect(p)
    con.execute('create table Teams (yearID int)')
    con.commit()
    con.close()
    ro = erarates.open_db(str(p))
    assert ro.execute('select count(*) from Teams').fetchone() == (0,)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute('insert into Teams values (1)')
    with pytest.raises(sqlite3.OperationalError):
        erarates.open_db(str(tmp_path / 'absent.sqlite'))


def test_script_exits_2_without_arguments_and_imports_no_game_module():
    script = os.path.join(HARNESS, 'erarates.py')
    p = subprocess.run([sys.executable, script], capture_output=True, text=True)
    assert p.returncode == 2
    code = ('import sys; sys.path.insert(0, %r); import erarates, referee; '
            'bad = [m for m in ("gamedata", "ctree", "stats", "league") if m in sys.modules]; print(bad)' % HARNESS)
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert p.stdout.strip() == '[]', p.stderr
