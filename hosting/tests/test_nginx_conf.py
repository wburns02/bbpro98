"""hosting/nginx.conf: every route the tunnel can reach asks the PIN gate first. A structural check of the config
text (no nginx needed), so a new location cannot be added without the gate check."""
import os
import re

CONF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'nginx.conf')


def locations():
    """{location header: body} for the server block. Bodies here never nest braces."""
    with open(CONF, encoding='utf-8') as f:
        text = re.sub(r'#[^\n]*', '', f.read())
    return {' '.join(m.group(1).split()): m.group(2) for m in re.finditer(r'location\s+([^{]+?)\s*\{([^{}]*)\}', text)}


def test_only_the_gate_itself_is_reachable_without_the_cookie():
    locs = locations()
    open_ones = sorted(k for k, body in locs.items() if 'auth_request' not in body)
    assert open_ones == ['/gate/', '= /_gate_auth', '= /gate/auth', '@login']
    assert re.search(r'\binternal\s*;', locs['= /_gate_auth'])
    assert 'proxy_pass' not in locs['@login']
    for k, body in locs.items():
        if 'auth_request' in body:
            assert re.search(r'auth_request\s+/_gate_auth\s*;', body), k
            assert re.search(r'error_page\s+401\s*=\s*@login\s*;', body), k


def test_the_cookie_oracle_is_not_public():
    # /gate/auth is for nginx's own subrequest (/_gate_auth, internal); from outside it only answers "is this cookie
    # valid" with no rate limit.
    body = locations().get('= /gate/auth', '')
    assert re.search(r'return\s+404\s*;', body) and 'proxy_pass' not in body


def test_the_game_page_cannot_be_framed_by_another_site():
    # SameSite=Lax keeps the cookie out of cross-site frames but not out of frames on sibling subdomains (same site).
    assert re.search(r'add_header\s+X-Frame-Options\s+SAMEORIGIN\s+always\s*;', locations()['/'])


def test_binds_loopback_only():
    with open(CONF, encoding='utf-8') as f:
        listens = re.findall(r'^\s*listen\s+([^;]+);', f.read(), re.M)
    assert listens and all(x.startswith('127.0.0.1:') for x in listens)
