"""The in-game Mods menu's bridge: a long-running host process that answers the requests a mod DLL writes into
the game's Mods/spool directory. The game runs in a sandbox with no network, so the requests are answered here by the
repo's own Python: league news pages (server.route), the player development pages under /news/development/ and the
Mods/focus.txt they set (focus.py), which aging.dll reads at each offseason, the offseason trade pages under /news/gm/
(aigm.py: the computer teams' preseason trades, written into the ASN, and each human team's proposals to accept or
reject), the player cards under /news/card/ (the Team Statistics screen's click, playercard.dll), Create a Player
(create.validate and createweb.commit), and a season built from the Lahman database
(work/lahman/build.py, run as a subprocess). Standard library only.

The DLL writes q<ID>.tmp and renames it to q<ID>.req. The bridge claims the request by renaming it to q<ID>.work,
writes r<ID>.tmp and renames that to r<ID>.rsp, then removes the .work file. A picture page (a player card tab drawn
with the game's own fonts, cardimg.py) also writes r<ID>.bmp, before the .rsp, and says image=1 in the header.
parse_request reads a request, render writes a reply, and process_spool answers every pending request once.
"""
import argparse
import datetime
import os
import pathlib
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import textwrap
import threading
import time
import traceback
import types
import urllib.parse
import zlib
from html.parser import HTMLParser

import aigm
import cardimg
import create
import createweb
import focus
import gamedata
import history
import portrait
import recap
import scout
import server
import watch

VERSION = 1
MAX_REQUEST = 8192          # bytes
MAX_LINES = 100
MAX_VALUE = 256             # characters
MAX_WORKERS = 4             # requests answered at once
HOUSEKEEP_EVERY = 60        # seconds
ALIVE = 'alive.txt'         # the heartbeat the game reads: the unix time of the last pass, one line
ALIVE_EVERY = 2             # seconds between heartbeats
STALE = 600                 # seconds before a reply or temporary file is removed
BUILD_TIMEOUT = 900         # seconds
TAIL = 10                   # lines of build output in a reply
WIDTH = 76                  # columns of news text
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_PY = os.path.join(REPO, 'work', 'lahman', 'build.py')
# Seasons a build can make, per kind: build.py's --leagues for it, the letter in the association's stem (16L1927,
# 12N1942) and the years. main() reads the years from the database; these are the SABR 2025 release's.
KINDS = {'mlb': ('NA,NL,AA,UA,PL,AL,FL', 'L', 'MLB'), 'negro': ('NNL,ECL,ANL,EWL,NSL,NN2,NAL', 'N', 'Negro Leagues')}
RANGES = {'mlb': (1871, 2025), 'negro': (1920, 1948)}
BUSY_TEXT = 'A season is already being built. Try again when it finishes.'
NO_BUILD_TEXT = ('Build a Season is not set up here: start the bridge with --db (a Lahman database) and '
                 '--templates (the minted structure templates).')
WAIT_TEXT = 'Computer-run teams sign free agents on their own, so if you wait he may land somewhere else.'
KEY_RE = re.compile(r'[a-z0-9_]{1,24}')
ARSENAL_RE = re.compile(r'p_(%s)_(now|ceil)' % '|'.join(create.PITCH_SLOTS))   # capitalised, as create.PITCH_SLOTS is
LOW_RE = re.compile(r'[\x00-\x1f]')
REQ_RE = re.compile(r'q([0-9a-f]{8})\.req')
NEWS_RE = re.compile(r'/news/[\x21-\x7e]*')
NUMBER_RE = re.compile(r'-?[0-9.,]+%?')
TYPOGRAPHY = str.maketrans({'—': '-', '–': '-', '‘': "'", '’': "'", '“': '"', '”': '"',
                            '…': '...', '←': '<-', '→': '->', '•': '*', ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' '})
HIDDEN = ('head', 'style', 'script')
HEADINGS = ('h1', 'h2', 'h3', 'h4')
UNDERLINES = {'h1': '=', 'h2': '-'}
_SLOTS = threading.BoundedSemaphore(MAX_WORKERS)    # one per worker: a full set leaves requests for the next poll
_BUILD = threading.Lock()                           # held for a whole season build


def parse_request(raw):
    """The request's fields as a dict, op among them; None when the bytes break a rule: over 8192 bytes, more than 100
    lines, a key outside [a-z0-9_]{1,24} (other than an arsenal field p_<SLOT>_now or _ceil, whose slot is capitalised
    as in create.PITCH_SLOTS), a value over 256 characters or with a control character, a key given twice, or a first
    line that is not op=."""
    if len(raw) > MAX_REQUEST:
        return None
    lines = [ln[:-1] if ln.endswith('\r') else ln for ln in raw.decode('latin-1').split('\n')]
    lines = [ln for ln in lines if ln]
    if not lines or len(lines) > MAX_LINES:
        return None
    fields = {}
    for ln in lines:
        key, eq, value = ln.partition('=')
        if not eq or not (KEY_RE.fullmatch(key) or ARSENAL_RE.fullmatch(key)) or key in fields:
            return None
        if len(value) > MAX_VALUE or LOW_RE.search(value):
            return None
        fields[key] = value
    return fields if next(iter(fields)) == 'op' else None


def render(header, body):
    """A reply's bytes: each header pair as key=value and CRLF, an empty CRLF line, then the body with CRLF line ends.
    The typographic marks map to plain ASCII first; anything else latin-1 cannot hold becomes '?'."""
    text = ''.join('%s=%s\r\n' % pair for pair in header) + '\r\n' + re.sub(r'\r\n?|\n', '\r\n', body)
    return text.translate(TYPOGRAPHY).encode('latin-1', errors='replace')


def _plain(value):
    """A header value as one line: a control character (a TAB, a line break) becomes a space."""
    return LOW_RE.sub(' ', str(value))


def _collapse(parts):
    """The text of some pieces, each run of whitespace as one space and the ends trimmed."""
    return ' '.join(''.join(parts).split())


def _route_path(href, base):
    """The path and query an href leads to, resolved against the page's path: no scheme, host or fragment. An href
    urllib cannot parse (a broken IPv6 host such as http://[x) leads nowhere: ''."""
    try:
        return urllib.parse.urlsplit(urllib.parse.urljoin(base, href))._replace(scheme='', netloc='',
                                                                                fragment='').geturl()
    except ValueError:
        return ''


def _grid(rows):
    """Rows as aligned lines: each column as wide as its widest cell, two spaces between columns, a cell that reads as a
    number right-aligned and the rest left-aligned."""
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    grid = [r + [''] * (ncols - len(r)) for r in rows]
    widths = [max(len(r[c]) for r in grid) for c in range(ncols)]
    lines = []
    for r in grid:
        cells = [r[c].rjust(widths[c]) if NUMBER_RE.fullmatch(r[c]) else r[c].ljust(widths[c]) for c in range(ncols)]
        lines.append('  '.join(cells).rstrip())
    return lines


def _tidy(lines):
    """The lines with each run of blank lines cut to one, and none at either end."""
    out = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    while out and not out[-1]:
        out.pop()
    return out


class _Page(HTMLParser):
    """One page's text, built as the parser meets its tags. The paragraph being built is in flow; a heading, a table
    cell or a caption collects its text in cap until it closes."""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.out = []           # finished lines
        self.flow = []          # the paragraph's text so far
        self.links = []         # (label, path) of each /news/ link, in marker order
        self.title_parts = []
        self.in_title = False
        self.hidden = 0         # open head, style and script elements
        self.lists = []         # per open ol or ul: [tag, items numbered so far, open items when it began]
        self.items = []         # per open li: [prefix, the prefix has not led a line yet]
        self.anchor = None      # (path, text parts) of an open link to /news/
        self.cap = None         # (kind, parts) while a heading, cell or caption collects its text
        self.table = None       # {'caption': str, 'rows': [...]} while a table is open
        self.row = None         # the cells of the open row

    def _sink(self):
        return self.cap[1] if self.cap else self.flow

    def _flush(self):
        """Ends the paragraph being built: its text, wrapped, becomes lines. A list item's first line keeps its
        prefix and later lines are indented by the prefix's width."""
        text = _collapse(self.flow)
        self.flow = []
        if not text:
            return
        prefix, lead = self.items[-1] if self.items else ('', False)
        if self.items:
            self.items[-1][1] = False
        pad = ' ' * len(prefix)
        self.out.extend(textwrap.fill(text, WIDTH, initial_indent=prefix if lead else pad,
                                      subsequent_indent=pad).split('\n'))

    def _finish_cap(self):
        """Ends the heading, cell or caption being collected, if one is open."""
        if self.cap is None:
            return
        kind, parts = self.cap
        self.cap = None
        text = _collapse(parts)
        if kind == 'cell':
            if self.row is not None:
                self.row.append(text)
        elif kind == 'caption':
            if self.table is not None:
                self.table['caption'] = text
        elif text:
            self.out.append(text)
            if kind in UNDERLINES:
                self.out.append(UNDERLINES[kind] * len(text))
            self.out.append('')

    def _end_row(self):
        if self.row:
            self.table['rows'].append(self.row)
        self.row = None

    def _end_table(self):
        if self.table is None:
            return
        table, self.table = self.table, None
        if table['caption']:
            self.out.append(table['caption'])
        self.out.extend(_grid(table['rows']))
        self.out.append('')

    def _close_link(self):
        if self.anchor is None:
            return
        target, parts = self.anchor
        self.anchor = None
        self.links.append((_collapse(parts) or target, target))
        self._sink().append(' [%d]' % len(self.links))

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
        elif tag in HIDDEN:
            self.hidden += 1
        elif tag == 'a':
            href = dict(attrs).get('href')
            target = _route_path(href, self.path) if href is not None else ''
            self.anchor = (target, []) if target.startswith('/news/') else None
        elif tag in HEADINGS:
            self._flush()
            self.cap = (tag, [])
        elif tag in ('ol', 'ul'):
            self._flush()
            self.lists.append([tag, 0, len(self.items)])
        elif tag == 'li':
            self._flush()
            if self.lists and self.lists[-1][0] == 'ol':
                self.lists[-1][1] += 1
                prefix = '%d. ' % self.lists[-1][1]
            else:
                prefix = '- '
            self.items.append([prefix, True])
        elif tag == 'table':
            self._flush()
            self.table, self.row = {'caption': '', 'rows': []}, None
        elif tag == 'tr':
            self._flush()
            self._finish_cap()
            self._end_row()
            if self.table is not None:
                self.row = []
        elif tag in ('td', 'th'):
            if self.table is not None:
                self._finish_cap()
                if self.row is None:
                    self.row = []
                self.cap = ('cell', [])
        elif tag == 'caption':
            if self.table is not None:
                self.cap = ('caption', [])
        elif tag == 'br':
            if self.cap:
                self.cap[1].append(' ')
            else:
                self._flush()
        elif tag in ('p', 'div', 'section', 'header'):
            self._flush()

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag in HIDDEN:
            self.hidden = max(0, self.hidden - 1)
        elif tag == 'a':
            self._close_link()
        elif tag in HEADINGS or tag in ('td', 'th', 'caption'):
            self._finish_cap()
        elif tag == 'tr':
            self._finish_cap()
            self._end_row()
        elif tag == 'table':
            self._flush()
            self._finish_cap()
            self._end_row()
            self._end_table()
        elif tag == 'li':
            self._flush()
            if self.items:
                self.items.pop()
        elif tag in ('ol', 'ul'):
            self._flush()
            if self.lists:
                _, _, depth = self.lists.pop()
                del self.items[depth:]
                if not self.lists:
                    self.out.append('')
        elif tag in ('p', 'div', 'section', 'header'):
            self._flush()
            if tag == 'p':
                self.out.append('')

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif not self.hidden:
            self._sink().append(data)
            if self.anchor is not None:
                self.anchor[1].append(data)

    def finish(self):
        """Ends whatever the page left open at its end."""
        self._flush()
        self._finish_cap()
        self._end_row()
        self._end_table()


def html_to_text(html, path):
    """(title, text, links) for a page at path: its text laid out as the news pages are (headings underlined,
    paragraphs wrapped, lists numbered or dashed, tables aligned), and each /news/ link as (label, path) in the order
    its [n] marker appears in the text. Scripts, styles and the head are not output."""
    page = _Page(path)
    page.feed(html)
    page.close()
    page.finish()
    title = _collapse(page.title_parts)
    return title, '\n'.join(_tidy(page.out)), page.links


def _season(game, year, letter='L'):
    """(STEM, ASN path) of the season built for year (a file <n><letter><year>.ASN in Assn/), or (None, None)."""
    assn = os.path.join(game, 'Assn')
    pat = re.compile(r'[0-9]{1,2}%s%d\.ASN' % (letter, year), re.I)
    for f in sorted(os.listdir(assn)):
        if pat.fullmatch(f) and not os.path.islink(os.path.join(assn, f)):
            return os.path.splitext(f)[0].upper(), os.path.join(assn, f)
    return None, None


def _leftovers(game, year, letter='L'):
    """True when Assn/ or Stats/ holds anything named for a <n><letter><year> season (any extension), or either
    directory is a symlink. build.py writes those names with the host's permissions, so it never runs over one."""
    pat = re.compile(r'[0-9]{1,2}%s%d\.[A-Za-z]+' % (letter, year), re.I)
    for sub in ('Assn', 'Stats'):
        path = os.path.join(game, sub)
        if os.path.islink(path):
            return True
        if os.path.isdir(path) and any(pat.fullmatch(f) for f in os.listdir(path)):
            return True
    return False


def _tail(*outputs):
    """The last TAIL lines of a build's output, stdout then stderr."""
    text = '\n'.join(o.rstrip('\n') for o in outputs if o and o.strip())
    return '\n'.join(text.splitlines()[-TAIL:])


def _paragraphs(*parts):
    return '\n\n'.join(p for p in parts if p)


def _ping(ctx, req):
    """build=1 when Build a Season can run here; build=0 with NO_BUILD_TEXT as the body when it cannot."""
    if ctx.db and ctx.templates:
        return [('status', 'ok'), ('version', str(VERSION)), ('build', '1')], ''
    return [('status', 'ok'), ('version', str(VERSION)), ('build', '0')], NO_BUILD_TEXT


def _assns(ctx, req):
    assns = watch.associations(ctx.game)
    stems = sorted(assns)
    header = [('status', 'ok'), ('count', str(len(stems)))]
    header += [('assn.%d' % i, '%s\t%s' % (stem, _plain(createweb._label(stem, assns[stem]))))
               for i, stem in enumerate(stems)]
    return header, ''


def _ratings(ratings):
    return ','.join('%s:%d' % item for item in ratings.items())


def _archetypes(ctx, req):
    header = [('status', 'ok'), ('count', str(len(create.ARCHETYPES)))]
    for i, (key, arch) in enumerate(create.ARCHETYPES.items()):
        pitches = ['%s:%d:%d' % ((slot,) + arch['pitches'][slot]) for slot in create.PITCH_SLOTS
                   if slot in arch['pitches']]
        header += [('arch.%d' % i, '%s\t%s\t%s' % (key, arch['label'], arch['role'])),
                   ('arch.%d.blurb' % i, _plain(arch['blurb'])),
                   ('arch.%d.now' % i, _ratings(arch['now'])),
                   ('arch.%d.ceil' % i, _ratings(arch['ceiling'])),
                   ('arch.%d.pitches' % i, ','.join(pitches))]
    header += [('grades', ','.join(str(g) for g in create.GRADES)),
               ('ages', '%d-%d' % (create.AGES[0], create.AGES[-1])),
               ('budget.hit', '%d,%d' % create.BUDGET['hit']),
               ('budget.pit', '%d,%d' % create.BUDGET['pit']),
               ('positions', ','.join(create.POSITIONS))]
    return header, ''


def _refused(key, message):
    return [('status', 'error'), (key, _plain(message))], message


def _signed(spec, label, pid):
    name = '%s %s' % (spec['first'], spec['last'])
    body = ['%s (%s) is in the %s free agent pool.' % (name, createweb.POSITION_LABELS[spec['pos']], label), '',
            'Scouting report:']
    body += ['  ' + s for s in create.scouting_report(spec)]
    body += ['', 'To sign him:']
    body += ['%d. %s' % (i, s) for i, s in enumerate(createweb.sign_steps(label), 1)]
    body += ['', WAIT_TEXT]
    header = [('status', 'ok'), ('pid', str(pid)), ('name', _plain(name)), ('assn', spec['assn'])]
    return header, '\n'.join(body)


def _create(ctx, req):
    form = {k: v for k, v in req.items() if k != 'op'}
    assns = watch.associations(ctx.game)
    spec, errors = create.validate(form, assns)
    if errors:
        fields = sorted(errors)
        return ([('status', 'error')] + [('error.' + f, _plain(errors[f])) for f in fields],
                '\n'.join('%s: %s' % (f, errors[f]) for f in fields))
    stem = spec['assn']
    label = createweb._label(stem, assns[stem])
    try:
        pid = createweb.commit(ctx.game, ctx.data, ctx.donor, ctx.backup, ctx.proc, spec,
                               datetime.datetime.now().astimezone())
    except createweb.CapReached:
        return _refused('error.assn', 'This association already has %d created players.' % createweb.CAP)
    except create.AssociationOpen:
        return _refused('error.assn', '%s is open in the game. Go back to the main menu, then create the player again.'
                        % label)
    except Exception:
        traceback.print_exc()
        return [('status', 'error')], 'Could not add the player.'
    return _signed(spec, label, pid)


def _news_reply(status, path, title, text, links):
    """A news reply: the header (status, http, path, title, count and link.N) and the page's text."""
    header = [('status', 'ok' if status == 200 else 'error'), ('http', str(status)), ('path', _plain(path)),
              ('title', _plain(title)), ('count', str(len(links)))]
    header += [('link.%d' % i, '%s\t%s' % (_plain(label), _plain(target))) for i, (label, target) in enumerate(links)]
    return header, text


def _news(ctx, req):
    path = req.get('path', '')
    if len(path) > MAX_VALUE or not NEWS_RE.fullmatch(path):
        return [('status', 'error')], 'Bad request.'
    if _in_development(path):
        return _development(ctx, path)
    if _in_card(path):
        return _card(ctx, path)
    if _in_gm(path):
        return _gm(ctx, path)
    data = pathlib.Path(ctx.data)     # server.route joins paths with /
    status, _, body, extra = server.route(data, path)
    for _ in range(3):
        target = next((v for k, v in extra if k.lower() == 'location'), '')
        if status not in (301, 302, 303) or not target.startswith('/news/'):
            break
        path = target
        status, _, body, extra = server.route(data, path)
    title, text, links = html_to_text(body.decode('utf-8', 'replace'), path)
    stem = _assn_page_stem(ctx, path) if status == 200 else None
    if stem is not None:
        links.append(('Player development', '/news/development/%s/' % stem))
        links.append(('Offseason trades', '/news/gm/%s/' % stem))
    return _news_reply(status, path, title, text, links)


def _run_build(ctx, year, kind='mlb'):
    leagues, letter, _ = KINDS[kind]
    cmd = [sys.executable, BUILD_PY, '--year', str(year), '--install', ctx.game, '--db', ctx.db,
           '--templates', ctx.templates]
    if kind != 'mlb':
        cmd += ['--leagues', leagues]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=BUILD_TIMEOUT, cwd=REPO)
    except subprocess.TimeoutExpired:
        return [('status', 'error')], _paragraphs('The build failed.', 'Timed out.')
    stem, asn = _season(ctx.game, year, letter)
    if run.returncode == 0 and stem is not None:
        label = createweb._label(stem, asn)
        header = [('status', 'ok'), ('existed', '0'), ('stem', stem), ('label', _plain(label))]
        return header, _paragraphs('Built %s (%s).' % (label, stem), LOAD_TEXT % label, _tail(run.stdout))
    return [('status', 'error')], _paragraphs('The build failed.', _tail(run.stdout, run.stderr))


# The game stays on the association it had open; a new one has to be loaded by hand, and the list shows ten rows.
LOAD_TEXT = ('To play it, close this window and choose Main > Load Association, then pick "%s" '
             '(scroll the list with the mouse wheel if it is not shown).')


def _build(ctx, req):
    year, kind = req.get('year', ''), req.get('league', 'mlb')
    if kind not in KINDS:
        return [('status', 'error')], 'Bad request.'
    _, letter, title = KINDS[kind]
    if not (ctx.db and ctx.templates):
        return [('status', 'error')], NO_BUILD_TEXT
    span = getattr(ctx, 'ranges', RANGES).get(kind)
    if span is None:
        return [('status', 'error')], 'This database has no %s seasons.' % title
    first, last = span
    if not (re.fullmatch(r'[0-9]{4}', year) and first <= int(year) <= last):
        return [('status', 'error')], 'Pick a year from %d to %d for %s.' % (first, last, title)
    year = int(year)
    stem, asn = _season(ctx.game, year, letter)
    if stem is None and _leftovers(ctx.game, year, letter):
        return [('status', 'error')], ('Files for a %d season are already in the game without its association. '
                                       'Remove them, then build again.' % year)
    if stem is None:
        if not _BUILD.acquire(blocking=False):
            return [('status', 'busy')], BUSY_TEXT
        try:
            stem, asn = _season(ctx.game, year, letter)     # a build may have finished since the look above
            if stem is None:
                return _run_build(ctx, year, kind)
        finally:
            _BUILD.release()
    label = createweb._label(stem, asn)
    header = [('status', 'ok'), ('existed', '1'), ('stem', stem), ('label', _plain(label))]
    return header, _paragraphs('%s is already in the game (%s).' % (label, stem), LOAD_TEXT % label)


# The player development pages under /news/development/ and the focus file they set (focus.py). The pages read the
# association's ASN and PYR; the file is <game>/Mods/focus.txt, held by descriptor like the spool.
FOCUS_FILE = 'focus.txt'
FOCUS_TMP = 'focus.tmp'
FULL_TEXT = '%d players in this association already have a focus. Clear one first.' % focus.MAX_PER_ASSN
ASSN_PAGE_RE = re.compile(r'/news/([A-Za-z0-9]{1,8})/')
_FOCUS_LOCK = threading.Lock()      # held for each read-modify-write of focus.txt


def _in_development(path):
    """True for /news/development and anything beneath it: those paths are the bridge's own, never server.route's."""
    page = urllib.parse.urlsplit(path).path
    return page == '/news/development' or page.startswith('/news/development/')


def _in_gm(path):
    """True for /news/gm and anything beneath it: those pages are the bridge's own, never server.route's."""
    page = urllib.parse.urlsplit(path).path
    return page == '/news/gm' or page.startswith('/news/gm/')


def _assn_page_stem(ctx, path):
    """The STEM of an association's news page (/news/<STEM>/, the path with no query), or None: the game's associations
    only, matched without case."""
    m = ASSN_PAGE_RE.fullmatch(urllib.parse.urlsplit(path).path)
    if m is None:
        return None
    stem = m.group(1).upper()
    return stem if stem in watch.associations(ctx.game) else None


def _league(ctx, stem):
    """What the development pages read of one association (STEM upper-cased): its label and season year, its teams (from
    the ASN), and its players and birth serials (from the PYR). None when the game has no association with that STEM."""
    stem = stem.upper()
    asn = watch.associations(ctx.game).get(stem)
    if asn is None:
        return None
    info = gamedata.association(asn)
    pyr = gamedata.find(os.path.join(ctx.game, 'Assn'), stem + '.PYR')
    return types.SimpleNamespace(stem=stem, label=createweb._label(stem, asn), year=info['season_year'],
                                 teams=info['teams'], players=gamedata.players(pyr) if pyr else {},
                                 births=focus.births(pyr) if pyr else {}, pyr=pyr)


def _mods_dir(game, make=False):
    """A descriptor for <game>/Mods, opened from the game's descriptor without following a symlink. With make the
    directory is made when missing (mkdir relative to the game's descriptor)."""
    gfd = open_dir(game)
    try:
        if make:
            try:
                os.mkdir('Mods', dir_fd=gfd)
            except FileExistsError:
                pass
        return os.open('Mods', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=gfd)
    finally:
        os.close(gfd)


def _read_focus(game):
    """The entries in <game>/Mods/focus.txt: none when Mods or the file is missing, when Mods is a symlink, or when the
    file is not a regular file.
    At most MAX_FILE bytes are read."""
    try:
        mods = _mods_dir(game)
    except OSError:             # no Mods, or Mods is a symlink (ELOOP) or not a directory
        return []
    try:
        return focus.parse(_read(mods, FOCUS_FILE, focus.MAX_FILE).decode('latin-1'))
    finally:
        os.close(mods)


def _write_focus(game, entries):
    """Writes <game>/Mods/focus.txt, making Mods when missing. The text goes to focus.tmp in Mods (an old one removed,
    then O_EXCL|O_NOFOLLOW) and is renamed over focus.txt through the Mods descriptor, which replaces a symlink rather
    than writing through it."""
    mods = _mods_dir(game, make=True)
    try:
        _remove(mods, FOCUS_TMP)
        fd = os.open(FOCUS_TMP, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=mods)
        with os.fdopen(fd, 'wb') as fh:
            fh.write(focus.format(entries).encode('latin-1'))
        os.replace(FOCUS_TMP, FOCUS_FILE, src_dir_fd=mods, dst_dir_fd=mods)
    finally:
        os.close(mods)


def _focus_of(entries, pid, birth):
    """The kind a player is focused on, or None."""
    entry = focus.find(entries, pid, birth)
    return None if entry is None else entry['kind']


def _who(p, year):
    """'<name> (<pos>, <age>)', the age left out when the season year or the birth year is unknown."""
    if year is None or p['born'] is None:
        return '%s (%s)' % (p['name'], p['pos'])
    return '%s (%s, %d)' % (p['name'], p['pos'], year - p['born'])


def _heading(title):
    """A page title as the body's heading, underlined as html_to_text writes a page's h1: the in-game reader shows the
    title only in the window caption, which a Wine desktop with no window manager never draws."""
    return [title, '=' * len(title), '']


def _player_page(lg, entries, pid, status, note=''):
    """(status, path, title, text, links) for a player's page as entries leave him, after an optional note."""
    p = lg.players[pid]
    kind = _focus_of(entries, pid, lg.births[pid])
    tid = next((t for t in sorted(lg.teams) if pid in lg.teams[t]['roster']), None)
    base = '/news/development/%s/p/%d' % (lg.stem, pid)
    title = _who(p, lg.year)
    lines = ([note, ''] if note else []) + _heading(title)
    lines += ['Current focus: %s' % kind if kind else 'No focus.']
    lines += ['Team: %s' % lg.teams[tid]['name'] if tid is not None else 'Free agent']
    links = [('Focus on %s' % k, '%s/set/%s' % (base, k)) for k in focus.kinds_for(p['pos'])]
    if kind is not None:
        links.append(('Clear focus', base + '/clear'))
    if tid is not None:
        links.append(('Back to %s' % lg.teams[tid]['name'], '/news/development/%s/team/%d' % (lg.stem, tid)))
    links.append(('All teams', '/news/development/%s/' % lg.stem))
    return status, base, title, '\n'.join(lines), links


def _dev_association(ctx, stem):
    lg = _league(ctx, stem)
    if lg is None:
        return None
    entries = _read_focus(ctx.game)
    count = sum(1 for e in entries if e['assn'] == lg.stem)
    named = [e for e in entries if e['assn'] == lg.stem and e['pid'] in lg.players]
    title = 'Player development: %s' % lg.label
    text = _heading(title) + ['Players with a focus (%d of %d):' % (count, focus.MAX_PER_ASSN)]
    text += ['%s: %s' % (lg.players[e['pid']]['name'], e['kind']) for e in named]
    text += ['', 'Pick a team to choose a focus.']
    links = [('%s: %s' % (lg.players[e['pid']]['name'], e['kind']), '/news/development/%s/p/%d' % (lg.stem, e['pid']))
             for e in named]
    links += [(team['name'] or 'Team %d' % tid, '/news/development/%s/team/%d' % (lg.stem, tid))
              for tid, team in sorted(lg.teams.items())]
    return 200, '/news/development/%s/' % lg.stem, title, '\n'.join(text), links


def _dev_team(ctx, stem, tid):
    lg = _league(ctx, stem)
    tid = int(tid)
    if lg is None or tid not in lg.teams:
        return None
    team = lg.teams[tid]
    entries = _read_focus(ctx.game)
    named = sorted((pid for pid in team['roster'] if pid in lg.players), key=lambda pid: (lg.players[pid]['name'], pid))
    hitters = [pid for pid in named if lg.players[pid]['pos'] != 'P']
    pitchers = [pid for pid in named if lg.players[pid]['pos'] == 'P']
    links = []
    for pid in hitters + pitchers:
        kind = _focus_of(entries, pid, lg.births[pid])
        label = _who(lg.players[pid], lg.year) + ('' if kind is None else ': %s' % kind)
        links.append((label, '/news/development/%s/p/%d' % (lg.stem, pid)))
    links.append(('All teams', '/news/development/%s/' % lg.stem))
    title = '%s: development' % team['name']
    return (200, '/news/development/%s/team/%d' % (lg.stem, tid), title,
            '\n'.join(_heading(title) + ['Pick a player to set his focus.']), links)


def _dev_player(ctx, stem, pid):
    lg = _league(ctx, stem)
    pid = int(pid)
    if lg is None or pid not in lg.players:
        return None
    return _player_page(lg, _read_focus(ctx.game), pid, 200)


def _dev_set(ctx, stem, pid, kind):
    lg = _league(ctx, stem)
    pid = int(pid)
    if lg is None or pid not in lg.players or kind not in focus.kinds_for(lg.players[pid]['pos']):
        return None
    with _FOCUS_LOCK:
        entries = _read_focus(ctx.game)
        try:
            entries = focus.set_focus(entries, lg.stem, pid, lg.births[pid], kind)
        except focus.FocusFull:
            return _player_page(lg, entries, pid, 409, FULL_TEXT)
        _write_focus(ctx.game, entries)
    return _player_page(lg, entries, pid, 200, 'Focus set: %s.' % kind)


def _dev_clear(ctx, stem, pid):
    lg = _league(ctx, stem)
    pid = int(pid)
    if lg is None or pid not in lg.players:
        return None
    with _FOCUS_LOCK:
        entries = focus.clear_focus(_read_focus(ctx.game), pid, lg.births[pid])
        _write_focus(ctx.game, entries)
    return _player_page(lg, entries, pid, 200, 'Focus cleared.')


DEV_PAGES = (
    (re.compile(r'/news/development/([A-Za-z0-9]{1,8})/'), _dev_association),
    (re.compile(r'/news/development/([A-Za-z0-9]{1,8})/team/([0-9]{1,2})'), _dev_team),
    (re.compile(r'/news/development/([A-Za-z0-9]{1,8})/p/([0-9]{1,5})'), _dev_player),
    (re.compile(r'/news/development/([A-Za-z0-9]{1,8})/p/([0-9]{1,5})/set/([a-z]+)'), _dev_set),
    (re.compile(r'/news/development/([A-Za-z0-9]{1,8})/p/([0-9]{1,5})/clear'), _dev_clear),
)


def _development(ctx, path):
    """The reply for a path under /news/development: the page its route names, else Not found."""
    built = None
    for pattern, page in DEV_PAGES:
        m = pattern.fullmatch(path)
        if m is not None:
            built = page(ctx, *m.groups())
            break
    if built is None:
        return _news_reply(404, path, 'Not found', 'Not found.', [])
    return _news_reply(*built)


# The player card under /news/card/<STEM>/p/<pid>: what the game's card shows for one player, as text for the Mods menu's
# reader. It reads the association's files (ASN, PYR, PYF, Stats) and the watcher's data folder, which need not have had
# a pass. Ratings are shown now and at peak; a stats row is shown for each period the stats file has for him.
CARD_RE = re.compile(r'/news/card/([A-Za-z0-9]{1,8})/p/([0-9]{1,5})(?:/(batting|pitching|career|news)(?:/([0-9]{1,3}))?)?')
CARD_TABS = (('', 'Overview'), ('batting', 'Batting'), ('pitching', 'Pitching'), ('career', 'Career'), ('news', 'News'))
CAREER_ROWS = 20                # career table rows a page shows (the totals rows go on the last page)
CARD_NEWS = 10                  # news items a card lists, newest first
CARD_SCAN = 2000                # story files searched for a name: the newest by modification time
PAST_RE = re.compile(r'[0-9]{4}(?:-[0-9]{1,2})?')   # a past/<D> archived season folder (year, or year-2, -3)
CARD_PERIODS = ((0, 'Last 7 days'), (1, 'This season'), (3, 'Last season'), (2, 'Career'))     # (stats scope, label)
BAT_COLS = ('G', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'BB', 'SO', 'SB', 'AVG', 'OBP', 'SLG')
PIT_COLS = ('G', 'W', 'L', 'SV', 'IP', 'H', 'ER', 'BB', 'SO', 'HR', 'ERA', 'WHIP')
HIT_RATINGS = ('contact', 'power', 'speed', 'arm')
PIT_RATINGS = ('stamina', 'control', 'hold', 'strikeout')
NO_RATING = '-'


def _in_card(path):
    """True for /news/card and anything beneath it: those pages are the bridge's own, never server.route's."""
    page = urllib.parse.urlsplit(path).path
    return page == '/news/card' or page.startswith('/news/card/')


def _rate(num, den):
    """A rate as the game prints it: .xyz, or 1.000 at one; '---' with nothing to divide by."""
    if den <= 0:
        return '---'
    v = round(1000 * num / den)
    return '%d.%03d' % divmod(v, 1000) if v >= 1000 else '.%03d' % v


def _bat_row(label, b):
    """One batting period as the card's row, from a gamedata.season_lines batting line."""
    tb = b['h1b'] + 2 * b['h2b'] + 3 * b['h3b'] + 4 * b['hr']
    counts = (b['g'], b['ab'], b['r'], b['h'], b['h2b'], b['h3b'], b['hr'], b['rbi'], b['bb'], b['so'], b['sb'])
    on_base = b['h'] + b['bb'] + b['hbp']
    reach = b['ab'] + b['bb'] + b['hbp'] + b['sf']
    return [label] + [str(n) for n in counts] + [_rate(b['h'], b['ab']), _rate(on_base, reach), _rate(tb, b['ab'])]


def _pit_row(label, q):
    """One pitching period as the card's row, from a gamedata.season_lines pitching line."""
    outs = q['outs']
    era = '---' if not outs else '%.2f' % (27 * q['er'] / outs)
    whip = '---' if not outs else '%.2f' % (3 * (q['h'] + q['bb']) / outs)
    return [label, str(q['g']), str(q['w']), str(q['l']), str(q['sv']), '%d.%d' % divmod(outs, 3), str(q['h']),
            str(q['er']), str(q['bb']), str(q['so']), str(q['hr']), era, whip]


def _grade(value):
    return NO_RATING if value is None else str(scout.grade(value))


def _rating_rows(rec, pos):
    """The card's rating rows (name, now grade, peak grade): a pitcher's own set and the pitches he has (now or peak
    above zero), a hitter's four hitting ratings and his fielding at his own position."""
    ratings = gamedata.ratings(rec)
    if pos == 'P':
        keys = PIT_RATINGS
    else:
        keys = HIT_RATINGS + ((pos,) if pos in gamedata.POSITIONS else ())
    rows = []
    for k in keys:
        now, peak = ratings[k]
        label = create.RATING_LABELS.get(k, 'Fielding (%s)' % k)
        rows.append([label, _grade(now), _grade(peak)])
    if pos == 'P':
        for code in gamedata.PITCH_CODES:
            now, peak = ratings[code]
            if now or peak:
                rows.append([create.PITCH_LABELS[code], _grade(now), _grade(peak)])
    return rows


def _off_roster(ctx, lg, pid):
    """'Free agent' for a player in the association's free agent file, 'Retired' for one in none of the rosters, or 'Not
    on a roster' when that file cannot be read."""
    pyf = gamedata.find(os.path.join(ctx.game, 'Assn'), lg.stem + '.PYF')
    try:
        free = gamedata.free_agents(pyf) if pyf else None
    except (OSError, ValueError):
        free = None
    if free is None:
        return 'Not on a roster'
    return 'Free agent' if pid in free else 'Retired'


def _card_stats(ctx, lg, pid):
    """(batting rows, pitching rows, career games by position) for one player from the association's Stats DAT: a row
    for each period the file has him in, none when the association has no stats file."""
    stats_dir = os.path.join(ctx.game, 'Stats')
    dat = gamedata.find(stats_dir, lg.stem + '.DAT') if os.path.isdir(stats_dir) else None
    if dat is None:
        return [], [], {}
    bat, pit = [], []
    for scope, label in CARD_PERIODS:
        lines = gamedata.season_lines(dat, scope)
        if pid in lines['bat']:
            bat.append(_bat_row(label, lines['bat'][pid]))
        if pid in lines['pit']:
            pit.append(_pit_row(label, lines['pit'][pid]))
    return bat, pit, gamedata.career_games(dat).get(pid, {})


def _strings_of(value):
    """Every string inside a decoded JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings_of(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings_of(v)


def _int_of(value):
    return value if type(value) is int else 0


def _move_key(ev):
    """A transaction event's place in time as (season, month, day, 0). An offseason event is dated to the season before
    the one it is named for, after that season's last day."""
    year = _int_of(ev.get('year'))
    date = ev.get('date') if isinstance(ev.get('date'), str) else ''
    if date == 'Offseason':
        return (year - 1, 13, 0, 0)
    month, _, day = date.partition(' ')
    if month in recap.MONTHS and day.isdigit():
        return (year, recap.MONTHS.index(month) + 1, int(day), 0)
    return (year, 0, 0, 0)


def _recent_stories(folder, sub='recaps', limit=None):
    """(key, story) for the newest story files of a watcher folder's sub (a folder relative path), by modification
    time: at most limit of them read (CARD_SCAN when limit is None)."""
    rdir = os.path.join(folder, sub)
    try:
        names = [n for n in os.listdir(rdir) if n.endswith('.json') and server.KEY_RE.fullmatch(n[:-len('.json')])]
    except OSError:
        return []

    def mtime(name):
        try:
            return os.path.getmtime(os.path.join(rdir, name))
        except OSError:
            return 0.0
    out = []
    for name in sorted(names, key=mtime, reverse=True)[:CARD_SCAN if limit is None else limit]:
        rec = server._read_obj(os.path.join(rdir, name))
        if rec is not None:
            out.append((name[:-len('.json')], rec))
    return out


def _past_dirs(folder):
    """The past/<D> folder names of a watcher folder that match PAST_RE, newest season first (the year, then the
    archive number, both descending)."""
    try:
        names = os.listdir(os.path.join(folder, 'past'))
    except OSError:
        return []
    return sorted((n for n in names if PAST_RE.fullmatch(n)), key=lambda n: (int(n[:4]), int(n[5:] or 0)),
                  reverse=True)


def _past_year(folder, d):
    """A past folder's season: past/<D>/meta.json's season_year when it is an int (bool excluded), else the folder
    name's year."""
    meta = server._read_obj(os.path.join(folder, 'past', d, 'meta.json'))
    year = meta.get('season_year') if isinstance(meta, dict) else None
    return year if type(year) is int else int(d[:4])


def _watch_folder(ctx, stem):
    """The watcher's data folder for an association (matched without case), or None when there is none."""
    if not os.path.isdir(ctx.data):
        return None
    folder = gamedata.find(ctx.data, stem)
    return folder if folder and os.path.isdir(folder) else None


def _card_news(folder, lg, pid):
    """The news that names a player, newest first, as (label, path): the game stories from the watcher's folder and
    its past/<D> seasons whose text has his name (a story's place in time is its season, which is the association's
    for the current stories and the past folder's season_year for an archived one, then month, day and slot), and
    the transaction log's events for his id (_move_key). [] with no folder."""
    if folder is None:
        return []
    stem, year = os.path.basename(folder), lg.year or 0
    pattern = re.compile(r'(?<!\w)%s(?!\w)' % re.escape(lg.players[pid]['name']))

    def story(key, rec, season, path):
        if not pattern.search(' '.join(_strings_of(rec))):
            return
        head = rec.get('headline')
        label = head if isinstance(head, str) and head else '(untitled)'
        items.append(((season, _int_of(rec.get('month')), _int_of(rec.get('day')), _int_of(rec.get('slot'))), label,
                      path))
    items = []
    current = _recent_stories(folder)
    left = CARD_SCAN - len(current)                         # the cap is spent on the current season's stories first
    for key, rec in current:
        story(key, rec, year, '/news/%s/%s' % (stem, key))
    log = server._read_obj(os.path.join(folder, 'moves', 'log.json'))
    events = log.get('events') if isinstance(log, dict) else None
    for ev in events if isinstance(events, list) else []:
        label = server._move_text(ev) if isinstance(ev, dict) and ev.get('pid') == pid else ''
        if label:
            note, path = ev.get('note'), '/news/%s/moves' % stem
            if type(note) is int and server.NOTE_RE.fullmatch(str(note)) and \
                    os.path.isfile(os.path.join(folder, 'moves', 'notes', '%d.json' % note)):
                path = '/news/%s/moves/%d' % (stem, note)
            items.append((_move_key(ev), label, path))
    for d in _past_dirs(folder):                            # then past seasons, newest first
        if left <= 0:
            break
        found = _recent_stories(folder, os.path.join('past', d, 'recaps'), limit=left)
        left -= len(found)
        for key, rec in found:
            story(key, rec, _past_year(folder, d), '/news/%s/past/%s/%s' % (stem, d, key))
    items.sort(key=lambda item: item[0], reverse=True)
    return [(label, path) for _, label, path in items[:CARD_NEWS]]


def _card_page(ctx, stem, pid):
    """(title, text, links) for a player's card, or None when the game has no such association or player."""
    lg = _league(ctx, stem)
    if lg is None or pid not in lg.players:
        return None
    p, rec = lg.players[pid], gamedata.record(lg.pyr, pid)
    tid = next((t for t in sorted(lg.teams) if pid in lg.teams[t]['roster']), None)
    team = (lg.teams[tid]['name'] or 'Team %d' % tid) if tid is not None else _off_roster(ctx, lg, pid)
    title = _who(p, lg.year)
    lines = _heading(title) + ['Team: %s' % team, 'Position: %s' % (p['pos'] or '?')]
    if lg.year is not None and p['born'] is not None:
        lines.append('Age: %d' % (lg.year - p['born']))
    if p['bats'] or p['throws']:
        lines.append('Bats/throws: %s/%s' % (p['bats'] or '?', p['throws'] or '?'))
    rows = _rating_rows(rec, p['pos'])
    if rows:
        lines += [''] + _grid([['Ratings', 'Now', 'Peak']] + rows)
    bat, pit, games = _card_stats(ctx, lg, pid)
    if bat:
        lines += [''] + _grid([['Batting'] + list(BAT_COLS)] + bat)
    if pit:
        lines += [''] + _grid([['Pitching'] + list(PIT_COLS)] + pit)
    if not bat and not pit:
        lines += ['', 'No batting or pitching lines in the stats file.']
    if games:
        lines += ['', 'Career games by position: ' + ', '.join('%s %d' % (pos, games[pos])
                                                              for pos in gamedata.POSITIONS if pos in games)]
    kind = _focus_of(_read_focus(ctx.game), pid, lg.births[pid])
    lines += ['', 'Current focus: %s' % kind if kind else 'No focus.']
    folder = _watch_folder(ctx, lg.stem)
    news = _card_news(folder, lg, pid)
    lines += ['', 'News'] + (['- %s' % label for label, _ in news] or ['No news yet.'])
    links = list(news) + [('Player development', '/news/development/%s/p/%d' % (lg.stem, pid))]
    if folder is not None:
        links.append(('Association news', '/news/%s/' % os.path.basename(folder)))
    return title, '\n'.join(lines), links


def _card(ctx, path):
    """The reply for a path under /news/card: the player's card as a picture page (_card_image) when the game's fonts
    can be read, else as text; Not found for anything else."""
    m = CARD_RE.fullmatch(urllib.parse.urlsplit(path).path)
    fonts = _card_fonts(ctx.game) if m else None
    if m and fonts is not None:
        built = _card_image(ctx, fonts, m.group(1), int(m.group(2)), m.group(3) or '', int(m.group(4) or 0))
        if built is not None:
            return built
    built = _card_page(ctx, m.group(1), int(m.group(2))) if m else None      # text: every tab is the one page
    if built is None:
        return _news_reply(404, path, 'Not found', 'No such association or player.' if m else 'Not found.', [])
    return _news_reply(200, path, *built)


_FONTS = {}


def _card_fonts(game):
    """The game's own fonts and palette for card pictures (cardimg.Fonts), read once per game folder; None when they
    cannot be read (the card is then text)."""
    if game not in _FONTS:
        try:
            _FONTS[game] = cardimg.Fonts.load(game)
        except (OSError, cardimg.FontError):
            _FONTS[game] = None
    return _FONTS[game]


def _card_who(lg, pid):
    """(first name, last name, birth date or None) of a player from his PYR record."""
    rec = gamedata.record(lg.pyr, pid)
    try:
        born = datetime.date.fromordinal(lg.births[pid] - 365)
    except (KeyError, ValueError, OverflowError):
        born = None
    return gamedata.cstr(rec[30:47]).strip(), gamedata.cstr(rec[47:64]).strip(), born


def _lahman_path(ctx):
    """The Lahman database for the card's real seasons: the bridge's --db, else history.find_db; None when neither."""
    db = getattr(ctx, 'db', None)
    return db if db and os.path.isfile(db) else history.find_db()


def _short_team(name):
    """A team's short label for the career table: the initials of its name, at most three ('New York Yankees' NYY)."""
    words = [w for w in re.split(r'[^A-Za-z0-9]+', name or '') if w]
    if len(words) == 1:
        return words[0][:3].upper()
    return ''.join(w[0] for w in words)[:3].upper()


def _career(ctx, lg, pid, kind, first, last, born):
    """(rows, lahman id) for a player's career table: his real seasons before the association's start year (Lahman,
    when the database and a match exist), the seasons the watcher archived, and this season from the stats file."""
    start, lid, real = history.start_year(lg.stem, lg.year), None, []
    path = _lahman_path(ctx)
    if path and born is not None:
        try:
            conn = history.open_db(path)    # one per request: each request runs in its own thread
            try:
                lid = history.lahman_id(conn, first, last, born)
                real = history.real_seasons(conn, lid, kind, before=start) if lid else []
            finally:
                conn.close()
        except sqlite3.Error:
            lid, real = None, []
    sim = history.sim_seasons(ctx.data, lg.stem, pid, kind) if os.path.isdir(ctx.data) else []
    sim = history.drop_seeded(sim, lg.stem)
    for r in sim:
        r['team'] = _short_team(r['team'])            # the archive keeps the team's full name
    stats_dir = os.path.join(ctx.game, 'Stats')
    dat = gamedata.find(stats_dir, lg.stem + '.DAT') if os.path.isdir(stats_dir) else None
    keys = history.BAT_KEYS if kind == 'bat' else history.PIT_KEYS
    if dat is not None and lg.year is not None and not any(r['year'] == lg.year for r in sim):
        line = gamedata.season_lines(dat, 1)[kind].get(pid)
        tid = next((t for t in sorted(lg.teams) if pid in lg.teams[t]['roster']), None)
        if line and line.get('g'):
            sim.append(dict({k: line.get(k, 0) for k in keys}, year=lg.year,
                            team=_short_team(lg.teams[tid]['name']) if tid is not None else ''))
    rows = history.merge(real, sim, start)
    other = None
    career = gamedata.season_lines(dat, 2)[kind].get(pid) if dat is not None else None
    if career:
        listed = history.totals(rows, kind)
        diff = {k: career.get(k, 0) - listed[k] for k in keys}
        if diff['g'] > 0:
            # Games the game counts in his career that no row lists (played before archiving). When some stat is short
            # the career line comes from other data than the rows (stock MLBPA files): report the games only.
            other = diff if all(v >= 0 for v in diff.values()) else {'g': diff['g'], 'short': True}
    return rows, lid, other


def _other_note(rows, season=None):
    """The note under an Other row: the years it covers when they fall between the last real season and the first
    archived one (simmed before archiving existed), or the season before this one when nothing is archived yet; else
    the generic text."""
    real = [r['year'] for r in rows if not r['sim']]
    played = [r['year'] for r in rows if r['sim']]
    end = min(played) if played else season if type(season) is int else None
    if real and end is not None:
        lo, hi = max(real) + 1, end - 1
        if lo <= hi:
            if lo == hi:
                return 'Other: %d, a season simmed before it was saved.' % lo
            return 'Other: %d to %d, seasons simmed before they were saved.' % (lo, hi)
    return 'Other: career games the game kept with no season.'


def _career_cells(year, team, line, kind):
    if kind == 'bat':
        b = dict(line, h1b=line['h'] - line['h2b'] - line['h3b'] - line['hr'])
        return [str(year), team] + _bat_row('', b)[1:]
    return [str(year), team] + _pit_row('', line)[1:]


def _card_tab_body(ctx, lg, pid, tab, page, p, rec, base, who):
    """The body dict for one tab of the card picture (cardimg's 'body')."""
    if tab in ('batting', 'pitching'):
        bat, pit, _ = _card_stats(ctx, lg, pid)
        rows, cols = (bat, BAT_COLS) if tab == 'batting' else (pit, PIT_COLS)
        return {'kind': 'table', 'caption': '%s by period' % tab.capitalize(), 'columns': ['Period'] + list(cols),
                'rows': [{'cells': r, 'color': 'yellow' if r[0] == 'Career' else 'white'} for r in rows],
                'note': None if rows else 'No %s lines in the stats file yet.' % tab}
    if tab == 'career':
        kind = 'pit' if p['pos'] == 'P' else 'bat'
        rows, lid, other = _career(ctx, lg, pid, kind, *who)
        cells = [{'cells': _career_cells(r['year'], r['team'], r, kind), 'color': 'yellow' if r['sim'] else 'white'}
                 for r in rows]
        line = other if other is not None and not other.get('short') else None
        if line is not None:
            at = next((i for i, r in enumerate(rows) if r['sim']), len(rows))     # before the association's seasons
            cells.insert(at, {'cells': _career_cells('Other', '', line, kind), 'color': 'yellow'})
        if cells:
            tot = history.totals(rows + ([line] if line is not None else []), kind)
            cells.append({'cells': _career_cells('Total', '%d yr' % len(rows) if rows else '', tot, kind),
                          'bold': True})
        pages = max(1, -(-len(cells) // CAREER_ROWS))
        page = min(page, pages - 1)
        cols = ['Year', 'Team'] + list(BAT_COLS if kind == 'bat' else PIT_COLS)
        if line is not None:
            note = _other_note(rows, lg.year)
        elif other is not None:
            note = 'The game counts %d more career games; those seasons were not archived.' % other['g']
        else:
            note = None if cells else 'No seasons on record yet.'
        return {'kind': 'table', 'columns': cols, 'rows': cells[page * CAREER_ROWS:(page + 1) * CAREER_ROWS],
                'caption': 'Career %s, page %d of %d%s' % ('pitching' if kind == 'pit' else 'batting', page + 1, pages,
                                                            '.   White: real seasons.   Yellow: this association.'
                                                            if lid else ''),
                'note': note, 'prev': '%s/career/%d' % (base, page - 1) if page > 0 else None,
                'next': '%s/career/%d' % (base, page + 1) if page + 1 < pages else None}
    if tab == 'news':
        folder = _watch_folder(ctx, lg.stem)
        news = _card_news(folder, lg, pid)
        items = [('Latest news', None)] + (news or [('No news yet.', None)]) + [('More', None),
                                                                                ('Player development',
                                                                                 '/news/development/%s/p/%d' % (lg.stem, pid))]
        if folder is not None:
            items.append(('Association news', '/news/%s/' % os.path.basename(folder)))
        return {'kind': 'links', 'caption': None, 'items': items}
    ratings = gamedata.ratings(rec)
    keys = PIT_RATINGS if p['pos'] == 'P' else HIT_RATINGS + ((p['pos'],) if p['pos'] in gamedata.POSITIONS else ())
    rows = []
    for k in keys:
        now, peak = ratings[k]
        peak = now if peak is None else peak            # strikeout has no peak of its own
        rows.append((create.RATING_LABELS.get(k, 'Fielding (%s)' % k), scout.grade(now), scout.grade(peak)))
    if p['pos'] == 'P':
        rows += [(create.PITCH_LABELS[c], scout.grade(ratings[c][0]), scout.grade(ratings[c][1]))
                 for c in gamedata.PITCH_CODES if ratings[c][0] or ratings[c][1]]
    kind = _focus_of(_read_focus(ctx.game), pid, lg.births[pid])
    facts = [('Focus', kind or 'none')]
    # The facts column fits at most 8 characters: the career games from the stats file's career line (one
    # season_lines call), then up to the three positions he has played most; a position fact is skipped when it would
    # only repeat the Games fact (a pure pitcher with P 427 and Games 427).
    stats_dir = os.path.join(ctx.game, 'Stats')
    dat = gamedata.find(stats_dir, lg.stem + '.DAT') if os.path.isdir(stats_dir) else None
    games = gamedata.career_games(dat).get(pid, {}) if dat is not None else {}
    try:
        lines = gamedata.season_lines(dat, 2) if dat is not None else None
    except (OSError, ValueError):               # a bad stats file: no career line
        lines = None
    bat, pit = (lines['bat'], lines['pit']) if lines is not None else ({}, {})
    own, other = (pit, bat) if p['pos'] == 'P' else (bat, pit)
    if pid in own:
        career = own[pid]['g']
    elif pid in other:
        career = other[pid]['g']
    else:
        career = sum(games.values())
    if career:
        facts.append(('Games', str(career)))
        tops = sorted((g for g in gamedata.POSITIONS if games.get(g)),
                      key=lambda g: (-games[g], gamedata.POSITIONS.index(g)))
        if len(tops) != 1 or games[tops[0]] != career:
            facts += [(g, str(games[g])) for g in tops[:3]]
    seed = zlib.crc32(('%s|%s' % (p['name'], lg.births.get(pid))).encode('latin-1', 'replace'))
    tid = next((t for t in sorted(lg.teams) if pid in lg.teams[t]['roster']), None)
    team = lg.teams[tid]['name'] if tid is not None else ''
    pic = portrait.portrait(seed, age=(lg.year - p['born']) if lg.year and p['born'] else 28, pos=p['pos'],
                            power=scout.grade(ratings['power'][0]), speed=scout.grade(ratings['speed'][0]),
                            bats=p['bats'], throws=p['throws'], era=lg.year or 1998, letter=team[:1])
    return {'kind': 'overview', 'portrait': pic, 'ratings': rows, 'facts': facts,
            'links': [('Player development', '/news/development/%s/p/%d' % (lg.stem, pid))]}


def _card_image(ctx, fonts, stem, pid, tab, page):
    """(header, body, picture) for one tab of a player's card drawn with the game's fonts, or None when the game has no
    such association or player. The header carries image=1 and the picture's click regions as hot.N = 'x,y,w,h<TAB>
    path'; the body is a short text for a reader without picture support, and the links are the tabs."""
    lg = _league(ctx, stem)
    if lg is None or pid not in lg.players:
        return None
    p, rec = lg.players[pid], gamedata.record(lg.pyr, pid)
    base = '/news/card/%s/p/%d' % (lg.stem, pid)
    tid = next((t for t in sorted(lg.teams) if pid in lg.teams[t]['roster']), None)
    team = (lg.teams[tid]['name'] or 'Team %d' % tid) if tid is not None else _off_roster(ctx, lg, pid)
    who = _card_who(lg, pid)
    head = [p['pos'] or '?', team]
    if lg.year is not None and p['born'] is not None:
        head.append('Age %d' % (lg.year - p['born']))
    head.append('Bats %s, throws %s' % (p['bats'] or '?', p['throws'] or '?'))
    line2 = ['Born %s' % who[2].strftime('%b %-d, %Y') if who[2] else 'Birth date unknown']
    body = _card_tab_body(ctx, lg, pid, tab, page, p, rec, base, who)
    tabs = [(label, base + ('/' + key if key else ''), key == tab) for key, label in CARD_TABS]
    card = {'title': p['name'], 'subtitle': lg.label, 'tabs': tabs,
            'header': ['   |   '.join(head), '   |   '.join(line2)], 'body': body,
            'status_left': 'Click a tab or a link. Back returns to the last page.',
            'status_right': '%d season' % lg.year if lg.year else ''}
    bmp, hots = cardimg.render(card, fonts)
    path = base + ('/' + tab if tab else '') + ('/%d' % page if tab == 'career' and page else '')
    header, text = _news_reply(200, path, p['name'], '\n'.join(_heading(_who(p, lg.year)) +
                                                                ['This card is a picture page.']),
                               [(label, target) for label, target, sel in tabs if not sel])
    header += [('image', '1'), ('hots', str(len(hots)))]
    header += [('hot.%d' % i, '%d,%d,%d,%d\t%s' % (x, y, w, h, _plain(target)))
               for i, (x, y, w, h, target) in enumerate(hots)]
    return header, text, bmp


# The offseason trades under /news/gm/ (aigm.py). The season's ledger is <data>/<STEM>/gm.json; the ASN is written only
# after aigm.validate passes, with a copy of it first. Everything here runs under _GM_LOCK.
GM_FILE = 'gm.json'
OPEN_TEXT = '%s is open in the game. Go back to the main menu, then try again.'
BAD_LEDGER_TEXT = ('The trade record (%s/gm.json in the news data folder) cannot be read, so trades may already have '
                   'run this season. Move that file aside to run them again.')
_GM_LOCK = threading.Lock()


def _gm_league(ctx, stem):
    """What the offseason pages read of one association (STEM upper-cased): its label, season year, teams, players, the
    ASN's path and whether its season has started (a game has been played). None when the game has no association with
    that STEM."""
    stem = stem.upper()
    asn = watch.associations(ctx.game).get(stem)
    if asn is None:
        return None
    info = gamedata.association(asn)
    pyr = gamedata.find(os.path.join(ctx.game, 'Assn'), stem + '.PYR')
    return types.SimpleNamespace(stem=stem, asn=asn, label=createweb._label(stem, asn), year=info['season_year'],
                                 teams=info['teams'], players=gamedata.players(pyr) if pyr else {},
                                 started=any(g['played'] for g in info['games']))


def _ledger_for(ctx, stem, year):
    """The ledger of stem's season year, or None: a missing or unreadable file, one of another kind, or one for another
    season."""
    led = watch.read_json(os.path.join(ctx.data, stem, GM_FILE))
    if led is None or led.get('kind') != 'gm' or led.get('season_year') != year:
        return None
    if not isinstance(led.get('trades'), list) or not isinstance(led.get('proposals'), list):
        return None
    if not all(_entry_ok(t) for t in led['trades']) or not all(_entry_ok(p, True) for p in led['proposals']):
        return None
    return led


_GM_INTS = ('a', 'b', 'a_gives', 'b_gives')
_GM_NAMES = ('a_name', 'b_name', 'a_gives_name', 'b_gives_name')
_GM_STATUS = ('open', 'accepted', 'rejected', 'stale')


def _ledger_blocks_run(ctx, stem, year):
    """True when a gm.json is there that _ledger_for cannot use and that is not plainly another season's: unreadable,
    torn, hand-edited or of another kind. Trades may already have run from it, so a run must not plan them again over
    an ASN that already holds them. A readable ledger of another season is the normal case and may be replaced."""
    path = os.path.join(ctx.data, stem, GM_FILE)
    if not os.path.lexists(path):
        return False
    led = watch.read_json(path)
    return not (led is not None and led.get('kind') == 'gm' and type(led.get('season_year')) is int
                and led['season_year'] != year)


def _entry_ok(e, proposal=False):
    """True when a ledger trade (or proposal) has the fields the pages read with the right types: a hand-edited or
    corrupt gm.json then counts as missing instead of failing every page."""
    if not isinstance(e, dict):
        return False
    if not all(type(e.get(k)) is int for k in _GM_INTS) or not all(isinstance(e.get(k), str) for k in _GM_NAMES):
        return False
    if not all(e.get(k) is None or type(e.get(k)) is int for k in ('a_drops', 'b_drops')):
        return False
    return not proposal or e.get('status') in _GM_STATUS


def _write_ledger(ctx, stem, led):
    watch.write_json(os.path.join(ctx.data, stem, GM_FILE), led)


def _held(ctx, lg):
    """The association's game files some process holds open (create.open_by_anyone): the ASN, PYR, PYF and DAT."""
    assn_dir = os.path.join(ctx.game, 'Assn')
    stats = os.path.join(ctx.game, 'Stats')
    paths = [lg.asn, gamedata.find(assn_dir, lg.stem + '.PYR'), gamedata.find(assn_dir, lg.stem + '.PYF'),
             gamedata.find(stats, lg.stem + '.DAT') if os.path.isdir(stats) else None]
    return create.open_by_anyone([p for p in paths if p], ctx.proc)


def _read_bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _put_asn(ctx, lg, new):
    """Copies the ASN to a new folder under ctx.backup (named for the STEM and the time; a number is added when that
    second has one), then replaces it with new."""
    base = os.path.join(ctx.backup, '%s-%s-gm' % (lg.stem, datetime.datetime.now().strftime('%Y%m%dT%H%M%S')))
    folder, n = base, 1
    while os.path.exists(folder):
        n += 1
        folder = '%s-%d' % (base, n)
    os.makedirs(folder)
    shutil.copy2(lg.asn, folder)
    create._write_atomic(lg.asn, new)


def _team(lg, tid):
    return lg.teams[tid]['name'] or 'Team %d' % tid


def _named(lg, trade):
    """A trade or proposal with the names its lines show: the two teams' and the two players'."""
    out = dict(trade)
    out.update(a_name=_team(lg, trade['a']), b_name=_team(lg, trade['b']),
               a_gives_name=lg.players[trade['a_gives']]['name'], b_gives_name=lg.players[trade['b_gives']]['name'])
    return out


def _gm_reply(ctx, lg, status=200, note=''):
    """(status, path, title, text, links) for the offseason trades of lg: the season's trades and proposals when its
    ledger exists, else the run link while the preseason lasts. The note, when there is one, comes first."""
    base = '/news/gm/%s/' % lg.stem
    title = 'Offseason trades: %s' % lg.label
    led = _ledger_for(ctx, lg.stem, lg.year)
    body, links = [], []
    if led is not None:
        body += ['Trades made (%d):' % len(led['trades'])]
        body += ['%s trade %s to %s for %s' % (t['a_name'], t['a_gives_name'], t['b_name'], t['b_gives_name'])
                 for t in led['trades']]
        body += ['', 'Proposals for your teams:']
        for n, p in enumerate(led['proposals'], 1):
            body.append('%d. %s get %s, %s get %s (%s)' % (n, p['a_name'], p['b_gives_name'], p['b_name'],
                                                          p['a_gives_name'], p['status']))
            if p['status'] == 'open':
                links += [('Accept %d' % n, base + 'accept/%d' % n), ('Reject %d' % n, base + 'reject/%d' % n)]
        if not led['proposals']:
            body.append('None.')
    else:
        body += ['No trades yet this season.']
        if lg.started:
            body += ['Trades run in the preseason, before the first game.']
        else:
            body += ["Computer-run teams trade bench players to fill each other's needs.",
                     'Human-run teams only get proposals.']
            links += [('Run computer trades', base + 'run')]
    links += [('Player development', '/news/development/%s/' % lg.stem), ('League news', '/news/%s/' % lg.stem)]
    text = ([note, ''] if note else []) + _heading(title) + body
    return status, base, title, '\n'.join(text), links


def _gm_view(ctx, stem):
    with _GM_LOCK:
        lg = _gm_league(ctx, stem)
        return None if lg is None else _gm_reply(ctx, lg)


def _gm_run(ctx, stem):
    """Plans this preseason's computer trades, applies and checks them, writes the ASN (when there are any) and the
    ledger, once a season."""
    with _GM_LOCK:
        lg = _gm_league(ctx, stem)
        if lg is None:
            return None
        if lg.started:
            return _gm_reply(ctx, lg, 409, 'The season has started.')
        if _ledger_for(ctx, lg.stem, lg.year) is not None:
            return _gm_reply(ctx, lg, 409, 'Trades already ran this season.')
        if _ledger_blocks_run(ctx, lg.stem, lg.year):
            return _gm_reply(ctx, lg, 409, BAD_LEDGER_TEXT % lg.stem)
        if _held(ctx, lg):
            return _gm_reply(ctx, lg, 409, OPEN_TEXT % lg.label)
        old = _read_bytes(lg.asn)
        snap = aigm.read(old)
        found = aigm.plan(snap['windows'], lg.players, lg.year, snap['human'])
        new = old
        for trade in found['trades']:
            new = aigm.apply_trade(new, trade)
        problems = aigm.validate(snap['windows'], aigm.read(new)['windows'], lg.players)
        if problems:
            return _gm_reply(ctx, lg, 500, 'Trade check failed: %s' % problems[0])
        if found['trades']:
            _put_asn(ctx, lg, new)
        _write_ledger(ctx, lg.stem, {
            'kind': 'gm', 'season_year': lg.year, 'created': watch.now_iso(),
            'trades': [_named(lg, t) for t in found['trades']],
            'proposals': [dict(_named(lg, p), status='open') for p in found['proposals']]})
        return _gm_reply(ctx, lg, 200, '%d trades made.' % len(found['trades']))


def _gm_proposal(ctx, stem, n):
    """(lg, ledger, proposal) for proposal n of stem's season, or None when there is no such one. Callers hold
    _GM_LOCK."""
    lg = _gm_league(ctx, stem)
    led = None if lg is None else _ledger_for(ctx, lg.stem, lg.year)
    if led is None or not 1 <= n <= len(led['proposals']):
        return None
    return lg, led, led['proposals'][n - 1]


def _gm_accept(ctx, stem, n):
    """Writes proposal n into the ASN when it still fits the file (else it is stale). The game must not hold the files."""
    n = int(n)
    with _GM_LOCK:
        found = _gm_proposal(ctx, stem, n)
        if found is None:
            return None
        lg, led, prop = found
        if prop['status'] != 'open':
            return _gm_reply(ctx, lg, 409, 'Proposal %d is %s.' % (n, prop['status']))
        if _held(ctx, lg):
            return _gm_reply(ctx, lg, 409, OPEN_TEXT % lg.label)
        old = _read_bytes(lg.asn)
        try:
            new = aigm.apply_trade(old, prop)
        except aigm.SwapError:
            prop['status'] = 'stale'
            _write_ledger(ctx, lg.stem, led)
            return _gm_reply(ctx, lg, 200, 'Proposal %d is out of date.' % n)
        problems = aigm.validate(aigm.read(old)['windows'], aigm.read(new)['windows'], lg.players)
        if problems:
            return _gm_reply(ctx, lg, 500, 'Trade check failed: %s' % problems[0])
        _put_asn(ctx, lg, new)
        prop['status'] = 'accepted'
        _write_ledger(ctx, lg.stem, led)
        return _gm_reply(ctx, lg, 200, 'Trade made.')


def _gm_reject(ctx, stem, n):
    """Marks proposal n rejected. No game file is written."""
    n = int(n)
    with _GM_LOCK:
        found = _gm_proposal(ctx, stem, n)
        if found is None:
            return None
        lg, led, prop = found
        if prop['status'] != 'open':
            return _gm_reply(ctx, lg, 409, 'Proposal %d is %s.' % (n, prop['status']))
        prop['status'] = 'rejected'
        _write_ledger(ctx, lg.stem, led)
        return _gm_reply(ctx, lg, 200, 'Proposal rejected.')


GM_PAGES = (
    (re.compile(r'/news/gm/([A-Za-z0-9]{1,8})/'), _gm_view),
    (re.compile(r'/news/gm/([A-Za-z0-9]{1,8})/run'), _gm_run),
    (re.compile(r'/news/gm/([A-Za-z0-9]{1,8})/accept/([0-9]{1,3})'), _gm_accept),
    (re.compile(r'/news/gm/([A-Za-z0-9]{1,8})/reject/([0-9]{1,3})'), _gm_reject),
)


def _gm(ctx, path):
    """The reply for a path under /news/gm: the page its route names, else Not found."""
    built = None
    for pattern, page in GM_PAGES:
        m = pattern.fullmatch(path)
        if m is not None:
            built = page(ctx, *m.groups())
            break
    if built is None:
        return _news_reply(404, path, 'Not found', 'Not found.', [])
    return _news_reply(*built)


OPS = {'ping': _ping, 'assns': _assns, 'archetypes': _archetypes, 'create': _create, 'news': _news, 'build': _build}


def handle(ctx, req):
    """(header, body) for a parsed request. An unknown op is an error, and so is an exception inside an op."""
    fn = OPS.get(req['op'])
    if fn is None:
        return [('status', 'error')], 'Unknown request.'
    try:
        return fn(ctx, req)
    except Exception:
        traceback.print_exc()
        return [('status', 'error')], 'Something went wrong.'


def open_dir(path):
    """A descriptor for directory path, opened one component at a time from / with O_NOFOLLOW, so a symlink anywhere
    on the path raises OSError (ELOOP). The game side can write everything under the Wine prefix, so the bridge holds
    the spool by descriptor and works relative to it: renaming or swapping a directory afterwards never redirects it."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in [p for p in os.path.abspath(path).split(os.sep) if p]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
    except BaseException:
        os.close(fd)
        raise
    return fd


def make_spool(game):
    """Creates Mods/spool under game when missing, never through a symlink (mkdirat does not follow one)."""
    fd = open_dir(game)
    try:
        for part in ('Mods', 'spool'):
            try:
                os.mkdir(part, dir_fd=fd)
            except FileExistsError:
                pass
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
    finally:
        os.close(fd)


def _read(dfd, name, limit=MAX_REQUEST + 1):
    """Up to limit bytes of a file (a request by default, so an oversize one shows); b'' (a bad request, or no entries
    for focus.txt) unless it is a regular file. The game side can write the spool, so never follow a symlink and never
    block on a FIFO or device."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except OSError:             # ELOOP: a symlink
        return b''
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return b''
        chunks, left = [], limit
        while left > 0:
            chunk = os.read(fd, left)
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        return b''.join(chunks)
    finally:
        os.close(fd)


def _remove(dfd, name):
    try:
        os.remove(name, dir_fd=dfd)
    except FileNotFoundError:
        pass


def _put(dfd, rid, data, ext):
    """Writes data as r<rid>.tmp and renames it to r<rid>.<ext>, all relative to the spool descriptor."""
    tmp = 'r%s.tmp' % rid
    _remove(dfd, tmp)           # a name the game side planted (a symlink) goes, and O_EXCL never writes through one
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
    with os.fdopen(fd, 'wb') as fh:
        fh.write(data)
    os.replace(tmp, 'r%s.%s' % (rid, ext), src_dir_fd=dfd, dst_dir_fd=dfd)


def _respond(dfd, rid, header, body, picture=None):
    """Writes a reply; a picture page's BMP (r<rid>.bmp) goes first, so it is complete before the reader sees the
    .rsp that names it."""
    if picture is not None:
        _put(dfd, rid, picture, 'bmp')
    _put(dfd, rid, render(header, body), 'rsp')


def _answer(ctx, dfd, rid):
    """Claims request rid in the spool held by dfd, answers it and removes its work file. A request another worker
    has claimed is skipped."""
    work = 'q%s.work' % rid
    try:
        os.rename('q%s.req' % rid, work, src_dir_fd=dfd, dst_dir_fd=dfd)
    except FileNotFoundError:
        return
    try:
        req = parse_request(_read(dfd, work))
        if req is None:
            header, body, picture = [('status', 'error')], 'Bad request.', None
        else:
            header, body, *rest = handle(ctx, req)
            picture = rest[0] if rest else None
        _respond(dfd, rid, header, body, picture)
        op = req['op'] if req is not None and req['op'] in OPS else '-'
        sys.stderr.write('modbridge: %s %s %s\n' % (rid, op, dict(header)['status']))
    finally:
        _remove(dfd, work)


def _slot(ctx, dfd, rid):
    try:
        _answer(ctx, dfd, rid)
    finally:
        os.close(dfd)
        _SLOTS.release()


def process_spool(ctx, spool, wait=True):
    """Claims and answers every pending request in spool once, each in its own worker thread, at most MAX_WORKERS at a
    time; a request that finds every slot taken waits for the next call. With wait the workers are joined first.
    Raises OSError when the spool path holds a symlink (open_dir)."""
    threads = []
    dfd = open_dir(spool)
    try:
        for name in sorted(os.listdir(dfd)):
            m = REQ_RE.fullmatch(name)
            if m is None:
                continue
            if not _SLOTS.acquire(blocking=False):
                break
            own = os.dup(dfd)       # each worker closes its own descriptor
            t = threading.Thread(target=_slot, args=(ctx, own, m.group(1)), daemon=True)
            try:
                t.start()
            except BaseException:
                os.close(own)
                _SLOTS.release()
                raise
            threads.append(t)
    finally:
        os.close(dfd)
    if wait:
        for t in threads:
            t.join()


def spool_ok(game):
    """True when Mods and Mods/spool under game are real directories, not symlinks: the game side can write there,
    and the bridge removes and writes files in the spool with the host's permissions."""
    path = game
    for part in ('Mods', 'spool'):
        path = os.path.join(path, part)
        try:
            if not stat.S_ISDIR(os.lstat(path).st_mode):
                return False
        except FileNotFoundError:
            return False
    return True


def beat(spool, now=None):
    """Writes the unix time (whole seconds) and a newline to ALIVE in spool: the game's player card reads its age to tell
    whether a bridge is running. Through open_dir and alive.tmp (O_EXCL, O_NOFOLLOW, then os.replace), so a symlink the
    game side planted as either name is never written through."""
    now = time.time() if now is None else now
    dfd = open_dir(spool)
    try:
        _remove(dfd, 'alive.tmp')   # a name the game side planted goes, as in _put
        fd = os.open('alive.tmp', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
        with os.fdopen(fd, 'wb') as fh:
            fh.write(b'%d\n' % int(now))
        os.replace('alive.tmp', ALIVE, src_dir_fd=dfd, dst_dir_fd=dfd)   # replaces a symlink alive.txt itself
    finally:
        os.close(dfd)


def beat_due(last, now=None):
    """True when no beat has been made (last is None) or ALIVE_EVERY seconds have passed since last (time.monotonic)."""
    now = time.monotonic() if now is None else now
    return last is None or now - last >= ALIVE_EVERY


def housekeep(spool, now=None):
    """Removes replies (r*.rsp), their pictures (r*.bmp) and temporary files (*.tmp) older than STALE seconds by
    mtime. Work files are kept. Works through open_dir, so it never removes anything outside the spool."""
    now = time.time() if now is None else now
    dfd = open_dir(spool)
    try:
        for name in os.listdir(dfd):
            if not (name.endswith('.tmp') or (name.startswith('r') and name.endswith(('.rsp', '.bmp')))):
                continue
            try:
                if now - os.stat(name, dir_fd=dfd, follow_symlinks=False).st_mtime > STALE:
                    os.remove(name, dir_fd=dfd)
            except FileNotFoundError:
                pass
    finally:
        os.close(dfd)


def serve(ctx, poll):
    """Answers the game's spool until interrupted, housekeeping it every HOUSEKEEP_EVERY seconds and beating (ALIVE)
    every ALIVE_EVERY."""
    spool = os.path.join(ctx.game, 'Mods', 'spool')
    try:
        make_spool(ctx.game)
    except OSError:     # a symlink on the path; the loop below reports it until it is a plain directory
        traceback.print_exc()
    sys.stderr.write('modbridge: spool %s\n' % spool)
    due = 0.0
    last_beat = None
    while True:
        try:
            if not spool_ok(ctx.game):
                sys.stderr.write('modbridge: %s is not a plain directory; not answering\n' % spool)
                time.sleep(HOUSEKEEP_EVERY)
                continue
            if time.monotonic() >= due:
                housekeep(spool)
                due = time.monotonic() + HOUSEKEEP_EVERY
            if beat_due(last_beat):
                beat(spool)
                last_beat = time.monotonic()
            process_spool(ctx, spool, wait=False)
        except OSError:     # a spool that vanished or cannot be read this pass; the next pass tries again
            traceback.print_exc()
        time.sleep(poll)


def year_ranges(db):
    """{kind: (first, last)} of the seasons db holds; RANGES for a kind it has none of (a pre-2024 release has no
    Negro Leagues) or when it cannot be read."""
    out = dict(RANGES)
    try:
        con = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            for kind, (leagues, _, _) in KINDS.items():
                ids = leagues.split(',')
                first, last = con.execute('SELECT MIN(yearID), MAX(yearID) FROM teams WHERE lgID IN (%s)'
                                          % ','.join('?' * len(ids)), ids).fetchone()
                if first is None:
                    out.pop(kind, None)
                else:
                    out[kind] = (int(first), int(last))
        finally:
            con.close()
    except sqlite3.Error:
        traceback.print_exc()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='Answer the requests the in-game Mods menu writes to its spool.')
    ap.add_argument('--game', required=True, help='the game directory (holds Assn/ and Stats/)')
    ap.add_argument('--data', required=True, help='the news data directory (the ledger goes in created/)')
    ap.add_argument('--backup', required=True, help='where the files are copied before each write')
    ap.add_argument('--db', help='the Lahman database (build.py opens it read-only); without it and --templates, '
                    'Build a Season answers that it is not set up')
    ap.add_argument('--templates', help='the directory of minted structure templates')
    ap.add_argument('--donor', help='the stock PYR the new player is seeded from (default: <game>/Assn/MLBPA96E.PYR)')
    ap.add_argument('--poll', type=float, default=0.25, help='seconds between looks at the spool')
    args = ap.parse_args(argv)
    assn = os.path.join(args.game, 'Assn')
    if not os.path.isdir(assn):
        ap.error('no Assn directory in %s' % args.game)
    donor = args.donor or gamedata.find(assn, 'MLBPA96E.PYR') or os.path.join(assn, 'MLBPA96E.PYR')
    if not os.path.isfile(donor):
        ap.error('no donor file: %s' % donor)
    if not os.path.isdir(args.data):
        ap.error('not a directory: %s' % args.data)
    ctx = types.SimpleNamespace(game=args.game, data=args.data, backup=args.backup, donor=donor, db=args.db,
                                templates=args.templates, proc='/proc',
                                ranges=year_ranges(args.db) if args.db else dict(RANGES))
    try:
        serve(ctx, args.poll)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
