"""Watcher.moves after a pass that stopped before the snapshot: last.json is written right after the log, and notes
missing from the log are written on a later pass."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watch  # noqa: E402
from test_watch import world, league, league_scan, moves_log, move_notes, LEAGUE_PLAYERS, league_player  # noqa: E402,F401


def watcher(gd, data):
    lines = []
    return watch.Watcher(str(gd), str(data), None, None, log=lines.append), lines


def errors(lines):
    return [s for s in lines if s.startswith('30L1998: ')]


def two_moves(gd, data, st):
    """A watcher past its first scan, and the roster changed so the next scan logs 'retired' (note 0) and 'signed'."""
    w, lines = watcher(gd, data)
    league_scan(w, gd, st)
    st.update(fa=set(), rosters={1: [100], 2: [200, 300, 400]})
    return w, lines


def last(data):
    return json.loads((data / '30L1998' / 'moves' / 'last.json').read_text())


def fail_notes(data):
    """A plain file where the notes folder belongs, so the first note write fails."""
    mdir = data / '30L1998' / 'moves'
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / 'notes').write_text('in the way')
    return mdir / 'notes'


def clear_fault(path):
    path.unlink()
    path.mkdir()


def test_a_failed_note_write_does_not_log_the_events_twice(league):
    gd, data, st = league
    w, lines = two_moves(gd, data, st)
    notes = fail_notes(data)
    league_scan(w, gd, st)
    assert errors(lines) and moves_log(data)['count'] == 2
    clear_fault(notes)
    league_scan(w, gd, st)
    log = moves_log(data)
    assert log['count'] == 2 and [e['kind'] for e in log['events']] == ['retired', 'signed']
    assert [e.get('note') for e in log['events']] == [0, None]
    note = move_notes(data)[0]
    assert note['kind'] == 'move' and note['event']['note'] == 0 and note['headline'] == 'Joe Old retires'


def test_the_snapshot_is_written_even_when_a_note_write_raises(league):
    gd, data, st = league
    w, lines = two_moves(gd, data, st)
    fail_notes(data)
    league_scan(w, gd, st)
    assert errors(lines)
    snap = last(data)
    assert snap['where']['300'] == 2 and snap['where']['101'] == -1 and snap['date'] == 'April 2'


def test_a_note_that_exists_is_not_rewritten(league):
    gd, data, st = league
    w, lines = two_moves(gd, data, st)
    st['career']['bat'][400]['hr'] = 500
    league_scan(w, gd, st)
    assert sorted(move_notes(data)) == [0, 1]                           # Ann Bat's 500th, Joe Old's retirement
    d = data / '30L1998' / 'moves' / 'notes'
    kept = json.loads((d / '0.json').read_text())
    kept['created'] = 'sentinel'
    (d / '0.json').write_text(json.dumps(kept))
    (d / '1.json').unlink()
    league_scan(w, gd, st)
    notes = move_notes(data)
    assert not errors(lines) and sorted(notes) == [0, 1]
    assert notes[0]['created'] == 'sentinel' and notes[1]['created'] != 'sentinel'
    assert moves_log(data)['count'] == 3


def log_events(data, events, count=None):
    path = data / '30L1998' / 'moves' / 'log.json'
    path.write_text(json.dumps({'events': events, 'count': len(events) if count is None else count}))


def logged(n, **kw):
    ev = {'kind': 'retired', 'name': 'Joe Old', 'pid': 101, 'pos': 'P', 'age': 38, 'from': 'Team One', 'to': None,
          'date': 'April 1', 'year': 1998, 'note': n}
    ev.update(kw)
    return ev


def first_pass(league):
    gd, data, st = league
    w, lines = watcher(gd, data)
    league_scan(w, gd, st)
    return w, lines, gd, data, st


def test_events_of_an_earlier_season_get_no_catch_up_note(league):
    w, lines, gd, data, st = first_pass(league)
    log_events(data, [logged(0, year=1997), logged(1)])
    league_scan(w, gd, st)
    assert not errors(lines) and sorted(move_notes(data)) == [1]
    note = move_notes(data)[1]
    assert note['facts']['date'] == 'April 1' and note['event']['date'] == 'April 1'


def test_a_catch_up_writes_at_most_move_catchup_notes(league):
    w, lines, gd, data, st = first_pass(league)
    assert watch.MOVE_CATCHUP == 20
    log_events(data, [logged(n) for n in range(25)])
    league_scan(w, gd, st)
    assert not errors(lines) and sorted(move_notes(data)) == list(range(20))
    league_scan(w, gd, st)                                              # the next pass takes up the rest
    assert sorted(move_notes(data)) == list(range(25))


def test_malformed_logged_events_are_skipped(league):
    w, lines, gd, data, st = first_pass(league)
    bad_pid = logged(0)
    del bad_pid['pid']
    bad_kind = logged(1)
    del bad_kind['kind']
    bad_name = logged(2)
    del bad_name['name']
    log_events(data, [bad_pid, bad_kind, bad_name, logged(3, note='3'), logged(4, note=None), logged(5, note=True),
                      logged(6, pos=None, age=None), {'note': 7}, logged(8), 'junk'])
    league_scan(w, gd, st)
    assert not errors(lines) and sorted(move_notes(data)) == [6, 8]
    assert last(data)['year'] == 1998


def test_with_no_events_the_log_and_snapshot_are_left_as_they_are(league):
    w, lines, gd, data, st = first_pass(league)
    log_events(data, [logged(0)], count=9)
    league_scan(w, gd, st)
    assert moves_log(data)['count'] == 9 and sorted(move_notes(data)) == [0]
