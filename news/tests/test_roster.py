"""roster.py: move (a hitter or a pitcher leaving and joining a window: substitute from the reserves or none, an empty
slot or a demotion or no room, the lineup and rotation replace rules, every SwapError, the input left alone), problems
(each rule), apply (only the changed windows are rewritten, a round trip through aigm.read), due (the ceil threshold,
the ledger) and apply_due (done, skipped, the problem check, purity). All on synthetic windows and a synthetic ASN; the
fixture helpers are test_aigm's."""
import copy
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aigm        # noqa: E402
import roster      # noqa: E402
from tests.test_aigm import hit, make_asn, pit   # noqa: E402

NONE = 0xFFFF
POS9 = ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH')


def win(active=(), reserves=(), order=(), align=(), rotation=(), pen=()):
    """A 126 id window: the active ids from 0, reserve pairs (level 1) from 25, the order and alignment in both places,
    the rotation at 113 and the bullpen at 120."""
    w = [0] * 126
    w[:len(active)] = active
    for i, pid in enumerate(reserves):
        w[25 + 2 * i], w[26 + 2 * i] = pid, 1 if pid else 0
    for start in (77, 86):
        w[start:start + len(order)] = order
    for start in (95, 104):
        w[start:start + len(align)] = align
    w[113:113 + len(rotation)] = rotation
    w[120:120 + len(pen)] = pen
    return w


def reserves(w):
    return [(w[25 + 2 * i], w[26 + 2 * i]) for i in range(15)]


def at(w, start, n=9):
    return w[start:start + n]


def team(base):
    """(window, players) of a full team: hitters base+1..base+9 (C 1B 2B 3B SS LF CF RF DH, worth 50) in the lineup, a
    bench LF base+10 (40), a rotation base+11..base+15 (50) and a bullpen base+16, base+17 (30, 20). 17 active."""
    players = {base + i + 1: hit(pos, 50) for i, pos in enumerate(POS9)}
    players[base + 10] = hit('LF', 40)
    players.update({base + 11 + i: pit(50) for i in range(5)})
    players.update({base + 16: pit(30), base + 17: pit(20)})
    ids = [base + i for i in range(1, 18)]
    w = win(ids, order=ids[:9], align=ids[:9], rotation=ids[10:15], pen=ids[15:17])
    return w, players


# move: the src side

SRC = 1
DST = 2


def two(src_extra=None, dst=None):
    """({1: window, 2: window}, players): two full teams, team 2 at base 200; the pieces replace team 1's window."""
    w1, p1 = team(100)
    w2, p2 = team(200)
    return {SRC: w1, DST: dst if dst is not None else w2}, {**p1, **p2}


def test_an_active_hitter_leaves_for_the_first_empty_active_slot_of_the_other_team():
    windows, players = two()
    out = roster.move(windows, 110, SRC, DST, players, None)           # the bench LF
    assert 110 not in out[SRC] and out[SRC][9] == 0 and out[SRC][:9] == windows[SRC][:9]
    assert out[DST][17] == 110 and out[DST][:17] == windows[DST][:17]
    assert at(out[SRC], 77) == at(windows[SRC], 77)                    # the bench player held no lineup place


def test_a_reserve_of_his_kind_takes_the_leavers_slot_and_the_lineups():
    windows, players = two()
    players.update({150: hit('1B', 45), 151: pit(10), 152: hit('2B', 44)})
    windows[SRC] = win(windows[SRC][:17], reserves=(151, 150, 152), order=windows[SRC][77:86],
                       align=windows[SRC][95:104], rotation=windows[SRC][113:118], pen=windows[SRC][120:122])
    out = roster.move(windows, 103, SRC, DST, players, None)           # the starting 2B; 150 is the first hitter
    w = out[SRC]
    assert w[2] == 150 and 103 not in w
    assert at(w, 77) == at(w, 86) == [101, 102, 150, 104, 105, 106, 107, 108, 109]
    assert at(w, 95) == at(w, 104) == [101, 102, 150, 104, 105, 106, 107, 108, 109]
    assert reserves(w)[:3] == [(151, 1), (152, 1), (0, 0)]             # 150's pair left, the later ones shifted


def test_with_no_reserve_the_slot_empties_and_the_best_unused_hitter_refills_each_lineup():
    windows, players = two()
    players[111] = hit('LF', 70)
    windows[SRC][17] = 111                                             # a better bench hitter, active, in no lineup
    out = roster.move(windows, 103, SRC, DST, players, None)
    w = out[SRC]
    assert w[2] == 0
    for start in (77, 86, 95, 104):
        assert at(w, start) == [101, 102, 111, 104, 105, 106, 107, 108, 109]


def test_the_refill_is_the_best_valued_hitter_and_ties_go_to_the_lower_id():
    windows, players = two()
    players.update({120: hit('LF', 60), 119: hit('LF', 60), 121: hit('LF', 55)})
    windows[SRC][17:20] = [120, 121, 119]
    out = roster.move(windows, 103, SRC, DST, players, None)
    assert out[SRC][77 + 2] == 119


def test_a_refill_never_duplicates_a_player_already_in_that_order():
    windows, players = two()
    players.update({120: hit('LF', 70), 121: hit('LF', 65)})
    windows[SRC][17:19] = [120, 121]
    windows[SRC][86:95] = [120 if v == 102 else v for v in windows[SRC][86:95]]     # 120 already bats in the LHP order
    out = roster.move(windows, 103, SRC, DST, players, None)
    assert out[SRC][77 + 2] == 120 and out[SRC][86 + 2] == 121


def test_a_pitcher_reserve_does_not_replace_a_hitter():
    windows, players = two()
    players[151] = pit(10)
    windows[SRC] = win(windows[SRC][:17], reserves=(151,), order=windows[SRC][77:86], align=windows[SRC][95:104],
                       rotation=windows[SRC][113:118], pen=windows[SRC][120:122])
    out = roster.move(windows, 103, SRC, DST, players, None)
    assert out[SRC][2] == 0 and reserves(out[SRC])[0] == (151, 1)


def test_a_leaving_pitcher_is_replaced_by_the_first_pitcher_reserve_in_rotation_and_bullpen():
    windows, players = two()
    players.update({150: hit('1B', 45), 151: pit(10), 152: pit(12)})
    windows[SRC] = win(windows[SRC][:17], reserves=(150, 151, 152), order=windows[SRC][77:86],
                       align=windows[SRC][95:104], rotation=windows[SRC][113:118], pen=windows[SRC][120:122])
    out = roster.move(windows, 112, SRC, DST, players, None)           # the second starter
    w = out[SRC]
    assert w[11] == 151 and at(w, 113, 5) == [111, 151, 113, 114, 115]
    assert reserves(w)[:3] == [(150, 1), (152, 1), (0, 0)]
    assert at(w, 77) == at(windows[SRC], 77)                           # the lineups are untouched
    out = roster.move(windows, 116, SRC, DST, players, None)           # a reliever
    assert at(out[SRC], 120, 2) == [151, 117]


def test_with_no_pitcher_reserve_a_leaving_pitcher_is_removed_and_the_rest_shift_left():
    windows, players = two()
    out = roster.move(windows, 112, SRC, DST, players, None)
    w = out[SRC]
    assert w[11] == 0 and at(w, 113, 6) == [111, 113, 114, 115, 0, 0] and w[119] == 0
    out = roster.move(windows, 116, SRC, DST, players, None)
    assert at(out[SRC], 120, 6) == [117, 0, 0, 0, 0, 0]


def test_a_gap_among_the_reserve_pairs_is_kept_when_a_pair_leaves():
    windows, players = two()
    players.update({150: hit('1B', 45), 152: hit('2B', 44), 153: hit('2B', 43)})
    w = win(windows[SRC][:17], reserves=(150, 0, 152, 153), order=windows[SRC][77:86])
    windows[SRC] = w
    out = roster.move(windows, 152, SRC, DST, players, None)
    assert reserves(out[SRC])[:4] == [(150, 1), (0, 0), (153, 1), (0, 0)]


def test_a_reserve_leaves_by_his_pair_and_the_later_pairs_shift_left():
    windows, players = two()
    players.update({150: hit('1B', 45), 151: pit(10), 152: hit('2B', 44)})
    windows[SRC] = win(windows[SRC][:17], reserves=(150, 151, 152), order=windows[SRC][77:86])
    out = roster.move(windows, 151, SRC, DST, players, None)
    assert reserves(out[SRC])[:3] == [(150, 1), (152, 1), (0, 0)]
    assert out[SRC][:25] == windows[SRC][:25]
    assert out[DST][17] == 151


# move: the dst side

def full(base):
    """A window of 25 active (a full team): team(base) plus 8 more bench players, ids base+20 to base+27: 4 hitters
    worth 30 to 33, then 4 pitchers worth 16 down to 13."""
    w, players = team(base)
    extra = [base + 20 + i for i in range(8)]
    for i, pid in enumerate(extra):
        players[pid] = hit('1B', 30 + i) if i < 4 else pit(20 - i)
    w[17:25] = extra
    return w, players


def test_a_full_team_demotes_its_lowest_valued_unused_player_of_the_same_kind():
    wd, pd = full(200)                                 # bench hitters 220..223 (30..33) and 210 (40)
    windows, players = two(dst=wd)
    players.update(pd)
    out = roster.move(windows, 110, SRC, DST, players, None)
    w = out[DST]
    assert w[17] == 110 and w[18:25] == wd[18:25]       # 220 (value 30) made room
    assert reserves(w)[0] == (220, 1)
    assert 220 in w and w[:17] == wd[:17]


def test_a_full_team_demotes_a_pitcher_for_a_pitcher_and_ties_go_to_the_lower_id():
    wd, pd = full(200)
    pd[224], pd[225] = pit(5), pit(5)                   # two pitchers at the lowest value
    windows, players = two(dst=wd)
    players.update(pd)
    out = roster.move(windows, 116, SRC, DST, players, None)
    assert out[DST][21] == 116 and reserves(out[DST])[0] == (224, 1)


@pytest.mark.parametrize('index', [80, 100, 115, 122])      # an order, an alignment, the rotation, the bullpen
def test_a_player_in_a_lineup_rotation_or_bullpen_is_never_demoted(index):
    wd, pd = full(200)
    pd[220] = hit('1B', 1)                              # the lowest, but in a slot below
    wd[index] = 220
    windows, players = two(dst=wd)
    players.update(pd)
    out = roster.move(windows, 110, SRC, DST, players, None)
    assert reserves(out[DST])[0] == (221, 1) and 220 in out[DST][:25]


def test_a_full_team_with_nobody_to_demote_has_no_room():
    ids = list(range(201, 210)) + list(range(211, 227))             # 9 hitters, all in the lineups, and 16 pitchers
    wd = win(ids, order=ids[:9], align=ids[:9], rotation=ids[9:14], pen=ids[14:20])
    windows, players = two(dst=wd)
    players.update({i: hit('1B', 50) for i in ids[:9]})
    players.update({i: pit(50) for i in ids[9:]})
    before = copy.deepcopy(windows)
    with pytest.raises(aigm.SwapError, match='no room'):
        roster.move(windows, 110, SRC, DST, players, None)
    assert windows == before


def test_a_full_team_with_no_empty_reserve_pair_has_no_room():
    wd, pd = full(200)
    wd[25:55] = [v for i in range(15) for v in (1000 + i, 1)]
    windows, players = two(dst=wd)
    players.update(pd)
    with pytest.raises(aigm.SwapError, match='no room'):
        roster.move(windows, 110, SRC, DST, players, None)


# move: the lineup and rotation rules

def test_a_better_hitter_takes_the_alignment_players_place_in_both_orders_and_alignments():
    windows, players = two()
    players[110] = hit('SS', 51)                        # team 2's SS is 205, worth 50
    windows[SRC][9] = 110
    out = roster.move(windows, 110, SRC, DST, players, None)
    w = out[DST]
    for start in (77, 86, 95, 104):
        assert at(w, start) == [201, 202, 203, 204, 110, 206, 207, 208, 209]
    assert 205 in w[:25]                                # benched, not released


def test_an_equal_or_worse_hitter_does_not_replace_the_alignment_player():
    windows, players = two()
    players[110] = hit('SS', 50)
    out = roster.move(windows, 110, SRC, DST, players, None)
    assert at(out[DST], 77) == at(windows[DST], 77)
    players[110] = hit('SS', 49)
    out = roster.move(windows, 110, SRC, DST, players, None)
    assert at(out[DST], 95) == at(windows[DST], 95)


def test_a_hitter_at_dh_or_with_an_empty_position_replaces_nobody():
    windows, players = two()
    players[110] = hit('DH', 90)
    assert at(roster.move(windows, 110, SRC, DST, players, None)[DST], 77) == at(windows[DST], 77)
    players[110] = hit('C', 90)
    windows[DST][95] = 0                                # no alignment catcher
    out = roster.move(windows, 110, SRC, DST, players, None)
    assert at(out[DST], 95) == at(windows[DST], 95)


def test_a_better_pitcher_takes_the_lowest_rotation_place_and_the_displaced_one_goes_to_the_pen():
    windows, players = two()
    players[111] = pit(60)
    players[213] = pit(40)                              # team 2's weakest starter
    windows[DST][120:122] = [216, 217]
    windows[DST][122] = 0
    out = roster.move(windows, 111, SRC, DST, players, None)
    w = out[DST]
    assert at(w, 113, 5) == [211, 212, 111, 214, 215] and at(w, 120, 4) == [216, 217, 213, 0]


def test_a_displaced_pitcher_with_a_full_bullpen_just_leaves_the_rotation():
    windows, players = two()
    players[111] = pit(60)
    windows[DST][120:126] = [216, 217, 218, 219, 220, 221]
    out = roster.move(windows, 111, SRC, DST, players, None)
    assert at(out[DST], 113, 5) == [111, 212, 213, 214, 215] and at(out[DST], 120, 6) == windows[DST][120:126]


def test_a_pitcher_not_above_the_lowest_starter_leaves_the_rotation_alone():
    windows, players = two()
    players[111] = pit(50)                              # equal to every starter
    out = roster.move(windows, 111, SRC, DST, players, None)
    assert at(out[DST], 113, 6) == at(windows[DST], 113, 6)


# move: the errors and the input

@pytest.mark.parametrize('pid, src, dst, text', [
    (201, SRC, DST, 'is not on the roster of team 1'),
    (101, SRC, SRC, 'already on team 1'),
    (999, SRC, DST, 'not a known player'),
    (101, SRC, 9, 'no live r record'),
    (101, 9, DST, 'no live r record'),
])
def test_move_refuses_a_move_that_does_not_fit(pid, src, dst, text):
    windows, players = two()
    before = copy.deepcopy(windows)
    with pytest.raises(aigm.SwapError, match=text):
        roster.move(windows, pid, src, dst, players, None)
    assert windows == before


def test_move_refuses_a_player_already_in_the_other_window_and_one_only_in_a_lineup():
    windows, players = two()
    windows[DST][30] = 101                              # anywhere in dst's window counts
    with pytest.raises(aigm.SwapError, match='already on team 2'):
        roster.move(windows, 101, SRC, DST, players, None)
    windows, players = two()
    windows[SRC][0] = 0                                 # 101 is in the lineups but no longer active or reserve
    with pytest.raises(aigm.SwapError, match='not on the roster'):
        roster.move(windows, 101, SRC, DST, players, None)


def test_move_refuses_a_move_with_no_hitter_left_to_refill_a_lineup():
    players = {i: hit('1B', 50) for i in range(101, 110)}
    players.update({i: pit(50) for i in range(111, 116)})
    w = win(list(range(101, 110)) + list(range(111, 116)), order=list(range(101, 110)), align=list(range(101, 110)))
    windows = {SRC: w, DST: win([201])}
    players[201] = hit('1B', 50)
    with pytest.raises(aigm.SwapError, match='no active hitter'):
        roster.move(windows, 101, SRC, DST, players, None)


def test_move_never_changes_its_input_and_returns_every_team():
    windows, players = two()
    windows[3] = win([301])
    before = copy.deepcopy(windows)
    out = roster.move(windows, 110, SRC, DST, players, 1977)
    assert windows == before
    assert set(out) == {1, 2, 3} and out[3] == windows[3] and out[3] is not windows[3]
    assert all(out[t] is not windows[t] for t in out)


def test_the_value_uses_the_season_year_for_the_age():
    windows, players = two()
    players[110] = hit('SS', 50, born=1950)             # 27 in 1977: 50. A rookie's 1.10 would beat the 50 at SS
    assert at(roster.move(windows, 110, SRC, DST, players, 1977)[DST], 77) == at(windows[DST], 77)
    players[110] = hit('SS', 50, born=1955)             # 22: 55
    assert 110 in at(roster.move(windows, 110, SRC, DST, players, 1977)[DST], 77)


# problems

def test_a_sound_pair_of_teams_has_no_problems():
    windows, players = two()
    assert roster.problems(windows, players) == []


def test_an_id_on_two_teams_is_a_problem():
    windows, players = two()
    windows[DST][30] = 101
    assert roster.problems(windows, players) == ['101 is on team 1 and team 2']


def test_a_lineup_rotation_or_bullpen_id_off_the_active_list_is_a_problem():
    windows, players = two()
    windows[SRC][0] = 0                                 # 101 leaves the active list but stays in the lineups
    windows[SRC][113] = 150
    windows[SRC][120] = 151
    got = roster.problems(windows, players)
    assert '101 is in the batting order of team 1 but not on its active roster' in got
    assert '101 is in the alignment of team 1 but not on its active roster' in got
    assert '150 is in the rotation of team 1 but not on its active roster' in got
    assert '151 is in the bullpen of team 1 but not on its active roster' in got
    assert len([p for p in got if p.startswith('101 ')]) == 2      # once per kind of lineup, not per copy


def test_the_pitchers_slot_and_empty_places_are_not_ids():
    windows, players = two()
    windows[SRC][77:86] = [NONE] + windows[SRC][78:86]              # the pitcher bats first in the RHP order
    windows[SRC][120:126] = [0] * 6
    got = roster.problems(windows, players)
    assert got == []


def test_a_team_needs_nine_active_hitters_and_five_active_pitchers():
    windows, players = two()
    windows[SRC][8:10] = [0, 0]                         # DH 109 and the bench LF 110: 8 hitters left
    windows[DST][10:15] = [0] * 5                       # 200 has 5 pitchers fewer than... 2 left (216, 217)
    got = roster.problems(windows, players)
    assert 'team 1 has 8 active hitters, needs 9' in got
    assert 'team 2 has 2 active pitchers, needs 5' in got


def test_players_not_in_the_player_table_count_as_neither():
    windows, players = two()
    for pid in (101, 102, 111, 112, 113):
        del players[pid]                                # team 1: 8 hitters and 4 pitchers are known
    got = roster.problems(windows, players)
    assert 'team 1 has 8 active hitters, needs 9' in got and 'team 1 has 4 active pitchers, needs 5' in got


# apply

@pytest.fixture
def asn(monkeypatch):
    """build(windows) -> bytes of a synthetic ASN with aigm.locate pointed at its records; its loc is .loc."""
    def build(windows):
        data, loc = make_asn(windows)
        monkeypatch.setattr(aigm, 'locate', lambda _data: loc)
        build.loc = loc
        return data
    return build


def test_apply_rewrites_only_the_windows_that_differ(asn):
    windows, players = two()
    windows[3] = win([301, 302])
    data = asn(windows)
    moved = roster.move(windows, 110, SRC, DST, players, None)
    new = roster.apply(data, moved)
    assert len(new) == len(data)
    changed = {i for i in range(len(data)) if data[i] != new[i]}
    inside = set()
    for tid in (SRC, DST):
        off = asn.loc['r'][tid][0]
        inside |= set(range(off + 42, off + 294))
    assert changed and changed <= inside
    assert aigm.read(new)['windows'] == moved


def test_apply_round_trips_through_read_and_a_second_apply_changes_nothing(asn):
    windows, players = two()
    data = asn(windows)
    assert aigm.read(data)['windows'] == windows
    assert roster.apply(data, windows) == data          # nothing differs: not a byte moves
    moved = roster.move(windows, 112, SRC, DST, players, None)
    new = roster.apply(data, moved)
    assert aigm.read(new)['windows'] == moved
    assert roster.apply(new, moved) == new


def test_apply_leaves_the_teams_the_windows_dict_lacks_alone(asn):
    windows, players = two()
    windows[3] = win([301])
    data = asn(windows)
    moved = roster.move(windows, 110, SRC, DST, players, None)
    new = roster.apply(data, {t: w for t, w in moved.items() if t != 3})
    assert aigm.read(new)['windows'][3] == windows[3]


@pytest.mark.parametrize('bad', [{9: [0] * 126}, {1: [0] * 125}, {1: [0] * 125 + [70000]}, {1: [0] * 125 + [-1]}])
def test_apply_refuses_a_window_that_cannot_be_written(asn, bad):
    data = asn({1: win([101])})
    with pytest.raises(ValueError):
        roster.apply(data, bad)


# due

def games(**teams):
    """Games for assoc: team t plays n games against team 9 (the first `played` of them played): t=(n, played)."""
    out = []
    for tid, (n, played) in teams.items():
        tid = int(tid[1:])
        out += [{'away': tid, 'home': 9, 'played': i < played} for i in range(n)]
    return {'games': out}


def doc(*ats, frm=1):
    return {'kind': 'moves', 'year': 1977, 'moves': [{'pid': 101, 'name': 'Pat Doe', 'from': frm, 'to': 2, 'at': a}
                                                    for a in ats]}


@pytest.mark.parametrize('played, due_now', [(2, False), (3, True), (4, True)])
def test_a_move_is_due_at_the_ceil_of_its_share_of_the_schedule(played, due_now):
    assert (roster.due(doc(0.25), games(t1=(10, played)), None) == [0]) is due_now      # ceil(2.5) = 3


@pytest.mark.parametrize('at, n, need', [(0.3, 10, 3), (0.07, 100, 7), (0.57, 100, 57), (0.5, 162, 81),
                                         (0.95, 162, 154)])
def test_an_exact_threshold_is_not_pushed_up_by_float_noise(at, n, need):
    assert need == math.ceil(round(at * n, 6))
    assert roster.due(doc(at), games(t1=(n, need)), None) == [0]
    assert roster.due(doc(at), games(t1=(n, need - 1)), None) == []


def test_a_game_counts_for_both_its_teams_and_only_when_played():
    g = {'games': [{'away': 1, 'home': 2, 'played': True}, {'away': 2, 'home': 1, 'played': True},
                   {'away': 1, 'home': 2, 'played': False}, {'away': 1, 'home': 2, 'played': False}]}
    assert roster.due(doc(0.5), g, None) == [0]         # 2 of 4
    assert roster.due(doc(0.75), g, None) == []         # needs 3
    assert roster.due(doc(0.5, frm=2), g, None) == [0]


def test_a_move_is_judged_by_its_own_from_team():
    g = games(t1=(10, 9), t2=(10, 0))
    d = doc(0.9)
    d['moves'].append(dict(d['moves'][0], **{'from': 2}))
    assert roster.due(d, g, None) == [0]


def test_a_team_with_no_scheduled_game_is_never_due():
    assert roster.due(doc(0.05, frm=7), games(t1=(10, 10)), None) == []
    assert roster.due(doc(0.05), {'games': []}, None) == []


def test_indexes_in_the_ledger_are_not_due_again():
    d = doc(0.1, 0.2, 0.3)
    g = games(t1=(10, 10))
    assert roster.due(d, g, None) == [0, 1, 2]
    assert roster.due(d, g, {'kind': 'moves', 'year': 1977, 'done': {}}) == [0, 1, 2]
    ledger = {'kind': 'moves', 'year': 1977,
              'done': {'0': {'status': 'done'}, '2': {'status': 'skipped', 'reason': 'x'}}}
    assert roster.due(d, g, ledger) == [1]


def test_a_malformed_move_is_never_due():
    d = {'moves': [{'from': 1}, {'from': 1, 'at': 'x'}, {'from': [1], 'at': 0.1}, 7, {'from': 1, 'at': 0.1}]}
    assert roster.due(d, games(t1=(10, 10)), None) == [4]
    assert roster.due({}, games(t1=(10, 10)), None) == []


# apply_due

def pair(asn, extra=None):
    windows, players = two()
    return windows, players, asn(windows)


def mv(pid, frm, to, at):
    return {'pid': pid, 'name': 'n%s' % pid, 'from': frm, 'to': to, 'at': at}


def moves_doc(*moves):
    return {'kind': 'moves', 'year': 1977, 'moves': list(moves)}


def test_due_moves_are_applied_in_index_order_and_recorded(asn):
    windows, players, data = pair(asn)
    d = moves_doc(mv(110, SRC, DST, 0.5), mv(203, DST, SRC, 0.1), mv(112, SRC, DST, 0.9))
    new, led = roster.apply_due(data, d, games(t1=(10, 6), t2=(10, 3)), players, 1977, None)
    assert led == {'kind': 'moves', 'year': 1977, 'done': {'0': {'status': 'done', 'played': 6},
                                                           '1': {'status': 'done', 'played': 3}}}
    after = aigm.read(new)['windows']
    assert 110 in after[DST] and 110 not in after[SRC]
    assert 203 in after[SRC] and 203 not in after[DST]
    assert 112 in after[SRC]                            # 0.9 of 10 is 9 games: not due
    expect = roster.move(roster.move(windows, 110, SRC, DST, players, 1977), 203, DST, SRC, players, 1977)
    assert after == expect


def test_a_second_run_applies_nothing_that_is_in_the_ledger(asn):
    windows, players, data = pair(asn)
    d = moves_doc(mv(110, SRC, DST, 0.5))
    g = games(t1=(10, 6))
    new, led = roster.apply_due(data, d, g, players, 1977, None)
    again, led2 = roster.apply_due(new, d, g, players, 1977, led)
    assert again == new and led2 == led


def test_a_move_that_does_not_fit_is_skipped_and_the_others_still_run(asn):
    windows, players, data = pair(asn)
    d = moves_doc(mv(201, SRC, DST, 0.5), mv(110, SRC, DST, 0.5), mv('x', SRC, DST, 0.5))
    new, led = roster.apply_due(data, d, games(t1=(10, 5)), players, 1977, None)
    assert led['done']['0'] == {'status': 'skipped', 'reason': '201 is not on the roster of team 1', 'played': 5}
    assert led['done']['1'] == {'status': 'done', 'played': 5}
    assert led['done']['2'] == {'status': 'skipped', 'reason': 'the move is malformed', 'played': 5}
    assert 110 in aigm.read(new)['windows'][DST]


def test_a_skipped_move_is_not_tried_again(asn):
    windows, players, data = pair(asn)
    d = moves_doc(mv(201, SRC, DST, 0.5))
    g = games(t1=(10, 5))
    new, led = roster.apply_due(data, d, g, players, 1977, None)
    assert new == data
    assert roster.due(d, g, led) == []


def test_a_result_with_a_new_problem_is_refused_and_nothing_is_applied(asn):
    windows, players, data = pair(asn)
    d = moves_doc(mv(115, SRC, DST, 0.1), mv(116, SRC, DST, 0.1), mv(117, SRC, DST, 0.1))     # 4 pitchers left
    ledger = {'kind': 'moves', 'year': 1977, 'done': {}}
    with pytest.raises(ValueError, match='team 1 has 4 active pitchers, needs 5'):
        roster.apply_due(data, d, games(t1=(10, 10)), players, 1977, ledger)
    assert ledger == {'kind': 'moves', 'year': 1977, 'done': {}}


def test_a_problem_the_file_already_had_does_not_stop_a_move(asn):
    windows, players = two()
    windows[SRC][14:17] = [0, 0, 0]                                    # team 1 starts with 4 pitchers
    data = asn(windows)
    assert roster.problems(windows, players) == ['115 is in the rotation of team 1 but not on its active roster',
                                                 '116 is in the bullpen of team 1 but not on its active roster',
                                                 '117 is in the bullpen of team 1 but not on its active roster',
                                                 'team 1 has 4 active pitchers, needs 5']
    d = moves_doc(mv(110, SRC, DST, 0.1))
    new, led = roster.apply_due(data, d, games(t1=(10, 10)), players, 1977, None)
    assert led['done']['0']['status'] == 'done'      # the same problems before and after: nothing new


def test_apply_due_never_changes_its_inputs(asn):
    windows, players, data = pair(asn)
    d = moves_doc(mv(110, SRC, DST, 0.1))
    ledger = {'kind': 'moves', 'year': 1977, 'done': {'5': {'status': 'done', 'played': 1}}}
    before = copy.deepcopy((d, ledger, players))
    new, led = roster.apply_due(data, d, games(t1=(10, 10)), players, 1977, ledger)
    assert (d, ledger, players) == before
    assert led is not ledger and led['done']['5'] == {'status': 'done', 'played': 1} and '0' in led['done']
    assert new != data
