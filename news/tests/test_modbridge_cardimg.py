"""The player card as a picture page (/news/card/<STEM>/p/<pid>[/<tab>[/<page>]]) through modbridge.process_spool: the
reply's image=1 header and hot.N click regions, the r<ID>.bmp written before the .rsp, the Career tab's real Lahman
seasons, archived sim seasons and paging, the text fallback when the game has no fonts, housekeeping of stale pictures,
and the watcher's season archive (watch.history_piece). Fonts and the palette are synthetic, written into the test
game folder; the Lahman database is a tiny one built here. cardimg.render is wrapped to capture the card dict it is given.
"""
import os
import sqlite3
import struct
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cardimg     # noqa: E402
import gamedata    # noqa: E402
import history     # noqa: E402
import modbridge   # noqa: E402
import season      # noqa: E402
import watch       # noqa: E402
from tests.test_modbridge import NAMES, ask, bridge, pyf_bytes, pyr_bytes, site   # noqa: E402,F401
from tests.test_modbridge_card import REAL, RECORDS, TEAMS, YEAR, card_record, page   # noqa: E402

BASE = '/news/card/TEST77/p/100'


def fnx(ver, height, width, count=96):
    """A synthetic FNX font: every glyph but the space is a block of ink (ver 1) or palette index 0xCE (ver 3)."""
    stride = (width + 7) // 8 if ver == 1 else width
    ink = bytes([0xF0] * stride) if ver == 1 else bytes([0xCE] * width)
    glyphs = [bytes(stride * height) if i == 0 else ink * min(7, height) + bytes(stride * (height - min(7, height)))
              for i in range(count)]
    tstart = 17
    wstart = tstart + 2 * count
    dstart = wstart + count
    head = b'FNX:' + struct.pack('<HBBBBBHHH', ver, width, height, height - 2, 0x20, count, tstart, wstart, dstart)
    offsets = struct.pack('<%dH' % count, *[i * len(glyphs[0]) for i in range(count)])
    return head + offsets + bytes([width] * count) + b''.join(glyphs)


def pal():
    entries = b''.join(bytes([i, 255 - i, i // 2, 0]) for i in range(256))
    return b'RIFF' + struct.pack('<I', 4 + 12 + 4 + 1024) + b'PAL data' + struct.pack('<IHH', 4 + 1024, 0x300, 256) + entries


def lahman(path, seasons):
    """A Lahman database with Pat Doe (born 1952-07-01) batting in each year of seasons, for team CIN (teamIDBR CIN)."""
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE people(playerID TEXT, nameFirst TEXT, nameLast TEXT, birthYear INT, birthMonth INT, birthDay INT);
        CREATE TABLE teams(yearID INT, teamID TEXT, teamIDBR TEXT);
        CREATE TABLE batting(playerID, yearID, stint, teamID, G, AB, R, H, "2B", "3B", HR, RBI, SB, CS, BB, SO, IBB,
                             HBP, SH, SF, GIDP);
        CREATE TABLE pitching(playerID, yearID, stint, teamID, W, L, G, GS, CG, SHO, SV, IPouts, H, ER, HR, BB, SO, HBP,
                              BFP, R);''')
    conn.execute("INSERT INTO people VALUES ('doepa01', 'Pat', 'Doe', 1952, 7, 1)")
    for y in seasons:
        conn.execute("INSERT INTO teams VALUES (?, 'CIN', 'CIN')", (y,))
        conn.execute("INSERT INTO batting VALUES ('doepa01', ?, 1, 'CIN', 150, 500, 70, 140, 25, 3, ?, 80, 5, 2, 60, 90,"
                     " 0, 2, 1, 4, 10)", (y, y % 40))
    conn.commit()
    conn.close()


@pytest.fixture
def pic(bridge, site, monkeypatch, tmp_path):
    """(ctx, spool, cards): the bridge on TEST77 (as test_modbridge_card) with fonts and a palette in the game folder,
    and the list of card dicts cardimg.render has been given."""
    ctx, spool = bridge
    game = site[0]
    (game / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes(RECORDS))
    (game / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes([205]))
    (game / '4.FNX').write_bytes(fnx(1, 11, 6))
    (game / '5.fnx').write_bytes(fnx(3, 20, 10, 95))
    (game / 'bb0.pal').write_bytes(pal())
    monkeypatch.setattr(gamedata, 'association',
                        lambda path: {'name': NAMES[os.path.basename(path)], 'season_year': YEAR, 'teams': TEAMS,
                                      'games': []})
    monkeypatch.setattr(modbridge, '_FONTS', {})
    ctx.db = str(tmp_path / 'none.sqlite')
    monkeypatch.setattr(history, 'DEFAULT_DB', str(tmp_path / 'absent.sqlite'))
    monkeypatch.delenv('BBPRO98_LAHMAN', raising=False)
    cards = []
    real = cardimg.render

    def spy(card, fonts):
        cards.append(card)
        return real(card, fonts)
    monkeypatch.setattr(cardimg, 'render', spy)
    return ctx, spool, cards


def hots(head):
    return [(tuple(int(v) for v in h.split('\t')[0].split(',')), h.split('\t')[1])
            for h in (head['hot.%d' % i] for i in range(int(head['hots'])))]


def bmp_of(spool):
    names = [n for n in os.listdir(spool) if n.endswith('.bmp')]
    assert len(names) == 1
    with open(os.path.join(spool, names[0]), 'rb') as fh:
        return fh.read()


def test_overview_is_a_picture_page_with_tab_and_link_hotspots(pic):
    ctx, spool, cards = pic
    head, body = page(ctx, spool, BASE)
    assert head['status'] == 'ok' and head['http'] == '200' and head['image'] == '1'
    data = bmp_of(spool)
    assert data[:2] == b'BM' and struct.unpack_from('<ii', data, 18) == (680, 450)
    assert struct.unpack_from('<I', data, 2)[0] == len(data)
    targets = [t for _, t in hots(head)]
    assert targets[:4] == [BASE + '/batting', BASE + '/pitching', BASE + '/career', BASE + '/news']
    assert '/news/development/TEST77/p/100' in targets
    for (x, y, w, h), _ in hots(head):
        assert 0 <= x and 0 <= y and x + w <= 680 and y + h <= 450 and w > 0 and h > 0
    card = cards[-1]
    assert card['title'] == 'Pat Doe' and card['body']['kind'] == 'overview'
    assert [sel for _, _, sel in card['tabs']] == [True, False, False, False, False]
    w, h, rgb = card['body']['portrait']
    assert (w, h, len(rgb)) == (120, 150, 120 * 150 * 3)
    assert ('Contact', 60, 70) in card['body']['ratings']
    assert 'Reds' in card['header'][0] and 'Born Jul 1, 1952' in card['header'][1]
    assert 'This card is a picture page.' in body          # a reader without pictures still gets a page


def test_the_picture_is_written_before_the_reply_that_names_it(pic, monkeypatch):
    ctx, spool, _ = pic
    order = []
    real = modbridge._put

    def put(dfd, rid, data, ext):
        order.append(ext)
        return real(dfd, rid, data, ext)
    monkeypatch.setattr(modbridge, '_put', put)
    page(ctx, spool, BASE + '/batting')
    assert order == ['bmp', 'rsp']


def test_the_portrait_is_the_same_every_time_and_differs_between_players(pic):
    ctx, spool, cards = pic
    page(ctx, spool, BASE)
    page(ctx, spool, BASE)
    page(ctx, spool, '/news/card/TEST77/p/205')
    assert cards[0]['body']['portrait'] == cards[1]['body']['portrait'] != cards[2]['body']['portrait']


def test_career_tab_joins_real_seasons_the_archive_and_totals(pic, tmp_path):
    ctx, spool, cards = pic
    lahman(ctx.db, [1974, 1975, 1976, 1977])                 # 1977 is replayed by the association: dropped
    history.archive_season(ctx.data, 'TEST77', 1977, {'bat': {100: {'g': 10, 'ab': 30, 'h': 9, 'hr': 2}}},
                           {100: 'Cincinnati Reds'})
    head, _ = page(ctx, spool, BASE + '/career')
    assert head['image'] == '1'
    body = cards[-1]['body']
    assert body['kind'] == 'table' and body['columns'][:2] == ['Year', 'Team']
    years = [(r['cells'][0], r['cells'][1], r.get('color')) for r in body['rows']]
    assert years == [('1974', 'CIN', 'white'), ('1975', 'CIN', 'white'), ('1976', 'CIN', 'white'),
                     ('1977', 'CR', 'yellow'), ('Total', '4 yr', None)]
    assert body['rows'][-1]['bold'] is True
    hr = body['columns'].index('HR')
    assert body['rows'][0]['cells'][hr] == str(1974 % 40) and body['rows'][3]['cells'][hr] == '2'
    assert body['rows'][-1]['cells'][hr] == str(1974 % 40 + 1975 % 40 + 1976 % 40 + 2)
    assert body['prev'] is None and body['next'] is None
    assert body['caption'].endswith('Yellow: this association.') and body['note'] is None
    assert [sel for _, _, sel in cards[-1]['tabs']] == [False, False, False, True, False]


def test_career_pages_twenty_rows_with_prev_and_next(pic):
    ctx, spool, cards = pic
    lahman(ctx.db, range(1950, 1976))                        # 26 seasons and a total: two pages
    head, _ = page(ctx, spool, BASE + '/career')
    first = cards[-1]['body']
    assert len(first['rows']) == 20 and first['prev'] is None and first['next'] == BASE + '/career/1'
    assert first['caption'].startswith('Career batting, page 1 of 2.')
    assert (BASE + '/career/1') in [t for _, t in hots(head)]
    page(ctx, spool, BASE + '/career/1')
    second = cards[-1]['body']
    assert len(second['rows']) == 7 and second['rows'][-1]['cells'][0] == 'Total'
    assert second['prev'] == BASE + '/career/0' and second['next'] is None
    head, _ = page(ctx, spool, BASE + '/career/99')          # past the end: the last page
    assert cards[-1]['body']['caption'].startswith('Career batting, page 2 of 2') and head['path'] == BASE + '/career/99'


def test_career_without_a_database_lists_only_this_association(pic):
    ctx, spool, cards = pic
    history.archive_season(ctx.data, 'TEST77', 1976, {'bat': {100: {'g': 5}}})
    page(ctx, spool, BASE + '/career')
    body = cards[-1]['body']
    assert [r['cells'][0] for r in body['rows']] == ['1976', 'Total']
    assert body['caption'] == 'Career batting, page 1 of 1' and body['note'] is None


def test_career_of_a_player_with_no_seasons_says_so(pic):
    ctx, spool, cards = pic
    page(ctx, spool, '/news/card/TEST77/p/300/career')
    assert cards[-1]['body']['rows'] == [] and cards[-1]['body']['note'] == 'No seasons on record yet.'


def test_pitcher_career_uses_pitching_columns(pic):
    ctx, spool, cards = pic
    history.archive_season(ctx.data, 'TEST77', 1976, {'pit': {205: {'g': 30, 'w': 12, 'l': 8, 'outs': 600}}})
    page(ctx, spool, '/news/card/TEST77/p/205/career')
    body = cards[-1]['body']
    assert body['caption'].startswith('Career pitching') and 'W' in body['columns']
    assert body['rows'][0]['cells'][body['columns'].index('W')] == '12'


def test_news_tab_is_a_links_page(pic):
    ctx, spool, cards = pic
    head, _ = page(ctx, spool, BASE + '/news')
    body = cards[-1]['body']
    assert body['kind'] == 'links' and ('No news yet.', None) in body['items']
    assert ('Player development', '/news/development/TEST77/p/100') in body['items']
    assert '/news/development/TEST77/p/100' in [t for _, t in hots(head)]


@pytest.mark.parametrize('path', [BASE + '/stats', BASE + '/career/1000', BASE + '/career/x', BASE + '/batting/1/2',
                                  '/news/card/TEST77/p/999/career', '/news/card/NOPE/p/100/batting'])
def test_bad_tab_paths_are_not_found(pic, path):
    ctx, spool, cards = pic
    head, _ = page(ctx, spool, path)
    assert head['http'] == '404' and 'image' not in head and cards == []
    assert not [n for n in os.listdir(spool) if n.endswith('.bmp')]


def test_without_fonts_every_tab_is_the_text_card(pic, monkeypatch):
    ctx, spool, cards = pic
    monkeypatch.setattr(modbridge, '_card_fonts', lambda game: None)
    for path in (BASE, BASE + '/career', BASE + '/career/3', BASE + '/news'):
        head, body = page(ctx, spool, path)
        assert head['http'] == '200' and 'image' not in head and body.split('\n')[0] == 'Pat Doe (3B, 25)'
    assert cards == [] and not [n for n in os.listdir(spool) if n.endswith('.bmp')]


def test_a_bad_font_file_gives_the_text_card(pic):
    ctx, spool, cards = pic
    with open(os.path.join(ctx.game, '4.FNX'), 'wb') as fh:
        fh.write(b'FNX:\x09\x00')
    head, _ = page(ctx, spool, BASE)
    assert head['http'] == '200' and 'image' not in head and cards == []


def test_housekeep_removes_stale_pictures(tmp_path):
    spool = tmp_path / 'spool'
    spool.mkdir()
    old, new = spool / 'r00000001.bmp', spool / 'r00000002.bmp'
    old.write_bytes(b'BM')
    new.write_bytes(b'BM')
    past = time.time() - modbridge.STALE - 10
    os.utime(old, (past, past))
    modbridge.housekeep(str(spool))
    assert not old.exists() and new.exists()


def test_watcher_archives_a_complete_season_with_team_names(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    w = watch.Watcher(str(tmp_path / 'game'), str(data), None, None, log=lambda s: None)
    lines = {1: {'bat': {100: {'g': 3, 'hr': 1}}, 'pit': {}}, 3: {'bat': {100: {'g': 9}}, 'pit': {}}}
    monkeypatch.setattr(gamedata, 'season_lines', lambda dat, scope: lines[scope])
    assoc = {'season_year': 1977, 'teams': {1: {'name': 'Cincinnati Reds', 'roster': [100]}}}
    monkeypatch.setattr(season, 'complete', lambda a: False)
    w.history_piece(assoc, 'TEST77', 'x.DAT')
    assert history.sim_seasons(str(data), 'TEST77', 100, 'bat')[0]['year'] == 1976       # last season, no team
    assert not os.path.exists(history.archive_path(str(data), 'TEST77', 1977))
    monkeypatch.setattr(season, 'complete', lambda a: True)
    w.history_piece(assoc, 'TEST77', 'x.DAT')
    rows = history.sim_seasons(str(data), 'TEST77', 100, 'bat')
    assert [(r['year'], r['team'], r['g']) for r in rows] == [(1976, '', 9), (1977, 'Cincinnati Reds', 3)]
    lines[1]['bat'][100]['g'] = 50                       # archived once: a later pass leaves the file alone
    w.history_piece(assoc, 'TEST77', 'x.DAT')
    assert history.sim_seasons(str(data), 'TEST77', 100, 'bat')[1]['g'] == 3


@pytest.mark.parametrize('assoc,dat', [({'season_year': None, 'teams': TEAMS}, 'x.DAT'),
                                       ({'season_year': 1977, 'teams': {}}, 'x.DAT'),
                                       ({'season_year': 1977, 'teams': TEAMS}, None)])
def test_watcher_archives_nothing_without_a_year_teams_or_stats(tmp_path, monkeypatch, assoc, dat):
    data = tmp_path / 'data'
    monkeypatch.setattr(gamedata, 'season_lines', lambda d, s: {'bat': {100: {'g': 1}}, 'pit': {}})
    monkeypatch.setattr(season, 'complete', lambda a: True)
    watch.Watcher(str(tmp_path / 'game'), str(data), None, None, log=lambda s: None).history_piece(assoc, 'TEST77', dat)
    assert not (data / 'TEST77' / 'history').exists()


def test_watcher_skips_a_season_with_no_games(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    monkeypatch.setattr(gamedata, 'season_lines', lambda d, s: {'bat': {100: {'g': 0}}, 'pit': {}})
    monkeypatch.setattr(season, 'complete', lambda a: False)
    watch.Watcher(str(tmp_path / 'game'), str(data), None, None, log=lambda s: None).history_piece(
        {'season_year': 1977, 'teams': TEAMS}, 'TEST77', 'x.DAT')
    assert not (data / 'TEST77' / 'history').exists()


REAL_DB = history.DEFAULT_DB


@pytest.mark.skipif(not (os.path.isfile(os.path.join(REAL, 'Assn', 'MLBPA97.ASN')) and os.path.isfile(REAL_DB)
                         and os.path.isfile(os.path.join(REAL, '4.FNX'))), reason='no game install or Lahman here')
def test_real_install_career_has_chipper_jones_real_seasons(tmp_path, monkeypatch):
    """MLBPA97 pid 104 is Chipper Jones (jonesch06): the Career tab shows his real Braves seasons before 1997."""
    monkeypatch.setattr(modbridge, '_FONTS', {})
    cards = []
    real = cardimg.render
    monkeypatch.setattr(cardimg, 'render', lambda card, fonts: (cards.append(card), real(card, fonts))[1])
    spool = tmp_path / 'spool'
    spool.mkdir()
    ctx = types.SimpleNamespace(game=REAL, data=str(tmp_path / 'data'), backup=str(tmp_path / 'backup'), donor='',
                                db=REAL_DB, templates=None, proc=str(tmp_path / 'proc'))
    os.makedirs(ctx.data)
    head, _ = page(ctx, str(spool), '/news/card/MLBPA97/p/104/career')
    assert head['image'] == '1'
    body = cards[-1]['body']
    hr = body['columns'].index('HR')
    real_rows = {r['cells'][0]: r for r in body['rows'] if r.get('color') == 'white'}
    assert {'1993', '1995', '1996'} <= set(real_rows) and not any(int(y) >= 1997 for y in real_rows)
    assert real_rows['1995']['cells'][1] == 'ATL' and real_rows['1995']['cells'][hr] == '23'
    assert real_rows['1996']['cells'][hr] == '30'
    assert body['caption'].endswith('Yellow: this association.')


def test_career_lists_games_no_season_holds_as_other(pic, monkeypatch):
    """The stats file's career line counts 40 games more than the listed seasons: an Other row holds them, before the
    association's seasons, and the total equals the game's career."""
    ctx, spool, cards = pic
    lahman(ctx.db, [1975, 1976])
    history.archive_season(ctx.data, 'TEST77', 1977, {'bat': {100: {'g': 10, 'hr': 2}}})
    career = dict({k: 10 ** 6 for k in history.BAT_KEYS}, g=350, hr=2 + 1975 % 40 + 1976 % 40 + 9)
    monkeypatch.setattr(gamedata, 'find', lambda d, name: os.path.join(d, name) if name.endswith('.DAT')
                        else _find(d, name))
    monkeypatch.setattr(gamedata, 'season_lines',
                        lambda dat, scope: {'bat': {100: career} if scope == 2 else {}, 'pit': {}})
    page(ctx, spool, BASE + '/career')
    body = cards[-1]['body']
    cols = body['columns']
    got = [(r['cells'][0], r['cells'][cols.index('G')], r['cells'][cols.index('HR')]) for r in body['rows']]
    assert got == [('1975', '150', str(1975 % 40)), ('1976', '150', str(1976 % 40)), ('Other', '40', '9'),
                   ('1977', '10', '2'), ('Total', '350', str(career['hr']))]
    assert body['rows'][-1]['cells'][1] == '3 yr' and body['note'] == 'Other: career games the game kept with no season.'


_find = gamedata.find


def test_career_line_from_other_data_gives_a_note_not_a_row(pic, monkeypatch):
    """A stock file's career line counts more games but fewer home runs than the Lahman rows: no Other row (it would
    show negative or zeroed stats), a note with the games instead, and the total stays the sum of the rows."""
    ctx, spool, cards = pic
    lahman(ctx.db, [1975, 1976])
    career = {'g': 340, 'hr': 1}
    monkeypatch.setattr(gamedata, 'find', lambda d, name: os.path.join(d, name) if name.endswith('.DAT')
                        else _find(d, name))
    monkeypatch.setattr(gamedata, 'season_lines',
                        lambda dat, scope: {'bat': {100: career} if scope == 2 else {}, 'pit': {}})
    page(ctx, spool, BASE + '/career')
    body = cards[-1]['body']
    assert [r['cells'][0] for r in body['rows']] == ['1975', '1976', 'Total']
    assert body['rows'][-1]['cells'][body['columns'].index('G')] == '300'
    assert body['note'] == 'The game counts 40 more career games; those seasons were not archived.'
