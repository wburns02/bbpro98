"""The Hall of Fame for an association's retired players: who is on the ballot in a season, their career score, who is
inducted, and the induction story. Pure functions over plain dicts, as scout.py and moves.py are; the model is reached
only through the complete() callable the caller passes in. Prompt rules and the number check are recap's. The two
readers at the bottom (archive_years, sim_index) only read the watcher's history folder.

A player is on the ballot in season year S when he is retired, played a simulated season, and his last season with a
line (R) is MIN_WAIT to MAX_WAIT seasons back (ten ballots). His career score comes from the merged career rows
(history.totals); pct is that score against the induction bar. pct of INDUCT_PCT or more inducts him, under DROP_PCT
drops him for good, and the ballot of S - R == MAX_WAIT is his last. A retired player's totals never change, so a
player who is not inducted on his first ballot stays on the list, with the same pct, until he is dropped.

A career is a dict {'pid', 'name', 'pos', 'gone', 'rows'}: gone is True when no team roster and not the free-agent
list holds him, pos is the PYR position ('P' makes him a pitcher), and rows are history.merge's rows of his kind.
The hof dict (hof.json) is the contract run() keeps: 'stem', 'updated', 'year' (the season the last ballot was held
for), 'inducted' (cumulative: pid, name, kind, year, retired, score, pct, line, teams, story), 'ballot' (the latest
year's ballot, without its inductees and without the players it dropped on pct) and 'dropped' (pids).
"""
import json
import os
import re

import feed
import history
import recap

MIN_WAIT = 5        # seasons after his last one that a player is first on the ballot
MAX_WAIT = 15       # ... and last (ten ballots)
INDUCT_PCT = 75
DROP_PCT = 5
BAR = 50            # the score that is 75 percent
PCT_CAP = 99
SYSTEM = ("You are a newspaper baseball writer covering the association's Hall of Fame. Write the induction story of "
          "the one player in the facts: 90 to 140 words on his career and what it earned. Write numbers without "
          "commas. " + recap.RULES)
TEAM_COUNT = re.compile(r'[0-9]+TM')       # Lahman's label for a year with several teams ('2TM'): not a team


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def kind_of(pos):
    """'pit' for the PYR position 'P', else 'bat'."""
    return 'pit' if pos == 'P' else 'bat'


def score(kind, totals):
    """The career score of totals (history.totals of kind's rows; a missing key counts 0). bat: 40*h/3000 + 25*hr/500
    + 15*rbi/1500 + 10*r/1500 + 5*sb/400, plus clamp(100*(h/ab - .250), -5, 10) once ab is 4000. pit: 45*w/300 +
    25*so/3000 + 15*sv/300, plus clamp(10*(3.50 - ERA), -10, 15) once outs is 4500, with ERA 27*er/outs. Any other
    kind is a ValueError."""
    def t(key):
        return totals.get(key, 0)
    if kind == 'bat':
        s = 40 * t('h') / 3000 + 25 * t('hr') / 500 + 15 * t('rbi') / 1500 + 10 * t('r') / 1500 + 5 * t('sb') / 400
        if t('ab') >= 4000:
            s += clamp(100 * (t('h') / t('ab') - 0.250), -5, 10)
        return s
    if kind == 'pit':
        s = 45 * t('w') / 300 + 25 * t('so') / 3000 + 15 * t('sv') / 300
        if t('outs') >= 4500:
            s += clamp(10 * (3.50 - 27 * t('er') / t('outs')), -10, 15)
        return s
    raise ValueError('kind must be bat or pit, not %r' % (kind,))


def pct(s):
    """The score as a percent of the bar: min(99, round(75 * s / 50)). Python's round, so an exact half goes to the
    even number."""
    return min(PCT_CAP, round(INDUCT_PCT * s / BAR))


def eligible(year, last, gone, sim):
    """True when a player is on the ballot of season year: he is gone (retired), played a simulated season (sim), and
    last, the year of his last season with a line, is MIN_WAIT to MAX_WAIT seasons back. A last of None (no line at
    all) is never eligible."""
    return bool(gone and sim and last is not None and MIN_WAIT <= year - last <= MAX_WAIT)


def teams_of(rows):
    """The distinct team labels of rows in the order of first appearance. A blank label and a several-teams label
    ('2TM') are left out."""
    out = []
    for row in rows:
        team = row.get('team')
        if isinstance(team, str) and team and not TEAM_COUNT.fullmatch(team) and team not in out:
            out.append(team)
    return out


def ballot(year, careers, skip=()):
    """The players on the ballot of season year, best first (pct, then name, then pid): one dict per eligible career
    whose pid is not in skip, {'pid', 'name', 'kind', 'retired' (the year of his last line), 'years_on', 'score',
    'pct', 'line' (history.totals), 'teams'}. years_on is year - retired - 4: 1 on the first ballot, 11 on the last."""
    out = []
    for c in careers:
        rows = c.get('rows') or []
        last = max((r['year'] for r in rows), default=None)
        if c['pid'] in skip or not eligible(year, last, c.get('gone'), any(r.get('sim') for r in rows)):
            continue
        kind = kind_of(c.get('pos'))
        line = history.totals(rows, kind)
        s = score(kind, line)
        out.append({'pid': c['pid'], 'name': c['name'], 'kind': kind, 'retired': last, 'years_on': year - last - 4,
                    'score': round(s, 2), 'pct': pct(s), 'line': line, 'teams': teams_of(rows)})
    out.sort(key=lambda b: (-b['pct'], b['name'], b['pid']))
    return out


def held(old):
    """The season year of the last ballot in an hof dict, or None for no dict or no year in it."""
    year = old.get('year') if isinstance(old, dict) else None
    return year if isinstance(year, int) and not isinstance(year, bool) else None


def due(old, year):
    """True when the ballot of season year has not been held: no hof dict, or its year is below year."""
    last = held(old)
    return last is None or last < year


def run(old, year, careers, stem, updated):
    """The hof dict after the ballot of season year, from the old one (None or {} for the first). Everyone on the
    ballot with pct of INDUCT_PCT or more is inducted (year, and a story of None until one is written); under
    DROP_PCT is dropped; the rest are on the new ballot, and are dropped after it when their last ballot (year -
    retired == MAX_WAIT). The inducted list and the dropped pids carry over whole, and nobody in either is on a
    ballot again. An old dict already at year or later is returned as it is (a ballot is held once a season)."""
    if isinstance(old, dict) and not due(old, year):
        return old
    old = old if isinstance(old, dict) else {}
    inducted = [dict(e) for e in old.get('inducted') or [] if isinstance(e, dict) and isinstance(e.get('pid'), int)]
    dropped = [p for p in old.get('dropped') or [] if isinstance(p, int)]
    on_ballot = []
    for b in ballot(year, careers, {e['pid'] for e in inducted} | set(dropped)):
        if b['pct'] >= INDUCT_PCT:
            inducted.append({'pid': b['pid'], 'name': b['name'], 'kind': b['kind'], 'year': year,
                             'retired': b['retired'], 'score': b['score'], 'pct': b['pct'], 'line': b['line'],
                             'teams': b['teams'], 'story': None})
        elif b['pct'] < DROP_PCT:
            dropped.append(b['pid'])
        else:
            on_ballot.append({k: b[k] for k in ('pid', 'name', 'kind', 'retired', 'years_on', 'score', 'pct')})
            if year - b['retired'] >= MAX_WAIT:
                dropped.append(b['pid'])
    return {'stem': stem, 'updated': updated, 'year': year, 'inducted': inducted, 'ballot': on_ballot,
            'dropped': dropped}


def inducted_year(doc, pid):
    """The year pid was inducted according to an hof dict, or None: no dict, a pid that is not in its inducted list,
    or an entry with no int year."""
    entries = doc.get('inducted') if isinstance(doc, dict) else None
    for e in entries if isinstance(entries, list) else []:
        if isinstance(e, dict) and e.get('pid') == pid and type(e.get('pid')) is int:
            year = e.get('year')
            return year if type(year) is int else None
    return None


def story_key(year, pid):
    """The story's file key (and URL tail): '2036-1234' for hof/2036-1234.json."""
    return '%d-%d' % (year, pid)


def _rate(num, den):
    return feed._bare('%.3f' % (num / den))


def story_facts(entry, association):
    """What an induction story may say, from one inducted entry of the hof dict: the association, the player's name and
    kind, the induction year, the year he retired, his seasons, his teams in order, the career line (history.totals)
    and pct. A hitter with at-bats also has 'avg' ('.301'), a pitcher with outs has 'era' ('3.12') and 'ip'
    ('2411.1')."""
    line = dict(entry.get('line') or {})
    facts = {'association': association, 'name': entry['name'], 'kind': entry['kind'], 'year': entry['year'],
             'retired': entry['retired'], 'seasons': line.get('seasons', 0), 'teams': list(entry.get('teams') or []),
             'line': line, 'pct': entry['pct']}
    if entry['kind'] == 'bat' and line.get('ab'):
        facts['avg'] = _rate(line.get('h', 0), line['ab'])
    if entry['kind'] == 'pit' and line.get('outs'):
        facts['era'] = '%.2f' % (27 * line.get('er', 0) / line['outs'])
        facts['ip'] = recap.ip(line['outs'])
    return facts


def _plural(n, noun):
    return '%d %s' % (n, noun if n == 1 else noun + 's')


def _joined(items):
    """'A', 'A and B', 'A, B and C'."""
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def template(facts):
    """A story built only from the facts: a headline and two paragraphs (the career, then the numbers). Players are
    named again rather than given a pronoun; every number in it is a fact, so it passes recap.numbers_ok."""
    name, line = facts['name'], facts['line']
    head = '%s elected to the Hall of Fame' % name
    career = '%s was elected to the Hall of Fame in %d with %d%% of the vote.' % (name, facts['year'], facts['pct'])
    played = '%s played %s' % (name, _plural(facts['seasons'], 'season'))
    if facts['teams']:
        played += ' for ' + _joined(facts['teams'])
    career += ' %s and last appeared in %d.' % (played, facts['retired'])
    if facts['kind'] == 'bat':
        stats = [_plural(line.get('h', 0), 'hit'), _plural(line.get('hr', 0), 'home run'),
                 '%d RBI' % line.get('rbi', 0)]
        if 'avg' in facts:
            stats.append('a %s average' % facts['avg'])
        numbers = '%s finished with %s.' % (name, _joined(stats))
    else:
        numbers = '%s finished %d-%d' % (name, line.get('w', 0), line.get('l', 0))
        if 'era' in facts:
            numbers += ' with a %s ERA' % facts['era']
        numbers += ', %s and %s' % (_plural(line.get('so', 0), 'strikeout'), _plural(line.get('sv', 0), 'save'))
        if 'ip' in facts:
            numbers += ' over %s innings' % facts['ip']
        numbers += '.'
    return {'headline': head, 'body': career + '\n' + numbers}


def prompt(facts):
    """(system, user) for an induction story."""
    return SYSTEM, recap.facts_message(facts)


def write(facts, budget, complete, attempts=2):
    """An induction story from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, prompt, template, attempts)


def archive_years(data_dir, stem):
    """The seasons with a history archive for stem, ascending: the <year>.json files in <data_dir>/<STEM>/history. []
    for a stem that is not a valid one or no history folder."""
    if not isinstance(stem, str) or history.STEM_RE.fullmatch(stem) is None:
        return []
    try:
        names = os.listdir(os.path.join(data_dir, stem.upper(), 'history'))
    except OSError:
        return []
    return sorted(int(n[:4]) for n in names if history.SIM_FILE_RE.fullmatch(n))


def sim_index(data_dir, stem):
    """{'bat': {pid: rows}, 'pit': {pid: rows}} from every readable archive, each file read once: rows are what
    history.sim_seasons gives for that pid and kind (ascending, {'year', 'team', then the line's keys}). The Hall's
    ballot looks at thousands of players, where sim_seasons reads every file once for each of them. Unreadable or
    malformed files are skipped."""
    out = {'bat': {}, 'pit': {}}
    for year in archive_years(data_dir, stem):
        try:
            with open(history.archive_path(data_dir, stem, year), encoding='utf-8') as f:
                doc = json.load(f)
        except (OSError, ValueError, RecursionError):
            continue
        if not isinstance(doc, dict):
            continue
        teams = doc.get('team')
        for kind, keys in (('bat', history.BAT_KEYS), ('pit', history.PIT_KEYS)):
            lines = doc.get(kind)
            for key, line in (lines.items() if isinstance(lines, dict) else ()):
                if not isinstance(line, dict) or not key.isascii() or not key.isdigit() or str(int(key)) != key:
                    continue
                team = teams.get(key) if isinstance(teams, dict) else None
                out[kind].setdefault(int(key), []).append(
                    dict(year=year, team=team if isinstance(team, str) else '', **history._keep(line, keys)))
    return out
