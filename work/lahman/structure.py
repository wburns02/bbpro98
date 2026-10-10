"""League shapes: which template fits a season's real leagues, and where each team goes.

plan() only reads the teams() rows it is given. It never touches a database and never changes its input.
"""

from itertools import permutations

SHAPES = {
    'T8': [[8]],
    'T10': [[10]],
    'T12': [[6, 6]],
    'T14_77': [[7, 7]],
    'T14_554': [[5, 5, 4]],
    'T16_2L': [[8], [8]],
    'T18': [[8], [10]],
    'T20': [[10], [10]],
    'T22': [[10], [6, 6]],
    'T24_2x12': [[6, 6], [6, 6]],
    'T24_3x8': [[8], [8], [8]],
    'T26_12_14': [[6, 6], [7, 7]],
    'T26_8_8_10': [[8], [8], [10]],
    'T28_77': [[7, 7], [7, 7]],
    'T28_554': [[5, 5, 4], [5, 5, 4]],
    'T30': [[5, 5, 4], [8, 8]],
    'T34': [[10], [6, 6], [6, 6]],
}

EAST = ('BLN', 'BRO', 'BSN', 'NY1', 'PHI', 'WAS')
DIV_RANK = {'E': 0, 'C': 1, 'W': 2}


def plan(teams, year):
    year = int(year)
    rows = [dict(t) for t in teams]
    if year >= 2013:
        for t in rows:
            if t['teamID'] == 'HOU' and t['lgID'] == 'AL':
                t['lgID'], t['divID'] = 'NL', 'W'

    real = {}
    for t in rows:
        real.setdefault(t['lgID'], []).append(t)
    lg_ids = sorted(real)

    # Each option sorts by cost, then most division-count matches, then template order, then slot assignment.
    options = []
    for index, (key, shape) in enumerate(SHAPES.items()):
        for slots in permutations(range(len(shape)), len(lg_ids)):
            cost = sum(sum(shape[i]) for i in range(len(shape)) if i not in slots)
            matches = 0
            for lg, slot in zip(lg_ids, slots):
                m, n = sum(shape[slot]), len(real[lg])
                cost += max(0, m - n) + 2 * max(0, n - m)
                divs = {t['divID'] for t in real[lg] if t['divID']}
                matches += len(shape[slot]) == len(divs)
            options.append((cost, -matches, index, slots, key))
    if not options:
        raise ValueError(f'{year} has {len(lg_ids)} leagues; no template holds that many')
    cost, _, _, slots, key = min(options)

    owner = dict(zip(slots, lg_ids))
    leagues, dropped = [], []
    for i, sizes in enumerate(SHAPES[key]):
        lg = owner.get(i)
        m = sum(sizes)
        if lg is None:
            leagues.append({'lgID': None, 'divisions': [[None] * s for s in sizes]})
            continue
        kept, gone = _fit(real[lg], m, lg, year)
        dropped += gone
        seq = [t['teamID'] for t in kept] + [None] * (m - len(kept))
        divisions, pos = [], 0
        for s in sizes:
            divisions.append(seq[pos:pos + s])
            pos += s
        leagues.append({'lgID': lg, 'divisions': divisions})
    return {'template': key, 'leagues': leagues, 'dropped': sorted(dropped), 'cost': cost}


def _fit(rows, slots, lg, year):
    """Return (kept teams in fill order, dropped teamIDs) for one real league in `slots` places."""
    gone = []
    if len(rows) > slots:
        by_id = sorted(rows, key=lambda t: t['teamID'], reverse=True)
        fewest_g = sorted(by_id, key=lambda t: t['G'])  # stable: equal G keeps the highest teamID first
        gone = [t['teamID'] for t in fewest_g[:len(rows) - slots]]
    kept = [t for t in rows if t['teamID'] not in gone]
    return _order(kept, lg, year), gone


def _order(rows, lg, year):
    if lg == 'NL' and 1892 <= year <= 1899:  # 12 teams, no divisions: the EAST cities fill division 1
        return sorted(rows, key=lambda t: (t['teamID'] not in EAST, t['teamID']))
    return sorted(rows, key=lambda t: (DIV_RANK.get(t['divID'] or '', 3), t['teamID']))
