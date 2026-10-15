"""The postseason page: bracket.facts and template, Watcher.postseason_piece (gamedata.postseason replaced by a dict),
and the pages server.route serves from postseason.json."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bracket   # noqa: E402
import gamedata  # noqa: E402
import server    # noqa: E402
import watch     # noqa: E402

TEAMS = {tid: {'tid': tid, 'name': name, 'abbrev': name[:3].upper(), 'roster': []}
         for tid, name in ((1, 'Ash'), (2, 'Birch'), (3, 'Cedar'), (4, 'Dogwood'))}
ASSOC = {'name': '1998 Test', 'season_year': 1998, 'teams': TEAMS, 'games': []}


def game(away, home, away_runs, home_runs):
    return {'away': away, 'home': home, 'away_runs': away_runs, 'home_runs': home_runs}


def series(t1, t2, wins, games=(), best=5, winner=None):
    return {'best_of': best, 'teams': [t1, t2], 'wins': list(wins), 'winner': winner, 'home': t1, 'games': list(games)}


def bracket_of(*rounds, complete=False, current=True, champion=None):
    return {'complete': complete, 'current': current, 'best_of': [5, 7, 7], 'champion': champion,
            'rounds': [{'round': n, 'series': list(s)} for n, s in enumerate(rounds, 1)]}


def started():
    """Two division series played (1 beat 2, 3 and 4 level), the later rounds not filled yet."""
    return bracket_of(
        [series(1, 2, (3, 1), [game(2, 1, 1, 4), game(2, 1, 2, 3), game(1, 2, 5, 0), game(1, 2, 2, 6),
                               game(2, 1, 0, 1)], winner=1),
         series(3, 4, (1, 1), [game(4, 3, 2, 3), game(4, 3, 4, 1)])],
        [series(1, 0, (0, 0))], [series(0, 0, (0, 0))])


def finished():
    return bracket_of([series(1, 2, (3, 0), [game(2, 1, 0, 1)] * 3, winner=1)],
                      [series(1, 3, (4, 3), [game(3, 1, 0, 1)] * 7, best=7, winner=1)],
                      [series(1, 4, (4, 0), [game(4, 1, 0, 1)] * 4, best=7, winner=1)],
                      complete=True, champion=1)


# facts and template

def test_facts_name_the_teams_and_survive_a_json_round_trip():
    f = bracket.facts(ASSOC, finished(), 1998)
    assert f['association'] == '1998 Test' and f['season'] == 1998 and f['complete'] is True
    assert f['champion'] == 'Ash'
    assert [(r['round'], r['name']) for r in f['rounds']] == [(1, 'Division Series'), (2, 'League Championship Series'),
                                                            (3, 'World Series')]
    assert f['rounds'][2]['series'][0] == {
        'teams': ['Ash', 'Dogwood'], 'wins': [4, 0], 'best_of': 7, 'winner': 'Ash',
        'games': [{'away': 'Dogwood', 'home': 'Ash', 'away_runs': 0, 'home_runs': 1}] * 4}
    assert json.loads(json.dumps(f)) == f


def test_facts_call_an_unknown_team_by_its_id():
    b = bracket_of([series(1, 99, (0, 1), [game(99, 1, 3, 2)])])
    s = bracket.facts(ASSOC, b, 1998)['rounds'][0]['series'][0]
    assert s['teams'] == ['Ash', 'team 99'] and s['games'][0]['away'] == 'team 99'


def test_facts_drop_a_series_with_an_empty_slot_and_a_round_left_empty():
    f = bracket.facts(ASSOC, started(), 1998)
    assert [r['round'] for r in f['rounds']] == [1]
    assert len(f['rounds'][0]['series']) == 2
    b = bracket_of([series(1, 2, (1, 0), [game(2, 1, 0, 1)]), series(3, None, (0, 0))])
    assert len(bracket.facts(ASSOC, b, 1998)['rounds'][0]['series']) == 1
    assert f['champion'] is None


def test_played_needs_a_game():
    assert bracket.played(bracket.facts(ASSOC, started(), 1998))
    assert not bracket.played(bracket.facts(ASSOC, bracket_of([series(1, 2, (0, 0))]), 1998))
    assert not bracket.played(bracket.facts(ASSOC, bracket_of([series(0, 0, (0, 0))]), 1998))


def test_template_headline_names_the_champion_or_the_season():
    assert bracket.template(bracket.facts(ASSOC, finished(), 1998))['headline'] == 'Ash win the 1998 World Series'
    assert bracket.template(bracket.facts(ASSOC, started(), 1998))['headline'] == '1998 postseason'


def test_template_sentences_by_state():
    b = bracket_of(
        [series(1, 2, (3, 1), [game(2, 1, 1, 4)] * 4, winner=1),
         series(4, 3, (1, 3), [game(3, 4, 1, 0)] * 4, winner=3)],
        [series(1, 3, (2, 1), [game(3, 1, 0, 1)] * 3), series(2, 4, (2, 1), [game(4, 2, 0, 1)] * 3)],
        [series(3, 4, (1, 1), [game(4, 3, 0, 1)] * 2)])
    b['rounds'][1]['series'][1]['teams'] = [4, 2]
    b['rounds'][1]['series'][1]['wins'] = [1, 2]
    b['rounds'].append({'round': 4, 'series': [series(1, 2, (0, 0))]})
    body = bracket.template(bracket.facts(ASSOC, b, 1998))['body']
    assert body.split('\n\n') == [
        'Ash beat Birch 3-1 in the Division Series. Cedar beat Dogwood 3-1 in the Division Series.',
        'Ash leads Cedar 2-1 in the League Championship Series. '
        'Birch leads Dogwood 2-1 in the League Championship Series.',
        'Cedar and Dogwood are tied 1-1 in the World Series.',
        'Ash and Birch meet in the Round 4.']


def test_template_puts_the_winner_first_when_it_is_the_second_team():
    b = bracket_of([series(1, 2, (1, 3), [game(2, 1, 1, 0)] * 4, winner=2)])
    assert bracket.template(bracket.facts(ASSOC, b, 1998))['body'] == 'Birch beat Ash 3-1 in the Division Series.'


# postseason_piece

class Pieces:
    def __init__(self, tmp_path, monkeypatch):
        self.out = str(tmp_path / 'data' / 'A')
        self.logs = []
        self.b = started()
        self.w = watch.Watcher(str(tmp_path / 'game'), str(tmp_path / 'data'), None, None, log=self.logs.append)
        monkeypatch.setattr(gamedata, 'postseason', lambda path: self.step())

    def step(self):
        if isinstance(self.b, Exception):
            raise self.b
        return self.b

    def run(self, year=1998):
        self.w.postseason_piece(self.out, dict(ASSOC, season_year=year), 'x.ASN')

    def path(self, *sub):
        return os.path.join(self.out, *sub, 'postseason.json')

    def read(self, *sub):
        with open(self.path(*sub), encoding='utf-8') as fh:
            return json.load(fh)


@pytest.fixture
def pieces(tmp_path, monkeypatch):
    return Pieces(tmp_path, monkeypatch)


def test_the_current_bracket_is_written_to_the_season_folder(pieces):
    pieces.run()
    rec = pieces.read()
    assert rec['kind'] == 'postseason' and rec['source'] == 'template' and rec['created']
    assert rec['headline'] == '1998 postseason' and rec['body'].startswith('Ash beat Birch 3-1 in the Division Series.')
    assert rec['facts'] == bracket.facts(ASSOC, pieces.b, 1998)
    assert pieces.logs == ['A postseason 1998 (7 games) (template)']


def test_last_seasons_bracket_goes_to_its_past_folder_only_when_that_exists(pieces):
    pieces.b['current'] = False
    pieces.run(1999)
    assert not os.path.exists(os.path.join(pieces.out, 'past')) and not os.path.exists(pieces.path())
    os.makedirs(os.path.join(pieces.out, 'past', '1998-2'))
    pieces.run(1999)
    assert not os.path.exists(pieces.path('past', '1998'))
    os.makedirs(os.path.join(pieces.out, 'past', '1998'))
    pieces.run(1999)
    assert pieces.read('past', '1998')['facts']['season'] == 1998 and not os.path.exists(pieces.path())


@pytest.mark.parametrize('b', [None, OSError('gone'), ValueError('torn'), IndexError('short'),
                               bracket_of([series(1, 2, (0, 0))])])
def test_nothing_is_written_without_a_bracket_or_a_game(pieces, b):
    pieces.b = b
    pieces.run()
    assert not os.path.exists(pieces.out) and pieces.logs == []


def test_nothing_is_written_without_a_season_year(pieces):
    pieces.w.postseason_piece(pieces.out, {k: v for k, v in ASSOC.items() if k != 'season_year'}, 'x.ASN')
    pieces.w.postseason_piece(pieces.out, dict(ASSOC, season_year=True), 'x.ASN')
    assert not os.path.exists(pieces.out)


def test_an_unchanged_bracket_leaves_the_file_alone_and_a_new_game_rewrites_it(pieces):
    pieces.run()
    first = pieces.read()
    first['created'] = '2000-01-01T00:00:00'
    with open(pieces.path(), 'w', encoding='utf-8') as fh:
        json.dump(first, fh)
    pieces.run()
    assert pieces.read()['created'] == '2000-01-01T00:00:00' and len(pieces.logs) == 1
    pieces.b['rounds'][0]['series'][1]['games'].append(game(3, 4, 5, 2))
    pieces.b['rounds'][0]['series'][1]['wins'] = [2, 1]
    pieces.run()
    rec = pieces.read()
    assert rec['created'] != '2000-01-01T00:00:00' and 'Cedar leads Dogwood 2-1' in rec['body']
    assert pieces.logs[-1] == 'A postseason 1998 (8 games) (template)'


def test_the_finished_bracket_names_the_champion(pieces):
    pieces.b = finished()
    pieces.run()
    assert pieces.read()['headline'] == 'Ash win the 1998 World Series'


def test_a_rollover_archives_the_postseason_file_with_the_season(pieces):
    assert watch.SEASON_ENTRIES[-1] == 'postseason.json'
    pieces.run()
    with open(os.path.join(pieces.out, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump({'season_year': 1998}, fh)
    assert pieces.w.rollover('A', pieces.out, dict(ASSOC, season_year=1999)) == '1998'
    assert not os.path.exists(pieces.path()) and pieces.read('past', '1998')['kind'] == 'postseason'
    pieces.b['current'] = False         # the ASN still holds 1998's bracket: the archived file is already current
    created = pieces.read('past', '1998')['created']
    pieces.run(1999)
    assert pieces.read('past', '1998')['created'] == created


def test_a_scan_writes_the_piece_after_the_season_pieces(tmp_path, monkeypatch):
    game_dir = tmp_path / 'game'
    (game_dir / 'Assn').mkdir(parents=True)
    (game_dir / 'Stats').mkdir()
    (game_dir / 'Assn' / '30L1998.ASN').write_bytes(b'asn')
    full = {tid: dict(t, city='X', stadium='Park', manager='M', league='AL', division='East', w=0, l=0)
            for tid, t in TEAMS.items()}
    monkeypatch.setattr(gamedata, 'association', lambda path: dict(ASSOC, teams=full, games=[]))
    monkeypatch.setattr(gamedata, 'names', lambda path: {})
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: {'bat': {}, 'pit': {}})
    monkeypatch.setattr(gamedata, 'postseason', lambda path: started())
    logs = []
    watch.Watcher(str(game_dir), str(tmp_path / 'data'), None, None, log=logs.append).scan()
    assert (tmp_path / 'data' / '30L1998' / 'postseason.json').is_file()
    assert [m for m in logs if 'postseason' in m] == ['30L1998 postseason 1998 (7 games) (template)']


# the pages

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding='utf-8')


def piece(b=None, assoc=ASSOC):
    f = json.loads(json.dumps(bracket.facts(assoc, b or started(), 1998)))
    return dict(bracket.template(f), kind='postseason', source='template', facts=f, created='2026-10-09T14:03:11')


@pytest.fixture
def root(tmp_path):
    write(tmp_path / 'A' / 'meta.json', {'assn': 'A', 'name': '1998 Test', 'updated': '2026-10-09T14:03:11',
                                         'last_day': None, 'standings': [], 'leaders': {}})
    return tmp_path


def html_of(root, target):
    status, ctype, body, _ = server.route(root, target)
    return status, body.decode()


def test_the_page_shows_the_headline_the_rounds_and_the_games(root):
    write(root / 'A' / 'postseason.json', piece())
    status, html = html_of(root, '/news/A/postseason')
    assert status == 200 and '<h1>1998 postseason</h1>' in html and '<p class="dateline">1998 postseason</p>' in html
    assert '<h2>Division Series</h2>' in html and '<h2>League Championship Series</h2>' not in html
    assert '<caption>Ash vs Birch</caption>' in html
    assert ('<tr><td>1</td><td class="t">Birch</td><td>1</td><td class="t">Ash</td><td>4</td></tr>') in html
    assert '<tr><td>2</td><td class="t">Dogwood</td><td>4</td><td class="t">Cedar</td><td>1</td></tr>' in html
    assert '<p>Ash beat Birch 3-1 in the Division Series.' in html


def test_a_series_without_games_is_a_caption_line(root):
    p = piece()
    p['facts']['rounds'][0]['series'].append({'teams': ['Ash', 'Cedar'], 'wins': [0, 0], 'best_of': 5, 'winner': None,
                                              'games': []})
    write(root / 'A' / 'postseason.json', p)
    html = html_of(root, '/news/A/postseason')[1]
    assert '<p>Ash vs Cedar</p>' in html and '<caption>Ash vs Cedar</caption>' not in html


def test_the_front_page_links_the_postseason_first_in_the_season_box(root):
    assert 'Postseason' not in html_of(root, '/news/A/')[1]
    write(root / 'A' / 'postseason.json', piece())
    write(root / 'A' / 'awards.json', {'kind': 'awards', 'headline': 'Awards', 'body': '', 'facts': {}})
    html = html_of(root, '/news/A/')[1]
    assert ('<section class="season"><h2>Season</h2><ul><li><a href="/news/A/postseason">Postseason</a></li>'
            '<li><a href="/news/A/awards">Season awards</a></li>') in html


def test_a_past_season_serves_and_links_its_own_postseason(root):
    write(root / 'A' / 'past' / '1997' / 'meta.json', {'assn': 'A', 'name': '1997 Test', 'standings': [],
                                                       'leaders': {}, 'season_year': 1997})
    write(root / 'A' / 'past' / '1997' / 'postseason.json', piece(finished()))
    status, html = html_of(root, '/news/A/past/1997/postseason')
    assert status == 200 and '<h1>Ash win the 1998 World Series</h1>' in html
    assert '<a href="/news/A/past/1997/">' in html
    assert '<a href="/news/A/past/1997/postseason">Postseason</a>' in html_of(root, '/news/A/past/1997/')[1]
    assert html_of(root, '/news/A/postseason')[0] == 404


@pytest.mark.parametrize('content', [None, {'kind': 'awards', 'headline': 'x', 'facts': {}}, '{"kind": ', '[1]'])
def test_a_missing_or_wrong_file_is_404(root, content):
    if content is not None:
        write(root / 'A' / 'postseason.json', content)
    status, html = html_of(root, '/news/A/postseason')
    assert status == 404 and 'Not found' in html


@pytest.mark.parametrize('facts', [None, 'x', [], {'rounds': 3}, {'rounds': [None, {'series': 5}, {'series': [7]}]},
                                   {'rounds': [{'name': 'R', 'series': [{'teams': 'ab',
                                                                         'games': [1, {'away': None}]}]}]}])
def test_a_thin_or_wrong_typed_file_still_renders(root, facts):
    write(root / 'A' / 'postseason.json', {'kind': 'postseason', 'headline': 'H', 'body': 'B', 'facts': facts})
    assert html_of(root, '/news/A/postseason')[0] == 200


def test_names_from_the_file_are_escaped(root):
    teams = {1: {'name': '<b>Ash</b>', 'abbrev': 'ASH'}, 2: {'name': 'Bi"rch & Co', 'abbrev': 'BIR'}}
    b = bracket_of([series(1, 2, (1, 0), [game(2, 1, 0, 1)])])
    p = piece(b, dict(ASSOC, teams=teams))
    p['headline'] = '<script>alert(1)</script>'
    write(root / 'A' / 'postseason.json', p)
    html = html_of(root, '/news/A/postseason')[1]
    assert '<b>Ash' not in html and '<script>alert' not in html
    assert '&lt;b&gt;Ash&lt;/b&gt; vs Bi&quot;rch &amp; Co' in html
