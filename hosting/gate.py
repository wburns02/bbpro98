#!/usr/bin/env python3
"""PIN gate for the hosted game: nginx asks it, per request, whether the visitor has signed in.

    python3 hosting/gate.py --pin-file ~/.config/bbpro98/gate_pin --secret-file ~/.config/bbpro98/gate_secret

Listens on 127.0.0.1:6154 (behind hosting/nginx.conf, which is the only thing the tunnel reaches):

    GET  /gate/auth     204 with a valid sign-in cookie, else 401 (nginx auth_request)
    GET  /gate/login    the PIN form
    POST /gate/login    checks the PIN; sets the cookie and redirects to `next`
    GET  /gate/logout   revokes the sign-in cookie it was sent (a copy of it stops working too) and clears it

The PIN and the cookie-signing secret live in files outside the repo (the secret is made on first run, mode 600);
revoked sign-ins are kept beside the secret in <secret-file>.revoked until they would have expired.
A PIN is short, so wrong guesses are rate limited per visitor (X-Real-IP, which nginx sets from Cloudflare's
CF-Connecting-IP) and in total: past GLOBAL_FAILS wrong PINs in an hour, a login waits out the hour. A browser that
signed in before carries a signed device cookie (bbdev, Path=/gate, a year) and has a pool of its own instead
(DEVICE_FAILS an hour for that one cookie), so strangers guessing from many addresses cannot lock the owner out, a
copied device cookie buys at most DEVICE_FAILS guesses an hour, and it can only use up its own pool, never another
browser's; the per-visitor limit applies to both. Device cookies are bound to the PIN: a new PIN voids them all.
"""
import argparse
import hashlib
import hmac
import html
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse

COOKIE = 'bbgate'
MAX_AGE = 30 * 86400                 # seconds a sign-in lasts
DEVICE_COOKIE = 'bbdev'
DEVICE_AGE = 365 * 86400             # seconds a browser that signed in stays exempt from the global limit
IP_FAILS, IP_WINDOW = 5, 900         # wrong PINs per visitor per window (seconds)
GLOBAL_FAILS, GLOBAL_WINDOW = 30, 3600
DEVICE_FAILS = 5                     # wrong PINs an hour from one device cookie (counted per cookie)
MAX_BODY = 1024

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>BBPro '98</title>
<style>
:root {{ --bg: #f4efe4; --fg: #2b241b; --muted: #75695a; --line: #cdbfa8; --accent: #7a2e1d; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1d1914; --fg: #efe6d6; --muted: #a89a86; --line: #4a4033;
  --accent: #e0896f; }} }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--fg);
  font: 16px/1.4 Georgia, 'Times New Roman', serif; padding: 0 16px; }}
form {{ display: grid; gap: 12px; width: min(100%, 280px); text-align: center; }}
h1 {{ font-size: 1.5rem; margin: 0; letter-spacing: .02em; }}
p {{ margin: 0; color: var(--muted); font-size: .9rem; }}
input {{ font: inherit; font-size: 1.6rem; letter-spacing: .4em; text-align: center; padding: 8px; border: 1px solid
  var(--line); border-radius: 4px; background: transparent; color: var(--fg); }}
button {{ font: inherit; padding: 8px; border: 0; border-radius: 4px; background: var(--accent); color: var(--bg);
  cursor: pointer; }}
.err {{ color: var(--accent); }}
</style></head><body>
<form method="post" action="/gate/login">
<h1>BBPro '98</h1>
<p>Enter the PIN.</p>
<input name="pin" type="password" inputmode="numeric" autocomplete="current-password" maxlength="32" autofocus
  aria-label="PIN">
<input type="hidden" name="next" value="{next}">
<button type="submit">Play ball</button>
{msg}
</form></body></html>"""


def safe_next(v):
    """A same-site path to return to after sign-in; anything else (another host, a scheme) becomes '/'."""
    if not v or not v.startswith('/') or v.startswith('//') or '\\' in v or any(ord(c) < 32 for c in v):
        return '/'
    return v


class Gate:
    def __init__(self, pin, secret, now=time.time, revoked_path=None):
        self.pin = pin.encode()
        self.secret = secret
        self.now = now
        self.fails = {}              # ip -> [times]
        self.all_fails = []
        self.device_fails = {}       # device cookie signature -> [times]
        self.lock = threading.Lock()
        self.revoked_path = revoked_path
        self.revoked = self._load_revoked()      # sig -> exp of signed-out sign-ins

    def _sign(self, kind, exp):
        return hmac.new(self.secret, (kind + exp).encode(), hashlib.sha256).hexdigest()

    def _check(self, kind, tok):
        exp, _, sig = (tok or '').partition('.')
        if not exp.isdigit() or len(exp) > 12 or not sig:
            return None
        return sig if hmac.compare_digest(sig, self._sign(kind, exp)) and int(exp) > self.now() else None

    def token(self):
        exp = str(int(self.now()) + MAX_AGE)
        return exp + '.' + self._sign('', exp)

    def _device_kind(self):
        # Bound to the PIN: changing the PIN voids every device cookie, so one minted while someone knew the old PIN
        # buys no guesses at the new one.
        return 'dev:%s:' % hashlib.sha256(self.pin).hexdigest()

    def device_token(self):
        exp = str(int(self.now()) + DEVICE_AGE)
        return exp + '.' + self._sign(self._device_kind(), exp)

    def valid(self, tok):
        sig = self._check('', tok)
        if sig is None:
            return False
        with self.lock:
            return sig not in self.revoked

    def device(self, tok):
        """The id (signature) of a device cookie this gate signed and that has not expired, else None: a browser that
        signed in before. Only a correct PIN mints one, so the per-device table is bounded by real sign-ins."""
        return self._check(self._device_kind(), tok)

    def _load_revoked(self):
        try:
            with open(self.revoked_path, encoding='utf-8') as f:
                obj = json.load(f)
        except (TypeError, OSError, ValueError):
            return {}
        now = self.now()
        return {k: v for k, v in obj.items() if isinstance(k, str) and type(v) is int and v > now} \
            if isinstance(obj, dict) else {}

    def revoke(self, tok):
        """Signs out one sign-in cookie for good: True when tok was valid. Only a valid cookie can be revoked, so the
        list is bounded by real sign-ins; entries drop once they would have expired anyway."""
        sig = self._check('', tok)
        if sig is None:
            return False
        with self.lock:
            now = self.now()
            self.revoked = {k: v for k, v in self.revoked.items() if v > now}
            self.revoked[sig] = int(tok.partition('.')[0])
            if self.revoked_path:
                tmp = self.revoked_path + '.tmp'
                try:
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(self.revoked, f)
                    os.replace(tmp, self.revoked_path)
                except OSError as e:     # still revoked until a restart; signing out must not fail on a full disk
                    print('gate: cannot save %s: %s' % (self.revoked_path, e), flush=True)
        return True

    def _recent(self, times, window):
        t = self.now() - window
        return [x for x in times if x > t]

    def _blocked(self, ip, device=None):
        self.all_fails = self._recent(self.all_fails, GLOBAL_WINDOW)
        if device is not None:
            dev = self._recent(self.device_fails.get(device, []), GLOBAL_WINDOW)
            if dev:
                self.device_fails[device] = dev
            else:
                self.device_fails.pop(device, None)
        mine = self._recent(self.fails.get(ip, []), IP_WINDOW)
        if mine:
            self.fails[ip] = mine
        else:
            self.fails.pop(ip, None)
        if device is not None:
            return len(mine) >= IP_FAILS or len(dev) >= DEVICE_FAILS
        return len(mine) >= IP_FAILS or len(self.all_fails) >= GLOBAL_FAILS

    def blocked(self, ip, device=None):
        with self.lock:
            return self._blocked(ip, device)

    def attempt(self, ip, pin, device=None):
        """'ok', 'wrong' or 'blocked'. The limit check, the comparison and the count of a wrong PIN happen under one
        lock, so parallel guesses cannot all pass the check before any of them is counted. Wrong PINs are capped at
        GLOBAL_FAILS an hour, which also bounds the per-visitor table; a known browser (device, from Gate.device) is
        held to DEVICE_FAILS of its own instead."""
        with self.lock:
            if self._blocked(ip, device):
                return 'blocked'
            if hmac.compare_digest(pin.encode(), self.pin):
                return 'ok'
            t = self.now()
            self.fails.setdefault(ip, []).append(t)
            if device is not None:
                self.device_fails.setdefault(device, []).append(t)
            else:
                self.all_fails.append(t)
            return 'wrong'


def cookie_of(header, name=COOKIE):
    for part in (header or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == name:
            return v
    return None


def handler(gate):
    class H(http.server.BaseHTTPRequestHandler):
        server_version = 'gate'
        sys_version = ''

        def log_message(self, fmt, *args):
            pass

        def _ip(self):
            return self.headers.get('X-Real-IP') or self.client_address[0]

        def _send(self, code, body=b'', headers=()):
            self.send_response(code)
            for k, v in headers:
                self.send_header(k, v)
            if body:
                self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if body and self.command != 'HEAD':
                self.wfile.write(body)

        def _form(self, code, nxt, msg=''):
            m = '<p class="err" role="alert">%s</p>' % html.escape(msg) if msg else ''
            self._send(code, PAGE.format(next=html.escape(safe_next(nxt), quote=True), msg=m).encode(),
                       [('X-Frame-Options', 'DENY'), ('Content-Security-Policy', "default-src 'none'; "
                         "style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")])

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            if u.path == '/gate/auth':
                self._send(204 if gate.valid(cookie_of(self.headers.get('Cookie'))) else 401)
            elif u.path == '/gate/login':
                self._form(200, urllib.parse.parse_qs(u.query).get('next', ['/'])[0])
            elif u.path == '/gate/logout':
                gate.revoke(cookie_of(self.headers.get('Cookie')))
                self._send(303, headers=[('Location', '/gate/login'), ('Set-Cookie', '%s=; Path=/; Max-Age=0; '
                                          'HttpOnly; Secure; SameSite=Lax' % COOKIE)])
            else:
                self._send(404)

        def do_POST(self):
            if urllib.parse.urlsplit(self.path).path != '/gate/login':
                return self._send(404)
            try:
                n = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                n = -1
            if not 0 <= n <= MAX_BODY:
                return self._send(413)
            f = urllib.parse.parse_qs(self.rfile.read(n).decode('utf-8', 'replace'))
            nxt = f.get('next', ['/'])[0]
            device = gate.device(cookie_of(self.headers.get('Cookie'), DEVICE_COOKIE))
            got = gate.attempt(self._ip(), f.get('pin', [''])[0].strip(), device)
            if got == 'blocked':
                return self._form(429, nxt, 'Too many wrong PINs. Try again later.')
            if got != 'ok':
                return self._form(401, nxt, 'Wrong PIN.')
            self._send(303, headers=[('Location', safe_next(nxt)),
                                     ('Set-Cookie', '%s=%s; Path=/gate; Max-Age=%d; HttpOnly; Secure; '
                                      'SameSite=Strict' % (DEVICE_COOKIE, gate.device_token(), DEVICE_AGE)),
                                     ('Set-Cookie', '%s=%s; Path=/; Max-Age=%d; '
                                      'HttpOnly; Secure; SameSite=Lax' % (COOKIE, gate.token(), MAX_AGE))])

    return H


def load_secret(path):
    try:
        with open(path, 'rb') as f:
            s = f.read()
        if len(s) >= 32:
            return s
    except FileNotFoundError:
        pass
    s = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(s)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--pin-file', required=True)
    ap.add_argument('--secret-file', required=True)
    ap.add_argument('--port', type=int, default=6154)
    a = ap.parse_args(argv)
    with open(a.pin_file) as f:
        pin = f.read().strip()
    if len(pin) < 4:
        raise SystemExit('PIN file must hold a PIN of at least 4 characters')
    g = Gate(pin, load_secret(a.secret_file), revoked_path=a.secret_file + '.revoked')
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', a.port), handler(g))
    srv.serve_forever()


if __name__ == '__main__':
    main()
