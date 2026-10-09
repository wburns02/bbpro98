"""recap.py on synthetic games: records, game facts, the number check, parse, the template and write()'s fallbacks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import hive  # noqa: E402
import recap  # noqa: E402

OAK, CWS = 26, 4
NAMES = {201: 'Ann Able', 202: 'Bob Baker', 203: 'Cy Cole', 301: 'Dan Dale', 302: 'Eli Ford', 401: 'Gus Hall',
         402: 'Hal Ives', 501: 'Ian Jett', 502: 'Kip Lowe'}
BUDGET = object()


def team(tid, name, abbrev, stadium):
    return {'tid': tid, 'name': name, 'abbrev': abbrev, 'city': 'OAKLAND.', 'stadium': stadium, 'manager': 'Art Howe',
            'league': 'American League', 'division': 'Western', 'w': 0, 'l': 0}


def gm(month, day, slot, away, home, ar=0, hr=0, played=True, innings=9):
    return {'month': month, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': innings}


def assoc(games):
    return {'name': '1998 Major Leagues', 'games': games,
            'teams': {OAK: team(OAK, 'Oakland Athletics', 'OAK', 'Oakland-Alameda County Stadium'),
                      CWS: team(CWS, 'Chicago White Sox', 'CWS', 'Comiskey Park')}}


def bat(pid, ab=4, h=0, hr=0, rbi=0, sb=0, r=0):
    return {'ab': ab, 'h': h, '2b': 0, '3b': 0, 'hr': hr, 'rbi': rbi, 'bb': 0, 'so': 0, 'r': r, 'sb': sb, 'pid': pid}


def pit(pid, outs=27, h=0, r=0, er=0, bb=0, so=0, w=0, l=0, sv=0):
    return {'outs': outs, 'h': h, 'r': r, 'er': er, 'bb': bb, 'so': so, 'hr': 0, 'w': w, 'l': l, 'sv': sv, 'pid': pid}


def side(tid, runs, hits, batting, pitching):
    return {'tid': tid, 'runs': runs, 'hits': hits, 'batting': batting, 'pitching': pitching}


def played(ar=3, hr=5, innings=9, save=True):
    """CWS at OAK on April 15, final CWS ar, OAK hr. Pre-games put CWS at 1-2 and OAK at 2-1 through this game.
    The first pitcher on each side takes that side's decision; with save, the winner's second pitcher gets the save.
    No 6 anywhere in the facts, so tests can use 6 as a wrong number."""
    away_pit = [pit(401, outs=22, h=5, r=3, er=3, bb=1, so=4), pit(402, outs=5, h=2, so=1)]
    home_pit = [pit(501, outs=21, h=4, r=2, er=2, bb=1, so=5), pit(502, outs=6, h=1, so=2)]
    box = {'away': side(CWS, ar, 7, [bat(201, h=3, rbi=1, r=1), bat(202, h=1)], away_pit),
           'home': side(OAK, hr, 9, [bat(301, h=2, hr=1, rbi=3, r=1), bat(302, h=1, sb=2, r=1)], home_pit)}
    win, lose = ('away', 'home') if ar > hr else ('home', 'away')
    box[win]['pitching'][0]['w'] = 1
    box[lose]['pitching'][0]['l'] = 1
    if save:
        box[win]['pitching'][1]['sv'] = 1
    game = gm(4, 15, 13, CWS, OAK, ar=ar, hr=hr, innings=innings)
    prior = [gm(4, 1, 13, OAK, CWS, ar=4, hr=2), gm(4, 8, 13, CWS, OAK, ar=7, hr=2)]
    return assoc(prior + [game]), box, game


def facts_of(**kw):
    a, box, game = played(**kw)
    return recap.game_facts(a, box, game, NAMES)


def schedule():
    """CWS and OAK games in scrambled file order, with an unplayed game on 4/2 between two played ones. The unplayed
    game carries runs, so only its played flag keeps it out of the records."""
    return [gm(4, 4, 13, CWS, OAK, ar=7, hr=2), gm(4, 2, 13, CWS, OAK, ar=3, hr=1, played=False),
            gm(4, 1, 13, OAK, CWS, ar=4, hr=2), gm(4, 3, 13, OAK, CWS, ar=1, hr=5)]


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


GOOD = 'Athletics top Chicago\n\nOakland beat Chicago 5-3 at home on April 15.'
BAD = 'Athletics top Chicago\n\nOakland beat Chicago 6-3 at home on April 15.'
NO_THREE = {'innings': 9, 'date': 'April 15', 'away': {'name': 'A', 'runs': 5, 'record': '2-1'},
            'home': {'name': 'B', 'runs': 4, 'record': '1-2'}}


def test_ip_formats_outs_as_innings_and_thirds():
    assert recap.ip(23) == '7.2'
    assert recap.ip(27) == '9.0'
    assert recap.ip(0) == '0.0'
    assert recap.ip(1) == '0.1'


def test_records_stop_at_the_game_and_skip_unplayed():
    games = schedule()
    sched = assoc(games)
    d, b, a, c = games                 # 4/4, 4/2 (unplayed), 4/1, 4/3
    assert recap.records(sched, a) == {'away': (1, 0), 'home': (0, 1)}
    # Through the unplayed 4/2 game: only 4/1 counts.
    assert recap.records(sched, b) == {'away': (0, 1), 'home': (1, 0)}
    assert recap.records(sched, c) == {'away': (1, 1), 'home': (1, 1)}
    assert recap.records(sched, d) == {'away': (2, 1), 'home': (1, 2)}


def test_records_match_the_game_by_its_key_not_its_identity():
    games = schedule()
    assert recap.records(assoc(games), dict(games[3])) == {'away': (1, 1), 'home': (1, 1)}


def test_records_reject_a_game_not_on_the_schedule():
    with pytest.raises(ValueError):
        recap.records(assoc(schedule()), gm(5, 1, 13, OAK, CWS, ar=1, hr=0))


def test_game_facts_full_shape_for_a_home_win():
    f = facts_of()
    assert f == {
        'association': '1998 Major Leagues',
        'date': 'April 15',
        'innings': 9,
        'away': {'name': 'Chicago White Sox', 'abbrev': 'CWS', 'runs': 3, 'hits': 7, 'record': '1-2'},
        'home': {'name': 'Oakland Athletics', 'abbrev': 'OAK', 'runs': 5, 'hits': 9, 'record': '2-1',
                 'stadium': 'Oakland-Alameda County Stadium'},
        'winner': 'home',
        'batters': [
            {'team': 'OAK', 'name': 'Dan Dale', 'ab': 4, 'h': 2, '2b': 0, '3b': 0, 'hr': 1, 'rbi': 3, 'bb': 0, 'r': 1,
             'sb': 0},
            {'team': 'CWS', 'name': 'Ann Able', 'ab': 4, 'h': 3, '2b': 0, '3b': 0, 'hr': 0, 'rbi': 1, 'bb': 0, 'r': 1,
             'sb': 0},
            {'team': 'OAK', 'name': 'Eli Ford', 'ab': 4, 'h': 1, '2b': 0, '3b': 0, 'hr': 0, 'rbi': 0, 'bb': 0, 'r': 1,
             'sb': 2},
        ],
        'decisions': {
            'win': {'team': 'OAK', 'name': 'Ian Jett', 'ip': '7.0', 'h': 4, 'r': 2, 'er': 2, 'bb': 1, 'so': 5},
            'loss': {'team': 'CWS', 'name': 'Gus Hall', 'ip': '7.1', 'h': 5, 'r': 3, 'er': 3, 'bb': 1, 'so': 4},
            'save': {'team': 'OAK', 'name': 'Kip Lowe', 'ip': '2.0', 'h': 1, 'r': 0, 'er': 0, 'bb': 0, 'so': 2},
        },
        'notes': [],
    }


def test_game_facts_keeps_only_notable_batters_sorted_and_capped_at_six():
    a, box, game = played()
    names = {**NAMES, 601: 'Al Zed', 602: 'Bo Yim', 603: 'Cy Xu', 604: 'Di Wu', 605: 'Ed Vo', 606: 'Fu Ta',
             607: 'Gi Sa', 608: 'Hu Ro', 609: 'Ix Pe'}
    box['away']['batting'] = [bat(601, h=3, rbi=3), bat(602, h=3, rbi=3), bat(603, h=3, hr=1),
                              bat(604, h=4, rbi=4)]
    box['home']['batting'] = [bat(605, h=5, rbi=3), bat(606, sb=2), bat(607, h=2, hr=2), bat(608, h=3),
                              bat(609, h=2, rbi=2, sb=1)]
    f = recap.game_facts(a, box, game, names)
    assert [b['name'] for b in f['batters']] == ['Gi Sa', 'Cy Xu', 'Di Wu', 'Ed Vo', 'Al Zed', 'Bo Yim']
    assert [b['team'] for b in f['batters']] == ['OAK', 'CWS', 'CWS', 'OAK', 'CWS', 'CWS']


def test_first_flagged_line_on_the_away_side_wins_each_role():
    a, box, game = played()
    box['away']['pitching'][0]['w'] = 1       # Gus Hall, read before Ian Jett on the home side
    f = recap.game_facts(a, box, game, NAMES)
    assert f['decisions']['win']['name'] == 'Gus Hall'


def test_no_save_gives_a_none_save():
    assert facts_of(save=False)['decisions']['save'] is None


def test_notes_come_in_order_shutout_extra_innings_complete_game_then_multi_homer():
    a, box, game = played(ar=5, hr=0, innings=10)
    box['away']['pitching'] = box['away']['pitching'][:1]          # Gus Hall alone
    box['away']['batting'].append(bat(203, h=2, hr=2, rbi=2))     # Cy Cole, two home runs
    f = recap.game_facts(a, box, game, NAMES)
    assert f['notes'] == ['shutout', 'extra innings', 'complete game by Gus Hall', 'Cy Cole hit 2 home runs']


def test_single_notes_fire_alone():
    assert facts_of(ar=5, hr=0)['notes'] == ['shutout']
    assert facts_of(innings=10)['notes'] == ['extra innings']
    assert facts_of()['notes'] == []


def test_game_facts_refuses_a_tie():
    with pytest.raises(ValueError):
        facts_of(ar=3, hr=3)


def test_allowed_numbers_walks_values_not_keys_and_skips_bools_and_none():
    f = {'ip': '7.2', 'name': 'Player 947', 'year': '1998 Major Leagues', 'n': 23, 'flag': True, 'none': None,
         'col5': 'x', 'nested': [{'x': 'Gus'}]}
    assert recap.allowed_numbers(f) == {'7.2', '7', '2', '947', '1998', '23'}


def test_allowed_numbers_adds_the_margin_and_total_of_a_game():
    assert recap.allowed_numbers({'away': {'runs': 5}, 'home': {'runs': 3}}) == {'5', '3', '2', '8'}


def test_numbers_ok_accepts_a_correct_story_and_rejects_a_wrong_score():
    f = facts_of()
    assert recap.numbers_ok('Oakland beat Chicago 5-3 on April 15, its 2-1 start.', f)
    assert not recap.numbers_ok('Oakland won 6-3.', f)


def test_numbers_ok_checks_number_words_case_insensitively_and_hyphenated():
    assert recap.numbers_ok('a two-run ninth', NO_THREE)            # 2 is in the record
    assert recap.numbers_ok('nine innings', NO_THREE)
    assert not recap.numbers_ok('a three-run homer', NO_THREE)
    assert not recap.numbers_ok('Three runs', NO_THREE)
    assert not recap.numbers_ok('twenty runs', NO_THREE)


def test_numbers_ok_matches_ordinals_and_digits_whole():
    assert not recap.numbers_ok('a 10th-inning homer', NO_THREE)
    assert recap.numbers_ok('a 10th-inning homer', {'innings': 10})
    assert not recap.numbers_ok('pitched 7.5 innings', {'ip': '7.1'})
    assert recap.numbers_ok('pitched 7.1 innings', {'ip': '7.1'})
    # 7 and 1 are in the facts on their own, but 7.1 is not.
    assert not recap.numbers_ok('pitched 7.1 innings', {'a': 7, 'b': 1})


def test_numbers_ok_splits_a_decimal_average_into_its_digits():
    assert recap.numbers_ok('hit .312', {'avg': '.312'})          # .312 yields 312
    assert not recap.numbers_ok('hit .312', {'avg': 1})


def test_numbers_ok_does_not_check_one_or_ordinals():
    assert recap.numbers_ok('One run, in the first inning', {'innings': 9})


def test_prompt_puts_the_facts_in_the_user_message_as_sorted_json():
    f = facts_of()
    system, user = recap.prompt(f)
    assert user == 'Facts:\n' + json.dumps(f, indent=1, sort_keys=True)
    assert '80 to 130 words' in system and 'Spell numbers as digits' in system


def test_parse_splits_headline_from_body():
    assert recap.parse('Athletics win\n\nOakland beat Chicago.\nMore.') == {
        'headline': 'Athletics win', 'body': 'Oakland beat Chicago.\nMore.'}


def test_parse_strips_markdown_from_the_headline():
    assert recap.parse('## **Oakland Wins**\n\nBody.') == {'headline': 'Oakland Wins', 'body': 'Body.'}


def test_parse_handles_crlf_and_a_headline_across_lines():
    assert recap.parse('Athletics\r\nwin again\r\n\r\nFirst line.\r\nSecond.\r\n') == {
        'headline': 'Athletics win again', 'body': 'First line.\nSecond.'}


def test_parse_needs_a_body_a_headline_and_a_headline_of_at_most_120():
    assert recap.parse('Headline only') is None
    assert recap.parse('Headline\n\n   \n') is None
    assert recap.parse('**\n\nBody') is None
    assert recap.parse('x' * 121 + '\n\nBody') is None
    assert recap.parse('x' * 120 + '\n\nBody')['headline'] == 'x' * 120


def test_template_home_win_reads_as_plain_prose():
    t = recap.template(facts_of())
    assert t['headline'] == 'Oakland Athletics 5, Chicago White Sox 3'
    assert t['body'] == (
        'Oakland Athletics beat Chicago White Sox 5-3 at Oakland-Alameda County Stadium on April 15. '
        'Dan Dale went 2-for-4 with 1 home run and 3 RBI. Ann Able went 3-for-4 with 1 RBI. Eli Ford went 1-for-4. '
        'Ian Jett got the win, allowing 2 runs over 7.0 innings. Kip Lowe earned the save over 2.0 innings. '
        'Chicago White Sox is 1-2; Oakland Athletics is 2-1.')


def test_template_away_win_names_the_away_side_and_its_pitchers():
    t = recap.template(facts_of(ar=5, hr=3))
    assert t['headline'] == 'Chicago White Sox 5, Oakland Athletics 3'
    assert t['body'].startswith('Chicago White Sox beat Oakland Athletics 5-3 at Oakland-Alameda County '
                                'Stadium on April 15. ')
    assert 'Gus Hall got the win, allowing 3 runs over 7.1 innings.' in t['body']
    assert 'Hal Ives earned the save over 1.2 innings.' in t['body']
    assert 'Chicago White Sox is 2-1; Oakland Athletics is 1-2.' in t['body']


def test_template_names_at_most_three_batters():
    f = facts_of()
    f['batters'].append(dict(f['batters'][0], name='Gus Fourth'))
    t = recap.template(f)
    assert 'Gus Fourth' not in t['body']
    assert t['body'].count(' went ') == 3


def test_template_extra_innings_and_missing_save_say_so():
    t = recap.template(facts_of(innings=10, save=False))
    assert 'It took 10 innings.' in t['body']
    assert 'save' not in t['body']


@pytest.mark.parametrize('kw', [{}, {'ar': 5, 'hr': 3}, {'innings': 11}, {'save': False},
                                {'ar': 5, 'hr': 3, 'save': False}, {'ar': 5, 'hr': 0},
                                {'ar': 3, 'hr': 5, 'innings': 12}])
def test_template_passes_numbers_ok(kw):
    f = facts_of(**kw)
    t = recap.template(f)
    assert recap.numbers_ok(t['headline'] + '\n' + t['body'], f)


def test_write_takes_a_story_that_checks_out():
    f = facts_of()
    c = Scripted(GOOD)
    assert recap.write(f, BUDGET, c) == {'headline': 'Athletics top Chicago',
                                         'body': 'Oakland beat Chicago 5-3 at home on April 15.', 'source': 'glm'}
    assert len(c.calls) == 1
    assert c.calls[0][:2] == recap.prompt(f) and c.calls[0][2] is BUDGET


def test_write_retries_a_bad_number_and_takes_the_next_story():
    c = Scripted(BAD, GOOD)
    assert recap.write(facts_of(), BUDGET, c)['source'] == 'glm'
    assert len(c.calls) == 2


def test_write_falls_back_to_the_template_when_two_stories_have_bad_numbers():
    f = facts_of()
    c = Scripted(BAD, BAD)
    out = recap.write(f, BUDGET, c)
    assert out == dict(recap.template(f), source='template', reason='numbers')
    assert len(c.calls) == 2


def test_write_stops_at_once_when_the_budget_is_spent():
    c = Scripted(hive.BudgetExceeded('daily budget spent'), GOOD)
    out = recap.write(facts_of(), BUDGET, c)
    assert out['source'] == 'template' and out['reason'] == 'budget'
    assert len(c.calls) == 1


def test_write_retries_a_hive_error_and_takes_the_next_story():
    c = Scripted(hive.HiveError('timeout'), GOOD)
    assert recap.write(facts_of(), BUDGET, c)['source'] == 'glm'
    assert len(c.calls) == 2


def test_write_budget_after_an_error_still_stops_at_once():
    c = Scripted(hive.HiveError('timeout'), hive.BudgetExceeded('spent'), GOOD)
    out = recap.write(facts_of(), BUDGET, c)
    assert out['reason'] == 'budget' and len(c.calls) == 2


def test_write_reports_the_kind_of_the_last_failure():
    assert recap.write(facts_of(), BUDGET, Scripted('no blank line here', 'still none'))['reason'] == 'format'
    assert recap.write(facts_of(), BUDGET, Scripted(hive.HiveError('x'), 'no blank line'))['reason'] == 'format'
    assert recap.write(facts_of(), BUDGET, Scripted(hive.HiveError('x'), hive.HiveError('y')))['reason'] == 'error'
