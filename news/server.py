"""Read-only web pages for the news sidecar: the league news, game stories and season previews and awards the watcher
writes into a data directory, served under /news. The Cloudflare tunnel forwards the prefix unchanged, behind a login
this server never sees.
Standard library only. The server reads the data directory and never writes to it.
"""
import argparse
import html
import http.client
import json
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PER_PAGE = 30
TOP = 3
SEP = ' · '
# fullmatch, never $: a '$' also matches before a trailing newline, so '30L1998%0A' would get through.
ASSN_RE = re.compile(r'[A-Za-z0-9_]{1,8}')
KEY_RE = re.compile(r'[0-9a-f]{16}')
FEED_RE = re.compile(r'([0-9]{2})-([0-9]{2})\.json')
PAGE_RE = re.compile(r'[0-9]{1,5}')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December')
LEADERS = (('avg', 'AVG'), ('hr', 'HR'), ('rbi', 'RBI'), ('w', 'W'), ('era', 'ERA'), ('so', 'SO'), ('sv', 'SV'))
BYLINES = {'glm': 'Staff writer', 'template': 'Wire report'}
HTML_TYPE = 'text/html; charset=utf-8'
JSON_TYPE = 'application/json'
HEADERS = (
    ('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
                                "frame-ancestors 'self'"),
    ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'no-referrer'),
    ('Cache-Control', 'no-cache'),
)
CSS = """
:root {
  --paper: #f6f1e3; --ink: #1d1b16; --muted: #6b6559; --rule: #1d1b16; --faint: #cdc3a9; --accent: #9b2b22;
  --serif: Georgia, 'Times New Roman', serif;
  --sans: 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #171613; --ink: #ece6d6; --muted: #a39c89; --rule: #ece6d6; --faint: #3d3a31; --accent: #e8786d;
  }
}
* { box-sizing: border-box; }
html { background: var(--paper); color: var(--ink); }
body { margin: 0; font: 17px/1.5 var(--serif); overflow-wrap: break-word; }
a { color: inherit; text-decoration-thickness: 1px; text-underline-offset: 3px; }
a:hover { color: var(--accent); }
.page { max-width: 1100px; margin: 0 auto; padding: 16px; }
.masthead { text-align: center; border-bottom: 3px double var(--rule); margin-bottom: 20px; padding-bottom: 10px; }
.masthead h1 { font-size: clamp(2rem, 6vw, 3.25rem); line-height: 1.05; margin: 2px 0 4px; }
.kicker { margin: 0; font: .8rem var(--sans); letter-spacing: .14em; text-transform: uppercase; color: var(--accent); }
.through, .meta, .dateline, .byline, .nav { margin: 0; font: .95rem var(--sans); color: var(--muted); }
h1, h2 { font-weight: 700; line-height: 1.2; text-wrap: balance; }
h2 { font-size: 1.35rem; margin: 0 0 4px; }
.grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 24px; }
@media (max-width: 759px) { .grid { grid-template-columns: minmax(0, 1fr); } }
.feed, .story, .assn { border-top: 1px solid var(--faint); padding: 12px 0; }
.feed p, .story p, .assn p { margin: 6px 0 0; }
.index { list-style: none; margin: 0; padding: 0; }
.side section { border-top: 3px double var(--rule); padding-top: 8px; margin-bottom: 20px; }
.side h2 { font: 700 .95rem var(--sans); letter-spacing: .08em; text-transform: uppercase; }
.pager { display: flex; justify-content: space-between; font: .95rem var(--sans); border-top: 1px solid var(--faint);
         padding-top: 10px; }
.empty { font-style: italic; color: var(--muted); }
.table-wrap { overflow-x: auto; margin: 4px 0 14px; }
table { width: 100%; border-collapse: collapse; font: .95rem var(--sans); font-variant-numeric: tabular-nums; }
caption { caption-side: top; text-align: left; font-weight: 700; padding: 2px 0 4px; }
th, td { padding: 3px 8px 3px 0; text-align: right; white-space: nowrap; border-bottom: 1px solid var(--faint); }
th { font-weight: 700; }
th.t, td.t { text-align: left; }
.story-page { max-width: 760px; }
.story-page h1 { font-size: clamp(1.7rem, 4vw, 2.4rem); line-height: 1.1; margin: 8px 0; }
.story-page h2 { margin-top: 18px; }
.decision { font: 1rem var(--sans); margin: 4px 0; }
.label { display: inline-block; width: 1.4em; font-weight: 700; color: var(--accent); }
"""


def esc(value):
    """Display text of a JSON value, HTML-escaped. Every value from a data file goes through here."""
    return html.escape(_text(value), quote=True)


def _text(value):
    """A JSON scalar as text. Anything else (null, a list, an object) is ''."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ''
    return str(value)


def _d(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _int(obj, key, default=0):
    value = obj.get(key)
    return value if type(value) is int else default


def _read_obj(path):
    """The JSON object in path, or None when it is missing, unreadable, corrupt or some other JSON value."""
    try:
        with open(path, encoding='utf-8') as fh:
            value = json.load(fh)
    except (OSError, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _assn_names(data_dir):
    try:
        names = os.listdir(data_dir)
    except OSError:
        return []
    return sorted(n for n in names if ASSN_RE.fullmatch(n) and (data_dir / n).is_dir())


def _stories(assn_dir):
    """(key, recap) for every readable game story, newest first: by (month, day, slot) descending, then key."""
    try:
        names = os.listdir(assn_dir / 'recaps')
    except OSError:
        return []
    out = []
    for name in names:
        key = name[:-len('.json')] if name.endswith('.json') else ''
        rec = _read_obj(assn_dir / 'recaps' / name) if KEY_RE.fullmatch(key) else None
        if rec is not None:
            out.append((key, rec))
    out.sort(key=lambda kr: (-_int(kr[1], 'month'), -_int(kr[1], 'day'), -_int(kr[1], 'slot'), kr[0]))
    return out


def _latest_feed(assn_dir):
    """The newest readable 'Around the league' column, or None. Newest is by the MM-DD in the file name."""
    feed_dir = assn_dir / 'feed'
    try:
        names = os.listdir(feed_dir)
    except OSError:
        return None
    dated = []
    for name in names:
        m = FEED_RE.fullmatch(name)
        if m and 1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31:
            dated.append((int(m[1]), int(m[2]), name))
    for _, _, name in sorted(dated, reverse=True):
        feed = _read_obj(feed_dir / name)
        if feed is not None:
            return feed
    return None


def _date_text(month, day):
    """'April 15', or '' when month and day are not a date."""
    if type(month) is int and type(day) is int and 1 <= month <= 12 and 1 <= day <= 31:
        return '%s %d' % (MONTHS[month - 1], day)
    return ''


def _through(meta):
    """'through April 15', or 'no games yet'."""
    last = meta.get('last_day')
    text = _date_text(*last) if isinstance(last, list) and len(last) == 2 else ''
    return 'through ' + text if text else 'no games yet'


def _when(rec):
    return _text(_d(rec.get('facts')).get('date')) or _date_text(_int(rec, 'month'), _int(rec, 'day'))


def _score(facts):
    """'SEA 5, OAK 3' with the winner first; '' when the facts carry no teams."""
    away, home = _d(facts.get('away')), _d(facts.get('home'))
    if not away or not home:
        return ''
    sides = [' '.join(x for x in (_text(d.get('abbrev')), _text(d.get('runs'))) if x) for d in (away, home)]
    if facts.get('winner') == 'home':
        sides.reverse()
    return ', '.join(sides)


def _paragraphs(body):
    """Body text as its non-empty lines."""
    return [line.strip() for line in _text(body).split('\n') if line.strip()]


def _paras_html(paras):
    return ''.join('<p>%s</p>' % esc(p) for p in paras)


def _table(caption, heads, rows, text=1):
    """A table in an overflow wrapper. The first `text` columns are names, left-aligned; the rest are numbers."""
    def cells(values, tag):
        return ''.join('<%s%s>%s</%s>' % (tag, ' class="t"' if i < text else '', esc(v), tag)
                       for i, v in enumerate(values))
    body = ''.join('<tr>%s</tr>' % cells(r, 'td') for r in rows)
    return ('<div class="table-wrap"><table><caption>%s</caption><thead><tr>%s</tr></thead><tbody>%s</tbody>'
            '</table></div>' % (esc(caption), cells(heads, 'th'), body))


def _page(title, body):
    """One document: the shared head and style, then body. title is text; body is markup."""
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<div class="page">\n%s\n</div>\n</body>\n</html>\n'
            % (esc(title), CSS, body)).encode('utf-8')


def _page_reply(status, title, body, extra=()):
    return status, HTML_TYPE, _page(title, body), extra


def _masthead(name, through=''):
    return ('<header class="masthead"><p class="kicker">BASEBALL PRO \'98 &middot; LEAGUE NEWS</p>'
            '<h1>%s</h1>%s</header>' % (esc(name), '<p class="through">%s</p>' % esc(through) if through else ''))


def _nav():
    return '<p class="nav"><a href="/news/">All leagues</a> &middot; <a href="/">Back to the game</a></p>'


def _notice(status, title, message, extra=()):
    return _page_reply(status, title, _masthead(title) + '<p>%s</p>' % message + _nav(), extra)


def _not_found():
    return _notice(404, 'Not found', 'No such page in the league news.')


def _moved(target):
    body = _masthead('Moved') + '<p>Moved to <a href="%s">%s</a>.</p>' % (esc(target), esc(target))
    return _page_reply(301, 'Moved', body, (('Location', target),))


def _standings_html(groups):
    tables = []
    for g in _dicts(groups):
        league, division = _text(g.get('league')).strip(), _text(g.get('division')).strip()
        caption = ' '.join(x for x in (league, division) if x) or 'Standings'
        rows = [[t.get('name'), t.get('w'), t.get('l'), t.get('pct'), t.get('gb')] for t in _dicts(g.get('teams'))]
        tables.append(_table(caption, ('Team', 'W', 'L', 'Pct', 'GB'), rows))
    return '<section>%s</section>' % (''.join(tables) or '<p class="empty">No standings yet.</p>')


def _leaders_html(leaders):
    leaders = _d(leaders)
    tables = []
    for key, label in LEADERS:
        rows = [[r.get('name'), r.get('value')] for r in _dicts(leaders.get(key))[:TOP]]
        if rows:
            tables.append(_table(label, ('Player', 'Value'), rows))
    return '<section><h2>Leaders</h2>%s</section>' % (''.join(tables) or '<p class="empty">No leaders yet.</p>')


def _feed_html(feed):
    kicker = SEP.join(x for x in ('Around the league', _text(feed.get('date'))) if x)
    return ('<article class="feed"><p class="kicker">%s</p><h2>%s</h2>%s</article>'
            % (esc(kicker), esc(feed.get('headline')), _paras_html(_paragraphs(feed.get('body')))))


def _story_row(assn, key, rec):
    meta = SEP.join(x for x in (_when(rec), _score(_d(rec.get('facts')))) if x)
    return ('<article class="story"><h2><a href="/news/%s/%s">%s</a></h2><p class="meta">%s</p>%s</article>'
            % (esc(assn), esc(key), esc(rec.get('headline')) or '(untitled)', esc(meta),
               _paras_html(_paragraphs(rec.get('body'))[:1])))


def _page_href(assn, page):
    return '/news/%s/' % assn if page == 1 else '/news/%s/?page=%d' % (assn, page)


def _pager(assn, page, total):
    links = []
    if page > 1:
        links.append('<a href="%s">&larr; Newer stories</a>' % esc(_page_href(assn, page - 1)))
    if page * PER_PAGE < total:
        links.append('<a href="%s">Older stories &rarr;</a>' % esc(_page_href(assn, page + 1)))
    return '<nav class="pager">%s</nav>' % ''.join(links) if links else ''


def _page_no(qs):
    raw = parse_qs(qs).get('page', [''])[0]
    n = int(raw) if PAGE_RE.fullmatch(raw) else 0
    return n if 1 <= n <= 10000 else 1


def _index(data_dir):
    found = []
    for assn in _assn_names(data_dir):
        meta = _read_obj(data_dir / assn / 'meta.json')
        if meta is not None:
            found.append((_text(meta.get('updated')), assn, meta))
    found.sort(key=lambda row: (row[0], row[1]), reverse=True)
    items = []
    for _, assn, meta in found:
        latest = _text(_d(_latest_feed(data_dir / assn)).get('headline'))
        items.append('<li class="assn"><h2><a href="/news/%s/">%s</a></h2><p class="meta">%s</p>%s</li>'
                     % (esc(assn), esc(meta.get('name')) or esc(assn), esc(_through(meta)),
                        '<p>%s</p>' % esc(latest) if latest else ''))
    body = (_masthead('League News')
            + ('<ul class="index">%s</ul>' % ''.join(items) if items else '<p class="empty">No league news yet.</p>')
            + '<p class="nav"><a href="/">Back to the game</a></p>')
    return _page_reply(200, 'League News', body)


def _association(data_dir, assn, qs):
    meta = _read_obj(data_dir / assn / 'meta.json')
    if meta is None:
        return _not_found()
    page = _page_no(qs)
    name = _text(meta.get('name')) or assn
    stories = _stories(data_dir / assn)
    lead = []
    if page == 1:
        feed = _latest_feed(data_dir / assn)
        if feed:
            lead.append(_feed_html(feed))
    shown = stories[(page - 1) * PER_PAGE:page * PER_PAGE]
    if not stories:
        lead.append('<p class="empty">No game stories yet.</p>')
    elif not shown:
        lead.append('<p class="empty">No stories on this page.</p>')
    lead.extend(_story_row(assn, key, rec) for key, rec in shown)
    lead.append(_pager(assn, page, len(stories)))
    season = _season_links(data_dir, assn) if page == 1 else ''
    side = season + _standings_html(meta.get('standings')) + _leaders_html(meta.get('leaders'))
    body = (_masthead(name, _through(meta)) + _nav()
            + '<div class="grid"><section class="lead">%s</section><aside class="side">%s</aside></div>'
            % (''.join(lead), side))
    return _page_reply(200, '%s · League News' % name, body)


def _decision(label, p):
    """One W, L or S line; '' when the game had no such pitcher."""
    if not p:
        return ''
    stats = tuple(esc(p.get(k)) for k in ('ip', 'h', 'r', 'er', 'bb', 'so'))
    return ('<p class="decision"><span class="label">%s</span> %s (%s): %s IP, %s H, %s R, %s ER, %s BB, %s SO</p>'
            % ((label, esc(p.get('name')), esc(p.get('team'))) + stats))


def _byline_html(rec):
    source = rec.get('source')
    byline = BYLINES.get(source) if isinstance(source, str) else None
    return '<p class="byline">%s</p>' % esc(byline) if byline else ''


def _league_nav(assn, facts):
    league = _text(facts.get('association')) or assn
    return ('<p class="nav"><a href="/news/%s/">&larr; %s</a> &middot; <a href="/news/">All leagues</a></p>'
            % (esc(assn), esc(league)))


def _story_page(assn, key, rec):
    facts = _d(rec.get('facts'))
    headline = _text(rec.get('headline'))
    stadium = _text(_d(facts.get('home')).get('stadium'))
    away, home = _d(facts.get('away')), _d(facts.get('home'))
    box = _table('Box score', ('Team', 'R', 'H'), [[s.get('name'), s.get('runs'), s.get('hits')] for s in (away, home)])
    bats = [[b.get('team'), b.get('name'), b.get('ab'), b.get('h'), b.get('hr'), b.get('rbi'), b.get('bb'), b.get('r')]
            for b in _dicts(facts.get('batters'))]
    decisions = _d(facts.get('decisions'))
    lines = ''.join(_decision(label, _d(decisions.get(role)))
                    for label, role in (('W', 'win'), ('L', 'loss'), ('S', 'save')))
    parts = [
        _league_nav(assn, facts),
        '<article class="story-page"><h1>%s</h1>' % esc(headline),
        '<p class="dateline">%s</p>' % esc(SEP.join(x for x in (_when(rec), stadium) if x)),
        _byline_html(rec),
        _paras_html(_paragraphs(rec.get('body'))),
        box,
        _table('Notable batters', ('Team', 'Batter', 'AB', 'H', 'HR', 'RBI', 'BB', 'R'), bats, text=2) if bats else '',
        '<section><h2>Decisions</h2>%s</section>' % lines if lines else '',
        '</article>',
    ]
    return _page_reply(200, headline or 'Game story', ''.join(parts))


def _story(data_dir, assn, key):
    rec = _read_obj(data_dir / assn / 'recaps' / (key + '.json'))
    return _story_page(assn, key, rec) if rec is not None else _not_found()


def _season_file(data_dir, assn, which):
    """The season preview or awards (which: 'preview' or 'awards') as an object of that kind, else None."""
    rec = _read_obj(data_dir / assn / (which + '.json'))
    return rec if rec is not None and rec.get('kind') == which else None


def _season_page(assn, rec, label, below):
    """A season page in the game story layout: the body, then the markup in below."""
    headline = _text(rec.get('headline'))
    parts = [
        _league_nav(assn, _d(rec.get('facts'))),
        '<article class="story-page"><h1>%s</h1>' % esc(headline),
        '<p class="dateline">%s</p>' % esc(label),
        _byline_html(rec),
        _paras_html(_paragraphs(rec.get('body'))),
        ''.join(below),
        '</article>',
    ]
    return _page_reply(200, headline or label, ''.join(parts))


def _hitter_text(hitter):
    if not isinstance(hitter, dict):
        return ''
    return '%s, %s HR, %s RBI' % (_text(hitter.get('name')), _text(hitter.get('hr')), _text(hitter.get('rbi')))


def _pitcher_text(pitcher):
    if not isinstance(pitcher, dict):
        return ''
    return '%s, %s-%s, %s ERA' % (_text(pitcher.get('name')), _text(pitcher.get('w')), _text(pitcher.get('l')),
                                  _text(pitcher.get('era')))


def _preview_page(assn, rec):
    tables = []
    for div in _dicts(_d(rec.get('facts')).get('divisions')):
        league, division = _text(div.get('league')).strip(), _text(div.get('division')).strip()
        caption = ' '.join(x for x in (league, division) if x) or 'Teams'
        rows = [[t.get('name'), t.get('manager'), _hitter_text(t.get('hitter')), _pitcher_text(t.get('pitcher'))]
                for t in _dicts(div.get('teams'))]
        tables.append(_table(caption, ('Team', 'Manager', 'Top hitter', 'Top pitcher'), rows, text=4))
    return _season_page(assn, rec, 'Season preview', tables)


def _awards_page(assn, rec):
    sections = []
    for lg in _dicts(_d(rec.get('facts')).get('leagues')):
        tables = []
        mvp = [[m.get('name'), m.get('team'), m.get('avg'), m.get('hr'), m.get('rbi'), m.get('r'), m.get('sb'),
                m.get('runs_created')] for m in _dicts(lg.get('mvp'))]
        cy = [[p.get('name'), p.get('team'), p.get('w'), p.get('l'), p.get('era'), p.get('ip'), p.get('so'),
               p.get('sv')] for p in _dicts(lg.get('cy_young'))]
        champs = [[c.get('division'), c.get('team'), c.get('record')] for c in _dicts(lg.get('champions'))]
        if mvp:
            tables.append(_table('MVP', ('Player', 'Team', 'AVG', 'HR', 'RBI', 'R', 'SB', 'RC'), mvp, text=2))
        if cy:
            tables.append(_table('Cy Young', ('Pitcher', 'Team', 'W', 'L', 'ERA', 'IP', 'SO', 'SV'), cy, text=2))
        if champs:
            tables.append(_table('Division champions', ('Division', 'Team', 'Record'), champs, text=2))
        league = _text(lg.get('league')).strip() or 'The league'
        sections.append('<section><h2>%s</h2>%s</section>' % (esc(league), ''.join(tables)))
    return _season_page(assn, rec, 'Season awards', sections)


def _season(data_dir, assn, which):
    """The season preview or awards page; 404 when its file is missing, unreadable or of another kind."""
    rec = _season_file(data_dir, assn, which)
    if rec is None:
        return _not_found()
    return _preview_page(assn, rec) if which == 'preview' else _awards_page(assn, rec)


def _season_links(data_dir, assn):
    """The Season box for the side column: awards above preview, each only when its file exists. '' for neither."""
    links = ['<li><a href="/news/%s/%s">%s</a></li>' % (esc(assn), which, label)
             for which, label in (('awards', 'Season awards'), ('preview', 'Season preview'))
             if _season_file(data_dir, assn, which) is not None]
    if not links:
        return ''
    return '<section class="season"><h2>Season</h2><ul>%s</ul></section>' % ''.join(links)


def _status(data_dir):
    budget = _read_obj(data_dir / 'budget.json') or {}
    limits = _read_obj(data_dir / 'limits.json') or {}
    date = budget.get('date')
    status = {
        'date': date if isinstance(date, str) else None,
        'calls': _int(budget, 'calls'),
        'out_tokens': _int(budget, 'out_tokens'),
        'in_tokens': _int(budget, 'in_tokens'),
        'calls_per_day': _int(limits, 'calls_per_day', None),
        'tokens_per_day': _int(limits, 'tokens_per_day', None),
    }
    return 200, JSON_TYPE, json.dumps(status).encode('utf-8'), ()


def _segments(path):
    """Decoded segments of a request path ('/news/x/' -> ['news', 'x', '']), or None for a path to refuse: a
    backslash, an empty middle segment, or a '.' or '..' segment, raw or decoded. Splitting comes before decoding,
    so an encoded slash stays inside its segment and fails the name check.
    """
    if not path.startswith('/') or '\\' in path:
        return None
    raw = path[1:].split('/')
    if '' in raw[:-1]:
        return None
    segs = [unquote(s) for s in raw]
    if any(s in ('.', '..') or '..' in s or '/' in s or '\\' in s for s in raw + segs):
        return None
    return segs


def route(data_dir, target):
    """(status, content type, body, extra headers) for a GET or HEAD request target."""
    try:
        parts = urlsplit(target)
    except ValueError:
        return _not_found()
    segs = _segments(parts.path)
    if not segs or segs[0] != 'news':
        return _not_found()
    rest, qs = segs[1:], parts.query
    suffix = '?' + qs if qs else ''
    if not rest:
        return _moved('/news/' + suffix)
    if rest == ['']:
        return _index(data_dir)
    if rest == ['status.json']:
        return _status(data_dir)
    assn = rest[0]
    if not ASSN_RE.fullmatch(assn):
        return _not_found()
    if len(rest) == 1:
        return _moved('/news/%s/%s' % (assn, suffix))
    if len(rest) == 2 and rest[1] == '':
        return _association(data_dir, assn, qs)
    if len(rest) == 2 and KEY_RE.fullmatch(rest[1]):
        return _story(data_dir, assn, rest[1])
    if len(rest) == 2 and rest[1] in ('preview', 'awards'):
        return _season(data_dir, assn, rest[1])
    return _not_found()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._reply(head=False)

    def do_HEAD(self):
        self._reply(head=True)

    def __getattr__(self, name):
        """Any other method, whatever its name, gets a 405: the base class looks methods up as do_<METHOD>."""
        if name.startswith('do_'):
            return self._refuse
        raise AttributeError(name)

    def _refuse(self):
        self._send(*_notice(405, 'Method not allowed', 'Only GET and HEAD are served here.',
                            (('Allow', 'GET, HEAD'),)), head=False)

    def _reply(self, head):
        try:
            reply = route(self.server.data_dir, self.path)
        except Exception:  # one bad page should cost one 500, not the connection
            traceback.print_exc()
            reply = _notice(500, 'Server error', 'Something went wrong. Try again later.')
        self._send(*reply, head=head)

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
        """Errors the base class raises itself (a malformed request line, say) get the same page and headers."""
        self._send(*_notice(code, http.client.responses.get(code, 'Error'), 'The request could not be served.'),
                   head=self.command == 'HEAD')

    def log_message(self, format, *args):
        sys.stderr.write('%s %s\n' % (self.address_string(), format % args))


def make_server(data_dir, host='127.0.0.1', port=0):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.data_dir = Path(data_dir)
    return srv


def serve(data_dir, host='127.0.0.1', port=6153):
    """Serve until interrupted."""
    srv = make_server(data_dir, host, port)
    sys.stderr.write('news: serving %s on http://%s:%d/news/\n' % (data_dir, host, srv.server_address[1]))
    try:
        srv.serve_forever()
    finally:
        srv.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description='Serve the league news pages, read-only.')
    ap.add_argument('--data', default=os.environ.get('BBNEWS_DATA'),
                    help="the watcher's data directory (default: $BBNEWS_DATA)")
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=6153)
    args = ap.parse_args(argv)
    if not args.data:
        ap.error('no data directory: pass --data or set BBNEWS_DATA')
    if not os.path.isdir(args.data):
        ap.error('not a directory: %s' % args.data)
    serve(args.data, args.host, args.port)


if __name__ == '__main__':
    main()
