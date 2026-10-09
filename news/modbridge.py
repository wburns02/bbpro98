"""The in-game Mods menu's bridge: a long-running host process that answers the requests a mod DLL writes into
the game's Mods/spool directory. The game runs in a sandbox with no network, so the requests are answered here by the
repo's own Python: league news pages (server.route), Create a Player (create.validate and createweb.commit), and a
season built from the Lahman database (work/lahman/build.py, run as a subprocess). Standard library only.

The DLL writes q<ID>.tmp and renames it to q<ID>.req. The bridge claims the request by renaming it to q<ID>.work,
writes r<ID>.tmp and renames that to r<ID>.rsp, then removes the .work file. parse_request reads a request, render
writes a reply, and process_spool answers every pending request once.
"""
import argparse
import datetime
import os
import pathlib
import re
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


def _season(game, year):
    """(STEM, ASN path) of the season built for year (a file <n>L<year>.ASN in Assn/), or (None, None)."""
    assn = os.path.join(game, 'Assn')
    pat = re.compile(r'[0-9]{1,2}L%d\.ASN' % year, re.I)
    for f in sorted(os.listdir(assn)):
        if pat.fullmatch(f) and not os.path.islink(os.path.join(assn, f)):
            return os.path.splitext(f)[0].upper(), os.path.join(assn, f)
    return None, None


def _leftovers(game, year):
    """True when Assn/ or Stats/ holds anything named for a <n>L<year> season (any extension), or either directory
    is a symlink. build.py writes those names with the host's permissions, so it never runs over one."""
    pat = re.compile(r'[0-9]{1,2}L%d\.[A-Za-z]+' % year, re.I)
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


def _news(ctx, req):
    path = req.get('path', '')
    if len(path) > MAX_VALUE or not NEWS_RE.fullmatch(path):
        return [('status', 'error')], 'Bad request.'
    data = pathlib.Path(ctx.data)     # server.route joins paths with /
    status, _, body, extra = server.route(data, path)
    for _ in range(3):
        target = next((v for k, v in extra if k.lower() == 'location'), '')
        if status not in (301, 302, 303) or not target.startswith('/news/'):
            break
        path = target
        status, _, body, extra = server.route(data, path)
    title, text, links = html_to_text(body.decode('utf-8', 'replace'), path)
    header = [('status', 'ok' if status == 200 else 'error'), ('http', str(status)), ('path', _plain(path)),
              ('title', _plain(title)), ('count', str(len(links)))]
    header += [('link.%d' % i, '%s\t%s' % (_plain(label), _plain(target))) for i, (label, target) in enumerate(links)]
    return header, text


def _run_build(ctx, year):
    cmd = [sys.executable, BUILD_PY, '--year', str(year), '--install', ctx.game, '--db', ctx.db,
           '--templates', ctx.templates]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=BUILD_TIMEOUT, cwd=REPO)
    except subprocess.TimeoutExpired:
        return [('status', 'error')], _paragraphs('The build failed.', 'Timed out.')
    stem, asn = _season(ctx.game, year)
    if run.returncode == 0 and stem is not None:
        label = createweb._label(stem, asn)
        header = [('status', 'ok'), ('existed', '0'), ('stem', stem), ('label', _plain(label))]
        return header, _paragraphs('Built %s (%s). Pick it from the association list.' % (label, stem),
                                   _tail(run.stdout))
    return [('status', 'error')], _paragraphs('The build failed.', _tail(run.stdout, run.stderr))


def _build(ctx, req):
    year = req.get('year', '')
    if not (re.fullmatch(r'[0-9]{4}', year) and 1871 <= int(year) <= 2019):
        return [('status', 'error')], 'Pick a year from 1871 to 2019.'
    year = int(year)
    stem, asn = _season(ctx.game, year)
    if stem is None and _leftovers(ctx.game, year):
        return [('status', 'error')], ('Files for a %d season are already in the game without its association. '
                                       'Remove them, then build again.' % year)
    if stem is None:
        if not _BUILD.acquire(blocking=False):
            return [('status', 'busy')], BUSY_TEXT
        try:
            stem, asn = _season(ctx.game, year)     # a build may have finished since the look above
            if stem is None:
                return _run_build(ctx, year)
        finally:
            _BUILD.release()
    label = createweb._label(stem, asn)
    header = [('status', 'ok'), ('existed', '1'), ('stem', stem), ('label', _plain(label))]
    return header, '%s is already in the game (%s).' % (label, stem)


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


def _read(path):
    """Up to MAX_REQUEST + 1 bytes of a request; b'' (a bad request) unless it is a regular file. The game side can
    write the spool, so never follow a symlink and never block on a FIFO or device."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:             # ELOOP: a symlink
        return b''
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return b''
        chunks, left = [], MAX_REQUEST + 1
        while left > 0:
            chunk = os.read(fd, left)
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        return b''.join(chunks)
    finally:
        os.close(fd)


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _respond(spool, rid, header, body):
    tmp = os.path.join(spool, 'r%s.tmp' % rid)
    _remove(tmp)                # a name the game side planted (a symlink) goes, and O_EXCL never writes through one
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as fh:
        fh.write(render(header, body))
    os.replace(tmp, os.path.join(spool, 'r%s.rsp' % rid))


def _answer(ctx, spool, rid):
    """Claims request rid, answers it and removes its work file. A request another worker has claimed is skipped."""
    work = os.path.join(spool, 'q%s.work' % rid)
    try:
        os.rename(os.path.join(spool, 'q%s.req' % rid), work)
    except FileNotFoundError:
        return
    try:
        req = parse_request(_read(work))
        if req is None:
            header, body = [('status', 'error')], 'Bad request.'
        else:
            header, body = handle(ctx, req)
        _respond(spool, rid, header, body)
        op = req['op'] if req is not None and req['op'] in OPS else '-'
        sys.stderr.write('modbridge: %s %s %s\n' % (rid, op, dict(header)['status']))
    finally:
        _remove(work)


def _slot(ctx, spool, rid):
    try:
        _answer(ctx, spool, rid)
    finally:
        _SLOTS.release()


def process_spool(ctx, spool, wait=True):
    """Claims and answers every pending request in spool once, each in its own worker thread, at most MAX_WORKERS at a
    time; a request that finds every slot taken waits for the next call. With wait the workers are joined first."""
    threads = []
    for name in sorted(os.listdir(spool)):
        m = REQ_RE.fullmatch(name)
        if m is None:
            continue
        if not _SLOTS.acquire(blocking=False):
            break
        t = threading.Thread(target=_slot, args=(ctx, spool, m.group(1)), daemon=True)
        try:
            t.start()
        except BaseException:
            _SLOTS.release()
            raise
        threads.append(t)
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
    """Removes replies (r*.rsp) and temporary files (*.tmp) older than STALE seconds by mtime. Work files are kept."""
    now = time.time() if now is None else now
    for name in os.listdir(spool):
        if not (name.endswith('.tmp') or (name.startswith('r') and name.endswith('.rsp'))):
            continue
        path = os.path.join(spool, name)
        try:
            if now - os.path.getmtime(path) > STALE:
                os.remove(path)
        except FileNotFoundError:
            pass


def serve(ctx, poll):
    """Answers the game's spool until interrupted, housekeeping it every HOUSEKEEP_EVERY seconds."""
    spool = os.path.join(ctx.game, 'Mods', 'spool')
    os.makedirs(spool, exist_ok=True)
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
                                templates=args.templates, proc='/proc')
    try:
        serve(ctx, args.poll)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
