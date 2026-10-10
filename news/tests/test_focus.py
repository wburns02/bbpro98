"""focus.py: the lines of focus.txt (parse, format), the entries (find, set_focus, clear_focus), the kinds a position
can be focused on (kinds_for) and the birth serials of a PYR file (births). All pure but births, which reads a
synthetic PYR written under tmp_path with test_modbridge's player() and pyr_bytes().
"""
import copy
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import focus       # noqa: E402
import gamedata    # noqa: E402
from tests.test_modbridge import player, pyr_bytes   # noqa: E402

HEADER = '# development focus: pid birth kind assn (written by the news bridge)\n'


def ent(pid, birth, kind, assn=None):
    return {'pid': pid, 'birth': birth, 'kind': kind, 'assn': assn}


def serial(year):
    """The birth serial player() packs for a July 1 birth in year."""
    return datetime.date(year, 7, 1).toordinal() + 365


# parse

def test_parse_reads_pid_birth_kind_and_assn():
    assert focus.parse('100 5000 Contact\n205 6000 control TEST77\n') == [
        ent(100, 5000, 'contact'), ent(205, 6000, 'control', 'TEST77')]


def test_parse_uppercases_the_assn_and_keeps_none_for_one_that_is_not_a_stem():
    assert focus.parse('100 1 power test77')[0]['assn'] == 'TEST77'
    for token in ('TOOLONGXX', 'A-B', 'A_B', 'A\xe9'):
        assert focus.parse('100 1 power %s' % token)[0]['assn'] is None


def test_parse_takes_the_bounds_and_ignores_tokens_after_the_assn():
    assert focus.parse('100 0 contact\n32767 4294967295 defense\n') == [
        ent(100, 0, 'contact'), ent(32767, 4294967295, 'defense')]
    assert focus.parse('100 1 power TEST77 extra tokens\r\n') == [ent(100, 1, 'power', 'TEST77')]


@pytest.mark.parametrize('text', [
    '99 1 power',                   # pid under 100
    '32768 1 power',                # pid over 32767
    '+100 1 power',                 # a sign
    '1_00 1 power',                 # an underscore (int() would take it)
    '100 -1 power',                 # birth under 0
    '100 4294967296 power',         # birth over u32
    '100 x power',
    '100 1 speedy',                 # not a kind
    '100 1',                        # fewer than three tokens
    'pid 1 power',
])
def test_parse_skips_a_line_that_breaks_a_rule(text):
    assert focus.parse(text) == []


def test_parse_skips_blank_and_comment_lines():
    text = '\n# a comment\n  # indented\n\t\n100 1 power\n#100 2 power\n'
    assert focus.parse(text) == [ent(100, 1, 'power')]


def test_parse_keeps_the_first_line_for_a_repeated_pid_and_birth():
    text = '100 1 power TEST77\n100 1 speed ODD78\n100 2 speed ODD78\n'
    assert focus.parse(text) == [ent(100, 1, 'power', 'TEST77'), ent(100, 2, 'speed', 'ODD78')]


def test_a_skipped_line_does_not_claim_its_pid_and_birth():
    # aging.dll cannot read the first line, so the second is the one it uses
    assert focus.parse('100 1 nope\n100 1 power\n') == [ent(100, 1, 'power')]


def test_parse_stops_at_max_entries():
    text = ''.join('%d 1 power\n' % (100 + i) for i in range(focus.MAX_ENTRIES + 5))
    entries = focus.parse(text)
    assert len(entries) == focus.MAX_ENTRIES
    assert entries[-1]['pid'] == 100 + focus.MAX_ENTRIES - 1


# format

def test_format_writes_the_header_then_one_line_per_entry():
    entries = [ent(100, 5, 'power', 'TEST77'), ent(205, 6, 'stuff')]
    assert focus.format(entries) == HEADER + '100 5 power TEST77\n205 6 stuff\n'


def test_format_of_no_entries_is_the_header_alone():
    assert focus.format([]) == HEADER


def test_parse_of_format_gives_the_entries_back():
    entries = [ent(100, 5, 'power', 'TEST77'), ent(205, 6, 'stuff'), ent(32767, 4294967295, 'defense', 'ODD78')]
    assert focus.parse(focus.format(entries)) == entries


# find, set_focus, clear_focus

def test_find_matches_pid_and_birth_together():
    entries = [ent(100, 5, 'power', 'TEST77')]
    assert focus.find(entries, 100, 5) is entries[0]
    assert focus.find(entries, 100, 6) is None
    assert focus.find([], 100, 5) is None


def test_set_focus_appends_a_new_player():
    assert focus.set_focus([], 'TEST77', 100, 5, 'power') == [ent(100, 5, 'power', 'TEST77')]


def test_set_focus_changes_an_existing_entry_in_place():
    entries = [ent(100, 5, 'power', 'TEST77'), ent(205, 6, 'stuff', 'TEST77'), ent(300, 7, 'speed', 'ODD78')]
    out = focus.set_focus(entries, 'ODD78', 205, 6, 'control')
    assert out == [entries[0], ent(205, 6, 'control', 'ODD78'), entries[2]]


def test_set_focus_and_clear_focus_never_change_their_input():
    entries = [ent(100, 5, 'power', 'TEST77'), ent(205, 6, 'stuff', 'TEST77')]
    before = copy.deepcopy(entries)
    changed = focus.set_focus(entries, 'TEST77', 205, 6, 'control')
    appended = focus.set_focus(entries, 'TEST77', 300, 7, 'power')
    cleared = focus.clear_focus(entries, 100, 5)
    assert entries == before
    assert changed[0] is not entries[0] and appended[0] is not entries[0] and cleared[0] is not entries[1]


@pytest.mark.parametrize('kind', ['Contact', 'speed ', 'hit', ''])
def test_set_focus_refuses_a_kind_that_is_not_a_lowercase_kind(kind):
    with pytest.raises(ValueError):
        focus.set_focus([], 'TEST77', 100, 5, kind)


def test_set_focus_allows_five_per_association_and_refuses_a_sixth():
    entries = []
    for i in range(focus.MAX_PER_ASSN):
        entries = focus.set_focus(entries, 'TEST77', 100 + i, 1, 'power')
    with pytest.raises(focus.FocusFull):
        focus.set_focus(entries, 'TEST77', 200, 1, 'power')
    assert len(focus.set_focus(entries, 'ODD78', 200, 1, 'power')) == focus.MAX_PER_ASSN + 1
    assert focus.set_focus(entries, 'TEST77', 100, 1, 'speed')[0]['kind'] == 'speed'


def test_set_focus_refuses_the_max_entries_in_all_but_still_changes_one():
    entries = [ent(100 + i, 1, 'power', 'ASN%d' % (i // focus.MAX_PER_ASSN)) for i in range(focus.MAX_ENTRIES)]
    with pytest.raises(focus.FocusFull):
        focus.set_focus(entries, 'NEW', 5000, 1, 'power')
    assert focus.set_focus(entries, 'NEW', 100, 1, 'speed')[0] == ent(100, 1, 'speed', 'NEW')


def test_clear_focus_removes_the_player_and_keeps_the_rest_in_order():
    entries = [ent(100, 5, 'power', 'TEST77'), ent(205, 6, 'stuff', 'TEST77'), ent(300, 7, 'speed')]
    assert focus.clear_focus(entries, 205, 6) == [entries[0], entries[2]]


def test_clear_focus_matches_the_birth_too():
    entries = [ent(100, 5, 'power', 'TEST77')]
    assert focus.clear_focus(entries, 100, 6) == entries


def test_clear_focus_of_an_absent_player_is_an_equal_copy():
    entries = [ent(100, 5, 'power', 'TEST77')]
    out = focus.clear_focus(entries, 999, 1)
    assert out == entries and out is not entries


# kinds_for

def test_kinds_for_a_pitcher_and_a_hitter():
    assert focus.kinds_for('P') == ('control', 'stuff', 'defense')
    assert focus.kinds_for('SS') == ('contact', 'power', 'speed', 'defense')
    assert focus.kinds_for('') == focus.HITTER_KINDS == ('contact', 'power', 'speed', 'defense')


# births

def test_births_reads_the_birth_serial_of_each_named_player_with_pid_100_or_more(tmp_path):
    path = tmp_path / 'T77.PYR'
    path.write_bytes(pyr_bytes([player(100, born=1952), player(205, 'Bo', 'Bee', pos=1, born=1975),
                                player(50, born=1960), player(300, '', '', born=1970)]))
    assert focus.births(str(path)) == {100: serial(1952), 205: serial(1975)}
    assert set(focus.births(str(path))) == set(gamedata.players(str(path)))
