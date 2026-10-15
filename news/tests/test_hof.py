"""hof.py on plain dicts: the career score and pct, who is on the ballot (every year edge), who is inducted or dropped
and how the list carries over, the induction story (template, model text, the numbers check), and the archive reader
against history.sim_seasons. No game files: careers are built here from rows."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hive     # noqa: E402
import history  # noqa: E402
import hof      # noqa: E402
import recap    # noqa: E402

S = 2040


def row(year, sim=True, team='Reds', **line):
    return dict(line, year=year, team=team, sim=sim)


def career(pid, name, last, h=0, pos='1B', gone=True, first=None, sim=True, **line):
    """A career of one season ending in last (or the seasons first..last), the h hits (and the rest of line) spread
    over its seasons as a single row each year's total."""
    years = range(first or last, last + 1)
    rows = [row(y, sim=sim, h=h if y == last else 0, **line) for y in years]
    return {'pid': pid, 'name': name, 'pos': pos, 'gone': gone, 'rows': rows}


# Only hits score here: 40*h/3000 = h/75, and pct = round(h/50). 3750 hits is exactly the bar (50), 3700 is pct 74,
# 250 is pct 5 (3.33), 200 is pct 4 (2.67).
HITS = {75: 3750, 74: 3700, 5: 250, 4: 200}


def test_hitter_score_is_hand_computed_with_the_average_term_from_4000_at_bats():
    t = dict(h=1500, hr=250, rbi=900, r=750, sb=80, ab=5000)
    # 20 + 12.5 + 9 + 5 + 1 = 47.5, and .300 against .250 is 5
    assert hof.score('bat', t) == pytest.approx(52.5)
    assert hof.pct(hof.score('bat', t)) == 79
    base = dict(h=1200, hr=0, rbi=0, r=0, sb=0)
    assert hof.score('bat', dict(base, ab=3999)) == pytest.approx(16.0)         # 40*1200/3000: no average term
    assert hof.score('bat', dict(base, ab=4000)) == pytest.approx(16.0 + 5.0)   # .300: 100*.050
    assert hof.score('bat', dict(base, h=1600, ab=4000)) == pytest.approx(40 * 1600 / 3000 + 10)    # .400: capped at 10
    assert hof.score('bat', dict(base, h=400, ab=4000)) == pytest.approx(40 * 400 / 3000 - 5)       # .100: floor of -5
    assert hof.score('bat', dict(base, h=1000, ab=4000)) == pytest.approx(40 * 1000 / 3000)         # .250: nothing


def test_pitcher_score_is_hand_computed_with_the_era_term_from_4500_outs():
    t = dict(w=200, so=2000, sv=20, outs=6000, er=700)
    # 30 + 16.667 + 1, and ERA 27*700/6000 = 3.15 against 3.50 is 3.5
    assert hof.score('pit', t) == pytest.approx(30 + 50 / 3 + 1 + 3.5)
    assert hof.pct(hof.score('pit', t)) == 77
    base = dict(w=100, so=0, sv=0)                                              # 15 points before any ERA term
    assert hof.score('pit', dict(base, outs=4499, er=1500)) == pytest.approx(15.0)    # below 4500 outs: nothing
    assert hof.score('pit', dict(base, outs=4500, er=1500)) == pytest.approx(5.0)     # ERA 9.00: 10*(3.5-9), floor -10
    assert hof.score('pit', dict(base, outs=4500, er=0)) == pytest.approx(30.0)       # ERA 0.00: 35, capped at 15
    assert hof.score('pit', dict(base, outs=4500, er=525)) == pytest.approx(18.5)     # ERA 3.15
    assert hof.score('pit', dict(base, outs=4500, er=720)) == pytest.approx(6.8)      # ERA 4.32: 10*(3.5-4.32)
    assert hof.score('pit', {}) == 0 and hof.score('bat', {}) == 0              # missing keys count 0


def test_score_rejects_another_kind():
    with pytest.raises(ValueError):
        hof.score('dh', {})


@pytest.mark.parametrize('s, want', [(50.0, 75), (49.3, 74), (49.7, 75), (2.9, 4), (3.1, 5), (1000, 99),
                                     (66.0, 99), (0, 0), (65.9, 99), (64.9, 97)])
def test_pct_is_the_score_against_the_bar_capped_at_99(s, want):
    assert hof.pct(s) == want


@pytest.mark.parametrize('last, ok', [(S - 4, False), (S - 5, True), (S - 15, True), (S - 16, False), (S, False),
                                      (S + 1, False)])
def test_eligibility_runs_from_five_to_fifteen_seasons_after_the_last_line(last, ok):
    assert hof.eligible(S, last, True, True) is ok


def test_eligibility_needs_a_retired_player_with_a_simulated_season_and_a_line():
    assert hof.eligible(S, S - 6, False, True) is False         # on a roster or a free agent
    assert hof.eligible(S, S - 6, True, False) is False         # every row real
    assert hof.eligible(S, None, True, True) is False           # no line at all
    assert hof.eligible(S, S - 6, True, True) is True


def test_ballot_lists_only_eligible_careers_with_years_on_and_pct_best_first():
    careers = [career(1, 'Four', S - 4, h=HITS[75]), career(2, 'Five', S - 5, h=HITS[5]),
               career(3, 'Fifteen', S - 15, h=HITS[74]), career(4, 'Sixteen', S - 16, h=HITS[75]),
               career(5, 'Active', S - 6, h=HITS[75], gone=False), career(6, 'Real', S - 6, h=HITS[75], sim=False),
               career(7, 'Bee', S - 7, h=HITS[5]), career(8, 'Ann', S - 7, h=HITS[5])]
    got = hof.ballot(S, careers)
    assert [(b['pid'], b['years_on'], b['pct'], b['retired']) for b in got] == [
        (3, 11, 74, S - 15), (8, 3, 5, S - 7), (7, 3, 5, S - 7), (2, 1, 5, S - 5)]      # pct, then name, then pid
    assert got[0]['kind'] == 'bat' and got[0]['line']['h'] == HITS[74] and got[0]['line']['seasons'] == 1
    assert [b['pid'] for b in hof.ballot(S, careers, skip={3, 7})] == [8, 2]


def test_ballot_kind_follows_the_position_and_scores_a_pitcher_as_one():
    pit = career(1, 'Hurler', S - 6, pos='P', w=290)            # 43.5 points: pct 65
    got = hof.ballot(S, [pit])
    assert got[0]['kind'] == 'pit' and got[0]['score'] == 43.5 and got[0]['pct'] == 65


def test_a_mixed_career_uses_its_real_and_simulated_rows_together():
    rows = [row(2018, sim=False, h=2000), row(S - 6, h=1750)]
    got = hof.ballot(S, [{'pid': 1, 'name': 'Both', 'pos': '1B', 'gone': True, 'rows': rows}])
    assert got[0]['line']['h'] == 3750 and got[0]['line']['seasons'] == 2 and got[0]['pct'] == 75


def test_run_inducts_at_75_keeps_74_drops_4_keeps_5_and_drops_after_the_last_ballot():
    careers = [career(1, 'In', S - 5, h=HITS[75]), career(2, 'Almost', S - 6, h=HITS[74]),
               career(3, 'Out', S - 7, h=HITS[4]), career(4, 'Barely', S - 8, h=HITS[5]),
               career(5, 'Last', S - 15, h=HITS[74]), career(6, 'Gone', S - 16, h=HITS[75])]
    got = hof.run(None, S, careers, '30L2025', 'now')
    assert got['stem'] == '30L2025' and got['updated'] == 'now' and got['year'] == S
    assert [(e['pid'], e['year'], e['retired'], e['pct'], e['story']) for e in got['inducted']] == [
        (1, S, S - 5, 75, None)]
    assert got['inducted'][0]['kind'] == 'bat' and got['inducted'][0]['line']['h'] == HITS[75]
    assert got['inducted'][0]['score'] == 50.0 and got['inducted'][0]['teams'] == ['Reds']
    assert [(b['pid'], b['years_on'], b['pct']) for b in got['ballot']] == [(2, 2, 74), (5, 11, 74), (4, 4, 5)]
    assert sorted(got['dropped']) == [3, 5]           # 4 percent now; the 15-year man after his last ballot
    assert {'pid', 'name', 'kind', 'retired', 'years_on', 'score', 'pct'} == set(got['ballot'][0])


def test_run_carries_the_inducted_list_and_the_dropped_pids_to_later_years():
    first = hof.run(None, S, [career(1, 'In', S - 5, h=HITS[75]), career(3, 'Out', S - 7, h=HITS[4]),
                              career(2, 'Almost', S - 6, h=HITS[74])], 's', 'a')
    again = [career(1, 'In', S - 5, h=HITS[75]), career(3, 'Out', S - 7, h=HITS[4]),
             career(2, 'Almost', S - 6, h=HITS[74]), career(9, 'Late', S - 5, h=HITS[75])]
    second = hof.run(first, S + 1, again, 's', 'b')
    assert [(e['pid'], e['year']) for e in second['inducted']] == [(1, S), (9, S + 1)]      # 1 keeps his first year
    assert [b['pid'] for b in second['ballot']] == [2] and second['ballot'][0]['years_on'] == 3
    assert second['dropped'] == [3] and second['year'] == S + 1 and second['updated'] == 'b'
    third = hof.run(second, S + 2, [], 's', 'c')            # nobody eligible: nothing is rewritten away
    assert [e['pid'] for e in third['inducted']] == [1, 9] and third['dropped'] == [3] and third['ballot'] == []


def test_run_never_puts_an_inducted_or_dropped_player_on_a_ballot_again():
    old = {'year': S - 1, 'inducted': [{'pid': 1, 'name': 'In', 'year': S - 1}], 'ballot': [], 'dropped': [2]}
    got = hof.run(old, S, [career(1, 'In', S - 6, h=HITS[75]), career(2, 'Out', S - 6, h=HITS[74])], 's', 'x')
    assert got['inducted'] == old['inducted'] and got['ballot'] == [] and got['dropped'] == [2]


def test_run_holds_one_ballot_a_season_year():
    done = hof.run(None, S, [career(1, 'In', S - 5, h=HITS[75])], 's', 'a')
    assert hof.run(done, S, [career(2, 'Other', S - 5, h=HITS[75])], 's', 'b') is done
    assert hof.run(done, S - 1, [career(2, 'Other', S - 5, h=HITS[75])], 's', 'b') is done
    assert hof.due(None, S) and hof.due({}, S) and hof.due({'year': S - 1}, S) and hof.due({'year': 'x'}, S)
    assert not hof.due({'year': S}, S) and not hof.due({'year': S + 1}, S)
    assert hof.held(None) is None and hof.held({'year': True}) is None and hof.held({'year': S}) == S


def test_run_ignores_old_entries_that_are_not_player_dicts():
    old = {'year': S - 1, 'inducted': ['x', {'pid': 'y'}, {'pid': 5, 'year': S - 1}], 'dropped': [7, 'z', None]}
    got = hof.run(old, S, [], 's', 'x')
    assert got['inducted'] == [{'pid': 5, 'year': S - 1}] and got['dropped'] == [7]


def test_the_last_ballot_is_shown_and_then_dropped_even_for_a_low_pct():
    got = hof.run(None, S, [career(1, 'Last', S - 15, h=HITS[5])], 's', 'x')
    assert [b['pid'] for b in got['ballot']] == [1] and got['dropped'] == [1]
    got = hof.run(got, S + 1, [career(1, 'Last', S - 15, h=HITS[5])], 's', 'y')     # a season later: out of range
    assert got['ballot'] == [] and got['dropped'] == [1]


def test_teams_are_distinct_in_order_without_blanks_or_several_team_labels():
    rows = [row(1, team='NYY'), row(2, team='2TM'), row(3, team=''), row(4, team='Reds'), row(5, team='NYY'),
            row(6, team=None), row(7, team='Cubs')]
    assert hof.teams_of(rows) == ['NYY', 'Reds', 'Cubs']


ZERO_BAT = {k: 0 for k in history.BAT_KEYS}
ZERO_PIT = {k: 0 for k in history.PIT_KEYS}


def entry(kind='bat', **over):
    line = ({'g': 1450, 'ab': 5600, 'r': 900, 'h': 1700, 'hr': 120, 'rbi': 800, 'sb': 40, 'seasons': 12}
            if kind == 'bat' else {'g': 500, 'w': 212, 'l': 150, 'sv': 3, 'outs': 6000, 'er': 700, 'so': 2200,
                                   'seasons': 15})
    base = {'pid': 100, 'name': 'Pat Doe', 'kind': kind, 'year': 2036, 'retired': 2031, 'score': 61.5, 'pct': 92,
            'line': line, 'teams': ['Reds', 'Cubs'], 'story': None}
    return dict(base, **over)


def test_story_facts_hold_what_a_story_may_say():
    f = hof.story_facts(entry(), 'Test League')
    assert f == {'association': 'Test League', 'name': 'Pat Doe', 'kind': 'bat', 'year': 2036, 'retired': 2031,
                 'seasons': 12, 'teams': ['Reds', 'Cubs'], 'line': entry()['line'], 'pct': 92, 'avg': '.304'}
    p = hof.story_facts(entry('pit'), 'Test League')
    assert (p['era'], p['ip'], p['seasons']) == ('3.15', '2000.0', 15) and 'avg' not in p
    bare = hof.story_facts(entry(line=dict(ZERO_BAT, seasons=1), teams=[]), 'x')
    assert 'avg' not in bare and bare['teams'] == []


def test_template_is_built_from_the_facts_and_passes_the_numbers_check():
    one_hit = dict(ZERO_BAT, seasons=1, h=1, hr=1)
    for e in (entry(), entry('pit'), entry(teams=['Reds']), entry(teams=['A', 'B', 'C'], line=one_hit),
              entry(teams=[], line=dict(ZERO_BAT, seasons=3)), entry('pit', line=dict(ZERO_PIT, seasons=1, w=1))):
        f = hof.story_facts(e, 'Test League')
        t = hof.template(f)
        assert t['headline'] == 'Pat Doe elected to the Hall of Fame'
        assert recap.numbers_ok(t['headline'] + '\n' + t['body'], f), t['body']
        assert '\n' in t['body'] and ' - ' not in t['body'] and not {'\u2014', '\u2013'} & set(t['body'])
    t = hof.template(hof.story_facts(entry(), 'Test League'))['body']
    assert t.split('\n')[0] == ('Pat Doe was elected to the Hall of Fame in 2036 with 92% of the vote. Pat Doe played '
                                '12 seasons for Reds and Cubs and last appeared in 2031.')
    assert t.split('\n')[1] == 'Pat Doe finished with 1700 hits, 120 home runs, 800 RBI and a .304 average.'
    t = hof.template(hof.story_facts(entry('pit'), 'Test League'))['body']
    assert t.split('\n')[1] == ('Pat Doe finished 212-150 with a 3.15 ERA, 2200 strikeouts and 3 saves over 2000.0 '
                                'innings.')
    one = hof.template(hof.story_facts(entry(teams=['A', 'B', 'C'], line=one_hit), 'x'))['body']
    assert 'played 1 season for A, B and C' in one and '1 hit, 1 home run and 0 RBI' in one


class Scripted:
    """A complete() stand-in: answers in order; an exception instance is raised instead of answered."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, system, user, budget):
        self.calls.append((system, user))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer, {'completion_tokens': 10}


def test_write_takes_model_text_whose_numbers_are_facts():
    facts = hof.story_facts(entry(), 'Test League')
    good = 'Doe goes into the Hall\n\nPat Doe, with 1700 hits and 120 home runs, is in the Hall of Fame class of 2036.'
    complete = Scripted(good)
    got = hof.write(facts, object(), complete)
    assert got == {'headline': 'Doe goes into the Hall', 'body': good.split('\n\n')[1], 'source': 'glm'}
    system, user = complete.calls[0]
    assert 'Hall of Fame' in system and 'without commas' in system and '"name": "Pat Doe"' in user


def test_write_falls_back_to_the_template_when_a_number_is_wrong():
    facts = hof.story_facts(entry(), 'Test League')
    bad = 'Doe goes into the Hall\n\nPat Doe finished with 1800 hits.'
    complete = Scripted(bad, bad)
    got = hof.write(facts, object(), complete)
    assert (got['source'], got['reason']) == ('template', 'numbers') and len(complete.calls) == 2
    assert got['headline'] == hof.template(facts)['headline'] and got['body'] == hof.template(facts)['body']
    comma = Scripted('Doe\n\nPat Doe had 1,700 hits.', 'Doe\n\nPat Doe had 1,700 hits.')
    assert hof.write(facts, object(), comma)['reason'] == 'numbers'            # 1,700 reads as 1 and 700


@pytest.mark.parametrize('answer, reason', [(hive.BudgetExceeded('spent'), 'budget'), (hive.HiveError('down'), 'error'),
                                            ('no blank line here', 'format')])
def test_write_falls_back_when_the_model_cannot_answer(answer, reason):
    got = hof.write(hof.story_facts(entry(), 'x'), object(), Scripted(answer, answer))
    assert (got['source'], got['reason']) == ('template', reason) and got['headline'].endswith('Hall of Fame')


def test_inducted_year_reads_the_hof_dict_without_trusting_it():
    doc = {'inducted': [{'pid': 7, 'year': 2036}, {'pid': 8, 'year': 'x'}, 'junk', {'pid': True, 'year': 2037}]}
    assert hof.inducted_year(doc, 7) == 2036
    assert hof.inducted_year(doc, 8) is None and hof.inducted_year(doc, 9) is None
    assert hof.inducted_year(doc, 1) is None
    for bad in (None, [], {}, {'inducted': 'x'}, {'inducted': None}):
        assert hof.inducted_year(bad, 7) is None


def test_story_key_is_the_year_and_pid():
    assert hof.story_key(2036, 1234) == '2036-1234'


def write_archives(tmp_path, stem='30L2025'):
    """Archives for 2026 to 2029 with two hitters, a pitcher, a hitter who pitched, keys that mean no player, and a
    torn file and a non-object file beside them."""
    data = str(tmp_path)
    for year in (2026, 2027, 2028, 2029):
        history.archive_season(data, stem, year,
                               {'bat': {100: {'g': 100 + year % 10, 'h': 50, 'hr': 5}, 101: {'g': 3}},
                                'pit': {200: {'g': 30, 'w': 10, 'outs': 600}, 100: {'g': 1}}},
                               {100: 'Reds', 200: 'Cubs'} if year != 2027 else None)
    folder = os.path.join(data, stem, 'history')
    with open(os.path.join(folder, '2030.json'), 'w') as f:
        f.write('{"year": 2030, "bat": {')
    with open(os.path.join(folder, '2031.json'), 'w') as f:
        f.write('[1, 2]')
    with open(os.path.join(folder, '2032.json'), 'w') as f:
        json.dump({'year': 2032, 'bat': {'0100': {'g': 9}, 'x': {'g': 9}, '102': 'bad', '103': {'g': 7, 'h': 'x'}},
                   'pit': [], 'team': {'103': 4}}, f)
    with open(os.path.join(folder, 'seen.json'), 'w') as f:
        json.dump({'years': [2026]}, f)
    return data


def test_archive_years_lists_the_year_files_only(tmp_path):
    data = write_archives(tmp_path)
    assert hof.archive_years(data, '30L2025') == [2026, 2027, 2028, 2029, 2030, 2031, 2032]
    assert hof.archive_years(data, '30l2025') == [2026, 2027, 2028, 2029, 2030, 2031, 2032]
    assert hof.archive_years(data, 'NOPE') == [] and hof.archive_years(data, '../x') == []
    assert hof.archive_years(data, None) == []


def test_sim_index_equals_what_sim_seasons_gives_for_each_player(tmp_path):
    data = write_archives(tmp_path)
    index = hof.sim_index(data, '30L2025')
    assert sorted(index['bat']) == [100, 101, 103] and sorted(index['pit']) == [100, 200]
    for kind in ('bat', 'pit'):
        for pid, rows in index[kind].items():
            assert rows == history.sim_seasons(data, '30L2025', pid, kind), (kind, pid)
    assert index['bat'][100][1]['team'] == '' and index['bat'][100][0]['team'] == 'Reds'
    assert index['bat'][103] == [dict(year=2032, team='', **history._keep({'g': 7}, history.BAT_KEYS))]
    assert hof.sim_index(str(tmp_path), 'NOPE') == {'bat': {}, 'pit': {}}


def test_hof_json_roundtrips_through_json(tmp_path):
    got = hof.run(None, S, [career(1, 'In', S - 5, h=HITS[75]), career(2, 'Almost', S - 6, h=HITS[74])], 's', 'x')
    assert json.loads(json.dumps(got)) == got
