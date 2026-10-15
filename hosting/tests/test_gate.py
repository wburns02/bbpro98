"""hosting/gate.py: the PIN check, the signed cookie, the rate limits and the HTTP surface, on a real local server."""
import http.client
import os
import sys
import threading
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate  # noqa: E402

SECRET = b's' * 32


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def test_token_round_trip_and_expiry():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    tok = g.token()
    assert g.valid(tok)
    assert not g.valid(tok[:-1] + ('0' if tok[-1] != '0' else '1'))
    assert not gate.Gate('4321', b'x' * 32, now=c).valid(tok)
    assert not g.valid('') and not g.valid(None) and not g.valid('abc.def') and not g.valid('123')
    c.t += gate.MAX_AGE + 1
    assert not g.valid(tok)


def test_forged_expiry_rejected():
    g = gate.Gate('4321', SECRET, now=Clock())
    exp, _, sig = g.token().partition('.')
    assert not g.valid(str(int(exp) + 10 ** 6) + '.' + sig)


def test_per_ip_limit_then_window_expires():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    for _ in range(gate.IP_FAILS):
        assert g.attempt('1.1.1.1', '0000') == 'wrong'
    assert g.attempt('1.1.1.1', '4321') == 'blocked'           # even the right PIN waits out the window
    assert g.attempt('2.2.2.2', '4321') == 'ok'
    c.t += gate.IP_WINDOW + 1
    assert not g.blocked('1.1.1.1')
    assert g.attempt('1.1.1.1', '4321') == 'ok'


def test_parallel_guesses_cannot_pass_the_limit():
    g = gate.Gate('4321', SECRET, now=Clock())
    out, start = [], threading.Barrier(40)

    def guess(i):
        start.wait()
        out.append(g.attempt('1.1.1.1', '%04d' % i))

    ts = [threading.Thread(target=guess, args=(i,)) for i in range(40)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert out.count('wrong') == gate.IP_FAILS and out.count('blocked') == 40 - gate.IP_FAILS


def test_global_limit_across_addresses():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    for i in range(gate.GLOBAL_FAILS):
        assert g.attempt('10.0.%d.%d' % (i // 250, i % 250), '9999') == 'wrong'
    assert g.blocked('9.9.9.9')
    c.t += gate.GLOBAL_WINDOW + 1
    assert not g.blocked('9.9.9.9')


@pytest.mark.parametrize('v,want', [('/news/14L1875', '/news/14L1875'), ('/', '/'), ('', '/'), (None, '/'),
                                    ('//evil.example', '/'), ('https://evil.example', '/'), ('/\\evil', '/'),
                                    ('/a\r\nSet-Cookie: x=1', '/')])
def test_safe_next(v, want):
    assert gate.safe_next(v) == want


def test_cookie_of():
    assert gate.cookie_of('a=1; bbgate=xyz; b=2') == 'xyz'
    assert gate.cookie_of('a=1') is None and gate.cookie_of(None) is None


@pytest.fixture
def server():
    g = gate.Gate('4321', SECRET)
    srv = gate.http.server.ThreadingHTTPServer(('127.0.0.1', 0), gate.handler(g))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    h = dict(headers or {})
    if body is not None:
        body = urllib.parse.urlencode(body)
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read().decode()


def test_http_flow(server):
    assert req(server, 'GET', '/gate/auth')[0] == 401
    code, _, page = req(server, 'GET', '/gate/login?next=/news/%22%3E%3Cscript%3E')
    assert code == 200 and '<script>' not in page and 'name="pin"' in page
    code, _, page = req(server, 'POST', '/gate/login', {'pin': '0000', 'next': '/news'}, {'X-Real-IP': '5.5.5.5'})
    assert code == 401 and 'Wrong PIN' in page
    code, h, _ = req(server, 'POST', '/gate/login', {'pin': '4321', 'next': '//evil.example'}, {'X-Real-IP': '5.5.5.5'})
    assert code == 303 and h['Location'] == '/'
    cookie = h['Set-Cookie']
    for flag in ('HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/'):
        assert flag in cookie
    tok = cookie.split(';')[0]
    assert req(server, 'GET', '/gate/auth', headers={'Cookie': tok})[0] == 204
    code, h, _ = req(server, 'GET', '/gate/logout')
    assert code == 303 and 'Max-Age=0' in h['Set-Cookie']
    assert req(server, 'GET', '/elsewhere')[0] == 404
    assert req(server, 'POST', '/gate/login', {'pin': 'x' * 2000})[0] == 413


def test_http_lockout(server):
    for _ in range(gate.IP_FAILS):
        req(server, 'POST', '/gate/login', {'pin': '1111'}, {'X-Real-IP': '6.6.6.6'})
    code, _, page = req(server, 'POST', '/gate/login', {'pin': '4321'}, {'X-Real-IP': '6.6.6.6'})
    assert code == 429 and 'Too many' in page
    assert req(server, 'POST', '/gate/login', {'pin': '4321'}, {'X-Real-IP': '7.7.7.7'})[0] == 303


def test_known_browser_skips_the_global_limit_only():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    dev = g.device(g.device_token())
    for i in range(gate.GLOBAL_FAILS):
        g.attempt('10.0.%d.%d' % (i // 250, i % 250), '9999')
    assert g.attempt('9.9.9.9', '4321') == 'blocked'
    assert dev and g.attempt('9.9.9.9', '4321', dev) == 'ok'
    for _ in range(gate.IP_FAILS):
        g.attempt('8.8.8.8', '0000', g.device(g.device_token()))
    assert g.attempt('8.8.8.8', '4321', dev) == 'blocked'          # the per-visitor limit still holds


def test_copied_device_cookie_uses_up_only_its_own_pool():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    stolen = g.device(g.device_token())
    c.t += 1
    owner = g.device(g.device_token())
    assert stolen != owner
    for i in range(gate.DEVICE_FAILS):                              # one guess per address, so no per-IP limit
        assert g.attempt('10.9.0.%d' % i, '0000', stolen) == 'wrong'
    assert g.attempt('10.9.1.1', '4321', stolen) == 'blocked'
    assert g.attempt('10.9.1.2', '4321', owner) == 'ok'             # the owner's browser is untouched
    assert g.attempt('10.9.1.3', '4321') == 'ok'                    # and so is the strangers' pool
    c.t += gate.GLOBAL_WINDOW + 1
    assert g.attempt('10.9.1.1', '4321', stolen) == 'ok'
    assert g.device_fails == {}


def test_device_token_is_not_a_session_and_vice_versa():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    dev, tok = g.device_token(), g.token()
    assert not g.valid(dev) and g.device(tok) is None
    assert gate.Gate('4321', b'x' * 32, now=c).device(dev) is None
    assert g.device('') is None and g.device(None) is None and g.device('9' * 40 + '.ab') is None
    c.t += gate.DEVICE_AGE + 1
    assert g.device(dev) is None


def test_revoke_survives_a_restart_and_expires(tmp_path):
    c = Clock()
    path = str(tmp_path / 'secret.revoked')
    g = gate.Gate('4321', SECRET, now=c, revoked_path=path)
    tok = g.token()
    c.t += 1
    other = g.token()
    assert g.revoke(tok) and not g.valid(tok) and g.valid(other)
    assert not g.revoke('123.abc') and not g.revoke(None)
    assert oct(os.stat(path).st_mode & 0o777) == '0o600'
    g2 = gate.Gate('4321', SECRET, now=c, revoked_path=path)
    assert not g2.valid(tok) and g2.valid(other)
    c.t += gate.MAX_AGE + 5
    g3 = gate.Gate('4321', SECRET, now=c, revoked_path=path)
    assert g3.revoked == {}


def test_revoked_file_damaged_or_missing(tmp_path):
    path = tmp_path / 'r'
    assert gate.Gate('4321', SECRET, now=Clock(), revoked_path=str(path)).revoked == {}
    for junk in ('not json', '[1, 2]', '{"a": "x", "b": 1.5}'):
        path.write_text(junk)
        assert gate.Gate('4321', SECRET, now=Clock(), revoked_path=str(path)).revoked == {}


def test_http_logout_revokes_and_device_cookie(server):
    code, h, _ = req(server, 'POST', '/gate/login', {'pin': '4321', 'next': '/news'}, {'X-Real-IP': '5.5.5.6'})
    assert code == 303
    tok = h['Set-Cookie'].split(';')[0]
    assert req(server, 'GET', '/gate/auth', headers={'Cookie': tok})[0] == 204
    code, h, _ = req(server, 'GET', '/gate/logout', headers={'Cookie': tok})
    assert code == 303 and 'Max-Age=0' in h['Set-Cookie']
    assert req(server, 'GET', '/gate/auth', headers={'Cookie': tok})[0] == 401      # a saved copy is dead too


def test_http_device_cookie_flags_and_global_bypass(server):
    c = http.client.HTTPConnection('127.0.0.1', server, timeout=5)
    c.request('POST', '/gate/login', body='pin=4321', headers={'Content-Type': 'application/x-www-form-urlencoded',
                                                               'X-Real-IP': '5.5.5.7'})
    r = c.getresponse()
    r.read()
    cookies = r.msg.get_all('Set-Cookie')
    dev = [v for v in cookies if v.startswith(gate.DEVICE_COOKIE + '=')]
    assert len(cookies) == 2 and len(dev) == 1
    for flag in ('HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/gate', 'Max-Age=%d' % gate.DEVICE_AGE):
        assert flag in dev[0]
    devc = dev[0].split(';')[0]
    for i in range(gate.GLOBAL_FAILS):
        req(server, 'POST', '/gate/login', {'pin': '9999'}, {'X-Real-IP': '10.1.%d.%d' % (i // 250, i % 250)})
    assert req(server, 'POST', '/gate/login', {'pin': '4321'}, {'X-Real-IP': '5.5.5.8'})[0] == 429
    assert req(server, 'POST', '/gate/login', {'pin': '4321'}, {'X-Real-IP': '5.5.5.8', 'Cookie': devc})[0] == 303
    forged = devc[:-1] + ('0' if devc[-1] != '0' else '1')
    assert req(server, 'POST', '/gate/login', {'pin': '4321'}, {'X-Real-IP': '5.5.5.9', 'Cookie': forged})[0] == 429


def test_revoke_with_unwritable_file_still_signs_out(tmp_path):
    g = gate.Gate('4321', SECRET, now=Clock(), revoked_path=str(tmp_path / 'no' / 'such' / 'dir'))
    tok = g.token()
    assert g.revoke(tok) and not g.valid(tok)


def test_new_pin_voids_device_cookies():
    c = Clock()
    dev = gate.Gate('4321', SECRET, now=c).device_token()
    assert gate.Gate('4321', SECRET, now=c).device(dev)
    assert gate.Gate('8765', SECRET, now=c).device(dev) is None
