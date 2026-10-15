"""Tests for referee.py: fake run logs, fake rates, placeholder DAT files in tmp_path and an in-memory Lahman table.
No game, Wine, DAT parsing or database file."""
import json
import os
import re
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import referee  # noqa: E402

RATES = {'BA': 0.27, 'HR/AB': 0.03, 'BB/AB': 0.09, 'SO/AB': 0.16}
STEM = '30L2025'


def demo(k, age=28.5, rmin=40, pmin=18, year=None):
    return {'demographics': k, 'year': 2025 + k if year is None else year, 'rostered': 1100, 'mean_age': age,
            'roster_min': rmin, 'pitchers_min': pmin, 't': '00:00:00'}


def play(of=2430, played=None, done=True):
    return [{'round': 1, 'progress': of // 3, 'of': of}, {'round': 2, 'progress': of - 10, 'of': of},
            {'season': STEM, 'done': done, 'played': of if played is None else played, 'rounds': 2, 'stops': 0}]


def run_log(n=10, ages=None, rmin=None, pmin=None, over=None):
    """The seasonloop shape: a baseline demographics line, then per season its demographics and rounds, then the
    post-run measurement. ages / rmin / pmin map season -> value; over maps season -> kwargs for play()."""
    ages, rmin, pmin, over = ages or {}, rmin or {}, pmin or {}, over or {}
    lines = [dict(demo('loaded', age=99.0, rmin=1, pmin=1, year=2024))]
    for k in range(n):
        lines.append(demo(k, ages.get(k, 28.5), rmin.get(k, 40), pmin.get(k, 18)))
        lines += play(**over.get(k, {}))
    lines.append(demo(n, age=60.0, rmin=2, pmin=2))
    return lines


def judge(lines=None, rates=None, crashes=(), bands=None, ref=None, n=10):
    lines = run_log(n) if lines is None else lines
    rates = [dict(RATES) for _ in range(n)] if rates is None else rates
    return referee.judge(lines, rates, list(crashes), bands or {}, ref)


def only(res, word):
    return [f for f in res['fails'] if word in f]


# ---- the clean run and the bands -----------------------------------------------

def test_clean_run_passes():
    res = judge()
    assert res['verdict'] == 'PASS' and res['fails'] == []
    assert len(res['rows']) == 10                      # the baseline and the post-run measurement are not seasons
    r = res['rows'][3]
    assert (r['k'], r['year'], r['mean_age'], r['drift'], r['roster_min'], r['pitchers_min']) == (3, 2028, 28.5, 0.0, 40, 18)
    assert r['BA'] == 0.27 and r['played'] == 2430 and r['of'] == 2430 and r['done'] is True


def test_result_keys():
    assert sorted(judge()) == ['fails', 'rows', 'verdict']


def test_age_drift_over_the_band_fails():
    res = judge(run_log(ages={0: 28.5, 6: 28.81}))
    assert res['verdict'] == 'FAIL' and only(res, 'age drift') and 'season 6' in only(res, 'age drift')[0]
    assert res['rows'][6]['drift'] == pytest.approx(0.31)
    assert judge(run_log(ages={4: 28.2}))['verdict'] == 'PASS'                      # exactly 0.3 down passes
    assert judge(run_log(ages={4: 28.1}))['verdict'] == 'FAIL'                      # drift is two sided
    assert judge(run_log(ages={6: 28.81}), bands={'age_drift': 0.5})['verdict'] == 'PASS'


def test_drift_is_measured_from_the_first_season_not_the_baseline():
    lines = run_log(ages={k: 31.0 for k in range(10)})                              # baseline says 99.0
    assert judge(lines)['verdict'] == 'PASS'


def test_roster_min_below_the_band_fails():
    res = judge(run_log(rmin={5: 35}))
    assert res['verdict'] == 'FAIL' and 'roster_min 35 in season 5' in only(res, 'roster_min')[0]
    assert judge(run_log(rmin={5: 36}))['verdict'] == 'PASS'
    assert judge(run_log(rmin={5: 35}), bands={'roster_min': 30})['verdict'] == 'PASS'


def test_pitchers_min_below_the_band_fails():
    res = judge(run_log(pmin={2: 14}))
    assert res['verdict'] == 'FAIL' and only(res, 'pitchers_min')
    assert judge(run_log(pmin={2: 15}))['verdict'] == 'PASS'


def test_missing_demographic_values_fail():
    lines = [{k: v for k, v in o.items() if k not in ('roster_min', 'mean_age')} for o in run_log()]
    res = judge(lines)
    assert only(res, 'roster_min: none') and only(res, 'age drift: no mean_age')


def test_unfinished_season_fails():
    res = judge(run_log(over={4: {'done': False, 'played': 1200}}))
    assert res['verdict'] == 'FAIL' and 'season 4' in only(res, 'did not finish')[0]
    assert res['rows'][4]['done'] is False
    assert any('seasons: 9 completed' in f for f in res['fails'])


def test_played_below_of_fails():
    res = judge(run_log(over={7: {'played': 2400}}))
    assert res['verdict'] == 'FAIL' and 'season 7: played 2400 of 2430' in res['fails'][0]
    assert judge(run_log(over={7: {'played': 2430}}))['verdict'] == 'PASS'
    assert judge(run_log(over={7: {'played': 2500}}))['verdict'] == 'PASS'


def test_the_largest_of_in_the_season_counts():
    lines = run_log()
    lines.insert(lines.index(next(o for o in lines if o.get('demographics') == 1)) + 1,
                 {'round': 9, 'progress': 5, 'of': 3000})
    res = judge(lines)
    assert 'season 1: played 2430 of 3000 games' in res['fails']


def test_a_loaded_mid_season_that_did_not_finish_fails():
    lines = run_log()
    lines.insert(1, {'season': 'mid', 'done': False, 'timeout': True})
    res = judge(lines)
    assert res['verdict'] == 'FAIL' and only(res, 'baseline season mid')
    assert len(res['rows']) == 10


def test_fewer_seasons_than_the_band_fails():
    res = judge(run_log(9), n=9)
    assert res['verdict'] == 'FAIL' and res['fails'] == ['seasons: 9 completed, need 10']
    assert judge(run_log(9), n=9, bands={'seasons': 9})['verdict'] == 'PASS'
    assert judge(run_log(0), rates=[], n=0)['verdict'] == 'FAIL'
    assert judge([], rates=[], n=0)['verdict'] == 'FAIL'


def test_missing_dat_fails():
    rates = [dict(RATES) for _ in range(10)]
    rates[3] = None
    res = judge(rates=rates)
    assert res['verdict'] == 'FAIL' and res['fails'] == ['season 3: no readable Stats DAT']
    assert res['rows'][3]['BA'] is None
    rates[0] = None                                                                # the first one missing: season 1 is the reference
    assert len(only(judge(rates=rates), 'no readable')) == 2


def test_crash_evidence_fails():
    res = judge(crashes=['bbtrace.log: 12:00 CRASH at LINEUP+0x116e0'])
    assert res['verdict'] == 'FAIL' and 'LINEUP+0x116e0' in only(res, 'crash')[0] and '1 line' in res['fails'][0]
    lines = run_log() + [{'crash': 'LINEUP+0x116e0', 't': '09:00:00'}]
    assert judge(lines)['verdict'] == 'FAIL'
    assert judge(run_log() + [{'crash': False}])['verdict'] == 'PASS'


# ---- rates ------------------------------------------------------------------------

def test_rates_are_held_to_the_first_season():
    rates = [dict(RATES) for _ in range(10)]
    rates[4] = dict(RATES, BA=0.27 * 1.09, **{'BB/AB': 0.09 * 0.92})
    assert judge(rates=rates)['verdict'] == 'PASS'
    rates[4]['BA'] = 0.27 * 1.2
    res = judge(rates=rates)
    assert res['verdict'] == 'FAIL' and 'season 4: BA x1.20 outside 10% of first' in res['fails']
    assert judge(rates=rates, bands={'rate_tol': 0.25})['verdict'] == 'PASS'
    rates[4] = dict(RATES, **{'SO/AB': 0.5})                                       # strikeouts are not judged
    assert judge(rates=rates)['verdict'] == 'PASS'


def test_a_none_rate_is_a_miss():
    rates = [dict(RATES) for _ in range(10)]
    rates[2] = dict.fromkeys(RATES)
    assert judge(rates=rates)['verdict'] == 'FAIL'


REAL = {'BA': 0.265, 'HR/AB': 0.030, 'BB/AB': 0.088, 'SO/AB': 0.17}


def test_real_reference_is_used_when_given():
    bands = {'rate_ref': 'real:1996'}
    assert judge(bands=bands, ref=REAL)['verdict'] == 'PASS'
    far = dict(REAL, BA=0.2)                                                      # every season .27 against a .200 league
    res = judge(bands=bands, ref=far)
    assert res['verdict'] == 'FAIL' and len(only(res, 'outside 10% of real:1996')) == 10
    assert only(judge(bands=bands), 'no real:1996 reference')                      # the caller must supply it
    assert judge(bands={'rate_ref': 'first'}, ref=far)['verdict'] == 'PASS'        # first ignores ref


def test_bands_are_checked():
    for bad in ({'nope': 1}, {'rate_ref': 'real'}, {'rate_ref': 'real:96'}, {'seasons': 'ten'}, {'age_drift': -1}):
        with pytest.raises(ValueError):
            judge(bands=bad)
    assert referee.merge_bands({'seasons': 3})['age_drift'] == 0.3


def test_split_baseline_and_trailing_measurement():
    segs = referee.season_segments(run_log(3))
    assert [s['demo']['demographics'] for s in segs] == [0, 1, 2]
    only_demo = [demo(0, 28.0), demo(1, 28.1)]                                     # no season objects at all: both stay
    assert len(referee.season_segments(only_demo)) == 2


# ---- the table ----------------------------------------------------------------------

def test_render():
    out = referee.render(judge())
    rows = out.splitlines()
    assert rows[0].split()[:4] == ['season', 'year', 'mean', 'age'] and len(rows) == 12
    assert rows[1].split() == ['0', '2025', '28.50', '+0.00', '40', '18', '.2700', '.0300', '.0900', '2430/2430']
    assert rows[-1] == 'REFEREE PASS'
    bad = referee.render(judge(crashes=['x CRASH'], rates=[None] + [dict(RATES)] * 9))
    assert bad.splitlines()[-1].startswith('REFEREE FAIL: season 0: no readable Stats DAT; ')
    assert bad.splitlines()[1].split()[6] == '-'


# ---- evidence on disk and the CLI --------------------------------------------------------

def make_out(tmp_path, n=10, skip=(), crash=None):
    out = tmp_path / 'out'
    for k in range(n):
        d = out / ('complete_%d' % k) / 'Stats'
        d.mkdir(parents=True)
        if k not in skip:
            (d / (STEM + '.DAT')).write_bytes(b'x')
    if crash:
        (out / crash[0]).write_text('ok line\n' + crash[1] + '\n')
    return str(out)


def loader(rates_by_k=None):
    """A DAT reader: the season index comes from the path; lines give BA .27, HR/AB .03, BB/AB .09."""
    def load(path):
        k = int(re.search(r'complete_(\d+)', path).group(1))
        if rates_by_k and k in rates_by_k:
            ba = rates_by_k[k]
        else:
            ba = 0.27
        return {'bat': {100: dict(ab=10000, h=round(10000 * ba), hr=300, bb=900, so=1600, r=0, g=0)}, 'pit': {}}
    return load


def write_log(tmp_path, lines):
    p = tmp_path / 'run.log'
    p.write_text('== start\n' + '\n'.join(json.dumps(o) for o in lines) + '\nTraceback junk\n')
    return str(p)


def teams_db(path):
    con = sqlite3.connect(':memory:')
    con.execute('create table Teams (yearID int, lgID text, AB int, H int, HR int, BB int, SO int, R int, G int)')
    if path != 'empty':
        con.execute("insert into Teams values (1996, 'AL', 10000, 2650, 300, 880, 1700, 1300, 162)")
    return con


def test_find_crashes_reads_both_trace_files_and_subdirs(tmp_path):
    out = make_out(tmp_path)
    with open(os.path.join(out, 'bbtrace.log'), 'w') as fh:
        fh.write('fine\n12:00 CRASH one\ncrash lowercase\n')
    with open(os.path.join(out, 'complete_3', 'bbtrace.1.log'), 'w') as fh:
        fh.write('CRASH two\n')
    with open(os.path.join(out, 'other.log'), 'w') as fh:
        fh.write('CRASH not scanned\n')
    got = referee.find_crashes(out)
    assert len(got) == 2 and 'one' in got[0] and got[1].startswith(os.path.join('complete_3', 'bbtrace.1.log'))
    assert referee.find_crashes(out, limit=1) == [got[0]]
    assert referee.find_crashes(str(tmp_path / 'absent')) == []


def test_evaluate_clean_run(tmp_path):
    res = referee.evaluate(open(write_log(tmp_path, run_log())).read(), make_out(tmp_path), STEM, load=loader())
    assert res['verdict'] == 'PASS', res['fails']
    assert res['rows'][9]['BA'] == 0.27


def test_evaluate_missing_and_unreadable_dats_and_crash_files(tmp_path):
    text = open(write_log(tmp_path, run_log())).read()
    out = make_out(tmp_path, skip=(2,), crash=('bbtrace.log', 'CRASH in LINEUP'))
    res = referee.evaluate(text, out, STEM, load=loader())
    assert res['verdict'] == 'FAIL'
    assert only(res, 'season 2: no readable') and only(res, 'crash evidence')

    def torn(path):
        if 'complete_5' in path:
            raise ValueError('torn')
        return loader()(path)
    out = make_out(tmp_path / 'b')
    res = referee.evaluate(text, out, STEM, load=torn)
    assert res['fails'] == ['season 5: no readable Stats DAT']


def test_evaluate_real_reference_uses_the_injected_database(tmp_path):
    text = open(write_log(tmp_path, run_log())).read()
    out = make_out(tmp_path)
    seen = []

    def connect(path):
        seen.append(path)
        return teams_db(path)
    bands = {'rate_ref': 'real:1996'}
    res = referee.evaluate(text, out, STEM, bands, db='/x/lahman.sqlite', load=loader(), connect=connect)
    assert seen == ['/x/lahman.sqlite'] and res['verdict'] == 'PASS', res['fails']
    far = referee.evaluate(text, out, STEM, bands, load=loader({3: 0.35}), connect=connect)    # real BA is .265
    assert far['verdict'] == 'FAIL' and 'season 3: BA' in only(far, 'real:1996')[0]
    assert referee.evaluate(text, out, STEM, {'rate_ref': 'first'}, load=loader({3: 0.35}), connect=connect)['verdict'] == 'FAIL'
    with pytest.raises(ValueError, match='no Lahman teams'):
        referee.evaluate(text, out, STEM, {'rate_ref': 'real:1996'}, load=loader(), connect=lambda p: teams_db('empty'))


def test_cli_exit_codes_and_output(tmp_path, capsys):
    log = write_log(tmp_path, run_log())
    out = make_out(tmp_path)
    assert referee.main([log, out, '--stem', STEM], load=loader()) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[-1] == 'REFEREE PASS' and printed[0].startswith('season')
    assert referee.main([log, out, '--stem', STEM], load=loader({4: 0.4})) == 1
    assert capsys.readouterr().out.splitlines()[-1].startswith('REFEREE FAIL: season 4: BA')
    # bands file: a looser tolerance passes the same run; --json prints the result
    bands = tmp_path / 'bands.json'
    bands.write_text(json.dumps({'rate_tol': 0.6}))
    assert referee.main([log, out, '--stem', STEM, '--bands', str(bands), '--json'], load=loader({4: 0.4})) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj['verdict'] == 'PASS' and len(obj['rows']) == 10


def test_cli_real_ref_through_the_bands_file(tmp_path, capsys):
    log = write_log(tmp_path, run_log())
    out = make_out(tmp_path)
    bands = tmp_path / 'bands.json'
    bands.write_text(json.dumps({'rate_ref': 'real:1996'}))
    args = [log, out, '--stem', STEM, '--bands', str(bands), '--db', 'whatever']
    assert referee.main(args, load=loader(), connect=teams_db) == 0
    assert referee.main(args, load=loader({1: 0.2}), connect=teams_db) == 1
    capsys.readouterr()
    assert referee.main(args, load=loader(), connect=lambda p: teams_db('empty')) == 2
    assert 'no Lahman teams for 1996' in capsys.readouterr().err
    assert referee.main(args, load=loader(), connect=lambda p: sqlite3.connect(os.path.join(p, 'no', 'such'))) == 2


def test_cli_bad_input_exits_2(tmp_path, capsys):
    log = write_log(tmp_path, run_log())
    out = make_out(tmp_path)
    assert referee.main([str(tmp_path / 'absent.log'), out, '--stem', STEM], load=loader()) == 2
    assert referee.main([log, str(tmp_path / 'absent'), '--stem', STEM], load=loader()) == 2
    bad = tmp_path / 'bad.json'
    bad.write_text('{"seasons": ')
    assert referee.main([log, out, '--stem', STEM, '--bands', str(bad)], load=loader()) == 2
    bad.write_text('{"mystery": 1}')
    assert referee.main([log, out, '--stem', STEM, '--bands', str(bad)], load=loader()) == 2
    assert 'mystery' in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        referee.main([log, out], load=loader())                                      # --stem is required
    assert e.value.code == 2

