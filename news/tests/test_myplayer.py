"""myplayer.py: the follow list, the game log, the weekly column and the words of a page, on synthetic dicts."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hive       # noqa: E402
import myplayer   # noqa: E402
import recap      # noqa: E402

NOW = '2026-10-15T09:00:00'


def doc(*pids):
    return {'kind': 'follow', 'players': [{'pid': p, 'birth': p * 10, 'since': NOW} for p in pids]}


# the follow list

@pytest.mark.parametrize('bad', [None, 5, 'x', [], {}, {'kind': 'other', 'players': []}, {'kind': 'follow'},
                                 {'kind': 'follow', 'players': 'x'}, {'kind': 'follow', 'players': None}])
def test_a_bad_doc_is_the_empty_doc(bad):
    assert myplayer.parse(bad) == {'kind': 'follow', 'players': []}
    assert myplayer.followed(bad) == {}


def test_parse_keeps_good_entries_and_drops_the_rest():
    raw = {'kind': 'follow', 'players': [
        {'pid': 7, 'birth': 70, 'since': 'a'}, 'x', None, {'pid': 'z'}, {'pid': True}, {'pid': 0}, {'pid': -3},
        {'pid': 8, 'birth': 'late', 'since': 5}, {'pid': 7, 'birth': 71, 'since': 'b'}]}
    assert myplayer.parse(raw) == {'kind': 'follow', 'players': [
        {'pid': 8, 'birth': None, 'since': ''}, {'pid': 7, 'birth': 71, 'since': 'b'}]}


def test_parse_keeps_only_the_newest_three():
    assert [p['pid'] for p in myplayer.parse(doc(1, 2, 3, 4, 5))['players']] == [3, 4, 5]


def test_add_appends_and_does_not_change_the_old_doc():
    old = doc(1)
    new = myplayer.add(old, 2, 20, NOW)
    assert old == doc(1)
    assert new['players'] == [{'pid': 1, 'birth': 10, 'since': NOW}, {'pid': 2, 'birth': 20, 'since': NOW}]
    assert myplayer.followed(new) == {1: 10, 2: 20}


def test_add_to_nothing_starts_a_list():
    assert myplayer.add(None, 4, None, NOW) == {'kind': 'follow', 'players': [{'pid': 4, 'birth': None, 'since': NOW}]}


def test_a_fourth_follow_replaces_the_oldest():
    d = doc(1, 2, 3)
    assert myplayer.MAX_FOLLOW == 3
    new = myplayer.add(d, 4, 40, 'later')
    assert [p['pid'] for p in new['players']] == [2, 3, 4]
    assert new['players'][-1]['since'] == 'later'
    assert [p['pid'] for p in d['players']] == [1, 2, 3]


def test_following_the_same_player_again_changes_nothing():
    d = doc(1, 2)
    assert myplayer.add(d, 1, 10, 'later') == d


def test_an_id_reused_by_a_new_player_replaces_the_old_entry_and_goes_last():
    new = myplayer.add(doc(1, 2, 3), 1, 99, 'later')
    assert new['players'] == [{'pid': 2, 'birth': 20, 'since': NOW}, {'pid': 3, 'birth': 30, 'since': NOW},
                              {'pid': 1, 'birth': 99, 'since': 'later'}]


def test_remove_drops_the_player_and_ignores_a_stranger():
    d = doc(1, 2)
    assert myplayer.followed(myplayer.remove(d, 1)) == {2: 20}
    assert myplayer.remove(d, 9) == d
    assert myplayer.remove(None, 1) == {'kind': 'follow', 'players': []}
    assert d == doc(1, 2)


def test_matching_drops_an_id_the_pyr_gives_to_someone_else():
    follows = {1: 10, 2: 20, 3: None, 4: 40}
    births = {1: 10, 2: 21, 3: 5}
    assert myplayer.matching(follows, births) == {1: 10, 3: None}      # 2 reused, 4 gone, 3 has no birth to contradict
    assert myplayer.matching(follows, None) == follows                 # PYR unreadable: nobody is dropped
    assert myplayer.matching(follows, {}) == {}


# the game log

BOX = {'away': {'tid': 1, 'runs': 3,
                'batting': [{'pid': 100, 'ab': 4, 'h': 2, 'hr': 1, 'rbi': 2}, {'pid': 101, 'ab': 3, 'h': 0}],
                'pitching': [{'pid': 150, 'outs': 21, 'er': 2, 'so': 7, 'w': 1, 'l': 0, 'sv': 0}]},
       'home': {'tid': 2, 'runs': 2,
                'batting': [{'pid': 200, 'ab': 4, 'h': 1, 'hr': 0, 'rbi': 0}],
                'pitching': [{'pid': 250, 'outs': 24, 'er': 3, 'so': 4, 'w': 0, 'l': 1, 'sv': 0},
                             {'pid': 251, 'outs': 3, 'er': 0, 'so': 1, 'w': 0, 'l': 0, 'sv': 1}]}}
GAME = {'month': 4, 'day': 9, 'slot': 3, 'away': 1, 'home': 2, 'away_runs': 3, 'home_runs': 2, 'played': True}
ABBREVS = {1: 'ASH', 2: 'BIR'}


def test_game_line_for_a_visiting_hitter():
    assert myplayer.game_line(BOX, GAME, 100, ABBREVS) == {
        'month': 4, 'day': 9, 'slot': 3, 'opp': 'BIR', 'home': False,
        'bat': {'pid': 100, 'ab': 4, 'h': 2, 'hr': 1, 'rbi': 2}, 'pit': None}


def test_game_line_for_a_home_pitcher_names_the_visitors():
    line = myplayer.game_line(BOX, GAME, 251, ABBREVS)
    assert line['home'] is True and line['opp'] == 'ASH' and line['bat'] is None
    assert line['pit'] == {'pid': 251, 'outs': 3, 'er': 0, 'so': 1, 'w': 0, 'l': 0, 'sv': 1}
    assert 'ip' not in line['pit']


def test_game_line_keeps_both_lines_of_a_pitcher_who_batted():
    box = {'away': {'tid': 1, 'batting': [{'pid': 150, 'ab': 2, 'h': 1}], 'pitching': BOX['away']['pitching']},
           'home': BOX['home']}
    line = myplayer.game_line(box, GAME, 150, ABBREVS)
    assert line['bat'] == {'pid': 150, 'ab': 2, 'h': 1} and line['pit']['outs'] == 21 and line['home'] is False


def test_game_line_is_none_for_a_player_not_in_the_box_and_has_no_opponent_without_an_abbrev():
    assert myplayer.game_line(BOX, GAME, 999, ABBREVS) is None
    assert myplayer.game_line(BOX, GAME, 100, {})['opp'] == ''


def test_append_game_adds_in_schedule_order_once_per_date_and_slot():
    a = {'month': 4, 'day': 9, 'slot': 3}
    b = {'month': 4, 'day': 2, 'slot': 1}
    c = {'month': 4, 'day': 9, 'slot': 1}
    games = myplayer.append_game([], a)
    games = myplayer.append_game(games, b)
    games = myplayer.append_game(games, c)
    assert games == [b, c, a]
    assert myplayer.append_game(games, dict(a, opp='XXX')) == [b, c, a]      # already logged: kept as it was


# the season file

def test_a_page_rolls_only_when_both_seasons_are_known_and_differ():
    page = myplayer.new_page(100, 'Al Winner', 1998)
    assert page == {'pid': 100, 'name': 'Al Winner', 'season_year': 1998, 'games': [], 'columns': []}
    assert myplayer.rolled(page, 1999) is True
    assert myplayer.rolled(page, 1998) is False
    assert myplayer.rolled(page, None) is False
    assert myplayer.rolled(dict(page, season_year=None), 1999) is False
    assert myplayer.rolled(dict(page, season_year=True), 1999) is False


# the weekly column

def games_of(n, start=1, **line):
    return [{'month': 4, 'day': start + i, 'slot': 0, 'opp': 'BIR', 'home': True,
             'bat': dict({'ab': 4, 'h': 1, 'hr': 0, 'rbi': 1}, **line), 'pit': None} for i in range(n)]


def test_window_waits_for_six_games_after_the_last_column():
    assert myplayer.WEEK == 6
    assert myplayer.window(games_of(5), []) == []
    assert myplayer.window(games_of(6), []) == games_of(6)
    col = {'through': [4, 6], 'text': 't', 'source': 'template', 'facts': {}}
    assert myplayer.window(games_of(11), [col]) == []                       # 5 games after April 6
    assert myplayer.window(games_of(12), [col]) == games_of(12)[6:]
    assert myplayer.window(games_of(12), [dict(col, through=[4, 5]), col]) == games_of(12)[6:]   # the newest column
    assert myplayer.window(games_of(7), [{'through': 'bad'}]) == games_of(7)      # a column that says nothing counts none


def test_window_covers_every_game_after_the_column_not_just_six():
    assert len(myplayer.window(games_of(10), [])) == 10
    assert myplayer.through_of(games_of(10)) == [4, 10]


def test_week_facts_hitter_sums_and_season_rate():
    games = [{'bat': {'ab': 4, 'h': 2, 'hr': 1, 'rbi': 3}, 'pit': None}, {'bat': None, 'pit': None},
             {'bat': {'ab': 5}, 'pit': None}]
    facts = myplayer.week_facts('Al Winner', games, {'bat': {'ab': 80, 'h': 24, 'hr': 3, 'rbi': 9}, 'pit': None},
                                {'w': 4, 'l': 2})
    assert facts == {'name': 'Al Winner', 'kind': 'bat', 'n': 3, 'team_w': 4, 'team_l': 2, 'ab': 9, 'h': 2, 'hr': 1,
                     'rbi': 3, 'season_avg': '.300', 'season_hr': 3, 'season_rbi': 9}


def test_week_facts_season_average_edges():
    one = myplayer.week_facts('A', games_of(1), {'bat': {'ab': 3, 'h': 3, 'hr': 0, 'rbi': 0}, 'pit': None}, {})
    none = myplayer.week_facts('A', games_of(1), {'bat': None, 'pit': None}, {'w': 1})
    zero = myplayer.week_facts('A', games_of(1), {'bat': {'ab': 0, 'h': 0, 'hr': 0, 'rbi': 0}}, {})
    assert one['season_avg'] == '1.000' and none['season_avg'] == '---' and zero['season_avg'] == '---'
    assert none['season_hr'] == 0 and none['team_w'] == 1 and none['team_l'] == 0


def test_week_facts_for_a_pitcher_when_any_game_has_a_pitching_line():
    games = [{'bat': None, 'pit': {'outs': 20, 'er': 2}}, {'bat': {'ab': 1}, 'pit': {'outs': 7, 'er': 1}},
             {'bat': None, 'pit': None}]
    facts = myplayer.week_facts('Bo Loser', games, {'bat': None, 'pit': {'outs': 121, 'er': 40, 'w': 3}},
                                {'w': 9, 'l': 9})
    assert facts == {'name': 'Bo Loser', 'kind': 'pit', 'n': 3, 'team_w': 9, 'team_l': 9, 'ip': '9.0',
                     'era': '%.2f' % (27 * 3 / 27), 'season_ip': '40.1', 'season_era': '%.2f' % (27 * 40 / 121)}
    assert facts['era'] == '3.00' and facts['season_era'] == '8.93'


def test_week_facts_pitcher_without_outs_has_no_era():
    games = [{'bat': None, 'pit': {'outs': 0, 'er': 2}}]
    facts = myplayer.week_facts('Bo', games, {'bat': None, 'pit': None}, {'w': 0, 'l': 0})
    assert facts['ip'] == '0.0' and facts['era'] == '---' and facts['season_ip'] == '0.0'
    assert facts['season_era'] == '---'


HIT_FACTS = {'name': 'Al Winner', 'kind': 'bat', 'n': 6, 'team_w': 4, 'team_l': 2, 'ab': 22, 'h': 7, 'hr': 2, 'rbi': 5,
             'season_avg': '.300', 'season_hr': 3, 'season_rbi': 9}
PIT_FACTS = {'name': 'Bo Loser', 'kind': 'pit', 'n': 6, 'team_w': 4, 'team_l': 2, 'ip': '12.2', 'era': '2.13',
             'season_ip': '40.1', 'season_era': '3.50'}


def test_template_text_for_a_hitter_is_exact():
    assert myplayer.template(HIT_FACTS) == {
        'headline': "Al Winner's week",
        'body': "Al Winner went 7 for 22 with 2 home runs and 5 RBI over his team's last 6 games. Al Winner is "
                'hitting .300 with 3 home runs and 9 RBI on the season.'}


def test_template_text_for_a_pitcher_is_exact():
    assert myplayer.template(PIT_FACTS) == {
        'headline': "Bo Loser's week",
        'body': 'Bo Loser pitched 12.2 innings over 6 games with a 2.13 ERA. Bo Loser has a 3.50 ERA over 40.1 '
                'innings on the season.'}


@pytest.mark.parametrize('facts', [HIT_FACTS, PIT_FACTS])
def test_the_template_passes_the_number_check(facts):
    t = myplayer.template(facts)
    assert recap.numbers_ok(t['headline'] + '\n' + t['body'], facts)


def test_template_of_facts_built_by_week_facts_passes_the_number_check():
    facts = myplayer.week_facts('Al Winner', games_of(6, h=2, hr=1), {'bat': {'ab': 80, 'h': 24, 'hr': 3, 'rbi': 9}},
                                {'w': 4, 'l': 2})
    t = myplayer.template(facts)
    assert recap.numbers_ok(t['body'], facts) and '.300' in t['body']


class Budget:
    def __init__(self):
        self.calls = 0


def answer(text):
    def complete(system, user, budget):
        complete.seen.append((system, user))
        return text, {}
    complete.seen = []
    return complete


def test_write_takes_a_model_column_whose_numbers_are_the_facts():
    complete = answer("Winner's hot week\n\nAl Winner hit .300 with 2 home runs over 6 games.")
    piece = myplayer.write(HIT_FACTS, Budget(), complete)
    assert piece == {'headline': "Winner's hot week",
                     'body': 'Al Winner hit .300 with 2 home runs over 6 games.', 'source': 'glm'}
    system, user = complete.seen[0]
    assert 'Never invent' in system and '"season_avg": ".300"' in user


def test_write_falls_back_to_the_template_when_the_model_invents_a_number():
    complete = answer("Winner's hot week\n\nAl Winner hit .412 with 2 home runs over 6 games.")
    piece = myplayer.write(HIT_FACTS, Budget(), complete)
    assert piece['source'] == 'template' and piece['reason'] == 'numbers'
    assert piece['body'] == myplayer.template(HIT_FACTS)['body'] and len(complete.seen) == 2


def test_write_falls_back_when_the_budget_is_spent():
    def complete(system, user, budget):
        raise hive.BudgetExceeded('out')
    piece = myplayer.write(HIT_FACTS, Budget(), complete)
    assert piece['source'] == 'template' and piece['reason'] == 'budget'


def test_column_entry_has_the_four_keys():
    games = games_of(6)
    piece = {'headline': 'h', 'body': 'the text', 'source': 'glm'}
    assert myplayer.column(piece, {'n': 6}, games) == {'through': [4, 6], 'text': 'the text', 'source': 'glm',
                                                       'facts': {'n': 6}}


# the words of a page

def test_plan_text():
    assert myplayer.plan_text({'pid': 1, 'birth': 2, 'kind': 'power', 'assn': 'X'}) == 'Offseason training plan: power'
    assert myplayer.plan_text(None) == 'No offseason plan set.'


def test_milestones_are_the_players_events_newest_first_and_capped():
    events = [{'pid': 1, 'kind': 'new', 'n': i} for i in range(30)] + [{'pid': 2, 'kind': 'new'}, 'junk', None]
    got = myplayer.milestones(events, 1)
    assert myplayer.MILESTONES == 20 and len(got) == 20
    assert [e['n'] for e in got] == list(range(29, 9, -1))
    assert myplayer.milestones(events, 3) == []
    assert [e['n'] for e in myplayer.milestones(events, 1, limit=2)] == [29, 28]


def test_stat_text_for_hitters_and_pitchers():
    assert myplayer.stat_text({'g': 20, 'ab': 80, 'h': 24, 'hr': 3, 'rbi': 9}, 'bat') == '.300 AVG, 3 HR, 9 RBI in 20 games'
    assert myplayer.stat_text({'ab': 80, 'h': 24, 'hr': 3, 'rbi': 9}, 'bat') == '.300 AVG, 3 HR, 9 RBI'
    assert myplayer.stat_text({'g': 9, 'w': 3, 'l': 1, 'outs': 121, 'er': 40, 'so': 35, 'sv': 2}, 'pit') == \
        '3-1, 8.93 ERA, 40.1 IP, 35 SO, 2 SV in 9 games'
    for line, kind in ((None, 'bat'), ('x', 'pit'), ({'ab': 0}, 'bat'), ({'outs': 0}, 'pit'), ({}, 'bat')):
        assert myplayer.stat_text(line, kind) == ''
    assert myplayer.stat_text({'ab': 'many', 'h': 1}, 'bat') == ''


def test_line_text_joins_the_batting_and_pitching_words():
    assert myplayer.bat_text({'ab': 4, 'h': 2, 'hr': 1, 'rbi': 2, 'sb': 0}) == '2-for-4, 1 HR, 2 RBI'
    assert myplayer.pit_text({'outs': 19, 'er': 2, 'so': 7, 'w': 1, 'l': 0, 'sv': 0}) == '6.1 IP, 2 ER, 7 SO, W'
    game = {'bat': {'ab': 2, 'h': 0}, 'pit': {'outs': 3, 'er': 0, 'so': 1, 'sv': 1}}
    assert myplayer.line_text(game) == '0-for-2; 1.0 IP, 0 ER, 1 SO, SV'
    assert myplayer.line_text({'bat': None, 'pit': None}) == '' and myplayer.line_text(None) == ''
