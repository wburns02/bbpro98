"""The rookie class of a season for the news sidecar: who is new to the league, written once per season. A player is
new when his (pid, name, birth year) is not in the previous season's snapshot, since the game can reuse a pid. The
column names the best newcomers, hitters and pitchers, graded on the real-world 20-80 scouting scale from their
ratings. Pure functions over the dicts gamedata.py returns; the model is reached only through the complete() callable
the caller passes in. Prompt rules and the number check are recap's.
"""
import recap
import scout
import season

TOP = 6                 # hitters and pitchers named in the column, each
FREE_AGENT = 'free agent'
GRADES = ('contact', 'power', 'speed', 'fielding', 'control', 'strikeout', 'stamina')
SYSTEM = ("You are a baseball writer for the newspaper covering the newcomers to the league this season: 120 to 200 "
          "words on the rookie class, naming only the players given and using the scouting grades given. " + recap.RULES)
POSITIONS = {'C': 'catcher', '1B': 'first baseman', '2B': 'second baseman', '3B': 'third baseman', 'SS': 'shortstop',
             'LF': 'left fielder', 'CF': 'center fielder', 'RF': 'right fielder'}


def snapshot(players):
    """What the next season compares against: {'ids': [[pid, name, born], ...]} for every player, sorted by pid."""
    return {'ids': sorted([pid, p['name'], p['born']] for pid, p in players.items())}


def _known(prev):
    """The set of (pid, name, born) in a snapshot, or None when it is no baseline: not a dict, ids not a list, or ids
    with rows but none of them well formed. Rows that are not 3-item lists are skipped."""
    ids = prev.get('ids') if isinstance(prev, dict) else None
    if not isinstance(ids, list):
        return None
    known = set()
    for row in ids:
        if isinstance(row, list) and len(row) == 3:
            try:
                known.add(tuple(row))
            except TypeError:
                pass
    return known if known or not ids else None


def newcomers(players, prev):
    """Sorted pids in `players` whose [pid, name, born] is not in the previous snapshot. [] without a baseline."""
    known = _known(prev)
    if known is None:
        return []
    return sorted(pid for pid, p in players.items() if (pid, p['name'], p['born']) not in known)


def _age(born, year):
    return year - born if isinstance(born, int) and isinstance(year, int) else None


def class_facts(assoc, players, pids, year):
    """What the column may say: the association and season, the scale, the size of the class, and its hitters and
    pitchers (all of them, best first by the sum of their grades, then name). Pids not in `players` are skipped."""
    pids = list(pids)
    teams = {pid: assoc['teams'][tid]['name'] for tid, ps in season._players(assoc).items() for pid in ps}
    hitters, pitchers = [], []
    for pid in pids:
        if pid not in players:
            continue
        p = players[pid]
        who = {'pid': pid, 'name': p['name'], 'age': _age(p['born'], year), 'team': teams.get(pid, FREE_AGENT)}
        if p['pos'] == 'P':
            pitchers.append(dict(who, throws=scout.SIDES.get(p['throws'], ''), control=scout.grade(p['control']),
                                 strikeout=scout.grade(p['strikeout']), stamina=scout.grade(p['stamina'])))
        else:
            hitters.append(dict(who, pos=p['pos'], bats=scout.SIDES.get(p['bats'], ''),
                                contact=scout.grade(p['contact']), power=scout.grade(p['power']),
                                speed=scout.grade(p['speed']), fielding=scout.grade(p['fielding'])))
    for rows in (hitters, pitchers):
        rows.sort(key=lambda r: (-sum(v for k, v in r.items() if k in GRADES and v is not None), r['name']))
    return {'association': assoc['name'], 'season': year, 'scale': scout.SCALE, 'count': len(pids),
            'hitters': hitters, 'pitchers': pitchers}


def headline_facts(facts):
    """The facts the model writes from: the first TOP hitters and pitchers."""
    return dict(facts, hitters=facts['hitters'][:TOP], pitchers=facts['pitchers'][:TOP])


def _and(parts):
    """'a', 'a and b', 'a, b and c'."""
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


def _grades(r, labels):
    """'grades 60 for contact, 45 for power and 70 for speed', leaving out a grade that is missing; '' when none."""
    parts = ['%d for %s' % (r[key], label) for key, label in labels if r.get(key) is not None]
    return 'grades ' + _and(parts) if parts else ''


def bio(r):
    """One plain sentence on a rookie, from its own dict: age, side, position, team, then the grades for what the
    rookie does. A missing age or side is left out."""
    if 'control' in r:
        side = {'left': 'left-handed', 'right': 'right-handed', 'switch': 'switch-throwing'}.get(r.get('throws'), '')
        role = ' '.join(w for w in (side, 'pitcher') if w)
        grades = _grades(r, (('control', 'control'), ('strikeout', 'strikeout stuff'), ('stamina', 'stamina')))
    else:
        side = {'left': 'left-handed hitting', 'right': 'right-handed hitting', 'switch': 'switch-hitting'}.get(
            r.get('bats'), '')
        role = ' '.join(w for w in (side, POSITIONS.get(r.get('pos'), 'player')) if w)
        grades = _grades(r, (('contact', 'contact'), ('power', 'power'), ('speed', 'speed')))
    team = r.get('team')
    where = ''
    if team == FREE_AGENT:
        where = ' and free agent'
    elif team:
        where = ' for the ' + team
    head = '%s, %d,' % (r['name'], r['age']) if r.get('age') is not None else r['name'] + ','
    sentence = '%s a %s%s' % (head, role, where)
    return sentence + (', ' + grades if grades else '') + '.'


def template(facts):
    """A column built only from the facts: the size of the class, then the best hitters, then the best pitchers."""
    s = facts['season']
    when = ' in %d' % s if isinstance(s, int) else ''
    n = facts['count']
    count = ('%d new player%s joined the league%s.' % (n, '' if n == 1 else 's', when) if n
             else 'No new players joined the league%s.' % when)
    top = headline_facts(facts)
    hitters = ' '.join([count] + [bio(h) for h in top['hitters']])
    pitchers = ' '.join(bio(p) for p in top['pitchers'])
    return {'headline': 'The rookie class of %d' % s if isinstance(s, int) else 'The rookie class',
            'body': '\n'.join(part for part in (hitters, pitchers) if part)}


def prompt(facts):
    """(system, user) for the rookie column."""
    return SYSTEM, recap.facts_message(facts)


def write(facts, budget, complete, attempts=2):
    """The rookie column from the model, or the template when it cannot give one that checks out."""
    return recap.draft(headline_facts(facts), budget, complete, prompt, template, attempts)
