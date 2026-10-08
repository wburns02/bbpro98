import copy
import json
from pathlib import Path

import pytest

from lahman.structure import SHAPES, plan

FIXTURE = {int(y): teams for y, teams in json.loads(
    Path(__file__).with_name('teams_fixture.json').read_text()).items()}

# year: (template, filler slots, dropped teamIDs, cost)
EXPECTED = {
    1871: ('T10', 1, [], 1),
    1872: ('T12', 1, [], 1),
    1874: ('T8', 0, [], 0),
    1875: ('T14_77', 1, [], 1),
    1876: ('T8', 0, [], 0),
    1877: ('T8', 2, [], 2),
    1882: ('T16_2L', 2, [], 2),
    1884: ('T34', 2, ['RIC'], 4),
    1890: ('T26_8_8_10', 1, [], 1),
    1891: ('T18', 1, [], 1),
    1892: ('T12', 0, [], 0),
    1901: ('T16_2L', 0, [], 0),
    1914: ('T24_3x8', 0, [], 0),
    1961: ('T18', 0, [], 0),
    1962: ('T20', 0, [], 0),
    1969: ('T24_2x12', 0, [], 0),
    1977: ('T26_12_14', 0, [], 0),
    1993: ('T28_77', 0, [], 0),
    1994: ('T28_554', 0, [], 0),
    1998: ('T30', 0, [], 0),
    2013: ('T30', 0, [], 0),
}

EAST_SET = {'BLN', 'BRO', 'BSN', 'NY1', 'PHI', 'WAS'}


def fillers(p):
    return sum(count_fillers(lg['divisions']) for lg in p['leagues'])


def count_fillers(divisions):
    return sum(d.count(None) for d in divisions)


def league(p, lg_id):
    return next(lg for lg in p['leagues'] if lg['lgID'] == lg_id)


@pytest.mark.parametrize('year', sorted(EXPECTED))
def test_expected_template_fillers_dropped_and_cost(year):
    key, n_fillers, dropped, cost = EXPECTED[year]
    p = plan(FIXTURE[year], year)
    assert p['template'] == key
    assert fillers(p) == n_fillers
    assert p['dropped'] == dropped
    assert p['cost'] == cost


@pytest.mark.parametrize('year', sorted(FIXTURE))
def test_division_sizes_equal_template(year):
    p = plan(FIXTURE[year], year)
    shape = SHAPES[p['template']]
    assert len(p['leagues']) == len(shape)
    for lg, sizes in zip(p['leagues'], shape):
        assert [len(d) for d in lg['divisions']] == sizes


@pytest.mark.parametrize('year', sorted(FIXTURE))
def test_every_real_team_placed_once_and_cost_adds_up(year):
    p = plan(FIXTURE[year], year)
    placed = [t for lg in p['leagues'] for d in lg['divisions'] for t in d if t is not None]
    assert sorted(placed + p['dropped']) == sorted(t['teamID'] for t in FIXTURE[year])
    assert len(set(placed)) == len(placed)
    assert p['cost'] == fillers(p) + 2 * len(p['dropped'])


def test_1882_both_fillers_sit_in_aa():
    p = plan(FIXTURE[1882], 1882)
    assert count_fillers(league(p, 'AA')['divisions']) == 2
    assert count_fillers(league(p, 'NL')['divisions']) == 0


def test_1884_drops_ric_and_nl_gets_the_fillers():
    p = plan(FIXTURE[1884], 1884)
    assert p['dropped'] == ['RIC']
    assert count_fillers(league(p, 'NL')['divisions']) == 2
    assert count_fillers(league(p, 'AA')['divisions']) == 0


def test_1892_division_one_is_the_east_set():
    p = plan(FIXTURE[1892], 1892)
    (nl,) = p['leagues']
    assert nl['lgID'] == 'NL'
    assert set(nl['divisions'][0]) == EAST_SET
    assert set(nl['divisions'][1]) == set(t['teamID'] for t in FIXTURE[1892]) - EAST_SET


def test_1998_nl_divisions_follow_ordering_rule():
    p = plan(FIXTURE[1998], 1998)
    nl_teams = [t for t in FIXTURE[1998] if t['lgID'] == 'NL']
    east = sorted(t['teamID'] for t in nl_teams if t['divID'] == 'E')
    cen = sorted(t['teamID'] for t in nl_teams if t['divID'] == 'C')
    west = sorted(t['teamID'] for t in nl_teams if t['divID'] == 'W')
    assert league(p, 'NL')['divisions'] == [east + cen[:3], cen[3:] + west]


def test_2013_houston_moves_to_nl():
    p = plan(FIXTURE[2013], 2013)
    assert 'HOU' in [t for d in league(p, 'NL')['divisions'] for t in d]
    assert 'HOU' not in [t for d in league(p, 'AL')['divisions'] for t in d]


def test_1993_and_1994_pick_the_matching_division_count():
    assert plan(FIXTURE[1993], 1993)['template'] == 'T28_77'
    assert plan(FIXTURE[1994], 1994)['template'] == 'T28_554'


def test_plan_does_not_mutate_its_input():
    snapshot = copy.deepcopy(FIXTURE)
    for year in sorted(FIXTURE):
        plan(FIXTURE[year], year)
    assert FIXTURE == snapshot


def test_drop_order_fewest_g_then_highest_team_id():
    # 15 NL teams: one slot short of T14. Equal G drops the highest teamID; a lower G drops first.
    teams = [{'teamID': f'T{i:02d}', 'lgID': 'NL', 'divID': '', 'G': 50} for i in range(1, 16)]
    p = plan(teams, 1900)
    assert p['template'] == 'T14_77'
    assert p['dropped'] == ['T15']
    teams[2]['G'] = 40  # T03 now has the fewest G
    assert plan(teams, 1900)['dropped'] == ['T03']


def test_too_many_leagues_raises():
    teams = [{'teamID': f'{lg}{i}', 'lgID': lg, 'divID': '', 'G': 10} for lg in 'ABCD' for i in range(8)]
    with pytest.raises(ValueError):
        plan(teams, 1900)
