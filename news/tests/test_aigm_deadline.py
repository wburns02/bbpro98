"""aigm's July deadline: deadline_window (its edges), deadline_plan (the contender and rebuilder pairs, the veteran who
would start, the prospect, both sides receiving 0.9 of what they give, the age and slot rules, hitter and pitcher kinds,
best gain first, one trade per team, MAX_TRADES, proposals for human teams, the fog, the inputs left alone) and
apply_deadline (roster.move twice), on synthetic windows with the real layout (alignments, rotation, bullpen, reserves).
"""
import copy
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aigm        # noqa: E402
import fog         # noqa: E402
import roster      # noqa: E402
from tests.test_aigm import hit, pit, standings, win    # noqa: E402

YEAR = 2000
POS = aigm.ALIGN_POS        # C 1B 2B 3B SS LF CF RF
STEM = 'DL77'


def pid_of(tid, pos):
    """The id of team tid's starter at pos (see team)."""
    return 100 * tid + 1 + POS.index(pos)


def bench_of(tid):
    return 100 * tid + 9


def ace_of(tid):
    """The first pitcher of team tid's rotation."""
    return 100 * tid + 21


def arm_of(tid):
    """The first pitcher of team tid's bullpen."""
    return 100 * tid + 26


def spare_of(tid, i=0):
    """A free id for a reserve of team tid."""
    return 100 * tid + 31 + i


def team(tid, reserves=()):
    """(players, window) of team tid, base 100 * tid: starters base + 1..8 at C 1B 2B 3B SS LF CF RF (contact 50, age
    28) in both batting orders and alignments, a bench LF base + 9 (contact 40), a rotation base + 21..25 (control 50),
    a bullpen base + 26, 27 (control 40) and the given reserve ids (pairs from index 25, level 1). A clean roster:
    9 hitters and 7 pitchers active, no roster.problems."""
    base = 100 * tid
    starters = [base + 1 + i for i in range(len(POS))]
    rotation = [base + 21 + i for i in range(5)]
    pen = [base + 26, base + 27]
    players = {pid: hit(pos, 50, born=YEAR - 28) for pid, pos in zip(starters, POS)}
    players[base + 9] = hit('LF', 40, born=YEAR - 28)
    players.update({pid: pit(50, born=YEAR - 28) for pid in rotation})
    players.update({pid: pit(40, born=YEAR - 28) for pid in pen})
    w = win(starters + [base + 9] + rotation + pen)
    for i, pid in enumerate(reserves):
        w[aigm.ACTIVE + 2 * i], w[aigm.ACTIVE + 2 * i + 1] = pid, 1
    for start in aigm.ORDERS + aigm.ALIGNS:
        w[start:start + 9] = starters + [0]
    w[aigm.ROTATION[0]:aigm.ROTATION[0] + 5] = rotation
    w[aigm.BULLPEN[0]:aigm.BULLPEN[0] + 2] = pen
    return players, w


def league(tids=(1, 2, 3)):
    """(players, windows) of the teams in tids."""
    players, windows = {}, {}
    for tid in tids:
        p, w = team(tid)
        players.update(p)
        windows[tid] = w
    return players, windows


def age(players, pid, years, rating=None):
    """players[pid] made `years` old in YEAR, and given contact (hitter) or control (pitcher) `rating` when given."""
    players[pid]['born'] = YEAR - years
    if rating is not None:
        players[pid]['control' if players[pid]['pos'] == 'P' else 'contact'] = rating


TEAMS = standings((1, 60, 40), (2, 40, 60), (3, 52, 48))    # contend, rebuild (20 back), neutral (8 back)
FIRST = {'c': 1, 'r': 2, 'vet': pid_of(2, '1B'), 'prospect': bench_of(1), 'gain': 49.5, 'kind': 'deadline'}


def deal(players):
    """Team 2's 1B (80, age 32) for team 1's bench LF (70, age 22): FIRST."""
    age(players, pid_of(2, '1B'), 32, 80)
    age(players, bench_of(1), 22, 70)
    return players


def plan(players, windows, teams=TEAMS, **kw):
    return aigm.deadline_plan(windows, players, YEAR, teams, **kw)


def trade_keys(found):
    return [(t['c'], t['r'], t['vet'], t['prospect']) for t in found['trades']]


# the window

def games(total, played):
    return [{'away': 1, 'home': 2, 'played': i < played} for i in range(total)]


@pytest.mark.parametrize('total, played, inside', [
    (20, 10, False), (20, 11, True), (20, 12, True), (20, 13, True), (20, 14, False),
    (200, 109, False), (200, 110, True), (200, 130, True), (200, 131, False),
    (100, 0, False), (100, 100, False)])
def test_the_deadline_window_is_55_to_65_percent_of_the_schedule_both_ends_in(total, played, inside):
    assert aigm.deadline_window({'games': games(total, played)}) is inside


def test_the_window_is_the_mean_of_each_teams_share_not_the_share_of_all_games():
    # teams 1 and 2 have played 4 of 4 and teams 3 and 4 18 of 36: 22 of 40 games (0.55), but a mean share of 0.75
    g = games(4, 4) + [{'away': 3, 'home': 4, 'played': i < 18} for i in range(36)]
    assert aigm.deadline_window({'games': g}) is False
    g = games(4, 2) + [{'away': 3, 'home': 4, 'played': i < 24} for i in range(36)]      # 0.5 and 0.667: mean 0.583
    assert aigm.deadline_window({'games': g}) is True


@pytest.mark.parametrize('assoc', [{}, {'games': []}, {'games': [{'played': True}] * 4}])
def test_a_league_with_no_scheduled_game_is_outside_the_window(assoc):
    assert aigm.deadline_window(assoc) is False


# the plan

def test_a_contender_buys_a_rebuilding_teams_veteran_for_its_prospect():
    players, windows = league()
    deal(players)
    found = plan(players, windows)
    assert found == {'trades': [FIRST], 'proposals': []}
    # team 1 gets 80 for 70 (+10); team 2 (rebuild) gets 70 * 1.25 for 80 * 0.6 (+39.5)


def test_the_plan_is_deterministic_and_never_changes_its_inputs():
    players, windows = league()
    deal(players)
    before_w, before_p, before_t = copy.deepcopy(windows), copy.deepcopy(players), copy.deepcopy(TEAMS)
    first = plan(players, windows, human=frozenset({3}))
    assert plan(players, windows, human=frozenset({3})) == first
    assert windows == before_w and players == before_p and TEAMS == before_t


def test_only_a_contender_and_a_rebuilder_trade():
    players, windows = league((1, 2, 3, 4))
    deal(players)
    age(players, pid_of(3, '2B'), 33, 90)                      # a neutral team's veteran who would start for team 1
    teams = standings((1, 60, 40), (2, 40, 60), (3, 52, 48), (4, 59, 41))     # 4 is a second contender
    age(players, bench_of(4), 22, 70)
    found = plan(players, windows, teams)
    assert trade_keys(found) == [(1, 2, pid_of(2, '1B'), bench_of(1))]


def test_two_contenders_do_not_trade():
    players, windows = league()
    deal(players)
    assert plan(players, windows, standings((1, 60, 40), (2, 59, 41)))['trades'] == []


def test_a_neutral_team_is_no_partner_on_either_side():
    players, windows = league()
    deal(players)
    age(players, bench_of(1), 40)                               # the contender has no prospect now ...
    age(players, bench_of(3), 22, 70)                           # ... the neutral team 3 does
    assert plan(players, windows)['trades'] == []
    players, windows = league()
    age(players, pid_of(3, '1B'), 32, 80)                       # the neutral team has the veteran, team 1 a prospect
    age(players, bench_of(1), 22, 70)
    assert plan(players, windows)['trades'] == []


def test_the_rebuilder_sells_the_veteran_and_the_contender_the_prospect_not_the_other_way():
    players, windows = league()
    age(players, pid_of(1, '1B'), 32, 80)                       # the contender has the veteran ...
    age(players, bench_of(2), 22, 70)                           # ... and the rebuilder the prospect
    assert plan(players, windows)['trades'] == []


@pytest.mark.parametrize('years, traded', [(28, False), (29, True), (35, True)])
def test_a_veteran_is_29_or_older(years, traded):
    players, windows = league()
    deal(players)
    age(players, pid_of(2, '1B'), years)
    assert bool(plan(players, windows)['trades']) is traded


@pytest.mark.parametrize('years, traded', [(20, True), (26, True), (27, False)])
def test_a_prospect_is_26_or_younger(years, traded):
    players, windows = league()
    deal(players)
    age(players, bench_of(1), years)
    assert bool(plan(players, windows)['trades']) is traded


@pytest.mark.parametrize('rating, traded', [(50, False), (51, True)])
def test_the_veteran_must_beat_the_alignment_player_at_his_position(rating, traded):
    players, windows = league()
    deal(players)
    age(players, pid_of(2, '1B'), 32, rating)                   # team 1's 1B starter is 50
    age(players, bench_of(1), 22, 45)
    assert bool(plan(players, windows)['trades']) is traded


def test_a_veteran_at_a_position_the_contender_has_no_alignment_player_for_is_not_wanted():
    players, windows = league()
    deal(players)
    for start in aigm.ALIGNS:
        windows[1][start + POS.index('1B')] = 0
    assert plan(players, windows)['trades'] == []


@pytest.mark.parametrize('prospect, traded', [(88, True), (89, False)])
def test_the_contender_must_receive_nine_tenths_of_what_it_gives(prospect, traded):
    players, windows = league()
    deal(players)
    age(players, bench_of(1), 22, prospect)                     # team 1 gets 80 and gives 88: 80 >= 79.2; 89: 80 < 80.1
    assert bool(plan(players, windows)['trades']) is traded


@pytest.mark.parametrize('prospect, traded', [(57, False), (58, True)])
def test_the_rebuilder_must_receive_nine_tenths_of_what_it_gives(prospect, traded):
    players, windows = league()
    deal(players)
    age(players, pid_of(2, '1B'), 29, 80)                       # rebuild values age 29 at 1.0: gives 80, needs 72
    age(players, bench_of(1), 22, prospect)                     # gets prospect * 1.25: 71.25 against 72.5
    assert bool(plan(players, windows)['trades']) is traded


def test_the_prospect_comes_from_the_bench_or_the_reserves_not_the_lineup_or_rotation():
    players, windows = league()
    deal(players)
    age(players, bench_of(1), 40)                               # the bench hitter is no prospect now
    age(players, pid_of(1, 'LF'), 22, 70)                       # a young starter: in the alignments, so not for sale
    assert plan(players, windows)['trades'] == []
    players[spare_of(1)] = hit('LF', 70, born=YEAR - 22)        # a young reserve is
    p, w = team(1, reserves=[spare_of(1)])
    windows[1] = w
    found = plan(players, windows)
    assert [t['prospect'] for t in found['trades']] == [spare_of(1)]


def test_the_veteran_must_be_on_the_active_roster():
    players, windows = league()
    deal(players)
    players[spare_of(2)] = hit('1B', 99, born=YEAR - 33)        # a better veteran, but only a reserve
    p, w = team(2, reserves=[spare_of(2)])
    windows[2] = w
    deal(players)
    assert [t['vet'] for t in plan(players, windows)['trades']] == [pid_of(2, '1B')]


def test_a_pitcher_is_traded_for_a_pitcher_who_beats_the_lowest_rotation_pitcher():
    players, windows = league()
    age(players, ace_of(2), 32, 90)                             # team 2's rotation ace; team 1's lowest rotation is 50
    age(players, arm_of(1), 22, 70)                                  # team 1's bullpen arm
    found = plan(players, windows)
    assert trade_keys(found) == [(1, 2, ace_of(2), arm_of(1))]
    assert found['trades'][0]['gain'] == pytest.approx((90 - 70) + (70 * 1.25 - 90 * 0.6))


def test_a_pitcher_who_does_not_beat_the_rotation_is_not_wanted_and_kinds_do_not_mix():
    players, windows = league()
    age(players, ace_of(2), 32, 50)                                  # 50 does not beat 50
    age(players, arm_of(1), 22, 40)
    assert plan(players, windows)['trades'] == []
    players, windows = league()
    deal(players)
    age(players, bench_of(1), 40)
    age(players, arm_of(1), 22, 60)                             # the only prospect is a pitcher, the veteran a hitter
    assert plan(players, windows)['trades'] == []


def test_a_young_rotation_pitcher_is_not_a_prospect():
    players, windows = league()
    age(players, ace_of(2), 32, 90)
    age(players, ace_of(1), 22, 70)                                  # in team 1's rotation
    assert plan(players, windows)['trades'] == []


def test_the_best_gain_goes_first_and_each_team_trades_once():
    players, windows = league((1, 2, 3, 4))
    deal(players)
    age(players, pid_of(4, '1B'), 32, 90)
    age(players, bench_of(3), 22, 70)
    teams = standings((1, 60, 40), (2, 40, 60), division='E') | standings((3, 60, 40), (4, 40, 60), division='W')
    found = plan(players, windows, teams)
    # (c, r) = (1, 4) and (3, 4) tie at 53.5 and the lower c wins; then team 4 is used and (3, 2) is left at 49.5
    assert trade_keys(found) == [(1, 4, pid_of(4, '1B'), bench_of(1)), (3, 2, pid_of(2, '1B'), bench_of(3))]
    assert [t['gain'] for t in found['trades']] == [53.5, 49.5]
    assert len({tid for t in found['trades'] for tid in (t['c'], t['r'])}) == 4


def test_no_more_than_max_trades_are_made():
    n = aigm.MAX_TRADES + 1
    tids = range(1, 2 * n + 1)
    players, windows = league(tids)
    rows = {}
    for k in range(n):
        c, r = 2 * k + 1, 2 * k + 2
        age(players, pid_of(r, '1B'), 32, 80 + k)               # the later the rebuilder, the better his veteran
        age(players, bench_of(c), 22, 70)
        rows |= standings((c, 60, 40), (r, 40, 60), division='D%d' % k)
    found = plan(players, windows, rows)
    assert len(found['trades']) == aigm.MAX_TRADES
    # every contender offers the same prospect, so the six best veterans (the last six rebuilders) go to contenders
    # 1, 3, ...
    assert [(t['c'], t['r']) for t in found['trades']] == [(2 * i + 1, 2 * (n - i)) for i in range(aigm.MAX_TRADES)]


def test_a_trade_that_cannot_be_made_is_left_out():
    players, windows = league()
    deal(players)
    windows[2][8] = 0                                           # team 2 has no bench hitter to refill the 1B slot
    assert plan(players, windows)['trades'] == []


def test_an_unknown_year_makes_no_trade():
    players, windows = league()
    deal(players)
    assert aigm.deadline_plan(windows, players, None, TEAMS)['trades'] == []


# human teams

def crowd():
    """Team 2 (rebuild) has four 1B/2B/3B/SS veterans (80, age 32); team 1 (contend) four prospects (70, age 22):
    the bench LF and three reserves."""
    players, windows = league()
    p, windows[1] = team(1, reserves=[spare_of(1, i) for i in range(3)])
    for i in range(3):
        players[spare_of(1, i)] = hit('LF', 70, born=YEAR - 22)
    age(players, bench_of(1), 22, 70)
    for pos in ('1B', '2B', '3B', 'SS'):
        age(players, pid_of(2, pos), 32, 80)
    return players, windows


def test_a_human_contender_gets_proposals_instead_of_trades():
    players, windows = crowd()
    found = plan(players, windows, human=frozenset({1}))
    assert found['trades'] == []
    assert len(found['proposals']) == aigm.MAX_PROPOSALS
    assert all(p['c'] == 1 and p['r'] == 2 and p['kind'] == 'deadline' for p in found['proposals'])
    seen = [x for p in found['proposals'] for x in (p['vet'], p['prospect'])]
    assert len(seen) == len(set(seen))                          # no player is in two proposals


def test_a_human_rebuilder_gets_proposals_too():
    players, windows = crowd()
    found = plan(players, windows, human=frozenset({2}))
    assert found['trades'] == [] and len(found['proposals']) == aigm.MAX_PROPOSALS
    assert all(p['r'] == 2 and p['c'] == 1 for p in found['proposals'])


def test_two_human_teams_make_no_deal_with_each_other():
    players, windows = crowd()
    assert plan(players, windows, human=frozenset({1, 2})) == {'trades': [], 'proposals': []}


def test_a_neutral_human_team_gets_no_proposal():
    players, windows = crowd()
    assert plan(players, windows, human=frozenset({3}))['proposals'] == []


def test_a_proposal_never_uses_a_player_of_a_chosen_trade():
    players, windows = league((1, 2, 3, 4))
    deal(players)                                               # teams 3 and 4 trade (3 contends, 4 rebuilds)
    p, windows[1] = team(1, reserves=[spare_of(1)])
    players[spare_of(1)] = hit('LF', 70, born=YEAR - 22)
    age(players, pid_of(4, '2B'), 33, 85)
    age(players, pid_of(4, '1B'), 32, 99)
    age(players, bench_of(3), 22, 70)
    teams = standings((1, 60, 40), (2, 40, 60), division='E') | standings((3, 60, 40), (4, 40, 60), division='W')
    found = plan(players, windows, teams, human=frozenset({1}))
    taken = {x for t in found['trades'] for x in (t['vet'], t['prospect'])}
    assert found['trades'] and found['proposals']
    for prop in found['proposals']:
        assert prop['c'] == 1 and {prop['vet'], prop['prospect']}.isdisjoint(taken)


# the fog

def test_with_a_stem_each_side_scores_the_deal_through_its_own_fogged_view():
    players, windows = league()
    age(players, pid_of(2, '1B'), 32, 95)
    age(players, pid_of(1, '1B'), 28, 40)
    age(players, bench_of(1), 22, 70)

    def seen(pid, viewer, mode, own):
        return aigm.mode_value(fog.view(players[pid], STEM, viewer, YEAR, own=own, pid=pid), YEAR, mode)
    vet, pro = pid_of(2, '1B'), bench_of(1)
    expected = (seen(vet, 1, 'contend', False) - seen(pro, 1, 'contend', True)
                + seen(pro, 2, 'rebuild', False) - seen(vet, 2, 'rebuild', True))
    found = plan(players, windows, stem=STEM)
    assert trade_keys(found) == [(1, 2, vet, pro)]
    assert found['trades'][0]['gain'] == pytest.approx(expected, abs=0.01)
    assert found['trades'][0]['gain'] != plan(players, windows)['trades'][0]['gain']
    assert plan(players, windows, stem=STEM) == found


def test_without_a_stem_the_plan_sees_the_true_ratings():
    players, windows = league()
    deal(players)
    assert plan(players, windows, stem=None) == plan(players, windows)


# apply_deadline

def test_apply_deadline_moves_the_veteran_to_the_contender_and_the_prospect_to_the_rebuilder():
    players, windows = league()
    deal(players)
    before = copy.deepcopy(windows)
    after = aigm.apply_deadline(windows, FIRST, players, YEAR)
    vet, pro = FIRST['vet'], FIRST['prospect']
    assert windows == before                                    # the input is not changed
    assert vet in after[1][:25] and vet not in after[2] and pro in after[2][:25] and pro not in after[1]
    assert after[1][aigm.ALIGNS[0] + POS.index('1B')] == vet     # he starts at 1B for team 1
    assert roster.problems(after, players) == []


def test_apply_deadline_is_two_roster_moves(monkeypatch):
    calls = []

    def move(windows, pid, src, dst, players, year):
        calls.append((pid, src, dst, year))
        return windows
    monkeypatch.setattr(roster, 'move', move)
    aigm.apply_deadline({}, FIRST, {}, YEAR)
    assert calls == [(FIRST['vet'], 2, 1, YEAR), (FIRST['prospect'], 1, 2, YEAR)]


def test_apply_deadline_refuses_a_trade_whose_players_have_moved():
    players, windows = league()
    deal(players)
    moved = roster.move(windows, FIRST['vet'], 2, 3, players, YEAR)
    with pytest.raises(aigm.SwapError):
        aigm.apply_deadline(moved, FIRST, players, YEAR)
    with pytest.raises(aigm.SwapError):
        aigm.apply_deadline({1: windows[1]}, FIRST, players, YEAR)


# a whole league

def random_league(seed, n=12):
    """(players, windows, teams): n teams of the standard roster with random ratings and ages, and random records."""
    rng = random.Random(seed)
    players, windows, teams = league(range(1, n + 1)) + ({},)
    for pid, p in players.items():
        age(players, pid, rng.randint(19, 38), rng.randint(30, 95))
    for tid in windows:
        w, l = rng.randint(20, 70), rng.randint(20, 70)
        teams[tid] = {'w': w, 'l': l, 'league': 'N' if tid % 2 else 'A', 'division': 'E' if tid % 4 < 2 else 'W'}
    return players, windows, teams


@pytest.mark.parametrize('seed', range(8))
def test_a_whole_league_plans_valid_deadline_trades(seed):
    players, windows, teams = random_league(seed)
    modes = aigm.deadline_modes(teams)
    human = frozenset({1, 2})
    found = plan(players, windows, teams, human=human, stem=STEM)
    assert found == plan(players, windows, teams, human=human, stem=STEM)
    assert len(found['trades']) <= aigm.MAX_TRADES
    used = [tid for t in found['trades'] for tid in (t['c'], t['r'])]
    assert len(used) == len(set(used)) and not set(used) & human
    after = windows
    for t in found['trades']:
        assert modes[t['c']] == 'contend' and modes[t['r']] == 'rebuild'
        after = aigm.apply_deadline(after, t, players, YEAR)
    assert set(roster.problems(after, players)) <= set(roster.problems(windows, players))
    for h in human:
        mine = [p for p in found['proposals'] if h in (p['c'], p['r'])]
        assert len(mine) <= aigm.MAX_PROPOSALS
        assert all(modes[p['c']] == 'contend' and modes[p['r']] == 'rebuild' and not {p['c'], p['r']} - {h} & human
                   for p in mine)
