"""moves.py on hand-made snapshots and players, and gamedata.free_agents() on synthetic PYF files (there are no game
files in the repo). watch.py's and server.py's use of these are in test_watch.py and test_server.py."""
import json
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import hive      # noqa: E402
import moves     # noqa: E402

ASSN_NAME = '1998 Major Leagues'


def player(name, pos, born):
    return {'name': name, 'pos': pos, 'born': born}


PLAYERS = {
    50: player('Id Small', 'P', 1960),            # under 100: not a player, left out of the snapshot
    100: player('Al Winner', 'RF', 1970),
    101: player('Joe Old', 'P', 1960),
    200: player('Bo Loser', 'P', 1975),
    300: player('Pat Smith', 'SS', 1971),
    400: player('Ann Bat', '1B', 1966),
    600: player('Gone Man', 'C', 1950),
}
CAREER = {'bat': {400: {'hr': 499, 'h': 2100, 'rbi': 1500, 'sb': 10, 'ab': 7000}},
          'pit': {101: {'w': 199, 'sv': 3, 'so': 2100, 'outs': 3000}}}
SEASON = {'bat': {400: {'hr': 41, 'h': 170, 'rbi': 90, 'sb': 2}}, 'pit': {}}
TEAMS = {1: {'tid': 1, 'name': 'Ash'}, 2: {'tid': 2, 'name': 'Boston Red Sox'}}


def assoc(rosters, name=ASSN_NAME, season_year=None):
    """An association dict as gamedata.association() gives it, for the rosters {tid: [pid]} given."""
    return {'name': name, 'season_year': season_year,
            'teams': {tid: dict(TEAMS[tid], roster=list(rosters.get(tid, []))) for tid in TEAMS}, 'games': []}


EMPTY = {'bat': {}, 'pit': {}}
PREV_ROSTERS = {1: [100, 101], 2: [200, 400]}


def prev_snapshot():
    return moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, SEASON)


def test_snapshot_places_every_player_and_keeps_only_the_lines_there_are():
    s = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, SEASON)
    assert s['year'] == 1998
    assert s['where'] == {'100': 1, '101': 1, '200': 2, '300': 0, '400': 2, '600': -1}     # 600: retired
    assert s['names']['400'] == 'Ann Bat' and s['pos']['101'] == 'P' and s['born']['600'] == 1950
    assert s['career'] == {
        '101': {'hr': 0, 'h': 0, 'rbi': 0, 'sb': 0, 'w': 199, 'sv': 3, 'so_p': 2100},
        '400': {'hr': 499, 'h': 2100, 'rbi': 1500, 'sb': 10, 'w': 0, 'sv': 0, 'so_p': 0},
    }
    assert s['season'] == {'400': {'hr': 41, 'h': 170, 'rbi': 90, 'sb': 2, 'w': 0, 'sv': 0, 'so_p': 0}}
    assert json.loads(json.dumps(s)) == s                                  # JSON-able, keys already strings


def test_snapshot_year_is_none_without_a_year_in_the_name():
    assert moves.snapshot(assoc(PREV_ROSTERS, 'Majors'), PLAYERS, set(), CAREER, SEASON)['year'] is None


def test_snapshot_year_is_the_season_date_before_the_name_year():
    def year(a):
        return moves.snapshot(a, PLAYERS, {300}, CAREER, SEASON)['year']

    assert year(assoc(PREV_ROSTERS, 'MLBPA97', season_year=2008)) == 2008
    assert year(assoc(PREV_ROSTERS, '1998 Major Leagues', 2001)) == 2001
    assert year(assoc(PREV_ROSTERS, 'MLBPA97')) is None


def test_ages_and_the_rollover_use_the_season_date_of_a_career_league():
    prev = moves.snapshot(assoc(PREV_ROSTERS, 'MLBPA97', season_year=2007), PLAYERS, {300}, CAREER, SEASON)
    cur = moves.snapshot(assoc({1: [100], 2: [200, 400]}, 'MLBPA97', season_year=2008), PLAYERS, {300}, CAREER, SEASON)
    got = moves.diff(prev, cur, TEAMS, same_season=prev['year'] == cur['year'])
    # Joe Old retires at 48 (2008 - 1960). Ann Bat's 41 home runs are last season's lines still in the stats file:
    # a rollover step reports no season milestone, or every 40-homer season would be announced twice.
    assert [(e['kind'], e['name'], e['age'], e.get('stat'), e.get('value')) for e in got] == [
        ('retired', 'Joe Old', 48, None, None)]


def test_first_snapshot_yields_no_events():
    cur = prev_snapshot()
    assert moves.diff(None, cur, TEAMS) == []


def test_diff_names_each_kind_of_move_in_a_stable_order():
    cur = moves.snapshot(assoc({1: [200], 2: [300, 400, 500]}),
                         {**PLAYERS, 500: player('Kim New', 'SS', 1977)}, {100},
                         {'bat': {400: {'hr': 500, 'h': 2100, 'sb': 10}}, 'pit': {}},
                         {'bat': {400: {'hr': 42, 'h': 170, 'sb': 2}}, 'pit': {}})
    got = moves.diff(prev_snapshot(), cur, TEAMS)
    assert [(e['kind'], e['name']) for e in got] == [
        ('milestone', 'Ann Bat'), ('moved', 'Bo Loser'), ('new', 'Kim New'), ('released', 'Al Winner'),
        ('retired', 'Joe Old'), ('signed', 'Pat Smith')]
    by = {e['kind']: e for e in got}
    assert by['signed'] == {'kind': 'signed', 'pid': 300, 'name': 'Pat Smith', 'pos': 'SS', 'age': 27,
                            'from': 'Free agents', 'to': 'Boston Red Sox'}
    assert by['released']['from'] == 'Ash' and by['released']['to'] == 'Free agents'
    assert by['moved']['from'] == 'Boston Red Sox' and by['moved']['to'] == 'Ash'
    assert by['new'] == {'kind': 'new', 'pid': 500, 'name': 'Kim New', 'pos': 'SS', 'age': 21, 'from': '',
                         'to': 'Boston Red Sox'}
    assert by['retired'] == {'kind': 'retired', 'pid': 101, 'name': 'Joe Old', 'pos': 'P', 'age': 38,
                             'from': 'Ash', 'to': ''}
    assert got[0] == {'kind': 'milestone', 'pid': 400, 'name': 'Ann Bat', 'pos': '1B', 'age': 32,
                      'from': '', 'to': 'Boston Red Sox', 'stat': 'career hr', 'value': 500, 'total': 500}


def test_a_player_who_stays_put_or_is_still_retired_has_no_event():
    cur = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, SEASON)
    assert moves.diff(prev_snapshot(), cur, TEAMS) == []


def test_career_milestone_is_the_highest_mark_crossed_in_one_step():
    more = {'bat': {400: {'hr': 611, 'h': 2600, 'sb': 10}}, 'pit': {}}
    got = moves.diff(prev_snapshot(), moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, more, SEASON), TEAMS)
    assert [(e['stat'], e['value'], e['total']) for e in got if e['kind'] == 'milestone'] == [
        ('career h', 2500, 2600), ('career hr', 600, 611)]


def test_season_milestone_counts_only_in_the_same_season():
    cur_season = {'bat': {400: {'hr': 41, 'h': 170, 'sb': 2}}, 'pit': {}}
    later = {'bat': {400: {'hr': 42, 'h': 170, 'sb': 2}}, 'pit': {}}
    base = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, cur_season)
    cur = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, later)
    assert [e for e in moves.diff(base, cur, TEAMS, same_season=True) if e['kind'] == 'milestone'] == []
    # across a rollover the stats may still be last season's: no season milestone either way
    assert [e for e in moves.diff(base, cur, TEAMS, same_season=False) if e['kind'] == 'milestone'] == []


def test_season_milestone_crosses_in_the_same_season():
    base = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, {'bat': {400: {'hr': 39}}, 'pit': {}})
    cur = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, CAREER, {'bat': {400: {'hr': 41}}, 'pit': {}})
    got = moves.diff(base, cur, TEAMS, same_season=True)
    assert [(e['stat'], e['value'], e['total']) for e in got if e['kind'] == 'milestone'] == [('season hr', 40, 41)]


def test_season_pitching_milestone_and_the_age_from_the_snapshot_year():
    base = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, EMPTY, {'bat': {}, 'pit': {101: {'so': 249}}})
    cur = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, EMPTY, {'bat': {}, 'pit': {101: {'so': 251}}})
    got = moves.diff(base, cur, TEAMS, same_season=True)
    assert [(e['stat'], e['value'], e['age']) for e in got] == [('season so_p', 250, 38)]     # 1998 - 1960


def test_notable_is_a_milestone_or_a_retirement_at_a_career_total():
    cur = prev_snapshot()
    assert moves.notable({'kind': 'milestone', 'pid': 400}, cur)
    assert moves.notable({'kind': 'retired', 'pid': 101}, cur)          # 199 wins: over the 150 bar
    assert not moves.notable({'kind': 'retired', 'pid': 600}, cur)      # no career line at all
    assert not moves.notable({'kind': 'signed', 'pid': 300}, cur)
    assert not moves.notable({'kind': 'released', 'pid': 100}, cur)
    assert not moves.notable({'kind': 'new', 'pid': 500}, cur)
    low = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, {'bat': {600: {'hr': 199}}, 'pit': {}}, EMPTY)
    assert not moves.notable({'kind': 'retired', 'pid': 600}, low)
    high = moves.snapshot(assoc(PREV_ROSTERS), PLAYERS, {300}, {'bat': {600: {'hr': 200}}, 'pit': {}}, EMPTY)
    assert moves.notable({'kind': 'retired', 'pid': 600}, high)


def test_facts_carry_the_event_and_the_career_totals_when_given():
    ev = dict(kind='milestone', pid=400, name='Ann Bat', pos='1B', age=32, **{'from': '', 'to': 'Boston Red Sox'},
              stat='career hr', value=500, total=500)
    f = moves.facts(ev, ASSN_NAME, 'June 3', {'hr': 500})
    assert f == {'association': ASSN_NAME, 'date': 'June 3', 'kind': 'milestone', 'name': 'Ann Bat', 'pos': '1B',
                 'age': 32, 'from': '', 'to': 'Boston Red Sox', 'stat': 'career hr', 'value': 500, 'total': 500,
                 'career': {'hr': 500}}
    signed = dict(kind='signed', pid=300, name='Pat Smith', pos='SS', age=27, **{'from': 'Free agents', 'to': 'Ash'})
    plain = moves.facts(signed, ASSN_NAME, 'Offseason')
    assert not {'stat', 'value', 'total', 'career'} & set(plain)


EVENTS = [
    dict(kind='signed', pid=300, name='Pat Smith', pos='SS', age=27, **{'from': 'Free agents', 'to': 'Boston Red Sox'}),
    dict(kind='released', pid=100, name='Al Winner', pos='', age=None, **{'from': 'Ash', 'to': 'Free agents'}),
    dict(kind='moved', pid=200, name='Bo Loser', pos='P', age=None, **{'from': 'Boston Red Sox', 'to': 'Ash'}),
    dict(kind='new', pid=500, name='Kim New', pos='SS', age=21, **{'from': '', 'to': 'Boston Red Sox'}),
    dict(kind='retired', pid=101, name='Joe Old', pos='P', age=38, **{'from': 'Ash', 'to': ''}),
    dict(kind='retired', pid=102, name='', pos='', age=None, **{'from': '', 'to': ''}),
    dict(kind='milestone', pid=400, name='Ann Bat', pos='1B', age=32, **{'from': '', 'to': 'Boston Red Sox'},
         stat='career hr', value=500, total=501),
    dict(kind='milestone', pid=400, name='Ann Bat', pos='1B', age=32, **{'from': '', 'to': ''},
         stat='season hr', value=40, total=41),
    dict(kind='milestone', pid=401, name='Zed Tall', pos='', age=None, **{'from': '', 'to': 'Ash'},
         stat='career so_p', value=2000, total=2001),
    dict(kind='milestone', pid=402, name='Bo Quick', pos='', age=None, **{'from': '', 'to': 'Ash'},
         stat='career sb', value=300, total=300),
]


@pytest.mark.parametrize('event', EVENTS, ids=lambda e: '%s-%s' % (e['kind'], e['stat'] if 'stat' in e else e['name']))
def test_template_is_never_empty_and_names_the_player_without_a_pronoun(event):
    f = moves.facts(event, ASSN_NAME, 'June 3')
    piece = moves.template(f)
    assert piece['headline'].strip() and piece['body'].strip()
    assert event['name'] in piece['headline'] or not event['name']
    assert '\n' not in piece['headline']


def test_template_texts_say_what_happened():
    def tpl(i):
        return moves.template(moves.facts(EVENTS[i], ASSN_NAME, 'June 3'))

    assert tpl(0) == {'headline': 'Pat Smith signs with Boston Red Sox',
                      'body': 'Pat Smith (SS, 27) signed with Boston Red Sox from the free agents.'}
    assert tpl(4) == {'headline': 'Joe Old retires', 'body': 'Joe Old (P, 38) has retired.'}
    assert tpl(6)['headline'] == 'Ann Bat reached 500 career home runs'
    assert tpl(6)['body'] == 'Ann Bat (1B, 32) is with Boston Red Sox and has reached 500 career home runs.'
    assert tpl(7)['headline'] == 'Ann Bat reached 40 home runs this season'
    assert tpl(8)['headline'] == 'Zed Tall reached 2000 career strikeouts'


def test_template_adds_the_career_totals_of_a_retirement():
    f = moves.facts(EVENTS[4], ASSN_NAME, 'Offseason', {'hr': 1, 'h': 2, 'w': 199, 'sv': 0})
    assert moves.template(f)['body'] == ('Joe Old (P, 38) has retired. The career totals are 1 home run, 2 hits, '
                                         '199 wins.')


def test_date_text_is_the_last_played_day_or_offseason():
    assert moves.date_text((6, 3)) == 'June 3'
    assert moves.date_text(None) == 'Offseason'


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
    f = moves.facts(EVENTS[6], ASSN_NAME, 'June 3')
    model = Scripted('Ann Bat reaches 500\n\nAnn Bat (1B, 32) is with Boston Red Sox and has reached 500 career home '
                     'runs.')
    piece = moves.write(f, 'B', model)
    assert (piece['source'], piece['headline']) == ('glm', 'Ann Bat reaches 500')
    assert model.calls[0][0] == moves.SYSTEM and 'Ann Bat' in model.calls[0][1]


def test_write_falls_back_on_a_stray_number_a_budget_error_and_errors():
    f = moves.facts(EVENTS[6], ASSN_NAME, 'June 3')
    wrong = 'Ann Bat reaches 502\n\nAnn Bat has reached 502 career home runs.'
    piece = moves.write(f, 'B', Scripted(wrong, wrong))
    assert (piece['source'], piece['reason']) == ('template', 'numbers')
    spent = moves.write(f, 'B', Scripted(hive.BudgetExceeded('spent')))
    assert (spent['source'], spent['reason']) == ('template', 'budget')
    down = moves.write(f, 'B', Scripted(hive.HiveError('down'), hive.HiveError('down')))
    assert (down['source'], down['reason']) == ('template', 'error')


def pyf_bytes(ids, head=b'PPD:'):
    return head + struct.pack('<Ih', 0, len(ids)) + struct.pack('<%dH' % len(ids), *ids)


def test_free_agents_reads_the_ids_after_the_count(tmp_path):
    f = tmp_path / 'X.PYF'
    f.write_bytes(pyf_bytes([300, 301, 65535]))
    assert gamedata.free_agents(str(f)) == {300, 301, 65535}
    f.write_bytes(pyf_bytes([]))
    assert gamedata.free_agents(str(f)) == set()


@pytest.mark.parametrize('blob', [b'', b'PPD', pyf_bytes([300], head=b'XXXX'), pyf_bytes([300, 301])[:-2]])
def test_free_agents_refuses_a_file_that_is_not_a_whole_pyf(tmp_path, blob):
    f = tmp_path / 'X.PYF'
    f.write_bytes(blob)
    with pytest.raises(ValueError):
        gamedata.free_agents(str(f))
