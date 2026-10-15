"""rookies.py on hand-built players and associations: the snapshot and who counts as new, the class facts, the bios and
the template, and write() with a scripted complete() as test_scout.py builds it."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hive      # noqa: E402
import recap     # noqa: E402
import rookies   # noqa: E402
import scout     # noqa: E402


def player(name, pos='', bats='R', throws='R', born=1977, contact=0, power=0, speed=0, stamina=0, control=0,
           strikeout=0, fielding=0):
    """A players() entry."""
    return {'name': name, 'pos': pos, 'bats': bats, 'throws': throws, 'born': born, 'contact': contact,
            'power': power, 'speed': speed, 'stamina': stamina, 'control': control, 'strikeout': strikeout,
            'fielding': fielding}


PLAYERS = {
    101: player('Jose Diaz', 'SS', bats='L', contact=75, power=40, speed=99, fielding=60),     # 65 / 45 / 80 / 55
    102: player('Abe Cruz', 'C', contact=99, power=99, speed=0, fielding=None),               # 80 / 80 / 20 / None
    103: player('Ben Cruz', '', bats='', contact=99, power=99, speed=0, fielding=None),       # same sum as Abe
    104: player('Cal Dunn', 'LF', bats='S', born=None, contact=50, power=50, speed=50, fielding=50),
    201: player('Al Jones', 'P', throws='L', born=1976, control=75, strikeout=99, stamina=40),
    202: player('Bo Kemp', 'P', control=0, strikeout=0, stamina=0),
    203: player('Cy Lund', 'P', throws='', born=None, control=50, strikeout=50, stamina=50),
}


def team(tid, name, roster=()):
    return {'tid': tid, 'name': name, 'abbrev': name[:3].upper(), 'roster': list(roster)}


def world():
    """Chicago Cubs (1) list 101 and 201; Three Rivers (2) lists 201 too (the first team keeps him) and 104. 102, 103,
    202 and 203 are on no roster."""
    return {'name': '1998 Major Leagues', 'season_year': 1998, 'games': [],
            'teams': {1: team(1, 'Chicago Cubs', [101, 201, 55]), 2: team(2, 'Three Rivers', [201, 104])}}


def facts(pids=(101, 102, 103, 104, 201, 202, 203), year=1998):
    return rookies.class_facts(world(), PLAYERS, pids, year)


def names(rows):
    return [r['name'] for r in rows]


# snapshot and newcomers

def test_snapshot_lists_every_player_by_pid_with_name_and_birth_year():
    snap = rookies.snapshot(PLAYERS)
    assert snap['ids'][0] == [101, 'Jose Diaz', 1977]
    assert [row[0] for row in snap['ids']] == sorted(PLAYERS)
    assert [104, 'Cal Dunn', None] in snap['ids']
    assert rookies.snapshot({}) == {'ids': []}


def test_snapshot_records_the_season_only_when_it_is_an_int():
    assert rookies.snapshot(PLAYERS, 1998)['season'] == 1998
    assert rookies.snapshot(PLAYERS, 1998)['ids'] == rookies.snapshot(PLAYERS)['ids']
    for bad in (None, True, False, '1998', 1998.0):
        assert rookies.snapshot(PLAYERS, bad) == {'ids': rookies.snapshot(PLAYERS)['ids']}
    assert list(rookies.snapshot(PLAYERS)) == ['ids']


def test_newcomers_ignores_the_snapshots_season():
    prev = rookies.snapshot({pid: PLAYERS[pid] for pid in (101, 102, 201)}, 1997)
    assert rookies.newcomers(PLAYERS, prev) == [103, 104, 202, 203]
    assert rookies.newcomers(PLAYERS, rookies.snapshot(PLAYERS, 1998)) == []


def test_newcomers_are_the_triples_not_in_the_previous_snapshot():
    prev = rookies.snapshot({pid: PLAYERS[pid] for pid in (101, 102, 201)})
    assert rookies.newcomers(PLAYERS, prev) == [103, 104, 202, 203]
    assert rookies.newcomers(PLAYERS, rookies.snapshot(PLAYERS)) == []


def test_a_reused_pid_with_a_new_name_or_birth_year_is_new():
    prev = rookies.snapshot(PLAYERS)
    renamed = {**PLAYERS, 101: player('Jo Diaz', 'SS')}
    reborn = {**PLAYERS, 104: player('Cal Dunn', 'LF', born=1980)}
    assert rookies.newcomers(renamed, prev) == [101]
    assert rookies.newcomers(reborn, prev) == [104]


def test_newcomers_survives_a_json_round_trip():
    import json
    prev = json.loads(json.dumps(rookies.snapshot(PLAYERS)))
    assert rookies.newcomers(PLAYERS, prev) == []


@pytest.mark.parametrize('prev', [None, {}, {'ids': 'x'}, {'ids': None}, {'ids': {'a': 1}}, [], 'x', 5,
                                  {'ids': ['junk', [1, 2], 7]}])
def test_newcomers_is_empty_without_a_baseline(prev):
    assert rookies.newcomers(PLAYERS, prev) == []


def test_newcomers_skips_malformed_rows():
    prev = {'ids': [[101, 'Jose Diaz', 1977], 'junk', [102, 'Abe Cruz'], [103, ['x'], 1], None, (201, 'Al Jones', 1976)]}     # a tuple row is not a list
    assert rookies.newcomers(PLAYERS, prev) == [102, 103, 104, 201, 202, 203]


# class_facts

def test_class_facts_top_level_and_teams():
    f = facts()
    assert (f['association'], f['season'], f['scale'], f['count']) == ('1998 Major Leagues', 1998, scout.SCALE, 7)
    assert set(f) == {'association', 'season', 'scale', 'count', 'hitters', 'pitchers'}
    team_of = {r['name']: r['team'] for r in f['hitters'] + f['pitchers']}
    assert team_of['Jose Diaz'] == 'Chicago Cubs' and team_of['Al Jones'] == 'Chicago Cubs'
    assert team_of['Cal Dunn'] == 'Three Rivers'
    assert team_of['Abe Cruz'] == team_of['Bo Kemp'] == 'free agent'


def test_class_facts_rows_are_graded_and_aged():
    f = facts()
    jose = next(h for h in f['hitters'] if h['name'] == 'Jose Diaz')
    assert jose == {'pid': 101, 'name': 'Jose Diaz', 'pos': 'SS', 'age': 21, 'bats': 'left', 'team': 'Chicago Cubs',
                    'contact': 65, 'power': 45, 'speed': 80, 'fielding': 55}
    al = f['pitchers'][0]
    assert al == {'pid': 201, 'name': 'Al Jones', 'age': 22, 'throws': 'left', 'team': 'Chicago Cubs', 'control': 65,
                  'strikeout': 80, 'stamina': 45}
    by = {r['name']: r for r in f['hitters'] + f['pitchers']}
    assert by['Cal Dunn']['age'] is None and by['Cal Dunn']['bats'] == 'switch'
    assert by['Cy Lund']['throws'] == '' and by['Abe Cruz']['fielding'] is None and by['Ben Cruz']['bats'] == ''
    assert all(v in range(20, 81, 5) for r in by.values() for k, v in r.items()
               if k in ('contact', 'power', 'speed', 'fielding', 'control', 'strikeout', 'stamina') and v is not None)


def test_class_facts_age_is_none_when_the_year_is_not_an_int():
    f = rookies.class_facts(world(), PLAYERS, [101, 201], None)
    assert f['season'] is None and f['hitters'][0]['age'] is None and f['pitchers'][0]['age'] is None


def test_class_facts_sorts_best_first_by_grade_sum_then_name():
    f = facts()
    # Jose 65+45+80+55 = 245; Cal 50 x4 = 200 (fielding 50 -> 50); Abe and Ben 80+80+20+0 = 180, by name
    assert names(f['hitters']) == ['Jose Diaz', 'Cal Dunn', 'Abe Cruz', 'Ben Cruz']
    assert names(f['pitchers']) == ['Al Jones', 'Cy Lund', 'Bo Kemp']


def test_class_facts_skips_unknown_pids_but_counts_the_class_as_given():
    f = rookies.class_facts(world(), PLAYERS, [101, 999, 201], 1998)
    assert names(f['hitters']) == ['Jose Diaz'] and names(f['pitchers']) == ['Al Jones']
    assert f['count'] == 3
    empty = rookies.class_facts(world(), PLAYERS, [], 1998)
    assert (empty['count'], empty['hitters'], empty['pitchers']) == (0, [], [])


# headline_facts

def test_headline_facts_cuts_each_list_to_top_and_keeps_the_count():
    many = {pid: player('Hitter %d' % pid, 'CF', contact=(pid - 100) * 8) for pid in range(100, 112)}
    many.update({pid: player('Pitcher %d' % pid, 'P', control=(pid - 200) * 10) for pid in range(200, 209)})
    f = rookies.class_facts(world(), many, sorted(many), 1998)
    h = rookies.headline_facts(f)
    assert rookies.TOP == 6 and len(f['hitters']) == 12 and len(f['pitchers']) == 9
    assert h['hitters'] == f['hitters'][:6] and h['pitchers'] == f['pitchers'][:6]
    assert h['count'] == 21 and len(f['hitters']) == 12     # the input is not changed


# bio

def test_bio_of_a_hitter_matches_the_example():
    r = {'pid': 1, 'name': 'Jose Diaz', 'pos': 'SS', 'age': 21, 'bats': 'left', 'team': 'Chicago Cubs', 'contact': 60,
         'power': 45, 'speed': 70, 'fielding': 50}
    assert rookies.bio(r) == ('Jose Diaz, 21, a left-handed hitting shortstop for the Chicago Cubs, grades 60 for '
                              'contact, 45 for power and 70 for speed.')


def test_bio_of_a_pitcher_names_control_strikeout_stuff_and_stamina():
    r = {'pid': 2, 'name': 'Al Jones', 'age': 22, 'throws': 'right', 'team': 'Three Rivers', 'control': 65,
         'strikeout': 80, 'stamina': 45}
    assert rookies.bio(r) == ('Al Jones, 22, a right-handed pitcher for the Three Rivers, grades 65 for control, 80 '
                              'for strikeout stuff and 45 for stamina.')


def test_bio_leaves_out_a_missing_age_side_position_and_a_free_agent_team():
    hitter = {'pid': 3, 'name': 'Hub Zane', 'pos': '', 'age': None, 'bats': '', 'team': 'free agent', 'contact': 20,
              'power': 25, 'speed': 30, 'fielding': None}
    pitcher = {'pid': 4, 'name': 'Cy Lund', 'age': None, 'throws': '', 'team': 'free agent', 'control': 50,
               'strikeout': 50, 'stamina': 50}
    assert rookies.bio(hitter) == 'Hub Zane, a player and free agent, grades 20 for contact, 25 for power and 30 for speed.'
    assert rookies.bio(pitcher) == ('Cy Lund, a pitcher and free agent, grades 50 for control, 50 for strikeout '
                                    'stuff and 50 for stamina.')
    switch = dict(hitter, bats='switch', pos='1B', team='Ash', age=19)
    assert rookies.bio(switch).startswith('Hub Zane, 19, a switch-hitting first baseman for the Ash, grades')


def test_no_bio_or_template_prints_none():
    for r in facts()['hitters'] + facts()['pitchers']:
        assert 'None' not in rookies.bio(r)
    for f in (facts(), facts(year=None), facts(pids=())):
        piece = rookies.template(f)
        assert 'None' not in piece['headline'] + piece['body']


# template

def test_template_headline_and_body_of_a_class():
    piece = rookies.template(facts())
    assert piece['headline'] == 'The rookie class of 1998'
    hitters, pitchers = piece['body'].split('\n')
    assert hitters.startswith('7 new players joined the league in 1998. Jose Diaz, 21, a left-handed hitting '
                              'shortstop for the Chicago Cubs, grades 65 for contact, 45 for power and 80 for speed. ')
    assert hitters.index('Jose Diaz') < hitters.index('Cal Dunn') < hitters.index('Abe Cruz')
    assert pitchers.startswith('Al Jones, 22, a left-handed pitcher for the Chicago Cubs, grades 65 for control')
    assert 'Al Jones' not in hitters and 'Jose Diaz' not in pitchers


def test_template_names_only_the_top_players():
    many = {pid: player('Hitter %d' % pid, 'CF', contact=(pid - 100) * 8) for pid in range(100, 112)}
    f = rookies.class_facts(world(), many, sorted(many), 1998)
    body = rookies.template(f)['body']
    assert body.count('center fielder') == 6 and body.startswith('12 new players joined')
    assert 'Hitter 111' in body and 'Hitter 100' not in body


def test_template_with_no_season_year_or_no_rookies_or_one():
    assert rookies.template(facts(year=None))['headline'] == 'The rookie class'
    assert rookies.template(facts(year=None))['body'].startswith('7 new players joined the league. ')
    none = rookies.template(facts(pids=()))
    assert none == {'headline': 'The rookie class of 1998', 'body': 'No new players joined the league in 1998.'}
    assert rookies.template(facts(pids=(), year=None))['body'] == 'No new players joined the league.'
    one = rookies.template(facts(pids=(201,)))
    assert one['body'].startswith('1 new player joined the league in 1998.\nAl Jones, 22, a left-handed pitcher')


def test_template_passes_numbers_ok_on_each_fixture():
    fixtures = [facts(), facts(year=None), facts(pids=()), facts(pids=(101,)), facts(pids=(201,)),
                dict(facts(), hitters=[]), dict(facts(), pitchers=[])]
    for f in fixtures:
        piece = rookies.template(f)
        assert recap.numbers_ok(piece['headline'] + '\n' + piece['body'], f), piece['body']


# prompt and write

def test_prompt_is_the_column_system_and_the_facts():
    assert 'newcomers' in rookies.SYSTEM and '120 to 200 words' in rookies.SYSTEM and recap.RULES in rookies.SYSTEM
    f = facts()
    assert rookies.prompt(f) == (rookies.SYSTEM, recap.facts_message(f))


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


def test_write_takes_the_model_answer_that_checks_out():
    f = facts()
    model = Scripted('A class of speed and arms\n\nJose Diaz grades 80 for speed and is 21.')
    piece = rookies.write(f, 'B', model)
    assert (piece['source'], piece['headline']) == ('glm', 'A class of speed and arms')
    assert model.calls[0][0] == rookies.SYSTEM and 'Jose Diaz' in model.calls[0][1]


def test_write_shows_the_model_only_the_top_players():
    many = {pid: player('Hitter %d' % pid, 'CF', contact=(pid - 100) * 8) for pid in range(100, 112)}
    f = rookies.class_facts(world(), many, sorted(many), 1998)
    model = Scripted('Big class\n\nHitter 111 is new.')
    rookies.write(f, 'B', model)
    assert 'Hitter 111' in model.calls[0][1] and 'Hitter 100' not in model.calls[0][1]


def test_write_falls_back_on_a_stray_number_a_budget_error_and_errors():
    f = facts()
    wrong = 'A class of speed and arms\n\nJose Diaz grades 81 for speed.'
    piece = rookies.write(f, 'B', Scripted(wrong, wrong))
    assert (piece['source'], piece['reason']) == ('template', 'numbers')
    assert piece['headline'] == 'The rookie class of 1998'
    spent = rookies.write(f, 'B', Scripted(hive.BudgetExceeded('spent')))
    assert (spent['source'], spent['reason']) == ('template', 'budget')
    down = rookies.write(f, 'B', Scripted(hive.HiveError('down'), hive.HiveError('down')))
    assert (down['source'], down['reason']) == ('template', 'error')
