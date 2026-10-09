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
        assert not g.blocked('1.1.1.1')
        assert not g.check('1.1.1.1', '0000')
    assert g.blocked('1.1.1.1')
    assert not g.blocked('2.2.2.2')
    c.t += gate.IP_WINDOW + 1
    assert not g.blocked('1.1.1.1')
    assert g.check('1.1.1.1', '4321')


def test_global_limit_across_addresses():
    c = Clock()
    g = gate.Gate('4321', SECRET, now=c)
    for i in range(gate.GLOBAL_FAILS):
        g.check('10.0.%d.%d' % (i // 250, i % 250), '9999')
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
