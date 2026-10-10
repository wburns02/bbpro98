"""aigm.py: the age factor and the value; plan (the best trades, ties, MAX_TRADES, one trade per team, the balance, the
need, catchers and pitchers never traded, proposals only for human teams and never on a chosen trade's players,
MAX_PROPOSALS, the inputs left alone); read and apply_trade on synthetic ASN bytes (locate is pointed at the records,
the cipher seed is at 0x310-0x311); locate's filter on a fake ctree.parse; validate (each problem); and one check on the
real 1950 association, which skips when its files are not on the machine.
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
