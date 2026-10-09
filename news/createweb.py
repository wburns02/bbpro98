"""The create-a-player form: a small HTTP service on 127.0.0.1 that nginx serves under /create/, behind the site's
PIN gate. A visitor builds a player in three steps: his association, name, position, hands, age, an archetype and a
mode; then his Now and Ceiling grades (and a pitcher's arsenal); then a baseball card to check before he is signed.
create.add_player writes him into that association's free agent pool, and the ledger in the data directory lists who
was made. Standard library only. Pages are server.py's; the POST is checked for its origin, length and type before it
is read.
"""
import argparse
import contextlib
import datetime
import fcntl
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
import scout
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
ARSENAL_PAIRS = (('none', 'Not thrown'),) + GRADE_PAIRS
ROLE_LABELS = {'hit': 'hitter', 'pit': 'pitcher'}
MODE_TEXT = (
    ('realistic', 'Realistic: the budget is %d Now and %d Ceiling points for hitters and %d and %d for pitchers, '
                  'counting only grades above 50; a ceiling can sit at most %d above Now at 22 or under, %d at 23 to 26, '
                  '%d at 27 to 30 and none from 31.' % (create.BUDGET['hit'][0], create.BUDGET['hit'][1],
                                                        create.BUDGET['pit'][0], create.BUDGET['pit'][1],
                                                        create.max_gap(22), create.max_gap(23), create.max_gap(27))),
    ('sandbox', 'Sandbox: no budget or age limits.'),
)
WHO_FIELDS = ('assn', 'first', 'last', 'pos', 'bats', 'throws', 'age', 'archetype', 'mode')
ROW_PREFIXES = ('now_', 'ceil_', 'p_')      # the fields that sit beside a rating row; other messages go above the rows
NAV = '<p class="nav"><a href="/create/">Create a player</a> &middot; <a href="/">Back to the game</a></p>'
FORM_CSS = '.field { margin: 0.6em 0; } .field label { display: block; } .error { font-weight: 700; } ' \
           '.note { font-style: italic; } .mode { display: block; }'
CARD_CSS = '.card { border: 2px solid #234; border-radius: 6px; max-width: 34em; margin: 1em 0; padding: 0.8em; } ' \
           '.card h2 { margin: 0; } .rating { display: flex; gap: 0.6em; align-items: center; margin: 0.3em 0; } ' \
           '.rating .name { width: 9em; } .rating .nums { width: 6em; text-align: right; } ' \
           '.bar { position: relative; flex: 1; height: 0.8em; background: #eee; } ' \
           '.bar span { position: absolute; top: 0; left: 0; height: 100%; } ' \
           '.bar .ceil { background: #bcd; } .bar .now { background: #234; }'
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


def _section(legend, body):
    return '<fieldset><legend>%s</legend>%s</fieldset>' % (server.esc(legend), body)


def _row(text, controls, messages):
    """One rating's row: its name, its controls, and the messages for them beside it."""
    msgs = ''.join('<p class="error">%s</p>' % server.esc(m) for m in messages if m)
    return '<div class="field"><span>%s</span> %s%s</div>' % (server.esc(text), ' '.join(controls), msgs)


def _grade_rows(names, values, errors):
    """A Now select, and for every rating but strikeout a Ceiling select, one row per rating."""
    rows = []
    for r in names:
        controls = ['Now %s' % _select('now_' + r, GRADE_PAIRS, values.get('now_' + r, '50'))]
        messages = [errors.get('now_' + r, '')]
        if r != 'strikeout':
            controls.append('Ceiling %s' % _select('ceil_' + r, GRADE_PAIRS, values.get('ceil_' + r, '50')))
            messages.append(errors.get('ceil_' + r, ''))
        rows.append(_row(create.RATING_LABELS[r], controls, messages))
    return ''.join(rows)


def _arsenal_rows(values, errors):
    """Seven rows in slot order, each with a Now and a Ceiling select whose first option is 'Not thrown'."""
    rows = []
    for slot in create.PITCH_SLOTS:
        field = 'p_' + slot
        controls = ['Now %s' % _select(field + '_now', ARSENAL_PAIRS, values.get(field + '_now', 'none')),
                    'Ceiling %s' % _select(field + '_ceil', ARSENAL_PAIRS, values.get(field + '_ceil', 'none'))]
        rows.append(_row(create.PITCH_LABELS[slot], controls, [errors.get(field, '')]))
    return ''.join(rows)


def _read_grade(value):
    """The grade a posted value reads as, or None; the budget line counts only real grades."""
    return int(value) if value.isdigit() and int(value) in create.GRADES else None


def _budget_text(values):
    """Realistic mode's budget for the values given: the points Now and Ceiling spend against their maximums, and the
    most a ceiling can sit above Now at this age. A grade that does not read counts as 50, so it spends nothing."""
    pos = values.get('pos', '')
    names = create.ROLE_RATINGS[create.role(pos)]
    now = {r: _read_grade(values.get('now_' + r, '')) or 50 for r in names}
    ceiling = {r: _read_grade(values.get('ceil_' + r, '')) or 50 for r in names if r != 'strikeout'}
    pitches = {}
    if create.role(pos) == 'pit':
        for slot in create.PITCH_SLOTS:
            n = _read_grade(values.get('p_%s_now' % slot, 'none'))
            c = _read_grade(values.get('p_%s_ceil' % slot, 'none'))
            if n is not None and c is not None:
                pitches[slot] = (n, c)
    b = create.budget({'pos': pos, 'now': now, 'ceiling': ceiling, 'pitches': pitches})
    text = 'Now: %d of %d points; Ceiling: %d of %d points.' % (b['now'], b['now_max'], b['ceiling'], b['ceiling_max'])
    age = values.get('age', '')
    if age.isdigit():
        text += ' At %d a ceiling can be at most %d above Now.' % (int(age), create.max_gap(int(age)))
    return text


def _hidden(values, fields):
    return ''.join('<input type="hidden" name="%s" value="%s">' % (server.esc(f), server.esc(values.get(f, '')))
                   for f in fields)


def _form_fields(pos):
    """Every field a form for this position carries: step one's, then each grade of the role, then the arsenal. The
    preview passes on only these, never whatever else was posted."""
    names = create.ROLE_RATINGS[create.role(pos)]
    fields = list(WHO_FIELDS)
    fields += ['now_' + r for r in names] + ['ceil_' + r for r in names if r != 'strikeout']
    if create.role(pos) == 'pit':
        fields += ['p_%s_%s' % (slot, k) for slot in create.PITCH_SLOTS for k in ('now', 'ceil')]
    return fields


def _archetype_default(chosen, pos):
    """The archetype the select starts on: the one posted, else the first of the posted position's role (a browser starts
    on the first position, a pitcher)."""
    if chosen:
        return chosen
    role = create.role(pos or 'P')
    return next(k for k, a in create.ARCHETYPES.items() if a['role'] == role)


def _mode_field(chosen, error=''):
    radios = ''.join('<label class="mode"><input type="radio" name="mode" value="%s"%s> %s</label>'
                     % (m, ' checked' if m == chosen else '', server.esc(t)) for m, t in MODE_TEXT)
    msg = '<p class="error">%s</p>' % server.esc(error) if error else ''
    return '<fieldset><legend>Mode</legend>%s%s</fieldset>' % (radios, msg)


def _created(data, labels):
    items = ''.join('<li>%s, %s, %s, %s</li>' % (
        server.esc(e.get('name')), server.esc(POSITION_LABELS.get(e.get('pos'), e.get('pos'))),
        server.esc(labels.get(stem, stem)), server.esc(_day(e.get('created'))))
        for stem, e in _all_entries(data))
    if not items:
        return '<h2>Created players</h2><p>None yet.</p>'
    return '<h2>Created players</h2><ul>%s</ul>' % items


def _who_page(srv, values, errors, notice=''):
    """Step one: the association, the player's name, position, hands, age, archetype and mode, with the created players
    below. values are the posted or default values; errors maps a field to its message."""
    assns = watch.associations(srv.game)
    labels = _labels(assns)
    stems = sorted(assns, key=lambda s: (labels[s], s))

    def value(field, default=''):
        return values.get(field, default)

    def error(field):
        return errors.get(field, '')

    archetypes = [(k, '%s (%s)' % (a['label'], ROLE_LABELS[a['role']])) for k, a in create.ARCHETYPES.items()]
    blurbs = ''.join('<li><b>%s</b> %s</li>' % (server.esc(a['label']), server.esc(a['blurb']))
                     for a in create.ARCHETYPES.values())
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
    out.append(_field('Archetype', _select('archetype', archetypes,
                                           _archetype_default(value('archetype'), value('pos'))), error('archetype')))
    out.append('<ul class="blurbs">%s</ul>' % blurbs)
    out.append(_mode_field(value('mode', 'realistic'), error('mode')))
    out.append('<p><button type="submit" name="step" value="who">Next</button></p>')
    out.append('</form>')
    out.append(_created(srv.data, labels))
    return ''.join(out)


def _ratings_page(values, errors, notice=''):
    """Step two: a Now and a Ceiling grade for each rating of the role (a pitcher also has his arsenal), the budget in
    realistic mode, and the step one values as hidden inputs. errors are the posted form's; messages not beside a row go
    above the rows."""
    role = create.role(values.get('pos', ''))
    top = [m for k, m in errors.items() if not k.startswith(ROW_PREFIXES)]
    out = [server._masthead('Create a Player'), '<style>%s</style>' % FORM_CSS]
    if notice:
        out.append('<p class="error">%s</p>' % server.esc(notice))
    out.extend('<p class="error">%s</p>' % server.esc(m) for m in top)
    if values.get('mode') == 'realistic':
        out.append('<p class="note">%s</p>' % server.esc(_budget_text(values)))
    out.append('<form method="post" action="/create/">')
    out.append(_hidden(values, WHO_FIELDS))
    if role == 'hit':
        out.append(_section('Hitting and fielding', _grade_rows(create.HIT_RATINGS, values, errors)))
    else:
        out.append(_section('Pitching', _grade_rows(create.ROLE_RATINGS['pit'], values, errors)))
        out.append(_section('Arsenal', _arsenal_rows(values, errors)))
    out.append('<p><button type="submit" name="step" value="ratings">Preview the card</button> '
               '<button type="submit" name="step" value="back">Back</button></p>')
    out.append('</form>')
    return ''.join(out)


def _pct(grade):
    """A grade's place on a card's bar: 20 at the left edge, 80 at the right, as a CSS width."""
    return '%.1f%%' % ((grade - 20) / 60 * 100)


def _bar(name, now, ceil, nums):
    """One row of the card: a bar filled to the Now grade, the Ceiling reached in a lighter shade, and the numbers."""
    return ('<div class="rating"><span class="name">%s</span><span class="bar"><span class="ceil" style="width:%s">'
            '</span><span class="now" style="width:%s"></span></span><span class="nums">%s</span></div>'
            % (server.esc(name), _pct(ceil), _pct(now), server.esc(nums)))


def _card_rows(spec):
    now, ceiling = spec['now'], spec['ceiling']
    rows = []
    for r in create.ROLE_RATINGS[create.role(spec['pos'])]:
        if r == 'strikeout':
            rows.append(_bar(create.RATING_LABELS[r], now[r], now[r], str(now[r])))
        else:
            rows.append(_bar(create.RATING_LABELS[r], now[r], ceiling[r], '%d / %d' % (now[r], ceiling[r])))
    for slot in create.PITCH_SLOTS:
        if slot in spec['pitches']:
            n, c = spec['pitches'][slot]
            rows.append(_bar(create.PITCH_LABELS[slot], n, c, '%d / %d' % (n, c)))
    return ''.join(rows)


def _preview_page(srv, form, spec):
    """The baseball card for a valid spec: the front, then the back with the scouting report and the closest real
    player, then the buttons that edit the ratings or sign him. Every posted value rides along as a hidden input."""
    stem = spec['assn']
    label = _label(stem, watch.associations(srv.game).get(stem))
    match = create.comparable(srv.game, stem, spec, scout.year_of(label) or 1997)
    if match is None:
        like = 'Plays like: no close match in this association.'
    else:
        like = 'Plays like: %s (%s, age %d)' % (match['name'], match['team'] or 'free agent', match['age'])
    report = ''.join('<li>%s</li>' % server.esc(s) for s in create.scouting_report(spec))
    card = ('<div class="card"><div class="front"><h2>%s</h2><p>%s &middot; B/T %s/%s &middot; age %d</p>'
            '<p>%s &middot; %s</p>%s</div><div class="back"><h3>Scouting report</h3><ul>%s</ul><p>%s</p></div></div>'
            % (server.esc('%s %s' % (spec['first'], spec['last'])), server.esc(POSITION_LABELS[spec['pos']]),
               server.esc(spec['bats']), server.esc(spec['throws']), spec['age'], server.esc(label),
               server.esc(create.ARCHETYPES[spec['archetype']]['label']), _card_rows(spec), report,
               server.esc(like)))
    out = [server._masthead('Create a Player'), '<style>%s%s</style>' % (FORM_CSS, CARD_CSS), card,
           '<form method="post" action="/create/">',
           _hidden(form, _form_fields(spec['pos'])),
           '<p><button type="submit" name="step" value="edit">Edit ratings</button> '
           '<button type="submit" name="step" value="commit">Sign him into the pool</button></p>',
           '</form>']
    return ''.join(out)


def _step_who(srv, form):
    who, errors = create.validate_who(form, watch.associations(srv.game))
    if errors:
        return server._page_reply(422, 'Create a Player', _who_page(srv, form, errors))
    values = {k: str(v) for k, v in who.items()}
    values.update(create.archetype_fields(who['archetype']))
    return server._page_reply(200, 'Create a Player', _ratings_page(values, {}))


def _step_back(srv, form):
    return server._page_reply(200, 'Create a Player', _who_page(srv, form, {}))


def _step_ratings(srv, form):
    spec, errors = create.validate(form, watch.associations(srv.game))
    if errors:
        return server._page_reply(422, 'Create a Player', _ratings_page(form, errors))
    return server._page_reply(200, 'Create a Player', _preview_page(srv, form, spec))


def _step_edit(srv, form):
    _, errors = create.validate_who(form, watch.associations(srv.game))
    if errors:
        return server._page_reply(422, 'Create a Player', _who_page(srv, form, errors))
    return server._page_reply(200, 'Create a Player', _ratings_page(form, {}))


def _step_commit(srv, form):
    assns = watch.associations(srv.game)
    spec, errors = create.validate(form, assns)
    if errors:
        return server._page_reply(422, 'Create a Player', _ratings_page(form, errors))
    return _commit(srv, form, spec, assns)


def _step_unknown(srv, form):
    return server._page_reply(422, 'Create a Player', _who_page(srv, form, {}, 'Start again.'))


STEPS = {'who': _step_who, 'back': _step_back, 'ratings': _step_ratings, 'edit': _step_edit, 'commit': _step_commit}


class CapReached(Exception):
    """The association already has CAP created players."""


@contextlib.contextmanager
def _file_lock(data):
    """An exclusive lock on <data>/.create.lock, held by every process that creates players (this form and the
    in-game bridge, modbridge.py), so the cap count, the write and the ledger stay together across processes."""
    with open(os.path.join(data, '.create.lock'), 'a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def commit(game, data, donor, backup, proc, spec, now):
    """Sign a valid spec's player into his association's free agent pool and add him to the ledger: the lock, the cap,
    the write, then the ledger entry. Returns his id. Raises CapReached at CAP created players, create.AssociationOpen
    while the game holds the association's files, and whatever add_player raises otherwise."""
    stem = spec['assn']
    with _LOCK, _file_lock(data):
        entries = _read_ledger(data, stem)
        if len(entries) >= CAP:
            raise CapReached(stem)
        pid, _ = create.add_player(game, spec, donor, backup, now, proc)
        entries.append({'pid': pid, 'name': '%s %s' % (spec['first'], spec['last']), 'pos': spec['pos'],
                        'assn': stem, 'created': now.isoformat(timespec='seconds'),
                        'archetype': spec['archetype'], 'mode': spec['mode']})
        _write_ledger(data, stem, entries)
    return pid


def sign_steps(label):
    """How to sign a created player in the game, one step per line."""
    return ('League Management, then Main > Load Association and pick %s.' % label,
            'Team > Select Team and pick your team.',
            'Team > Data: Ownership must say Human (one click on Computer makes it Human). Claim Free Agent is greyed '
            'out for computer-owned teams.',
            'Team > Claim Free Agent, press OK (tick only his position to find him fast), then double-click his name. '
            'The claim goes through when the league plays its next day.')


def _commit(srv, form, spec, assns):
    """The create path for a valid spec: commit, then the done page."""
    stem = spec['assn']
    now = datetime.datetime.now().astimezone()
    try:
        pid = commit(srv.game, srv.data, srv.donor, srv.backup, srv.proc, spec, now)
    except CapReached:
        return _notice(429, 'Create a Player', 'This association already has %d created players.' % CAP)
    except create.AssociationOpen:
        notice = ('%s is open in the game. Go back to the game\'s main menu, then create the player again.'
                  % _label(stem, assns[stem]))
        return server._page_reply(409, 'Create a Player', _ratings_page(form, {}, notice))
    except Exception:
        traceback.print_exc()
        return _notice(500, 'Create a Player', 'Could not add the player.')
    target = '/create/done?' + urlencode({'assn': stem, 'pid': pid})
    body = server._masthead('Player created') + '<p><a href="%s">Continue</a></p>' % server.esc(target)
    return server._page_reply(303, 'Player created', body, (('Location', target),))


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
    steps = sign_steps(label)
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
            return server._page_reply(200, 'Create a Player', _who_page(self.server, {}, {}))
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
        return STEPS.get(form.get('step', 'who'), _step_unknown)(srv, form)

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
