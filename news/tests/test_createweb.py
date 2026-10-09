"""createweb.py over real sockets (port 0, a thread) on a synthetic game directory whose association names are stubbed.
No game files are read. The checks are the form page and each step of the flow (who, back, ratings, edit, commit, and an
unknown step), the POST's origin, length, type and field checks, the cap, the refusal while the game has the association
open, the baseball card, and the done page."""
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
NAME_MSG = 'Use letters, spaces, apostrophes, periods or hyphens, up to 16 characters.'
WHO_HIT = {'assn': 'TEST77', 'first': 'Pat', 'last': 'Doe', 'pos': 'SS', 'bats': 'R', 'throws': 'R', 'age': '24',
           'archetype': 'regular', 'mode': 'realistic'}
HIT = dict(WHO_HIT, now_contact='60', ceil_contact='60', now_power='50', ceil_power='50', now_speed='65',
           ceil_speed='65', now_arm='55', ceil_arm='55', now_fielding='70', ceil_fielding='70')
GOOD = dict(HIT, step='commit')
WHO_PIT = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': '25',
           'archetype': 'ace', 'mode': 'realistic'}
PIT = dict(WHO_PIT, now_stamina='60', ceil_stamina='60', now_control='50', ceil_control='50', now_hold='50',
           ceil_hold='50', now_strikeout='70', p_FB_now='70', p_FB_ceil='75', p_SL_now='50', p_SL_ceil='55')
PITCH_GOOD = dict(PIT, step='commit')


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


def test_the_first_step_starts_on_its_defaults_with_every_archetype_and_blurb(web):
    text = call(web, 'GET', '/create/')[2].decode()
    assert '<button type="submit" name="step" value="who">' in text
    assert '<input type="number" name="age" min="17" max="45" value="22">' in text
    assert '<option value="ace" selected>' in text          # the position starts on Pitcher, so the archetype does too
    assert 'Contact hitter (hitter)' in text and 'Power ace (pitcher)' in text
    assert text.count('<li><b>') == len(create.ARCHETYPES)
    assert '<input type="radio" name="mode" value="realistic" checked>' in text
    assert 'Sandbox: no budget or age limits.' in text and 'Realistic: the budget is 50 Now' in text


def test_bare_path_moves_and_strangers_are_refused(web):
    status, headers, _ = call(web, 'GET', '/create')
    assert status == 301 and headers['Location'] == '/create/'
    assert call(web, 'GET', '/nope')[0] == 404
    status, headers, _ = call(web, 'PUT', '/create/')
    assert status == 405 and headers['Allow'] == 'GET, HEAD, POST'


def test_head_has_headers_and_no_body(web):
    status, _, body = call(web, 'HEAD', '/create/')
    assert status == 200 and body == b''


def test_who_step_moves_to_the_ratings_prefilled_from_the_archetype(web):
    status, _, body = post(web, dict(WHO_PIT, step='who'))
    text = body.decode()
    assert status == 200
    assert 'Preview the card' in text and 'name="step" value="back"' in text
    assert '<option value="75" selected>' in text           # the ace's fastball Now
    assert 'Now: 75 of 80 points; Ceiling: 95 of 110 points.' in text
    assert '<input type="hidden" name="archetype" value="ace">' in text
    assert '<input type="hidden" name="first" value="Al">' in text


def test_a_post_with_no_step_is_the_first_step(web):
    assert 'Preview the card' in post(web, WHO_PIT)[2].decode()


def test_who_step_errors_are_422_on_step_one(web):
    status, _, body = post(web, dict(WHO_PIT, step='who', first='', archetype='contact'))
    text = body.decode()
    assert status == 422
    assert 'Enter a first name.' in text and 'Pick an archetype for this position.' in text
    assert 'name="step" value="who"' in text


def test_back_returns_to_step_one_with_the_values_posted(web):
    status, _, body = post(web, dict(PIT, step='back', first='Zed'))
    text = body.decode()
    assert status == 200
    assert 'value="Zed"' in text and '<option value="ace" selected>' in text and 'name="p_FB_now"' not in text
    assert '<option value="P" selected>' in text and 'name="step" value="who"' in text


def test_edit_keeps_the_posted_ratings_not_the_archetypes(web):
    status, _, body = post(web, dict(HIT, step='edit', now_contact='75', ceil_contact='75'))
    text = body.decode()
    assert status == 200
    assert text.count('<option value="75" selected>') == 2          # contact's Now and Ceiling, as posted
    assert 'Preview the card' in text


def test_edit_with_a_bad_who_is_422_on_step_one(web):
    status, _, body = post(web, dict(HIT, step='edit', first='<x>'))
    text = body.decode()
    assert status == 422 and NAME_MSG in text and 'name="step" value="who"' in text


def test_ratings_step_previews_the_card_with_its_bars_and_comparison(web, site):
    game, data, _, _, _ = site
    status, _, body = post(web, dict(HIT, step='ratings'))
    text = body.decode()
    assert status == 200
    assert 'Sign him into the pool' in text and 'Edit ratings' in text
    assert 'width:66.7%' in text                             # contact at 60: (60 - 20) / 60 of the bar
    assert 'Pat Doe' in text and 'B/T R/R &middot; age 24' in text and '1977 Major Leagues' in text
    assert 'Plays like: no close match in this association.' in text     # no shortstop in the pool
    assert '<input type="hidden" name="now_contact" value="60">' in text
    assert not data.joinpath('created').exists()


def test_the_preview_carries_only_the_form_fields_never_extra_posted_keys(web):
    status, _, body = post(web, dict(HIT, step='ratings', **{'"><script>x</script>': '1', 'extra': 'y'}))
    text = body.decode()
    assert status == 200
    assert '<script>x' not in text and 'name="extra"' not in text
    assert '<input type="hidden" name="assn" value="TEST77">' in text and 'name="step"' not in text.split('<button')[0]


def test_plays_like_names_the_closest_real_player(web):
    text = post(web, dict(HIT, step='ratings', pos='2B'))[2].decode()
    assert 'Plays like: Pat Doe (free agent, age 25)' in text


def test_the_card_shows_a_pitchers_arsenal_in_slot_order_and_strikeout_as_one_number(web):
    text = post(web, dict(PIT, step='ratings'))[2].decode()
    assert text.index('Fastball') < text.index('Slider')
    assert '<span class="nums">70</span>' in text
    assert 'Fastball' in text and 'Changeup' not in text


def test_ratings_errors_are_422_on_step_two(web):
    status, _, body = post(web, dict(HIT, step='ratings', now_contact='52'))
    text = body.decode()
    assert status == 422
    assert 'Pick a grade from 20 to 80, in steps of 5.' in text and 'Preview the card' in text


def test_a_ceiling_below_its_now_is_422(web):
    status, _, body = post(web, dict(HIT, step='ratings', ceil_contact='55'))
    assert status == 422 and 'Ceiling must be at least Now.' in body.decode()


def test_a_budget_over_shows_above_the_rows(web):
    now80 = {k: '80' for k in HIT if k.startswith(('now_', 'ceil_')) and 'strikeout' not in k}
    status, _, body = post(web, dict(HIT, step='ratings', **now80))
    text = body.decode()
    assert status == 422
    assert 'Over the realistic budget: Now uses 150 of 50 points.' in text
    assert text.index('Over the realistic budget') < text.index('name="now_contact"')


def test_sandbox_skips_the_budget_line_and_the_limits(web):
    status, _, body = post(web, dict(WHO_HIT, mode='sandbox', step='who'))
    assert status == 200 and 'Now: ' not in body.decode()
    now80 = {k: '80' for k in HIT if k.startswith(('now_', 'ceil_')) and 'strikeout' not in k}
    assert post(web, dict(HIT, mode='sandbox', age='27', step='ratings', **now80))[0] == 200


def test_the_pitcher_arsenal_needs_two_to_five_pitches(web):
    status, _, body = post(web, dict(PIT, step='ratings', p_SL_now='none', p_SL_ceil='none'))
    assert status == 422 and 'Pick 2 to 5 pitches.' in body.decode()


def test_the_realistic_gap_is_422_with_the_age_in_the_message(web):
    status, _, body = post(web, dict(HIT, step='ratings', age='27', ceil_contact='70'))
    assert status == 422 and 'At 27 a ceiling can be at most 5 above Now.' in body.decode()


def test_unknown_step_starts_again_on_step_one(web):
    status, _, body = post(web, dict(HIT, step='jump'))
    text = body.decode()
    assert status == 422 and 'Start again.' in text and 'name="step" value="who"' in text


def test_good_commit_creates_the_player_redirects_and_writes_the_ledger(web, site):
    game, data, backup, _, _ = site
    status, headers, _ = post(web, GOOD)
    assert status == 303
    assert headers['Location'] == '/create/done?assn=TEST77&pid=206'
    _, recs = create.decipher((game / 'Assn' / 'TEST77.PYR').read_bytes())
    assert [r[0] | r[1] << 8 for r in recs] == [100, 205, 206]
    assert create.pyf_ids((game / 'Assn' / 'TEST77.PYF').read_bytes()) == [100, 205, 206]
    assert any(backup.iterdir())
    ledger = json.loads((data / 'created' / 'TEST77.json').read_text())
    assert [(e['pid'], e['name'], e['pos'], e['assn'], e['archetype'], e['mode']) for e in ledger] == [
        (206, 'Pat Doe', 'SS', 'TEST77', 'regular', 'realistic')]


def test_a_pitcher_commit_writes_his_thrown_pitches_and_zeroes_the_rest(web, site):
    game = site[0]
    status, _, _ = post(web, PITCH_GOOD)
    assert status == 303
    _, recs = create.decipher((game / 'Assn' / 'TEST77.PYR').read_bytes())
    rec = recs[-1]
    assert rec[68] == 1 and rec[0x5d + 7] == create.rating(70)
    assert all(rec[0x5d + i] == 0 and rec[0x46 + i] == 0 for i in (8, 9, 11, 12, 13))


def test_sandbox_commit_records_the_mode_in_the_ledger(web, site):
    _, data = site[0], site[1]
    now80 = {k: '80' for k in HIT if k.startswith(('now_', 'ceil_')) and 'strikeout' not in k}
    assert post(web, dict(HIT, step='commit', mode='sandbox', age='27', **now80))[0] == 303
    ledger = json.loads((data / 'created' / 'TEST77.json').read_text())
    assert ledger[-1]['mode'] == 'sandbox'


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


def test_a_bad_name_is_422_with_the_form_back_and_the_value_escaped(web):
    status, _, body = post(web, dict(GOOD, first='<script>'))
    text = body.decode()
    assert status == 422
    assert NAME_MSG in text
    assert '&lt;script&gt;' in text and '<script>' not in text      # echoed back into the hidden input, escaped
    assert 'name="pos" value="SS"' in text and 'name="age" value="24"' in text and 'name="last" value="Doe"' in text


def test_a_bad_grade_is_422_beside_its_row_with_the_form_back(web):
    status, _, body = post(web, dict(GOOD, now_contact='52'))
    text = body.decode()
    assert status == 422 and 'Pick a grade from 20 to 80, in steps of 5.' in text
    assert 'name="first" value="Pat"' in text and 'name="archetype" value="regular"' in text


def test_an_open_association_is_409_and_the_files_are_untouched(web, site):
    game, data, backup, _, proc = site
    pyr = game / 'Assn' / 'TEST77.PYR'
    before = pyr.read_bytes()
    (proc / '99' / 'fd').mkdir(parents=True)
    os.symlink(pyr, proc / '99' / 'fd' / '3')
    status, _, body = post(web, GOOD)
    text = html.unescape(body.decode())
    assert status == 409
    assert '1977 Major Leagues is open in the game. Go back to the game' in text
    assert 'Preview the card' in text
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
