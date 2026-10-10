"""The player development pages and the focus file, through modbridge.process_spool: every route and every 404, set,
clear and the FocusFull 409, the Player development link on an association page, a focus.txt that is a symlink or not
a regular file, a game with no Mods directory, and the read limit. The association is stubbed with teams, rosters and
a season year (gamedata.association has no teams in test_modbridge's site fixture). Helpers and fixtures come from
test_modbridge.py.
"""
import datetime
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import focus       # noqa: E402
import gamedata    # noqa: E402
import modbridge   # noqa: E402
from tests.test_modbridge import NAMES, ask, bridge, player, pyr_bytes, serve_pages, site   # noqa: E402,F401

YEAR = 1977
RECORDS = [
    player(100, 'Pat', 'Doe', pos=4, born=1952),       # 2B
    player(120, 'Al', 'Ames', pos=7, born=1950),       # LF
    player(205, 'Bo', 'Bee', pos=1, born=1948),        # P
    player(310, 'Cy', 'Young', pos=1, born=1955),      # P, on the Cubs
    player(400, 'Fr', 'Ee', pos=3, born=1958),         # 1B, on no roster
]
TEAMS = {1: {'name': 'Reds', 'roster': [100, 120, 205, 999]},     # 999 has no record in the PYR
         2: {'name': 'Cubs', 'roster': [310]}}
BASE = '/news/development/TEST77'
NOT_FOUND = [
    '/news/development/NOPE/',                      # no association with that STEM
    '/news/development/NOPE/team/1',
    '/news/development/NOPE/p/100',
    '/news/development/TEST77/team/9',              # a tid the association does not have
    '/news/development/TEST77/team/100',            # not a tid: three digits
    '/news/development/TEST77/p/777',               # no player 777 in the PYR
    '/news/development/TEST77/p/777/set/power',
    '/news/development/TEST77/p/777/clear',
    '/news/development/TEST77/p/205/set/contact',   # a pitcher is focused on control, stuff or defense
    '/news/development/TEST77/p/100/set/control',   # a hitter is focused on contact, power, speed or defense
    '/news/development/TEST77/p/100/set/Power',     # kinds are lowercase
    '/news/development/TEST77/p/100/set/nope',
    '/news/development/TEST77/p/100/set/',
    '/news/development/TEST77/p/100/clear/',
    '/news/development/TEST77/p/abc',
    '/news/development/TEST77/moves',
    '/news/development/TEST77/team/1/',
    '/news/development/TEST77/?x=1',
    '/news/development/',
    '/news/development',
]


def serial(year):
    return datetime.date(year, 7, 1).toordinal() + 365


def ent(pid, birth, kind, assn='TEST77'):
    return {'pid': pid, 'birth': birth, 'kind': kind, 'assn': assn}


def stub_league(monkeypatch, year=YEAR):
    def association(path):
        return {'name': NAMES[os.path.basename(path)], 'season_year': year, 'teams': TEAMS, 'games': []}
    monkeypatch.setattr(gamedata, 'association', association)


@pytest.fixture
def dev(bridge, site, monkeypatch):
    """(ctx, spool, game): the bridge on the site, with TEST77's PYR and the association stubbed."""
    ctx, spool = bridge
    game = site[0]
    (game / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes(RECORDS))
    stub_league(monkeypatch)
    return ctx, spool, game


def page(ctx, spool, path):
    return ask(ctx, spool, 'op=news\npath=' + path)


def links_of(head):
    return [tuple(head['link.%d' % i].split('\t')) for i in range(int(head['count']))]


def focus_file(game):
    return game / 'Mods' / 'focus.txt'


def write_focus(game, text):
    (game / 'Mods').mkdir(exist_ok=True)
    focus_file(game).write_text(text)


def entries_of(game):
    return focus.parse(focus_file(game).read_text())


# the association page

def test_association_page_lists_the_teams_with_no_focus(dev):
    ctx, spool, _ = dev
    head, body = page(ctx, spool, BASE + '/')
    assert head == {'status': 'ok', 'http': '200', 'path': BASE + '/',
                    'title': 'Player development: 1977 Major Leagues', 'count': '2',
                    'link.0': 'Reds\t' + BASE + '/team/1', 'link.1': 'Cubs\t' + BASE + '/team/2'}
    assert body.split('\n')[0] == 'Players with a focus (0 of 5):'


def test_association_page_names_each_focused_player_in_file_order(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(205, serial(1948), 'stuff'), ent(100, serial(1952), 'contact'),
                                    ent(777, 1, 'power', 'ODD78'), ent(120, serial(1950), 'speed', 'ODD78')]))
    head, body = page(ctx, spool, BASE + '/')
    assert '(2 of 5)' in body and 'Bo Bee: stuff' in body.split('\n') and 'Pat Doe: contact' in body.split('\n')
    assert links_of(head) == [('Bo Bee: stuff', BASE + '/p/205'), ('Pat Doe: contact', BASE + '/p/100'),
                              ('Reds', BASE + '/team/1'), ('Cubs', BASE + '/team/2')]


# the team page

def test_team_page_lists_hitters_then_pitchers_by_name_with_ages_and_focus(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(205, serial(1948), 'control')]))
    head, _ = page(ctx, spool, BASE + '/team/1')
    assert head['title'] == 'Reds: development'
    assert links_of(head) == [('Al Ames (LF, 27)', BASE + '/p/120'), ('Pat Doe (2B, 25)', BASE + '/p/100'),
                              ('Bo Bee (P, 29): control', BASE + '/p/205'), ('All teams', BASE + '/')]


def test_team_page_leaves_out_the_age_when_the_season_year_is_unknown(dev, monkeypatch):
    ctx, spool, _ = dev
    stub_league(monkeypatch, year=None)
    head, _ = page(ctx, spool, BASE + '/team/2')
    assert links_of(head) == [('Cy Young (P)', BASE + '/p/310'), ('All teams', BASE + '/')]


# the player page

def test_player_page_for_a_hitter_with_no_focus(dev):
    ctx, spool, _ = dev
    head, body = page(ctx, spool, BASE + '/p/100')
    assert head['status'] == 'ok' and head['http'] == '200' and head['title'] == 'Pat Doe (2B, 25)'
    assert body.split('\n') == ['No focus.', 'Team: Reds']
    assert links_of(head) == [('Focus on contact', BASE + '/p/100/set/contact'),
                              ('Focus on power', BASE + '/p/100/set/power'),
                              ('Focus on speed', BASE + '/p/100/set/speed'),
                              ('Focus on defense', BASE + '/p/100/set/defense'),
                              ('Back to Reds', BASE + '/team/1'), ('All teams', BASE + '/')]


def test_player_page_for_a_pitcher_with_a_focus(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(205, serial(1948), 'stuff')]))
    head, body = page(ctx, spool, BASE + '/p/205')
    assert head['title'] == 'Bo Bee (P, 29)'
    assert body.split('\n') == ['Current focus: stuff', 'Team: Reds']
    assert links_of(head) == [('Focus on control', BASE + '/p/205/set/control'),
                              ('Focus on stuff', BASE + '/p/205/set/stuff'),
                              ('Focus on defense', BASE + '/p/205/set/defense'),
                              ('Clear focus', BASE + '/p/205/clear'),
                              ('Back to Reds', BASE + '/team/1'), ('All teams', BASE + '/')]


def test_a_player_on_no_roster_is_a_free_agent(dev):
    ctx, spool, _ = dev
    head, body = page(ctx, spool, BASE + '/p/400')
    assert head['title'] == 'Fr Ee (1B, 19)'
    assert body.split('\n') == ['No focus.', 'Free agent']
    labels = [label for label, _ in links_of(head)]
    assert not any(label.startswith('Back to') for label in labels)
    assert labels[-1] == 'All teams'


# set and clear

def test_set_writes_the_focus_file_and_shows_the_player(dev):
    ctx, spool, game = dev
    head, body = page(ctx, spool, BASE + '/p/100/set/power')
    assert head['status'] == 'ok' and head['http'] == '200' and head['path'] == BASE + '/p/100'
    assert body.split('\n') == ['Focus set: power.', '', 'Current focus: power', 'Team: Reds']
    assert ('Clear focus', BASE + '/p/100/clear') in links_of(head)
    assert focus_file(game).read_text() == focus.format([ent(100, serial(1952), 'power')])
    assert sorted(os.listdir(game / 'Mods')) == ['focus.txt', 'spool']


def test_a_second_set_changes_the_kind_in_place(dev):
    ctx, spool, game = dev
    page(ctx, spool, BASE + '/p/205/set/stuff')
    page(ctx, spool, BASE + '/p/100/set/contact')
    page(ctx, spool, BASE + '/p/100/set/speed')
    assert entries_of(game) == [ent(205, serial(1948), 'stuff'), ent(100, serial(1952), 'speed')]


def test_clear_removes_the_focus_and_shows_the_player(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(100, serial(1952), 'power'), ent(205, serial(1948), 'stuff')]))
    head, body = page(ctx, spool, BASE + '/p/100/clear')
    assert head['status'] == 'ok' and head['http'] == '200'
    assert body.split('\n') == ['Focus cleared.', '', 'No focus.', 'Team: Reds']
    assert 'Clear focus' not in [label for label, _ in links_of(head)]
    assert entries_of(game) == [ent(205, serial(1948), 'stuff')]


def test_a_sixth_focus_in_the_association_is_refused_and_the_file_is_unchanged(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(500 + i, 1, 'power') for i in range(focus.MAX_PER_ASSN)]))
    before = focus_file(game).read_bytes()
    head, body = page(ctx, spool, BASE + '/p/100/set/power')
    assert head['status'] == 'error' and head['http'] == '409' and head['title'] == 'Pat Doe (2B, 25)'
    assert body.split('\n')[0] == '5 players in this association already have a focus. Clear one first.'
    assert focus_file(game).read_bytes() == before
    assert ('Focus on power', BASE + '/p/100/set/power') in links_of(head)
    assert ('All teams', BASE + '/') in links_of(head)


def test_focus_in_another_association_does_not_count_toward_this_one(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(500 + i, 1, 'power', 'ODD78') for i in range(focus.MAX_PER_ASSN)]))
    head, _ = page(ctx, spool, BASE + '/p/100/set/power')
    assert head['status'] == 'ok' and len(entries_of(game)) == focus.MAX_PER_ASSN + 1


def test_changing_the_focus_of_one_of_five_is_allowed_at_five(dev):
    ctx, spool, game = dev
    write_focus(game, focus.format([ent(100, serial(1952), 'contact')] + [ent(500 + i, 1, 'power') for i in range(4)]))
    head, _ = page(ctx, spool, BASE + '/p/100/set/power')
    assert head['status'] == 'ok' and entries_of(game)[0] == ent(100, serial(1952), 'power')


# every 404

@pytest.mark.parametrize('path', NOT_FOUND)
def test_every_404_is_plain_not_found_and_writes_nothing(dev, monkeypatch, path):
    ctx, spool, game = dev
    seen = serve_pages(monkeypatch, {})
    head, body = page(ctx, spool, path)
    assert head == {'status': 'error', 'http': '404', 'path': path, 'title': 'Not found', 'count': '0'}
    assert body == 'Not found.'
    assert seen == [] and not focus_file(game).exists()


# the focus file

def test_a_symlinked_focus_file_reads_as_none_and_is_never_written_through(dev, tmp_path):
    ctx, spool, game = dev
    victim = tmp_path / 'victim.txt'
    victim.write_text(focus.format([ent(205, serial(1948), 'stuff')]))
    before = victim.read_bytes()
    (game / 'Mods').mkdir(exist_ok=True)
    os.symlink(victim, focus_file(game))
    _, body = page(ctx, spool, BASE + '/')
    assert body.split('\n')[0] == 'Players with a focus (0 of 5):'
    head, _ = page(ctx, spool, BASE + '/p/100/set/power')
    assert head['status'] == 'ok'
    assert victim.read_bytes() == before
    assert focus_file(game).is_file() and not focus_file(game).is_symlink()
    assert entries_of(game) == [ent(100, serial(1952), 'power')]


def test_a_symlinked_mods_dir_reads_as_none_and_a_set_fails_closed(dev, tmp_path):
    ctx, spool, game = dev
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'focus.txt').write_text(focus.format([ent(100, serial(1952), 'power', 'MLBPA97')]))
    before = (elsewhere / 'focus.txt').read_bytes()
    mods = game / 'Mods'
    if mods.exists():
        mods.rename(game / 'Mods.real')     # the spool is held by descriptor, so it survives the rename
    os.symlink(elsewhere, mods)
    assert modbridge._read_focus(str(game)) == []
    head, _ = modbridge.handle(ctx, {'op': 'news', 'path': BASE + '/p/100/set/power'})
    assert dict(head)['status'] == 'error'
    assert (elsewhere / 'focus.txt').read_bytes() == before and sorted(os.listdir(elsewhere)) == ['focus.txt']


def test_a_focus_file_that_is_not_a_regular_file_reads_as_none(dev):
    ctx, spool, game = dev
    (game / 'Mods' / 'focus.txt').mkdir()
    _, body = page(ctx, spool, BASE + '/')
    assert body.split('\n')[0] == 'Players with a focus (0 of 5):'


def test_read_takes_at_most_max_file_bytes(dev):
    ctx, spool, game = dev
    write_focus(game, '100 %d power\n' % serial(1952) + '#' * focus.MAX_FILE)
    assert modbridge._read_focus(str(game)) == [ent(100, serial(1952), 'power', None)]
    write_focus(game, '#' * focus.MAX_FILE + '\n100 %d power\n' % serial(1952))
    assert modbridge._read_focus(str(game)) == []


def test_a_game_with_no_mods_directory_reads_as_no_focus_and_a_set_makes_it(site, tmp_path, monkeypatch):
    game, data = site[0], site[1]
    (game / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes(RECORDS))
    stub_league(monkeypatch)
    spool = tmp_path / 'spool'
    spool.mkdir()
    ctx = types.SimpleNamespace(game=str(game), data=str(data))
    assert not (game / 'Mods').exists()
    _, body = page(ctx, str(spool), BASE + '/')
    assert body.split('\n')[0] == 'Players with a focus (0 of 5):'
    assert not (game / 'Mods').exists()
    head, _ = page(ctx, str(spool), BASE + '/p/100/set/power')
    assert head['status'] == 'ok'
    assert (game / 'Mods').is_dir() and focus_file(game).is_file()
    assert entries_of(game) == [ent(100, serial(1952), 'power')]


# the Player development link on an association's news page

def test_an_association_news_page_gets_a_player_development_link(bridge, monkeypatch):
    ctx, spool = bridge
    html = b'<title>1977 Major Leagues</title><p>See <a href="/news/x/">the opener</a>.</p>'
    serve_pages(monkeypatch, {'/news/TEST77/': (200, html, ())})
    head, _ = page(ctx, spool, '/news/TEST77/')
    assert head['status'] == 'ok' and head['count'] == '2'
    assert links_of(head) == [('the opener', '/news/x/'), ('Player development', BASE + '/')]


def test_a_redirected_association_page_links_to_its_stem_in_capitals(bridge, monkeypatch):
    ctx, spool = bridge
    serve_pages(monkeypatch, {'/news/test77': (301, b'', (('Location', '/news/test77/'),)),
                              '/news/test77/': (200, b'<title>1977</title><p>hi</p>', ())})
    head, _ = page(ctx, spool, '/news/test77')
    assert head['path'] == '/news/test77/' and links_of(head) == [('Player development', BASE + '/')]


@pytest.mark.parametrize('path, status', [('/news/', 200), ('/news/TEST77/moves', 200), ('/news/NOPE/', 200),
                                          ('/news/TEST77/', 404)])
def test_only_an_ok_association_page_gets_the_link(bridge, monkeypatch, path, status):
    ctx, spool = bridge
    serve_pages(monkeypatch, {path: (status, b'<title>x</title><p>y</p>', ())})
    head, _ = page(ctx, spool, path)
    assert head['count'] == '0'
