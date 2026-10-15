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


def real_ctx(tmp_path, data, monkeypatch):
    """A bridge on the real install that answers with the text card (the install has fonts; test_modbridge_cardimg
    covers the picture)."""
    monkeypatch.setattr(modbridge, '_card_fonts', lambda game: None)
    spool = tmp_path / 'spool'
    spool.mkdir()
    ctx = types.SimpleNamespace(game=REAL, data=data, backup=str(tmp_path / 'backup'), donor='', db=None,
                                templates=None, proc=str(tmp_path / 'proc'))
    return ctx, str(spool)


@pytest.mark.skipif(not os.path.isfile(os.path.join(REAL, 'Assn', 'MLBPA97.ASN')), reason='no game install here')
def test_card_on_the_real_install(tmp_path, monkeypatch):
    """Chipper Jones in MLBPA97: his 3B ratings are read from the PYR, his career games by position from the stats file,
    and his team from the roster window."""
    ctx, spool = real_ctx(tmp_path, str(tmp_path / 'data'), monkeypatch)
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


def past_season(folder, d, year, stories, meta=True):
    """A past/<D> archived season under the watcher folder: meta.json with season_year year (or no meta.json when meta
    is False) and stories as {key: record}."""
    rdir = os.path.join(folder, 'past', d, 'recaps')
    os.makedirs(rdir)
    if meta:
        with open(os.path.join(folder, 'past', d, 'meta.json'), 'w', encoding='utf-8') as fh:
            json.dump({'season_year': year}, fh)
    for key, rec in stories.items():
        with open(os.path.join(rdir, key + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(rec, fh)


def test_past_season_story_lists_below_the_current_one_under_its_own_path(card):
    """A story in past/1976/recaps shows with the /past/1976 link, sorted below this season's story."""
    ctx, spool, _ = card
    folder = os.path.join(ctx.data, 'TEST77')
    watcher(ctx)
    past_season(folder, '1976', 1976, {'1234567890abcdef': {'headline': 'Pat Doe wins the pennant',
                                                            'body': 'Pat Doe carried the Reds to October.',
                                                            'month': 9, 'day': 28, 'slot': 1}})
    head, _ = page(ctx, spool, '/news/card/TEST77/p/100')
    assert ('Pat Doe homers twice', '/news/TEST77/' + STORY) in links_of(head)
    assert ('Pat Doe wins the pennant', '/news/TEST77/past/1976/1234567890abcdef') in links_of(head)
    assert links_of(head).index(('Pat Doe homers twice', '/news/TEST77/' + STORY)) < \
        links_of(head).index(('Pat Doe wins the pennant', '/news/TEST77/past/1976/1234567890abcdef'))


def test_past_folders_order_newest_season_first_and_meta_beats_the_folder_name(card):
    """past/1976-2 (meta season_year 1976) sorts with the 1976 stories and below past/1977's, whose story sorts with
    the current season's by its month and day (an archived season shares the association's year)."""
    ctx, spool, _ = card
    folder = os.path.join(ctx.data, 'TEST77')
    watcher(ctx)
    past_season(folder, '1977', 1977, {'aaaaaaaaaaaaaaaa': {'headline': 'Pat Doe wins the MVP',
                                                            'body': 'Pat Doe led the league.', 'month': 5, 'day': 2,
                                                            'slot': 0}})
    past_season(folder, '1976', 1976, {'1234567890abcdef': {'headline': 'Pat Doe wins the pennant',
                                                            'body': 'Pat Doe carried the Reds.', 'month': 9, 'day': 28,
                                                            'slot': 1}})
    past_season(folder, '1976-2', 1976, {'bbbbbbbbbbbbbbbb': {'headline': 'Pat Doe re-signs',
                                                             'body': 'Pat Doe stays with the Reds.', 'month': 10,
                                                             'day': 5, 'slot': 0}})
    head, _ = page(ctx, spool, '/news/card/TEST77/p/100')
    order = [path for _, path in links_of(head)]
    assert order.index('/news/TEST77/past/1977/aaaaaaaaaaaaaaaa') < \
        min(order.index('/news/TEST77/past/1976/1234567890abcdef'),
            order.index('/news/TEST77/past/1976-2/bbbbbbbbbbbbbbbb'))
    assert abs(order.index('/news/TEST77/past/1976/1234567890abcdef') -
               order.index('/news/TEST77/past/1976-2/bbbbbbbbbbbbbbbb')) == 1


def test_past_folders_that_do_not_match_the_archive_pattern_are_ignored(card):
    ctx, spool, _ = card
    folder = os.path.join(ctx.data, 'TEST77')
    watcher(ctx)
    past_season(folder, '97', 1976, {'1234567890abcdef': {'headline': 'Pat Doe wins', 'body': 'Pat Doe.',
                                                          'month': 4, 'day': 1, 'slot': 0}})
    past_season(folder, '1976-123', 1976, {'234567890abcdef1': {'headline': 'Pat Doe wins again',
                                                                'body': 'Pat Doe again.', 'month': 4, 'day': 2,
                                                                'slot': 0}})
    os.makedirs(os.path.join(folder, 'past', '../x', 'recaps'), exist_ok=True)
    with open(os.path.join(folder, 'past', '../x', 'recaps', STORY + '.json'), 'w', encoding='utf-8') as fh:
        json.dump({'headline': 'Pat Doe escapes', 'body': 'Pat Doe outside past/', 'month': 4, 'day': 3,
                   'slot': 0}, fh)
    head, _ = page(ctx, spool, '/news/card/TEST77/p/100')
    labels = [label for label, _ in links_of(head)]
    assert 'Pat Doe wins' not in labels and 'Pat Doe wins again' not in labels
    assert 'Pat Doe escapes' not in labels and 'Pat Doe homers twice' in labels


def test_an_unreadable_past_meta_falls_back_to_the_year_in_the_folder_name(card):
    """The invalid meta.json is skipped silently and past/1976 still sorts by its folder year."""
    ctx, spool, _ = card
    folder = os.path.join(ctx.data, 'TEST77')
    watcher(ctx)
    past_season(folder, '1976', 1976, {'34567890abcdef12': {'headline': 'Pat Doe wins the award',
                                                            'body': 'Pat Doe is named best player.', 'month': 8,
                                                            'day': 20, 'slot': 0}}, meta=False)
    with open(os.path.join(folder, 'past', '1976', 'meta.json'), 'w', encoding='utf-8') as fh:
        fh.write('{not json')
    head, _ = page(ctx, spool, '/news/card/TEST77/p/100')
    assert ('Pat Doe wins the award', '/news/TEST77/past/1976/34567890abcdef12') in links_of(head)
    order = [path for _, path in links_of(head)]
    assert order.index('/news/TEST77/' + STORY) < order.index('/news/TEST77/past/1976/34567890abcdef12')


def test_the_scan_cap_spent_on_the_current_season_leaves_nothing_for_the_past(card, monkeypatch):
    """With a lowered CARD_SCAN, story files read in total never exceed it: the current season's are read first."""
    ctx, spool, _ = card
    folder = os.path.join(ctx.data, 'TEST77')
    watcher(ctx)
    past_season(folder, '1976', 1976, {'aaaaaaaaaaaaaaaa': {'headline': 'Pat Doe wins the MVP',
                                                            'body': 'Pat Doe led the league.', 'month': 5, 'day': 2,
                                                            'slot': 0}})
    read = []
    real = modbridge.server._read_obj

    def spy(path):
        read.append(path)
        return real(path)
    monkeypatch.setattr(modbridge.server, '_read_obj', spy)
    monkeypatch.setattr(modbridge, 'CARD_SCAN', 2)
    head, _ = page(ctx, spool, '/news/card/TEST77/p/100')
    story_reads = [p for p in read if '/recaps/' in p]
    assert len(story_reads) <= 2
    assert os.path.join(folder, 'recaps', STORY + '.json') in story_reads
    assert os.path.join(folder, 'recaps', OTHER + '.json') in story_reads
    assert not any(p.startswith(os.path.join(folder, 'past')) for p in story_reads)


@pytest.mark.skipif(not os.path.isdir(os.path.join(NEWS, 'MLBPA97')), reason='no watcher data here')
def test_card_on_the_real_install_with_the_watcher_folder_but_no_stories(tmp_path, monkeypatch):
    ctx, spool = real_ctx(tmp_path, NEWS, monkeypatch)
    head, body = page(ctx, spool, '/news/card/MLBPA97/p/99999')
    assert head['http'] == '404' and body == NO_SUCH
    head, body = page(ctx, spool, '/news/card/MLBPA97/p/104')
    assert head['status'] == 'ok'
    assert ('Association news', '/news/MLBPA97/') in links_of(head)
    assert 'No news yet.' in body.split('\n')
