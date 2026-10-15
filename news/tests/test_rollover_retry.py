"""Watcher.rollover stages the move in past/.rolling-<year>/ and renames it into place at the end, so a pass that fails
part way is finished by the next one into the same folder."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import watch  # noqa: E402

ENTRIES = ('meta.json', 'recaps/aa.json', 'feed/10-01.json', 'awards.json', 'preview.json')
NEW = {'season_year': 1998}


def rolling(tmp_path):
    lines = []
    return watch.Watcher(str(tmp_path / 'game'), str(tmp_path / 'data'), None, None, log=lines.append), lines


def season(tmp_path):
    out = tmp_path / 'data' / 'A'
    for name in ENTRIES:
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(json.dumps({'season_year': 1997} if name == 'meta.json' else {}))
    return out


def fail_once(monkeypatch, when):
    """os.replace raises OSError once, on the first call when(n, src, dst) picks; every other call goes through."""
    real, state = os.replace, {'n': 0, 'failed': False}

    def replace(src, dst):
        state['n'] += 1
        if not state['failed'] and when(state['n'], src, dst):
            state['failed'] = True
            raise OSError('disk')
        real(src, dst)

    monkeypatch.setattr(watch.os, 'replace', replace)


def holds_everything(folder):
    return all((folder / name).exists() for name in ENTRIES)


def folders(out):
    return sorted(os.listdir(out / 'past'))


def test_a_rollover_with_no_failure_leaves_no_stage(tmp_path):
    out = season(tmp_path)
    w, lines = rolling(tmp_path)
    assert w.rollover('A', str(out), NEW) == '1997'
    assert lines == ['A season 1997 news archived to past/1997']
    assert folders(out) == ['1997'] and holds_everything(out / 'past' / '1997')
    assert json.loads((out / 'meta.json').read_text())['season_year'] == 1998
    assert not any((out / name).exists() for name in ENTRIES if name != 'meta.json')


def test_a_failure_part_way_is_finished_by_the_next_pass_into_the_same_folder(tmp_path, monkeypatch):
    out = season(tmp_path)
    w, lines = rolling(tmp_path)
    fail_once(monkeypatch, lambda n, src, dst: n == 2)
    with pytest.raises(OSError):
        w.rollover('A', str(out), NEW)
    assert folders(out) == ['.rolling-1997'] and lines == []
    assert w.rollover('A', str(out), NEW) == '1997'
    assert folders(out) == ['1997'] and holds_everything(out / 'past' / '1997')
    assert lines == ['A season 1997 news archived to past/1997']


def test_a_failure_on_the_final_rename_keeps_everything_in_the_stage(tmp_path, monkeypatch):
    out = season(tmp_path)
    w, lines = rolling(tmp_path)
    final = str(out / 'past' / '1997')
    fail_once(monkeypatch, lambda n, src, dst: dst == final)
    with pytest.raises(OSError):
        w.rollover('A', str(out), NEW)
    assert folders(out) == ['.rolling-1997'] and holds_everything(out / 'past' / '.rolling-1997') and lines == []
    assert w.rollover('A', str(out), NEW) == '1997'
    assert folders(out) == ['1997'] and holds_everything(out / 'past' / '1997')


@pytest.mark.parametrize('fails', [False, True])
def test_a_name_already_taken_goes_to_the_next_suffix_failed_or_not(tmp_path, monkeypatch, fails):
    out = season(tmp_path)
    (out / 'past' / '1997').mkdir(parents=True)
    (out / 'past' / '1997' / 'old.json').write_text('{}')
    w, lines = rolling(tmp_path)
    if fails:
        fail_once(monkeypatch, lambda n, src, dst: n == 2)
        with pytest.raises(OSError):
            w.rollover('A', str(out), NEW)
        assert folders(out) == ['.rolling-1997', '1997']
    assert w.rollover('A', str(out), NEW) == '1997-2'
    assert folders(out) == ['1997', '1997-2'] and holds_everything(out / 'past' / '1997-2')
    assert (out / 'past' / '1997' / 'old.json').exists() and not (out / 'past' / '1997' / 'meta.json').exists()
    assert lines == ['A season 1997 news archived to past/1997-2']


def test_no_rollover_creates_no_past_folder_and_no_stage(tmp_path):
    out = season(tmp_path)
    w, lines = rolling(tmp_path)
    assert w.rollover('A', str(out), {'season_year': 1997}) is None
    (out / 'meta.json').unlink()
    assert w.rollover('A', str(out), NEW) is None
    assert not (out / 'past').exists() and lines == []


def test_a_pass_that_fails_after_the_rollover_never_archives_the_new_season_again(tmp_path):
    out = season(tmp_path)
    w, lines = rolling(tmp_path)
    assert w.rollover('A', str(out), NEW) == '1997'
    (out / 'recaps').mkdir()
    (out / 'recaps' / 'new.json').write_text('{}')      # a 1998 story written before a later step raised
    assert w.rollover('A', str(out), NEW) is None
    assert folders(out) == ['1997'] and (out / 'recaps' / 'new.json').exists()
