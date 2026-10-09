"""Scouting reports for the news sidecar: one report per team, written once per association. Each names the team's best
hitters and pitchers, graded on the real-world 20-80 scouting scale from their ratings, with last season's numbers where
they qualify; the team page lists the whole roster. Pure functions over the dicts gamedata.py returns; the model is
reached only through the complete() callable the caller passes in. Prompt rules and the number check are recap's.
"""
import re

import feed
import recap
import season

HITTERS = 5             # hitters named in a report
PITCHERS = 4            # pitchers named in a report
MIN_AB = 100            # last season's line shown for a hitter with this many at-bats
MIN_OUTS = 60           # ... and for a pitcher with this many outs (20 innings)
SCALE = '20-80 scouting scale: 50 is average, 60 plus, 70 plus-plus, 80 the best'
SYSTEM = ("You are a baseball scout writing the spring report on one team for the newspaper: 120 to 200 words on its "
          "best hitters and pitchers, using the scouting grades and last season's numbers given. " + recap.RULES)
POSITION_ORDER = ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
SIDES = {'L': 'left', 'R': 'right', 'S': 'switch'}
YEAR = re.compile(r'[0-9]{4}(?= |\Z)')


def grade(rating):
    """A 0-99 rating on the 20-80 scale in steps of 5: 0 is 20, 50 is 50, 99 is 80. None stays None."""
    if rating is None:
        return None
    return 20 + 5 * round(min(max(rating, 0), 99) * 12 / 99)


def year_of(name):
    """The season year an association is named for ('1998 Major Leagues' -> 1998), or None."""
    m = YEAR.match(name)
    return int(m.group()) if m else None


def _age(born, year):
    return year - born if isinstance(born, int) and isinstance(year, int) else None


def _hand(p):
    """'L/R' from bats and throws; '' when neither is known, '?' for a side that is not."""
    if not p['bats'] and not p['throws']:
        return ''
    return '%s/%s' % (p['bats'] or '?', p['throws'] or '?')


def _position_rank(pos):
    return POSITION_ORDER.index(pos) if pos in POSITION_ORDER else len(POSITION_ORDER)


def roster(assoc, tid, players, year):
    """The team's whole roster for its page: {'hitters': [...], 'pitchers': [...]}. Hitters in position order, then name;
    pitchers best first by their control, strikeout and stamina grades, then name. Players not in `players` are
    skipped."""
    hitters, pitchers = [], []
    for pid in season._players(assoc).get(tid, []):
        if pid not in players:
            continue
        p = players[pid]
        age = _age(p['born'], year)
        if p['pos'] == 'P':
            pitchers.append({'pid': pid, 'name': p['name'], 'hand': _hand(p), 'age': age,
                             'control': grade(p['control']), 'strikeout': grade(p['strikeout']),
                             'stamina': grade(p['stamina']), 'fielding': grade(p['fielding'])})
        else:
            hitters.append({'pid': pid, 'name': p['name'], 'pos': p['pos'], 'hand': _hand(p), 'age': age,
                            'contact': grade(p['contact']), 'power': grade(p['power']),
                            'speed': grade(p['speed']), 'fielding': grade(p['fielding'])})
    hitters.sort(key=lambda h: (_position_rank(h['pos']), h['name']))
    pitchers.sort(key=lambda r: (-(r['control'] + r['strikeout'] + r['stamina']), r['name']))
    return {'hitters': hitters, 'pitchers': pitchers}


def _last_bat(line):
    """Last season's line for a hitter with MIN_AB at-bats, else None."""
    if not line or line['ab'] < MIN_AB:
        return None
    return {'avg': feed._bare('%.3f' % (line['h'] / line['ab'])), 'hr': line['hr'], 'rbi': line['rbi']}


def _last_pit(line):
    """Last season's line for a pitcher with MIN_OUTS outs, else None."""
    if not line or line['outs'] < MIN_OUTS:
        return None
    return {'w': line['w'], 'l': line['l'], 'era': '%.2f' % (line['er'] * 27 / line['outs']), 'so': line['so'],
            'sv': line['sv'], 'ip': recap.ip(line['outs'])}


def team_facts(assoc, tid, players, last, year):
    """What a report may say about one team: its name and setting, the scale, and its best hitters and pitchers (by
    grades, first HITTERS and PITCHERS), each with last season's line where it qualifies."""
    t = assoc['teams'][tid]
    rost = roster(assoc, tid, players, year)
    hitters = sorted(rost['hitters'], key=lambda h: (-(h['contact'] + h['power'] + h['speed']), h['name']))
    return {
        'association': assoc['name'], 'team': t['name'], 'manager': t['manager'], 'stadium': t['stadium'],
        'league': t['league'], 'division': t['division'], 'scale': SCALE,
        'hitters': [{'name': h['name'], 'pos': h['pos'], 'bats': SIDES.get(players[h['pid']]['bats'], ''),
                     'age': h['age'], 'contact': h['contact'], 'power': h['power'], 'speed': h['speed'],
                     'fielding': h['fielding'], 'last': _last_bat(last['bat'].get(h['pid']))}
                    for h in hitters[:HITTERS]],
        'pitchers': [{'name': r['name'], 'throws': SIDES.get(players[r['pid']]['throws'], ''), 'age': r['age'],
                      'control': r['control'], 'strikeout': r['strikeout'], 'stamina': r['stamina'],
                      'last': _last_pit(last['pit'].get(r['pid']))}
                     for r in rost['pitchers'][:PITCHERS]],
    }


def _plural(n, noun):
    return '%d %s' % (n, noun if n == 1 else noun + 's')


def _hitter_text(h):
    who = '%s (%s)' % (h['name'], h['pos']) if h['pos'] else h['name']
    text = '%s grades %d for contact, %d for power and %d for speed.' % (who, h['contact'], h['power'], h['speed'])
    if h['last']:
        s = h['last']
        text += ' %s hit %s with %s and %d RBI last season.' % (h['name'], s['avg'], _plural(s['hr'], 'home run'),
                                                              s['rbi'])
    return text


def _pitcher_text(p):
    text = '%s grades %d for control, %d for strikeout stuff and %d for stamina.' % (
        p['name'], p['control'], p['strikeout'], p['stamina'])
    if p['last']:
        s = p['last']
        text += ' %s went %d-%d with a %s ERA last season.' % (p['name'], s['w'], s['l'], s['era'])
    return text


def template(facts):
    """A report built only from the facts: one paragraph on the hitters, one on the pitchers. Players are named again
    rather than given a pronoun."""
    name = facts['team']
    hitters = (' '.join(_hitter_text(h) for h in facts['hitters'])
               or 'No hitters on the roster of %s are on file.' % name)
    pitchers = (' '.join(_pitcher_text(p) for p in facts['pitchers'])
                or 'No pitchers on the roster of %s are on file.' % name)
    return {'headline': 'Scouting the %s' % name, 'body': '\n'.join([hitters, pitchers])}


def prompt(facts):
    """(system, user) for a scouting report."""
    return SYSTEM, recap.facts_message(facts)


def write(facts, budget, complete, attempts=2):
    """A scouting report from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, prompt, template, attempts)
