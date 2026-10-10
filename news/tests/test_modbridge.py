"""modbridge.py over a tmp spool on a synthetic game directory whose association names are stubbed. No game files are read,
no network is used and no real build runs: subprocess.run is faked for the build checks and server.route for the news
checks. The checks are the request and reply rules (parse_request, render), each op answered through process_spool, the
create op's refusals and cap, the news links and redirects, the text layout (html_to_text), and the spool's housekeeping
and worker limit.
"""
import itertools
import os
import struct
import subprocess
import sys
import textwrap
import time
import types
import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import create      # noqa: E402
import createweb   # noqa: E402
import league      # noqa: E402 (work/ is on the path once gamedata is imported)
import modbridge   # noqa: E402
import server      # noqa: E402

NAMES = {'TEST77.ASN': '1977 Major Leagues', 'ODD78.ASN': '<b>1978</b> & Friends', '16L1927.ASN': '1927 Major Leagues',
         '16l1927.asn': '1927 Major Leagues'}
HTML = 'text/html; charset=utf-8'
WAIT = 'Computer-run teams sign free agents on their own, so if you wait he may land somewhere else.'
WHO_HIT = {'assn': 'TEST77', 'first': 'Pat', 'last': 'Doe', 'pos': 'SS', 'bats': 'R', 'throws': 'R', 'age': '24',
           'archetype': 'regular', 'mode': 'realistic'}
HIT = dict(WHO_HIT, now_contact='60', ceil_contact='60', now_power='50', ceil_power='50', now_speed='65',
           ceil_speed='65', now_arm='55', ceil_arm='55', now_fielding='70', ceil_fielding='70')
WHO_PIT = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': '25',
           'archetype': 'ace', 'mode': 'realistic'}
PIT = dict(WHO_PIT, now_stamina='60', ceil_stamina='60', now_control='50', ceil_control='50', now_hold='50',
           ceil_hold='50', now_strikeout='70', p_FB_now='70', p_FB_ceil='75', p_SL_now='50', p_SL_ceil='55')
PAGE = ('<html><head><title>League &amp; News</title><style>p { color: red }</style></head><body>'
        '<h1>Standings</h1>'
        '<p>The  <a href="/news/x/">Opener</a> was big. See <a href="/">home</a> and '
        '<a href="/news/y/?q=1">more</a>.</p>'
        '<table><caption>Top</caption><tr><th>Team</th><th>W</th></tr>'
        '<tr><td><a href="/news/t/">Reds</a></td><td>100</td></tr>'
        '<tr><td>Cubs</td><td>7</td></tr></table></body></html>')
_ids = itertools.count(0x1000)


def player(pid, first='Pat', last='Doe', pos=6, born=1972, cur=None):
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, datetime.date(born, 7, 1).toordinal() + 365)
    p[0x44] = pos
    for i, v in (cur or {}).items():
        p[0x5d + i] = v
    return bytes(p)


def pyr_bytes(records, seed=(0x6b, 0xe2)):
    t = league._forward(seed)
    return bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records)


def pyf_bytes(ids):
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(create.gamedata, 'association',
                        lambda path: {'name': NAMES[os.path.basename(path)], 'teams': {}, 'games': []})
    game = tmp_path / 'game'
    (game / 'Assn').mkdir(parents=True)
    (game / 'Stats').mkdir()
    (game / 'Assn' / 'TEST77.ASN').write_bytes(b'asn')
    (game / 'Assn' / 'ODD78.ASN').write_bytes(b'asn')
    (game / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes([player(100, pos=4, born=1952),
                                                          player(205, 'Bo', 'Bee', pos=1)]))
    (game / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes([100, 205]))
    stock = tmp_path / 'stock'
    stock.mkdir()
    donor = stock / 'MLBPA96E.PYR'
    donor.write_bytes(pyr_bytes([player(105, 'Don', 'Or', cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82}),
                                 player(300, 'Dan', 'Pit', pos=1, born=1975, cur={5: 66, 6: 50, 7: 82, 9: 50})]))
    data = tmp_path / 'data'
    data.mkdir()
    proc = tmp_path / 'proc'
    proc.mkdir()
    return game, data, tmp_path / 'backup', donor, proc


@pytest.fixture
def bridge(site):
    """(ctx, spool): a bridge context on the synthetic game, and its empty spool directory."""
    game, data, backup, donor, proc = site
    spool = game / 'Mods' / 'spool'
    spool.mkdir(parents=True)
    ctx = types.SimpleNamespace(game=str(game), data=str(data), backup=str(backup), donor=str(donor), db='lahman.sqlite',
                                templates='templates', proc=str(proc))
    return ctx, str(spool)


def form_text(op, form):
    return '\n'.join(['op=' + op] + ['%s=%s' % kv for kv in form.items()])


def write_request(spool, rid, text):
    with open(os.path.join(spool, 'q%s.req' % rid), 'wb') as fh:
        fh.write(text.encode('latin-1'))


def reply(spool, rid):
    """(header dict, body) of the reply to request rid; the body's CRLF line ends are read as newlines."""
    with open(os.path.join(spool, 'r%s.rsp' % rid), 'rb') as fh:
        head, _, body = fh.read().decode('latin-1').partition('\r\n\r\n')
    return dict(line.split('=', 1) for line in head.split('\r\n')), body.replace('\r\n', '\n')


def ask(ctx, spool, text):
    """Writes text as a request, answers the spool once and returns the reply."""
    rid = '%08x' % next(_ids)
    write_request(spool, rid, text)
    modbridge.process_spool(ctx, spool)
    return reply(spool, rid)


def serve_pages(monkeypatch, pages):
    """Replaces server.route with a lookup of pages (path -> status, body, extra). Returns the paths asked for."""
    seen = []

    def route(data, path):
        seen.append(path)
        status, body, extra = pages.get(path, (404, b'<title>Not found</title>', ()))
        return status, HTML, body, extra

    monkeypatch.setattr(server, 'route', route)
    return seen


def fake_build(monkeypatch, game, returncode=0, stdout='', stderr='', write=True, timeout=False):
    """Replaces subprocess.run with a build that writes 16L1927.ASN into the game (when write). Returns the calls made."""
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        if timeout:
            raise subprocess.TimeoutExpired(cmd, kw['timeout'])
        if write:
            (game / 'Assn' / '16L1927.ASN').write_bytes(b'asn')
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, 'run', run)
    return calls


# parse_request and render: the protocol's request and reply rules

def test_parse_request_reads_the_fields():
    raw = b'op=create\r\nassn=TEST77\n\nfirst=Pat\nq=a=b\n'
    assert modbridge.parse_request(raw) == {'op': 'create', 'assn': 'TEST77', 'first': 'Pat', 'q': 'a=b'}


@pytest.mark.parametrize('raw', [
    b'',                                       # no lines
    b'x=1\nop=ping',                           # first line is not op
    b'op',                                     # no =
    b'op=ping\nnoequals',
    b'op=ping\nop=ping',                       # key given twice
    b'op=ping\nx=1\nx=2',
    b'op=ping\nAB=1',                          # key outside [a-z0-9_]
    b'op=ping\na-b=1',
    b'op=ping\n' + b'k' * 25 + b'=1',          # key over 24 characters
    b'op=ping\nx=a\tb',                        # control characters in a value
    b'op=ping\nx=a\rb',
    b'op=ping\nx=a\x00',
    b'op=ping\nx=' + b'a' * 257,               # value over 256 characters
])
def test_parse_request_rejects_rule_breaks(raw):
    assert modbridge.parse_request(raw) is None


def test_parse_request_limits_size_and_lines():
    big = 'op=ping\n' + ''.join('k%d=%s\n' % (i, 'v' * 200) for i in range(40))
    assert len(big) > 8192 and modbridge.parse_request(big.encode()) is None
    ok = 'op=ping\n' + ''.join('k%d=%s\n' % (i, 'v' * 200) for i in range(20))
    assert len(ok) <= 8192 and modbridge.parse_request(ok.encode()) is not None
    hundred = 'op=ping\n' + ''.join('k%d=1\n' % i for i in range(99))
    assert modbridge.parse_request(hundred.encode()) is not None
    assert modbridge.parse_request((hundred + 'z=1\n').encode()) is None     # 101 lines
    assert modbridge.parse_request(('op=ping\n' + 'k' * 24 + '=' + 'v' * 256).encode()) is not None


def test_parse_request_allows_arsenal_keys_in_capitals_only_for_real_slots():
    fields = modbridge.parse_request(b'op=create\np_FB_now=70\np_KN_ceil=75')
    assert fields == {'op': 'create', 'p_FB_now': '70', 'p_KN_ceil': '75'}
    assert modbridge.parse_request(b'op=create\np_XX_now=70') is None
    assert modbridge.parse_request(b'op=create\np_FB_mid=70') is None


def test_render_layout():
    assert modbridge.render([('status', 'ok'), ('count', '2')], 'a\nb') == b'status=ok\r\ncount=2\r\n\r\na\r\nb'
    assert modbridge.render([('status', 'busy')], '') == b'status=busy\r\n\r\n'
    assert modbridge.render([('status', 'ok')], 'x\r\ny') == b'status=ok\r\n\r\nx\r\ny'


def test_render_maps_typography_and_replaces_what_latin1_lacks():
    out = modbridge.render([('status', 'ok')], '“Hi” — it’s… a b 中 café')
    assert out == b'status=ok\r\n\r\n"Hi" - it\'s... a b ? caf\xe9'


def test_render_maps_nav_arrows_and_bullets():
    out = modbridge.render([('status', 'ok')], '← Newer · Older → • x')
    assert out == b'status=ok\r\n\r\n<- Newer \xb7 Older -> * x'


# each op through process_spool

def test_ping(bridge):
    ctx, spool = bridge
    assert ask(ctx, spool, 'op=ping') == ({'status': 'ok', 'version': '1'}, '')


def test_assns_are_sorted_by_stem_with_labels(bridge):
    ctx, spool = bridge
    head, body = ask(ctx, spool, 'op=assns')
    assert head == {'status': 'ok', 'count': '2', 'assn.0': 'ODD78\t<b>1978</b> & Friends',
                    'assn.1': 'TEST77\t1977 Major Leagues'}
    assert body == ''


def test_archetypes_and_the_form_limits(bridge):
    ctx, spool = bridge
    head, _ = ask(ctx, spool, 'op=archetypes')
    keys = list(create.ARCHETYPES)
    ace = keys.index('ace')
    assert head['count'] == str(len(keys))
    assert head['arch.0'] == 'contact\tContact hitter\thit'
    assert head['arch.%d' % ace] == 'ace\tPower ace\tpit'
    assert head['arch.%d.blurb' % ace] == create.ARCHETYPES['ace']['blurb']
    assert head['arch.%d.now' % ace] == 'stamina:65,control:50,hold:50,strikeout:70'
    assert head['arch.%d.ceil' % ace] == 'stamina:70,control:55,hold:50'
    assert head['arch.%d.pitches' % ace] == 'FB:75:80,SL:65:70,CU:50:55'
    assert head['arch.0.pitches'] == ''
    assert head['grades'] == '20,25,30,35,40,45,50,55,60,65,70,75,80'
    assert head['ages'] == '17-45'
    assert head['budget.hit'] == '50,100' and head['budget.pit'] == '80,110'
    assert head['positions'] == 'P,C,1B,2B,3B,SS,LF,CF,RF'


def test_create_signs_a_hitter(bridge, site):
    ctx, spool = bridge
    game, data = site[0], site[1]
    pyr, pyf = game / 'Assn' / 'TEST77.PYR', game / 'Assn' / 'TEST77.PYF'
    pyr_before = pyr.read_bytes()
    head, body = ask(ctx, spool, form_text('create', HIT))
    assert head == {'status': 'ok', 'pid': '206', 'name': 'Pat Doe', 'assn': 'TEST77'}
    assert len(pyr.read_bytes()) == len(pyr_before) + 192
    assert create.pyf_ids(pyf.read_bytes())[-1] == 206
    entries = createweb._read_ledger(str(data), 'TEST77')
    assert [(e['pid'], e['name'], e['pos']) for e in entries] == [(206, 'Pat Doe', 'SS')]
    spec, _ = create.validate(HIT, {'TEST77': str(game / 'Assn' / 'TEST77.ASN')})
    lines = body.split('\n')
    assert lines[0] == 'Pat Doe (Shortstop) is in the 1977 Major Leagues free agent pool.'
    assert lines[1:3] == ['', 'Scouting report:']
    assert all('  ' + s in lines for s in create.scouting_report(spec))
    steps = ['%d. %s' % (i, s) for i, s in enumerate(createweb.sign_steps('1977 Major Leagues'), 1)]
    assert len(steps) == 4 and all(step in lines for step in steps)
    assert lines[lines.index('To sign him:') + 1] == steps[0]
    assert lines[-1] == WAIT


def test_create_signs_a_pitcher_with_his_arsenal(bridge, site):
    ctx, spool = bridge
    head, body = ask(ctx, spool, form_text('create', PIT))
    assert head['status'] == 'ok' and head['name'] == 'Al Ko'
    spec, _ = create.validate(PIT, {'TEST77': str(site[0] / 'Assn' / 'TEST77.ASN')})
    lines = body.split('\n')
    assert lines[0] == 'Al Ko (Pitcher) is in the 1977 Major Leagues free agent pool.'
    assert all('  ' + s in lines for s in create.scouting_report(spec))


def test_create_reports_each_bad_field(bridge):
    ctx, spool = bridge
    head, body = ask(ctx, spool, form_text('create', dict(HIT, first='', age='99')))
    assert head == {'status': 'error', 'error.age': 'Pick an age from 17 to 45.', 'error.first': 'Enter a first name.'}
    assert body == 'age: Pick an age from 17 to 45.\nfirst: Enter a first name.'


def test_create_reports_a_bad_rating(bridge):
    ctx, spool = bridge
    head, body = ask(ctx, spool, form_text('create', dict(HIT, now_contact='61')))
    assert head == {'status': 'error', 'error.now_contact': create.GRADE_MSG}
    assert body == 'now_contact: ' + create.GRADE_MSG


def test_create_while_the_association_is_open(bridge, site, tmp_path):
    ctx, spool = bridge
    pyr, pyf = site[0] / 'Assn' / 'TEST77.PYR', site[0] / 'Assn' / 'TEST77.PYF'
    before = (pyr.read_bytes(), pyf.read_bytes())
    fake = tmp_path / 'fakeproc'
    (fake / '4242' / 'fd').mkdir(parents=True)
    (fake / '4242' / 'fd' / '3').symlink_to(pyr)
    ctx.proc = str(fake)
    msg = '1977 Major Leagues is open in the game. Go back to the main menu, then create the player again.'
    head, body = ask(ctx, spool, form_text('create', HIT))
    assert head == {'status': 'error', 'error.assn': msg} and body == msg
    assert (pyr.read_bytes(), pyf.read_bytes()) == before
    assert createweb._read_ledger(ctx.data, 'TEST77') == []


def test_create_refused_at_the_cap(bridge, site):
    ctx, spool = bridge
    pyr = site[0] / 'Assn' / 'TEST77.PYR'
    before = pyr.read_bytes()
    entries = [{'pid': 100 + i, 'name': 'A B', 'pos': 'P', 'assn': 'TEST77', 'created': '2026-01-01T00:00:00',
                'archetype': 'ace', 'mode': 'realistic'} for i in range(createweb.CAP)]
    createweb._write_ledger(ctx.data, 'TEST77', entries)
    msg = 'This association already has 40 created players.'
    head, body = ask(ctx, spool, form_text('create', HIT))
    assert head == {'status': 'error', 'error.assn': msg} and body == msg
    assert pyr.read_bytes() == before


def test_news_page_as_text_with_numbered_links(bridge, monkeypatch):
    ctx, spool = bridge
    seen = serve_pages(monkeypatch, {'/news/': (200, PAGE.encode('utf-8'), ())})
    head, body = ask(ctx, spool, 'op=news\npath=/news/')
    assert head == {'status': 'ok', 'http': '200', 'path': '/news/', 'title': 'League & News', 'count': '3',
                    'link.0': 'Opener\t/news/x/', 'link.1': 'more\t/news/y/?q=1', 'link.2': 'Reds\t/news/t/'}
    assert seen == ['/news/']
    lines = body.split('\n')
    assert lines[:2] == ['Standings', '=' * 9]
    assert 'The Opener [1] was big. See home and more [2].' in lines
    assert 'Top' in lines
    assert 'Team' + ' ' * 6 + 'W' in lines
    assert 'Reds [3]  100' in lines
    assert 'Cubs' + ' ' * 8 + '7' in lines


def test_news_follows_a_redirect_within_news(bridge, monkeypatch):
    ctx, spool = bridge
    seen = serve_pages(monkeypatch, {'/news/old/': (301, b'', (('Location', '/news/new/'),)),
                                     '/news/new/': (200, b'<title>New</title><p>Here</p>', ())})
    head, body = ask(ctx, spool, 'op=news\npath=/news/old/')
    assert head == {'status': 'ok', 'http': '200', 'path': '/news/new/', 'title': 'New', 'count': '0'}
    assert body == 'Here' and seen == ['/news/old/', '/news/new/']


def test_news_stops_after_three_hops(bridge, monkeypatch):
    ctx, spool = bridge
    seen = serve_pages(monkeypatch, {'/news/loop/': (302, b'', (('Location', '/news/loop/'),))})
    head, _ = ask(ctx, spool, 'op=news\npath=/news/loop/')
    assert head['status'] == 'error' and head['http'] == '302' and head['path'] == '/news/loop/'
    assert len(seen) == 4


def test_news_does_not_follow_a_redirect_out_of_news(bridge, monkeypatch):
    ctx, spool = bridge
    seen = serve_pages(monkeypatch, {'/news/away/': (301, b'', (('Location', '/create/'),))})
    head, _ = ask(ctx, spool, 'op=news\npath=/news/away/')
    assert head == {'status': 'error', 'http': '301', 'path': '/news/away/', 'title': '', 'count': '0'}
    assert seen == ['/news/away/']


@pytest.mark.parametrize('path', ['/create/', '/news', '/news/a b', '/news/' + 'a' * 251])
def test_news_refuses_bad_paths(bridge, monkeypatch, path):
    ctx, spool = bridge
    seen = serve_pages(monkeypatch, {})
    head, body = ask(ctx, spool, 'op=news\npath=' + path)
    assert head == {'status': 'error'} and body == 'Bad request.' and seen == []


@pytest.mark.parametrize('year', ['1800', '2026', 'abcd', ''])
def test_build_refuses_a_year_out_of_range(bridge, monkeypatch, year):
    ctx, spool = bridge
    calls = fake_build(monkeypatch, None)
    head, body = ask(ctx, spool, 'op=build\nyear=' + year)
    assert head == {'status': 'error'} and body == 'Pick a year from 1871 to 2025 for MLB.'
    assert calls == []


@pytest.mark.parametrize('year', ['1919', '1949'])
def test_build_refuses_a_negro_leagues_year_out_of_range(bridge, monkeypatch, year):
    ctx, spool = bridge
    calls = fake_build(monkeypatch, None)
    head, body = ask(ctx, spool, 'op=build\nyear=%s\nleague=negro' % year)
    assert head == {'status': 'error'} and body == 'Pick a year from 1920 to 1948 for Negro Leagues.'
    assert calls == []


def test_build_refuses_an_unknown_league(bridge, monkeypatch):
    ctx, spool = bridge
    calls = fake_build(monkeypatch, None)
    assert ask(ctx, spool, 'op=build\nyear=1942\nleague=fed') == ({'status': 'error'}, 'Bad request.')
    assert calls == []


def test_build_refuses_a_kind_the_database_lacks(bridge, monkeypatch):
    ctx, spool = bridge
    ctx.ranges = {'mlb': (1871, 2019)}
    calls = fake_build(monkeypatch, None)
    head, body = ask(ctx, spool, 'op=build\nyear=1942\nleague=negro')
    assert head == {'status': 'error'} and body == 'This database has no Negro Leagues seasons.'
    head, body = ask(ctx, spool, 'op=build\nyear=2020')
    assert body == 'Pick a year from 1871 to 2019 for MLB.'
    assert calls == []


def test_build_negro_leagues_passes_the_leagues_and_finds_the_n_stem(bridge, site, monkeypatch):
    ctx, spool = bridge
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        (site[0] / 'Assn' / '16N1942.ASN').write_bytes(b'asn')
        return subprocess.CompletedProcess(cmd, 0, stdout='ok\n', stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    head, body = ask(ctx, spool, 'op=build\nyear=1942\nleague=negro')
    assert head['status'] == 'ok' and head['existed'] == '0' and head['stem'] == '16N1942'
    assert calls[0][-2:] == ['--leagues', 'NNL,ECL,ANL,EWL,NSL,NN2,NAL']
    # asking again finds the 16N1942 just built
    head, _ = ask(ctx, spool, 'op=build\nyear=1942\nleague=negro')
    assert head['existed'] == '1' and len(calls) == 1


def test_year_ranges_reads_the_database(tmp_path):
    import sqlite3
    db = tmp_path / 'l.sqlite'
    con = sqlite3.connect(str(db))
    con.execute('CREATE TABLE teams (yearID INTEGER, lgID TEXT)')
    con.executemany('INSERT INTO teams VALUES (?, ?)', [(1876, 'NL'), (2025, 'AL'), (1937, 'NAL'), (1931, 'NNL')])
    con.commit()
    con.close()
    assert modbridge.year_ranges(str(db)) == {'mlb': (1876, 2025), 'negro': (1931, 1937)}
    con = sqlite3.connect(str(db))
    con.execute("DELETE FROM teams WHERE lgID IN ('NAL', 'NNL')")
    con.commit()
    con.close()
    assert modbridge.year_ranges(str(db)) == {'mlb': (1876, 2025)}


@pytest.mark.parametrize('name', ['16L1927.ASN', '16l1927.asn'])
def test_build_reports_a_season_already_in_the_game(bridge, site, monkeypatch, name):
    ctx, spool = bridge
    game = site[0]
    (game / 'Assn' / name).write_bytes(b'asn')
    calls = fake_build(monkeypatch, game)
    head, body = ask(ctx, spool, 'op=build\nyear=1927')
    assert head == {'status': 'ok', 'existed': '1', 'stem': '16L1927', 'label': '1927 Major Leagues'}
    assert body == '1927 Major Leagues is already in the game (16L1927).'
    assert calls == []


def test_build_busy_while_another_season_is_built(bridge, site, monkeypatch):
    ctx, spool = bridge
    calls = fake_build(monkeypatch, site[0])
    modbridge._BUILD.acquire()
    try:
        head, body = ask(ctx, spool, 'op=build\nyear=1927')
    finally:
        modbridge._BUILD.release()
    assert head == {'status': 'busy'} and body == 'A season is already being built. Try again when it finishes.'
    assert calls == []


def test_build_success_runs_build_py_and_names_the_season(bridge, site, monkeypatch):
    ctx, spool = bridge
    stdout = ''.join('line %d\n' % i for i in range(12))
    calls = fake_build(monkeypatch, site[0], stdout=stdout)
    head, body = ask(ctx, spool, 'op=build\nyear=1927')
    assert head == {'status': 'ok', 'existed': '0', 'stem': '16L1927', 'label': '1927 Major Leagues'}
    assert body == ('Built 1927 Major Leagues (16L1927). Pick it from the association list.\n\n'
                    + '\n'.join('line %d' % i for i in range(2, 12)))
    cmd, kw = calls[0]
    assert cmd[1:] == [modbridge.BUILD_PY, '--year', '1927', '--install', ctx.game, '--db', ctx.db,
                       '--templates', ctx.templates]
    assert kw['timeout'] == 900 and kw['cwd'] == modbridge.REPO and kw['capture_output'] and kw['text']
    assert not modbridge._BUILD.locked()


@pytest.mark.parametrize('kw, body', [
    (dict(returncode=1, stdout='working\n', stderr='boom\n'), 'The build failed.\n\nworking\nboom'),
    (dict(returncode=0, write=False, stdout='done\n'), 'The build failed.\n\ndone'),
    (dict(timeout=True), 'The build failed.\n\nTimed out.'),
])
def test_build_failures_say_so(bridge, site, monkeypatch, kw, body):
    ctx, spool = bridge
    fake_build(monkeypatch, site[0], **kw)
    head, text = ask(ctx, spool, 'op=build\nyear=1927')
    assert head == {'status': 'error'} and text == body
    assert not modbridge._BUILD.locked()


def test_unknown_op_and_bad_request(bridge):
    ctx, spool = bridge
    assert ask(ctx, spool, 'op=nope') == ({'status': 'error'}, 'Unknown request.')
    assert ask(ctx, spool, 'op=ping\nop=ping') == ({'status': 'error'}, 'Bad request.')


def test_request_becomes_reply_and_the_work_file_goes(bridge):
    ctx, spool = bridge
    write_request(spool, 'deadbeef', 'op=ping')
    modbridge.process_spool(ctx, spool)
    assert os.listdir(spool) == ['rdeadbeef.rsp']


def test_names_that_do_not_match_are_left_alone(bridge):
    ctx, spool = bridge
    names = ['Q0000001.req', 'q1.req', 'q0000000G.req', 'q00000001.req.bak', 'q00000001.work']
    for name in names:
        open(os.path.join(spool, name), 'wb').close()
    modbridge.process_spool(ctx, spool)
    assert sorted(os.listdir(spool)) == sorted(names)


def test_full_workers_leave_requests_for_the_next_poll(bridge):
    ctx, spool = bridge
    write_request(spool, 'cafef00d', 'op=ping')
    for _ in range(modbridge.MAX_WORKERS):
        modbridge._SLOTS.acquire()
    try:
        modbridge.process_spool(ctx, spool)
        assert os.listdir(spool) == ['qcafef00d.req']
    finally:
        for _ in range(modbridge.MAX_WORKERS):
            modbridge._SLOTS.release()
    modbridge.process_spool(ctx, spool)
    assert os.listdir(spool) == ['rcafef00d.rsp']


def test_housekeeping_removes_stale_replies_and_temporaries(tmp_path):
    now = time.time()
    stale = ['r00000001.rsp', 'r00000002.tmp', 'q00000003.tmp', 'q00000005.work']
    for name in stale + ['r00000004.rsp']:
        (tmp_path / name).write_bytes(b'x')
    for name in stale:
        os.utime(tmp_path / name, (now - 1000, now - 1000))
    modbridge.housekeep(str(tmp_path), now)
    assert sorted(os.listdir(tmp_path)) == ['q00000005.work', 'r00000004.rsp']


# html_to_text: the layout of the text

def test_headings_are_underlined_and_followed_by_a_blank_line():
    title, text, links = modbridge.html_to_text('<h1>Big news</h1><h2>Sub</h2><h3>Minor</h3>', '/news/')
    assert (title, text, links) == ('', 'Big news\n========\n\nSub\n---\n\nMinor', [])


def test_at_most_one_blank_line_in_a_row_and_none_at_the_ends():
    _, text, _ = modbridge.html_to_text('<p>a</p><p></p><div></div><p>b</p><br><br><p></p>', '/news/')
    assert text == 'a\n\nb'


def test_ordered_lists_number_from_one_each_and_unordered_get_dashes():
    _, text, _ = modbridge.html_to_text('<ol><li>one</li><li>two</li></ol><ol><li>three</li></ol>'
                                        '<ul><li>x</li></ul>', '/news/')
    assert text == '1. one\n2. two\n\n1. three\n\n- x'


def test_paragraphs_wrap_at_76_columns():
    words = ' '.join(['word'] * 40)
    _, text, _ = modbridge.html_to_text('<p>%s</p>' % words, '/news/')
    assert text == textwrap.fill(words, 76)
    assert max(len(line) for line in text.split('\n')) <= 76


def test_list_item_continuation_lines_are_indented_by_the_prefix():
    words = ' '.join(['word'] * 40)
    _, text, _ = modbridge.html_to_text('<ul><li>%s</li></ul>' % words, '/news/')
    lines = text.split('\n')
    assert lines[0].startswith('- word') and len(lines) > 1
    assert all(line.startswith('  word') for line in lines[1:])


def test_title_is_read_and_head_script_and_style_are_not_output():
    title, text, links = modbridge.html_to_text(
        '<html><head><title> League &amp; News </title><style>p{}</style><script>var x = 1;</script></head>'
        '<body><p>hi</p></body></html>', '/news/')
    assert (title, text, links) == ('League & News', 'hi', [])


def test_links_resolve_against_the_page_and_only_news_links_are_numbered():
    html = '<p>Go <a href="../x/">up</a>, <a href="/">home</a>, <a href="/news/q/?p=2#top"></a>.</p>'
    _, text, links = modbridge.html_to_text(html, '/news/a/b/')
    assert links == [('up', '/news/a/x/'), ('/news/q/?p=2', '/news/q/?p=2')]
    assert text == 'Go up [1], home, [2].'


def test_a_table_nested_in_a_cell_does_not_break_the_page():
    _, text, _ = modbridge.html_to_text('<table><tr><td>a<table><tr><td>b</td></tr></table>c</td></tr></table>'
                                        '<p>after</p>', '/news/')
    assert text.split('\n')[-1] == 'after'


def test_news_through_the_real_server_with_a_string_data_dir(bridge):
    # The service passes --data as a str; server.route joins with /, so the bridge must hand it a Path.
    ctx, spool = bridge
    head, body = ask(ctx, spool, 'op=news\npath=/news/TEST77/')
    assert body != 'Something went wrong.'
    assert head['http'] in ('200', '404')


def test_a_planted_reply_symlink_is_never_written_through(bridge, tmp_path):
    ctx, spool = bridge
    victim = tmp_path / 'victim.txt'
    victim.write_text('keep')
    os.symlink(victim, os.path.join(spool, 'r%08x.tmp' % 0xfeed0001))
    write_request(spool, '%08x' % 0xfeed0001, 'op=ping')
    modbridge.process_spool(ctx, spool)
    assert victim.read_text() == 'keep'
    assert reply(spool, '%08x' % 0xfeed0001)[0]['status'] == 'ok'


def test_a_fifo_or_symlinked_request_is_a_bad_request_and_never_blocks(bridge, tmp_path):
    ctx, spool = bridge
    os.mkfifo(os.path.join(spool, 'q%08x.req' % 0xfeed0002))
    secret = tmp_path / 'secret'
    secret.write_text('op=ping\n')
    os.symlink(secret, os.path.join(spool, 'q%08x.req' % 0xfeed0003))
    modbridge.process_spool(ctx, spool)
    for rid in (0xfeed0002, 0xfeed0003):
        head, body = reply(spool, '%08x' % rid)
        assert head['status'] == 'error' and body == 'Bad request.'


def test_spool_ok_refuses_a_symlinked_spool(tmp_path):
    game = tmp_path / 'game'
    (game / 'Mods').mkdir(parents=True)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    os.symlink(elsewhere, game / 'Mods' / 'spool')
    assert not modbridge.spool_ok(str(game))
    os.remove(game / 'Mods' / 'spool')
    (game / 'Mods' / 'spool').mkdir()
    assert modbridge.spool_ok(str(game))


def test_a_symlinked_spool_is_never_worked_through(bridge, tmp_path):
    ctx, spool = bridge
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'keep.tmp').write_bytes(b'x')
    (elsewhere / 'r00000009.rsp').write_bytes(b'x')
    old = time.time() - 10000
    for name in ('keep.tmp', 'r00000009.rsp'):
        os.utime(elsewhere / name, (old, old))
    write_request(str(elsewhere), 'feed0004', 'op=ping')
    os.rename(spool, spool + '.old')
    os.symlink(elsewhere, spool)
    with pytest.raises(OSError):
        modbridge.housekeep(spool)
    with pytest.raises(OSError):
        modbridge.process_spool(ctx, spool)
    assert sorted(os.listdir(elsewhere)) == ['keep.tmp', 'qfeed0004.req', 'r00000009.rsp']


def test_a_spool_swapped_after_it_is_opened_keeps_the_reply_inside(bridge, tmp_path):
    ctx, spool = bridge
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    write_request(spool, 'feed0005', 'op=ping')
    dfd = modbridge.open_dir(spool)
    try:
        os.rename(spool, spool + '.old')
        os.symlink(elsewhere, spool)
        modbridge._answer(ctx, dfd, 'feed0005')
    finally:
        os.close(dfd)
    assert os.listdir(elsewhere) == []
    assert os.listdir(spool + '.old') == ['rfeed0005.rsp']


def test_make_spool_never_creates_through_a_symlinked_mods(tmp_path):
    game = tmp_path / 'game'
    game.mkdir()
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    os.symlink(elsewhere, game / 'Mods')
    with pytest.raises(OSError):
        modbridge.make_spool(str(game))
    assert os.listdir(elsewhere) == []
    os.remove(game / 'Mods')
    modbridge.make_spool(str(game))
    assert modbridge.spool_ok(str(game))


def test_build_refuses_over_leftover_or_planted_season_files(bridge, site, monkeypatch, tmp_path):
    ctx, spool = bridge
    game = site[0]
    calls = fake_build(monkeypatch, game)
    os.symlink(tmp_path / 'victim', game / 'Assn' / '16L1927.PYR')
    head, body = ask(ctx, spool, 'op=build\nyear=1927')
    assert head['status'] == 'error' and 'already in the game without' in body
    assert calls == []
