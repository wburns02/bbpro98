"""Roster moves and milestones for the league news: what changed between two scans of the game's files (a player signed,
released, moved, retired or created) and which career or season totals crossed a round number. Pure functions over the
dicts gamedata.py returns, as scout.py is; the model is reached only through the complete() callable the caller passes
in. Prompt rules and the number check are recap's.

A snapshot is a plain dict: 'year' (the association's season), 'where' (tid, 0 for a free agent, -1 for retired), and
'names', 'born', 'pos', 'career', 'season', all keyed by player id as a decimal string.
"""
import recap
import scout

CAREER = {'hr': (300, 400, 500, 600, 700), 'h': (2000, 2500, 3000), 'sb': (300, 500), 'w': (200, 250, 300),
          'sv': (300, 400), 'so_p': (2000, 2500, 3000)}
SEASON = {'hr': (40, 50, 60), 'h': (200,), 'sb': (50, 75, 100), 'w': (20, 25), 'sv': (40, 50), 'so_p': (250, 300)}
RETIRED = {'hr': 200, 'h': 1500, 'w': 150, 'sv': 200}       # a retirement is notable at these career totals
STAT_NAMES = {'hr': 'home run', 'h': 'hit', 'sb': 'stolen base', 'w': 'win', 'sv': 'save', 'so_p': 'strikeout'}
FREE_AGENTS = 'Free agents'
SYSTEM = ("You are a newspaper baseball writer covering the association's roster moves. Write a wire note of two or "
          "three sentences on the one move or milestone in the facts. " + recap.RULES)


def _age(born, year):
    return year - born if type(born) is int and type(year) is int else None


def _totals(lines, pid):
    """One player's career or season totals from a season_lines() result, or None when he has no line."""
    bat, pit = lines['bat'].get(pid), lines['pit'].get(pid)
    if bat is None and pit is None:
        return None
    bat, pit = bat or {}, pit or {}
    return {'hr': bat.get('hr', 0), 'h': bat.get('h', 0), 'rbi': bat.get('rbi', 0), 'sb': bat.get('sb', 0),
            'w': pit.get('w', 0), 'sv': pit.get('sv', 0), 'so_p': pit.get('so', 0)}


def _where(teams, tid):
    """A snapshot's 'where' as a name: a team's name, 'Free agents' for 0, '' for retired (-1)."""
    if tid == 0:
        return FREE_AGENTS
    return teams[tid]['name'] if tid > 0 and tid in teams else ''


def _passed(before, now, marks):
    """The highest mark a total went past going from before to now, or None."""
    passed = [m for m in marks if before < m <= now]
    return max(passed) if passed else None


def snapshot(assoc, players, fa_ids, career, season):
    """The league's players as a JSON-able dict. Every player in `players` (id 100 and up) has a where, a name, a birth
    year (or None) and a position; 'career' and 'season' hold the totals of those with a line. 'year' is the season: the
    ASN's season date, else the year the name starts with (None when neither)."""
    rostered = {}
    for tid in sorted(assoc['teams']):
        for pid in assoc['teams'][tid]['roster']:
            rostered.setdefault(pid, tid)
    year = assoc.get('season_year')
    if type(year) is not int:
        year = scout.year_of(assoc['name'])
    snap = {'year': year, 'where': {}, 'names': {}, 'born': {}, 'pos': {}, 'career': {}, 'season': {}}
    for pid in sorted(players):
        if pid < 100:
            continue
        key, p = str(pid), players[pid]
        snap['where'][key] = rostered.get(pid, 0 if pid in fa_ids else -1)
        snap['names'][key], snap['born'][key], snap['pos'][key] = p['name'], p['born'], p['pos']
        for scope, lines in (('career', career), ('season', season)):
            line = _totals(lines, pid)
            if line is not None:
                snap[scope][key] = line
    return snap


def diff(prev, cur, teams, same_season=True):
    """The events from the snapshot prev to cur, in a stable order (kind, then team, then name). With no prev (the first
    snapshot) there are none. Season totals are compared only when same_season;
    across a rollover the stats file can still hold last season's lines, so that step reports no season milestones.
    A milestone is the highest mark a total crossed in this step."""
    if prev is None:
        return []
    year, out = cur['year'], []
    for key in sorted(cur['where'], key=int):
        pid, now, was = int(key), cur['where'][key], prev['where'].get(key)
        base = {'pid': pid, 'name': cur['names'].get(key, ''), 'pos': cur['pos'].get(key, ''),
                'age': _age(cur['born'].get(key), year)}
        if was is None:
            if now >= 0:
                out.append(dict(base, kind='new', **{'from': '', 'to': _where(teams, now)}))
        elif was != now:
            kind = None
            if was == 0 and now > 0:
                kind = 'signed'
            elif was > 0 and now == 0:
                kind = 'released'
            elif was > 0 and now > 0:
                kind = 'moved'
            elif was >= 0 and now == -1:
                kind = 'retired'
            if kind:
                out.append(dict(base, kind=kind, **{'from': _where(teams, was), 'to': _where(teams, now)}))
        scopes = [('career', CAREER, cur['career'], prev['career'])]
        if same_season:     # across a rollover the stats file may still hold last season's lines: no season marks
            scopes.append(('season', SEASON, cur['season'], prev['season']))
        for scope, marks, lines, before in scopes:
            now_line, was_line = lines.get(key, {}), before.get(key, {})
            for stat, table in marks.items():
                mark = _passed(was_line.get(stat, 0), now_line.get(stat, 0), table)
                if mark is not None:
                    out.append(dict(base, kind='milestone', stat='%s %s' % (scope, stat), value=mark,
                                    total=now_line[stat], **{'from': '', 'to': _where(teams, now)}))
    out.sort(key=_sort_key)
    return out


def _sort_key(e):
    team = e['from'] if e['kind'] in ('released', 'retired') else e['to']
    return (e['kind'], team, e['name'], e['pid'], e.get('stat', ''))


def notable(event, players_now):
    """Whether an event gets a note: any milestone, or a retirement at a career total in RETIRED. players_now is the
    current snapshot, which holds the career totals."""
    if event['kind'] == 'milestone':
        return True
    if event['kind'] != 'retired':
        return False
    career = players_now['career'].get(str(event['pid']), {})
    return any(career.get(stat, 0) >= n for stat, n in RETIRED.items())


def date_text(last):
    """'June 3' for the last played day, a (month, day) pair, or 'Offseason' when no game is played yet."""
    return recap.date_text(*last) if last else 'Offseason'


def facts(event, assoc_name, date, career=None):
    """What a note may say: the event, the association and date, and the player's career totals when given."""
    out = {'association': assoc_name, 'date': date, 'kind': event['kind'], 'name': event['name'],
           'pos': event['pos'], 'age': event['age'], 'from': event['from'], 'to': event['to']}
    if event['kind'] == 'milestone':
        out.update(stat=event['stat'], value=event['value'], total=event['total'])
    if career is not None:
        out['career'] = career
    return out


def _who(f):
    """'Pat Smith (SS, 27)': the name, with the position and age where known."""
    bits = [f['pos']] if f.get('pos') else []
    if type(f.get('age')) is int:
        bits.append(str(f['age']))
    return '%s (%s)' % (f.get('name', ''), ', '.join(bits)) if bits else f.get('name', '')


def _plural(n, word):
    return '%d %s' % (n, word if n == 1 else word + 's')


def _milestone(f):
    """'reached 500 career home runs' or 'reached 40 home runs this season'."""
    scope, _, key = f['stat'].partition(' ')
    word = STAT_NAMES[key]
    if scope == 'season':
        return 'reached %d %ss this season' % (f['value'], word)
    return 'reached %d career %ss' % (f['value'], word)


def template(facts):
    """A note built only from the facts: a headline and one or two sentences. Players are named again, not given a
    pronoun."""
    name, to, frm, who = facts.get('name', ''), facts.get('to', ''), facts.get('from', ''), _who(facts)
    kind = facts.get('kind', '')
    if kind == 'signed':
        head, body = '%s signs with %s' % (name, to), '%s signed with %s from the free agents.' % (who, to)
    elif kind == 'released':
        head = '%s is released by %s' % (name, frm)
        body = '%s was released by %s and is a free agent.' % (who, frm)
    elif kind == 'moved':
        head, body = '%s moves to %s' % (name, to), '%s moved from %s to %s.' % (who, frm, to)
    elif kind == 'retired':
        head, body = '%s retires' % name, '%s has retired.' % who
        career = facts.get('career') or {}
        totals = [_plural(career[s], STAT_NAMES[s]) for s in ('hr', 'h', 'w', 'sv') if career.get(s)]
        if totals:
            body += ' The career totals are %s.' % ', '.join(totals)
    elif kind == 'new':
        head = '%s enters the league' % name
        body = '%s is new to the league and is listed with %s.' % (who, to)
    else:
        phrase = _milestone(facts)
        head = '%s %s' % (name, phrase)
        body = '%s is with %s and has %s.' % (who, to, phrase) if to else '%s has %s.' % (who, phrase)
    return {'headline': head, 'body': body}


def prompt(facts):
    """(system, user) for a note."""
    return SYSTEM, recap.facts_message(facts)


def write(facts, budget, complete, attempts=2):
    """A note from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, prompt, template, attempts)
