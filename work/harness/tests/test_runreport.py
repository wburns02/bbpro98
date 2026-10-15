"""Tests for runreport.py (log text only; no game files)."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'harness'))
import runreport  # noqa: E402

LOG = '\n'.join([
    "== start 01:20:44",
    "loading lane",
    '{"demographics": "loaded", "year": 2027, "rostered": 1283, "mean_age": 28.46, "le25": 290, "ge33": 174, "fa": 312, "retired": 189, "players": 1784, "t": "00:02:10"}',
    '{"round": 1, "progress": 3, "of": 27, "dticks": 400, "write_age_s": 0.1, "trace_age_s": 0.2, "t": "00:05:00"}',
    '{"round": 2, "progress": 9, "of": 27, "verdict": "ok", "dticks": 380, "write_age_s": 0.1, "trace_age_s": 0.2, "t": "00:08:00"}',
    '{"round": 3, "progress": 15, "of": 27, "verdict": "busy", "dticks": 900, "write_age_s": 0.4, "trace_age_s": 0.9, "t": "00:12:00"}',
    '{"round": 4, "played": 9, "of": 27, "stop": 1, "t": "00:15:00"}',
    "Traceback (most recent call last):",
    '  File "x.py", line 1, in <module>',
    "ValueError: boom",
    '{"season": "lah2026", "done": true, "played": 54, "rounds": 27, "stops": 1, "t": "00:20:00"}',
    '{"demographics": 0, "year": 2028, "rostered": 1313, "mean_age": 28.7, "le25": 292, "ge33": 198, "fa": 313, "retired": 296, "players": 1922, "t": "01:17:30"}',
    '{"postseason": "waiting", "verdict": "busy", "t": "01:18:00"}',
    '{"postseason": "stale_update_box", "t": "01:19:00"}',
    '{"postseason": "champion", "t": "01:21:00"}',
    '{"season": "mid", "done": false, "timeout": true, "t": "01:22:00"}',
    '{"season": null, "champion": null, "error": "stuck", "at": "mid", "t": "01:23:00"}',
    '{"round": 5, "progress": 21, "of": 27, "verdict": "ok", "dticks": 350, "write_age_s": 0.0, "trace_age_s": 0.1, "t": "01:24:00"}',
    '{"postseason": "sim", "t": "01:25:00"}',
    '{"season": 2028, "champion": "Cubs", "runner_up": "Yankees", "series": "4-2", "complete": true, "at": 0, "t": "01:26:00"}',
    '{"round": 9, "played": 27, "of": 27, "stop": 2, "t": "01:27:00"}',
    '{"round": 10, "progress": 24, "of": 2',
])


def test_parse_skips_non_json():
    lines = runreport.parse(LOG)
    assert len(lines) == 16
    assert all(isinstance(o, dict) for o in lines)
    assert lines[0]['demographics'] == 'loaded'
    assert lines[-1]['t'] == '01:27:00'


def test_parse_never_raises():
    for text in ('', 'junk', '{', '{"a":', '{"a": 1}', '}\n{"b": 2}', '\x00{]}'):
        assert isinstance(runreport.parse(text), list)


def test_summary_fields():
    s = runreport.summary(runreport.parse(LOG))
    assert [r['k'] for r in s['demographics']] == ['loaded', 0]
    d0, d1 = s['demographics']
    assert d0['step'] is None
    assert d0['year'] == 2027
    assert d0['rostered'] == 1283
    assert d0['mean_age'] == 28.46
    assert d0['le25'] == 290
    assert d0['ge33'] == 174
    assert d0['fa'] == 312
    assert d0['retired'] == 189
    assert d0['players'] == 1784
    assert d1['step'] == 0.24
    assert d1['year'] == 2028
    assert d1['pitchers_min'] is None
    assert len(s['champions']) == 2
    c0, c1 = s['champions']
    assert c0 == {'at': 'mid', 'season': None, 'champion': None, 'runner_up': None,
                  'series': None, 'error': 'stuck'}
    assert c1 == {'at': 0, 'season': 2028, 'champion': 'Cubs', 'runner_up': 'Yankees',
                  'series': '4-2', 'error': None}
    assert len(s['seasons']) == 2
    s0, s1 = s['seasons']
    assert s0 == {'stem': 'lah2026', 'done': True, 'played': 54, 'rounds': 27,
                  'stops': 1, 'timeout': False, 'wrong_association': False}
    assert s1['stem'] == 'mid' and s1['done'] is False and s1['timeout'] is True
    assert s['verdicts'] == {'ok': 2, 'busy': 2}
    assert s['postseason'] == {'waiting': 1, 'stale_update_box': 1, 'champion': 1, 'sim': 1}
    assert s['stops'] == 2
    assert s['first'] == '00:02:10'
    assert s['last'] == '01:27:00'


def test_summary_empty():
    s = runreport.summary([])
    assert s == {'demographics': [], 'champions': [], 'seasons': [], 'verdicts': {},
                 'postseason': {}, 'stops': 0, 'first': None, 'last': None}


def test_render_rows():
    s = runreport.summary(runreport.parse(LOG))
    r = runreport.render(s)
    assert '\x1b' not in r
    assert 'Demographics' in r and 'Champions' in r and 'Seasons' in r
    assert 'Verdicts' in r and 'Postseason' in r
    assert '28.46' in r and '+0.24' in r
    assert '2027  1283' in r or ('  2027' in r and '1283' in r)
    assert '2028 Cubs over Yankees 4-2' in r
    assert 'error: stuck' in r
    assert 'lah2026: done True, played 54, rounds 27, stops 1' in r
    assert 'mid: timeout' in r
    assert 'ok: 2' in r and 'busy: 2' in r
    assert 'waiting: 1' in r and 'stale_update_box: 1' in r
    assert 'Stops: 2' in r
    assert 'Span: 00:02:10 to 01:27:00' in r


def test_render_damaged_rows_dashes():
    text = '\n'.join([
        '{"demographics": true, "year": null, "rostered": 1283, "mean_age": "x", "t": "00:00:01"}',
        '{"season": "m", "champion": null, "runner_up": null, "series": null, "at": "x", "t": "00:00:02"}',
    ])
    s = runreport.summary(runreport.parse(text))
    r = runreport.render(s)
    assert '-' in r
    assert s['demographics'][0]['step'] is None
    assert s['demographics'][0]['year'] is None
    assert 'no champion yet' in r


def test_step_after_a_damaged_row_is_none():
    s = runreport.summary(runreport.parse('\n'.join([
        '{"demographics": 0, "mean_age": 28.0, "t": "00:00:01"}',
        '{"demographics": 1, "mean_age": "x", "t": "00:00:02"}',
        '{"demographics": 2, "mean_age": 28.5, "t": "00:00:03"}',
        '{"demographics": 3, "mean_age": 28.75, "t": "00:00:04"}',
    ])))
    assert [r['step'] for r in s['demographics']] == [None, None, None, 0.25]


def test_champion_error_row_renders_the_error():
    s = runreport.summary(runreport.parse(
        '{"season": null, "champion": null, "error": "torn", "at": 1, "t": "00:00:01"}'))
    assert 'error: torn' in runreport.render(s)


def test_bool_is_not_number():
    s = runreport.summary(runreport.parse(
        '{"demographics": 1, "mean_age": true, "t": "00:00:01"}'))
    assert s['demographics'][0]['step'] is None
    assert s['demographics'][0]['mean_age'] is True


def test_cli_json_and_missing(tmp_path, capsys):
    log = tmp_path / 'run.log'
    log.write_text(LOG)
    p = runreport.__file__
    out = subprocess.run([sys.executable, p, str(log)],
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert 'Demographics' in out.stdout
    j = subprocess.run([sys.executable, p, str(log), '--json'],
                       capture_output=True, text=True)
    s = json.loads(j.stdout)
    assert s['stops'] == 2
    assert s['first'] == '00:02:10'
    missing = subprocess.run([sys.executable, p, str(tmp_path / 'no.log')],
                             capture_output=True, text=True)
    assert missing.returncode == 2
    assert 'runreport:' in missing.stderr
    assert str(tmp_path / 'no.log') in missing.stderr


def test_render_no_champion_lines_says_none():
    r = runreport.render(runreport.summary(runreport.parse('{"demographics": 0, "year": 2028, "t": "00:00:01"}')))
    assert r.split('Champions\n', 1)[1].startswith('none\n')
