"""The League box: Watcher.league() (cached on the files' stats), meta.json's 'league' key and the front pages."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import server    # noqa: E402
import watch     # noqa: E402

TEAMS = {1: {'tid': 1, 'name': 'Ash', 'abbrev': 'ASH', 'city': 'X', 'stadium': 'Ash Park', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [100]}}
DEMOG = {'year': 1998, 'rostered': 1283, 'mean_age': 28.5, 'le25': 290, 'ge33': 174, 'hist': {27: 3}, 'fa': 312,
         'fa_mean_age': 30.1, 'retired': 40, 'players': 1635, 'roster_min': 20, 'pitchers_min': 9}
LEAGUE = {'year': 1998, 'rostered': 1283, 'mean_age': 28.5, 'le25': 290, 'ge33': 174, 'fa': 312}


@pytest.fixture
def lg(tmp_path, monkeypatch):
    """A Watcher over a game dir holding an ASN and a PYR, and demographics() replaced by a counting stub."""
    gd = tmp_path / 'game'
    (gd / 'Assn').mkdir(parents=True)
    asn, pyr = gd / 'Assn' / '30L1998.ASN', gd / 'Assn' / '30L1998.PYR'
    asn.write_bytes(b'asn')
    pyr.write_bytes(b'pyr')
    st = {'calls': [], 'raise': None}

    def demographics(asn_path, pyr_path, pyf_path, year):
        st['calls'].append((asn_path, pyr_path, pyf_path, year))
        if st['raise']:
            raise st['raise']
        return dict(DEMOG, year=year)

    monkeypatch.setattr(gamedata, 'demographics', demographics)
    w = watch.Watcher(str(gd), str(tmp_path / 'data'), None, None, log=lambda s: None)
    st.update(w=w, asn=asn, pyr=pyr, gd=gd)
    return st


def ask(st, year=1998, pyr=True):
    return st['w'].league('30L1998', str(st['asn']), str(st['pyr']) if pyr else None, year)


def touch(path, ns=5_000_000_000):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + ns))


def test_league_has_the_six_keys_and_reads_once(lg):
    assert ask(lg) == LEAGUE
    assert ask(lg) == LEAGUE
    assert lg['calls'] == [(str(lg['asn']), str(lg['pyr']), None, 1998)]


def test_league_reads_again_when_a_file_or_the_year_changes(lg):
    ask(lg)
    touch(lg['asn'])
    ask(lg)
    assert len(lg['calls']) == 2
    lg['pyr'].write_bytes(b'longer pyr')
    ask(lg)
    assert len(lg['calls']) == 3
    assert ask(lg, year=1999)['year'] == 1999 and len(lg['calls']) == 4


def test_league_error_gives_none_and_is_not_retried(lg):
    import struct
    for err in (OSError('gone'), ValueError('bad'), struct.error('torn'), KeyError('po'), IndexError('rec')):
        lg['w'].league_cache.clear()
        lg['calls'].clear()
        lg['raise'] = err
        assert ask(lg) is None and ask(lg) is None and ask(lg) is None
        assert len(lg['calls']) == 1
    touch(lg['pyr'])                    # a changed file is tried again, and recovers
    lg['raise'] = None
    assert ask(lg) == LEAGUE


def test_league_without_a_pyr_or_a_year_is_none(lg):
    assert ask(lg, pyr=False) is None
    assert ask(lg, year=None) is None
    assert lg['calls'] == []


def test_league_stat_error_is_none_and_not_cached(lg):
    lg['pyr'].unlink()
    assert ask(lg) is None and lg['calls'] == [] and lg['w'].league_cache == {}
    lg['pyr'].write_bytes(b'pyr')
    assert ask(lg) == LEAGUE


def test_league_pyf_joins_the_key(lg):
    ask(lg)
    pyf = lg['gd'] / 'Assn' / '30L1998.pyf'
    pyf.write_bytes(b'pyf')
    ask(lg)
    assert len(lg['calls']) == 2 and lg['calls'][1][2] == str(pyf)      # found case-insensitively and passed on
    ask(lg)
    touch(pyf)
    ask(lg)
    assert len(lg['calls']) == 3
    pyf.unlink()
    ask(lg)
    assert len(lg['calls']) == 4 and lg['calls'][3][2] is None


def test_association_writes_meta_league(lg, monkeypatch):
    gd = lg['gd']
    (gd / 'Stats').mkdir()
    monkeypatch.setattr(gamedata, 'association', lambda path: {'name': '1998 Test', 'teams': TEAMS, 'games': [],
                                                              'season_year': 1998})
    monkeypatch.setattr(gamedata, 'names', lambda path: {})
    lg['w'].scan()
    meta = json.loads(open(os.path.join(lg['w'].data, '30L1998', 'meta.json'), encoding='utf-8').read())
    assert meta['league'] == LEAGUE
    assert len(lg['calls']) == 1


# server

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding='utf-8')


def front(root, target='/news/30L1998/', **over):
    meta = {'assn': '30L1998', 'name': '1998 Major Leagues', 'last_day': [4, 15], 'standings': [
        {'league': 'American League', 'division': 'East', 'teams': [
            {'tid': 1, 'name': 'Ash', 'abbrev': 'ASH', 'w': 1, 'l': 0, 'pct': '1.000', 'gb': '-'}]}],
        'leaders': {}, 'league': LEAGUE}
    meta.update(over)
    for k in [k for k, v in over.items() if v is KeyError]:
        del meta[k]
    write(root / '30L1998' / 'meta.json', meta)
    status, _, body, _ = server.route(root, target)
    assert status == 200
    return body.decode()


def test_front_page_shows_the_league_box_before_the_standings(tmp_path):
    html = front(tmp_path)
    assert '<h2>League</h2>' in html
    assert '1,283 players on rosters, mean age 28.5.' in html
    assert '290 aged 25 or under, 174 aged 33 or over. 312 free agents.' in html
    assert html.index('class="league"') < html.index('<caption>American League East</caption>')


def test_page_two_has_no_league_box(tmp_path):
    story = {'key': 'k', 'assn': '30L1998', 'month': 4, 'day': 1, 'slot': 0, 'headline': 'H', 'body': 'B'}
    for i in range(server.PER_PAGE + 1):
        write(tmp_path / '30L1998' / 'recaps' / ('%016x.json' % i), dict(story, key='%016x' % i))
    assert 'class="league"' in front(tmp_path)
    assert 'class="league"' not in front(tmp_path, '/news/30L1998/?page=2')


@pytest.mark.parametrize('league', [
    KeyError, None, 'text', [1283], {}, dict(LEAGUE, rostered=0), dict(LEAGUE, rostered='1283'),
    dict(LEAGUE, rostered=True), dict(LEAGUE, rostered=-4), dict(LEAGUE, mean_age='28'), dict(LEAGUE, mean_age=None),
    dict(LEAGUE, mean_age=True), dict(LEAGUE, mean_age=float('nan')), dict(LEAGUE, mean_age=float('inf')),
    dict(LEAGUE, mean_age=10 ** 400)])
def test_a_missing_or_unsound_league_shows_no_box(tmp_path, league):
    assert 'class="league"' not in front(tmp_path, league=league)
    assert server._league_html(None if league is KeyError else league) == ''


def test_an_integer_mean_age_shows(tmp_path):
    assert 'mean age 28.0.' in front(tmp_path, league=dict(LEAGUE, mean_age=28))


def test_a_bad_count_shows_as_zero_and_the_text_never_reaches_the_page(tmp_path):
    html = front(tmp_path, league=dict(LEAGUE, fa='<b>many</b>', le25=None, ge33=2.5))
    assert '0 aged 25 or under, 0 aged 33 or over. 0 free agents.' in html
    assert 'many' not in html


def test_a_past_season_shows_its_own_box(tmp_path):
    front(tmp_path)
    write(tmp_path / '30L1998' / 'past' / '1997' / 'meta.json',
          dict(name='1997 Past League', last_day=[9, 28], standings=[], leaders={},
               league=dict(LEAGUE, rostered=1200, mean_age=27.3, le25=300, ge33=150, fa=100)))
    status, _, body, _ = server.route(tmp_path, '/news/30L1998/past/1997/')
    html = body.decode()
    assert status == 200
    assert '1,200 players on rosters, mean age 27.3.' in html
    assert '300 aged 25 or under, 150 aged 33 or over. 100 free agents.' in html
    write(tmp_path / '30L1998' / 'past' / '1996' / 'meta.json', dict(name='1996 Past League', standings=[]))
    assert 'class="league"' not in server.route(tmp_path, '/news/30L1998/past/1996/')[2].decode()
