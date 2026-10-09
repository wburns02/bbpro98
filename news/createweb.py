"""The create-a-player form: a small HTTP service on 127.0.0.1 that nginx serves under /create/, behind the site's
PIN gate. A visitor picks an association and a player's name, position, hand, age and scouting grades;
create.add_player writes him into that association's free agent pool, and the ledger in the data directory lists who
was made. Standard library only. Pages are server.py's; the POST is checked for its origin, length and type before it
is read.
"""
import argparse
import datetime
import http.client
import json
import os
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import create
import gamedata
import server
import watch

PORT = 6155
MAX_BODY = 4096
CAP = 40                    # created players per association
FORM_TYPE = 'application/x-www-form-urlencoded'
ASSN_RE = re.compile(r'[A-Za-z0-9]{1,8}')
PID_RE = re.compile(r'[0-9]{1,5}')
LEDGER_RE = re.compile(r'([A-Za-z0-9]{1,8})\.json')
HEADERS = (
    ('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; "
                                "frame-ancestors 'self'"),
    ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'same-origin'),
    ('Cache-Control', 'no-store'),
)
POSITION_LABELS = {'P': 'Pitcher', 'C': 'Catcher', '1B': 'First base', '2B': 'Second base', '3B': 'Third base',
                   'SS': 'Shortstop', 'LF': 'Left field', 'CF': 'Center field', 'RF': 'Right field'}
BATS_PAIRS = (('L', 'Left'), ('R', 'Right'), ('S', 'Switch'))
THROWS_PAIRS = (('L', 'Left'), ('R', 'Right'))
GRADE_LABELS = {20: '20 poor', 25: '25', 30: '30 well below', 35: '35', 40: '40 below average', 45: '45',
                50: '50 average', 55: '55', 60: '60 plus', 65: '65', 70: '70 plus-plus', 75: '75', 80: '80 elite'}
GRADE_PAIRS = tuple((str(g), GRADE_LABELS[g]) for g in create.GRADES)
GRADE_NAMES = {'contact': 'Contact', 'power': 'Power', 'speed': 'Speed', 'arm': 'Arm', 'fielding': 'Fielding',
               'stamina': 'Stamina', 'control': 'Control', 'strikeout': 'Strikeout', 'stuff': 'Stuff'}
NAV = '<p class="nav"><a href="/create/">Create a player</a> &middot; <a href="/">Back to the game</a></p>'
FORM_CSS = '.field { margin: 0.6em 0; } .field label { display: block; } .error { font-weight: 700; } ' \
           '.note { font-style: italic; }'
_LOCK = threading.Lock()    # one create at a time: the cap count, the write and the ledger go together


def _label(stem, asn):
    """An association's name, the STEM when it has none or its ASN does not parse."""
    if asn is None:
        return stem
    try:
        return gamedata.association(asn)['name'] or stem
    except Exception:  # an ASN that does not parse is listed by its STEM
        sys.stderr.write('createweb: cannot read the name of %s\n' % stem)
        return stem


def _labels(assns):
    return {stem: _label(stem, asn) for stem, asn in assns.items()}


def _read_ledger(data, stem):
    """The created players of one association, oldest first; [] when there are none. Raises ValueError or OSError on a
    ledger that cannot be read, so a corrupt file never reads as an empty one."""
    try:
        with open(os.path.join(data, 'created', stem + '.json'), encoding='utf-8') as fh:
            entries = json.load(fh)
    except FileNotFoundError:
        return []
    if not isinstance(entries, list):
        raise ValueError('ledger %s is not a list' % stem)
    return entries


def _write_ledger(data, stem, entries):
    folder = os.path.join(data, 'created')
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, '.%s.json.tmp' % stem)
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(entries, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, os.path.join(folder, stem + '.json'))


def _all_entries(data):
    """Every ledger entry as (STEM, entry), newest first. An unreadable ledger is skipped."""
    try:
        names = os.listdir(os.path.join(data, 'created'))
    except FileNotFoundError:
        return []
    out = []
    for f in names:
        m = LEDGER_RE.fullmatch(f)
        if not m:
            continue
        try:
            entries = _read_ledger(data, m.group(1))
        except (OSError, ValueError):
            sys.stderr.write('createweb: unreadable ledger %s\n' % f)
            continue
        out.extend((m.group(1), e) for e in entries if isinstance(e, dict))
    out.sort(key=lambda se: str(se[1].get('created', '')), reverse=True)
    return out


def _day(value):
    return value[:10] if isinstance(value, str) else ''


def _select(name, pairs, chosen):
    options = ''.join('<option value="%s"%s>%s</option>' % (server.esc(v), ' selected' if v == chosen else '',
                                                           server.esc(t)) for v, t in pairs)
    return '<select name="%s">%s</select>' % (name, options)


def _field(text, control, error=''):
    msg = '<p class="error">%s</p>' % server.esc(error) if error else ''
    return '<div class="field"><label>%s %s</label>%s</div>' % (server.esc(text), control, msg)


def _grades(legend, names, value, error):
    fields = ''.join(_field(GRADE_NAMES[n], _select(n, GRADE_PAIRS, value(n, '50')), error(n)) for n in names)
    return '<fieldset><legend>%s</legend>%s</fieldset>' % (server.esc(legend), fields)


def _created(data, labels):
    items = ''.join('<li>%s, %s, %s, %s</li>' % (
        server.esc(e.get('name')), server.esc(POSITION_LABELS.get(e.get('pos'), e.get('pos'))),
        server.esc(labels.get(stem, stem)), server.esc(_day(e.get('created'))))
        for stem, e in _all_entries(data))
    if not items:
        return '<h2>Created players</h2><p>None yet.</p>'
    return '<h2>Created players</h2><ul>%s</ul>' % items


def _form(srv, values, errors, notice=''):
    """The form page's body, with the values and messages given and the created players below it."""
    assns = watch.associations(srv.game)
    labels = _labels(assns)
    stems = sorted(assns, key=lambda s: (labels[s], s))

    def value(field, default=''):
        return values.get(field, default)

    def error(field):
        return errors.get(field, '')

    out = [server._masthead('Create a Player'), '<style>%s</style>' % FORM_CSS]
    if notice:
        out.append('<p class="error">%s</p>' % server.esc(notice))
    out.append('<form method="post" action="/create/">')
    out.append(_field('Association', _select('assn', [(s, labels[s]) for s in stems], value('assn')),
                      error('assn')))
    out.append(_field('First name', '<input type="text" name="first" maxlength="16" required value="%s">'
                      % server.esc(value('first')), error('first')))
    out.append(_field('Last name', '<input type="text" name="last" maxlength="16" required value="%s">'
                      % server.esc(value('last')), error('last')))
    out.append(_field('Position', _select('pos', [(p, POSITION_LABELS[p]) for p in create.POSITIONS],
                                          value('pos')), error('pos')))
    out.append(_field('Bats', _select('bats', BATS_PAIRS, value('bats')), error('bats')))
    out.append(_field('Throws', _select('throws', THROWS_PAIRS, value('throws')), error('throws')))
    out.append(_field('Age', '<input type="number" name="age" min="17" max="45" value="%s">'
                      % server.esc(value('age', '22')), error('age')))
    out.append('<p class="note">Pitchers use the pitching grades; everyone else the hitting and fielding grades.</p>')
    out.append(_grades('Hitting and fielding', create.HIT_GRADES, value, error))
    out.append(_grades('Pitching', create.PIT_GRADES, value, error))
    out.append('<p><button type="submit">Create player</button></p>')
    out.append('</form>')
    out.append(_created(srv.data, labels))
    return ''.join(out)


def _notice(status, title, message, extra=()):
    return server._page_reply(status, title, server._masthead(title) + '<p>%s</p>' % server.esc(message) + NAV, extra)


def _done(srv, query):
    q = parse_qs(query)
    assn = q.get('assn', [''])[0]
    pid = q.get('pid', [''])[0]
    if not (ASSN_RE.fullmatch(assn) and PID_RE.fullmatch(pid)):
        return _notice(404, 'Not found', 'No such page.')
    stem = assn.upper()
    entry = next((e for e in _read_ledger(srv.data, stem) if isinstance(e, dict) and e.get('pid') == int(pid)), None)
    if entry is None:
        return _notice(404, 'Not found', 'No such player.')
    label = _label(stem, watch.associations(srv.game).get(stem))
    text = '%s (%s) is in the %s free agent pool.' % (entry.get('name'), POSITION_LABELS.get(entry.get('pos'), ''), label)
    steps = ('League Management, then Main > Load Association and pick %s.' % label,
             'Team > Select Team and pick your team.',
             'Team > Data: Ownership must say Human (one click on Computer makes it Human). Claim Free Agent is greyed '
             'out for computer-owned teams.',
             'Team > Claim Free Agent, press OK (tick only his position to find him fast), then double-click his name. '
             'The claim goes through when the league plays its next day.')
    body = server._masthead('Player created') + '<p>%s</p><p>To sign him:</p><ol>%s</ol>' % (
        server.esc(text), ''.join('<li>%s</li>' % server.esc(s) for s in steps)) + \
        '<p>Computer-run teams sign free agents on their own, so if you wait he may land somewhere else.</p>' + \
        '<p class="nav"><a href="/create/">Create another</a> &middot; <a href="/">Back to the game</a></p>'
    return server._page_reply(200, 'Player created', body)


def _origin_ok(headers, origins):
    """The Origin header must be one of origins; when there is none, the Referer must lie under one of them."""
    origin = headers.get('Origin')
    if origin is not None:
        return origin in origins
    referer = headers.get('Referer') or ''
    return any(referer.startswith(o + '/') for o in origins)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._reply('GET')

    def do_HEAD(self):
        self._reply('HEAD')

    def do_POST(self):
        self._reply('POST')

    def __getattr__(self, name):
        """Any other method, whatever its name, gets a 405: the base class looks methods up as do_<METHOD>."""
        if name.startswith('do_'):
            return self._refuse
        raise AttributeError(name)

    def _refuse(self):
        self._send(*_notice(405, 'Method not allowed', 'Only GET, HEAD and POST are served here.',
                            (('Allow', 'GET, HEAD, POST'),)), head=False)

    def _reply(self, method):
        try:
            reply = self._route(method)
        except Exception:  # one bad request should cost one 500, not the connection
            traceback.print_exc()
            reply = _notice(500, 'Server error', 'Something went wrong. Try again later.')
        self._send(*reply, head=method == 'HEAD')

    def _route(self, method):
        target = urlsplit(self.path)
        if target.path == '/create/':
            if method == 'POST':
                return self._submit()
            return server._page_reply(200, 'Create a Player', _form(self.server, {}, {}))
        if target.path == '/create':
            return server._moved('/create/')
        if target.path == '/create/done':
            if method == 'POST':
                return _notice(405, 'Method not allowed', 'Only GET and HEAD are served here.',
                               (('Allow', 'GET, HEAD'),))
            return _done(self.server, target.query)
        return _notice(404, 'Not found', 'No such page.')

    def _submit(self):
        srv = self.server
        length = self.headers.get('Content-Length')
        if length is None or not re.fullmatch(r'[0-9]+', length):
            return _notice(411, 'Length required', 'The form must send a Content-Length.')
        if not 0 < int(length) <= MAX_BODY:
            return _notice(413, 'Too large', 'The form must be 1 to %d bytes.' % MAX_BODY)
        if not self.headers.get('Content-Type', '').startswith(FORM_TYPE):
            return _notice(415, 'Unsupported type', 'Send the form as an HTML form.')
        if not _origin_ok(self.headers, srv.origins):
            return _notice(403, 'Forbidden', 'The form must be posted from this site.')
        body = self.rfile.read(int(length)).decode('utf-8', 'replace')
        form = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}

        assns = watch.associations(srv.game)
        spec, errors = create.validate(form, assns)
        if errors:
            return server._page_reply(422, 'Create a Player', _form(srv, form, errors))
        stem = spec['assn']
        now = datetime.datetime.now().astimezone()
        with _LOCK:
            entries = _read_ledger(srv.data, stem)
            if len(entries) >= CAP:
                return _notice(429, 'Create a Player', 'This association already has %d created players.' % CAP)
            try:
                pid, _ = create.add_player(srv.game, spec, srv.donor, srv.backup, now, srv.proc)
            except create.AssociationOpen:
                notice = ('%s is open in the game. Go back to the game\'s main menu, then create the player again.'
                          % _label(stem, assns[stem]))
                return server._page_reply(409, 'Create a Player', _form(srv, form, {}, notice))
            except Exception:
                traceback.print_exc()
                return _notice(500, 'Create a Player', 'Could not add the player.')
            entries.append({'pid': pid, 'name': '%s %s' % (spec['first'], spec['last']), 'pos': spec['pos'],
                            'assn': stem, 'created': now.isoformat(timespec='seconds')})
            _write_ledger(srv.data, stem, entries)
        target = '/create/done?' + urlencode({'assn': stem, 'pid': pid})
        body = server._masthead('Player created') + '<p><a href="%s">Continue</a></p>' % server.esc(target)
        return server._page_reply(303, 'Player created', body, (('Location', target),))

    def _send(self, status, ctype, body, extra, head):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for name, value in tuple(extra) + HEADERS:
            self.send_header(name, value)
        self.end_headers()
        if not head:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the reader went away

    def send_error(self, code, message=None, explain=None):
        """Errors the base class raises itself get the same page and headers."""
        self._send(*_notice(code, http.client.responses.get(code, 'Error'), 'The request could not be served.'),
                   head=self.command == 'HEAD')


def make_server(game, data, backup, origins, donor, port=0, proc='/proc'):
    """The service on 127.0.0.1. origins are the https origins the form is posted from; donor is the stock PYR the new
    player is seeded from; proc is where open files are looked for (the default is the live /proc)."""
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    srv.game, srv.data, srv.backup = game, data, backup
    srv.origins = tuple(o.rstrip('/') for o in origins)
    srv.donor, srv.proc = donor, proc
    return srv


def serve(game, data, backup, origins, donor, port=PORT):
    """Serve until interrupted."""
    srv = make_server(game, data, backup, origins, donor, port)
    sys.stderr.write('createweb: serving on http://127.0.0.1:%d/create/\n' % srv.server_address[1])
    try:
        srv.serve_forever()
    finally:
        srv.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description='Serve the create-a-player form for the hosted game.')
    ap.add_argument('--game', required=True, help='the game directory (holds Assn/ and Stats/)')
    ap.add_argument('--data', required=True, help="the news data directory (the ledger goes in created/)")
    ap.add_argument('--backup', required=True, help='where the files are copied before each write')
    ap.add_argument('--origin', action='append', required=True, help='an https origin the form is posted from (repeat)')
    ap.add_argument('--donor', help='the stock PYR the new player is seeded from (default: <game>/Assn/MLBPA96E.PYR)')
    ap.add_argument('--port', type=int, default=PORT)
    args = ap.parse_args(argv)
    assn = os.path.join(args.game, 'Assn')
    if not os.path.isdir(assn):
        ap.error('no Assn directory in %s' % args.game)
    donor = args.donor or gamedata.find(assn, 'MLBPA96E.PYR') or os.path.join(assn, 'MLBPA96E.PYR')
    if not os.path.isfile(donor):
        ap.error('no donor file: %s' % donor)
    if not os.path.isdir(args.data):
        ap.error('not a directory: %s' % args.data)
    serve(args.game, args.data, args.backup, args.origin, donor, args.port)


if __name__ == '__main__':
    main()
