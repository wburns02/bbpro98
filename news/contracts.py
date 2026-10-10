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
# The mean MLB salary before the table's first season (the Lahman salaries start in 1985), in dollars: MLBPA figures
# from 1967 on, and rounded historical estimates before that. Years between two anchors take the geometric line.
HISTORY = ((1871, 1500), (1900, 2000), (1910, 3000), (1920, 5000), (1930, 7000), (1935, 6000), (1946, 11000),
           (1950, 13000), (1960, 17000), (1967, 19000), (1970, 29303), (1975, 44676), (1977, 76066), (1980, 143756),
           (1984, 329408))
GROWTH = 1.03           # a year, after the table's last season
NEGRO_PAY = 0.25        # a Negro Leagues season pays this share of the same year's MLB level


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


def level(table, year):
    """The mean salary, in dollars, a league of that year is priced to: the table's 'means' for its own seasons (the
    nearest year below for a missing one), growing GROWTH a year after them, and HISTORY's geometric line before them,
    joined to the table's first season. None when the table has no 'means'."""
    known = {int(y): v for y, v in (table.get('means') or {}).items()}
    if not known:
        return None
    first, last = min(known), max(known)
    if year > last:
        return known[last] * GROWTH ** (year - last)
    if year >= first:
        return float(known[max(y for y in known if y <= year)])
    anchors = [a for a in HISTORY if a[0] < first] + [(first, known[first])]
    if year <= anchors[0][0]:
        return float(anchors[0][1])
    for (y0, v0), (y1, v1) in zip(anchors, anchors[1:]):
        if y0 <= year <= y1:
            return v0 * (v1 / v0) ** ((year - y0) / (y1 - y0))
    return float(anchors[-1][1])


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


def _ranks(players):
    """{pid: (rank0, n)}: each player's 0-based rank from the worst within his role by rating index (ties to the lower
    pid), and the size of the role."""
    groups = {'bat': [], 'pit': []}
    for pid, p in players.items():
        groups[role(p)].append((_index(p), pid))
    out = {}
    for group in groups.values():
        group.sort()
        for rank0, (_, pid) in enumerate(group):
            out[pid] = (rank0, len(group))
    return out


def deciles(players):
    """{pid: 1..10} from every player's rating index, ranked within role; 1 is the worst, 10 the best. Ties go to the
    lower pid. A role of one player gives him decile 1."""
    return {pid: _decile(rank0, n) for pid, (rank0, n) in _ranks(players).items()}


def _place(rank0, n):
    """(decile, frac): the decile and how far up it the player sits, 0 at its bottom to 1 at its top."""
    d = _decile(rank0, n)
    return d, min(1.0, max(0.0, 10.0 * rank0 / n - (d - 1)))


def service(age):
    """Seasons of service at an age: from 22 on, one a year. None counts 0."""
    return 0 if age is None else max(0, age - 22)


def class_of(service):
    """pre below 3 seasons, arb below 6, fa from 6."""
    return 'pre' if service < 3 else 'arb' if service < 6 else 'fa'


def _ratio(cells, decile, frac):
    """The salary ratio at a place in the table: each cell holds the ratio at the middle of its decile (frac 0.5), and a
    place between two middles takes the straight line between them. Below the first middle it is the first cell; above
    the last it climbs to twice the last cell at the very top, as the best-paid stars do."""
    x = decile - 1 + frac - 0.5
    if x <= 0:
        return cells[0]
    if x >= 9:
        return cells[9] * (1 + 2 * (x - 9))
    i = int(x)
    return cells[i] + (x - i) * (cells[i + 1] - cells[i])


def _raw(table, role, cls, decile, year, frac=0.5):
    """A salary before rounding: the ratio at the place times the year's median, a pre-arbitration one never below
    PRE_FLOOR of the median."""
    median = scale(table, year)
    base = _ratio(table['ratio'][role][cls], decile, frac) * median
    return max(base, PRE_FLOOR * median) if cls == 'pre' else base


def _round(dollars):
    """To the nearest 100 under 10,000 (never below 100: an early or Negro Leagues salary can be a few hundred dollars),
    the nearest 1000 under a million, and the nearest 10,000 from a million up."""
    step = 100 if dollars < 10000 else 1000 if dollars < 1000000 else 10000
    return max(100, int(round(dollars / step)) * step)


def salary(table, role, cls, decile, year, frac=0.5):
    """A salary in dollars: the table's ratio for the role, class and place (decile, and frac up it; 0.5 is the decile's
    own cell) times the year's league median. A pre-arbitration salary is never below 0.3 of the median. Rounded as
    _round does."""
    return _round(_raw(table, role, cls, decile, year, frac))


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


def _active(assoc):
    """Every pid on an active roster (a team's 'active', or its whole roster when the team has none)."""
    return {pid for team in assoc['teams'].values() for pid in team.get('active', team['roster'])}


def _elapsed(prev, year):
    """Seasons since the previous state's season: 0 unless both are whole years and this one is later."""
    was = prev['season_year'] if prev is not None else None
    return year - was if type(was) is int and type(year) is int and year > was else 0


def _age(player, year):
    return None if player['born'] is None else year - player['born']


def _event(kind, pid, player, tid, pay, years, year):
    return {'kind': kind, 'pid': pid, 'name': player['name'], 'team': tid, 'salary': pay, 'years': years, 'year': year}


def _priced(player, age, year, place, table):
    """(class, raw salary) of a new contract for a player of that age at that place."""
    cls = class_of(service(age))
    return cls, _raw(table, role(player), cls, place[0], year, place[1])


def _factor(table, year, raws, pay):
    """What every new salary of this pass is multiplied by: pay, times the ratio that brings the mean of raws (the raw
    salary of every active player) to level(year). Just pay when the table has no 'means' or there are no raws."""
    target = level(table, year)
    if target is None or not raws:
        return pay
    return pay * target * len(raws) / sum(raws)


def _signing(player, tid, age, year, place, table, factor):
    cls, raw = _priced(player, age, year, place, table)
    years = years_for(cls, age, place[0])
    return {'team': tid, 'salary': _round(raw * factor), 'years': years, 'left': years,
            'signed': year, 'class': cls, 'name': player['name'], 'pos': player['pos'], 'age': age}


def update(prev, assoc, players, year, table, pay=1.0):
    """The contract state after this pass: {'season_year', 'contracts', 'events'}. prev is the last state or None; it is
    never changed. With no season year (year None) it returns prev, or an empty state when there is none.

    A rostered player with a contract still running keeps it, counted down by the seasons elapsed, on his current team
    (a 'moved' event when the team changed), even when he has been sent down to the reserves. A player on an active
    roster whose contract has run out signs a new one ('re-signed'); one with no contract signs one ('signed'). A
    reserve with no running contract has none: minor league pay is not priced. Within a decile the salary rises with
    the player's place in it, so the best players are not all paid the same. When the table has 'means', new salaries
    are scaled so the active players' mean comes to level(year); pay scales them again (NEGRO_PAY for a Negro Leagues
    season). No signing is logged on the first pass
    (prev None, or the empty state of a pass with no season year): opening contracts are not news. A player who had a
    contract and is still in the league but on no roster is 'released'. Events are added in ascending pid order and
    only the last EVENT_KEEP are kept."""
    if year is None:
        return prev if prev is not None else {'season_year': None, 'contracts': {}, 'events': []}
    old = prev['contracts'] if prev is not None else {}
    opened = prev is not None and prev['season_year'] is not None    # else this is the league's first priced pass
    elapsed = _elapsed(prev, year)
    ranks = _ranks(players)
    rostered, active = _rostered(assoc, players), _active(assoc)
    places = {pid: _place(*ranks[pid]) for pid in rostered if pid in active}
    factor = _factor(table, year, [_priced(players[pid], _age(players[pid], year), year, place, table)[1]
                                   for pid, place in places.items()], pay)
    contracts, news = {}, []
    for pid, tid in rostered.items():
        p = players[pid]
        age = _age(p, year)
        kept = old.get(str(pid))
        if kept is not None and kept['left'] - elapsed >= 1:
            c = dict(kept, team=tid, left=kept['left'] - elapsed, name=p['name'], pos=p['pos'], age=age)
            if kept['team'] != tid:
                news.append(_event('moved', pid, p, tid, 0, 0, year))
        elif pid in active:
            c = _signing(p, tid, age, year, places[pid], table, factor)
            if opened:
                news.append(_event('re-signed' if kept is not None else 'signed', pid, p, tid, c['salary'],
                                   c['years'], year))
        else:
            continue        # a reserve with no running contract is on a minor league deal, which is not priced here
        contracts[str(pid)] = c
    for key in old:
        pid = int(key) if key.isdigit() else None       # a key this module never wrote is no player
        if key not in contracts and pid in players and pid not in rostered:
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
