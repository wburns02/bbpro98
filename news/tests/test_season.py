"""season.py on synthetic leagues: complete(), the preview and awards facts with their thresholds and ties, the
templates' numbers, and the write_* fallbacks. gamedata's roster and scope additions have no fixture here (no game
files in the repo), so they are not tested; watch.py's use of these pieces is in test_watch.py."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feed     # noqa: E402
import hive     # noqa: E402
import recap    # noqa: E402
import season   # noqa: E402

NAMES = {101: 'Ann Hart', 102: 'Bo Lee', 103: 'Cal Ortiz', 104: 'Dee Moss', 105: 'Eli Park',
         151: 'Cy Ace', 152: 'Rel Closer', 153: 'Sam Save', 154: 'Ty Short', 155: 'Uma Few', 156: 'Vic Nine',
         201: 'Fay Quinn', 202: 'Gus Vale', 203: 'Hal Wade', 251: 'Ned Bird', 252: 'Oz Tal',
         301: 'Ivy Cole', 302: 'Jo Dean', 351: 'Kim Eve', 401: 'Lou Fox', 451: 'Mo Gil'}
ROSTERS = {1: [101, 102, 103, 104, 105, 151, 152, 153, 154, 155, 156], 2: [201, 202, 203, 251, 252],
           3: [301, 302, 351], 4: [401, 451]}
EMPTY = {'bat': {}, 'pit': {}}


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


def team(tid, name, league='American League', division='West', roster=(), manager='Mgr'):
    return {'tid': tid, 'name': name, 'abbrev': name[:3].upper(), 'city': 'CITY.', 'stadium': name + ' Park',
            'manager': manager, 'league': league, 'division': division, 'w': 0, 'l': 0, 'roster': list(roster)}


def gm(month, day, slot, away, home, ar=0, hr=0, played=True, innings=9):
    return {'month': month, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': innings}


def assoc(teams, games):
    return {'name': '1998 Major Leagues', 'teams': teams, 'games': games}


def four_teams(unplayed=False):
    """Ash and Birch (American League West and East), Cedar and Dogwood (National League East). Every away team wins
    its game, so the records are Ash 3-0, Birch 2-1, Cedar 1-2, Dogwood 0-3. Six games over four teams: 3 team games.
    With unplayed, the last game is not played."""
    teams = {1: team(1, 'Ash', 'American League', 'West', ROSTERS[1]),
             2: team(2, 'Birch', 'American League', 'East', ROSTERS[2]),
             3: team(3, 'Cedar', 'National League', 'East', ROSTERS[3]),
             4: team(4, 'Dogwood', 'National League', 'East', ROSTERS[4])}
    pairs = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
    games = [gm(4, day, 13, a, h, ar=5, hr=3, played=not (unplayed and day == 6))
             for day, (a, h) in enumerate(pairs, 1)]
    return assoc(teams, games)


def batting(ab, h, hr=0, rbi=0, h2b=0, h3b=0, bb=0, r=0, sb=0, so=0):
    return {'ab': ab, 'h': h, 'h2b': h2b, 'h3b': h3b, 'hr': hr, 'rbi': rbi, 'bb': bb, 'so': so, 'r': r, 'sb': sb}


def pitching(outs, er, w=0, l=0, so=0, sv=0):
    return {'outs': outs, 'h': 0, 'er': er, 'bb': 0, 'so': so, 'w': w, 'l': l, 'sv': sv}


def full_season():
    """One set of lines for the four_teams() rosters, used as last season (preview) or this season (awards)."""
    bats = {101: batting(500, 150, h2b=30, h3b=2, hr=30, rbi=100, bb=60, r=90, sb=5),
            102: batting(400, 120, h2b=20, hr=20, rbi=80, bb=40, r=70, sb=10),
            103: batting(300, 90, h2b=10, h3b=1, hr=10, rbi=40, bb=30, r=40, sb=2),
            104: batting(200, 60, h2b=5, hr=5, rbi=30, bb=10, r=30),
            105: batting(9, 9, hr=9, rbi=9),
            301: batting(400, 100, h2b=10, hr=5, rbi=40, bb=20, r=50),
            401: batting(400, 100, h2b=10, hr=5, rbi=40, bb=20, r=50)}
    pits = {151: pitching(180, 20, w=15, l=5, so=150),
            152: pitching(60, 5, w=2, l=3, so=40, sv=35),
            153: pitching(6, 0, so=4, sv=10),
            154: pitching(6, 0, so=4, sv=9),
            155: pitching(8, 0),
            156: pitching(9, 0),
            251: pitching(210, 30, w=12, l=8, so=200),
            351: pitching(150, 40, w=10, l=5, so=100),
            451: pitching(150, 40, w=10, l=5, so=100)}
    return {'bat': bats, 'pit': pits}


def rows(facts):
    """{team name: that team's preview row}."""
    return {t['name']: t for d in facts['divisions'] for t in d['teams']}


def blank_league(a):
    for t in a['teams'].values():
        t['league'] = t['division'] = ''
    return a


def check_numbers(piece, facts):
    assert recap.numbers_ok(piece['headline'] + '\n' + piece['body'], facts), piece['body']


def test_complete_needs_games_and_every_one_played():
    assert season.complete(assoc({}, [])) is False
    assert season.complete(assoc({}, [gm(4, 1, 13, 1, 2, played=False)])) is False
    assert season.complete(four_teams(unplayed=True)) is False
    assert season.complete(four_teams()) is True


def test_preview_hitter_needs_100_at_bats_then_most_homers_then_rbi_then_name():
    last = {'bat': {101: batting(99, 40, hr=40, rbi=90), 102: batting(100, 30, hr=30, rbi=60),
                    103: batting(100, 30, hr=30, rbi=70), 104: batting(100, 30, hr=30, rbi=70)}, 'pit': {}}
    h = rows(season.preview_facts(four_teams(), last, NAMES))['Ash']['hitter']
    assert h == {'name': 'Cal Ortiz', 'avg': '.300', 'hr': 30, 'rbi': 70}


def test_preview_pitcher_needs_150_outs_then_most_wins_then_lower_era_then_name():
    last = {'bat': {}, 'pit': {151: pitching(149, 10, w=30, l=1), 152: pitching(150, 60, w=12, l=3),
                               153: pitching(180, 15, w=12, l=3), 154: pitching(240, 80, w=12, l=3)}}
    p = rows(season.preview_facts(four_teams(), last, NAMES))['Ash']['pitcher']
    assert p == {'name': 'Sam Save', 'w': 12, 'l': 3, 'era': '2.25', 'so': 0}
    tied = {'bat': {}, 'pit': {151: pitching(150, 30, w=12, l=3), 152: pitching(150, 30, w=12, l=3)}}
    assert rows(season.preview_facts(four_teams(), tied, NAMES))['Ash']['pitcher']['name'] == 'Cy Ace'


def test_preview_leaves_out_players_on_no_roster_and_team_lines():
    a = four_teams()
    a['teams'][1]['roster'].append(5)               # an id under 100 is a team line, never a player
    last = {'bat': {5: batting(500, 200, hr=99, rbi=99), 999: batting(500, 200, hr=80, rbi=80),
                    101: batting(100, 20, hr=3, rbi=3)}, 'pit': {}}
    assert rows(season.preview_facts(a, last, NAMES))['Ash']['hitter']['name'] == 'Ann Hart'


def test_a_player_on_two_rosters_counts_for_the_first_team():
    a = four_teams()
    a['teams'][2]['roster'].append(101)             # Ann Hart is also on Birch's roster; Ash is the lower tid
    last = {'bat': {101: batting(300, 90, hr=30, rbi=90)}, 'pit': {}}
    r = rows(season.preview_facts(a, last, NAMES))
    assert r['Ash']['hitter']['name'] == 'Ann Hart'
    assert r['Birch']['hitter'] is None


def test_divisions_and_teams_come_in_standings_order():
    a = four_teams()
    got = season.preview_facts(a, full_season(), NAMES)['divisions']
    assert [(d['league'], d['division'], [t['name'] for t in d['teams']]) for d in got] == [
        (d['league'], d['division'], [t['name'] for t in d['teams']]) for d in feed.standings(a)]
    assert [d['division'] for d in got] == ['West', 'East', 'East']


def test_opening_day_is_the_earliest_game_and_the_counts_cover_every_game():
    a = four_teams()
    a['games'] = [gm(5, 2, 13, 1, 2), gm(4, 9, 13, 3, 4), gm(4, 1, 13, 1, 3, played=False)]
    f = season.preview_facts(a, EMPTY, NAMES)
    assert (f['opening_day'], f['games'], f['teams']) == ('April 1', 3, 4)
    assert season.preview_facts(assoc(a['teams'], []), EMPTY, NAMES)['opening_day'] is None


def test_preview_facts_lines_up_with_last_season():
    f = season.preview_facts(four_teams(), full_season(), NAMES)
    r = rows(f)
    assert r['Ash']['hitter'] == {'name': 'Ann Hart', 'avg': '.300', 'hr': 30, 'rbi': 100}
    assert r['Ash']['pitcher'] == {'name': 'Cy Ace', 'w': 15, 'l': 5, 'era': '3.00', 'so': 150}
    assert r['Birch']['hitter'] is None and r['Birch']['pitcher']['era'] == '3.86'
    assert r['Cedar']['pitcher']['name'] == 'Kim Eve' and r['Dogwood']['pitcher']['name'] == 'Mo Gil'


def test_preview_template_text():
    t = season.preview_template(season.preview_facts(four_teams(), full_season(), NAMES))
    assert t['headline'] == 'The season ahead'
    assert t['body'].split('\n')[0] == (
        'The 1998 Major Leagues season opens on April 1 with 4 teams and 6 games on the schedule.')
    assert t['body'].split('\n')[1] == (
        'American League West: Ash, managed by Mgr. Ann Hart hit 30 home runs with 100 RBI last season. '
        'Cy Ace went 15-5 with a 3.00 ERA.')


def preview_fixtures():
    blank = blank_league(four_teams())
    empty = {'association': '1998 Major Leagues', 'teams': 0, 'games': 0, 'opening_day': None, 'divisions': []}
    return [season.preview_facts(four_teams(), full_season(), NAMES),
            season.preview_facts(four_teams(), EMPTY, NAMES),
            season.preview_facts(assoc(four_teams()['teams'], []), EMPTY, NAMES),
            season.preview_facts(blank, full_season(), NAMES),
            empty]


def test_preview_template_passes_numbers_ok_on_each_fixture():
    for facts in preview_fixtures():
        check_numbers(season.preview_template(facts), facts)
    blank = season.preview_template(season.preview_facts(blank_league(four_teams()), EMPTY, NAMES))
    assert blank['body'].split('\n')[1].startswith('The league: Ash, managed by Mgr.')


def test_write_preview_takes_the_model_answer_that_checks_out():
    facts = season.preview_facts(four_teams(), full_season(), NAMES)
    ok = Scripted('Ash open\n\nAsh and Birch open the season with Ann Hart and Cy Ace leading the way.')
    piece = season.write_preview(facts, 'B', ok)
    assert (piece['headline'], piece['source']) == ('Ash open', 'glm')
    assert ok.calls == [(season.PREVIEW_SYSTEM, recap.facts_message(facts), 'B')]


def test_write_preview_falls_back_on_budget_error_and_on_an_invented_number():
    facts = season.preview_facts(four_teams(), full_season(), NAMES)
    spent = season.write_preview(facts, 'B', Scripted(hive.BudgetExceeded('spent')))
    assert (spent['source'], spent['reason'], spent['headline']) == ('template', 'budget', 'The season ahead')
    wrong = Scripted('Ash\n\nAsh won 99 games.', 'Ash\n\nAsh won 98 games.')
    bad = season.write_preview(facts, 'B', wrong)
    assert (bad['source'], bad['reason']) == ('template', 'numbers') and len(wrong.calls) == 2
    down = season.write_preview(facts, 'B', Scripted(hive.HiveError('down'), hive.HiveError('down')))
    assert (down['source'], down['reason']) == ('template', 'error')


def test_awards_candidates_are_ranked_by_score_and_capped_at_three():
    al, nl = season.awards_facts(four_teams(), full_season(), NAMES)['leagues']
    assert [c['name'] for c in al['mvp']] == ['Ann Hart', 'Bo Lee', 'Cal Ortiz']       # Dee Moss is fourth
    assert [c['runs_created'] for c in al['mvp']] == [103, 73, 48]
    assert al['mvp'][0] == {'name': 'Ann Hart', 'team': 'Ash', 'avg': '.300', 'hr': 30, 'rbi': 100, 'r': 90,
                            'sb': 5, 'runs_created': 103}
    assert [c['name'] for c in al['cy_young']] == ['Cy Ace', 'Rel Closer', 'Ned Bird']
    assert al['cy_young'][1] == {'name': 'Rel Closer', 'team': 'Ash', 'w': 2, 'l': 3, 'era': '2.25', 'so': 40,
                                 'sv': 35, 'ip': '20.0'}
    assert al['cy_young'][2]['ip'] == '70.0'
    assert al['champions'] == [{'division': 'West', 'team': 'Ash', 'record': '3-0'},
                               {'division': 'East', 'team': 'Birch', 'record': '2-1'}]
    assert nl['league'] == 'National League'
    assert nl['champions'] == [{'division': 'East', 'team': 'Cedar', 'record': '1-2'}]


def test_awards_ties_go_to_the_name():
    nl = season.awards_facts(four_teams(), full_season(), NAMES)['leagues'][1]
    assert [c['name'] for c in nl['mvp']] == ['Ivy Cole', 'Lou Fox']    # the same line on Cedar and Dogwood
    assert [c['name'] for c in nl['cy_young']] == ['Kim Eve', 'Mo Gil']


def test_mvp_needs_3_point_1_at_bats_per_team_game():
    # Three team games: 9.3 at-bats. Nine is out however many runs he created; ten is in.
    lines = {'bat': {105: batting(9, 9, hr=9), 104: batting(10, 4)}, 'pit': {}}
    al = season.awards_facts(four_teams(), lines, NAMES)['leagues'][0]
    assert [(c['name'], c['runs_created']) for c in al['mvp']] == [('Dee Moss', 2)]


def test_cy_young_needs_one_inning_per_team_game_or_ten_saves():
    # Three team games: nine outs. Eight is out; nine is in; a reliever with ten saves at six outs is in, nine is out.
    lines = {'bat': {}, 'pit': {155: pitching(8, 0), 156: pitching(9, 0), 154: pitching(6, 0, sv=9),
                                153: pitching(6, 0, sv=10, so=4)}}
    al = season.awards_facts(four_teams(), lines, NAMES)['leagues'][0]
    assert [c['name'] for c in al['cy_young']] == ['Sam Save', 'Vic Nine']


def test_one_league_association_has_a_blank_league_name():
    f = season.awards_facts(blank_league(four_teams()), full_season(), NAMES)
    lg = f['leagues'][0]
    assert [x['league'] for x in f['leagues']] == ['']
    assert [c['name'] for c in lg['mvp']] == ['Ann Hart', 'Bo Lee', 'Cal Ortiz']
    assert lg['champions'] == [{'division': '', 'team': 'Ash', 'record': '3-0'}]
    assert season.awards_template(f)['body'].startswith('The league: Ann Hart of the Ash is the MVP')


def test_awards_need_a_finished_season():
    with pytest.raises(ValueError):
        season.awards_facts(four_teams(unplayed=True), full_season(), NAMES)


def test_awards_template_text():
    body = season.awards_template(season.awards_facts(four_teams(), full_season(), NAMES))['body']
    assert body == ('American League: Ann Hart of the Ash is the MVP, batting .300 with 30 home runs and 100 RBI. '
                    'Cy Ace of the Ash wins the Cy Young at 15-5 with a 3.00 ERA. '
                    'Champions: Ash (3-0), Birch (2-1).\n'
                    'National League: Ivy Cole of the Cedar is the MVP, batting .250 with 5 home runs and 40 RBI. '
                    'Kim Eve of the Cedar wins the Cy Young at 10-5 with a 7.20 ERA. Champions: Cedar (1-2).')


def test_awards_template_passes_numbers_ok_on_each_fixture():
    fixtures = [season.awards_facts(four_teams(), full_season(), NAMES),
                season.awards_facts(four_teams(), EMPTY, NAMES),
                season.awards_facts(blank_league(four_teams()), full_season(), NAMES)]
    for facts in fixtures:
        check_numbers(season.awards_template(facts), facts)
    no_players = season.awards_template(fixtures[1])['body']
    assert no_players.startswith('American League: Champions: Ash (3-0), Birch (2-1).')


def test_write_awards_falls_back_on_budget_error_and_on_an_invented_number():
    facts = season.awards_facts(four_teams(), full_season(), NAMES)
    spent = season.write_awards(facts, 'B', Scripted(hive.BudgetExceeded('spent')))
    assert (spent['source'], spent['reason'], spent['headline']) == ('template', 'budget', 'Season awards')
    wrong = Scripted('Awards\n\nAnn Hart won 31 homers.', 'Awards\n\nAnn Hart won 33 homers.')
    bad = season.write_awards(facts, 'B', wrong)
    assert (bad['source'], bad['reason']) == ('template', 'numbers')
    ok = Scripted('Awards\n\nAnn Hart is the MVP for Ash.')
    assert season.write_awards(facts, 'B', ok)['source'] == 'glm'
    assert ok.calls[0][0] == season.AWARDS_SYSTEM
