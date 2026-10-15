"""server.py's champions page and champion rows over synthetic data directories: order, the World Series side,
bad file shapes and the Past seasons box."""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

HTML = 'text/html; charset=utf-8'


class Site:
    def __init__(self, root):
        self.root = root

    def route(self, target):
        return server.route(self.root, target)[:3]


@pytest.fixture
def site(tmp_path):
    return Site(tmp_path)


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding='utf-8')


def meta(name='1998 Major Leagues', **over):
    base = {'assn': '30L1998', 'name': name, 'updated': '2026-10-15T10:00:00', 'last_day': [4, 15],
            'standings': [], 'leaders': {}}
    base.update(over)
    return base


def postseason(assn='1998 Major Leagues', season=1998, champion='New York Yankees', rounds=None, **over):
    facts = dict(over.pop('facts', {}) or {})
    facts = dict({'association': assn, 'season': season, 'complete': champion is not None,
                  'champion': champion,
                  'rounds': rounds if rounds is not None else [
                      {'round': 1, 'name': 'Division series', 'series': []},
                      {'round': 3, 'name': 'World Series', 'series': [
                          {'teams': ['New York Yankees', 'Atlanta Braves'], 'wins': [4, 2], 'best_of': 7,
                           'winner': 'New York Yankees', 'games': []}]},
                  ]}, **facts)
    base = {'kind': 'postseason', 'created': '2026-10-15T10:00:00', 'facts': facts}
    base.update(over)
    return base


def ws_round(teams=('New York Yankees', 'Atlanta Braves'), wins=(4, 2)):
    return [{'round': 3, 'name': 'World Series', 'series': [{'teams': list(teams), 'wins': list(wins),
                                                             'best_of': 7, 'winner': teams[0], 'games': []}]}]


def seed(site):
    write(site.root / '30L1998' / 'meta.json', meta())
    return site


def cell_texts(html, caption):
    table = re.search(r'<table><caption>%s</caption>.*?<tbody>(.*?)</tbody>' % caption, html, re.S)
    return [re.findall(r'<td[^>]*>(.*?)</td>', row) for row in re.findall(r'<tr>(.*?)</tr>', table[1])]


def rows_of(html):
    return cell_texts(html, 'Champions')


def test_row_order_across_current_and_past(site):
    seed(site)
    for d, season, champ in (('1996', 1996, 'Boston Red Sox'), ('1997', 1997, 'Seattle Mariners')):
        write(site.root / '30L1998' / 'past' / d / 'postseason.json',
              postseason(season=season, champion=champ))
    write(site.root / '30L1998' / 'postseason.json', postseason(season=1998))
    rows = server._champion_rows(site.root, '30L1998')
    assert [r['season'] for r in rows] == [1998, 1997, 1996]
    assert [r['home'] for r in rows] == ['/news/30L1998/', '/news/30L1998/past/1997/', '/news/30L1998/past/1996/']
    assert [r['label'] for r in rows] == ['1998', '1997', '1996']
    assert [r['champion'] for r in rows] == ['New York Yankees', 'Seattle Mariners', 'Boston Red Sox']
    assert [r['runner_up'] for r in rows] == ['Atlanta Braves', None, None]
    assert [r['series'] for r in rows] == ['4-2', '4-2', '4-2']


def test_runner_up_and_series_when_the_champion_is_second(site):
    seed(site)
    write(site.root / '30L1998' / 'postseason.json',
          postseason(champion='Atlanta Braves', rounds=ws_round(('Atlanta Braves', 'Seattle Mariners'), (2, 4))))
    rows = server._champion_rows(site.root, '30L1998')
    assert rows[0]['champion'] == 'Atlanta Braves'
    assert rows[0]['runner_up'] == 'Seattle Mariners'
    assert rows[0]['series'] == '2-4'
    write(site.root / '30L1998' / 'postseason.json',
          postseason(champion='Seattle Mariners', rounds=ws_round(('Atlanta Braves', 'Seattle Mariners'), (2, 4))))
    rows = server._champion_rows(site.root, '30L1998')
    assert rows[0]['champion'] == 'Seattle Mariners'
    assert rows[0]['runner_up'] == 'Atlanta Braves'
    assert rows[0]['series'] == '4-2'


def test_in_progress_current_season_shows_teams_order_and_in_progress(site):
    seed(site)
    write(site.root / '30L1998' / 'postseason.json', postseason(champion=None, rounds=ws_round()))
    row = server._champion_rows(site.root, '30L1998')[0]
    assert row['champion'] is None and row['runner_up'] is None and row['series'] == '4-2'
    html = site.route('/news/30L1998/champions')[2].decode()
    assert '<td class="t">In progress</td><td class="t"></td><td>4-2</td>' in html
    write(site.root / '30L1998' / 'postseason.json',
          postseason(champion='Montreal Expos', rounds=ws_round(('', 'Atlanta Braves'), (1, 3))))
    row = server._champion_rows(site.root, '30L1998')[0]
    assert row['champion'] == 'Montreal Expos' and row['runner_up'] is None and row['series'] == '1-3'
    html = site.route('/news/30L1998/champions')[2].decode()
    assert '<td class="t">Montreal Expos</td><td class="t"></td><td>1-3</td>' in html


def test_past_folder_without_postseason_gives_no_row(site):
    seed(site)
    write(site.root / '30L1998' / 'past' / '1997' / 'meta.json', meta(name='1997 Past League'))
    write(site.root / '30L1998' / 'past' / '1998' / 'postseason.json', postseason(season=1998))
    rows = server._champion_rows(site.root, '30L1998')
    assert [r['season'] for r in rows] == [1998]
    assert rows[0]['home'] == '/news/30L1998/past/1998/'


def test_past_row_without_an_int_season_takes_the_past_label(site):
    seed(site)
    write(site.root / '30L1998' / 'past' / '1998-2' / 'postseason.json', postseason(season='1998'))
    rows = server._champion_rows(site.root, '30L1998')
    assert rows[0]['season'] is None and rows[0]['label'] == '1998 season (2)'


def post(**over):
    return postseason(**over)


def test_bad_shapes_give_empty_cells_not_crashes(site):
    seed(site)
    bads = [
        post(facts=None),
        post(facts=[]),
        post(facts={'association': 'A'}),
        post(facts={'rounds': 'no'}),
        post(facts={'rounds': [{'round': 3}, 'x', 5]}),
        post(rounds=[{'round': '3', 'series': [{'teams': ['A', 'B'], 'wins': [4, 2]}]}]),
        post(rounds=[{'round': 3, 'series': {'teams': ['A', 'B'], 'wins': [4, 2]}}]),
        post(rounds=[{'round': 3, 'series': [{'teams': ['A'], 'wins': [4, 2]},
                                             {'teams': ['A', 'B'], 'wins': ['4', 2]}]}]),
        post(rounds=[{'round': 3, 'series': [{'teams': ['A', 'B'], 'wins': [4]}]}]),
    ]
    for bad in bads:
        write(site.root / '30L1998' / 'postseason.json', bad)
        status, ctype, body = site.route('/news/30L1998/champions')
        html = body.decode()
        assert status == 200 and ctype == HTML
        assert isinstance(server._champion_rows(site.root, '30L1998'), list)
    write(site.root / '30L1998' / 'postseason.json', bads[-1])
    row = server._champion_rows(site.root, '30L1998')[0]
    assert row['champion'] == 'New York Yankees' and row['runner_up'] is None and row['series'] == ''


def test_team_names_are_escaped(site):
    seed(site)
    write(site.root / '30L1998' / 'postseason.json',
          postseason(champion='<b>Bad</b> & Co', rounds=ws_round(('<b>Bad</b> & Co', '<i>Evil</i>'), (4, 0))))
    status, _, body = site.route('/news/30L1998/champions')
    html = body.decode()
    assert status == 200
    assert '<b>' not in html and '<i>' not in html
    assert '&lt;b&gt;Bad&lt;/b&gt; &amp; Co' in html and '&lt;i&gt;Evil&lt;/i&gt;' in html
    assert '4-0' in html


def test_champions_page_layout_and_running_order(site):
    seed(site)
    write(site.root / '30L1998' / 'postseason.json', postseason(season=1998))
    write(site.root / '30L1998' / 'past' / '1997' / 'postseason.json', postseason(season=1997))
    status, ctype, body = site.route('/news/30L1998/champions')
    html = body.decode()
    assert status == 200 and ctype == HTML
    assert '<title>1998 Major Leagues · Champions</title>' in html
    assert '<h1>Champions</h1>' in html
    assert ('<p class="nav"><a href="/news/30L1998/">&larr; 1998 Major Leagues</a> &middot; '
            '<a href="/news/">All leagues</a></p>') in html
    assert ('<th class="t">Season</th><th class="t">Champion</th><th class="t">Runner-up</th><th>Series</th>'
            in html)
    assert html.index('href="/news/30L1998/postseason"') < html.index('href="/news/30L1998/past/1997/postseason"')
    assert 'href="/news/30L1998/past/1997/postseason">1997</a>' in html
    rows = rows_of(html)
    assert rows[0][:3] == ['<a href="/news/30L1998/postseason">1998</a>', 'New York Yankees', 'Atlanta Braves']
    assert rows[0][3] == '4-2'


def test_page_falls_back_to_the_assn_name_without_a_meta_name(site):
    write(site.root / '30L1998' / 'meta.json', meta(name=''))
    status, _, body = site.route('/news/30L1998/champions')
    assert '<title>30L1998 · Champions</title>' in body.decode()


def test_champions_is_404_without_meta_json(site):
    write(site.root / '30L1998' / 'postseason.json', postseason())
    for content in (None, '{"name": ', '[]'):
        if content is not None:
            write(site.root / '30L1998' / 'meta.json', content)
        status, _, body = site.route('/news/30L1998/champions')
        assert status == 404 and b'Not found' in body


def test_empty_message_with_no_files(site):
    write(site.root / '30L1998' / 'meta.json', meta())
    status, _, body = site.route('/news/30L1998/champions')
    html = body.decode()
    assert status == 200
    assert '<p class="empty">No postseason played yet.</p>' in html and '<table' not in html


def test_route_dispatches_champions(site):
    seed(site)
    write(site.root / '30L1998' / 'postseason.json', postseason())
    assert site.route('/news/30L1998/champions')[0] == 200
    assert site.route('/news/30L1998/champions/')[0] == 404
    assert site.route('/news/30L1998/champions/x')[0] == 404


def test_front_page_links_champions_only_when_a_champion_exists(site):
    seed(site)
    write(site.root / '30L1998' / 'postseason.json', postseason(champion=None))
    assert 'champions' not in site.route('/news/30L1998/')[2].decode()
    assert 'class="past"' not in site.route('/news/30L1998/')[2].decode()
    write(site.root / '30L1998' / 'postseason.json', postseason())
    html = site.route('/news/30L1998/')[2].decode()
    assert ('<section class="past"><h2>Past seasons</h2><ul>'
            '<li><a href="/news/30L1998/champions">Champions</a></li></ul></section>') in html


def test_front_page_champions_link_leads_the_past_list(site):
    seed(site)
    write(site.root / '30L1998' / 'past' / '1997' / 'meta.json', meta())
    write(site.root / '30L1998' / 'past' / '1997' / 'postseason.json', postseason())
    html = site.route('/news/30L1998/')[2].decode()
    box = re.search(r'<section class="past"><h2>Past seasons</h2><ul>(.*?)</ul></section>', html, re.S)
    assert re.findall(r'<li><a href="([^"]*)">([^<]*)</a></li>', box[1]) == [
        ('/news/30L1998/champions', 'Champions'),
        ('/news/30L1998/past/1997/', '1997 season'),
    ]


def test_front_page_without_any_champion_keeps_the_old_box(site):
    seed(site)
    write(site.root / '30L1998' / 'past' / '1997' / 'meta.json', meta())
    html = site.route('/news/30L1998/')[2].decode()
    box = re.search(r'<section class="past"><h2>Past seasons</h2><ul>(.*?)</ul></section>', html, re.S)
    assert re.findall(r'<li><a href="([^"]*)">([^<]*)</a></li>', box[1]) == [
        ('/news/30L1998/past/1997/', '1997 season'),
    ]
