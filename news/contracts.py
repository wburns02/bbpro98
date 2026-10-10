"""Contracts for the league news: each rostered player's salary and years, priced from the salary table (work/lahman/
salarytable.py, fitted on the real Lahman salaries of 1985 to 2016) and ticked down at each season rollover. The game
has no money; this is display only, and nothing here writes a game file. Pure functions over the dicts gamedata.py
returns; standard library only.
"""
import json

CLASSES = ('pre', 'arb', 'fa')
EVENT_KEEP = 100        # events kept in a state
PRE_FLOOR = 0.3         # a pre-arbitration salary is never below this share of the league median
MIN_SCALE = 3000.0      # the league median is never below this many dollars


def load_table(path):
    """The salary table, as json.load gives it. ValueError when it is not an object with 'years' (year to median dollars,
    at least one) and 'ratio' (ten numbers for each class of 'bat' and 'pit')."""
    with open(path, encoding='utf-8') as fh:
        table = json.load(fh)
    if not isinstance(table, dict):
        raise ValueError('%s: not an object' % path)
    years = table.get('years')
    if not isinstance(years, dict) or not years or not all(_int_key(y) and _number(v) for y, v in years.items()):
        raise ValueError('%s: no years of medians' % path)
    ratio = table.get('ratio')
    if not isinstance(ratio, dict) or not all(
            isinstance(ratio.get(role), dict) and isinstance(ratio[role].get(cls), list)
            and len(ratio[role][cls]) == 10 and all(_number(v) for v in ratio[role][cls])
            for role in ('bat', 'pit') for cls in CLASSES):
        raise ValueError('%s: no ratio for every role and class' % path)
    return table


def _number(v):
    return type(v) in (int, float)


def _int_key(k):
    return isinstance(k, str) and k.isdigit()


def scale(table, year):
    """The league median salary in dollars for that year. Inside the table's years it is the year's median, or the
    nearest year below when that year is missing. After the last year it grows 3% a year; before the first it shrinks
    7% a year. Never below 3000."""
    known = {int(y): v for y, v in table['years'].items()}
    first, last = min(known), max(known)
    if year > last:
        base = known[last] * 1.03 ** (year - last)
    elif year < first:
        base = known[first] * 0.93 ** (first - year)
    else:
        base = known[max(y for y in known if y <= year)]
    return max(MIN_SCALE, float(base))


def role(player):
    """'pit' for a pitcher (position P), else 'bat'."""
    return 'pit' if player['pos'] == 'P' else 'bat'


def _index(player):
    """A player's rating index: a batter's contact, power and speed/4 and fielding/4 (None counts 0); a pitcher's
    control, strikeout and stamina/4."""
    if role(player) == 'pit':
        return player['control'] + player['strikeout'] + player['stamina'] / 4
    return player['contact'] + player['power'] + player['speed'] / 4 + (player['fielding'] or 0) / 4


def _decile(rank0, n):
    """1..10 from a 0-based rank counted from the worst of n: min(10, 1 + int(10 * rank0 / n))."""
    return min(10, 1 + 10 * rank0 // n)


def deciles(players):
    """{pid: 1..10} from every player's rating index, ranked within role; 1 is the worst, 10 the best. Ties go to the
    lower pid. A role of one player gives him decile 1."""
    groups = {'bat': [], 'pit': []}
    for pid, p in players.items():
        groups[role(p)].append((_index(p), pid))
    out = {}
    for group in groups.values():
        group.sort()
        for rank0, (_, pid) in enumerate(group):
            out[pid] = _decile(rank0, len(group))
    return out


def service(age):
    """Seasons of service at an age: from 22 on, one a year. None counts 0."""
    return 0 if age is None else max(0, age - 22)


def class_of(service):
    """pre below 3 seasons, arb below 6, fa from 6."""
    return 'pre' if service < 3 else 'arb' if service < 6 else 'fa'


def salary(table, role, cls, decile, year):
    """A salary in dollars: the table's ratio for the role, class and decile times the year's league median. A
    pre-arbitration salary is never below 0.3 of the median. Rounded to the nearest 1000 under a million, and to the
    nearest 10,000 from a million up."""
    median = scale(table, year)
    base = table['ratio'][role][cls][decile - 1] * median
    if cls == 'pre':
        base = max(base, PRE_FLOOR * median)
    step = 1000 if base < 1000000 else 10000
    return int(round(base / step)) * step


def years_for(cls, age, decile):
    """Years on a new contract: 1 before free agency. A free agent's from his age (None counts 30): 5 through 28, 4 at
    29-30, 3 at 31-32, 2 at 33-34, 1 from 35. At most 2 for a decile of 5 or less."""
    if cls != 'fa':
        return 1
    age = 30 if age is None else age
    years = 5 if age <= 28 else 4 if age <= 30 else 3 if age <= 32 else 2 if age <= 34 else 1
    return min(years, 2) if decile <= 5 else years


def money(dollars):
    """'$850K', '$4.5M', '$62M'; under $10,000 the whole dollars, as '$9,500'."""
    if dollars < 10000:
        return '$%s' % format(int(dollars), ',')
    if dollars < 1000000:
        return '$%dK' % round(dollars / 1000)
    text = '%.1f' % (dollars / 1e6)
    return '$%sM' % (text[:-2] if text.endswith('.0') else text)


def _rostered(assoc, players):
    """{pid: tid} for every rostered pid that is in players: ascending tid, then roster order. A pid on two rosters keeps
    the first."""
    out = {}
    for tid in sorted(assoc['teams']):
        for pid in assoc['teams'][tid]['roster']:
            if pid in players:
                out.setdefault(pid, tid)
    return out


def _elapsed(prev, year):
    """Seasons since the previous state's season: 0 unless both are whole years and this one is later."""
    was = prev['season_year'] if prev is not None else None
    return year - was if type(was) is int and type(year) is int and year > was else 0


def _event(kind, pid, player, tid, pay, years, year):
    return {'kind': kind, 'pid': pid, 'name': player['name'], 'team': tid, 'salary': pay, 'years': years, 'year': year}


def _signing(player, tid, age, year, decile, table):
    cls = class_of(service(age))
    years = years_for(cls, age, decile)
    return {'team': tid, 'salary': salary(table, role(player), cls, decile, year), 'years': years, 'left': years,
            'signed': year, 'class': cls, 'name': player['name'], 'pos': player['pos'], 'age': age}


def update(prev, assoc, players, year, table):
    """The contract state after this pass: {'season_year', 'contracts', 'events'}. prev is the last state or None; it is
    never changed. With no season year (year None) it returns prev, or an empty state when there is none.

    A rostered player with a contract still running keeps it, counted down by the seasons elapsed, on his current team
    (a 'moved' event when the team changed). One whose contract has run out signs a new one ('re-signed'); one with no
    contract signs one ('signed'). No signing is logged on the first pass, when prev is None: opening contracts are not
    news. A player who had a contract and is still in the league but not rostered is 'released'. Events are added in
    ascending pid order and only the last EVENT_KEEP are kept."""
    if year is None:
        return prev if prev is not None else {'season_year': None, 'contracts': {}, 'events': []}
    old = prev['contracts'] if prev is not None else {}
    elapsed = _elapsed(prev, year)
    dec = deciles(players)
    contracts, news = {}, []
    for pid, tid in _rostered(assoc, players).items():
        p = players[pid]
        age = None if p['born'] is None else year - p['born']
        kept = old.get(str(pid))
        if kept is not None and kept['left'] - elapsed >= 1:
            c = dict(kept, team=tid, left=kept['left'] - elapsed, name=p['name'], pos=p['pos'], age=age)
            if kept['team'] != tid:
                news.append(_event('moved', pid, p, tid, 0, 0, year))
        else:
            c = _signing(p, tid, age, year, dec[pid], table)
            if prev is not None:
                news.append(_event('re-signed' if kept is not None else 'signed', pid, p, tid, c['salary'],
                                   c['years'], year))
        contracts[str(pid)] = c
    for key in old:
        pid = int(key)
        if key not in contracts and pid in players:
            news.append(_event('released', pid, players[pid], None, 0, 0, year))
    news.sort(key=lambda e: e['pid'])
    events = (list(prev['events']) if prev is not None else []) + news
    return {'season_year': year, 'contracts': contracts, 'events': events[-EVENT_KEEP:]}


def payroll(contracts, teams):
    """One row per team: its players, total and average salary (0 with no players), and top salary. Sorted by total, then
    tid."""
    rows = []
    for tid in teams:
        pays = [c['salary'] for c in contracts.values() if c['team'] == tid]
        total = sum(pays)
        rows.append({'tid': tid, 'name': teams[tid]['name'], 'players': len(pays), 'total': total,
                     'average': total // len(pays) if pays else 0, 'top': max(pays) if pays else 0})
    return sorted(rows, key=lambda r: (-r['total'], r['tid']))
