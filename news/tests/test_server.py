"""server.py over HTTP on synthetic data directories: routes, paging, escaping, refusals, headers and status.json."""
import http.client
import json
import os
import re
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

KEY = '0f3a9c1d2b4e5f60'
KEY2 = 'a1b2c3d4e5f60718'
HTML = 'text/html; charset=utf-8'
SECURITY = {
    'content-security-policy': ("default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                                "form-action 'none'; frame-ancestors 'self'"),
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    'cache-control': 'no-cache',
}
EMPTY_STATUS = {'date': None, 'calls': 0, 'out_tokens': 0, 'in_tokens': 0, 'calls_per_day': None,
                'tokens_per_day': None}


def write(path, obj):
    """JSON for obj, or obj itself when it is already text (for corrupt files)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding='utf-8')


def team(tid, name, abbrev, wins, losses, pct, gb):
    return {'tid': tid, 'name': name, 'abbrev': abbrev, 'w': wins, 'l': losses, 'pct': pct, 'gb': gb}


def meta(**over):
    base = {
        'assn': '30L1998', 'name': '1998 Major Leagues', 'updated': '2026-10-09T14:03:11', 'last_day': [4, 15],
        'standings': [
            {'league': 'American League', 'division': 'East', 'teams': [
                team(1, 'New York Yankees', 'NYA', 10, 3, '.769', '-'),
                team(2, 'Boston Red Sox', 'BOS', 7, 6, '.538', '3')]},
            {'league': '', 'division': '', 'teams': [team(3, 'Seattle Mariners', 'SEA', 7, 6, '.538', '-')]},
        ],
        'leaders': {
            'avg': [{'name': 'Larry Walker', 'value': '.412'}, {'name': 'Tony Gwynn', 'value': '.390'},
                    {'name': 'Ken Griffey', 'value': '.350'}, {'name': 'Fourth Hitter', 'value': '.300'}],
            'hr': [{'name': 'Mark McGwire', 'value': '9'}],
            'rbi': [], 'sb': [], 'w': [], 'so': [], 'sv': [], 'era': [],
        },
    }
    base.update(over)
    return base


def story(key, month=4, day=15, slot=13, ar=5, hr=3, headline='Seattle beats Oakland',
          body='Ken Griffey had three hits.\nThe Mariners won late.', source='glm'):
    """A recap file in the shape the watcher writes."""
    return {
        'key': key, 'assn': '30L1998', 'month': month, 'day': day, 'slot': slot, 'headline': headline,
        'body': body, 'source': source, 'created': '2026-10-09T14:03:11',
        'facts': {
            'association': '1998 Major Leagues', 'date': 'April %d' % day, 'innings': 9,
            'winner': 'away' if ar > hr else 'home',
            'away': {'name': 'Seattle Mariners', 'abbrev': 'SEA', 'runs': ar, 'hits': 9, 'record': '7-6'},
            'home': {'name': 'Oakland Athletics', 'abbrev': 'OAK', 'runs': hr, 'hits': 6, 'record': '5-8',
                     'stadium': 'Oakland-Alameda County Stadium'},
            'batters': [{'team': 'SEA', 'name': 'Ken Griffey', 'ab': 4, 'h': 3, '2b': 1, '3b': 0, 'hr': 1, 'rbi': 3,
                         'bb': 0, 'r': 1, 'sb': 0}],
            'decisions': {
                'win': {'team': 'SEA', 'name': 'Jamie Moyer', 'ip': '7.2', 'h': 5, 'r': 2, 'er': 2, 'bb': 1, 'so': 10},
                'loss': {'team': 'OAK', 'name': 'Kenny Rogers', 'ip': '6.0', 'h': 7, 'r': 4, 'er': 4, 'bb': 2, 'so': 3},
                'save': {'team': 'SEA', 'name': 'Norm Charlton', 'ip': '2.0', 'h': 1, 'r': 0, 'er': 0, 'bb': 0,
                         'so': 2},
            },
            'notes': ['shutout'],
        },
    }


def feed(month, day, headline, body='Columns body.\nSecond line.'):
    return {'month': month, 'day': day, 'date': 'April %d' % day, 'headline': headline, 'body': body,
            'source': 'template', 'created': '2026-10-09T14:03:11', 'facts': {}}


def seed(root):
    write(root / 'budget.json', {'date': '2026-10-09', 'calls': 12, 'out_tokens': 34000, 'in_tokens': 9000})
    write(root / 'limits.json', {'calls_per_day': 1000, 'tokens_per_day': 2000000})
    write(root / '30L1998' / 'meta.json', meta())
    write(root / '30L1998' / 'recaps' / (KEY + '.json'), story(KEY))
    write(root / '30L1998' / 'recaps' / (KEY2 + '.json'),
          story(KEY2, day=14, ar=2, hr=4, source='template', headline='Oakland edges Seattle'))
    write(root / '30L1998' / 'feed' / '04-02.json', feed(4, 2, 'Old column'))
    write(root / '30L1998' / 'feed' / '04-15.json', feed(4, 15, 'Yankees hold the East'))
    write(root / 'MLBPA97' / 'meta.json', meta(assn='MLBPA97', name='1997 Player Association',
                                              updated='2026-10-01T09:00:00', last_day=None, standings=[], leaders={}))


class Site:
    def __init__(self, root, port):
        self.root, self.port = root, port

    def get(self, path, method='GET'):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            body = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, body
        finally:
            conn.close()

    def keys(self, path):
        return re.findall(r'href="/news/30L1998/([0-9a-f]{16})"', self.get(path)[2].decode())


@pytest.fixture
def site(tmp_path):
    srv = server.make_server(tmp_path, port=0)
    thread = threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    thread.start()
    yield Site(tmp_path, srv.server_address[1])
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def seeded(site):
    seed(site.root)
    return site


def assert_secure(headers, body):
    for name, value in SECURITY.items():
        assert headers[name] == value
    assert headers['content-length'] == str(len(body))
    assert 'set-cookie' not in headers
    assert 'access-control-allow-origin' not in headers


def test_index_newest_first_with_latest_feed_and_no_games_yet(seeded):
    status, headers, body = seeded.get('/news/')
    html = body.decode()
    assert status == 200
    assert headers['content-type'] == HTML
    assert html.index('1998 Major Leagues') < html.index('1997 Player Association')
    assert 'through April 15' in html
    assert 'no games yet' in html
    assert 'Yankees hold the East' in html
    assert 'Old column' not in html
    assert 'href="/news/30L1998/"' in html
    assert 'Back to the game' in html


def test_index_skips_unreadable_meta_and_has_an_empty_state(site):
    assert 'No league news yet.' in site.get('/news/')[2].decode()
    write(site.root / 'BROKEN' / 'meta.json', '{"name": ')
    write(site.root / 'LISTED' / 'meta.json', '[]')
    write(site.root / 'NOTDIR', 'x')
    assert 'No league news yet.' in site.get('/news/')[2].decode()


def test_association_page_standings_leaders_and_feed(seeded):
    html = seeded.get('/news/30L1998/')[2].decode()
    assert 'through April 15' in html
    assert '<caption>American League East</caption>' in html
    assert '<caption>Standings</caption>' in html
    assert 'New York Yankees' in html and '.769' in html
    assert '<caption>AVG</caption>' in html and '<caption>HR</caption>' in html
    assert '<caption>RBI</caption>' not in html
    assert 'Larry Walker' in html and 'Ken Griffey' in html
    assert 'Fourth Hitter' not in html
    assert 'Yankees hold the East' in html
    assert 'Old column' not in html


def test_story_list_order_and_paging(site):
    write(site.root / '30L1998' / 'meta.json', meta())
    write(site.root / '30L1998' / 'feed' / '04-15.json', feed(4, 15, 'Column on page one'))
    for i in range(31):
        write(site.root / '30L1998' / 'recaps' / ('%016x.json' % i),
              story('%016x' % i, slot=i, headline='Story %d' % i))
    html1 = site.get('/news/30L1998/')[2].decode()
    html2 = site.get('/news/30L1998/?page=2')[2].decode()
    assert site.keys('/news/30L1998/') == ['%016x' % i for i in range(30, 0, -1)]
    assert site.keys('/news/30L1998/?page=2') == ['%016x' % 0]
    assert 'Column on page one' in html1 and 'Column on page one' not in html2
    assert 'Older stories' in html1 and 'Older stories' not in html2
    assert 'Newer stories' in html2 and 'Newer stories' not in html1
    assert 'href="/news/30L1998/?page=2"' in html1


def test_ties_on_date_and_slot_sort_by_key(site):
    write(site.root / '30L1998' / 'meta.json', meta())
    write(site.root / '30L1998' / 'recaps' / 'bbbbbbbbbbbbbbbb.json', story('bbbbbbbbbbbbbbbb', slot=13))
    write(site.root / '30L1998' / 'recaps' / 'aaaaaaaaaaaaaaaa.json', story('aaaaaaaaaaaaaaaa', slot=13))
    write(site.root / '30L1998' / 'recaps' / 'cccccccccccccccc.json', story('cccccccccccccccc', day=14, slot=13))
    assert site.keys('/news/30L1998/') == ['aaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbb', 'cccccccccccccccc']


@pytest.mark.parametrize('query', ['page=abc', 'page=0', 'page=-1', 'page=99999', 'page=1.5', 'page='])
def test_bad_page_numbers_mean_page_one(seeded, query):
    assert seeded.keys('/news/30L1998/?' + query) == seeded.keys('/news/30L1998/')


def test_story_page_box_batters_decisions_and_byline(seeded):
    status, _, body = seeded.get('/news/30L1998/' + KEY)
    html = body.decode()
    assert status == 200
    assert '<title>Seattle beats Oakland</title>' in html
    assert 'April 15 · Oakland-Alameda County Stadium' in html
    assert 'Staff writer' in html and 'Wire report' not in html
    assert 'Ken Griffey had three hits.' in html and 'The Mariners won late.' in html
    assert html.index('Seattle Mariners') < html.index('Oakland Athletics')
    assert '<td>4</td><td>3</td><td>1</td><td>3</td><td>0</td><td>1</td>' in html
    assert 'Jamie Moyer (SEA): 7.2 IP, 5 H, 2 R, 2 ER, 1 BB, 10 SO' in html
    assert 'Kenny Rogers (OAK): 6.0 IP' in html
    assert 'Norm Charlton (SEA): 2.0 IP' in html
    assert 'href="/news/30L1998/"' in html


def test_template_story_has_wire_byline(seeded):
    html = seeded.get('/news/30L1998/' + KEY2)[2].decode()
    assert 'Wire report' in html and 'Staff writer' not in html


def test_story_row_score_line_has_winner_first(seeded):
    html = seeded.get('/news/30L1998/')[2].decode()
    assert 'April 15 · SEA 5, OAK 3' in html
    assert 'April 14 · OAK 4, SEA 2' in html


def test_values_are_escaped_everywhere(seeded):
    write(seeded.root / '30L1998' / 'recaps' / ('dddddddddddddddd.json'),
          story('dddddddddddddddd', day=16, headline='<script>alert(1)</script>',
                body='Fine <b>bold</b> & "quoted"'))
    write(seeded.root / '30L1998' / 'feed' / '04-17.json', feed(4, 17, '<img src=x onerror=alert(1)>'))
    write(seeded.root / '30L1998' / 'meta.json',
          meta(leaders={'hr': [{'name': 'Bo "Slugger" Smith', 'value': '9'}]}))
    pages = [seeded.get(p)[2].decode() for p in ('/news/', '/news/30L1998/', '/news/30L1998/dddddddddddddddd')]
    for html in pages:
        assert '<script' not in html and '<img' not in html and '<b>bold' not in html
    index, assoc, story_page = pages
    assert '&lt;img src=x onerror=alert(1)&gt;' in index
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in assoc and '&lt;script&gt;alert(1)&lt;/script&gt;' in story_page
    assert 'Bo &quot;Slugger&quot; Smith' in assoc and '"Slugger"' not in assoc
    assert '&lt;b&gt;bold&lt;/b&gt; &amp; &quot;quoted&quot;' in story_page


@pytest.mark.parametrize('path', [
    '/news/../etc/', '/news/../etc', '/news/a.b/', '/news/a.b', '/news/TOOLONGNAME/', '/news/%2e%2e/',
    '/news/%2e%2e', '/news/..%2Fetc/', '/news/30L1998%0A/', '/news/30L%zz/', '/news/%00/', '/news/./',
])
def test_bad_association_name_is_404(seeded, path):
    assert seeded.get(path)[0] == 404


@pytest.mark.parametrize('name', ['0F3A9C1D2B4E5F60', '0f3a9c1d2b4e5f6', '0f3a9c1d2b4e5f60a'])
def test_bad_story_key_is_404_even_with_a_readable_file(seeded, name):
    write(seeded.root / '30L1998' / 'recaps' / (name + '.json'), story(name))
    assert seeded.get('/news/30L1998/' + name)[0] == 404


def test_missing_or_corrupt_meta_is_404(seeded):
    assert seeded.get('/news/MLBPA99/')[0] == 404
    write(seeded.root / 'NOMETA' / 'recaps' / (KEY + '.json'), story(KEY))
    assert seeded.get('/news/NOMETA/')[0] == 404
    write(seeded.root / '30L1998' / 'meta.json', '{"name": ')
    assert seeded.get('/news/30L1998/')[0] == 404
    write(seeded.root / '30L1998' / 'meta.json', '[]')
    assert seeded.get('/news/30L1998/')[0] == 404


def test_corrupt_recap_is_skipped_in_the_list_and_404_on_its_own_page(seeded):
    bad, listy = 'cccccccccccccccc', 'eeeeeeeeeeeeeeee'
    write(seeded.root / '30L1998' / 'recaps' / (bad + '.json'), '{"month": 4, "day"')
    write(seeded.root / '30L1998' / 'recaps' / (listy + '.json'), '[1, 2]')
    status, _, body = seeded.get('/news/30L1998/')
    assert status == 200
    assert seeded.keys('/news/30L1998/') == [KEY, KEY2]
    assert bad not in body.decode() and listy not in body.decode()
    assert seeded.get('/news/30L1998/' + bad)[0] == 404
    assert seeded.get('/news/30L1998/' + listy)[0] == 404


def test_unknown_story_is_404(seeded):
    assert seeded.get('/news/30L1998/ffffffffffffffff')[0] == 404
    assert seeded.get('/news/nope/' + KEY)[0] == 404


@pytest.mark.parametrize('path, location', [
    ('/news', '/news/'),
    ('/news/30L1998', '/news/30L1998/'),
    ('/news/30L1998?page=2', '/news/30L1998/?page=2'),
])
def test_redirects_add_the_trailing_slash(seeded, path, location):
    status, headers, body = seeded.get(path)
    assert status == 301 and headers['location'] == location
    assert headers['content-type'] == HTML
    assert_secure(headers, body)


@pytest.mark.parametrize('method', ['POST', 'PUT', 'DELETE', 'OPTIONS', 'BREW'])
def test_other_methods_are_405_with_allow(seeded, method):
    status, headers, body = seeded.get('/news/30L1998/', method)
    assert status == 405 and headers['allow'] == 'GET, HEAD'
    assert_secure(headers, body)


@pytest.mark.parametrize('path', ['/news/', '/news/30L1998/', '/news/30L1998/' + KEY, '/news/status.json',
                                  '/news/nope/', '/news'])
def test_head_has_no_body_and_the_get_length(seeded, path):
    get_status, get_headers, get_body = seeded.get(path)
    head_status, head_headers, head_body = seeded.get(path, 'HEAD')
    assert head_body == b''
    assert head_status == get_status
    assert head_headers['content-type'] == get_headers['content-type']
    assert head_headers['content-length'] == get_headers['content-length'] == str(len(get_body))
    assert_secure(head_headers, get_body)


@pytest.mark.parametrize('path, status, ctype', [
    ('/news/', 200, HTML),
    ('/news/30L1998/', 200, HTML),
    ('/news/30L1998/' + KEY, 200, HTML),
    ('/news/status.json', 200, 'application/json'),
    ('/news/nope/', 404, HTML),
    ('/', 404, HTML),
    ('/news', 301, HTML),
])
def test_every_response_carries_the_security_headers(seeded, path, status, ctype):
    got_status, headers, body = seeded.get(path)
    assert got_status == status
    assert headers['content-type'] == ctype
    assert_secure(headers, body)


@pytest.mark.parametrize('path', ['/news/30L1998/' + KEY + '/', '/news/30L1998/' + KEY + '/x', '/news//',
                                  '/news/a\\b/', '/elsewhere', '/news/status.json/'])
def test_unknown_routes_are_404_pages(seeded, path):
    status, headers, body = seeded.get(path)
    assert status == 404 and b'Not found' in body
    assert_secure(headers, body)


def test_status_merges_budget_and_limits_and_nothing_else(seeded):
    write(seeded.root / 'budget.json', {'date': '2026-10-09', 'calls': 12, 'out_tokens': 34000, 'in_tokens': 9000,
                                        'api_key': 'secret'})
    status, headers, body = seeded.get('/news/status.json')
    assert status == 200 and headers['content-type'] == 'application/json'
    assert json.loads(body) == {'date': '2026-10-09', 'calls': 12, 'out_tokens': 34000, 'in_tokens': 9000,
                                'calls_per_day': 1000, 'tokens_per_day': 2000000}
    assert_secure(headers, body)


def test_status_survives_missing_and_corrupt_files(site):
    assert json.loads(site.get('/news/status.json')[2]) == EMPTY_STATUS
    write(site.root / 'budget.json', '{"calls": ')
    write(site.root / 'limits.json', '[]')
    assert json.loads(site.get('/news/status.json')[2]) == EMPTY_STATUS
    write(site.root / 'limits.json', {'calls_per_day': 5, 'tokens_per_day': 7})
    assert json.loads(site.get('/news/status.json')[2]) == dict(EMPTY_STATUS, calls_per_day=5, tokens_per_day=7)


def test_one_log_line_per_request(seeded, capsys):
    seeded.get('/news/status.json')
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert '"GET /news/status.json HTTP/1.1" 200' in lines[0]


def test_main_needs_a_data_directory(monkeypatch, tmp_path):
    monkeypatch.delenv('BBNEWS_DATA', raising=False)
    with pytest.raises(SystemExit):
        server.main([])
    with pytest.raises(SystemExit):
        server.main(['--data', str(tmp_path / 'missing')])


def preview_file(**over):
    """A preview.json in the shape the watcher writes: two divisions, the second one unnamed."""
    base = {
        'headline': 'Yankees favored in a crowded East', 'body': 'The season opens April 6.\nFour clubs have a shot.',
        'source': 'glm', 'kind': 'preview', 'created': '2026-10-09T14:03:11',
        'facts': {
            'association': '1998 Major Leagues', 'teams': 3, 'games': 162, 'opening_day': 'April 6',
            'divisions': [
                {'league': 'American League', 'division': 'East', 'teams': [
                    {'name': 'New York Yankees', 'manager': 'Joe Torre', 'stadium': 'Yankee Stadium',
                     'hitter': {'name': 'Bernie Williams', 'avg': '.339', 'hr': 30, 'rbi': 98},
                     'pitcher': {'name': 'David Cone', 'w': 17, 'l': 6, 'era': '3.55', 'so': 200}},
                    {'name': 'Boston Red Sox', 'manager': 'Jimy Williams', 'stadium': 'Fenway Park',
                     'hitter': None, 'pitcher': None}]},
                {'league': '', 'division': '', 'teams': [
                    {'name': 'Seattle Mariners', 'manager': 'Lou Piniella', 'stadium': 'Kingdome',
                     'hitter': {'name': 'Ken Griffey', 'avg': '.304', 'hr': 56, 'rbi': 146},
                     'pitcher': {'name': 'Randy Johnson', 'w': 19, 'l': 4, 'era': '2.28', 'so': 213}}]},
            ],
        },
    }
    base.update(over)
    return base


def awards_file(**over):
    """An awards.json in the shape the watcher writes: an American and a National League, no Cy Young in the second."""
    base = {
        'headline': 'Gonzalez and Clemens take the American League', 'body': 'Texas and Toronto each had a winner.',
        'source': 'template', 'kind': 'awards', 'created': '2026-10-09T14:03:11',
        'facts': {
            'association': '1998 Major Leagues',
            'leagues': [
                {'league': 'American League',
                 'champions': [{'division': 'East', 'team': 'New York Yankees', 'record': '114-48'},
                               {'division': 'Central', 'team': 'Cleveland Indians', 'record': '89-73'}],
                 'mvp': [{'name': 'Juan Gonzalez', 'team': 'TEX', 'avg': '.318', 'hr': 45, 'rbi': 157, 'r': 110,
                          'sb': 3, 'runs_created': 129}],
                 'cy_young': [{'name': 'Roger Clemens', 'team': 'TOR', 'w': 20, 'l': 6, 'era': '2.65', 'so': 271,
                               'sv': 0, 'ip': '233.2'},
                              {'name': 'Mike Mussina', 'team': 'BAL', 'w': 19, 'l': 9, 'era': '3.15', 'so': 222,
                               'sv': 0, 'ip': '245.1'}]},
                {'league': 'National League',
                 'champions': [{'division': 'West', 'team': 'San Diego Padres', 'record': '98-64'}],
                 'mvp': [{'name': 'Sammy Sosa', 'team': 'CHC', 'avg': '.308', 'hr': 66, 'rbi': 158, 'r': 134,
                          'sb': 18, 'runs_created': 150}],
                 'cy_young': []},
            ],
        },
    }
    base.update(over)
    return base


MAKERS = {'preview': preview_file, 'awards': awards_file}


@pytest.fixture
def season(seeded):
    """seeded, plus both season files for 30L1998."""
    write(seeded.root / '30L1998' / 'preview.json', preview_file())
    write(seeded.root / '30L1998' / 'awards.json', awards_file())
    return seeded


def test_preview_page_has_the_story_layout_and_every_table_value(season):
    status, headers, body = season.get('/news/30L1998/preview')
    html = body.decode()
    assert status == 200 and headers['content-type'] == HTML
    assert '<title>Yankees favored in a crowded East</title>' in html
    assert ('<p class="nav"><a href="/news/30L1998/">&larr; 1998 Major Leagues</a> &middot; '
            '<a href="/news/">All leagues</a></p>') in html
    assert '<h1>Yankees favored in a crowded East</h1>' in html
    assert '<p class="dateline">Season preview</p><p class="byline">Staff writer</p>' in html
    assert '<p>The season opens April 6.</p><p>Four clubs have a shot.</p>' in html
    assert '<caption>American League East</caption>' in html
    assert '<caption>Teams</caption>' in html
    assert ('<th class="t">Team</th><th class="t">Manager</th><th class="t">Top hitter</th>'
            '<th class="t">Top pitcher</th>') in html
    assert ('<tr><td class="t">New York Yankees</td><td class="t">Joe Torre</td>'
            '<td class="t">Bernie Williams, 30 HR, 98 RBI</td>'
            '<td class="t">David Cone, 17-6, 3.55 ERA</td></tr>') in html
    assert ('<tr><td class="t">Boston Red Sox</td><td class="t">Jimy Williams</td><td class="t"></td>'
            '<td class="t"></td></tr>') in html
    assert ('<tr><td class="t">Seattle Mariners</td><td class="t">Lou Piniella</td>'
            '<td class="t">Ken Griffey, 56 HR, 146 RBI</td>'
            '<td class="t">Randy Johnson, 19-4, 2.28 ERA</td></tr>') in html


def test_awards_page_has_a_section_per_league_and_every_table_value(season):
    status, headers, body = season.get('/news/30L1998/awards')
    html = body.decode()
    assert status == 200 and headers['content-type'] == HTML
    assert '<title>Gonzalez and Clemens take the American League</title>' in html
    assert '<p class="dateline">Season awards</p><p class="byline">Wire report</p>' in html
    assert '<p>Texas and Toronto each had a winner.</p>' in html
    assert html.index('<section><h2>American League</h2>') < html.index('<section><h2>National League</h2>')
    assert ('<th class="t">Player</th><th class="t">Team</th><th>AVG</th><th>HR</th><th>RBI</th><th>R</th>'
            '<th>SB</th><th>RC</th>') in html
    assert ('<tr><td class="t">Juan Gonzalez</td><td class="t">TEX</td><td>.318</td><td>45</td><td>157</td>'
            '<td>110</td><td>3</td><td>129</td></tr>') in html
    assert ('<th class="t">Pitcher</th><th class="t">Team</th><th>W</th><th>L</th><th>ERA</th><th>IP</th>'
            '<th>SO</th><th>SV</th>') in html
    assert ('<tr><td class="t">Roger Clemens</td><td class="t">TOR</td><td>20</td><td>6</td><td>2.65</td>'
            '<td>233.2</td><td>271</td><td>0</td></tr>') in html
    assert ('<tr><td class="t">Mike Mussina</td><td class="t">BAL</td><td>19</td><td>9</td><td>3.15</td>'
            '<td>245.1</td><td>222</td><td>0</td></tr>') in html
    assert '<th class="t">Division</th><th class="t">Team</th><th>Record</th>' in html
    assert '<tr><td class="t">East</td><td class="t">New York Yankees</td><td>114-48</td></tr>' in html
    assert '<tr><td class="t">West</td><td class="t">San Diego Padres</td><td>98-64</td></tr>' in html
    assert html.count('<caption>MVP</caption>') == 2
    assert html.count('<caption>Cy Young</caption>') == 1
    assert html.count('<caption>Division champions</caption>') == 2


def test_one_league_awards_are_headed_the_league(season):
    one = {'association': '1998 Major Leagues', 'leagues': [
        {'league': '', 'champions': [{'division': 'West', 'team': 'Oakland Athletics', 'record': '74-88'}],
         'mvp': [], 'cy_young': [{'name': 'Kenny Rogers', 'team': 'OAK', 'w': 12, 'l': 9, 'era': '3.96', 'so': 163,
                                  'sv': 0, 'ip': '193.0'}]}]}
    write(season.root / '30L1998' / 'awards.json', awards_file(headline='One league', facts=one))
    html = season.get('/news/30L1998/awards')[2].decode()
    assert '<section><h2>The league</h2>' in html
    assert '<caption>Cy Young</caption>' in html and '<caption>Division champions</caption>' in html
    assert '<caption>MVP</caption>' not in html
    assert '<h2>American League</h2>' not in html


def test_season_pages_with_no_data_have_no_tables_and_need_no_meta(site):
    write(site.root / 'ORPHAN' / 'awards.json', awards_file(headline='', facts={'leagues': []}))
    write(site.root / 'LONELY' / 'preview.json', preview_file(headline='', facts={'divisions': []}))
    status, _, body = site.get('/news/ORPHAN/awards')
    html = body.decode()
    assert status == 200
    assert '<title>Season awards</title>' in html and '&larr; ORPHAN</a>' in html
    assert '<table' not in html and '<section>' not in html
    html = site.get('/news/LONELY/preview')[2].decode()
    assert '<title>Season preview</title>' in html and '&larr; LONELY</a>' in html
    assert '<table' not in html


@pytest.mark.parametrize('odd', [None, 'Bernie Williams', ['Bernie Williams']])
def test_hitter_and_pitcher_that_are_not_objects_are_empty_cells(season, odd):
    doc = preview_file()
    yankees = doc['facts']['divisions'][0]['teams'][0]
    yankees['hitter'], yankees['pitcher'] = odd, odd
    write(season.root / '30L1998' / 'preview.json', doc)
    html = season.get('/news/30L1998/preview')[2].decode()
    assert ('<tr><td class="t">New York Yankees</td><td class="t">Joe Torre</td><td class="t"></td>'
            '<td class="t"></td></tr>') in html
    assert 'None' not in html and 'Bernie' not in html


def test_missing_fields_in_a_hitter_or_pitcher_are_blank_not_none(season):
    doc = preview_file()
    yankees = doc['facts']['divisions'][0]['teams'][0]
    yankees['hitter'], yankees['pitcher'] = {'name': 'Bernie Williams'}, {'name': 'David Cone'}
    write(season.root / '30L1998' / 'preview.json', doc)
    html = season.get('/news/30L1998/preview')[2].decode()
    assert 'Bernie Williams,  HR,  RBI' in html and 'David Cone, -,  ERA' in html
    assert 'None' not in html


def test_names_and_headlines_are_escaped_on_both_season_pages(season):
    doc = preview_file(headline='<script>alert(1)</script>')
    doc['facts']['association'] = '<b>Lg</b>'
    doc['facts']['divisions'][0]['teams'][0]['name'] = '<script>x</script>'
    write(season.root / '30L1998' / 'preview.json', doc)
    awards = awards_file(headline='<img src=x onerror=alert(1)>')
    awards['facts']['leagues'][0]['league'] = '<script>y</script>'
    awards['facts']['leagues'][0]['mvp'][0]['name'] = '<img src=y onerror=alert(2)>'
    write(season.root / '30L1998' / 'awards.json', awards)
    preview_html = season.get('/news/30L1998/preview')[2].decode()
    awards_html = season.get('/news/30L1998/awards')[2].decode()
    for html in (preview_html, awards_html):
        assert '<script' not in html and '<img' not in html and '<b>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in preview_html and '&lt;script&gt;x&lt;/script&gt;' in preview_html
    assert '&lt;b&gt;Lg&lt;/b&gt;' in preview_html
    assert '&lt;img src=x onerror=alert(1)&gt;' in awards_html
    assert '&lt;script&gt;y&lt;/script&gt;' in awards_html and '&lt;img src=y onerror=alert(2)&gt;' in awards_html


@pytest.mark.parametrize('name', ['preview', 'awards'])
def test_missing_season_file_is_404(seeded, name):
    status, headers, body = seeded.get('/news/30L1998/' + name)
    assert status == 404 and b'Not found' in body
    assert_secure(headers, body)


@pytest.mark.parametrize('name', ['preview', 'awards'])
@pytest.mark.parametrize('content', ['{"headline": ', '[1, 2]', '"preview"', 'null'])
def test_corrupt_or_non_object_season_file_is_404(seeded, name, content):
    write(seeded.root / '30L1998' / (name + '.json'), content)
    assert seeded.get('/news/30L1998/' + name)[0] == 404


@pytest.mark.parametrize('name, kind', [
    ('preview', 'awards'), ('preview', 'Preview'), ('preview', ''), ('preview', None),
    ('awards', 'preview'), ('awards', 'Awards'), ('awards', None),
])
def test_season_file_of_another_kind_is_404(seeded, name, kind):
    doc = MAKERS[name]()
    doc['kind'] = kind
    write(seeded.root / '30L1998' / (name + '.json'), doc)
    assert seeded.get('/news/30L1998/' + name)[0] == 404


def test_season_file_without_a_kind_is_404(seeded):
    doc = preview_file()
    del doc['kind']
    write(seeded.root / '30L1998' / 'preview.json', doc)
    assert seeded.get('/news/30L1998/preview')[0] == 404


@pytest.mark.parametrize('path', ['/news/30L1998/preview/', '/news/30L1998/awards/', '/news/30L1998/preview/x'])
def test_season_paths_take_no_trailing_slash_variant(season, path):
    status, headers, body = season.get(path)
    assert status == 404 and b'Not found' in body
    assert_secure(headers, body)


@pytest.mark.parametrize('path, status', [
    ('/news/30L1998/preview', 200), ('/news/30L1998/awards', 200), ('/news/30L1998/', 200),
    ('/news/MLBPA97/preview', 404), ('/news/MLBPA97/awards', 404),
])
def test_season_pages_carry_the_security_headers(season, path, status):
    got, headers, body = season.get(path)
    assert got == status
    assert_secure(headers, body)


def test_league_page_links_awards_before_preview_above_the_standings(season):
    html = season.get('/news/30L1998/')[2].decode()
    assert ('<aside class="side"><section class="season"><h2>Season</h2><ul>'
            '<li><a href="/news/30L1998/awards">Season awards</a></li>'
            '<li><a href="/news/30L1998/preview">Season preview</a></li>'
            '</ul></section><section><div class="table-wrap"><table><caption>American League East</caption>') in html


@pytest.mark.parametrize('files, links', [
    (('preview',), ['Season preview']),
    (('awards',), ['Season awards']),
    (('awards', 'preview'), ['Season awards', 'Season preview']),
])
def test_league_page_lists_only_the_season_files_that_exist(seeded, files, links):
    for name in files:
        write(seeded.root / '30L1998' / (name + '.json'), MAKERS[name]())
    html = seeded.get('/news/30L1998/')[2].decode()
    for label in ('Season awards', 'Season preview'):
        assert (label in html) == (label in links)
    assert ('class="season"' in html) == bool(links)


def test_league_page_has_no_season_section_without_either_file(seeded):
    html = seeded.get('/news/30L1998/')[2].decode()
    assert 'class="season"' not in html and '<h2>Season</h2>' not in html


def test_season_section_is_on_the_first_page_only(season):
    for i in range(31):
        write(season.root / '30L1998' / 'recaps' / ('%016x.json' % i), story('%016x' % i, slot=i))
    html1 = season.get('/news/30L1998/')[2].decode()
    html2 = season.get('/news/30L1998/?page=2')[2].decode()
    assert season.keys('/news/30L1998/?page=2')
    assert 'class="season"' in html1 and 'class="season"' not in html2


def scout_file(tid, team, **over):
    """A scout/<tid>.json in the shape the watcher writes: two hitters (the second with no birth year) and a pitcher."""
    base = {
        'headline': 'Scouting the %s' % team, 'body': 'Ann Hart grades 80 for contact.\nBo Lee grades 70 for control.',
        'source': 'template', 'reason': 'off', 'kind': 'scout', 'tid': tid, 'abbrev': 'NYA', 'team': team,
        'created': '2026-10-09T14:03:11',
        'facts': {'association': '1998 Major Leagues', 'team': team, 'hitters': [], 'pitchers': []},
        'roster': {
            'hitters': [
                {'pid': 101, 'name': 'Ann Hart', 'pos': 'CF', 'hand': 'L/L', 'age': 32, 'contact': 80, 'power': 50,
                 'speed': 80, 'fielding': 60},
                {'pid': 102, 'name': 'Bo Lee', 'pos': 'C', 'hand': 'R/R', 'age': None, 'contact': 50, 'power': 50,
                 'speed': 50, 'fielding': 50},
            ],
            'pitchers': [
                {'pid': 201, 'name': 'Cy Ace', 'hand': 'R/L', 'age': 27, 'control': 75, 'strikeout': 80,
                 'stamina': 70, 'fielding': 40},
            ],
        },
    }
    base.update(over)
    return base


@pytest.fixture
def scouted(seeded):
    """seeded, plus scouting reports for Ash (tid 1) and Birch (tid 2)."""
    write(seeded.root / '30L1998' / 'scout' / '2.json', scout_file(2, 'Birch Blue'))
    write(seeded.root / '30L1998' / 'scout' / '1.json', scout_file(1, 'Ash Gold'))
    return seeded


def test_team_page_has_the_story_layout_and_the_roster_tables(scouted):
    status, headers, body = scouted.get('/news/30L1998/team/1')
    html = body.decode()
    assert status == 200 and headers['content-type'] == HTML
    assert '<title>Scouting the Ash Gold</title>' in html
    assert ('<p class="nav"><a href="/news/30L1998/">&larr; 1998 Major Leagues</a> &middot; '
            '<a href="/news/">All leagues</a></p>') in html
    assert '<h1>Scouting the Ash Gold</h1>' in html
    assert '<p class="dateline">Scouting report</p><p class="byline">Wire report</p>' in html
    assert '<p>Ann Hart grades 80 for contact.</p><p>Bo Lee grades 70 for control.</p>' in html
    assert html.index('<caption>Hitters</caption>') < html.index('<caption>Pitchers</caption>')
    assert ('<th class="t">Player</th><th class="t">Pos</th><th class="t">B/T</th><th>Age</th><th>Contact</th>'
            '<th>Power</th><th>Speed</th><th>Field</th>') in html
    assert ('<tr><td class="t">Ann Hart</td><td class="t">CF</td><td class="t">L/L</td><td>32</td><td>80</td>'
            '<td>50</td><td>80</td><td>60</td></tr>') in html
    assert ('<tr><td class="t">Bo Lee</td><td class="t">C</td><td class="t">R/R</td><td></td><td>50</td><td>50</td>'
            '<td>50</td><td>50</td></tr>') in html
    assert ('<th class="t">Player</th><th class="t">B/T</th><th>Age</th><th>Control</th><th>Strikeout</th>'
            '<th>Stamina</th><th>Field</th>') in html
    assert ('<tr><td class="t">Cy Ace</td><td class="t">R/L</td><td>27</td><td>75</td><td>80</td><td>70</td>'
            '<td>40</td></tr>') in html


def test_team_page_escapes_every_value(site):
    seed(site.root)
    rec = scout_file(3, '<b>Cut & Run</b>', headline='<i>Hi</i>')
    rec['roster']['hitters'][0]['name'] = '<img src=x onerror=1>'
    rec['roster']['hitters'][0]['pos'] = '"C"'
    write(site.root / '30L1998' / 'scout' / '3.json', rec)
    html = site.get('/news/30L1998/team/3')[2].decode()
    assert '<b>' not in html and '<i>' not in html and '<img' not in html
    assert '<title>&lt;i&gt;Hi&lt;/i&gt;</title>' in html
    assert '&lt;img src=x onerror=1&gt;' in html and '&quot;C&quot;' in html
    league_html = site.get('/news/30L1998/')[2].decode()
    assert '<a href="/news/30L1998/team/3">&lt;b&gt;Cut &amp; Run&lt;/b&gt;</a>' in league_html


@pytest.mark.parametrize('path', [
    '/news/30L1998/team/0', '/news/30L1998/team/3', '/news/30L1998/team/01', '/news/30L1998/team/100',
    '/news/30L1998/team/1x', '/news/30L1998/team/', '/news/30L1998/team/1/', '/news/30L1998/team/1/x',
    '/news/30L1998/team', '/news/MLBPA97/team/1',
])
def test_bad_team_paths_are_404(scouted, path):
    status, headers, body = scouted.get(path)
    assert status == 404 and b'Not found' in body
    assert_secure(headers, body)


@pytest.mark.parametrize('content', [
    '{"kind": ',                                                            # corrupt
    [scout_file(4, 'Dogwood')],                                             # not an object
    dict(scout_file(4, 'Dogwood'), kind='preview'),                         # another kind
    {k: v for k, v in scout_file(4, 'Dogwood').items() if k != 'kind'},     # no kind
])
def test_unreadable_or_other_kind_report_is_404(scouted, content):
    write(scouted.root / '30L1998' / 'scout' / '4.json', content)
    status, headers, body = scouted.get('/news/30L1998/team/4')
    assert status == 404
    assert_secure(headers, body)


def test_team_pages_carry_the_security_headers(scouted):
    status, headers, body = scouted.get('/news/30L1998/team/1')
    assert status == 200
    assert_secure(headers, body)


def test_league_page_links_each_report_by_team_name_then_tid(scouted):
    write(scouted.root / '30L1998' / 'scout' / '5.json', scout_file(5, 'Ash Gold'))
    write(scouted.root / '30L1998' / 'scout' / '3.json', scout_file(3, 'Zebra'))
    write(scouted.root / '30L1998' / 'scout' / '9.json', dict(scout_file(9, 'Alpha'), kind='preview'))
    write(scouted.root / '30L1998' / 'scout' / '8.json', '{"kind": ')
    write(scouted.root / '30L1998' / 'scout' / '100.json', scout_file(100, 'Beta'))
    html = scouted.get('/news/30L1998/')[2].decode()
    assert re.findall(r'href="/news/30L1998/team/(\d+)">([^<]*)</a>', html) == [
        ('1', 'Ash Gold'), ('5', 'Ash Gold'), ('2', 'Birch Blue'), ('3', 'Zebra')]


def test_scouting_box_is_above_the_standings_and_below_the_season_box(scouted):
    write(scouted.root / '30L1998' / 'preview.json', preview_file())
    html = scouted.get('/news/30L1998/')[2].decode()
    assert ('<aside class="side"><section class="season">' in html
            and html.index('class="season"') < html.index('class="scouting"')
            < html.index('<caption>American League East</caption>'))
    assert ('<section class="scouting"><h2>Scouting reports</h2><ul>'
            '<li><a href="/news/30L1998/team/1">Ash Gold</a></li>'
            '<li><a href="/news/30L1998/team/2">Birch Blue</a></li>'
            '</ul></section>') in html


def test_no_scouting_box_without_a_readable_report(seeded):
    html = seeded.get('/news/30L1998/')[2].decode()
    assert 'class="scouting"' not in html and 'Scouting reports' not in html


def test_scouting_box_is_on_the_first_page_only(scouted):
    for i in range(31):
        write(scouted.root / '30L1998' / 'recaps' / ('%016x.json' % i), story('%016x' % i, slot=i))
    html1 = scouted.get('/news/30L1998/')[2].decode()
    html2 = scouted.get('/news/30L1998/?page=2')[2].decode()
    assert 'class="scouting"' in html1 and 'class="scouting"' not in html2


def move(kind, pid, name, pos='SS', age=27, frm='Free agents', to='Boston Red Sox', date='June 3', year=1998,
         note=None, **extra):
    """A transaction log event in the shape the watcher writes."""
    ev = {'kind': kind, 'pid': pid, 'name': name, 'pos': pos, 'age': age, 'from': frm, 'to': to, 'date': date,
          'year': year}
    if note is not None:
        ev['note'] = note
    ev.update(extra)
    return ev


def move_note(event, headline='Ann Bat reached 500 career home runs', body='Ann Bat is with Boston.',
              source='template', **over):
    """A notes/<n>.json in the shape the watcher writes."""
    base = {
        'kind': 'move', 'headline': headline, 'body': body, 'source': source, 'event': event,
        'facts': {'association': '1998 Major Leagues', 'date': event.get('date', '')}, 'created': '2026-10-09T14:03:11',
    }
    if source == 'template':
        base['reason'] = 'off'
    base.update(over)
    return base


def replay_file(**over):
    """A replay.json in the shape the watcher writes: an American League with three matched teams, a National League
    with no matched team, and one filler team with no real counterpart."""
    base = {
        'kind': 'replay', 'year': 1998, 'created': '2026-10-09T14:03:11', 'played': 81.0, 'scheduled': 162.0,
        'teams': [
            {'name': 'New York Yankees', 'lg': 'AL', 'real': {'w': 114, 'l': 48, 'pct': 0.704},
             'sim': {'w': 47, 'l': 34, 'pct': 0.58}, 'diff': -0.124, 'wins_diff': -20.1},
            {'name': 'Boston Red Sox', 'lg': 'AL', 'real': {'w': 86, 'l': 76, 'pct': 0.531},
             'sim': {'w': 40, 'l': 41, 'pct': 0.494}, 'diff': -0.037, 'wins_diff': -6.0},
            {'name': 'Seattle Mariners', 'lg': 'AL', 'real': {'w': 84, 'l': 78, 'pct': 0.519},
             'sim': {'w': 45, 'l': 36, 'pct': 0.556}, 'diff': 0.037, 'wins_diff': 6.0},
        ],
        'unmatched': ['Filler Team 1'],
        'leagues': {
            'AL': {'rank_corr': 0.9, 'mean_abs_diff': 0.021, 'real_best': 'New York Yankees',
                   'sim_best': 'New York Yankees'},
            'NL': {'rank_corr': None, 'mean_abs_diff': None, 'real_best': None, 'sim_best': None},
        },
        'leaders': {stat: {'real': [], 'sim': []} for stat in ('HR', 'AVG', 'RBI', 'SB', 'W', 'SV', 'SO', 'ERA')},
        'players': [{'stat': 'HR', 'name': 'Mark McGwire', 'real': 70, 'sim': 12}],
    }
    base['leaders'].update({
        'HR': {'real': [['Mark McGwire', 70], ['Sammy Sosa', 66]], 'sim': [['Ken Griffey', 56]]},
        'AVG': {'real': [['Tony Gwynn', 0.39]], 'sim': [['Larry Walker', 0.412]]},
        'ERA': {'real': [['Roger Clemens', 2.65]], 'sim': [['Ned Ace', 3.1]]},
    })
    base.update(over)
    return base


def moves_log(root, events):
    write(root / '30L1998' / 'moves' / 'log.json', {'events': events, 'count': len(events)})


MILESTONE = dict(stat='career hr', value=500, total=500, **{'from': '', 'to': 'Boston Red Sox'})


def test_transactions_list_each_day_newest_first_in_plain_words(seeded):
    moves_log(seeded.root, [
        move('signed', 300, 'Pat Smith', date='June 3'),
        move('milestone', 400, 'Ann Bat', pos='1B', age=32, date='June 4', **MILESTONE),
        move('retired', 101, 'Joe Old', pos='P', age=38, frm='Ash', to='', date='Offseason'),
    ])
    status, headers, body = seeded.get('/news/30L1998/moves')
    html = body.decode()
    assert status == 200 and headers['content-type'] == HTML
    assert '<title>1998 Major Leagues · Transactions</title>' in html
    assert html.index('<h2>Offseason before 1998</h2>') < html.index('<h2>June 4, 1998</h2>') < html.index(
        '<h2>June 3, 1998</h2>')
    assert '<li>Signed: Pat Smith (SS, 27), Free agents to Boston Red Sox</li>' in html
    assert '<li>Milestone: Ann Bat (Boston Red Sox) reached 500 career home runs</li>' in html
    assert '<li>Retired: Joe Old (P, 38)</li>' in html
    assert '<a href="/news/30L1998/">&larr; 1998 Major Leagues</a>' in html
    assert_secure(headers, body)


def test_an_offseason_day_is_headed_by_the_season_it_leads_into(seeded):
    moves_log(seeded.root, [move('retired', 101, 'Joe Old', pos='P', age=38, frm='Ash', to='', date='Offseason',
                                 year=2008)])
    html = seeded.get('/news/30L1998/moves')[2].decode()
    assert '<h2>Offseason before 2008</h2>' in html and 'Offseason, 2008' not in html
    moves_log(seeded.root, [move('retired', 101, 'Joe Old', pos='P', age=38, frm='Ash', to='', date='Offseason',
                                 year=None)])
    assert '<h2>Offseason</h2>' in seeded.get('/news/30L1998/moves')[2].decode()


def test_a_note_dated_in_the_offseason_says_so_on_its_dateline(seeded):
    write(seeded.root / '30L1998' / 'moves' / 'notes' / '4.json', move_note(
        move('signed', 300, 'Pat Smith', date='Offseason', year=2008)))
    html = seeded.get('/news/30L1998/moves/4')[2].decode()
    assert '<p class="dateline">Offseason before 2008</p>' in html


def test_transaction_lines_escape_every_value(seeded):
    moves_log(seeded.root, [move('signed', 300, '<img src=x onerror=1> & "Bo"', to='Ash & <i>Co</i>')])
    html = seeded.get('/news/30L1998/moves')[2].decode()
    assert '<img' not in html and '<i>' not in html
    assert ('Signed: &lt;img src=x onerror=1&gt; &amp; &quot;Bo&quot; (SS, 27), Free agents to Ash &amp; '
            '&lt;i&gt;Co&lt;/i&gt;') in html


def test_transactions_are_paged_thirty_dates_a_page(seeded):
    moves_log(seeded.root, [move('retired', 500 + i, 'Old %d' % i, date='April %d' % i) for i in range(1, 32)])
    html1 = seeded.get('/news/30L1998/moves')[2].decode()
    html2 = seeded.get('/news/30L1998/moves?page=2')[2].decode()
    assert html1.count('<h2>') == 30 and html2.count('<h2>') == 1
    assert 'April 31, 1998' in html1 and 'April 1, 1998' not in html1
    assert 'April 1, 1998' in html2 and 'April 31, 1998' not in html2
    assert 'href="/news/30L1998/moves?page=2"' in html1 and 'Older dates' in html1 and 'Older dates' not in html2
    assert 'href="/news/30L1998/moves"' in html2 and 'Newer dates' in html2 and 'Newer dates' not in html1


def test_transactions_without_events_or_with_only_unnamed_kinds_say_so(seeded):
    assert 'No transactions yet.' in seeded.get('/news/30L1998/moves')[2].decode()
    moves_log(seeded.root, [move('mystery', 300, 'Pat Smith')])
    html = seeded.get('/news/30L1998/moves')[2].decode()
    assert 'No transactions yet.' in html and 'Pat Smith' not in html


def test_transactions_page_needs_the_association(seeded):
    assert seeded.get('/news/NOPE/moves')[0] == 404
    assert seeded.get('/news/30L1998/moves/')[0] == 404
    assert seeded.get('/news/30L1998/moves?page=2&x=1')[0] == 200


def test_a_line_with_a_note_links_to_it_and_one_without_does_not(seeded):
    moves_log(seeded.root, [move('milestone', 400, 'Ann Bat', date='June 4', note=4, **MILESTONE),
                            move('retired', 101, 'Joe Old', pos='P', age=38, frm='Ash', to='', note=5)])
    write(seeded.root / '30L1998' / 'moves' / 'notes' / '4.json', move_note(move('milestone', 400, 'Ann Bat')))
    html = seeded.get('/news/30L1998/moves')[2].decode()
    assert ('<li><a href="/news/30L1998/moves/4">Milestone: Ann Bat (Boston Red Sox) reached 500 career home runs'
            '</a></li>') in html
    assert '<li>Retired: Joe Old (P, 38)</li>' in html and 'moves/5' not in html


def test_note_page_is_the_story_layout_with_the_byline_and_the_escaped_text(seeded):
    write(seeded.root / '30L1998' / 'moves' / 'notes' / '4.json', move_note(
        move('milestone', 400, 'Ann Bat', pos='1B', age=32, date='June 4', year=1998, **MILESTONE),
        headline='<b>Ann Bat</b> reaches 500', body='Ann Bat is with Boston.\nHe hit it & ran.', source='glm'))
    status, headers, body = seeded.get('/news/30L1998/moves/4')
    html = body.decode()
    assert status == 200 and headers['content-type'] == HTML
    assert '<title>&lt;b&gt;Ann Bat&lt;/b&gt; reaches 500</title>' in html
    assert '<h1>&lt;b&gt;Ann Bat&lt;/b&gt; reaches 500</h1>' in html
    assert '<p class="dateline">June 4 · 1998</p><p class="byline">Staff writer</p>' in html
    assert '<p>Ann Bat is with Boston.</p><p>He hit it &amp; ran.</p>' in html
    assert ('<p class="nav"><a href="/news/30L1998/">&larr; 1998 Major Leagues</a> &middot; '
            '<a href="/news/">All leagues</a></p>') in html
    assert_secure(headers, body)


@pytest.mark.parametrize('path', ['/news/30L1998/moves/abc', '/news/30L1998/moves/1234567', '/news/30L1998/moves/9',
                                  '/news/30L1998/moves/7', '/news/30L1998/moves/8', '/news/30L1998/moves/4/',
                                  '/news/30L1998/moves/-1', '/news/30L1998/moves/4.json'])
def test_bad_or_missing_or_unreadable_note_is_404(seeded, path):
    write(seeded.root / '30L1998' / 'moves' / 'notes' / '4.json', move_note(move('signed', 300, 'Pat Smith')))
    write(seeded.root / '30L1998' / 'moves' / 'notes' / '7.json', '{"kind": ')
    write(seeded.root / '30L1998' / 'moves' / 'notes' / '8.json', dict(move_note(move('signed', 300, 'Pat')),
                                                                       kind='recap'))
    status, headers, body = seeded.get(path)
    assert status == 404
    assert_secure(headers, body)


def test_side_box_shows_the_five_newest_lines_and_only_with_events(seeded):
    assert 'class="transactions"' not in seeded.get('/news/30L1998/')[2].decode()
    moves_log(seeded.root, [])
    assert 'class="transactions"' not in seeded.get('/news/30L1998/')[2].decode()
    moves_log(seeded.root, [move('retired', 100 + i, 'Player %d' % i, pos='P', age=None, frm='Ash', to='')
                            for i in range(1, 8)])
    html = seeded.get('/news/30L1998/')[2].decode()
    assert ('<section class="transactions"><h2>Transactions</h2><ul class="moves">') in html
    assert html.index('Retired: Player 7') < html.index('Retired: Player 3')
    assert 'Retired: Player 2' not in html and 'Retired: Player 1' not in html
    assert '<a href="/news/30L1998/moves">All transactions</a>' in html
    assert html.index('class="transactions"') < html.index('<caption>American League East</caption>')


def test_side_box_is_on_the_first_page_only(seeded):
    moves_log(seeded.root, [move('signed', 300, 'Pat Smith')])
    for i in range(31):
        write(seeded.root / '30L1998' / 'recaps' / ('%016x.json' % i), story('%016x' % i, slot=i))
    assert 'class="transactions"' in seeded.get('/news/30L1998/')[2].decode()
    assert 'class="transactions"' not in seeded.get('/news/30L1998/?page=2')[2].decode()


@pytest.fixture
def scorecard(seeded):
    """seeded, plus the replay scorecard for 30L1998."""
    write(seeded.root / '30L1998' / 'replay.json', replay_file())
    return seeded


def test_replay_page_has_status_standings_leaders_and_the_real_leaders_in_the_sim(scorecard):
    status, headers, body = scorecard.get('/news/30L1998/replay')
    html = body.decode()
    assert status == 200 and headers['content-type'] == HTML
    assert '<title>1998 Major Leagues · Replay vs history</title>' in html
    assert ('<p class="nav"><a href="/news/30L1998/">&larr; 1998 Major Leagues</a> &middot; '
            '<a href="/news/">All leagues</a></p>') in html
    assert '<h1>Replay vs history</h1><p class="through">After 81 of 162 games per team</p>' in html
    assert ('<section><h2>AL</h2><p>Rank correlation with the real standings: 0.90. Mean gap in winning percentage: '
            '.021. Best real record: New York Yankees, 114-48. Best sim record: New York Yankees, 47-34.</p>') in html
    assert ('<th class="t">Team</th><th>Real W-L</th><th>Real Pct</th><th>Sim W-L</th><th>Sim Pct</th><th>Gap</th>'
            in html)
    assert ('<tr><td class="t">New York Yankees</td><td>114-48</td><td>.704</td><td>47-34</td><td>.580</td>'
            '<td>-20.1</td></tr>') in html
    assert ('<tr><td class="t">Seattle Mariners</td><td>84-78</td><td>.519</td><td>45-36</td><td>.556</td>'
            '<td>+6.0</td></tr>') in html
    assert '<p class="empty">No real counterpart: Filler Team 1.</p>' in html
    assert '<section><h2>NL</h2><p>Rank correlation with the real standings: n/a.</p></section>' in html
    assert '<caption>HR</caption>' in html and '<caption>AVG</caption>' in html
    assert ('<tr><td>1</td><td class="t">Mark McGwire</td><td>70</td><td class="t">Ken Griffey</td><td>56</td></tr>'
            in html)
    assert ('<tr><td>1</td><td class="t">Tony Gwynn</td><td>.390</td><td class="t">Larry Walker</td>'
            '<td>.412</td></tr>') in html
    assert ('<tr><td>1</td><td class="t">Roger Clemens</td><td>2.65</td><td class="t">Ned Ace</td>'
            '<td>3.10</td></tr>') in html
    assert '<caption>Players</caption>' in html
    assert '<tr><td class="t">HR</td><td class="t">Mark McGwire</td><td>70</td><td>12</td></tr>' in html


def test_replay_page_escapes_every_value(scorecard):
    team = dict(replay_file()['teams'][0], name='<b>Evil</b>')
    write(scorecard.root / '30L1998' / 'replay.json', replay_file(teams=[team], unmatched=['<i>Filler</i>']))
    html = scorecard.get('/news/30L1998/replay')[2].decode()
    assert '<b>Evil</b>' not in html and '<i>Filler</i>' not in html
    assert '&lt;b&gt;Evil&lt;/b&gt;' in html and '&lt;i&gt;Filler&lt;/i&gt;' in html


def test_replay_page_without_teams_or_leaders_says_so(seeded):
    write(seeded.root / '30L1998' / 'replay.json', replay_file(teams=[], leagues={}, leaders={}, players=[]))
    html = seeded.get('/news/30L1998/replay')[2].decode()
    assert '<p class="empty">No leaders yet.</p>' in html
    assert '<p class="empty">No real leaders in the sim yet.</p>' in html


@pytest.mark.parametrize('content', [None, 'not json', '[1, 2]', {'kind': 'awards'}, {'year': 1998}])
def test_replay_page_is_404_without_a_readable_replay_file_of_its_kind(seeded, content):
    if content is not None:
        write(seeded.root / '30L1998' / 'replay.json', content)
    status, headers, body = seeded.get('/news/30L1998/replay')
    assert status == 404
    assert headers['content-type'] == HTML


def test_replay_box_is_on_the_association_page_only_with_the_file(seeded):
    assert 'class="replay"' not in seeded.get('/news/30L1998/')[2].decode()
    write(seeded.root / '30L1998' / 'replay.json', replay_file())
    html = seeded.get('/news/30L1998/')[2].decode()
    assert ('<section class="replay"><h2>Replay vs history</h2><ul><li><a href="/news/30L1998/replay">Scorecard</a>'
            '</li></ul></section>') in html
