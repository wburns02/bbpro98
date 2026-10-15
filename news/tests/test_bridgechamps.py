"""The in-game news reader (modbridge._news over server.route) shows the League box and the Champions page: both are
server pages, so the bridge carries them as text and links with no bridge code of its own."""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modbridge  # noqa: E402

STEM = '30L1998'
LEAGUE = {'rostered': 1313, 'mean_age': 28.7, 'le25': 292, 'ge33': 198, 'fa': 313}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding='utf-8')


def meta(**over):
    base = {'assn': STEM, 'name': '1998 Major Leagues', 'updated': '2026-10-15T10:00:00', 'last_day': [10, 20],
            'standings': [], 'leaders': {}}
    base.update(over)
    return base


def postseason(champion='New York Yankees', wins=(4, 2)):
    return {'kind': 'postseason', 'created': '2026-10-15T10:00:00', 'source': 'template',
            'headline': 'Postseason', 'body': 'The bracket.',
            'facts': {'association': '1998 Major Leagues', 'season': 1998, 'complete': champion is not None,
                      'champion': champion,
                      'rounds': [{'round': 3, 'name': 'World Series', 'series': [
                          {'teams': ['New York Yankees', 'Atlanta Braves'], 'wins': list(wins), 'best_of': 7,
                           'winner': champion, 'games': []}]}]}}


@pytest.fixture
def ctx(tmp_path):
    game, data = tmp_path / 'game', tmp_path / 'data'
    (game / 'Assn').mkdir(parents=True)
    data.mkdir()
    return types.SimpleNamespace(game=str(game), data=str(data))


def news(ctx, path):
    header, text = modbridge._news(ctx, {'path': path})
    head = dict(header)
    links = [tuple(head[k].split('\t', 1)) for k, _ in header if k.startswith('link.')]
    return head, text, links


def test_front_page_text_carries_the_league_box(ctx):
    write(modbridge.pathlib.Path(ctx.data) / STEM / 'meta.json', meta(league=LEAGUE))
    head, text, _ = news(ctx, '/news/%s/' % STEM)
    assert head['status'] == 'ok' and head['http'] == '200'
    assert 'League' in text
    assert '1,313 players on rosters, mean age 28.7.' in text
    assert '292 aged 25 or under, 198 aged 33 or over. 313 free agents.' in text


def test_front_page_without_league_data_has_no_league_box(ctx):
    write(modbridge.pathlib.Path(ctx.data) / STEM / 'meta.json', meta())
    head, text, _ = news(ctx, '/news/%s/' % STEM)
    assert head['status'] == 'ok'
    assert 'players on rosters' not in text


def test_front_page_links_champions_once_a_season_has_one(ctx):
    root = modbridge.pathlib.Path(ctx.data) / STEM
    write(root / 'meta.json', meta(league=LEAGUE))
    write(root / 'postseason.json', postseason())
    _, _, links = news(ctx, '/news/%s/' % STEM)
    assert ('Champions', '/news/%s/champions' % STEM) in links


def test_front_page_has_no_champions_link_while_the_bracket_is_open(ctx):
    root = modbridge.pathlib.Path(ctx.data) / STEM
    write(root / 'meta.json', meta())
    write(root / 'postseason.json', postseason(champion=None, wins=(2, 1)))
    _, _, links = news(ctx, '/news/%s/' % STEM)
    assert all(label != 'Champions' for label, _ in links)


def test_champions_page_reads_as_text_with_the_season_link(ctx):
    root = modbridge.pathlib.Path(ctx.data) / STEM
    write(root / 'meta.json', meta())
    write(root / 'postseason.json', postseason())
    head, text, links = news(ctx, '/news/%s/champions' % STEM)
    assert head['status'] == 'ok' and head['http'] == '200'
    assert 'Champions' in head['title']
    assert 'New York Yankees' in text and 'Atlanta Braves' in text and '4-2' in text
    assert ('1998', '/news/%s/postseason' % STEM) in links


def test_champions_page_for_an_unknown_association_is_an_error_reply(ctx):
    head, _, _ = news(ctx, '/news/NOPE/champions')
    assert head['status'] == 'error' and head['http'] == '404'
