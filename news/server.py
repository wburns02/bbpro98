"""Read-only web pages for the news sidecar: the league news, game stories and season previews and awards the watcher
writes into a data directory, served under /news. The Cloudflare tunnel forwards the prefix unchanged, behind a login
this server never sees.
Standard library only. The server reads the data directory and never writes to it.
"""
import argparse
import html
import http.client
import json
import math
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import contracts

PER_PAGE = 30
TOP = 3
SEP = ' · '
# fullmatch, never $: a '$' also matches before a trailing newline, so '30L1998%0A' would get through.
ASSN_RE = re.compile(r'[A-Za-z0-9_]{1,8}')
KEY_RE = re.compile(r'[0-9a-f]{16}')
PAST_RE = re.compile(r'[0-9]{4}(?:-[0-9]{1,2})?')
YEAR_FILE_RE = re.compile(r'([0-9]{4})\.json')
YEAR_RE = re.compile(r'[0-9]{4}')
FEED_RE = re.compile(r'([0-9]{2})-([0-9]{2})\.json')
DAY_RE = re.compile(r'([0-9]{2})-([0-9]{2})')
PAGE_RE = re.compile(r'[0-9]{1,5}')
TID_RE = re.compile(r'[0-9]{1,2}')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December')
LEADERS = (('avg', 'AVG'), ('hr', 'HR'), ('rbi', 'RBI'), ('w', 'W'), ('era', 'ERA'), ('so', 'SO'), ('sv', 'SV'))
MOVES_BOX = 5       # newest transaction lines in the association's side column
NOTE_RE = re.compile(r'[0-9]{1,6}')
SIGNINGS = 20       # newest contract events on the payroll page
CONTRACT_STATUS = {'pre': 'Pre-arb', 'arb': 'Arbitration', 'fa': 'Free agent contract'}
STAT_WORDS = {'hr': 'home run', 'h': 'hit', 'sb': 'stolen base', 'w': 'win', 'sv': 'save', 'so_p': 'strikeout'}
REPLAY_STATS = ('HR', 'AVG', 'RBI', 'SB', 'W', 'SV', 'SO', 'ERA')
RECORD_STATS = (('hr', 'Home runs'), ('h', 'Hits'), ('rbi', 'RBI'), ('r', 'Runs'), ('sb', 'Stolen bases'),
                ('bb', 'Walks'), ('avg', 'Batting average'), ('w', 'Wins'), ('so', 'Strikeouts'), ('sv', 'Saves'),
                ('era', 'ERA'))
RECORD_ROWS = 10    # rows a record table shows
RECORD_SOURCES = {'lahman': 'real', 'sim': 'this league'}
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
.through, .meta, .dateline, .byline, .nav, .coverage { margin: 0; font: .95rem var(--sans); color: var(--muted); }
h1, h2 { font-weight: 700; line-height: 1.2; text-wrap: balance; }
h2 { font-size: 1.35rem; margin: 0 0 4px; }
.grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 24px; }
@media (max-width: 759px) { .grid { grid-template-columns: minmax(0, 1fr); } }
.feed, .story, .assn { border-top: 1px solid var(--faint); padding: 12px 0; }
.feed p, .story p, .assn p { margin: 6px 0 0; }
.index { list-style: none; margin: 0; padding: 0; }
.moves { list-style: none; margin: 4px 0 12px; padding: 0; }
.moves li { padding: 3px 0; border-bottom: 1px solid var(--faint); }
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


class _Markup(str):
    """HTML a page builder wrote itself: a table cell takes it as it is, where any other value is escaped."""


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


def _scout_files(folder):
    """[(tid, report)] for every readable scouting report in a season folder, by team name then tid."""
    scout_dir = folder / 'scout'
    try:
        names = os.listdir(scout_dir)
    except OSError:
        return []
    out = []
    for name in names:
        tid = name[:-len('.json')] if name.endswith('.json') else ''
        rec = _read_obj(scout_dir / name) if TID_RE.fullmatch(tid) else None
        if rec is not None and rec.get('kind') == 'scout':
            out.append((int(tid), rec))
    return sorted(out, key=lambda tr: (_text(tr[1].get('team')), tr[0]))


def _feed_days(folder):
    """Sorted (month, day) of every feed/<MM>-<DD>.json in a season folder, readable or not. [] when there is no feed
    folder."""
    try:
        names = os.listdir(folder / 'feed')
    except OSError:
        return []
    days = []
    for name in names:
        m = FEED_RE.fullmatch(name)
        if m and 1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31:
            days.append((int(m[1]), int(m[2])))
    return sorted(days)


def _feed_file(folder, month, day):
    return _read_obj(folder / 'feed' / ('%02d-%02d.json' % (month, day)))


def _latest_feed(assn_dir):
    """The newest readable 'Around the league' column, or None. Newest is by the MM-DD in the file name."""
    for month, day in reversed(_feed_days(assn_dir)):
        feed = _feed_file(assn_dir, month, day)
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
    """A table in an overflow wrapper. The first `text` columns are names, left-aligned; the rest are numbers. text
    may also be a tuple of the indexes of the name columns."""
    left = range(text) if isinstance(text, int) else text

    def cells(values, tag):
        return ''.join('<%s%s>%s</%s>' % (tag, ' class="t"' if i in left else '',
                                          v if isinstance(v, _Markup) else esc(v), tag)
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


def _nav(back=''):
    """The league nav line; back is markup for a link that leads it."""
    return '<p class="nav">%s<a href="/news/">All leagues</a> &middot; <a href="/">Back to the game</a></p>' % back


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


def _feed_html(feed, href=None):
    """The column. With href, the date in the kicker links there."""
    date = esc(feed.get('date'))
    if date and href:
        date = '<a href="%s">%s</a>' % (esc(href), date)
    kicker = SEP.join(x for x in ('Around the league', date) if x)
    return ('<article class="feed"><p class="kicker">%s</p><h2>%s</h2>%s</article>'
            % (kicker, esc(feed.get('headline')), _paras_html(_paragraphs(feed.get('body')))))


def _story_row(home, key, rec):
    meta = SEP.join(x for x in (_when(rec), _score(_d(rec.get('facts')))) if x)
    return ('<article class="story"><h2><a href="%s%s">%s</a></h2><p class="meta">%s</p>%s</article>'
            % (esc(home), esc(key), esc(rec.get('headline')) or '(untitled)', esc(meta),
               _paras_html(_paragraphs(rec.get('body'))[:1])))


def _page_href(path, page):
    return path if page == 1 else '%s?page=%d' % (path, page)


def _pager(path, page, total, newer='Newer stories', older='Older stories'):
    links = []
    if page > 1:
        links.append('<a href="%s">&larr; %s</a>' % (esc(_page_href(path, page - 1)), newer))
    if page * PER_PAGE < total:
        links.append('<a href="%s">%s &rarr;</a>' % (esc(_page_href(path, page + 1)), older))
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


def _comma(value):
    return '{:,}'.format(value)


def _league_html(league):
    """The League box (the age make-up) for the side column; '' unless league is a dict with a positive int 'rostered'
    and a finite number 'mean_age'. Only those checked numbers reach the page; a count that is not an int shows as 0."""
    if not isinstance(league, dict):
        return ''
    rostered, age = league.get('rostered'), league.get('mean_age')
    if type(rostered) is not int or rostered <= 0 or type(age) not in (int, float):
        return ''
    try:
        age = float(age)
    except OverflowError:
        return ''
    if not math.isfinite(age):
        return ''
    young, old, free = (_comma(_int(league, k)) for k in ('le25', 'ge33', 'fa'))
    return ('<section class="league"><h2>League</h2><p>%s players on rosters, mean age %s.</p>'
            '<p>%s aged 25 or under, %s aged 33 or over. %s free agents.</p></section>'
            % (_comma(rostered), '%.1f' % age, young, old, free))


def _coverage_html(meta):
    """A line for the lead column when the watcher has stories for only part of the played games: '' when the meta
    does not say so (old meta.json, a full run, no games played)."""
    played, stories = meta.get('played'), meta.get('stories')
    ok = (type(played) is int and type(stories) is int and played > 0 and stories < played)
    if not ok:
        return ''
    return ('<p class="coverage">Stories for %s of %s games played. The game keeps box scores for seven sim days; '
            'a watcher that is not running during a long sim misses the games in between.</p>'
            % (_comma(stories), _comma(played)))


def _lead_html(folder, home, page, coverage=''):
    """The front page's main column for a season folder: on page 1 the newest 'Around the league' column and the
    coverage line, then the page's stories (linked under home) and the pager."""
    stories = _stories(folder)
    lead = []
    if page == 1:
        feed = _latest_feed(folder)
        if feed:
            month, day = _int(feed, 'month'), _int(feed, 'day')
            href = '%sday/%02d-%02d' % (home, month, day) if 1 <= month <= 12 and 1 <= day <= 31 else None
            lead.append(_feed_html(feed, href))
        lead.append(coverage)
    shown = stories[(page - 1) * PER_PAGE:page * PER_PAGE]
    if not stories:
        lead.append('<p class="empty">No game stories yet.</p>')
    elif not shown:
        lead.append('<p class="empty">No stories on this page.</p>')
    lead.extend(_story_row(home, key, rec) for key, rec in shown)
    lead.append(_pager(home, page, len(stories)))
    return ''.join(lead)


def _front_page(title, masthead, nav, lead, side):
    body = (masthead + nav + '<div class="grid"><section class="lead">%s</section><aside class="side">%s</aside></div>'
            % (lead, side))
    return _page_reply(200, title, body)


def _association(data_dir, assn, qs):
    meta = _read_obj(data_dir / assn / 'meta.json')
    if meta is None:
        return _not_found()
    page = _page_no(qs)
    name = _text(meta.get('name')) or assn
    folder, home = data_dir / assn, '/news/%s/' % assn
    moves = _moves_box(data_dir, assn) if page == 1 else ''
    season = (_season_links(folder, home, _rookie_years(data_dir, assn), _read_obj(folder / 'records.json') is not None)
              if page == 1 else '')
    past = _past_box(data_dir, assn) if page == 1 else ''
    replay = _replay_link(folder, home) if page == 1 else ''
    payroll = _payroll_box(data_dir, assn) if page == 1 else ''
    scouting = _scouting_links(folder, home) if page == 1 else ''
    league = _league_html(meta.get('league')) if page == 1 else ''
    side = (moves + season + past + replay + payroll + scouting + league + _standings_html(meta.get('standings'))
            + _leaders_html(meta.get('leaders')))
    return _front_page('%s · League News' % name, _masthead(name, _through(meta)), _nav(),
                       _lead_html(folder, home, page, _coverage_html(meta)), side)


def _past_label(d):
    """'1997 season'; '1998-2' reads '1998 season (2)'."""
    year, _, again = d.partition('-')
    return '%s season (%s)' % (year, again) if again else '%s season' % year


def _past_key(d):
    year, _, again = d.partition('-')
    return int(year), int(again or 0), d


def _past_seasons(data_dir, assn):
    """[(D, meta or None)] for every archived season of the association, newest first: by year, then repeat number
    ('1998-2' before '1998'). meta is the season's last meta.json, None when it is missing or unreadable."""
    past_dir = data_dir / assn / 'past'
    if not ASSN_RE.fullmatch(assn):
        return []
    try:
        names = os.listdir(past_dir)
    except OSError:
        return []
    found = sorted((n for n in names if PAST_RE.fullmatch(n) and (past_dir / n).is_dir()), key=_past_key, reverse=True)
    return [(d, _read_obj(past_dir / d / 'meta.json')) for d in found]


def _champion_rows(data_dir, assn):
    """One row per season with a postseason file, newest first: the current folder's first, then the archived ones.
    Each row takes the World Series (the round whose 'round' is 3) for the runner-up and the series score."""
    folders = [(data_dir / assn, '/news/%s/' % assn, None, 'Current season')]
    folders += [(data_dir / assn / 'past' / d, '/news/%s/past/%s/' % (assn, d), d, _past_label(d))
                for d, _ in _past_seasons(data_dir, assn)]
    rows = []
    for folder, home, d, fallback in folders:
        rec = _season_file(folder, 'postseason')
        if rec is None:
            continue
        facts = _d(rec.get('facts'))
        season = facts.get('season')
        champion = facts.get('champion')
        champion = champion if isinstance(champion, str) and champion else None
        runner_up, series = None, ''
        for rnd in _dicts(facts.get('rounds')):
            if rnd.get('round') == 3:
                s = next(iter(_dicts(rnd.get('series')) or ()), None)
                if s is not None:
                    teams, wins = s.get('teams'), s.get('wins')
                    if (isinstance(teams, list) and len(teams) == 2 and all(isinstance(t, str) for t in teams)
                            and isinstance(wins, list) and len(wins) == 2 and all(type(w) is int for w in wins)):
                        if champion == teams[0]:
                            runner_up, series = teams[1], '%d-%d' % (wins[0], wins[1])
                        elif champion == teams[1]:
                            runner_up, series = teams[0], '%d-%d' % (wins[1], wins[0])
                        else:
                            series = '%d-%d' % (wins[0], wins[1])
                break
        rows.append({'home': home, 'season': season if type(season) is int else None,
                     'label': str(season) if type(season) is int else (fallback or _text(season)),
                     'champion': champion, 'runner_up': runner_up, 'series': series})
    return rows


def _champions(data_dir, assn):
    """The season champions, one row per season with a postseason file, newest first. 404 without the meta.json."""
    meta = _read_obj(data_dir / assn / 'meta.json')
    if meta is None:
        return _not_found()
    name = _text(meta.get('name')) or assn
    rows = [[_Markup('<a href="%spostseason">%s</a>' % (esc(r['home']), esc(r['label']))),
             r['champion'] or 'In progress', r['runner_up'] or '', r['series']]
            for r in _champion_rows(data_dir, assn)]
    table = (_table('Champions', ('Season', 'Champion', 'Runner-up', 'Series'), rows, text=(0, 1, 2)) if rows
             else '<p class="empty">No postseason played yet.</p>')
    body = _masthead('Champions') + _league_nav(assn, {'association': name}) + '<section>%s</section>' % table
    return _page_reply(200, '%s · Champions' % name, body)


def _past_box(data_dir, assn):
    """The Past seasons box for the side column: Champions when some season has one, then one link per archived
    season. '' for none."""
    links = ['<li><a href="/news/%s/champions">Champions</a></li>' % esc(assn)] \
        if any(r['champion'] for r in _champion_rows(data_dir, assn)) else []
    links += ['<li><a href="/news/%s/past/%s/">%s</a></li>' % (esc(assn), esc(d), esc(_past_label(d)))
              for d, _ in _past_seasons(data_dir, assn)]
    if not links:
        return ''
    return '<section class="past"><h2>Past seasons</h2><ul>%s</ul></section>' % ''.join(links)


def _past_front(folder, assn, d, qs):
    """A past season's front page: the current front page's layout from the archived files, without the moves, payroll
    and replay boxes, and a link back to the current season. 404 when the archived meta.json is unreadable."""
    meta = _read_obj(folder / 'meta.json')
    if meta is None:
        return _not_found()
    page = _page_no(qs)
    name = _text(meta.get('name')) or assn
    home = '/news/%s/past/%s/' % (assn, d)
    season = _season_links(folder, home) if page == 1 else ''
    scouting = _scouting_links(folder, home) if page == 1 else ''
    league = _league_html(meta.get('league')) if page == 1 else ''
    side = season + scouting + league + _standings_html(meta.get('standings')) + _leaders_html(meta.get('leaders'))
    back = '<a href="/news/%s/">&larr; Current season</a> &middot; ' % esc(assn)
    return _front_page('%s · %s · League News' % (name, _past_label(d)), _masthead(name, _through(meta)), _nav(back),
                       _lead_html(folder, home, page), side)


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


def _league_nav(assn, facts, home=None):
    """The back link to the season's front page (home, default the association's) and the league list."""
    league = _text(facts.get('association')) or assn
    return ('<p class="nav"><a href="%s">&larr; %s</a> &middot; <a href="/news/">All leagues</a></p>'
            % (esc(home or '/news/%s/' % assn), esc(league)))


def _story_page(assn, key, rec, home=None):
    facts = _d(rec.get('facts'))
    headline = _text(rec.get('headline'))
    stadium = _text(_d(facts.get('home')).get('stadium'))
    sides = (_d(facts.get('away')), _d(facts.get('home')))
    box = _table('Box score', ('Team', 'R', 'H'), [[s.get('name'), s.get('runs'), s.get('hits')] for s in sides])
    bats = [[b.get('team'), b.get('name'), b.get('ab'), b.get('h'), b.get('hr'), b.get('rbi'), b.get('bb'), b.get('r')]
            for b in _dicts(facts.get('batters'))]
    decisions = _d(facts.get('decisions'))
    lines = ''.join(_decision(label, _d(decisions.get(role)))
                    for label, role in (('W', 'win'), ('L', 'loss'), ('S', 'save')))
    parts = [
        _league_nav(assn, facts, home),
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


def _story(folder, assn, key, home):
    rec = _read_obj(folder / 'recaps' / (key + '.json'))
    return _story_page(assn, key, rec, home) if rec is not None else _not_found()


def _season_file(folder, which):
    """The season file of that kind (which: 'preview', 'awards', 'postseason', 'replay' or 'contracts') as an object,
    else None."""
    rec = _read_obj(folder / (which + '.json'))
    return rec if rec is not None and rec.get('kind') == which else None


def _story_layout(assn, rec, label, below, home=None):
    """A page in the game story layout: the body, then the markup in below."""
    headline = _text(rec.get('headline'))
    parts = [
        _league_nav(assn, _d(rec.get('facts')), home),
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


def _preview_page(assn, rec, home=None):
    tables = []
    for div in _dicts(_d(rec.get('facts')).get('divisions')):
        league, division = _text(div.get('league')).strip(), _text(div.get('division')).strip()
        caption = ' '.join(x for x in (league, division) if x) or 'Teams'
        rows = [[t.get('name'), t.get('manager'), _hitter_text(t.get('hitter')), _pitcher_text(t.get('pitcher'))]
                for t in _dicts(div.get('teams'))]
        tables.append(_table(caption, ('Team', 'Manager', 'Top hitter', 'Top pitcher'), rows, text=4))
    return _story_layout(assn, rec, 'Season preview', tables, home)


def _awards_page(assn, rec, home=None):
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
    return _story_layout(assn, rec, 'Season awards', sections, home)


def _game_story(rec, rnd, g, n):
    """True when a recap is the table's game's story: its post names the same round and 0-based game and its facts
    name the same sides and score. Never raises: a thin recap matches nothing."""
    post = rec.get('post')
    if not isinstance(post, dict) or post.get('round') != rnd or post.get('game') != n:
        return False
    away, home = _d(_d(rec.get('facts')).get('away')), _d(_d(rec.get('facts')).get('home'))
    return (away.get('name') == g.get('away') and home.get('name') == g.get('home')
            and away.get('runs') == g.get('away_runs') and home.get('runs') == g.get('home_runs'))


def _postseason_page(assn, rec, home=None, stories=()):
    """The bracket round by round: a table of games per series, a line for a series not started. With stories, the
    (key, recap) pairs a season's game stories are, each Game number links to its own story, the first row only."""
    facts = _d(rec.get('facts'))
    sections, used = [], set()
    for rnd in _dicts(facts.get('rounds')):
        series = []
        for s in _dicts(rnd.get('series')):
            caption = '%s vs %s' % tuple((_strings(s.get('teams')) + ['', ''])[:2])
            rows = []
            for n, g in enumerate(_dicts(s.get('games')), 1):
                key = next((k for k, r in stories if k not in used
                            and _game_story(r, rnd.get('round'), g, n - 1)), None) if home else None
                if key is not None:
                    used.add(key)
                cell = _Markup('<a href="%s%s">%d</a>' % (esc(home), esc(key), n)) if key else n
                rows.append([cell, g.get('away'), g.get('away_runs'), g.get('home'), g.get('home_runs')])
            series.append(_table(caption, ('Game', 'Away', 'R', 'Home', 'R'), rows, text=(1, 3)) if rows
                          else '<p>%s</p>' % esc(caption))
        sections.append('<section><h2>%s</h2>%s</section>' % (esc(rnd.get('name')), ''.join(series)))
    label = '%s postseason' % _text(facts.get('season'))
    return _story_layout(assn, rec, label.strip(), sections, home)


def _postseason(folder, assn, home):
    """The postseason page; 404 when its file is missing, unreadable or of another kind."""
    rec = _season_file(folder, 'postseason')
    return _postseason_page(assn, rec, home, _stories(folder)) if rec is not None else _not_found()


def _is_num(value):
    """A number a page can print: an int or a finite float, under 10**15 either way. json.load reads NaN, Infinity and
    400-digit ints, which would make round() or a '%.3f' raise and take the page down."""
    if type(value) is int:
        return abs(value) < 10 ** 15
    return type(value) is float and math.isfinite(value) and abs(value) < 1e15


def _pct_text(value):
    """A winning percentage as the standings print it: .612, 1.000. '' when not a number."""
    return ('%.3f' % value).lstrip('0') if _is_num(value) else ''


def _gap_text(value):
    """A signed gap in wins: +3.5, -0.5. '' when not a number."""
    return '%+.1f' % value if _is_num(value) else ''


def _stat_text(stat, value):
    if stat == 'AVG' and _is_num(value):
        return _pct_text(value)
    if stat == 'ERA' and _is_num(value):
        return '%.2f' % value
    return value


def _wl(side):
    return '%s-%s' % (_text(side.get('w')), _text(side.get('l')))


def _strings(value):
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _pairs(value):
    """[(name, value)] from a leaders list; entries that are not two-item lists are dropped."""
    if not isinstance(value, list):
        return []
    return [(p[0], p[1]) for p in value if isinstance(p, list) and len(p) == 2]


def _league_summary(info, teams):
    """The paragraph under a league's name: the rank correlation, the mean gap, and the best real and sim records."""
    corr = info.get('rank_corr')
    parts = ['Rank correlation with the real standings: %s.' % ('%.2f' % corr if _is_num(corr) else 'n/a')]
    gap = _pct_text(info.get('mean_abs_diff'))
    if gap:
        parts.append('Mean gap in winning percentage: %s.' % gap)
    for label, side, key in (('Best real record', 'real', 'real_best'), ('Best sim record', 'sim', 'sim_best')):
        best = _text(info.get(key))
        team = next((t for t in teams if best and _text(t.get('name')) == best), None)
        if team is not None:
            parts.append('%s: %s, %s.' % (label, best, _wl(_d(team.get(side)))))
    return ' '.join(parts)


def _league_section(lg, info, teams):
    rows = []
    for t in teams:
        real, sim = _d(t.get('real')), _d(t.get('sim'))
        rows.append([t.get('name'), _wl(real), _pct_text(real.get('pct')), _wl(sim), _pct_text(sim.get('pct')),
                     _gap_text(t.get('wins_diff'))])
    table = _table('Standings', ('Team', 'Real W-L', 'Real Pct', 'Sim W-L', 'Sim Pct', 'Gap'), rows) if rows else ''
    return '<section><h2>%s</h2><p>%s</p>%s</section>' % (esc(lg), esc(_league_summary(info, teams)), table)


def _leader_tables(leaders):
    tables = []
    for stat in REPLAY_STATS:
        side = _d(leaders.get(stat))
        real, sim = _pairs(side.get('real')), _pairs(side.get('sim'))
        if not real and not sim:
            continue
        rows = []
        for i in range(max(len(real), len(sim))):
            r, s = real[i] if i < len(real) else ('', ''), sim[i] if i < len(sim) else ('', '')
            rows.append([i + 1, r[0], _stat_text(stat, r[1]), s[0], _stat_text(stat, s[1])])
        tables.append(_table(stat, ('Rank', 'Real', 'Value', 'Sim', 'Value'), rows, text=(1, 3)))
    return tables


def _player_table(players):
    rows = [[_text(p.get('stat')), p.get('name'), _stat_text(_text(p.get('stat')), p.get('real')),
             _stat_text(_text(p.get('stat')), p.get('sim'))] for p in players]
    return _table('Players', ('Stat', 'Player', 'Real', 'Sim'), rows, text=2) if rows else ''


def _replay_page(assn, name, rec, home=None):
    """The replay scorecard: the season's status, each league's standings against the real ones with a summary, the
    leaders of each stat in both seasons, then the real leaders the sim has."""
    teams = _dicts(rec.get('teams'))
    leagues = _d(rec.get('leagues'))
    played, scheduled = rec.get('played'), rec.get('scheduled')
    # Per-team averages ('160.9' for 2414 games over 30 teams) read as whole games.
    status = ('After %d of %d games per team' % (round(played), round(scheduled))
              if _is_num(played) and _is_num(scheduled) else '')
    unmatched = _strings(rec.get('unmatched'))
    leaders = _leader_tables(_d(rec.get('leaders')))
    parts = [_masthead('Replay vs history', status), _league_nav(assn, {'association': name}, home)]
    for lg in sorted(leagues):
        parts.append(_league_section(lg, _d(leagues[lg]), [t for t in teams if _text(t.get('lg')) == lg]))
    if unmatched:
        parts.append('<p class="empty">%s</p>' % esc('No real counterpart: ' + ', '.join(unmatched) + '.'))
    parts.append('<section><h2>Leaders</h2>%s</section>' % (''.join(leaders) or '<p class="empty">No leaders yet.</p>'))
    players = _player_table(_dicts(rec.get('players')))
    parts.append('<section><h2>Real leaders in the sim</h2>%s</section>'
                 % (players or '<p class="empty">No real leaders in the sim yet.</p>'))
    return _page_reply(200, '%s · Replay vs history' % name, ''.join(parts))


def _replay(folder, assn, home):
    """The replay scorecard page; 404 when its file is missing, unreadable or of another kind."""
    rec = _season_file(folder, 'replay')
    if rec is None:
        return _not_found()
    name = _text(_d(_read_obj(folder / 'meta.json')).get('name')) or assn
    return _replay_page(assn, name, rec, home)


def _replay_link(folder, home):
    """The Replay vs history box for the side column: a link to the scorecard. '' without its file."""
    if _season_file(folder, 'replay') is None:
        return ''
    return ('<section class="replay"><h2>Replay vs history</h2><ul><li><a href="%sreplay">Scorecard</a>'
            '</li></ul></section>' % esc(home))


def _season(folder, assn, which, home):
    """The season preview or awards page; 404 when its file is missing, unreadable or of another kind."""
    rec = _season_file(folder, which)
    if rec is None:
        return _not_found()
    return _preview_page(assn, rec, home) if which == 'preview' else _awards_page(assn, rec, home)


def _rookie_years(data_dir, assn):
    """The seasons with a rookie class page, newest first: the <4 digits>.json files in <assn>/rookies (ids.json, the
    watcher's snapshot, is not one)."""
    if not ASSN_RE.fullmatch(assn):
        return []
    folder = data_dir / assn / 'rookies'
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = (YEAR_FILE_RE.fullmatch(n) for n in names)
    return sorted((int(m.group(1)) for m in found if m and (folder / m.group(0)).is_file()), reverse=True)


def _season_links(folder, home, rookie_years=(), records=False):
    """The Season box for the side column: postseason above awards above preview, each only when its file exists, then
    the Record book link when records is true, then a link per year in rookie_years (the current front page passes
    both; a past season's does not). '' for none."""
    links = ['<li><a href="%s%s">%s</a></li>' % (esc(home), which, label)
             for which, label in (('postseason', 'Postseason'), ('awards', 'Season awards'),
                                  ('preview', 'Season preview'))
             if _season_file(folder, which) is not None]
    if records:
        links.append('<li><a href="%srecords">Record book</a></li>' % esc(home))
    links += ['<li><a href="%srookies/%04d">%04d rookie class</a></li>' % (esc(home), y, y)
              for y in rookie_years]
    if not links:
        return ''
    return '<section class="season"><h2>Season</h2><ul>%s</ul></section>' % ''.join(links)


def _scouting_links(folder, home):
    """The Scouting reports box for the side column: one link per team's report. '' for none."""
    links = ['<li><a href="%steam/%d">%s</a></li>' % (esc(home), tid, esc(rec.get('team')))
             for tid, rec in _scout_files(folder)]
    if not links:
        return ''
    return '<section class="scouting"><h2>Scouting reports</h2><ul>%s</ul></section>' % ''.join(links)


def _team_page(assn, tid, rec, home=None):
    """A team's scouting report in the story layout, then its roster graded: hitters, then pitchers."""
    roster = _d(rec.get('roster'))
    hitters = [[h.get('name'), h.get('pos'), h.get('hand'), h.get('age'), h.get('contact'), h.get('power'),
                h.get('speed'), h.get('fielding')] for h in _dicts(roster.get('hitters'))]
    pitchers = [[p.get('name'), p.get('hand'), p.get('age'), p.get('control'), p.get('strikeout'), p.get('stamina'),
                 p.get('fielding')] for p in _dicts(roster.get('pitchers'))]
    tables = [
        _table('Hitters', ('Player', 'Pos', 'B/T', 'Age', 'Contact', 'Power', 'Speed', 'Field'), hitters, text=3),
        _table('Pitchers', ('Player', 'B/T', 'Age', 'Control', 'Strikeout', 'Stamina', 'Field'), pitchers, text=2),
    ]
    return _story_layout(assn, rec, 'Scouting report', tables, home)


def _team(folder, assn, tid, home):
    """A team's scouting report page; 404 when its file is missing, unreadable or of another kind."""
    rec = _read_obj(folder / 'scout' / (tid + '.json'))
    if rec is None or rec.get('kind') != 'scout':
        return _not_found()
    return _team_page(assn, tid, rec, home)


def _record_value(stat, value):
    """A record's value as a table prints it: .395 for avg, 1.01 for era, the count for the rest; '' when it is not a
    number a page can print (_is_num)."""
    if not _is_num(value):
        return ''
    if stat == 'avg':
        return _pct_text(value)
    return '%.2f' % value if stat == 'era' else value


def _record_tables(group, season):
    """One small table per stat of RECORD_STATS that has rows, in the record book's order: rank, name, year (seasons for
    a career), value and, for a single season, team. group is records.json's 'season' or 'career'. '' for none."""
    group = _d(group)
    tables = []
    for stat, label in RECORD_STATS:
        rows = _dicts(group.get(stat))[:RECORD_ROWS]
        if not rows:
            continue
        if season:
            body = [[i, r.get('name'), r.get('year'), _record_value(stat, r.get('value')), r.get('team')]
                    for i, r in enumerate(rows, 1)]
            tables.append(_table(label, ('Rank', 'Player', 'Year', 'Value', 'Team'), body, text=(1, 4)))
        else:
            body = [[i, r.get('name'), r.get('seasons'), _record_value(stat, r.get('value'))]
                    for i, r in enumerate(rows, 1)]
            tables.append(_table(label, ('Rank', 'Player', 'Seasons', 'Value'), body, text=(1,)))
    return ''.join(tables)


def _bar_html(bar):
    """The bar table: each stat's record to beat, its holder and year, and whether it is a real season or this league's
    own. '' when no stat has one."""
    bar = _d(bar)
    rows = []
    for stat, label in RECORD_STATS:
        b = _d(bar.get(stat))
        if b:
            rows.append([label, _record_value(stat, b.get('value')), b.get('name'), b.get('year'),
                         RECORD_SOURCES.get(b.get('source'), '') if isinstance(b.get('source'), str) else ''])
    if not rows:
        return ''
    table = _table('Record to beat', ('Stat', 'Value', 'Holder', 'Year', 'Source'), rows, text=(0, 2, 4))
    return '<section><h2>The bar</h2>%s</section>' % table


def _chase_html(folder):
    """The Chase box: the lines the newest column's facts carry in 'chase' (players on pace for a season record).
    '' when the newest column has none, as in the postseason."""
    lines = _strings(_d(_d(_latest_feed(folder)).get('facts')).get('chase'))
    if not lines:
        return ''
    return '<section><h2>Chase</h2><ul class="moves">%s</ul></section>' % ''.join('<li>%s</li>' % esc(x) for x in lines)


def _records(data_dir, assn):
    """The record book page: the chase box, the best single seasons and careers, then the bar. 404 without the
    association's meta.json. Without records.json, or with empty tables, it says the book fills in after the first
    simulated season."""
    meta = _read_obj(data_dir / assn / 'meta.json')
    if meta is None:
        return _not_found()
    name = _text(meta.get('name')) or assn
    folder = data_dir / assn
    doc = _d(_read_obj(folder / 'records.json'))
    season, career = _record_tables(doc.get('season'), True), _record_tables(doc.get('career'), False)
    through = _int(doc, 'through')
    parts = [_masthead('Record book', 'through %d' % through if through > 0 else ''),
             _league_nav(assn, {'association': name}), _chase_html(folder)]
    if season or career:
        parts.append('<section><h2>Single season</h2>%s</section>' % (season or '<p class="empty">None yet.</p>'))
        parts.append('<section><h2>Career</h2>%s</section>' % (career or '<p class="empty">None yet.</p>'))
    else:
        parts.append('<p class="empty">The record book fills in after the first simulated season.</p>')
    parts.append(_bar_html(doc.get('bar')))
    return _page_reply(200, '%s · Record book' % name, ''.join(parts))


def _rookies_page(assn, year, rec, home=None):
    """A season's rookie class in the story layout, then every hitter and pitcher of it."""
    facts = _d(rec.get('facts'))
    hitters = [[h.get('name'), h.get('pos'), h.get('age'), h.get('team'), h.get('contact'), h.get('power'),
                h.get('speed'), h.get('fielding')] for h in _dicts(facts.get('hitters'))]
    pitchers = [[p.get('name'), p.get('age'), p.get('team'), p.get('control'), p.get('strikeout'), p.get('stamina')]
                for p in _dicts(facts.get('pitchers'))]
    tables = [
        _table('Hitters', ('Player', 'Pos', 'Age', 'Team', 'Contact', 'Power', 'Speed', 'Fielding'), hitters,
               text=(0, 1, 3)) if hitters else '',
        _table('Pitchers', ('Player', 'Age', 'Team', 'Control', 'Strikeout', 'Stamina'), pitchers,
               text=(0, 2)) if pitchers else '',
    ]
    return _story_layout(assn, rec, '%s rookie class' % year, tables, home)


def _rookies(data_dir, assn, year):
    """A season's rookie class page; 404 for a year that is not four digits or a file missing or unreadable."""
    rec = _read_obj(data_dir / assn / 'rookies' / (year + '.json')) if YEAR_RE.fullmatch(year) else None
    if rec is None:
        return _not_found()
    return _rookies_page(assn, year, rec, '/news/%s/' % assn)


def _move_log(data_dir, assn):
    """The transaction log's events that have a line, oldest first; [] without a readable log."""
    log = _read_obj(data_dir / assn / 'moves' / 'log.json')
    return [ev for ev in _dicts(_d(log).get('events')) if _move_text(ev)]


def _who(ev):
    """'Pat Smith (SS, 27)': the name with its position and age where known."""
    bits = [b for b in (_text(ev.get('pos')), _text(ev.get('age'))) if b]
    name = _text(ev.get('name'))
    return '%s (%s)' % (name, ', '.join(bits)) if bits else name


def _milestone(ev):
    """'reached 500 career home runs' or 'reached 40 home runs this season'; a stat not named here is given as it is."""
    scope, _, key = _text(ev.get('stat')).partition(' ')
    value, word = _text(ev.get('value')), STAT_WORDS.get(key)
    if word is None or scope not in ('career', 'season'):
        return 'reached %s %s' % (value, _text(ev.get('stat')))
    if scope == 'season':
        return 'reached %s %ss this season' % (value, word)
    return 'reached %s career %ss' % (value, word)


def _move_text(ev):
    """One plain line for a logged event; '' for a kind the page does not name."""
    kind, who = _text(ev.get('kind')), _who(ev)
    frm, to = _text(ev.get('from')), _text(ev.get('to'))
    if kind == 'signed':
        return 'Signed: %s, %s to %s' % (who, frm, to)
    if kind == 'released':
        return 'Released: %s, %s to %s' % (who, frm, to)
    if kind == 'moved':
        return 'Moved: %s, %s to %s' % (who, frm, to)
    if kind == 'new':
        return 'New player: %s, %s' % (who, to)
    if kind == 'retired':
        return 'Retired: %s' % who
    if kind == 'milestone':
        return 'Milestone: %s%s %s' % (_text(ev.get('name')), ' (%s)' % to if to else '', _milestone(ev))
    return ''


def _move_html(assn_dir, assn, ev):
    """A list item for a logged event, linked to its note when the note's file is there."""
    text, n = _move_text(ev), ev.get('note')
    if type(n) is int and NOTE_RE.fullmatch(str(n)) and (assn_dir / 'moves' / 'notes' / ('%d.json' % n)).is_file():
        return '<li><a href="/news/%s/moves/%d">%s</a></li>' % (esc(assn), n, esc(text))
    return '<li>%s</li>' % esc(text)


def _offseason(date, year):
    """'Offseason before 2008' for an event dated Offseason (the offseason ahead of that season), else ''."""
    if date != 'Offseason':
        return ''
    return 'Offseason before %s' % year if year else 'Offseason'


def _move_days(events):
    """[(label, [event, ...])], newest date first. The log is in time order, so a run of events with the same date and
    year is one day; the label is the date with the year after it, or 'Offseason before' the year."""
    days, key = [], None
    for ev in reversed(events):
        now = (_text(ev.get('date')), _int(ev, 'year', None))
        if now != key:
            key = now
            label = _offseason(now[0], _text(now[1])) or ', '.join(x for x in (now[0], _text(now[1])) if x)
            days.append((label, []))
        days[-1][1].append(ev)
    return days


def _transactions(data_dir, assn, qs):
    """The Transactions page: roster moves and milestones, PER_PAGE dates a page, newest date first."""
    meta = _read_obj(data_dir / assn / 'meta.json')
    if meta is None:
        return _not_found()
    name = _text(meta.get('name')) or assn
    days = _move_days(_move_log(data_dir, assn))
    page = _page_no(qs)
    shown = days[(page - 1) * PER_PAGE:page * PER_PAGE]
    if not days:
        lead = '<p class="empty">No transactions yet.</p>'
    elif not shown:
        lead = '<p class="empty">No dates on this page.</p>'
    else:
        lead = ''.join('<section><h2>%s</h2><ul class="moves">%s</ul></section>'
                       % (esc(label), ''.join(_move_html(data_dir / assn, assn, ev) for ev in evs))
                       for label, evs in shown)
    pager = _pager('/news/%s/moves' % assn, page, len(days), 'Newer dates', 'Older dates')
    body = (_masthead(name, _through(meta)) + _league_nav(assn, {'association': name})
            + '<section class="story-page">%s%s</section>' % (lead, pager))
    return _page_reply(200, '%s · Transactions' % name, body)


def _move_note(data_dir, assn, n):
    """A transaction note in the story layout; 404 when its file is missing, unreadable or not a note."""
    rec = _read_obj(data_dir / assn / 'moves' / 'notes' / (n + '.json'))
    if rec is None or rec.get('kind') != 'move':
        return _not_found()
    ev = _d(rec.get('event'))
    date, year = _text(ev.get('date')), _text(ev.get('year'))
    when = _offseason(date, year) or SEP.join(x for x in (date, year) if x)
    return _story_layout(assn, rec, when or 'Transaction', [])


def _moves_box(data_dir, assn):
    """The Transactions box for the side column: the newest MOVES_BOX lines and a link to the page. '' for no events."""
    events = _move_log(data_dir, assn)
    if not events:
        return ''
    lines = ''.join(_move_html(data_dir / assn, assn, ev) for ev in reversed(events[-MOVES_BOX:]))
    return ('<section class="transactions"><h2>Transactions</h2><ul class="moves">%s</ul>'
            '<p><a href="/news/%s/moves">All transactions</a></p></section>' % (lines, esc(assn)))


def _money(value):
    """A dollar amount as contracts.money writes it; '' for anything that is not a number."""
    return contracts.money(value) if _is_num(value) else ''


def _team_row(rec, tid):
    """The payroll row of team tid in a contracts file, or None."""
    return next((r for r in _dicts(rec.get('payroll')) if _int(r, 'tid', None) == tid), None)


def _team_html(assn, row):
    """A payroll row's team name, linked to the team's payroll page when its tid is one the pages take; escaped."""
    tid, name = _int(row, 'tid', None), _text(row.get('name'))
    if tid is None or not TID_RE.fullmatch(str(tid)):
        return esc(name)
    return '<a href="/news/%s/payroll/%d">%s</a>' % (esc(assn), tid, esc(name))


def _signing_line(ev, teams):
    """One line for a contract event: a signing, a re-signing, a move or a release. '' for a kind the page does not name.
    teams maps a tid to its name."""
    kind, name = _text(ev.get('kind')), _text(ev.get('name'))
    team = teams.get(_int(ev, 'team', None), '')
    if kind in ('signed', 're-signed'):
        verb = 'signs with' if kind == 'signed' else 're-signs with'
        return '%s %s %s: %s yr, %s' % (name, verb, team, _text(ev.get('years')), _money(ev.get('salary')))
    if kind == 'moved':
        return '%s joins %s, contract travels' % (name, team)
    if kind == 'released':
        return '%s released' % name
    return ''


def _payroll_box(data_dir, assn):
    """The Payroll box for the side column: the top TOP teams by payroll with their totals, and a link to the pages.
    '' without a contracts file."""
    rec = _season_file(data_dir / assn, 'contracts')
    rows = _dicts(rec.get('payroll'))[:TOP] if rec is not None else []
    if not rows:
        return ''
    items = ''.join('<li>%s: %s</li>' % (_team_html(assn, r), esc(_money(r.get('total')))) for r in rows)
    return ('<section class="payroll"><h2>Payroll</h2><ul>%s</ul><p><a href="/news/%s/payroll">All payrolls</a></p>'
            '</section>' % (items, esc(assn)))


def _payroll(data_dir, assn):
    """The payroll page: each team's players, payroll, average and top salary, then the recent signings, newest first.
    404 when the contracts file is missing or of another kind."""
    rec = _season_file(data_dir / assn, 'contracts')
    if rec is None:
        return _not_found()
    name = _text(_d(_read_obj(data_dir / assn / 'meta.json')).get('name')) or assn
    rows = _dicts(rec.get('payroll'))
    teams = {_int(r, 'tid', None): _text(r.get('name')) for r in rows}
    table = _table('Payrolls', ('Team', 'Players', 'Payroll', 'Average', 'Top'),
                   [[_Markup(_team_html(assn, r)), r.get('players'), _money(r.get('total')), _money(r.get('average')),
                     _money(r.get('top'))] for r in rows]) if rows else '<p class="empty">No payrolls yet.</p>'
    lines = [line for line in (_signing_line(ev, teams) for ev in _dicts(rec.get('events'))) if line]
    recent = ''.join('<li>%s</li>' % esc(line) for line in reversed(lines[-SIGNINGS:]))
    signings = '<ul class="moves">%s</ul>' % recent if recent else '<p class="empty">No signings yet.</p>'
    through = 'Season %d' % rec['season_year'] if type(rec.get('season_year')) is int else ''
    body = (_masthead('Payroll', through) + _league_nav(assn, {'association': name})
            + '<section>%s</section><section><h2>Recent signings</h2>%s</section>' % (table, signings))
    return _page_reply(200, '%s · Payroll' % name, body)


def _payroll_team(data_dir, assn, tid):
    """One team's contracts, by salary then name: player, position, age, salary, years left and status. 404 when the
    contracts file is missing or of another kind, or tid is not one of its teams."""
    rec = _season_file(data_dir / assn, 'contracts')
    row = _team_row(rec, tid) if rec is not None else None
    if row is None:
        return _not_found()
    name = _text(_d(_read_obj(data_dir / assn / 'meta.json')).get('name')) or assn
    mine = [c for c in _d(rec.get('contracts')).values() if isinstance(c, dict) and _int(c, 'team', None) == tid]
    mine.sort(key=lambda c: (-_int(c, 'salary'), _text(c.get('name'))))
    rows = [[c.get('name'), c.get('pos'), c.get('age'), _money(c.get('salary')), c.get('left'),
             CONTRACT_STATUS.get(_text(c.get('class')), '')] for c in mine]
    table = _table('Contracts', ('Player', 'Pos', 'Age', 'Salary', 'Years left', 'Status'), rows, text=(0, 1, 5))
    body = (_masthead(_text(row.get('name')), 'Payroll') + _league_nav(assn, {'association': name})
            + '<section><p><a href="/news/%s/payroll">All payrolls</a></p>%s</section>' % (esc(assn), table))
    return _page_reply(200, '%s · Payroll' % _text(row.get('name')), body)


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


def _day_link(home, day, text):
    return '<a href="%sday/%02d-%02d">%s</a>' % (esc(home), day[0], day[1], text)


def _readable_around(folder, at):
    """The nearest column dates before and after `at` whose column reads (a pager link to an unreadable one would 404),
    sorted; each side read only as far as its first readable column."""
    days = _feed_days(folder)
    before = next((d for d in reversed(days) if d < at and _feed_file(folder, *d) is not None), None)
    after = next((d for d in days if d > at and _feed_file(folder, *d) is not None), None)
    return [d for d in (before, after) if d is not None]


def _day_pager(home, days, at):
    """Links to the column dates before and after `at` in days (sorted), each only when there is one."""
    before = [d for d in days if d < at]
    after = [d for d in days if d > at]
    links = []
    if before:
        links.append(_day_link(home, before[-1], '&larr; %s' % esc(_date_text(*before[-1]))))
    if after:
        links.append(_day_link(home, after[0], '%s &rarr;' % esc(_date_text(*after[0]))))
    return '<nav class="pager">%s</nav>' % ''.join(links) if links else ''


def _day(folder, assn, home, month, day):
    """One date's page: the column, every result in it, and the date's stories, with links to the dates around it.
    404 when the date has no readable column."""
    feed = _feed_file(folder, month, day)
    if feed is None:
        return _not_found()
    name = _text(_d(_read_obj(folder / 'meta.json')).get('name')) or assn
    date = _text(feed.get('date')) or _date_text(month, day)
    games = [[r.get('away'), r.get('away_runs'), r.get('home'), r.get('home_runs'), r.get('innings')]
             for r in _dicts(_d(feed.get('facts')).get('results'))]
    results = (_table('Results', ('Away', 'R', 'Home', 'R', 'Inn'), games, text=(0, 2)) if games
               else '<p class="empty">No games on this date.</p>')
    rows = [_story_row(home, key, rec) for key, rec in _stories(folder)
            if _int(rec, 'month') == month and _int(rec, 'day') == day]
    stories = ('<section><h2>Stories</h2>%s</section>'
               % (''.join(rows) or '<p class="empty">No stories for this date.</p>'))
    back = '<a href="%s">&larr; Front page</a> &middot; ' % esc(home)
    body = (_masthead(name, date) + _nav(back) + _feed_html(feed) + results + stories
            + _day_pager(home, _readable_around(folder, (month, day)), (month, day)))
    return _page_reply(200, '%s · %s · League News' % (name, date), body)


def _day_route(folder, assn, home, segment):
    """The day page for a path segment like '04-15'; 404 for any other segment."""
    m = DAY_RE.fullmatch(segment)
    if not m or not (1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31):
        return _not_found()
    return _day(folder, assn, home, int(m[1]), int(m[2]))


def _season_pages(folder, assn, home, rest):
    """The story, preview, awards, postseason, replay, team and day pages read from a season folder, linked under
    home. rest is the path after the season's front page; None when it is none of those pages."""
    if len(rest) == 2 and rest[0] == 'day':
        return _day_route(folder, assn, home, rest[1])
    if len(rest) == 1 and KEY_RE.fullmatch(rest[0]):
        return _story(folder, assn, rest[0], home)
    if len(rest) == 1 and rest[0] in ('preview', 'awards'):
        return _season(folder, assn, rest[0], home)
    if len(rest) == 1 and rest[0] == 'postseason':
        return _postseason(folder, assn, home)
    if len(rest) == 1 and rest[0] == 'replay':
        return _replay(folder, assn, home)
    if len(rest) == 2 and rest[0] == 'team' and TID_RE.fullmatch(rest[1]):
        return _team(folder, assn, rest[1], home)
    return None


def _past(data_dir, assn, rest, qs):
    """The pages under /news/<assn>/past/. rest starts at the season, D; 404 for a D that is not an archived season."""
    d = rest[0]
    folder = data_dir / assn / 'past' / d if PAST_RE.fullmatch(d) else None
    if folder is None or not folder.is_dir():
        return _not_found()
    home = '/news/%s/past/%s/' % (assn, d)
    if len(rest) == 1:
        return _moved(home + ('?' + qs if qs else ''))
    if rest[1:] == ['']:
        return _past_front(folder, assn, d, qs)
    return _season_pages(folder, assn, home, rest[1:]) or _not_found()


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
    reply = _season_pages(data_dir / assn, assn, '/news/%s/' % assn, rest[1:])
    if reply:
        return reply
    if len(rest) >= 3 and rest[1] == 'past':
        return _past(data_dir, assn, rest[2:], qs)
    if len(rest) == 3 and rest[1] == 'rookies':
        return _rookies(data_dir, assn, rest[2])
    if len(rest) == 2 and rest[1] == 'moves':
        return _transactions(data_dir, assn, qs)
    if len(rest) == 3 and rest[1] == 'moves' and NOTE_RE.fullmatch(rest[2]):
        return _move_note(data_dir, assn, rest[2])
    if len(rest) == 2 and rest[1] == 'champions':
        return _champions(data_dir, assn)
    if len(rest) == 2 and rest[1] == 'records':
        return _records(data_dir, assn)
    if len(rest) == 2 and rest[1] == 'payroll':
        return _payroll(data_dir, assn)
    if len(rest) == 3 and rest[1] == 'payroll' and TID_RE.fullmatch(rest[2]) and str(int(rest[2])) == rest[2]:
        return _payroll_team(data_dir, assn, int(rest[2]))     # canonical numbers only: '02' is not team 2's page
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
