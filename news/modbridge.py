"""The in-game Mods menu's bridge: a long-running host process that answers the requests a mod DLL writes into
the game's Mods/spool directory. The game runs in a sandbox with no network, so the requests are answered here by the
repo's own Python: league news pages (server.route), the player development pages under /news/development/ and the
Mods/focus.txt they set (focus.py), which aging.dll reads at each offseason, Create a Player (create.validate and
createweb.commit), and a season built from the Lahman database (work/lahman/build.py, run as a subprocess). Standard
library only.

The DLL writes q<ID>.tmp and renames it to q<ID>.req. The bridge claims the request by renaming it to q<ID>.work,
writes r<ID>.tmp and renames that to r<ID>.rsp, then removes the .work file. parse_request reads a request, render
writes a reply, and process_spool answers every pending request once.
"""
import argparse
import datetime
import os
import pathlib
import re
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
from html.parser import HTMLParser

import create
import createweb
import focus
import gamedata
import server
import watch

VERSION = 1
MAX_REQUEST = 8192          # bytes
MAX_LINES = 100
MAX_VALUE = 256             # characters
MAX_WORKERS = 4             # requests answered at once
HOUSEKEEP_EVERY = 60        # seconds
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
    """The path and query an href leads to, resolved against the page's path: no scheme, host or fragment."""
    return urllib.parse.urlsplit(urllib.parse.urljoin(base, href))._replace(scheme='', netloc='', fragment='').geturl()


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
    return [('status', 'ok'), ('version', str(VERSION))], ''


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
        return header, _paragraphs('Built %s (%s). Pick it from the association list.' % (label, stem),
                                   _tail(run.stdout))
    return [('status', 'error')], _paragraphs('The build failed.', _tail(run.stdout, run.stderr))


def _build(ctx, req):
    year, kind = req.get('year', ''), req.get('league', 'mlb')
    if kind not in KINDS:
        return [('status', 'error')], 'Bad request.'
    _, letter, title = KINDS[kind]
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
    return header, '%s is already in the game (%s).' % (label, stem)


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
                                 births=focus.births(pyr) if pyr else {})


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


def _respond(dfd, rid, header, body):
    tmp = 'r%s.tmp' % rid
    _remove(dfd, tmp)           # a name the game side planted (a symlink) goes, and O_EXCL never writes through one
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
    with os.fdopen(fd, 'wb') as fh:
        fh.write(render(header, body))
    os.replace(tmp, 'r%s.rsp' % rid, src_dir_fd=dfd, dst_dir_fd=dfd)


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
            header, body = [('status', 'error')], 'Bad request.'
        else:
            header, body = handle(ctx, req)
        _respond(dfd, rid, header, body)
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


def housekeep(spool, now=None):
    """Removes replies (r*.rsp) and temporary files (*.tmp) older than STALE seconds by mtime. Work files are kept.
    Works through open_dir, so it never removes anything outside the spool."""
    now = time.time() if now is None else now
    dfd = open_dir(spool)
    try:
        for name in os.listdir(dfd):
            if not (name.endswith('.tmp') or (name.startswith('r') and name.endswith('.rsp'))):
                continue
            try:
                if now - os.stat(name, dir_fd=dfd, follow_symlinks=False).st_mtime > STALE:
                    os.remove(name, dir_fd=dfd)
            except FileNotFoundError:
                pass
    finally:
        os.close(dfd)


def serve(ctx, poll):
    """Answers the game's spool until interrupted, housekeeping it every HOUSEKEEP_EVERY seconds."""
    spool = os.path.join(ctx.game, 'Mods', 'spool')
    try:
        make_spool(ctx.game)
    except OSError:     # a symlink on the path; the loop below reports it until it is a plain directory
        traceback.print_exc()
    sys.stderr.write('modbridge: spool %s\n' % spool)
    due = 0.0
    while True:
        try:
            if not spool_ok(ctx.game):
                sys.stderr.write('modbridge: %s is not a plain directory; not answering\n' % spool)
                time.sleep(HOUSEKEEP_EVERY)
                continue
            if time.monotonic() >= due:
                housekeep(spool)
                due = time.monotonic() + HOUSEKEEP_EVERY
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
    ap.add_argument('--db', required=True, help='the Lahman database (build.py opens it read-only)')
    ap.add_argument('--templates', required=True, help='the directory of minted structure templates')
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
                                templates=args.templates, proc='/proc', ranges=year_ranges(args.db))
    try:
        serve(ctx, args.poll)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
