"""contracts: pricing, deciles, service, the update of contract state and the payroll rows. The table is flat (every year
$1M) with a ratio by class: pre 0.5, arb 1.0, fa 2.0, so a salary is $500K, $1M or $2M."""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import contracts as C  # noqa: E402


def cell(ratio):
    return {r: {c: [ratio[c]] * 10 for c in C.CLASSES} for r in ('bat', 'pit')}


TABLE = {'source': 'test', 'years': {str(y): 1000000 for y in range(1985, 2017)},
         'ratio': cell({'pre': 0.5, 'arb': 1.0, 'fa': 2.0})}


def player(name, pos='RF', born=1970, contact=50, power=50, speed=50, stamina=50, control=50, strikeout=50,
           fielding=50):
    """A player as gamedata.players() gives him."""
    return {'name': name, 'pos': pos, 'born': born, 'bats': 'R', 'throws': 'R', 'contact': contact, 'power': power,
            'speed': speed, 'stamina': stamina, 'control': control, 'strikeout': strikeout, 'fielding': fielding}


# Ratings are all 50, so the ranks inside a role are by pid. Batters 100, 300, 400 are deciles 1, 4, 7; pitchers 101,
# 200 are deciles 1, 6.
PLAYERS = {100: player('Al Winner', 'RF', 1970), 101: player('Joe Old', 'P', 1960),
           200: player('Bo Loser', 'P', 1975), 300: player('Pat Smith', 'SS', 1971),
           400: player('Ann Bat', '1B', 1966)}
ROSTERS = {1: [100, 101], 2: [200, 400]}


def assoc(rosters, season=1998):
    return {'name': '1998 Test', 'season_year': season, 'games': [],
            'teams': {tid: {'tid': tid, 'name': 'Team %d' % tid, 'roster': list(pids)}
                      for tid, pids in rosters.items()}}


def first_pass(rosters=ROSTERS, players=PLAYERS):
    return C.update(None, assoc(rosters), players, 1998, TABLE)


def write_table(path, obj):
    path.write_text(json.dumps(obj), encoding='utf-8')
    return str(path)


# --- load_table -----------------------------------------------------------------------------------------------------

def test_load_table_reads_a_table_of_the_contract_shape(tmp_path):
    assert C.load_table(write_table(tmp_path / 't.json', TABLE)) == TABLE


@pytest.mark.parametrize('obj', [
    [1, 2], {'ratio': TABLE['ratio']}, {'years': TABLE['years']}, {'years': {}, 'ratio': TABLE['ratio']},
    {'years': {'1985': 'x'}, 'ratio': TABLE['ratio']}, {'years': {'nineteen': 1}, 'ratio': TABLE['ratio']},
    {'years': TABLE['years'], 'ratio': {'bat': TABLE['ratio']['bat']}},
    {'years': TABLE['years'], 'ratio': {'bat': TABLE['ratio']['bat'], 'pit': {'pre': [1.0] * 10}}},
    {'years': TABLE['years'], 'ratio': {'bat': TABLE['ratio']['bat'], 'pit': dict(TABLE['ratio']['pit'], fa=[1.0] * 9)}},
])
def test_a_table_without_years_or_ratio_is_a_value_error(tmp_path, obj):
    with pytest.raises(ValueError):
        C.load_table(write_table(tmp_path / 't.json', obj))


def test_a_table_that_is_not_json_is_a_value_error(tmp_path):
    (tmp_path / 't.json').write_text('{"years": ', encoding='utf-8')
    with pytest.raises(ValueError):
        C.load_table(str(tmp_path / 't.json'))


# --- scale ----------------------------------------------------------------------------------------------------------

def test_scale_inside_the_years_is_the_years_median_or_the_nearest_year_below():
    t = {'years': {'1990': 100000, '1992': 200000}}
    assert C.scale(t, 1990) == 100000.0
    assert C.scale(t, 1991) == 100000.0
    assert C.scale(t, 1992) == 200000.0


def test_scale_after_the_last_year_grows_three_percent_a_year():
    assert C.scale({'years': {'2000': 100000}}, 2002) == pytest.approx(100000 * 1.03 ** 2)


def test_scale_before_the_first_year_shrinks_seven_percent_a_year():
    assert C.scale({'years': {'1990': 100000}}, 1988) == pytest.approx(100000 * 0.93 ** 2)


def test_scale_is_never_below_three_thousand():
    assert C.scale({'years': {'1990': 1000}}, 1990) == 3000.0
    assert C.scale({'years': {'1990': 1000}}, 1980) == 3000.0


# --- role, deciles, service, class ----------------------------------------------------------------------------------

@pytest.mark.parametrize('pos, expected', [('P', 'pit'), ('RF', 'bat'), ('1B', 'bat'), ('', 'bat')])
def test_role_is_pit_for_a_pitcher_and_bat_otherwise(pos, expected):
    assert C.role({'pos': pos}) == expected


def test_deciles_rank_each_role_from_the_worst_to_the_best_and_a_lone_player_is_decile_one():
    bats = {100 + i: player('B%d' % i, 'RF', contact=30 + 5 * i) for i in range(10)}
    out = C.deciles({**bats, 500: player('P', 'P')})
    assert [out[100 + i] for i in range(10)] == list(range(1, 11))
    assert out[500] == 1


def test_pitchers_are_ranked_on_control_strikeouts_and_stamina_not_contact():
    pit = {1: player('A', 'P', control=90), 2: player('B', 'P', control=40, strikeout=40, stamina=40),
           3: player('C', 'P', contact=99, control=40, strikeout=40, stamina=40)}
    out = C.deciles(pit)
    assert out == {2: 1, 3: 4, 1: 7}      # B and C tie on the index (contact is not counted), so B is lower by pid


def test_a_missing_fielding_rating_counts_as_zero():
    out = C.deciles({1: player('X', 'SS', fielding=None), 2: player('Y', 'SS', fielding=40)})
    assert out == {1: 1, 2: 6}


def test_a_tie_in_index_goes_to_the_lower_pid():
    assert C.deciles({5: player('Five'), 3: player('Three')}) == {3: 1, 5: 6}


@pytest.mark.parametrize('age, expected', [(None, 0), (20, 0), (22, 0), (25, 3), (30, 8)])
def test_service_is_years_past_twenty_two(age, expected):
    assert C.service(age) == expected


@pytest.mark.parametrize('service, cls', [(0, 'pre'), (2, 'pre'), (3, 'arb'), (5, 'arb'), (6, 'fa'), (14, 'fa')])
def test_class_of_service(service, cls):
    assert C.class_of(service) == cls


# --- salary and years -----------------------------------------------------------------------------------------------

def test_salary_is_the_ratio_times_the_median_to_the_nearest_thousand_under_a_million():
    t = {'years': {'1998': 400000}, 'ratio': cell({'pre': 0.5, 'arb': 1.0, 'fa': 1.2345})}
    assert C.salary(t, 'bat', 'fa', 3, 1998) == 494000       # 493,800


def test_salary_rounds_to_the_nearest_ten_thousand_from_a_million_up():
    t = {'years': {'1998': 1000000}, 'ratio': cell({'pre': 0.5, 'arb': 1.0, 'fa': 1.2345})}
    assert C.salary(t, 'pit', 'fa', 10, 1998) == 1230000     # 1,234,500 to the nearest 10,000


def test_the_decile_picks_its_own_cell():
    ratio = cell({'pre': 0.5, 'arb': 1.0, 'fa': 1.0})
    ratio['bat']['fa'] = [i / 10 for i in range(1, 11)]
    t = {'years': {'1998': 1000000}, 'ratio': ratio}
    assert C.salary(t, 'bat', 'fa', 1, 1998) == 100000
    assert C.salary(t, 'bat', 'fa', 10, 1998) == 1000000


def test_a_pre_arbitration_salary_is_never_below_three_tenths_of_the_median():
    t = {'years': {'1998': 1000000}, 'ratio': cell({'pre': 0.05, 'arb': 0.05, 'fa': 1.0})}
    assert C.salary(t, 'bat', 'pre', 1, 1998) == 300000
    assert C.salary(t, 'bat', 'arb', 1, 1998) == 50000       # the floor is for pre-arbitration only


@pytest.mark.parametrize('cls, age, decile, years', [
    ('pre', 40, 1, 1), ('arb', 40, 9, 1),
    ('fa', 28, 8, 5), ('fa', 29, 8, 4), ('fa', 30, 8, 4), ('fa', 31, 8, 3), ('fa', 32, 8, 3),
    ('fa', 33, 8, 2), ('fa', 34, 8, 2), ('fa', 35, 8, 1), ('fa', None, 8, 4),
    ('fa', 28, 5, 2), ('fa', 28, 6, 5), ('fa', 35, 5, 1),
])
def test_years_for_a_new_contract(cls, age, decile, years):
    assert C.years_for(cls, age, decile) == years


@pytest.mark.parametrize('dollars, text', [
    (0, '$0'), (3000, '$3,000'), (9999, '$9,999'), (10000, '$10K'), (850000, '$850K'), (999000, '$999K'),
    (1000000, '$1M'), (4500000, '$4.5M'), (62000000, '$62M'),
])
def test_money(dollars, text):
    assert C.money(dollars) == text


# --- update ---------------------------------------------------------------------------------------------------------

def test_the_first_pass_prices_every_rostered_player_and_logs_no_events():
    s = first_pass()
    assert s['season_year'] == 1998 and s['events'] == []
    assert sorted(s['contracts']) == ['100', '101', '200', '400']
    assert s['contracts']['100'] == {'team': 1, 'salary': 2000000, 'years': 2, 'left': 2, 'signed': 1998,
                                     'class': 'fa', 'name': 'Al Winner', 'pos': 'RF', 'age': 28}
    assert s['contracts']['200'] == {'team': 2, 'salary': 500000, 'years': 1, 'left': 1, 'signed': 1998,
                                     'class': 'pre', 'name': 'Bo Loser', 'pos': 'P', 'age': 23}


def test_a_kept_contract_counts_down_and_takes_the_current_name_position_and_age():
    s0 = first_pass()
    players = {**PLAYERS, 100: player('Al Winner', 'LF', 1970)}
    s1 = C.update(s0, assoc(ROSTERS, 1999), players, 1999, TABLE)
    assert s1['contracts']['100'] == dict(s0['contracts']['100'], left=1, pos='LF', age=29)
    assert not any(e['pid'] == 100 for e in s1['events'])


def test_a_rollover_expires_a_contract_and_re_signs_it_with_a_new_price():
    s0 = first_pass()
    s1 = C.update(s0, assoc(ROSTERS, 1999), PLAYERS, 1999, TABLE)
    assert s1['events'] == [
        {'kind': 're-signed', 'pid': 101, 'name': 'Joe Old', 'team': 1, 'salary': 2000000, 'years': 1, 'year': 1999},
        {'kind': 're-signed', 'pid': 200, 'name': 'Bo Loser', 'team': 2, 'salary': 500000, 'years': 1, 'year': 1999},
    ]
    assert s1['contracts']['101'] == {'team': 1, 'salary': 2000000, 'years': 1, 'left': 1, 'signed': 1999,
                                      'class': 'fa', 'name': 'Joe Old', 'pos': 'P', 'age': 39}


def test_a_signing_in_the_same_season_is_logged_and_priced_by_its_service():
    s0 = first_pass()
    s1 = C.update(s0, assoc({1: [100, 101, 300], 2: [200, 400]}), PLAYERS, 1998, TABLE)
    assert s1['events'] == [{'kind': 'signed', 'pid': 300, 'name': 'Pat Smith', 'team': 1, 'salary': 1000000,
                             'years': 1, 'year': 1998}]
    assert s1['contracts']['300']['class'] == 'arb' and s1['contracts']['300']['left'] == 1


def test_a_moved_player_keeps_his_contract_and_gets_a_moved_event():
    s0 = first_pass()
    s1 = C.update(s0, assoc({1: [101], 2: [100, 200, 400]}), PLAYERS, 1998, TABLE)
    assert s1['events'] == [{'kind': 'moved', 'pid': 100, 'name': 'Al Winner', 'team': 2, 'salary': 0, 'years': 0,
                             'year': 1998}]
    assert s1['contracts']['100'] == dict(s0['contracts']['100'], team=2)


def test_a_moved_player_whose_contract_ran_out_is_re_signed_not_moved():
    s0 = first_pass()
    s1 = C.update(s0, assoc({1: [100], 2: [101, 200, 400]}, 1999), PLAYERS, 1999, TABLE)
    assert [(e['kind'], e['pid']) for e in s1['events']] == [('re-signed', 101), ('re-signed', 200)]


def test_a_released_player_is_logged_and_one_who_left_the_league_is_not():
    s0 = first_pass()
    players = {k: v for k, v in PLAYERS.items() if k != 400}
    s1 = C.update(s0, assoc({1: [100, 101], 2: []}), players, 1998, TABLE)
    assert s1['events'] == [{'kind': 'released', 'pid': 200, 'name': 'Bo Loser', 'team': None, 'salary': 0,
                             'years': 0, 'year': 1998}]
    assert sorted(s1['contracts']) == ['100', '101']


def test_events_go_in_pid_order_and_only_the_last_hundred_are_kept():
    players = {p: player('P%d' % p) for p in range(1000, 1150)}
    s0 = C.update(None, assoc({1: list(players)}), players, 1998, TABLE)
    s1 = C.update(s0, assoc({2: []}), players, 1998, TABLE)
    assert len(s1['events']) == 100
    assert [e['pid'] for e in s1['events']] == list(range(1050, 1150))
    assert all(e['kind'] == 'released' for e in s1['events'])


def test_a_season_of_none_returns_the_state_unchanged_or_an_empty_state():
    s0 = first_pass()
    assert C.update(s0, assoc(ROSTERS, None), PLAYERS, None, TABLE) == s0
    assert C.update(None, assoc(ROSTERS, None), PLAYERS, None, TABLE) == {'season_year': None, 'contracts': {},
                                                                          'events': []}


def test_the_previous_state_is_never_changed():
    s0 = first_pass()
    s1 = C.update(s0, assoc({1: [100, 300], 2: [400]}, 1999), PLAYERS, 1999, TABLE)
    before = copy.deepcopy(s1)
    C.update(s1, assoc({2: [100, 101]}, 2000), PLAYERS, 2000, TABLE)
    assert s1 == before


def test_a_player_without_a_birth_year_has_no_age_and_is_priced_as_pre_arbitration():
    s = C.update(None, assoc({1: [700]}), {700: player('No Born', 'RF', None)}, 1998, TABLE)
    assert s['contracts']['700'] == {'team': 1, 'salary': 500000, 'years': 1, 'left': 1, 'signed': 1998,
                                     'class': 'pre', 'name': 'No Born', 'pos': 'RF', 'age': None}


def test_a_pid_on_two_rosters_keeps_the_lower_tid_and_an_unknown_pid_gets_no_contract():
    s = C.update(None, assoc({2: [100], 1: [100, 999]}), PLAYERS, 1998, TABLE)
    assert list(s['contracts']) == ['100'] and s['contracts']['100']['team'] == 1


# --- payroll --------------------------------------------------------------------------------------------------------

def test_payroll_rows_are_sorted_by_total_then_tid_with_average_and_top():
    contracts = {'1': {'team': 2, 'salary': 500000}, '2': {'team': 1, 'salary': 2000000},
                 '3': {'team': 1, 'salary': 1000000}, '4': {'team': 3, 'salary': 1500000},
                 '5': {'team': 3, 'salary': 1500000}}
    teams = {1: {'name': 'Ash'}, 2: {'name': 'Birch'}, 3: {'name': 'Cedar'}, 4: {'name': 'Dune'}}
    rows = C.payroll(contracts, teams)
    assert rows == [
        {'tid': 1, 'name': 'Ash', 'players': 2, 'total': 3000000, 'average': 1500000, 'top': 2000000},
        {'tid': 3, 'name': 'Cedar', 'players': 2, 'total': 3000000, 'average': 1500000, 'top': 1500000},
        {'tid': 2, 'name': 'Birch', 'players': 1, 'total': 500000, 'average': 500000, 'top': 500000},
        {'tid': 4, 'name': 'Dune', 'players': 0, 'total': 0, 'average': 0, 'top': 0},
    ]


def test_payroll_average_is_whole_dollars():
    contracts = {'1': {'team': 1, 'salary': 1000000}, '2': {'team': 1, 'salary': 1000001}, '3': {'team': 1, 'salary': 1}}
    assert C.payroll(contracts, {1: {'name': 'Ash'}})[0]['average'] == 666667
