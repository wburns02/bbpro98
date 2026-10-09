"""createweb.py over real sockets (port 0, a thread) on a synthetic game directory whose association names are stubbed.
No game files are read. The checks are the form page, the POST's origin, length, type and field checks, the cap, the
refusal while the game has the association open, and the done page."""
import datetime
import html
import http.client
import json
import os
import struct
import sys
import threading
from urllib.parse import urlencode

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import create      # noqa: E402
import createweb   # noqa: E402
import league      # noqa: E402 (work/ is on the path once gamedata is imported)

ORIGIN = 'https://site.test'
FORM = 'application/x-www-form-urlencoded'
NAMES = {'TEST77.ASN': '1977 Major Leagues', 'ODD78.ASN': '<b>1978</b> & Friends'}
GOOD = {'assn': 'TEST77', 'first': 'Pat', 'last': 'Doe', 'pos': 'SS', 'bats': 'R', 'throws': 'R', 'age': '24',
        'contact': '60', 'power': '50', 'speed': '65', 'arm': '55', 'fielding': '70',
        'stamina': '50', 'control': '50', 'strikeout': '50', 'stuff': '50'}


def player(pid, first='Pat', last='Doe', pos=6, cur=None):
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, datetime.date(1972, 7, 1).toordinal() + 365)
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
    (game / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes([player(100, pos=3), player(205, 'Bo', 'Bee', pos=1)]))
    (game / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes([100, 205]))
    stock = tmp_path / 'stock'
    stock.mkdir()
    donor = stock / 'MLBPA96E.PYR'
    donor.write_bytes(pyr_bytes([player(105, 'Don', 'Or', cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})]))
    data = tmp_path / 'data'
    data.mkdir()
    proc = tmp_path / 'proc'
    proc.mkdir()
    return game, data, tmp_path / 'backup', donor, proc


@pytest.fixture
def web(site):
    game, data, backup, donor, proc = site
    srv = createweb.make_server(str(game), str(data), str(backup), [ORIGIN], str(donor), port=0, proc=str(proc))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', srv.server_address[1], timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, r.headers, r.read()
    finally:
        conn.close()


def raw(srv, headers):
    """A POST to /create/ with exactly these headers and no body (http.client adds nothing it is not given)."""
    conn = http.client.HTTPConnection('127.0.0.1', srv.server_address[1], timeout=10)
    try:
        conn.putrequest('POST', '/create/')
        for k, v in headers.items():
            conn.putheader(k, v)
        conn.endheaders()
        r = conn.getresponse()
        return r.status, r.headers, r.read()
    finally:
        conn.close()


def post(srv, fields, origin=ORIGIN, extra=None):
    headers = {'Content-Type': FORM}
    if origin is not None:
        headers['Origin'] = origin
    headers.update(extra or {})
    return call(srv, 'POST', '/create/', urlencode(fields).encode(), headers)


def test_form_page_lists_every_association_escaped_and_sorted(web):
    status, headers, body = call(web, 'GET', '/create/')
    text = body.decode()
    assert status == 200
    assert '<form method="post" action="/create/">' in text
    assert '&lt;b&gt;1978&lt;/b&gt; &amp; Friends' in text and '<b>1978' not in text
    assert text.index('1977 Major Leagues') < text.index('&lt;b&gt;1978')
    assert "default-src 'none'" in headers['Content-Security-Policy']
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['Cache-Control'] == 'no-store'


def test_bare_path_moves_and_strangers_are_refused(web):
    status, headers, _ = call(web, 'GET', '/create')
    assert status == 301 and headers['Location'] == '/create/'
    assert call(web, 'GET', '/nope')[0] == 404
    status, headers, _ = call(web, 'PUT', '/create/')
    assert status == 405 and headers['Allow'] == 'GET, HEAD, POST'


def test_head_has_headers_and_no_body(web):
    status, _, body = call(web, 'HEAD', '/create/')
    assert status == 200 and body == b''


def test_good_post_creates_the_player_redirects_and_writes_the_ledger(web, site):
    game, data, backup, _, _ = site
    status, headers, _ = post(web, GOOD)
    assert status == 303
    assert headers['Location'] == '/create/done?assn=TEST77&pid=206'
    _, recs = create.decipher((game / 'Assn' / 'TEST77.PYR').read_bytes())
    assert [r[0] | r[1] << 8 for r in recs] == [100, 205, 206]
    assert create.pyf_ids((game / 'Assn' / 'TEST77.PYF').read_bytes()) == [100, 205, 206]
    assert any(backup.iterdir())
    ledger = json.loads((data / 'created' / 'TEST77.json').read_text())
    assert [(e['pid'], e['name'], e['pos'], e['assn']) for e in ledger] == [(206, 'Pat Doe', 'SS', 'TEST77')]


def test_done_page_names_the_player_and_its_association(web):
    post(web, GOOD)
    status, _, body = call(web, 'GET', '/create/done?assn=TEST77&pid=206')
    assert status == 200
    assert 'Pat Doe (Shortstop) is in the 1977 Major Leagues free agent pool.' in body.decode()
    assert 'Ownership must say Human' in body.decode() and 'Team &gt; Claim Free Agent' in body.decode()
    assert call(web, 'GET', '/create/done?assn=TEST77&pid=999')[0] == 404
    assert call(web, 'GET', '/create/done?assn=..%2Fx&pid=206')[0] == 404
    assert call(web, 'GET', '/create/done')[0] == 404
    assert call(web, 'POST', '/create/done', b'', {'Origin': ORIGIN})[0] == 405


def test_created_players_are_listed_on_the_form(web):
    post(web, GOOD)
    text = call(web, 'GET', '/create/')[2].decode()
    assert 'Pat Doe, Shortstop, 1977 Major Leagues,' in text


def test_bad_origin_is_refused_and_nothing_is_written(web, site):
    game, data, backup, _, _ = site
    before = (game / 'Assn' / 'TEST77.PYR').read_bytes()
    assert post(web, GOOD, origin='https://evil.test')[0] == 403
    assert post(web, GOOD, origin=None)[0] == 403
    assert post(web, GOOD, origin=None, extra={'Referer': 'https://site.test.evil/create/'})[0] == 403
    assert (game / 'Assn' / 'TEST77.PYR').read_bytes() == before
    assert not data.joinpath('created').exists()


def test_a_referer_under_the_origin_is_accepted_when_no_origin_is_sent(web):
    status, _, _ = post(web, GOOD, origin=None, extra={'Referer': ORIGIN + '/create/'})
    assert status == 303


def test_length_and_type_are_checked_before_the_body(web):
    base = {'Origin': ORIGIN, 'Content-Type': FORM}
    assert raw(web, dict(base, **{'Content-Length': '5000'}))[0] == 413
    assert raw(web, dict(base, **{'Content-Length': '0'}))[0] == 413
    assert raw(web, base)[0] == 411
    assert raw(web, {'Origin': ORIGIN, 'Content-Type': 'application/json', 'Content-Length': '2'})[0] == 415


def test_a_bad_field_is_422_with_the_form_back_and_the_value_escaped(web):
    status, _, body = post(web, dict(GOOD, first='<script>', contact='52'))
    text = body.decode()
    assert status == 422
    assert 'Use letters, spaces, apostrophes, periods or hyphens, up to 16 characters.' in text
    assert 'Pick a grade from 20 to 80, in steps of 5.' in text
    assert '&lt;script&gt;' in text and '<script>' not in text
    assert '<option value="SS" selected>' in text and 'value="24"' in text and 'value="Doe"' in text


def test_an_open_association_is_409_and_the_files_are_untouched(web, site):
    game, data, backup, _, proc = site
    pyr = game / 'Assn' / 'TEST77.PYR'
    before = pyr.read_bytes()
    (proc / '99' / 'fd').mkdir(parents=True)
    os.symlink(pyr, proc / '99' / 'fd' / '3')
    status, _, body = post(web, GOOD)
    assert status == 409
    assert '1977 Major Leagues is open in the game. Go back to the game' in html.unescape(body.decode())
    assert pyr.read_bytes() == before
    assert not backup.exists() and not data.joinpath('created').exists()


def test_the_cap_is_429_per_association(web, site):
    game, data, _, _, _ = site
    (data / 'created').mkdir()
    entry = {'pid': 100, 'name': 'Old Timer', 'pos': 'C', 'assn': 'TEST77', 'created': '2026-01-01T00:00:00'}
    (data / 'created' / 'TEST77.json').write_text(json.dumps([entry] * 40))
    before = (game / 'Assn' / 'TEST77.PYR').read_bytes()
    status, _, body = post(web, GOOD)
    assert status == 429
    assert 'This association already has 40 created players.' in body.decode()
    assert (game / 'Assn' / 'TEST77.PYR').read_bytes() == before


def test_a_corrupt_ledger_stops_the_create_rather_than_resetting_it(web, site):
    game, data, _, _, _ = site
    (data / 'created').mkdir()
    (data / 'created' / 'TEST77.json').write_text('{"not": "a list"}')
    before = (game / 'Assn' / 'TEST77.PYR').read_bytes()
    assert post(web, GOOD)[0] == 500
    assert (game / 'Assn' / 'TEST77.PYR').read_bytes() == before
    assert json.loads((data / 'created' / 'TEST77.json').read_text()) == {'not': 'a list'}


def test_every_response_carries_the_csp_header(web):
    for method, path in (('GET', '/create/'), ('GET', '/nope'), ('PUT', '/create/'), ('POST', '/create/')):
        status, headers, _ = call(web, method, path, b'', {'Origin': 'https://evil.test'} if method == 'POST' else {})
        assert "frame-ancestors 'self'" in headers['Content-Security-Policy'], (method, path, status)
        assert headers['Referrer-Policy'] == 'same-origin'
