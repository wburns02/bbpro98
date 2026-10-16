"""aigm.py: the age factor and the value; plan (the best trades, ties, MAX_TRADES, one trade per team, the balance, the
need, catchers and pitchers never traded, proposals only for human teams and never on a chosen trade's players,
MAX_PROPOSALS, the inputs left alone); read and apply_trade on synthetic ASN bytes (locate is pointed at the records,
the cipher seed is at 0x310-0x311); locate's filter on a fake ctree.parse; validate (each problem); and one check on the
real 1950 association, which skips when its files are not on the machine. Then the upgrade: strength and the offseason
and deadline modes, mode_value at every age edge, the fog in planning (stem None as before), a mode's effect on a trade,
pitcher swaps (the rotation spot, the displaced pitcher, validate) and the salary term. The deadline is in
test_aigm_deadline.py.
"""
import copy
import os
import struct
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aigm        # noqa: E402
import ctree       # noqa: E402
import fog         # noqa: E402
import gamedata    # noqa: E402 (work/ is on the path once gamedata is imported)
import league      # noqa: E402

SEED = (0x6b, 0xe2)
REAL = '/mnt/nvme/bbpro98/next10/mm/own/16L1950.ASN'


def hit(pos, contact, born=1950):
    return {'name': '%s %d' % (pos, contact), 'pos': pos, 'bats': 'R', 'throws': 'R', 'born': born,
            'contact': contact, 'power': 0, 'speed': 0, 'stamina': 0, 'control': 0, 'strikeout': 0, 'fielding': 0}


def pit(control, born=1950):
    p = hit('P', 0, born)
    p['control'] = control
    return p


def win(active=(), lineup=()):
    """A window: the active ids at 0..24 (0 for an empty slot), the lineup ids from 25 on, then zeros."""
    w = list(active) + [0] * (aigm.ACTIVE - len(active)) + list(lineup)
    return w + [0] * (aigm.WINDOW_LEN - len(w))


def pairs(trades):
    return [(t['a'], t['b']) for t in trades]


def touched(trade):
    return {trade['a_gives'], trade['b_gives'], trade['a_drops'], trade['b_drops']} - {None}


# the age factor and the value

@pytest.mark.parametrize('age, factor', [(None, 1.0), (19, 1.10), (26, 1.10), (27, 1.0), (30, 1.0), (31, 0.9),
                                         (33, 0.9), (34, 0.75), (40, 0.75)])
def test_age_factor_steps_at_26_30_33(age, factor):
    assert aigm.age_factor(age) == factor


def test_value_is_the_rating_index_times_the_age_factor():
    p = hit('SS', 60, born=1950)
    p.update(power=40, speed=20, fielding=40)           # index 60 + 40 + 20/4 + 40/4 = 115
    assert aigm.value(p, 1977) == 115.0                 # age 27: factor 1.0
    assert aigm.value(p, 1975) == pytest.approx(115 * 1.10)     # age 25
    assert aigm.value(p, 1950 + 32) == pytest.approx(115 * 0.9)  # age 32
    assert aigm.value(p, 1950 + 35) == pytest.approx(115 * 0.75)  # age 35


def test_value_of_a_pitcher_is_control_plus_strikeout_plus_stamina_over_four():
    p = pit(50)
    p.update(strikeout=70, stamina=60)
    assert aigm.value(p, None) == 50 + 70 + 15


def test_value_uses_factor_one_when_the_year_or_the_birth_is_unknown():
    p = hit('1B', 66, born=None)
    assert aigm.value(p, 1977) == 66.0
    assert aigm.value(hit('1B', 66), None) == 66.0


# plan

def pair_players():
    return {101: hit('SS', 60), 102: hit('2B', 70), 201: hit('2B', 50), 202: hit('SS', 65)}


def pair_windows():
    """Team 1: SS starter 101, bench 2B 102. Team 2: 2B starter 201, bench SS 202."""
    return {1: win([101, 102], [101]), 2: win([201, 202], [201])}


def test_the_bench_players_trade_to_fill_each_others_needs():
    found = aigm.plan(pair_windows(), pair_players(), None)
    assert found == {'trades': [{'a': 1, 'b': 2, 'a_gives': 102, 'b_gives': 202, 'a_pos': '2B', 'b_pos': 'SS',
                                 'b_drops': 201, 'a_drops': 101, 'gain': 25.0}], 'proposals': []}


@pytest.mark.parametrize('contact, traded', [(63, True), (62, False)])
def test_the_two_values_must_be_within_a_tenth_of_the_larger(contact, traded):
    players = pair_players()
    players[202] = hit('SS', contact)                   # 70 against 63 is 7, the limit; 62 is 8
    assert bool(aigm.plan(pair_windows(), players, None)['trades']) is traded


def test_a_player_must_beat_the_starter_he_would_replace():
    players = pair_players()
    players[101] = hit('SS', 66)                        # team 1's SS starter; 202 (63) does not beat him
    players[202] = hit('SS', 63)
    assert aigm.plan(pair_windows(), players, None)['trades'] == []


def test_a_player_must_beat_the_starter_he_would_displace_on_the_other_side():
    players = pair_players()
    players[201] = hit('2B', 72)                        # team 2's 2B starter; 102 (70) does not beat him
    assert aigm.plan(pair_windows(), players, None)['trades'] == []


def test_a_position_with_no_starter_needs_its_best_bench_player():
    windows = {1: win([101, 102], [101]), 2: win([201, 202], [])}     # team 2 has no lineup at all
    trades = aigm.plan(windows, pair_players(), None)['trades']
    assert trades == [{'a': 1, 'b': 2, 'a_gives': 102, 'b_gives': 202, 'a_pos': '2B', 'b_pos': 'SS',
                       'b_drops': None, 'a_drops': 101, 'gain': 25.0}]


def test_catchers_and_pitchers_are_never_traded():
    players = pair_players()
    players.update({103: hit('C', 90), 104: pit(90), 203: hit('C', 90), 204: pit(90)})
    windows = {1: win([101, 102, 103, 104], [101]), 2: win([201, 202, 203, 204], [201])}
    trades = aigm.plan(windows, players, None)['trades']
    assert [(t['a_gives'], t['b_gives']) for t in trades] == [(102, 202)]


def test_an_equal_gain_goes_to_the_smaller_ids():
    players = pair_players()
    players[105] = hit('2B', 70)                        # a second 70 on team 1's bench: 102 wins the tie
    windows = {1: win([101, 102, 105], [101]), 2: win([201, 202], [201])}
    trades = aigm.plan(windows, players, None)['trades']
    assert [(t['a_gives'], t['b_gives']) for t in trades] == [(102, 202)]


def league_of(n):
    """n teams. Odd teams are donors (a bench 2B worth 70), even teams receivers (a bench SS worth 65); all have a 2B
    starter worth 50 and an SS starter worth 60, so every donor-receiver pair has one trade worth a gain of 25."""
    players, windows = {}, {}
    for tid in range(1, n + 1):
        base = 100 + tid * 10
        s2, ss, bench = base + 1, base + 2, base + 3
        players.update({s2: hit('2B', 50), ss: hit('SS', 60)})
        players[bench] = hit('2B', 70) if tid % 2 else hit('SS', 65)
        windows[tid] = win([s2, ss, bench], [s2, ss])
    return windows, players


def test_the_best_gain_goes_first_and_each_team_trades_once():
    windows, players = league_of(4)
    found = aigm.plan(windows, players, None)
    assert pairs(found['trades']) == [(1, 2), (3, 4)]


def test_no_more_than_max_trades_are_made():
    windows, players = league_of(2 * aigm.MAX_TRADES + 2)
    trades = aigm.plan(windows, players, None)['trades']
    assert len(trades) == aigm.MAX_TRADES
    assert pairs(trades) == [(2 * i + 1, 2 * i + 2) for i in range(aigm.MAX_TRADES)]


def test_a_human_team_is_never_traded_for_by_the_computer_teams():
    windows, players = league_of(4)
    found = aigm.plan(windows, players, None, human=frozenset({1, 2}))
    assert pairs(found['trades']) == [(3, 4)]


def human_scenario():
    """Team 1 is human and team 2 computer. Team 1 starts at 1B, 2B and 3B (50) and SS (60), with a bench of SS, 3B, 1B
    and 2B (70 each). Team 2 is the same with its bench on the other side."""
    players = {}
    for pid, pos, contact in ((101, '1B', 50), (102, '2B', 50), (103, '3B', 50), (104, 'SS', 60),
                              (111, 'SS', 70), (112, '3B', 70), (113, '1B', 70), (114, '2B', 70),
                              (201, '1B', 50), (202, '2B', 50), (203, '3B', 50), (204, 'SS', 60),
                              (211, '2B', 70), (212, '1B', 70), (213, '3B', 70), (214, 'SS', 70)):
        players[pid] = hit(pos, contact)
    windows = {1: win([101, 102, 103, 104, 111, 112, 113, 114], [101, 102, 103, 104]),
               2: win([201, 202, 203, 204, 211, 212, 213, 214], [201, 202, 203, 204])}
    return windows, players


def test_proposals_go_to_human_teams_only_and_at_most_max_proposals():
    windows, players = human_scenario()
    found = aigm.plan(windows, players, None, human=frozenset({1}))
    assert found['trades'] == []
    assert len(found['proposals']) == aigm.MAX_PROPOSALS
    assert all(p['a'] == 1 and p['b'] == 2 for p in found['proposals'])
    assert [(p['a_gives'], p['b_gives']) for p in found['proposals']] == [(112, 211), (113, 213), (114, 212)]


def test_no_proposal_uses_a_player_of_an_earlier_proposal():
    windows, players = human_scenario()
    found = aigm.plan(windows, players, None, human=frozenset({1}))
    seen = set()
    for p in found['proposals']:
        assert touched(p).isdisjoint(seen)
        seen |= touched(p)


def test_a_proposal_never_uses_a_player_of_a_chosen_trade():
    windows, players = human_scenario()
    # Teams 3 and 4 are computer teams that trade with each other: a donor (bench 2B 303 worth 70) and a receiver
    # (bench SS 403 worth 65), each with starters at 2B and SS.
    for tid, base in ((3, 300), (4, 400)):
        players.update({base + 1: hit('2B', 50), base + 2: hit('SS', 60)})
        windows[tid] = win([base + 1, base + 2, base + 3], [base + 1, base + 2])
    players[303], players[403] = hit('2B', 70), hit('SS', 65)
    found = aigm.plan(windows, players, None, human=frozenset({1}))
    chosen = set()
    for t in found['trades']:
        chosen |= touched(t)
    assert found['trades'], 'the computer teams should trade with each other'
    assert found['proposals'], 'the human team should get proposals'
    for p in found['proposals']:
        assert touched(p).isdisjoint(chosen)


def test_plan_never_changes_its_inputs():
    windows, players = human_scenario()
    before_w, before_p = copy.deepcopy(windows), copy.deepcopy(players)
    aigm.plan(windows, players, 1977, human=frozenset({1}))
    assert windows == before_w and players == before_p


# read, apply_trade and locate on synthetic bytes

def make_asn(windows, human=()):
    """(bytes, loc): a synthetic ASN with an r record per team (its id window enciphered from byte 42) and a t record
    per team (owner byte 1 for a human team), the seed at 0x310-0x311. loc is what locate returns for these records;
    each record's key byte is the team id, stored plain."""
    t = league._forward(SEED)
    data = bytearray(0x312)
    data[0x310:0x312] = bytes(SEED)
    loc = {'r': {}, 't': {}}

    def record(tid, plain):
        return bytes([tid]) + bytes(t[b] for b in plain[1:])

    for tid, w in sorted(windows.items()):
        plain = bytearray(294)
        plain[42:294] = struct.pack('<126H', *w)
        loc['r'][tid] = (len(data), 294)
        data += record(tid, plain)
    for tid in sorted(windows):
        plain = bytearray(294)
        plain[0x0c] = 1 if tid in human else 0
        loc['t'][tid] = (len(data), 294)
        data += record(tid, plain)
    return bytes(data), loc


@pytest.fixture
def asn(monkeypatch):
    """build(windows, human) -> (bytes, loc) of a synthetic ASN, with aigm.locate pointed at its records."""
    def build(windows, human=()):
        data, loc = make_asn(windows, human)
        monkeypatch.setattr(aigm, 'locate', lambda _data: loc)
        return data, loc
    return build


A_WIN = win([101, 102], [101])
B_WIN = win([201, 202], [201])
TRADE = {'a': 1, 'b': 2, 'a_gives': 102, 'b_gives': 202, 'a_pos': '2B', 'b_pos': 'SS', 'b_drops': 201, 'a_drops': 101,
         'gain': 25.0}


def test_read_gives_each_window_deciphered_and_the_human_teams(asn):
    windows = {1: A_WIN, 2: B_WIN, 3: win([301, 302])}
    data, _ = asn(windows, human=(2,))
    assert aigm.read(data) == {'windows': windows, 'human': frozenset({2})}


def test_read_refuses_an_r_record_too_short_for_its_window(asn, monkeypatch):
    data, loc = asn({1: A_WIN})
    monkeypatch.setattr(aigm, 'locate', lambda _data: {'r': {1: (loc['r'][1][0], 100)}, 't': {}})
    with pytest.raises(ValueError):
        aigm.read(data)


def test_locate_keeps_the_live_r_and_t_records_by_their_key_byte(monkeypatch):
    data = bytearray(64)
    data[10], data[20], data[30], data[40], data[50] = 3, 0xFF, 40, 5, 7   # live r; deleted; out of range; live t; x
    members = [{'name': 'r.dat', 'kind': 'data', 'num': 1}, {'name': 't.dat', 'kind': 'data', 'num': 2},
               {'name': 'x.dat', 'kind': 'data', 'num': 3}, {'name': 'r.idx', 'kind': 'index', 'num': 4}]
    by_mem = {1: [types.SimpleNamespace(off=o, pl=6) for o in (10, 20, 30)],
              2: [types.SimpleNamespace(off=40, pl=6)],
              3: [types.SimpleNamespace(off=50, pl=6)],
              4: [types.SimpleNamespace(off=10, pl=6)]}
    monkeypatch.setattr(ctree, 'parse', lambda _d: (None, by_mem, members))
    assert aigm.locate(bytes(data)) == {'r': {3: (10, 6)}, 't': {5: (40, 6)}}


def test_apply_trade_swaps_both_players_and_their_lineup_places(asn):
    data, _ = asn({1: A_WIN, 2: B_WIN})
    after = aigm.read(aigm.apply_trade(data, TRADE))['windows']
    assert after == {1: win([101, 202], [202]), 2: win([201, 102], [102])}


def test_apply_trade_changes_only_the_two_windows_and_no_key_byte(asn):
    data, loc = asn({1: A_WIN, 2: B_WIN, 3: win([301])})
    new = aigm.apply_trade(data, TRADE)
    assert len(new) == len(data)
    changed = {i for i in range(len(data)) if data[i] != new[i]}
    inside = set()
    for tid in (1, 2):
        off = loc['r'][tid][0]
        inside |= set(range(off + 42, off + 294))
    assert changed and changed <= inside
    for off, _ in list(loc['r'].values()) + list(loc['t'].values()):
        assert new[off] == data[off]


def test_a_team_with_no_starter_at_the_position_gets_no_drop(asn):
    data, _ = asn({1: A_WIN, 2: win([201, 202])})
    after = aigm.read(aigm.apply_trade(data, dict(TRADE, b_drops=None)))['windows']
    assert after == {1: win([101, 202], [202]), 2: win([201, 102])}


@pytest.mark.parametrize('windows, trade', [
    # team 2 has no live r record
    ({1: A_WIN}, TRADE),
    # 150 is not on team 1's active roster
    ({1: A_WIN, 2: B_WIN}, dict(TRADE, a_gives=150)),
    # 103 is in team 1's lineup only, not on its active roster
    ({1: win([101, 102], [101, 103]), 2: B_WIN}, dict(TRADE, a_gives=103)),
    # 205 is not on team 2's active roster
    ({1: A_WIN, 2: B_WIN}, dict(TRADE, b_gives=205)),
    # 202 is on team 1 as well
    ({1: win([101, 102, 202], [101]), 2: B_WIN}, TRADE),
    # 102 is on team 2 as well
    ({1: A_WIN, 2: win([201, 202, 102], [201])}, TRADE),
    # 202 is on team 2's bench, not in its lineups
    ({1: A_WIN, 2: B_WIN}, dict(TRADE, b_drops=202)),
    # 102 is on team 1's bench, not in its lineups
    ({1: A_WIN, 2: B_WIN}, dict(TRADE, a_drops=102)),
    # 102 is on a third team too
    ({1: A_WIN, 2: B_WIN, 3: win([102])}, TRADE),
    # 202 is on a third team too
    ({1: A_WIN, 2: B_WIN, 3: win([202])}, TRADE),
])
def test_apply_trade_refuses_a_trade_that_does_not_fit(asn, windows, trade):
    data, _ = asn(windows)
    with pytest.raises(aigm.SwapError):
        aigm.apply_trade(data, trade)


# validate

def squad(tid, pitchers=5, hitters=20, lineup=9):
    """(players, window) for team tid: its pitchers and hitters on the active roster (the hitters cycle through the
    field positions), the first lineup hitters as its lineup, and one more hitter, 1130 + 1000 * tid, on no roster."""
    base = 1000 * tid
    pitcher_ids = [base + i for i in range(pitchers)]
    ids = [base + 100 + i for i in range(hitters)]
    players = {pid: pit(50) for pid in pitcher_ids}
    for i, pid in enumerate(ids):
        players[pid] = hit(aigm.HITTER_POS[i % len(aigm.HITTER_POS)], 50)
    players[base + 130] = hit('LF', 50)
    return players, win(pitcher_ids + ids, ids[:lineup])


def league_pair():
    p1, w1 = squad(1)
    p2, w2 = squad(2)
    return {**p1, **p2}, {1: w1, 2: w2}


def replaced(w, index, value):
    out = list(w)
    out[index] = value
    return out


def test_validate_passes_when_nothing_moved():
    players, windows = league_pair()
    assert aigm.validate(windows, windows, players) == []


def test_validate_passes_a_reserve_who_is_not_on_the_active_roster():
    players, windows = league_pair()
    after = {**windows, 1: replaced(windows[1], 25, 1130)}  # index 25 is a reserve's id
    assert aigm.validate(windows, after, players) == []


def test_validate_refuses_a_different_set_of_teams():
    players, windows = league_pair()
    assert aigm.validate(windows, {1: windows[1]}, players) == ['the teams changed']


def test_validate_refuses_a_changed_set_of_active_players():
    players, windows = league_pair()
    active = list(windows[1][:25])
    active[-1] = 1199                                   # a bench hitter swapped for an id no one has
    after = {**windows, 1: active + windows[1][25:]}
    assert aigm.validate(windows, after, players) == ['the active players changed']


def test_validate_refuses_an_id_on_two_teams():
    players, windows = league_pair()
    active = list(windows[2][:25])
    active[-1] = 1100                                   # team 1's starter, now on team 2 as well
    after = {**windows, 2: active + windows[2][25:]}
    problems = aigm.validate(windows, after, players)
    assert '1100 is on team 1 and team 2' in problems


def test_validate_refuses_a_change_in_the_number_of_active_pitchers():
    players, windows = league_pair()
    p1 = list(windows[1][:25])
    p2 = list(windows[2][:25])
    p1[4], p2[-1] = 2119, 1004                          # swap a pitcher and a hitter between the teams
    after = {1: p1 + windows[1][25:], 2: p2 + windows[2][25:]}
    problems = aigm.validate(windows, after, players)
    assert 'team 1 has 4 active pitchers, had 5' in problems and 'team 2 has 6 active pitchers, had 5' in problems


def test_validate_refuses_fewer_than_five_pitchers():
    p1, w1 = squad(1, pitchers=4, hitters=21)
    p2, w2 = squad(2)
    windows = {1: w1, 2: w2}
    assert aigm.validate(windows, windows, {**p1, **p2}) == ['team 1 has 4 active pitchers, needs 5']


def test_validate_refuses_fewer_than_eight_other_players():
    p1, w1 = squad(1, pitchers=5, hitters=7)
    p2, w2 = squad(2)
    windows = {1: w1, 2: w2}
    assert aigm.validate(windows, windows, {**p1, **p2}) == ['team 1 has 7 active non-pitchers, needs 8']


def test_validate_refuses_a_lineup_player_who_is_not_on_the_active_roster():
    players, windows = league_pair()
    after = {**windows, 1: replaced(windows[1], 60, 1130)}     # index 60 is past the reserves
    assert aigm.validate(windows, after, players) == [
        '1130 is in a lineup of team 1 but not on its active roster']


# the real association, when its files are on this machine

@pytest.mark.skipif(not os.path.exists(REAL), reason='the 1950 association is not on this machine')
def test_a_real_1950_association_plans_a_trade_that_applies_and_validates():
    with open(REAL, 'rb') as fh:
        data = fh.read()
    snap = aigm.read(data)
    assert len(snap['windows']) == 16
    pyr = gamedata.find(os.path.dirname(REAL), '16L1950.PYR')
    players = gamedata.players(pyr)
    year = gamedata.association(REAL)['season_year']
    found = aigm.plan(snap['windows'], players, year, snap['human'])
    assert found['trades']
    trade = found['trades'][0]
    after = aigm.read(aigm.apply_trade(data, trade))['windows']
    assert trade['a_gives'] in after[trade['b']] and trade['a_gives'] not in after[trade['a']]
    assert trade['b_gives'] in after[trade['a']] and trade['b_gives'] not in after[trade['b']]
    assert aigm.validate(snap['windows'], after, players) == []


# strength and the team modes

def teams_of(strengths):
    """(windows, players): one team per tid with one active hitter worth strengths[tid] (contact, born unknown)."""
    players = {100 + tid: hit('1B', s) for tid, s in strengths.items()}
    return {tid: win([100 + tid]) for tid in strengths}, players


def test_strength_is_the_sum_of_value_over_the_active_ids():
    players = {101: hit('SS', 60), 102: hit('2B', 70), 103: hit('1B', 99, born=1950), 104: pit(50)}
    windows = {1: win([101, 102, 999]), 2: win([103], [101]), 3: win([104])}  # 999 is no player; lineups do not count
    assert aigm.strength(windows, players, None) == {1: 130.0, 2: 99.0, 3: 50.0}
    assert aigm.strength(windows, players, 1977)[2] == pytest.approx(99 * 1.0)  # age 27
    assert aigm.strength(windows, players, 1975)[2] == pytest.approx(99 * 1.10)  # age 25


def test_offseason_modes_give_the_top_third_contend_and_the_bottom_third_rebuild():
    windows, players = teams_of({1: 50, 2: 60, 3: 20, 4: 40, 5: 30, 6: 10})
    assert aigm.offseason_modes(windows, players, None) == {2: 'contend', 1: 'contend', 4: 'neutral', 5: 'neutral',
                                                            3: 'rebuild', 6: 'rebuild'}


def test_offseason_modes_break_ties_by_the_lower_tid():
    windows, players = teams_of({1: 60, 2: 60, 3: 60, 4: 30, 5: 30, 6: 30})
    modes = aigm.offseason_modes(windows, players, None)
    assert [t for t in modes if modes[t] == 'contend'] == [1, 2]
    assert modes[3] == 'neutral' and modes[4] == 'neutral'
    assert [t for t in modes if modes[t] == 'rebuild'] == [5, 6]


@pytest.mark.parametrize('n, third', [(1, 0), (2, 0), (3, 1), (5, 1), (6, 2), (7, 2), (30, 10)])
def test_offseason_modes_split_len_over_three_each_way(n, third):
    windows, players = teams_of({tid: 10 * tid for tid in range(1, n + 1)})
    modes = list(aigm.offseason_modes(windows, players, None).values())
    assert (modes.count('contend'), modes.count('rebuild'), modes.count('neutral')) == (third, third, n - 2 * third)


def standings(*rows, league='N', division='E'):
    """{tid: team} from (tid, w, l) rows in one division."""
    return {tid: {'w': w, 'l': l, 'league': league, 'division': division} for tid, w, l in rows}


@pytest.mark.parametrize('wins, mode', [(60, 'contend'), (55, 'contend'), (54, 'neutral'), (49, 'neutral'),
                                        (48, 'rebuild'), (30, 'rebuild')])
def test_deadline_modes_split_at_five_and_twelve_games_back(wins, mode):
    teams = standings((1, 60, 40), (2, wins, 100 - wins))   # games back: 60 - wins
    assert aigm.deadline_modes(teams)[2] == mode


def test_deadline_games_back_counts_half_games_and_uses_both_wins_and_losses():
    teams = standings((1, 60, 40), (2, 56, 45), (3, 54, 45), (4, 47, 50), (5, 46, 50))
    modes = aigm.deadline_modes(teams)
    assert modes == {1: 'contend', 2: 'contend', 3: 'neutral', 4: 'neutral', 5: 'rebuild'}   # 0 4.5 5.5 11.5 12.0 back


def test_a_division_leader_contends_even_with_a_losing_record():
    teams = standings((1, 20, 40), (2, 10, 50))
    assert aigm.deadline_modes(teams) == {1: 'contend', 2: 'neutral'}


def test_deadline_modes_measure_against_the_leader_of_the_same_league_and_division():
    teams = {**standings((1, 60, 40), (2, 40, 60)), **standings((3, 40, 60), (4, 38, 62), league='N', division='W'),
             **standings((5, 80, 20), (6, 60, 40), league='A', division='E')}
    modes = aigm.deadline_modes(teams)
    assert modes == {1: 'contend', 2: 'rebuild', 3: 'contend', 4: 'contend', 5: 'contend', 6: 'rebuild'}


def test_deadline_modes_of_a_league_that_has_not_played_are_all_contend():
    assert set(aigm.deadline_modes(standings((1, 0, 0), (2, 0, 0))).values()) == {'contend'}


# mode_value

@pytest.mark.parametrize('age, contend, rebuild, neutral', [
    (None, 1.0, 1.0, 1.0), (19, 1.0, 1.25, 1.10), (26, 1.0, 1.25, 1.10), (27, 1.0, 1.0, 1.0), (30, 1.0, 1.0, 1.0),
    (31, 1.0, 0.6, 0.9), (33, 1.0, 0.6, 0.9), (34, 0.8, 0.6, 0.75), (40, 0.8, 0.6, 0.75)])
def test_mode_value_factors_at_every_age_edge(age, contend, rebuild, neutral):
    p = hit('SS', 100, born=1950)
    year = None if age is None else 1950 + age
    assert aigm.mode_value(p, year, 'contend') == pytest.approx(100 * contend)
    assert aigm.mode_value(p, year, 'rebuild') == pytest.approx(100 * rebuild)
    assert aigm.mode_value(p, year, 'neutral') == pytest.approx(100 * neutral)
    assert aigm.mode_value(p, year, 'neutral') == pytest.approx(aigm.value(p, year))


def test_mode_value_with_an_unknown_birth_is_the_index_in_every_mode():
    p = hit('1B', 66, born=None)
    assert [aigm.mode_value(p, 1977, m) for m in ('contend', 'rebuild', 'neutral')] == [66.0] * 3


def test_mode_value_of_a_pitcher_uses_his_index():
    p = pit(50, born=1950)
    p.update(strikeout=70, stamina=60)
    assert aigm.mode_value(p, 1950 + 22, 'rebuild') == pytest.approx(135 * 1.25)


# the scouting fog in planning

STEM = 'FOG77'


def fogged(n=200):
    return {pid: dict(hit('1B', 50), seasons=0) for pid in range(1000, 1000 + n)}


def test_without_a_stem_every_team_sees_the_true_player():
    players = fogged(20)
    view = aigm._View(players, 1977, None, {1: 'neutral', 2: 'neutral'})
    assert all(view.see(t, pid, own) == aigm.mode_value(players[pid], 1977, 'neutral')
               for t in (1, 2) for pid in players for own in (False, True))


def test_with_a_stem_a_team_sees_the_players_through_fog_view():
    players = fogged(20)
    view = aigm._View(players, 1977, STEM, {1: 'contend', 2: 'rebuild'})
    for pid in players:
        assert view.see(1, pid) == aigm.mode_value(fog.view(players[pid], STEM, 1, 1977, pid=pid), 1977, 'contend')
        assert view.see(2, pid, True) == aigm.mode_value(fog.view(players[pid], STEM, 2, 1977, own=True, pid=pid),
                                                         1977, 'rebuild')
    assert any(view.see(1, pid) != aigm.mode_value(players[pid], 1977, 'contend') for pid in players)


def test_a_teams_own_view_is_closer_to_the_truth_than_its_view_of_others():
    players = fogged()
    view = aigm._View(players, 1977, STEM, {1: 'neutral'})
    truth = aigm.mode_value(players[1000], 1977, 'neutral')

    def spread(own):
        errors = [view.see(1, pid, own) - truth for pid in players]
        return (sum(e * e for e in errors) / len(errors)) ** 0.5
    assert 0 < spread(True) < spread(False)
    assert spread(True) < 0.75 * spread(False)         # sd 4 against sd 8 before the cut off


def test_different_viewers_see_the_same_player_differently():
    players = fogged(50)
    view = aigm._View(players, 1977, STEM, {1: 'neutral', 2: 'neutral'})
    assert any(view.see(1, pid) != view.see(2, pid) for pid in players)
    assert [view.see(1, pid) for pid in players] == [aigm._View(players, 1977, STEM, {1: 'neutral'}).see(1, pid)
                                                     for pid in players]


def test_plan_with_a_stem_scores_each_side_from_its_own_fogged_view():
    players = {pid: dict(p, seasons=0) for pid, p in {101: hit('SS', 40), 102: hit('2B', 90), 201: hit('2B', 30),
                                                      202: hit('SS', 95)}.items()}
    stem = next(s for s in ('S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8')
                if aigm.plan(pair_windows(), players, None, stem=s)['trades'])
    (trade,) = aigm.plan(pair_windows(), players, None, stem=stem)['trades']
    seen = lambda pid, team, own: fog.view(players[pid], stem, team, None, own=own, pid=pid)['contact']   # noqa: E731
    expected = (seen(202, 1, False) - seen(101, 1, True)) + (seen(102, 2, False) - seen(201, 2, True))
    assert trade['gain'] == pytest.approx(expected, abs=0.01)
    assert trade['gain'] != aigm.plan(pair_windows(), players, None)['trades'][0]['gain']


def test_a_stem_of_none_plans_as_before():
    windows, players = human_scenario()
    assert aigm.plan(windows, players, 1977, human=frozenset({1}), stem=None) == \
        aigm.plan(windows, players, 1977, human=frozenset({1}))


# the mode in a trade

def test_a_rebuilding_side_values_the_young_player_it_gets_more_than_a_contender_does():
    # 6 teams, the four strong ones with catchers only (never traded): teams 5 and 6 are the two that rebuild and trade.
    players = {tid * 100 + i: hit('C', 99) for tid in range(1, 5) for i in range(1, 4)}
    windows = {tid: win([tid * 100 + 1, tid * 100 + 2, tid * 100 + 3]) for tid in range(1, 5)}
    players.update({501: hit('SS', 40, born=1950), 502: hit('2B', 90, born=1940),       # 502 is 37 in 1977
                    601: hit('2B', 30, born=1950), 602: hit('SS', 62, born=1960)})      # 602 is 17
    windows[5], windows[6] = win([501, 502], [501]), win([601, 602], [601])
    modes = aigm.offseason_modes(windows, players, 1977)
    assert modes[5] == modes[6] == 'rebuild'
    (trade,) = aigm.plan(windows, players, 1977)['trades']
    assert (trade['a'], trade['b'], trade['a_gives'], trade['b_gives']) == (5, 6, 502, 602)
    # team 5 gets the 17 year old: 62 * 1.25 against its SS starter 40; team 6 the 37 year old: 90 * 0.6 against its
    # 2B starter 30
    assert trade['gain'] == pytest.approx((62 * 1.25 - 40) + (90 * 0.6 - 30))
    assert trade['gain'] != pytest.approx((62 * 1.10 - 40) + (90 * 0.75 - 30))     # neutral valuations


def test_the_balance_is_on_the_true_values_whatever_the_modes():
    players = {tid * 100 + i: hit('C', 99) for tid in range(1, 5) for i in range(1, 4)}
    windows = {tid: win([tid * 100 + 1, tid * 100 + 2, tid * 100 + 3]) for tid in range(1, 5)}
    players.update({501: hit('SS', 40, born=1950), 502: hit('2B', 90, born=1940),
                    601: hit('2B', 30, born=1950), 602: hit('SS', 80, born=1960)})      # 80 * 1.10 = 88 against 67.5
    windows[5], windows[6] = win([501, 502], [501]), win([601, 602], [601])
    assert aigm.plan(windows, players, 1977)['trades'] == []


# pitcher swaps

def arms_league(low_a=60, spare_a=80, low_b=55, spare_b=75):
    """(players, windows): two squads (5 pitchers, 20 identical hitters, so no hitter trade) whose pitchers 0..3 are the
    rotation (controls low_*, +1, +2, +3) and pitcher 4 a spare in the bullpen (control spare_*)."""
    p1, w1 = squad(1)
    p2, w2 = squad(2)
    players, windows = {**p1, **p2}, {1: w1, 2: w2}
    for tid, low, spare in ((1, low_a, spare_a), (2, low_b, spare_b)):
        base = 1000 * tid
        for i in range(4):
            players[base + i] = pit(low + i)
        players[base + 4] = pit(spare)
        w = windows[tid]
        w[aigm.ROTATION[0]:aigm.ROTATION[0] + 4] = [base + i for i in range(4)]
        w[aigm.BULLPEN[0]] = base + 4
    return players, windows


PITCH_TRADE = {'a': 1, 'b': 2, 'a_gives': 1004, 'b_gives': 2004, 'a_pos': 'P', 'b_pos': 'P', 'b_drops': 2000,
               'a_drops': 1000, 'gain': 40.0}


def test_a_spare_pitcher_trades_for_a_spare_pitcher_who_beats_the_lowest_rotation_pitcher():
    players, windows = arms_league()
    assert aigm.plan(windows, players, None) == {'trades': [PITCH_TRADE], 'proposals': []}
    # team 1 gets the 75 for its 60 (15), team 2 the 80 for its 55 (25)


@pytest.mark.parametrize('kwargs', [dict(spare_a=58), dict(spare_b=55), dict(spare_a=80, spare_b=60),
                                    dict(spare_a=90, spare_b=75)])
def test_a_pitcher_must_beat_the_lowest_rotation_pitcher_and_stay_within_the_balance(kwargs):
    players, windows = arms_league(**kwargs)
    assert aigm.plan(windows, players, None)['trades'] == []    # 58 < 60 | 55 <= 55 | 80 v 60 | 90 v 75: not within 10%


def test_a_rotation_pitcher_is_never_traded():
    players, windows = arms_league()
    players[1003] = pit(95)                                     # team 1's best pitcher is in its rotation
    assert [t['a_gives'] for t in aigm.plan(windows, players, None)['trades']] == [1004]


def test_a_team_with_no_rotation_makes_no_pitcher_trade():
    players, windows = arms_league()
    windows[2][aigm.ROTATION[0]:aigm.ROTATION[1]] = [0] * 6
    assert aigm.plan(windows, players, None)['trades'] == []


def test_the_lowest_valued_rotation_pitcher_is_the_one_displaced_with_ties_to_the_lower_id():
    players, windows = arms_league()
    players[1002] = pit(60)                                     # ties 1000 for the lowest
    (trade,) = aigm.plan(windows, players, None)['trades']
    assert trade['a_drops'] == 1000


@pytest.mark.parametrize('hitter_values, kind', [((90, 85), 'hitter'), ((60, 55), 'pitcher')])
def test_a_pitcher_trade_and_a_hitter_trade_compete_for_the_one_trade_per_team(hitter_values, kind):
    players, windows = arms_league()                    # the pitcher trade is worth 40
    players.update({1190: hit('2B', hitter_values[0]), 2190: hit('SS', hitter_values[1])})
    windows[1][24], windows[2][24] = 1190, 2190         # a bench hitter each (the last active slot)
    trades = aigm.plan(windows, players, None)['trades']
    assert len(trades) == 1 and pairs(trades) == [(1, 2)]
    assert (trades[0]['a_pos'] == 'P') == (kind == 'pitcher')


def test_a_pitcher_swap_writes_the_rotation_the_bullpen_and_validates(asn):
    players, windows = arms_league()
    data, _ = asn(windows)
    after = aigm.read(aigm.apply_trade(data, PITCH_TRADE))['windows']
    r0, b0 = aigm.ROTATION[0], aigm.BULLPEN[0]
    w1 = after[1]
    assert w1[:5] == [1000, 1001, 1002, 1003, 2004]             # 2004 has 1004's active slot; 1000 keeps his
    assert w1[r0:r0 + 4] == [2004, 1001, 1002, 1003]            # 2004 takes 1000's rotation spot
    assert w1[b0] == 1000                                       # the bullpen slot 1004 left goes to the displaced one
    assert after[2][:5] == [2000, 2001, 2002, 2003, 1004]
    assert after[2][r0:r0 + 4] == [1004, 2001, 2002, 2003] and after[2][b0] == 2000
    assert aigm.validate(windows, after, players) == []
    for tid in (1, 2):                                          # the pitcher counts are unchanged
        assert sum(1 for v in after[tid][:25] if v in players and players[v]['pos'] == 'P') == 5
        listed = [v for v in after[tid][r0:r0 + 6] + after[tid][b0:b0 + 6] if v]
        assert len(listed) == len(set(listed))                  # nobody is in the rotation and the pen, or twice


def test_a_pitcher_swap_keeps_a_displaced_pitcher_who_has_a_bullpen_slot_of_his_own(asn):
    players, windows = arms_league()
    windows[1][aigm.BULLPEN[0] + 1] = 1000                      # 1000 is in the pen as well as the rotation
    data, _ = asn(windows)
    after = aigm.read(aigm.apply_trade(data, PITCH_TRADE))['windows']
    pen = after[1][aigm.BULLPEN[0]:aigm.BULLPEN[1]]
    assert pen == [1000, 0, 0, 0, 0, 0] and 2004 not in pen     # 1004's slot is emptied, the rest shift left


@pytest.mark.parametrize('trade', [
    dict(PITCH_TRADE, a_drops=None),                    # no rotation pitcher named
    dict(PITCH_TRADE, a_drops=1004),                    # not in team 1's rotation
    dict(PITCH_TRADE, b_drops=2100),                    # not in team 2's rotation
    dict(PITCH_TRADE, a_gives=1001),                    # 1001 is in team 1's rotation
    dict(PITCH_TRADE, b_gives=2001),                    # 2001 is in team 2's rotation
    dict(PITCH_TRADE, a_gives=1999),                    # not on team 1 at all
])
def test_a_pitcher_swap_that_does_not_fit_is_refused(asn, trade):
    players, windows = arms_league()
    data, _ = asn(windows)
    with pytest.raises(aigm.SwapError):
        aigm.apply_trade(data, trade)


# salaries

def three_teams():
    """Team 1 is strong (two catchers, never traded), team 2 middle and team 3 weak: so team 1 contends, 2 is neutral
    and 3 rebuilds. Teams 2 and 3 are pair_windows(): one trade, 102 for 202, worth a gain of 25."""
    players = {**pair_players(), 301: hit('C', 99), 302: hit('C', 99)}
    pair = pair_windows()
    windows = {1: win([301, 302]), 2: pair[1], 3: pair[2]}
    return players, windows


SALARIES = {102: 2.0, 202: 6.0, 101: 4.0, 201: 4.0, 301: 4.0, 302: 4.0}      # the median is 4.0


def test_the_three_team_fixture_has_a_contender_a_neutral_team_and_a_rebuilder():
    players, windows = three_teams()
    assert aigm.offseason_modes(windows, players, None) == {1: 'contend', 2: 'neutral', 3: 'rebuild'}
    (trade,) = aigm.plan(windows, players, None)['trades']
    assert (trade['a'], trade['b'], trade['a_gives'], trade['b_gives'], trade['gain']) == (2, 3, 102, 202, 25.0)


def test_a_rebuild_side_gains_for_the_salary_it_sheds():
    players, windows = three_teams()
    (trade,) = aigm.plan(windows, players, None, salaries=SALARIES)['trades']
    assert trade['gain'] == 25.0 + 2.0 * (6.0 - 2.0) / 4.0      # team 3 gives 202 (6.0) for 102 (2.0)


def test_a_rebuild_side_loses_for_the_salary_it_takes_on():
    players, windows = three_teams()
    (trade,) = aigm.plan(windows, players, None, salaries={**SALARIES, 102: 6.0, 202: 2.0})['trades']
    assert trade['gain'] == 25.0 + 2.0 * (2.0 - 6.0) / 4.0


def test_only_a_rebuild_side_weighs_salary():
    players, windows = three_teams()
    swapped = {**SALARIES, 102: 6.0, 202: 2.0}            # team 2 (neutral) sheds 6.0 and takes on 2.0
    (trade,) = aigm.plan(windows, players, None, salaries=swapped)['trades']
    assert trade['gain'] == 25.0 + 2.0 * (2.0 - 6.0) / 4.0      # only team 3's term
    two = aigm.plan(pair_windows(), pair_players(), None, salaries=SALARIES)['trades']
    assert two[0]['gain'] == 25.0                               # two teams are both neutral


def test_missing_salaries_are_ignored():
    players, windows = three_teams()
    for salaries in (None, {}, {202: 6.0}, {102: 2.0}, {101: 1.0}):
        (trade,) = aigm.plan(windows, players, None, salaries=salaries)['trades']
        assert trade['gain'] == 25.0, salaries


def test_salary_relief_can_turn_a_downgrade_into_a_trade_for_a_rebuild_side():
    """Team 3 is the strongest (it contends), team 2 the weakest (it rebuilds). Team 2 would get a 65 SS for its 66 SS
    starter, a loss of 1, but sheds 9.0 of salary for 1.0 (median 4.0): 2 * 8 / 4 = 4."""
    players = {**pair_players(), 301: hit('C', 99), 302: hit('C', 99), 303: hit('C', 99), 304: hit('C', 99)}
    players[101] = hit('SS', 66)
    pair = pair_windows()
    windows = {1: win([301, 302]), 2: pair[1], 3: win([201, 202, 303, 304], [201])}
    assert aigm.offseason_modes(windows, players, None) == {1: 'neutral', 2: 'rebuild', 3: 'contend'}
    salaries = {101: 4.0, 102: 9.0, 201: 4.0, 202: 1.0, 301: 4.0, 302: 4.0}
    assert aigm.plan(windows, players, None)['trades'] == []
    assert aigm.plan(windows, players, None, salaries={**salaries, 102: 1.0, 202: 9.0})['trades'] == []
    (trade,) = aigm.plan(windows, players, None, salaries=salaries)['trades']
    assert (trade['a'], trade['b'], trade['a_gives'], trade['b_gives']) == (2, 3, 102, 202)
    assert trade['gain'] == (65 - 66 + 4.0) + (70 - 50)          # team 3 contends: no salary term for it
