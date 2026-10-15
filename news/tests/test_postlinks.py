"""The postseason page's Game column links to a game's story when the season folder has one: the story's post names
the same round and 0-based game and its facts name the same sides and score."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server   # noqa: E402

KEY1 = '000000000000aa01'
KEY2 = '000000000000aa02'


def game(away, home, away_runs, home_runs):
    return {'away': away, 'home': home, 'away_runs': away_runs, 'home_runs': home_runs}


def done_rec(key, rnd, n, away, home, away_runs, home_runs):
    return {'key': key, 'month': 10, 'day': 3, 'slot': 0, 'headline': 'Story %s' % key, 'body': '',
            'source': 'glm',
            'facts': {'away': {'name': away, 'runs': away_runs}, 'home': {'name': home, 'runs': home_runs}},
            'post': {'round': rnd, 'series': 0, 'game': n}, 'created': '2026-10-09T14:03:11'}


def piece(rounds):
    return {'kind': 'postseason', 'headline': '1998 postseason', 'body': 'B',
            'facts': {'season': 1998, 'complete': False, 'champion': None, 'rounds': rounds}, 'created': 'x'}


def rnd(name, series):
    return {'round': 1, 'name': name, 'series': series}


def ser(away, home, games):
    return {'teams': [away, home], 'wins': [0, 0], 'best_of': 5, 'winner': None, 'games': list(games)}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding='utf-8')


@pytest.fixture
def root(tmp_path):
    write(tmp_path / 'A' / 'meta.json', {'assn': 'A', 'name': '1998 Test', 'updated': '2026-10-09T14:03:11',
                                         'last_day': None, 'standings': [], 'leaders': {}})
    return tmp_path


def html_of(root, target):
    status, ctype, body, _ = server.route(root, target)
    return status, body.decode()


def recap(root, key, rec, past=None):
    folder = root / 'A' if past is None else root / 'A' / 'past' / past
    write(folder / 'recaps' / (key + '.json'), rec)


def one_rec(root, key=KEY1, **kw):
    round_ = kw.pop('post_round', 1)
    n = kw.pop('post_game', 0)
    recap(root, key, done_rec(key, round_, n, kw.pop('away', 'Ash'), kw.pop('home', 'Birch'),
                              kw.pop('away_runs', 1), kw.pop('home_runs', 4)), **kw)


def bracket_one_game():
    return piece([rnd('Division Series', [ser('Ash', 'Birch', [game('Ash', 'Birch', 1, 4)])])])


def test_a_matching_recap_links_that_row_only(root):
    write(root / 'A' / 'postseason.json', bracket_one_game())
    html = html_of(root, '/news/A/postseason')[1]
    assert '<tr><td>1</td><td class="t">Ash</td><td>1</td><td class="t">Birch</td><td>4</td></tr>' in html
    one_rec(root)
    html = html_of(root, '/news/A/postseason')[1]
    assert '<tr><td><a href="/news/A/%s">1</a></td><td class="t">Ash</td><td>1</td>' \
           '<td class="t">Birch</td><td>4</td></tr>' % KEY1 in html


def test_a_past_season_links_under_its_own_prefix(root):
    write(root / 'A' / 'past' / '1997' / 'meta.json', {'assn': 'A', 'name': '1997 Test', 'standings': [],
                                                       'leaders': {}, 'season_year': 1997})
    write(root / 'A' / 'past' / '1997' / 'postseason.json', bracket_one_game())
    recap(root, KEY1, done_rec(KEY1, 1, 0, 'Ash', 'Birch', 1, 4), past='1997')
    html = html_of(root, '/news/A/past/1997/postseason')[1]
    assert '<a href="/news/A/past/1997/%s">1</a>' % KEY1 in html
    assert '<a href="/news/A/%s' % KEY1 not in html


@pytest.mark.parametrize('rec', [
    done_rec(KEY1, 2, 0, 'Ash', 'Birch', 1, 4),            # wrong round
    done_rec(KEY1, 1, 1, 'Ash', 'Birch', 1, 4),            # wrong game index
    done_rec(KEY1, 1, 0, 'Ash', 'Birch', 4, 1),            # wrong score
    done_rec(KEY1, 1, 0, 'Birch', 'Ash', 1, 4),            # swapped sides
    done_rec(KEY1, 1, 0, 'Ash', 'Birch', 1, 4) | {'post': None},
    done_rec(KEY1, 1, 0, 'Ash', 'Birch', 1, 4) | {'post': 'game 1'},
    done_rec(KEY1, 1, 0, 'Ash', 'Birch', 1, 4) | {'facts': {'away': {'name': 'Ash'}}},
])
def test_a_recap_that_does_not_match_links_nothing(root, rec):
    write(root / 'A' / 'postseason.json', bracket_one_game())
    recap(root, KEY1, rec)
    assert status_matches(root)


def status_matches(root):
    status, html = html_of(root, '/news/A/postseason')
    assert status == 200
    assert '<a href="/news/A/%s' % KEY1 not in html
    assert '<tr><td>1</td><td class="t">Ash</td><td>1</td><td class="t">Birch</td><td>4</td></tr>' in html
    return status


def test_a_recap_with_no_post_links_nothing(root):
    write(root / 'A' / 'postseason.json', bracket_one_game())
    recap(root, KEY1, {'headline': 'H', 'facts': {'away': {'name': 'Ash', 'runs': 1},
                                                  'home': {'name': 'Birch', 'runs': 4}}})
    status_matches(root)


def test_two_series_each_link_their_own_story(root):
    two = piece([rnd('Division Series', [ser('Ash', 'Birch', [game('Ash', 'Birch', 1, 4)]),
                                         ser('Cedar', 'Dogwood', [game('Cedar', 'Dogwood', 2, 3)])])])
    write(root / 'A' / 'postseason.json', two)
    recap(root, KEY1, done_rec(KEY1, 1, 0, 'Ash', 'Birch', 1, 4))
    recap(root, KEY2, done_rec(KEY2, 1, 0, 'Cedar', 'Dogwood', 2, 3))
    html = html_of(root, '/news/A/postseason')[1]
    assert '<a href="/news/A/%s">1</a>' % KEY1 in html and '<a href="/news/A/%s">1</a>' % KEY2 in html


def test_two_identical_rows_one_recap_links_only_the_first(root):
    two = piece([rnd('Division Series', [ser('Ash', 'Birch', [game('Ash', 'Birch', 1, 4),
                                                              game('Ash', 'Birch', 1, 4)])])])
    write(root / 'A' / 'postseason.json', two)
    recap(root, KEY1, done_rec(KEY1, 1, 0, 'Ash', 'Birch', 1, 4))
    html = html_of(root, '/news/A/postseason')[1]
    assert html.count('<a href="/news/A/%s">' % KEY1) == 1


def test_no_recaps_folder_is_the_page_without_links(root):
    write(root / 'A' / 'postseason.json', bracket_one_game())
    status, html = html_of(root, '/news/A/postseason')
    assert status == 200 and '<tr><td>1</td><td class="t">Ash</td><td>1</td>' \
           '<td class="t">Birch</td><td>4</td></tr>' in html
    assert '<a href="/news/A/' + 16 * '0' not in html
