"""Holdouts for the two places hostile input arrives: the Mods spool the sandboxed game writes into
(news/modbridge.py) and the PIN gate in front of the hosted game (hosting/gate.py). Offline; the gate test servers bind
an OS-chosen port on 127.0.0.1."""
import http.client
import os
import stat
import threading
import types
import urllib.parse

import pytest

import gate
import modbridge

CTX = types.SimpleNamespace(game='', data='', backup='', donor='', db=None, templates=None, proc='/nonexistent')
RID_BAD, RID_OK, RID_FIFO = '0000a001', '0000a002', '0000a003'


def reply(spool, rid):
    with open(os.path.join(spool, 'r%s.rsp' % rid), 'rb') as fh:
        head, _, body = fh.read().decode('latin-1').partition('\r\n\r\n')
    return dict(line.split('=', 1) for line in head.split('\r\n')), body


def check_spool_behind_a_symlink_is_refused_and_nothing_is_answered(tmp_path):
    """Guards: the descriptor walk with O_NOFOLLOW. The game side can swap the spool directory for a symlink; the
    bridge must not read requests from, or write replies into, the directory it points at."""
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / ('q%s.req' % RID_OK)).write_bytes(b'op=ping\n')
    spool = tmp_path / 'spool'
    os.symlink(elsewhere, spool)
    with pytest.raises(OSError):
        modbridge.process_spool(CTX, str(spool))
    with pytest.raises(OSError):
        modbridge.beat(str(spool))
    assert sorted(p.name for p in elsewhere.iterdir()) == ['q%s.req' % RID_OK]
    assert modbridge.spool_ok(str(tmp_path)) is False                     # no Mods/spool at all


def check_planted_symlinks_and_fifos_in_the_spool_are_never_followed(tmp_path):
    """Guards: a request that is a symlink to a host file (would leak it into a reply), a reply temp name planted as a
    symlink (would overwrite the target), and a FIFO request (would block the bridge forever)."""
    secret = tmp_path / 'secret.txt'
    secret.write_bytes(b'op=ping\nnote=SECRET-TOKEN-1234\n')           # a valid request, so a followed link would be answered
    victim = tmp_path / 'victim.txt'
    victim.write_bytes(b'precious')
    spool = tmp_path / 'spool'
    spool.mkdir()
    os.symlink(secret, spool / ('q%s.req' % RID_BAD))
    (spool / ('q%s.req' % RID_OK)).write_bytes(b'op=ping\n')
    os.symlink(victim, spool / ('r%s.tmp' % RID_OK))
    os.mkfifo(spool / ('q%s.req' % RID_FIFO))
    worker = threading.Thread(target=modbridge.process_spool, args=(CTX, str(spool)), daemon=True)
    worker.start()
    worker.join(20)
    assert not worker.is_alive(), 'the bridge blocked on a planted FIFO'
    head, body = reply(str(spool), RID_BAD)
    assert head['status'] == 'error' and 'SECRET' not in body             # the symlinked request read as empty
    head, _ = reply(str(spool), RID_OK)
    assert head['status'] == 'ok'
    assert victim.read_bytes() == b'precious'                              # the planted temp name was not written through
    assert reply(str(spool), RID_FIFO)[0]['status'] == 'error'
    assert not os.path.islink(spool / ('r%s.rsp' % RID_OK))
    leftovers = [p.name for p in spool.iterdir() if p.name.endswith('.work')]
    assert leftovers == []                                                 # claimed work files are removed


def test_spool_never_follows_symlinks_or_fifos_planted_by_the_game_side(tmp_path):
    """Guards: the spool directory walk and the request/reply files inside it."""
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    check_spool_behind_a_symlink_is_refused_and_nothing_is_answered(tmp_path / 'a')
    check_planted_symlinks_and_fifos_in_the_spool_are_never_followed(tmp_path / 'b')


def test_request_parser_rejects_every_malformed_shape():
    """Guards: the 8 KB cap, 100 line cap, key charset, repeated keys, control characters, over-long values and a first
    line that is not op= (the request text becomes ASCII-only handler input)."""
    ok = modbridge.parse_request(b'op=ping\nname=Pat\r\n')
    assert ok == {'op': 'ping', 'name': 'Pat'}
    assert modbridge.parse_request(b'op=ping\n' + b'x' * 9000) is None
    assert modbridge.parse_request(('op=ping\n' + '\n'.join('k%d=1' % i for i in range(100))).encode()) is None
    assert modbridge.parse_request(b'op=ping\nBAD KEY=1') is None
    assert modbridge.parse_request(b'op=ping\n../x=1') is None
    assert modbridge.parse_request(b'op=ping\nk=1\nk=2') is None
    assert modbridge.parse_request(b'op=ping\nk=a\x01b') is None
    assert modbridge.parse_request(('op=ping\nk=' + 'v' * 257).encode()) is None
    assert modbridge.parse_request(b'name=Pat\nop=ping') is None
    assert modbridge.parse_request(b'') is None


# the PIN gate

@pytest.fixture
def served():
    """(gate, port): a Gate with PIN 4242 behind the real handler on an OS-chosen localhost port."""
    clock = [1_000_000.0]
    g = gate.Gate('4242', b's' * 32, now=lambda: clock[0])
    g.clock = clock
    import http.server
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), gate.handler(g))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield g, srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    h = dict(headers or {})
    if body is not None:
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read().decode('utf-8', 'replace')
    out = (r.status, dict((k.lower(), v) for k, v in r.getheaders()), data)
    c.close()
    return out


def login(port, pin, nxt='/', ip='10.0.0.1'):
    body = urllib.parse.urlencode({'pin': pin, 'next': nxt})
    return call(port, 'POST', '/gate/login', body, {'X-Real-IP': ip})


def check_only_the_right_pin_gets_a_cookie_and_only_a_genuine_cookie_passes(served):
    """Guards: a login that accepts a wrong PIN, a cookie missing HttpOnly/Secure/SameSite, and an auth check that
    accepts a forged, tampered, foreign-secret or expired token."""
    g, port = served
    status, headers, _ = login(port, '0000')
    assert status == 401 and 'set-cookie' not in headers
    status, headers, _ = login(port, '4242')
    assert status == 303
    cookie = headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite' in cookie
    token = cookie.split(';')[0].split('=', 1)[1]
    ask = lambda tok: call(port, 'GET', '/gate/auth', headers={'Cookie': 'bbgate=%s' % tok} if tok else {})[0]
    assert ask(token) == 204
    assert ask(None) == 401 and ask('') == 401
    exp, _, sig = token.partition('.')
    assert ask(exp + '.' + '0' * len(sig)) == 401                          # forged signature
    assert ask(str(int(exp) + 86400) + '.' + sig) == 401                   # extended expiry, old signature
    assert ask('9999999999.' + sig) == 401
    other = gate.Gate('4242', b'x' * 32, now=lambda: g.clock[0])
    assert ask(other.token()) == 401                                       # signed with some other secret
    g.clock[0] += gate.MAX_AGE + 1
    assert ask(token) == 401                                               # expired


def check_wrong_pin_lockout_is_per_visitor_and_global(served):
    """Guards: unlimited PIN guessing (a 4 digit PIN falls in minutes), and one visitor's failures locking out others
    more than the global cap says."""
    g, port = served
    for _ in range(gate.IP_FAILS):
        assert login(port, '1111', ip='10.0.0.7')[0] == 401
    status, headers, _ = login(port, '4242', ip='10.0.0.7')                # right PIN, but this visitor is locked
    assert status == 429 and 'set-cookie' not in headers
    assert login(port, '4242', ip='10.0.0.8')[0] == 303                    # another visitor is not
    g.clock[0] += gate.IP_WINDOW + 1
    assert login(port, '4242', ip='10.0.0.7')[0] == 303                    # the window passes
    fresh = gate.Gate('4242', b's' * 32, now=lambda: g.clock[0])
    for i in range(gate.GLOBAL_FAILS):                                     # many addresses, one failure each
        assert fresh.attempt('10.1.%d.%d' % (i // 200, i % 200), 'bad') == 'wrong'
    assert fresh.attempt('10.9.9.9', '4242') == 'blocked'                  # everyone waits out the hour
    g.clock[0] += gate.GLOBAL_WINDOW + 1
    assert fresh.attempt('10.9.9.9', '4242') == 'ok'


def check_login_redirects_stay_on_site_and_the_form_escapes_next(served):
    """Guards: an open redirect after sign-in (//host, https://host, backslash and CRLF tricks) and a reflected
    script in the login form's hidden next field."""
    _, port = served
    for bad in ('//evil.example', 'https://evil.example/x', '/\\evil.example', '/a\r\nSet-Cookie: x=1', 'javascript:1'):
        status, headers, _ = login(port, '4242', nxt=bad)
        assert status == 303 and headers['location'] == '/', repr(bad)
    status, headers, _ = login(port, '4242', nxt='/news/16L1927')
    assert headers['location'] == '/news/16L1927'
    status, _, page = call(port, 'GET', '/gate/login?next=' + urllib.parse.quote('/"><script>alert(1)</script>'))
    assert status == 200 and '<script>alert(1)' not in page
    assert call(port, 'GET', '/gate/nope')[0] == 404
    assert call(port, 'POST', '/gate/login', 'x' * 5000, {'X-Real-IP': '10.0.0.9'})[0] == 413      # body cap


def check_pin_and_secret_files(tmp_path):
    """Guards: starting the gate with a trivially short PIN, a signing secret that is short or world readable, and a
    secret that changes on every start (everyone signed out)."""
    short = tmp_path / 'pin'
    short.write_text('123\n')
    with pytest.raises(SystemExit):
        gate.main(['--pin-file', str(short), '--secret-file', str(tmp_path / 'sec'), '--port', '0'])
    sec = tmp_path / 'secret'
    s1 = gate.load_secret(str(sec))
    assert len(s1) >= 32 and stat.S_IMODE(os.stat(sec).st_mode) == 0o600
    assert gate.load_secret(str(sec)) == s1
    sec.write_bytes(b'tiny')
    s2 = gate.load_secret(str(sec))
    assert len(s2) >= 32 and s2 != b'tiny'


def test_gate_authenticates_only_genuine_cookies_and_limits_guessing(served):
    """Guards: wrong PINs, forged or expired cookies, cookie flags and unlimited PIN guessing."""
    check_only_the_right_pin_gets_a_cookie_and_only_a_genuine_cookie_passes(served)
    check_wrong_pin_lockout_is_per_visitor_and_global(served)


def test_gate_keeps_redirects_on_site_and_refuses_weak_pin_or_secret(served, tmp_path):
    """Guards: open redirect, reflected script in the login form, short PIN, short or world readable secret."""
    check_login_redirects_stay_on_site_and_the_form_escapes_next(served)
    check_pin_and_secret_files(tmp_path)
