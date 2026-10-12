"""The player card page (/news/card/<STEM>/p/<pid>) through modbridge.process_spool: the ratings now and at peak (scout
grades), a pitcher's pitches, the team or off-roster line, the news from a watcher folder, every 404 and traversal refusal,
and the card on the real install when it is present. The synthetic game is stubbed with teams and a season year (as in
test_modbridge_focus); the refusals and ratings checks need no game files. Helpers and fixtures come from test_modbridge.py.
"""
import json
import os
import re
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata    # noqa: E402
import modbridge   # noqa: E402
from tests.test_modbridge import NAMES, ask, bridge, player, pyf_bytes, pyr_bytes, site   # noqa: E402,F401

YEAR = 1977
REAL = '/mnt/nvme/bbpro98/work_install'                 # the game install (read only)
NEWS = '/mnt/nvme/bbpro98/news-data-local'              # the watcher's data folders for that install
STORY = '0123456789abcdef'
OTHER = 'fedcba9876543210'
NO_SUCH = 'No such association or player.'


def card_record(pid, first, last, pos, born, now=None, peak=None, attrs=None):
    """A PYR record with current ratings now (index: value), peak ratings peak and single attributes attrs (offset: value)
    as the rating block's indexes are laid out (modbridge reads them through gamedata.ratings)."""
    rec = bytearray(player(pid, first, last, pos=pos, born=born, cur=now))
    for i, v in (peak or {}).items():
        rec[0x46 + i] = v
    for off, v in (attrs or {}).items():
        rec[off] = v
    return bytes(rec)


# Index 0 is contact, 6 control, 7 the first pitch slot (FB), 18 fielding at 3B (14 + 4). Scout grades: 0 is 20, 50 is 50,
# 66 is 60, 70 is 60, 75 is 65, 80 is 70. Position bytes: 1 P, 5 3B, 6 SS.
RECORDS = [
    card_record(100, 'Pat', 'Doe', 5, 1952, now={0: 66, 18: 50}, peak={0: 80, 18: 60}),          # 3B, on the Reds
    card_record(205, 'Bo', 'Bee', 1, 1948, now={6: 70, 7: 70}, peak={6: 75, 7: 75}, attrs={0x76: 70}),  # P, free agent
    card_record(300, 'Old', 'Timer', 6, 1930),                                                  # SS, retired
]
TEAMS = {1: {'name': 'Reds', 'roster': [100]}}


@pytest.fixture
def card(bridge, site, monkeypatch):
    """(ctx, spool, game): the bridge on the site with TEST77's PYR and PYF, and the association stubbed."""
    ctx, spool = bridge
    game = site[0]
    (game / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes(RECORDS))
    (game / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes([205]))

    def association(path):
        return {'name': NAMES[os.path.basename(path)], 'season_year': YEAR, 'teams': TEAMS, 'games': []}
    monkeypatch.setattr(gamedata, 'association', association)
    return ctx, spool, game


def page(ctx, spool, path):
    return ask(ctx, spool, 'op=news\npath=' + path)


def links_of(head):
    return [tuple(head['link.%d' % i].split('\t')) for i in range(int(head['count']))]


def has_line(body, pattern):
    return re.search(r'^%s$' % pattern, body, re.M) is not None


def test_hitter_card_shows_now_and_peak_grades(card):
    """The positive control: the contact rating of 66 now and 80 at peak reads 60 and 70 on the card. If the rating block
    were not read, the row would be 20 20."""
    ctx, spool, _ = card
    head, body = page(ctx, spool, '/news/card/TEST77/p/100')
    assert head == {'status': 'ok', 'http': '200', 'path': '/news/card/TEST77/p/100', 'title': 'Pat Doe (3B, 25)',
                    'count': '1', 'link.0': 'Player development\t/news/development/TEST77/p/100'}
    assert body.split('\n')[:3] == ['Pat Doe (3B, 25)', '=' * 16, '']
    assert 'Team: Reds' in body.split('\n') and 'Position: 3B' in body.split('\n') and 'Age: 25' in body.split('\n')
    assert has_line(body, r'Contact\s+60\s+70')
    assert has_line(body, r'Power\s+20\s+20')
    assert has_line(body, r'Fielding \(3B\)\s+50\s+55')
    assert 'Fastball' not in body and 'Strikeout' not in body


def test_pitcher_card_shows_his_pitches_and_strikeout_with_no_peak(card):
    ctx, spool, _ = card
    head, body = page(ctx, spool, '/news/card/TEST77/p/205')
    assert head['status'] == 'ok' and head['http'] == '200'
    assert has_line(body, r'Control\s+60\s+65')
    assert has_line(body, r'Fastball\s+60\s+65')
    assert has_line(body, r'Strikeout\s+60\s+-')
    assert 'Curveball' not in body and 'Sinker' not in body and 'Fielding' not in body


def test_team_is_free_agent_or_retired_when_no_roster_holds_him(card):
    ctx, spool, _ = card
    assert 'Team: Free agent' in page(ctx, spool, '/news/card/TEST77/p/205')[1].split('\n')
    assert 'Team: Retired' in page(ctx, spool, '/news/card/TEST77/p/300')[1].split('\n')


def test_a_missing_stats_file_says_so(card):
    ctx, spool, _ = card
    body = page(ctx, spool, '/news/card/TEST77/p/100')[1]
    assert 'No batting or pitching lines in the stats file.' in body.split('\n')
    assert 'Current focus' not in body and 'No focus.' in body.split('\n')


def test_the_card_has_no_news_and_no_association_link_without_a_watcher_folder(card):
    ctx, spool, _ = card
    head, body = page(ctx, spool, '/news/card/TEST77/p/100')
    assert body.split('\n')[-2:] == ['News', 'No news yet.']
    assert links_of(head) == [('Player development', '/news/development/TEST77/p/100')]


def watcher(ctx):
    """The watcher's folder for TEST77: two stories (one names Pat Doe), a move log with his signing, a note for it, a
    notable event without a note, and an event for another player."""
    folder = os.path.join(ctx.data, 'TEST77')
    os.makedirs(os.path.join(folder, 'recaps'))
    os.makedirs(os.path.join(folder, 'moves', 'notes'))
    stories = {STORY: {'headline': 'Pat Doe homers twice', 'body': 'Pat Doe went deep twice for the Reds.',
                       'facts': {'batters': [{'name': 'Pat Doe'}]}, 'month': 4, 'day': 10, 'slot': 1},
               OTHER: {'headline': 'Bo Bee strikes out nine', 'body': 'Bo Bee was dominant.',
                       'facts': {}, 'month': 4, 'day': 11, 'slot': 0}}
    for key, rec in stories.items():
        with open(os.path.join(folder, 'recaps', key + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(rec, fh)
    events = [
        {'kind': 'signed', 'name': 'Pat Doe', 'pid': 100, 'pos': '3B', 'from': 'Free agents', 'to': 'Reds',
         'date': 'April 11', 'year': YEAR, 'note': 0},
        {'kind': 'moved', 'name': 'Bo Bee', 'pid': 205, 'from': 'Free agents', 'to': 'Reds', 'date': 'April 12',
         'year': YEAR},
        {'kind': 'new', 'name': 'Pat Doe', 'pid': 100, 'pos': '3B', 'to': 'Reds', 'date': 'Offseason', 'year': 1976},
    ]
    with open(os.path.join(folder, 'moves', 'log.json'), 'w', encoding='utf-8') as fh:
        json.dump({'events': events, 'count': len(events)}, fh)
    with open(os.path.join(folder, 'moves', 'notes', '0.json'), 'w', encoding='utf-8') as fh:
        json.dump({'kind': 'move', 'event': events[0]}, fh)


def test_news_lists_the_stories_and_moves_that_name_him_newest_first(card):
    ctx, spool, _ = card
    watcher(ctx)
    head, body = page(ctx, spool, '/news/card/TEST77/p/100')
    assert links_of(head) == [
        ('Signed: Pat Doe (3B), Free agents to Reds', '/news/TEST77/moves/0'),
        ('Pat Doe homers twice', '/news/TEST77/' + STORY),
        ('New player: Pat Doe (3B), Reds', '/news/TEST77/moves'),
        ('Player development', '/news/development/TEST77/p/100'),
        ('Association news', '/news/TEST77/'),
    ]
    lines = body.split('\n')
    assert lines[-4:] == ['News', '- Signed: Pat Doe (3B), Free agents to Reds', '- Pat Doe homers twice',
                          '- New player: Pat Doe (3B), Reds']


def test_each_card_lists_only_the_news_that_names_its_player(card):
    """Bo Bee has his move and his story; Pat Doe's signing is not his. Old Timer is named in nothing."""
    ctx, spool, _ = card
    watcher(ctx)
    head, body = page(ctx, spool, '/news/card/TEST77/p/205')
    assert links_of(head) == [
        ('Moved: Bo Bee, Free agents to Reds', '/news/TEST77/moves'),
        ('Bo Bee strikes out nine', '/news/TEST77/' + OTHER),
        ('Player development', '/news/development/TEST77/p/205'),
        ('Association news', '/news/TEST77/'),
    ]
    head, body = page(ctx, spool, '/news/card/TEST77/p/300')
    assert body.split('\n')[-2:] == ['News', 'No news yet.']
    assert [label for label, _ in links_of(head)] == ['Player development', 'Association news']


@pytest.mark.parametrize('path, text', [
    ('/news/card/NOPE/p/100', NO_SUCH),                    # no association with that STEM
    ('/news/card/TEST77/p/777', NO_SUCH),                  # no player 777 in the PYR
    ('/news/card/TEST77/p/0', NO_SUCH),
    ('/news/card/TEST77/p/100000', 'Not found.'),          # six digits: outside the pattern
    ('/news/card/TEST77/p/-1', 'Not found.'),
    ('/news/card/TEST77/p/1e2', 'Not found.'),
    ('/news/card/TEST77/p/abc', 'Not found.'),
    ('/news/card/TEST77/p/100/', 'Not found.'),
    ('/news/card/TEST77/p/100/x', 'Not found.'),
    ('/news/card', 'Not found.'),
    ('/news/card/', 'Not found.'),
    ('/news/card/TEST77', 'Not found.'),
    ('/news/card//p/100', 'Not found.'),
    ('/news/card/../x', 'Not found.'),                     # traversal, plain and encoded
    ('/news/card/../../etc/p/100', 'Not found.'),
    ('/news/card/%2e%2e/p/100', 'Not found.'),
    ('/news/card/%2E%2E%2Fx/p/100', 'Not found.'),
    ('/news/card/TEST77/../p/100', 'Not found.'),
    ('/news/card/TEST77/p/100/../x', 'Not found.'),
    ('/news/card//etc/passwd', 'Not found.'),              # an absolute path in the stem slot
    ('/news/card/TEST77/%2e%2e/p/100', 'Not found.'),
])
def test_card_refuses_unknown_and_malformed_paths_with_a_404(card, path, text):
    ctx, spool, _ = card
    head, body = page(ctx, spool, path)
    assert head == {'status': 'error', 'http': '404', 'path': path, 'title': 'Not found', 'count': '0'}
    assert body == text and 'Traceback' not in body


def test_card_stem_is_matched_without_case_and_the_query_is_ignored(card):
    ctx, spool, _ = card
    assert page(ctx, spool, '/news/card/test77/p/100')[0]['status'] == 'ok'
    head, body = page(ctx, spool, '/news/card/TEST77/p/100?x=1')
    assert head['http'] == '200' and 'Team: Reds' in body.split('\n')


def test_card_is_not_routed_to_the_news_server(card, monkeypatch):
    ctx, spool, _ = card
    seen = []
    monkeypatch.setattr(modbridge.server, 'route', lambda data, path: seen.append(path) or (404, 'text/html', b'', ()))
    page(ctx, spool, '/news/card/TEST77/p/100')
    assert seen == []


def real_ctx(tmp_path, data):
    spool = tmp_path / 'spool'
    spool.mkdir()
    ctx = types.SimpleNamespace(game=REAL, data=data, backup=str(tmp_path / 'backup'), donor='', db=None,
                                templates=None, proc=str(tmp_path / 'proc'))
    return ctx, str(spool)


@pytest.mark.skipif(not os.path.isfile(os.path.join(REAL, 'Assn', 'MLBPA97.ASN')), reason='no game install here')
def test_card_on_the_real_install(tmp_path):
    """Chipper Jones in MLBPA97: his 3B ratings are read from the PYR, his career games by position from the stats file,
    and his team from the roster window."""
    ctx, spool = real_ctx(tmp_path, str(tmp_path / 'data'))
    os.makedirs(ctx.data)
    head, body = page(ctx, spool, '/news/card/MLBPA97/p/104')
    assert head['status'] == 'ok' and head['http'] == '200'
    lines = body.split('\n')
    assert lines[0] == 'Chipper Jones (3B, 35)'
    assert 'Team: Atlanta' in lines and 'Position: 3B' in lines
    assert has_line(body, r'Contact\s+60\s+60') and has_line(body, r'Power\s+80\s+80')
    assert has_line(body, r'Career\s+1570\s+6025\s+956\s+2001.*')
    assert 'Career games by position: 2B 9, 3B 1530, SS 1, CF 2, RF 1' in lines
    assert 'No news yet.' in lines


@pytest.mark.skipif(not os.path.isdir(os.path.join(NEWS, 'MLBPA97')), reason='no watcher data here')
def test_card_on_the_real_install_with_the_watcher_folder_but_no_stories(tmp_path):
    ctx, spool = real_ctx(tmp_path, NEWS)
    head, body = page(ctx, spool, '/news/card/MLBPA97/p/99999')
    assert head['http'] == '404' and body == NO_SUCH
    head, body = page(ctx, spool, '/news/card/MLBPA97/p/104')
    assert head['status'] == 'ok'
    assert ('Association news', '/news/MLBPA97/') in links_of(head)
    assert 'No news yet.' in body.split('\n')
