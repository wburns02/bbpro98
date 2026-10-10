"""The replay scorecard: how a simulated season tracks the real season it was built from. An association named for a
Lahman season ('1998 Major Leagues', '1942 Negro Leagues') is set against that season's teams and leaders in the
Lahman database: standings by team, the rank correlation and mean gap per league, and the leaders of each stat in both.
real() is the only reader of the database and it only reads; scorecard() is pure over the dicts it is given.
"""
import math
import re

import recap

MLB_LEAGUES = ('NA', 'NL', 'AA', 'UA', 'PL', 'AL', 'FL')
NEGRO_LEAGUES = ('NNL', 'ECL', 'ANL', 'EWL', 'NSL', 'NN2', 'NAL')
LEAGUE_SETS = {'Major': MLB_LEAGUES, 'Negro': NEGRO_LEAGUES}
NAME = re.compile(r'([0-9]{4}) (Major|Negro) Leagues')
NAME_LEN = 16           # the PYR keeps each of a player's names to this many bytes
TOP = 5
MIN_PAIRS = 3           # teams needed for a rank correlation
AB_PER_GAME = 2.7       # at-bats per team game for an AVG to count
OUTS_PER_GAME = 3       # outs per team game for an ERA to count
BAT = ('HR', 'AVG', 'RBI', 'SB')
PIT = ('W', 'SV', 'SO', 'ERA')
BAT_SUMS = (('ab', 'AB'), ('h', 'H'), ('hr', 'HR'), ('rbi', 'RBI'), ('sb', 'SB'), ('bb', 'BB'))
PIT_SUMS = (('w', 'W'), ('l', 'L'), ('sv', 'SV'), ('outs', 'IPouts'), ('er', 'ER'), ('so', 'SO'))


def season_of(name):
    """(year, leagues) for an association named for a Lahman season: '1998 Major Leagues' is (1998, MLB_LEAGUES),
    '1942 Negro Leagues' is (1942, NEGRO_LEAGUES). None for any other name, stock MLBPA associations included."""
    m = NAME.fullmatch(name) if isinstance(name, str) else None
    return (int(m[1]), LEAGUE_SETS[m[2]]) if m else None


def _cut(text):
    """A name as the PYR stores it: latin-1, cut to NAME_LEN bytes, stripped."""
    return (text or '').encode('latin-1', 'replace')[:NAME_LEN].decode('latin-1').strip()


def _name(first, last):
    return (_cut(first) + ' ' + _cut(last)).strip()


def _sums(table, cols):
    # Column names come from the constants above, never from the caller; every value is bound.
    return ', '.join('SUM(COALESCE(%s.%s, 0))' % (table, col) for _, col in cols)


def _stints(con, table, cols, weight, year, leagues):
    """[(name, line)] in playerID order: each player's stints in leagues summed, with 'lg' the league of his stint with
    the most `weight` (at-bats or outs)."""
    keys = [key for key, _ in cols]
    marks = ','.join('?' * len(leagues))
    rows = con.execute(
        f'SELECT t.playerID, p.nameFirst, p.nameLast, t.lgID, {_sums("t", cols)} '
        f'FROM {table} t LEFT JOIN people p ON p.playerID = t.playerID '
        f'WHERE t.yearID = ? AND t.lgID IN ({marks}) GROUP BY t.playerID, t.lgID ORDER BY t.playerID, t.lgID',
        (year, *leagues)).fetchall()
    players = {}
    for pid, first, last, lg, *vals in rows:
        stint = dict(zip(keys, (int(v) for v in vals)))
        rec = players.setdefault(pid, {'name': _name(first, last), 'lg': lg, 'top': -1, 'line': dict.fromkeys(keys, 0)})
        for key in keys:
            rec['line'][key] += stint[key]
        if stint[weight] > rec['top']:
            rec['lg'], rec['top'] = lg, stint[weight]
    return [(rec['name'], dict(rec['line'], lg=rec['lg'])) for _, rec in sorted(players.items())]


def _biggest(pairs, weight):
    """{name: line} of (name, line) pairs: of two lines with one name, the one with more `weight` is kept; a tie keeps
    the first."""
    out = {}
    for name, line in pairs:
        if name not in out or line[weight] > out[name][weight]:
            out[name] = line
    return out


def real(con, year, leagues):
    """One season of the Lahman database, read through con (a read-only connection): {'teams': {teamID[:3]: {...}},
    'bat': {name: {...}}, 'pit': {name: {...}}}, for the teams in leagues. A player line sums his stints in leagues and
    carries 'lg', the league it was played in most (by at-bats, or outs for pitchers); qualifiers are set by that
    league's team games. Two players with one name keep the one with more at-bats (outs)."""
    marks = ','.join('?' * len(leagues))
    teams = {}
    for tid, lg, div, name, g, w, l in con.execute(
            f'SELECT teamID, lgID, divID, name, G, W, L FROM teams WHERE yearID = ? AND lgID IN ({marks}) '
            'ORDER BY teamID', (year, *leagues)):
        teams[tid[:3]] = {'name': name or '', 'lg': lg, 'div': div or '', 'g': int(g or 0), 'w': int(w or 0),
                          'l': int(l or 0)}
    return {
        'teams': teams,
        'bat': _biggest(_stints(con, 'batting', BAT_SUMS, 'ab', year, leagues), 'ab'),
        'pit': _biggest(_stints(con, 'pitching', PIT_SUMS, 'outs', year, leagues), 'outs'),
    }


def _pct(w, l):
    return w / (w + l) if w + l else None


def _per_team(games, teams):
    return games * 2 / teams if teams else 0.0


def _ranks(values):
    """1-based ranks of values; tied values share the average of the ranks they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for i in order[start:end + 1]:
            ranks[i] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def _spearman(pairs):
    """Spearman rank correlation of (real, sim) pairs: the Pearson correlation of their ranks. None under MIN_PAIRS
    pairs, or when one side has no spread."""
    if len(pairs) < MIN_PAIRS:
        return None
    rx, ry = _ranks([r for r, _ in pairs]), _ranks([s for _, s in pairs])
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy:
        return None
    return round(sxy / math.sqrt(sxx * syy), 3) or 0.0


def _best(group, side):
    """The name of the team with the best pct on one side ('real' or 'sim'), ties by name; None without one."""
    have = [m for m in group if m[side]['pct'] is not None]
    return min(have, key=lambda m: (-m[side]['pct'], m['name']))['name'] if have else None


def _qualifies(stat, line, games):
    """AVG and ERA need their denominator per team game; a counting stat needs a count above zero."""
    if stat == 'AVG':
        return line['ab'] > 0 and line['ab'] >= AB_PER_GAME * games
    if stat == 'ERA':
        return line['outs'] > 0 and line['outs'] >= OUTS_PER_GAME * games
    return line[stat.lower()] > 0


def _raw(stat, line):
    """The stat unrounded; AVG and ERA from their parts, None when the denominator is zero."""
    if stat == 'AVG':
        return line['h'] / line['ab'] if line['ab'] else None
    if stat == 'ERA':
        return line['er'] * 27 / line['outs'] if line['outs'] else None
    return line[stat.lower()]


def _shown(stat, raw):
    if raw is None:
        return None
    if stat == 'AVG':
        return round(raw, 3)
    if stat == 'ERA':
        return round(raw, 2)
    return raw


def _top(stat, pairs, games_of):
    """[name, value] of the TOP best lines for one stat among those that qualify. ERA is lowest-first; ties by name."""
    rows = []
    for name, line in pairs:
        if _qualifies(stat, line, games_of(line)):
            raw = _raw(stat, line)
            rows.append((name, raw, _shown(stat, raw)))
    rows.sort(key=lambda r: (r[1] if stat == 'ERA' else -r[1], r[0]))
    return [[name, shown] for name, _, shown in rows[:TOP]]


def _leaders(bat, pit, games_of):
    """{stat: [[name, value], ...]} for every batting and pitching stat. bat and pit are (name, line) pairs."""
    return {stat: _top(stat, bat if stat in BAT else pit, games_of) for stat in BAT + PIT}


def _players(real_leaders, sim_bat, sim_pit):
    """For each real top-5 player who is in the sim too (same name): his real and sim value of that stat. sim_bat and
    sim_pit map name to a line."""
    out = []
    for stat in BAT + PIT:
        pool = sim_bat if stat in BAT else sim_pit
        for name, real_value in real_leaders[stat]:
            line = pool.get(name)
            if line is not None:
                out.append({'stat': stat, 'name': name, 'real': real_value, 'sim': _shown(stat, _raw(stat, line))})
    return out


def scorecard(assoc, sim_lines, names, real_data):
    """The season against the real one, as JSON-able dicts. Teams match on abbrev; a sim team with no real counterpart
    (a filler) is named in 'unmatched'. A pct is None where a side has no decided game. A real line's qualifiers come
    from its league's team games (real()'s 'lg', or the max team G over all real teams when it has none); a sim line's
    from the sim's games played per team.

    assoc: association() from gamedata; sim_lines: gamedata.season_lines() for this season; names: {pid: name};
    real_data: real().
    """
    teams = assoc['teams']
    real_teams = real_data['teams']
    wl = recap.tally(assoc['games'])
    sim_g = _per_team(sum(1 for g in assoc['games'] if g['played']), len(teams))
    real_g = {}
    for t in real_teams.values():
        real_g[t['lg']] = max(real_g.get(t['lg'], 0), t['g'])
    season_g = max(real_g.values(), default=0)

    matched, unmatched = [], []
    for tid in sorted(teams):
        t = teams[tid]
        r = real_teams.get(t['abbrev'])
        if r is None:
            unmatched.append(t['name'])
            continue
        w, l = wl.get(tid, (0, 0))
        real_pct, sim_pct = _pct(r['w'], r['l']), _pct(w, l)
        diff = None if real_pct is None or sim_pct is None else sim_pct - real_pct
        matched.append({
            'name': t['name'], 'lg': r['lg'], 'real': {'w': r['w'], 'l': r['l'], 'pct': real_pct},
            'sim': {'w': w, 'l': l, 'pct': sim_pct}, 'diff': diff,
            'wins_diff': None if diff is None else (round(diff * r['g'], 1) or 0.0),
        })
    matched.sort(key=lambda m: (m['lg'], -(m['real']['pct'] or 0), m['name']))

    leagues = {}
    for lg in sorted({t['lg'] for t in real_teams.values()}):
        group = [m for m in matched if m['lg'] == lg]
        pairs = [(m['real']['pct'], m['sim']['pct']) for m in group
                 if m['real']['pct'] is not None and m['sim']['pct'] is not None]
        leagues[lg] = {
            'rank_corr': _spearman(pairs),
            'mean_abs_diff': round(sum(abs(s - r) for r, s in pairs) / len(pairs), 3) if pairs else None,
            'real_best': _best(group, 'real'),
            'sim_best': _best(group, 'sim'),
        }

    sim_bat = [(recap.name_of(names, p), s) for p, s in sorted(sim_lines['bat'].items()) if p >= 100]
    sim_pit = [(recap.name_of(names, p), s) for p, s in sorted(sim_lines['pit'].items()) if p >= 100]
    real_leaders = _leaders(list(real_data['bat'].items()), list(real_data['pit'].items()),
                            lambda line: real_g.get(line.get('lg'), season_g))
    sim_leaders = _leaders(sim_bat, sim_pit, lambda line: sim_g)
    return {
        'teams': matched,
        'unmatched': sorted(unmatched),
        'leagues': leagues,
        'leaders': {stat: {'real': real_leaders[stat], 'sim': sim_leaders[stat]} for stat in BAT + PIT},
        'players': _players(real_leaders, _biggest(sim_bat, 'ab'), _biggest(sim_pit, 'outs')),
        'played': round(sim_g, 1),
        'scheduled': round(_per_team(len(assoc['games']), len(teams)), 1),
    }
