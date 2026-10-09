"""scout.py on synthetic teams, and gamedata.players() / names() on synthetic PYR files built with the game's cipher (there
are no game files in the repo). watch.py's and server.py's use of these are in test_watch.py and test_server.py."""
import datetime
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import hive      # noqa: E402
import recap     # noqa: E402
import scout     # noqa: E402
import league    # noqa: E402 (work/ is on the path once gamedata is imported)

SEED = (0x6b, 0xe2)     # the cipher seed is per file: PYR bytes 0-1
BORN_1966 = datetime.date(1966, 5, 9).toordinal() + 365     # the birth serial: fromordinal(serial - 365)
BORN_1970 = datetime.date(1970, 1, 2).toordinal() + 365


def pyr_record(pid, first, last, serial=0, bats=0, throws=0, pos=0, contact=0, power=0, speed=0, stamina=0,
               control=0, strikeout=0, fields=()):
    """One 192-byte player record, plain. The offsets are written out here, not taken from gamedata, so the test checks
    gamedata's constants. fields: (position, rating) pairs written to the fielding slots."""
    p = bytearray(192)
    p[0], p[1] = pid & 0xff, pid >> 8
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, serial)
    p[0x41], p[0x42], p[0x44] = bats, throws, pos
    p[0x5d], p[0x5e], p[0x5f] = contact, power, speed
    p[0x62], p[0x63] = stamina, control
    p[0x76] = strikeout
    for position, rating in fields:
        p[0x5d + 14 + position - 1] = rating
    return bytes(p)


def write_pyr(path, records, seed=SEED):
    """A PYR file: a header record (the seed in its bytes 0-1), then each record enciphered as the game does."""
    t = league._forward(seed)
    path.write_bytes(bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records))
    return str(path)


RECORDS = [
    pyr_record(100, 'Ann', 'Hart', serial=BORN_1966, bats=1, throws=1, pos=9, contact=92, power=21, speed=70,
               strikeout=5, fields=((9, 60), (1, 11))),
    pyr_record(200, 'Bo', 'Lee', serial=0, bats=0, throws=2, pos=1, stamina=69, control=97, strikeout=47,
               fields=((1, 33),)),
    pyr_record(300, 'Cy', 'Ace', serial=BORN_1970, bats=3, throws=1, pos=10, contact=50, power=50, speed=50,
               strikeout=99),
    pyr_record(400, 'Dee', 'Moss', serial=0xFFFFFFFF, bats=2, throws=2, pos=2),
    pyr_record(50, 'Id', 'Small', serial=BORN_1966, pos=2),          # under 100: a team line, not a player
    pyr_record(500, '', '', serial=BORN_1966, pos=2),                # no name: not a player
]


def test_players_reads_each_field_of_the_pyr_layout(tmp_path):
    got = gamedata.players(write_pyr(tmp_path / 'x.PYR', RECORDS))
    assert sorted(got) == [100, 200, 300, 400]
    assert got[100] == {'name': 'Ann Hart', 'pos': 'RF', 'bats': 'L', 'throws': 'L', 'born': 1966, 'contact': 92,
                        'power': 21, 'speed': 70, 'stamina': 0, 'control': 0, 'strikeout': 5, 'fielding': 60}
    assert got[200] == {'name': 'Bo Lee', 'pos': 'P', 'bats': '', 'throws': 'R', 'born': None, 'contact': 0,
                        'power': 0, 'speed': 0, 'stamina': 69, 'control': 97, 'strikeout': 47, 'fielding': 33}
    assert got[300] == {'name': 'Cy Ace', 'pos': '', 'bats': 'S', 'throws': 'L', 'born': 1970, 'contact': 50,
                        'power': 50, 'speed': 50, 'stamina': 0, 'control': 0, 'strikeout': 99, 'fielding': None}
    assert got[400]['born'] is None and got[400]['bats'] == 'R' and got[400]['throws'] == 'R'


def test_names_is_unchanged_on_the_same_file(tmp_path):
    assert gamedata.names(write_pyr(tmp_path / 'x.PYR', RECORDS)) == {
        100: 'Ann Hart', 200: 'Bo Lee', 300: 'Cy Ace', 400: 'Dee Moss'}


@pytest.mark.parametrize('size', [100, 192 * 2 + 1])
def test_a_file_that_is_not_pyr_is_a_value_error(tmp_path, size):
    f = tmp_path / 'x.PYR'
    f.write_bytes(bytes(size))
    with pytest.raises(ValueError):
        gamedata.names(str(f))
    with pytest.raises(ValueError):
        gamedata.players(str(f))


def test_players_position_and_hand_codes_out_of_range_are_blank(tmp_path):
    odd = [pyr_record(601, 'Odd', 'Hand', pos=0, bats=9, throws=3, serial=BORN_1966)]
    got = gamedata.players(write_pyr(tmp_path / 'x.PYR', odd))[601]
    assert (got['pos'], got['bats'], got['throws'], got['fielding']) == ('', '', '', None)


def player(name, pos='', bats='R', throws='R', born=1966, contact=0, power=0, speed=0, stamina=0, control=0,
           strikeout=0, fielding=0):
    """A players() entry."""
    return {'name': name, 'pos': pos, 'bats': bats, 'throws': throws, 'born': born, 'contact': contact,
            'power': power, 'speed': speed, 'stamina': stamina, 'control': control, 'strikeout': strikeout,
            'fielding': fielding}


PLAYERS = {
    101: player('Ann Hart', 'CF', bats='L', throws='L', contact=99, power=50, speed=99),
    102: player('Bo Lee', '1B', contact=50, power=99, speed=0),
    103: player('Cal Ortiz', 'SS', bats='', contact=50, power=50, speed=50),
    104: player('Dee Moss', 'C', contact=0, power=0, speed=0),
    105: player('Eli Park', '2B', bats='S', contact=99, power=99, speed=99),
    106: player('Fay Quinn', 'RF', contact=50, power=0, speed=50),
    107: player('Gus Vale', 'LF', contact=70, power=70, speed=70),
    108: player('Hub Zane', '', bats='', throws='', contact=0, power=0, speed=0),
    201: player('Ivy Cole', 'P', throws='L', control=99, strikeout=99, stamina=99),
    202: player('Jo Dean', 'P', control=50, strikeout=50, stamina=50),
    203: player('Kim Eve', 'P', born=None, control=99, strikeout=0, stamina=50),
    204: player('Lou Fox', 'P', control=0, strikeout=0, stamina=0),
    205: player('Mo Gil', 'P', control=70, strikeout=70, stamina=70),
    301: player('Ned Bird', 'P', control=99, strikeout=99, stamina=99),       # on Birch's roster only
}
LAST = {'bat': {102: {'ab': 100, 'h': 30, '2b': 0, '3b': 0, 'hr': 3, 'rbi': 40, 'bb': 0, 'so': 0, 'r': 0, 'sb': 0},
                101: {'ab': 99, 'h': 40, '2b': 0, '3b': 0, 'hr': 9, 'rbi': 9, 'bb': 0, 'so': 0, 'r': 0, 'sb': 0},
                105: {'ab': 500, 'h': 150, '2b': 0, '3b': 0, 'hr': 30, 'rbi': 100, 'bb': 0, 'so': 0, 'r': 0, 'sb': 0}},
        'pit': {201: {'outs': 179, 'er': 20, 'w': 15, 'l': 5, 'so': 150, 'sv': 0, 'h': 0, 'bb': 0},
                202: {'outs': 60, 'er': 10, 'w': 1, 'l': 2, 'so': 5, 'sv': 0, 'h': 0, 'bb': 0},
                205: {'outs': 59, 'er': 0, 'w': 9, 'l': 0, 'so': 60, 'sv': 0, 'h': 0, 'bb': 0}}}


def team(tid, name, roster=()):
    return {'tid': tid, 'name': name, 'abbrev': name[:3].upper(), 'city': 'CITY.', 'stadium': name + ' Park',
            'manager': 'Mgr', 'league': 'American League', 'division': 'West', 'w': 0, 'l': 0, 'roster': list(roster)}


def world():
    """Ash (tid 1) with eight hitters, one of them unplaced, and five pitchers; 208 is on the roster but not in
    PLAYERS. Birch (tid 2) has Ned Bird."""
    teams = {1: team(1, 'Ash', [101, 102, 103, 104, 105, 106, 107, 108, 201, 202, 203, 204, 205, 208]),
             2: team(2, 'Birch', [301])}
    return {'name': '1998 Major Leagues', 'teams': teams, 'games': []}


def hit_names(rows):
    return [r['name'] for r in rows]


def test_grade_endpoints_rounding_and_clamp():
    assert (scout.grade(0), scout.grade(99), scout.grade(50), scout.grade(92)) == (20, 80, 50, 75)
    assert scout.grade(-5) == 20 and scout.grade(150) == 80
    assert scout.grade(None) is None
    assert {scout.grade(r) for r in range(100)} == set(range(20, 81, 5))


@pytest.mark.parametrize('name, year', [
    ('1998 Major Leagues', 1998), ('1997 MLBPA Opening Day', 1997), ('1998', 1998),
    ('MLBPA Assn Defaults', None), ('19984 x', None), ('', None), (' 1998 x', None), ('1998x', None),
])
def test_year_of_reads_a_leading_year_only(name, year):
    assert scout.year_of(name) == year


def test_roster_orders_hitters_by_position_then_name_and_pitchers_by_grades():
    r = scout.roster(world(), 1, PLAYERS, 1998)
    assert hit_names(r['hitters']) == ['Dee Moss', 'Bo Lee', 'Eli Park', 'Cal Ortiz', 'Gus Vale', 'Ann Hart',
                                       'Fay Quinn', 'Hub Zane']
    assert hit_names(r['pitchers']) == ['Ivy Cole', 'Mo Gil', 'Jo Dean', 'Kim Eve', 'Lou Fox']


def test_roster_rows_are_graded_and_aged_and_skip_players_not_given():
    r = scout.roster(world(), 1, PLAYERS, 1998)
    assert r['hitters'][0] == {'pid': 104, 'name': 'Dee Moss', 'pos': 'C', 'hand': 'R/R', 'age': 32, 'contact': 20,
                               'power': 20, 'speed': 20, 'fielding': 20}
    assert r['hitters'][5] == {'pid': 101, 'name': 'Ann Hart', 'pos': 'CF', 'hand': 'L/L', 'age': 32, 'contact': 80,
                               'power': 50, 'speed': 80, 'fielding': 20}
    assert r['hitters'][3]['hand'] == '?/R'                  # Cal Ortiz: no bats code
    assert r['hitters'][7]['hand'] == ''                     # Hub Zane: neither side known
    assert r['pitchers'][0] == {'pid': 201, 'name': 'Ivy Cole', 'hand': 'R/L', 'age': 32, 'control': 80,
                                'strikeout': 80, 'stamina': 80, 'fielding': 20}
    assert r['pitchers'][3]['age'] is None                   # Kim Eve: no birth year
    assert 301 not in [row['pid'] for row in r['hitters'] + r['pitchers']]     # Birch's player


def test_team_facts_picks_the_best_hitters_and_pitchers_and_their_last_season():
    f = scout.team_facts(world(), 1, PLAYERS, LAST, 1998)
    assert (f['association'], f['team'], f['manager'], f['stadium'], f['league'], f['division'], f['scale']) == (
        '1998 Major Leagues', 'Ash', 'Mgr', 'Ash Park', 'American League', 'West', scout.SCALE)
    assert hit_names(f['hitters']) == ['Eli Park', 'Ann Hart', 'Gus Vale', 'Bo Lee', 'Cal Ortiz']
    assert hit_names(f['pitchers']) == ['Ivy Cole', 'Mo Gil', 'Jo Dean', 'Kim Eve']
    assert f['hitters'][0] == {'name': 'Eli Park', 'pos': '2B', 'bats': 'switch', 'age': 32, 'contact': 80,
                               'power': 80, 'speed': 80, 'fielding': 20, 'last': {'avg': '.300', 'hr': 30, 'rbi': 100}}
    assert f['hitters'][1]['last'] is None                   # Ann Hart: 99 at-bats, one short of MIN_AB
    assert f['hitters'][3]['last'] == {'avg': '.300', 'hr': 3, 'rbi': 40}     # Bo Lee: exactly MIN_AB
    assert f['hitters'][3]['bats'] == 'right' and f['hitters'][4]['bats'] == ''
    assert f['pitchers'][0] == {'name': 'Ivy Cole', 'throws': 'left', 'age': 32, 'control': 80, 'strikeout': 80,
                                'stamina': 80,
                                'last': {'w': 15, 'l': 5, 'era': '3.02', 'so': 150, 'sv': 0, 'ip': '59.2'}}
    assert f['pitchers'][1]['last'] is None                  # Mo Gil: 59 outs, one short of MIN_OUTS
    assert f['pitchers'][2]['last'] == {'w': 1, 'l': 2, 'era': '4.50', 'so': 5, 'sv': 0, 'ip': '20.0'}   # exactly


def test_team_facts_keeps_every_key_even_when_a_team_has_no_one_to_name():
    empty = world()
    empty['teams'][2]['roster'] = []
    f = scout.team_facts(empty, 2, PLAYERS, LAST, 1998)
    assert f['hitters'] == [] and f['pitchers'] == []
    assert set(f) == {'association', 'team', 'manager', 'stadium', 'league', 'division', 'scale', 'hitters', 'pitchers'}


def test_template_text_names_the_players_and_their_numbers_with_no_pronouns():
    f = scout.team_facts(world(), 1, PLAYERS, LAST, 1998)
    piece = scout.template(f)
    assert piece['headline'] == 'Scouting the Ash'
    hitters, pitchers = piece['body'].split('\n')
    assert hitters.startswith('Eli Park (2B) grades 80 for contact, 80 for power and 80 for speed. Eli Park hit .300 '
                              'with 30 home runs and 100 RBI last season.')
    assert 'Ann Hart (CF) grades 80 for contact, 50 for power and 80 for speed.' in hitters
    assert pitchers.startswith('Ivy Cole grades 80 for control, 80 for strikeout stuff and 80 for stamina. Ivy Cole '
                               'went 15-5 with a 3.02 ERA last season.')
    assert ' He ' not in piece['body'] and not piece['body'].startswith('He ')


def test_template_says_1_home_run_in_the_singular():
    one = dict(LAST['bat'][102], hr=1)
    f = scout.team_facts(world(), 1, PLAYERS, dict(LAST, bat={102: one}), 1998)
    assert '1 home run and 40 RBI' in scout.template(f)['body']


def test_template_passes_numbers_ok_on_each_fixture():
    f = scout.team_facts(world(), 1, PLAYERS, LAST, 1998)
    no_last = scout.team_facts(world(), 1, PLAYERS, {'bat': {}, 'pit': {}}, 1998)
    fixtures = [f, dict(f, hitters=[]), dict(f, pitchers=[]), dict(f, hitters=[], pitchers=[]),
                dict(f, hitters=no_last['hitters'], pitchers=no_last['pitchers']), dict(f, team='Three Rivers')]
    for facts in fixtures:
        piece = scout.template(facts)
        assert recap.numbers_ok(piece['headline'] + '\n' + piece['body'], facts), piece['body']


def test_empty_hitters_and_pitchers_are_said_so_without_numbers():
    f = scout.team_facts(world(), 1, PLAYERS, LAST, 1998)
    piece = scout.template(dict(f, hitters=[], pitchers=[]))
    assert piece['body'] == ('No hitters on the roster of Ash are on file.\n'
                             'No pitchers on the roster of Ash are on file.')


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
    f = scout.team_facts(world(), 1, PLAYERS, LAST, 1998)
    model = Scripted('Ash camp report\n\nEli Park grades 80 for speed.')
    piece = scout.write(f, 'B', model)
    assert (piece['source'], piece['headline']) == ('glm', 'Ash camp report')
    assert model.calls[0][0] == scout.SYSTEM and 'Eli Park' in model.calls[0][1]


def test_write_falls_back_on_a_stray_number_a_budget_error_and_errors():
    f = scout.team_facts(world(), 1, PLAYERS, LAST, 1998)
    wrong = 'Ash camp report\n\nEli Park grades 81 for speed.'
    piece = scout.write(f, 'B', Scripted(wrong, wrong))
    assert (piece['source'], piece['reason']) == ('template', 'numbers')
    spent = scout.write(f, 'B', Scripted(hive.BudgetExceeded('spent')))
    assert (spent['source'], spent['reason']) == ('template', 'budget')
    down = scout.write(f, 'B', Scripted(hive.HiveError('down'), hive.HiveError('down')))
    assert (down['source'], down['reason']) == ('template', 'error')
