#!/usr/bin/env python3
"""PIN gate for the hosted game: nginx asks it, per request, whether the visitor has signed in.

    python3 hosting/gate.py --pin-file ~/.config/bbpro98/gate_pin --secret-file ~/.config/bbpro98/gate_secret

Listens on 127.0.0.1:6154 (behind hosting/nginx.conf, which is the only thing the tunnel reaches):

    GET  /gate/auth     204 with a valid sign-in cookie, else 401 (nginx auth_request)
    GET  /gate/login    the PIN form
    POST /gate/login    checks the PIN; sets the cookie and redirects to `next`
    GET  /gate/logout   clears the cookie

The PIN and the cookie-signing secret live in files outside the repo (the secret is made on first run, mode 600).
A PIN is short, so wrong guesses are rate limited per visitor (X-Real-IP, which nginx sets from Cloudflare's
CF-Connecting-IP) and in total: past GLOBAL_FAILS wrong PINs in an hour, every login waits out the hour.
"""
import argparse
import hashlib
import hmac
import html
import http.server
import os
import secrets
import threading
import time
import urllib.parse

COOKIE = 'bbgate'
MAX_AGE = 30 * 86400                 # seconds a sign-in lasts
IP_FAILS, IP_WINDOW = 5, 900         # wrong PINs per visitor per window (seconds)
GLOBAL_FAILS, GLOBAL_WINDOW = 30, 3600
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
    def __init__(self, pin, secret, now=time.time):
        self.pin = pin.encode()
        self.secret = secret
        self.now = now
        self.fails = {}              # ip -> [times]
        self.all_fails = []
        self.lock = threading.Lock()

    def token(self):
        exp = str(int(self.now()) + MAX_AGE)
        return exp + '.' + hmac.new(self.secret, exp.encode(), hashlib.sha256).hexdigest()

    def valid(self, tok):
        exp, _, sig = (tok or '').partition('.')
        if not exp.isdigit() or not sig:
            return False
        good = hmac.new(self.secret, exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > self.now()

    def _recent(self, times, window):
        t = self.now() - window
        return [x for x in times if x > t]

    def blocked(self, ip):
        with self.lock:
            self.all_fails = self._recent(self.all_fails, GLOBAL_WINDOW)
            mine = self.fails[ip] = self._recent(self.fails.get(ip, []), IP_WINDOW)
            if not mine:
                del self.fails[ip]
            return len(mine) >= IP_FAILS or len(self.all_fails) >= GLOBAL_FAILS

    def check(self, ip, pin):
        """True when the PIN is right. Callers ask blocked() first; a wrong PIN counts against ip and the total."""
        ok = hmac.compare_digest(pin.encode(), self.pin)
        if not ok:
            with self.lock:
                self.fails.setdefault(ip, []).append(self.now())
                self.all_fails.append(self.now())
                if len(self.fails) > 10000:          # bound memory under a spray of addresses
                    self.fails.clear()
        return ok


def cookie_of(header):
    for part in (header or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == COOKIE:
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
            ip = self._ip()
            if gate.blocked(ip):
                return self._form(429, nxt, 'Too many wrong PINs. Try again later.')
            if not gate.check(ip, f.get('pin', [''])[0].strip()):
                return self._form(401, nxt, 'Wrong PIN.')
            self._send(303, headers=[('Location', safe_next(nxt)), ('Set-Cookie', '%s=%s; Path=/; Max-Age=%d; '
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
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', a.port), handler(Gate(pin, load_secret(a.secret_file))))
    srv.serve_forever()


if __name__ == '__main__':
    main()
