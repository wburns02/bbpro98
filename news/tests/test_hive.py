"""hive.complete never lets a setup or stream problem escape as anything but HiveError, and a missing key costs no
call from the day's budget. No network: urlopen is replaced."""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hive  # noqa: E402


def budget(tmp_path):
    return hive.Budget(str(tmp_path / 'budget.json'), 5, 100000)


def stream(monkeypatch, *events):
    body = ''.join('data: %s\n' % e for e in events).encode()

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hive.urllib.request, 'urlopen', lambda req, timeout=None: Resp(body))


def no_network(monkeypatch):
    def urlopen(*a, **kw):
        raise AssertionError('no request may be sent')
    monkeypatch.setattr(hive.urllib.request, 'urlopen', urlopen)


def test_a_missing_key_file_is_a_hive_error_and_spends_no_call(tmp_path, monkeypatch):
    no_network(monkeypatch)
    monkeypatch.setattr(hive, 'KEY_FILE', str(tmp_path / 'nowhere.env'))
    monkeypatch.setattr(hive.load_key, '__defaults__', (str(tmp_path / 'nowhere.env'),))
    b = budget(tmp_path)
    with pytest.raises(hive.HiveError):
        hive.complete('s', 'u', b)
    assert b.status()['calls'] == 0


def test_load_key_reads_the_key_and_refuses_a_file_without_it(tmp_path):
    good, empty, binary = tmp_path / 'good.env', tmp_path / 'empty.env', tmp_path / 'bin.env'
    good.write_text('# x\nHIVEMODELS_API_KEY="abc"\n')
    empty.write_text('OTHER=1\n')
    binary.write_bytes(b'\xff\xfe\x00')
    assert hive.load_key(str(good)) == 'abc'
    for path in (empty, binary, tmp_path / 'nowhere.env'):
        with pytest.raises(hive.HiveError):
            hive.load_key(str(path))


@pytest.mark.parametrize('event', ['[1, 2]', '"text"', '{"choices": 5}', '{"choices": [7]}',
                                   '{"choices": [{"delta": [1]}]}', '{"choices": [{"delta": {"content": 9}}]}',
                                   '{"usage": [1]}', '{"usage": {"completion_tokens": "many"}}'])
def test_odd_stream_events_are_skipped_and_the_text_still_comes_back(tmp_path, monkeypatch, event):
    stream(monkeypatch, event, '{"choices": [{"delta": {"content": "Hello"}}]}', '[DONE]')
    b = budget(tmp_path)
    text, _ = hive.complete('s', 'u', b, key='k')
    assert text == 'Hello'
    st = b.status()
    assert st['calls'] == 1 and isinstance(st['out_tokens'], int) and isinstance(st['in_tokens'], int)


def test_a_stream_of_only_odd_events_is_an_empty_answer_hive_error(tmp_path, monkeypatch):
    stream(monkeypatch, '[1]', '{"choices": [7]}', '[DONE]')
    with pytest.raises(hive.HiveError):
        hive.complete('s', 'u', budget(tmp_path), key='k')


def test_a_good_stream_records_its_usage(tmp_path, monkeypatch):
    stream(monkeypatch, '{"choices": [{"delta": {"content": "Hi "}}]}',
           '{"choices": [{"delta": {"content": "there"}}], "usage": {"completion_tokens": 7, "prompt_tokens": 3}}',
           '[DONE]')
    b = budget(tmp_path)
    assert hive.complete('s', 'u', b, key='k') == ('Hi there', {'completion_tokens': 7, 'prompt_tokens': 3})
    st = b.status()
    assert (st['calls'], st['out_tokens'], st['in_tokens']) == (1, 7, 3)
