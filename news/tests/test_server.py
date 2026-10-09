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
