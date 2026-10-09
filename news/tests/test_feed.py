"""feed.py on synthetic leagues: standings, streaks, days, leaders, the 'Around the league' facts and the write()
fallbacks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feed  # noqa: E402
import hive  # noqa: E402
import recap  # noqa: E402

BUDGET = object()


def team(tid, name, league='American League', division='Western'):
    # w and l are set to nonsense on purpose: standings must count games, not these.
    return {'tid': tid, 'name': name, 'abbrev': name[:3].upper(), 'city': 'CITY.', 'stadium': name + ' Park',
            'manager': 'Mgr', 'league': league, 'division': division, 'w': 99, 'l': 99}


def gm(month, day, slot, away, home, ar=0, hr=0, played=True, innings=9):
    return {'month': month, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': innings}


def assoc(teams, games):
    return {'name': '1998 Major Leagues', 'teams': teams, 'games': games}


def results(pairs, first_day=1):
    """One game per (winner, loser) pair on consecutive days; the winner is away in every other game."""
    out = []
    for i, (win, lose) in enumerate(pairs):
        away_wins = i % 2 == 0
        away, home = (win, lose) if away_wins else (lose, win)
        ar, hr = (4, 2) if away_wins else (2, 4)
        out.append(gm(4, first_day + i, 13, away, home, ar=ar, hr=hr))
    return out


def b(ab, h, hr=0, rbi=0, sb=0):
    return {'ab': ab, 'h': h, 'hr': hr, 'rbi': rbi, 'sb': sb}


def p(outs, er, so=0, w=0, sv=0):
    return {'outs': outs, 'er': er, 'so': so, 'w': w, 'sv': sv}


class Scripted:
    """A complete() stand-in: answers in order; an exception instance is raised instead of answered."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, system, user, budget):
        self.calls.append((system, user, budget))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer, {'completion_tokens': 10}


# Alpha, Beta, Gamma (Western) and Delta, Epsilon (Eastern); 4-1, 3-2, 4-2, 1-5, 1-3.
PAIRS = [(1, 4), (1, 5), (1, 4), (1, 3), (2, 1), (2, 3), (2, 5), (3, 2), (3, 5), (3, 4), (3, 4), (4, 2), (5, 4)]
LEAGUE_NAMES = {1: 'Alpha', 2: 'Beta', 3: 'Gamma', 4: 'Delta', 5: 'Epsilon'}


def league_assoc():
    teams = {tid: team(tid, n, division='Western' if tid <= 3 else 'Eastern') for tid, n in LEAGUE_NAMES.items()}
    return assoc(teams, results(PAIRS))


def test_standings_order_pct_and_games_back_from_games_not_team_records():
    west, east = feed.standings(league_assoc())
    assert (west['league'], west['division'], east['division']) == ('American League', 'Western', 'Eastern')
    assert [(t['name'], t['w'], t['l'], t['pct'], t['gb']) for t in west['teams']] == [
        ('Alpha', 4, 1, '.800', '-'), ('Gamma', 4, 2, '.667', '.5'), ('Beta', 3, 2, '.600', '1')]
    assert [(t['name'], t['w'], t['l'], t['pct'], t['gb']) for t in east['teams']] == [
        ('Epsilon', 1, 3, '.250', '-'), ('Delta', 1, 5, '.167', '1')]


def test_standings_groups_follow_the_first_tid_not_the_dict_order():
    a = league_assoc()
    a['teams'] = dict(reversed(list(a['teams'].items())))
    assert [g['division'] for g in feed.standings(a)] == ['Western', 'Eastern']


def test_standings_break_a_pct_tie_by_wins_and_show_half_games():
    # Zed 4-2 and Ann 2-1 are both .667; the name order would put Ann first, the wins order Zed.
    teams = {1: team(1, 'Ann'), 2: team(2, 'Zed'), 3: team(3, 'Dun')}
    pairs = [(2, 3), (2, 3), (2, 3), (2, 3), (1, 2), (3, 2), (1, 3), (3, 1)]   # Zed 4-2, Ann 2-1, Dun 2-5
    west = feed.standings(assoc(teams, results(pairs)))[0]['teams']
    assert [(t['name'], t['pct'], t['gb']) for t in west] == [('Zed', '.667', '-'), ('Ann', '.667', '.5'),
                                                              ('Dun', '.286', '2.5')]


def test_standings_pct_is_1000_for_a_perfect_team_and_000_without_decisions():
    teams = {1: team(1, 'Xray'), 2: team(2, 'Yankee'), 3: team(3, 'Zulu')}
    west = feed.standings(assoc(teams, results([(1, 2), (1, 2)])))[0]['teams']
    assert [(t['name'], t['pct'], t['gb']) for t in west] == [('Xray', '1.000', '-'), ('Yankee', '.000', '2'),
                                                              ('Zulu', '.000', '1')]


def streak_assoc():
    """Ash wins 4/1-4/3 then loses 4/4-4/5; Cedar wins 4/6-4/9 over Dogwood; Birch and Dogwood mirror them.
    The 4/5 game is first in the file, so file order alone would give Ash L1. Elm never plays. An unplayed game
    on 4/12 must not count as the last day."""
    teams = {i: team(i, n) for i, n in enumerate(('Ash', 'Birch', 'Cedar', 'Dogwood', 'Elm'), 1)}
    games = [gm(4, 5, 13, 2, 1, ar=3, hr=2), gm(4, 3, 13, 1, 2, ar=5, hr=1), gm(4, 1, 13, 1, 2, ar=4, hr=2),
             gm(4, 2, 13, 1, 2, ar=3, hr=0), gm(4, 4, 13, 2, 1, ar=4, hr=1), gm(4, 6, 13, 3, 4, ar=5, hr=1),
             gm(4, 7, 13, 3, 4, ar=2, hr=0), gm(4, 8, 13, 4, 3, ar=0, hr=3), gm(4, 9, 13, 3, 4, ar=4, hr=2),
             gm(4, 12, 13, 1, 3, played=False)]
    return assoc(teams, games)


def test_streaks_are_current_runs_in_date_order_and_skip_teams_that_never_played():
    assert feed.streaks(streak_assoc()) == {1: 'L2', 2: 'W2', 3: 'W4', 4: 'L4'}


def test_last_day_is_the_latest_played_date_or_none():
    assert feed.last_day(streak_assoc()) == (4, 9)
    assert feed.last_day(assoc({}, [gm(4, 1, 13, 1, 2, played=False)])) is None


def test_day_results_are_the_day_played_games_in_slot_order():
    a = assoc({1: team(1, 'Ash'), 2: team(2, 'Birch')},
              [gm(4, 9, 2, 2, 1, ar=1, hr=3), gm(4, 9, 1, 1, 2, ar=5, hr=4, innings=10),
               gm(4, 9, 3, 1, 2, played=False)])
    assert feed.day_results(a, 4, 9) == [
        {'away': 'Ash', 'home': 'Birch', 'away_runs': 5, 'home_runs': 4, 'innings': 10},
        {'away': 'Birch', 'home': 'Ash', 'away_runs': 1, 'home_runs': 3, 'innings': 9}]
    assert feed.day_results(a, 4, 10) == []


SEASON_NAMES = {101: 'Ann Hart', 102: 'Bo Lee', 103: 'Cal Ortiz', 104: 'Dee Moss', 201: 'Eli Park', 202: 'Fay Quinn'}


def test_leaders_need_three_point_one_at_bats_per_team_game_for_avg():
    season = {'bat': {1: b(500, 300), 101: b(31, 10), 102: b(30, 15)}, 'pit': {}}
    assert feed.leaders(season, SEASON_NAMES, 10)['avg'] == [{'name': 'Ann Hart', 'value': '.323'}]


def test_leaders_need_one_inning_per_team_game_for_era():
    season = {'bat': {}, 'pit': {201: p(30, 3), 202: p(29, 0)}}
    assert feed.leaders(season, SEASON_NAMES, 10)['era'] == [{'name': 'Eli Park', 'value': '2.70'}]


def test_era_is_earned_runs_times_27_over_outs_to_two_places():
    # 2*27/27 = 2.00, 1*27/21 = 1.2857..., 10*27/60 = 4.50; player 203 has no name in SEASON_NAMES.
    season = {'bat': {}, 'pit': {201: p(27, 2), 202: p(21, 1), 203: p(60, 10)}}
    assert feed.leaders(season, SEASON_NAMES, 1)['era'] == [
        {'name': 'Fay Quinn', 'value': '1.29'}, {'name': 'Eli Park', 'value': '2.00'},
        {'name': 'Player 203', 'value': '4.50'}]


def test_avg_is_three_places_without_a_leading_zero_and_can_be_one_thousand():
    season = {'bat': {101: b(31, 31), 102: b(31, 0), 103: b(31, 10)}, 'pit': {}}
    assert [r['value'] for r in feed.leaders(season, SEASON_NAMES, 1)['avg']] == ['1.000', '.323', '.000']


def test_ties_break_by_name_for_counting_stats_avg_and_era():
    season = {'bat': {101: b(31, 10, hr=5), 102: b(62, 20, hr=5)}, 'pit': {201: p(30, 3), 202: p(60, 6)}}
    lead = feed.leaders(season, SEASON_NAMES, 1)
    assert [r['name'] for r in lead['hr']] == ['Ann Hart', 'Bo Lee']
    assert [r['name'] for r in lead['avg']] == ['Ann Hart', 'Bo Lee']      # 10/31 and 20/62 are the same average
    assert [r['name'] for r in lead['era']] == ['Eli Park', 'Fay Quinn']   # both 2.70


def test_only_the_top_five_show_and_zeros_are_left_out_of_counting_stats():
    bat = {100 + i: b(31, 10, hr=i) for i in range(1, 8)}
    bat[101] = b(31, 10, hr=0)
    bat[1] = b(500, 300, hr=99)                                       # team total, id below 100
    lead = feed.leaders({'bat': bat, 'pit': {}}, {}, 1)
    assert [r['value'] for r in lead['hr']] == ['7', '6', '5', '4', '3']
    assert lead['rbi'] == [] and lead['sb'] == []


def test_leaders_are_empty_when_nobody_qualifies_or_every_value_is_zero():
    season = {'bat': {101: b(31, 0)}, 'pit': {201: p(30, 0)}}
    lead = feed.leaders(season, SEASON_NAMES, 100)
    assert set(lead) == {'avg', 'hr', 'rbi', 'sb', 'w', 'so', 'sv', 'era'}
    assert lead['avg'] == [] and lead['era'] == [] and lead['hr'] == [] and lead['w'] == []


def test_missing_names_render_as_player_id():
    lead = feed.leaders({'bat': {999: b(4, 1, hr=1)}, 'pit': {}}, {}, 0)
    assert lead['hr'] == [{'name': 'Player 999', 'value': '1'}]


DAY_SEASON = {
    'bat': {1: b(900, 400, hr=50),                                   # team total: ignored
            101: b(31, 10, hr=2), 102: b(40, 14, hr=5), 103: b(9, 9), 104: b(3, 3)},
    'pit': {201: p(30, 3, w=1, so=10), 202: p(9, 0, sv=2), 203: p(6, 0, w=3)},
}
DAY_NAMES = {101: 'Ann Hart', 102: 'Bo Lee', 103: 'Cal Ortiz', 104: 'Dee Moss', 201: 'Eli Park', 202: 'Fay Quinn'}


def day_assoc():
    """Four teams in two divisions; 4/9 has two games in file order slot 2 then slot 1. Cedar and Dogwood have
    four straight games through 4/9. Five games played, so teams_played is 2.5."""
    teams = {1: team(1, 'Ash', division='Western'), 2: team(2, 'Birch', division='Western'),
             3: team(3, 'Cedar', division='Eastern'), 4: team(4, 'Dogwood', division='Eastern')}
    games = [gm(4, 9, 2, 4, 3, ar=2, hr=6), gm(4, 9, 1, 1, 2, ar=5, hr=4, innings=10),
             gm(4, 6, 13, 3, 4, ar=5, hr=1), gm(4, 7, 13, 3, 4, ar=2, hr=0), gm(4, 8, 13, 4, 3, ar=0, hr=3)]
    return assoc(teams, games)


def test_day_facts_has_the_whole_shape_with_values():
    assert feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 9) == {
        'association': '1998 Major Leagues',
        'date': 'April 9',
        'results': [{'away': 'Ash', 'home': 'Birch', 'away_runs': 5, 'home_runs': 4, 'innings': 10},
                    {'away': 'Dogwood', 'home': 'Cedar', 'away_runs': 2, 'home_runs': 6, 'innings': 9}],
        'division_leaders': [
            {'league': 'American League', 'division': 'Western', 'team': 'Ash', 'record': '1-0', 'lead': '1'},
            {'league': 'American League', 'division': 'Eastern', 'team': 'Cedar', 'record': '4-0', 'lead': '4'}],
        'streaks': [{'team': 'Cedar', 'streak': 'W4'}, {'team': 'Dogwood', 'streak': 'L4'}],
        'leaders': {
            'hr': [{'name': 'Bo Lee', 'value': '5'}, {'name': 'Ann Hart', 'value': '2'}],
            'avg': [{'name': 'Cal Ortiz', 'value': '1.000'}, {'name': 'Bo Lee', 'value': '.350'},
                    {'name': 'Ann Hart', 'value': '.323'}],
            'w': [{'name': 'Player 203', 'value': '3'}, {'name': 'Eli Park', 'value': '1'}],
            'era': [{'name': 'Fay Quinn', 'value': '0.00'}, {'name': 'Eli Park', 'value': '2.70'}],
        },
    }


def test_day_facts_streaks_need_four_games():
    three = assoc({1: team(1, 'Ash'), 2: team(2, 'Birch')}, [gm(4, d, 13, 1, 2, ar=5, hr=1) for d in (1, 2, 3)])
    assert feed.day_facts(three, {'bat': {}, 'pit': {}}, {}, 4, 3)['streaks'] == []


def test_day_facts_streaks_sort_by_length_then_team_and_cap_at_five():
    names = ('Ash', 'Birch', 'Quail', 'Rhino', 'Elm', 'Fig', 'Grape', 'Hops', 'Iris', 'Jade', 'Kale', 'Lime')
    teams = {i: team(i, n) for i, n in enumerate(names, 1)}
    # Ash and Birch win three in a row: too short. Quail and Rhino win five, so they lead although their names sort
    # last; each other pair wins four.
    spans = {(1, 2): 3, (3, 4): 5, (5, 6): 4, (7, 8): 4, (9, 10): 4, (11, 12): 4}
    games = [gm(4, d, 13, a, b, ar=5, hr=1) for (a, b), n in spans.items() for d in range(1, n + 1)]
    f = feed.day_facts(assoc(teams, games), {'bat': {}, 'pit': {}}, {}, 4, 5)
    assert f['streaks'] == [{'team': 'Quail', 'streak': 'W5'}, {'team': 'Rhino', 'streak': 'L5'},
                            {'team': 'Elm', 'streak': 'W4'}, {'team': 'Fig', 'streak': 'L4'},
                            {'team': 'Grape', 'streak': 'W4'}]


def test_template_lists_the_results_and_leaders_and_passes_numbers_ok():
    f = feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 9)
    t = feed.template(f)
    assert t['headline'] == 'Scores and standings'
    assert t['body'] == ('Ash 5, Birch 4. Cedar 6, Dogwood 2.\n'
                         'Ash leads the American League Western at 1-0. Cedar leads the American League Eastern at 4-0.')
    assert recap.numbers_ok(t['headline'] + '\n' + t['body'], f)


def test_template_on_a_day_with_no_games_and_in_a_one_league_era():
    f = feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 3)
    t = feed.template(f)
    assert t['headline'] == 'An off day'
    assert t['body'] == ('No games were played on April 3.\nAsh leads the American League Western at 1-0. '
                         'Cedar leads the American League Eastern at 4-0.')
    assert recap.numbers_ok(t['headline'] + '\n' + t['body'], f)

    one = assoc({1: team(1, 'Ash', league='', division=''), 2: team(2, 'Birch', league='', division='')},
                [gm(4, 1, 13, 1, 2, ar=5, hr=1)])
    f = feed.day_facts(one, {'bat': {}, 'pit': {}}, {}, 4, 1)
    t = feed.template(f)
    assert t['body'] == 'Ash 5, Birch 1.\nAsh leads the league at 1-0.'
    assert recap.numbers_ok(t['headline'] + '\n' + t['body'], f)


def test_prompt_is_the_column_brief_with_the_facts_message():
    f = feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 9)
    system, user = feed.prompt(f)
    assert '100 to 170 words' in system and 'Around the league' in system
    assert user == 'Facts:\n' + json.dumps(f, indent=1, sort_keys=True)


GOOD = 'Around the league: April 9\n\nAsh beat Birch 5-4 in ten innings, and Cedar beat Dogwood 6-2.'
BAD = 'Around the league: April 9\n\nCedar won 11-1.'


def test_write_takes_a_column_that_checks_out():
    f = feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 9)
    c = Scripted(GOOD)
    out = feed.write(f, BUDGET, c)
    assert out['source'] == 'glm' and out['headline'] == 'Around the league: April 9'
    assert c.calls[0][2] is BUDGET


def test_write_falls_back_with_the_right_reason():
    f = feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 9)
    fallback = dict(feed.template(f), source='template')

    assert feed.write(f, BUDGET, Scripted(BAD, BAD)) == dict(fallback, reason='numbers')
    assert feed.write(f, BUDGET, Scripted('no blank line', 'none')) == dict(fallback, reason='format')
    assert feed.write(f, BUDGET, Scripted(hive.HiveError('x'), hive.HiveError('y'))) == dict(fallback, reason='error')

    c = Scripted(hive.BudgetExceeded('spent'), GOOD)
    assert feed.write(f, BUDGET, c) == dict(fallback, reason='budget')
    assert len(c.calls) == 1


def test_write_retries_a_hive_error_then_takes_the_story():
    f = feed.day_facts(day_assoc(), DAY_SEASON, DAY_NAMES, 4, 9)
    c = Scripted(hive.HiveError('timeout'), GOOD)
    assert feed.write(f, BUDGET, c)['source'] == 'glm'
    assert len(c.calls) == 2
