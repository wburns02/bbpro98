"""League-wide pieces for the news sidecar: standings, streaks, one day's results, the season leaders, and the
'Around the league' column for that day. Pure functions over the dicts gamedata.py returns; the model is reached only
through the complete() callable the caller passes in. Prompt rules and the number check are recap's.
"""
import recap

TOP = 5


def _bare(s):
    """'0.600' -> '.600': baseball leaves off the leading zero."""
    return s[1:] if s.startswith('0') else s


def _pct(w, l):
    return w / (w + l) if w + l else 0.0


def _gb_str(gb):
    if gb == 0:
        return '-'
    if gb == int(gb):
        return str(int(gb))
    return ('-' if gb < 0 else '') + _bare('%.1f' % abs(gb))


def standings(assoc):
    """Divisions in order of first appearance in tid order. Each: {'league', 'division', 'teams'}, teams best first."""
    teams = assoc['teams']
    wl = recap.tally(assoc['games'])
    groups = {}
    for tid in sorted(teams):
        t = teams[tid]
        groups.setdefault((t['league'], t['division']), []).append(tid)
    out = []
    for (league, division), tids in groups.items():
        rows = []
        for tid in tids:
            w, l = wl.get(tid, (0, 0))
            rows.append({'tid': tid, 'name': teams[tid]['name'], 'abbrev': teams[tid]['abbrev'], 'w': w, 'l': l,
                         'pct': _bare('%.3f' % _pct(w, l)), 'gb': ''})
        rows.sort(key=lambda r: (-_pct(r['w'], r['l']), -r['w'], r['name']))
        lw, ll = rows[0]['w'], rows[0]['l']
        for r in rows:
            r['gb'] = _gb_str(((lw - r['w']) + (r['l'] - ll)) / 2)
        out.append({'league': league, 'division': division, 'teams': rows})
    return out


def streaks(assoc):
    """{tid: 'W3' | 'L2'}: each team's current streak. Teams with no decided game are absent."""
    cur = {}
    for g in recap.in_order(assoc['games']):
        res = recap.outcome(g)
        if res is None:
            continue
        for tid, kind in ((res[0], 'W'), (res[1], 'L')):
            prev = cur.get(tid)
            cur[tid] = (kind, prev[1] + 1 if prev and prev[0] == kind else 1)
    return {tid: '%s%d' % kn for tid, kn in cur.items()}


def last_day(assoc):
    """(month, day) of the latest played game, or None when nothing has been played."""
    days = [(g['month'], g['day']) for g in assoc['games'] if g['played']]
    return max(days) if days else None


def day_results(assoc, month, day):
    teams = assoc['teams']
    games = [g for g in assoc['games'] if g['played'] and (g['month'], g['day']) == (month, day)]
    return [{'away': teams[g['away']]['name'], 'home': teams[g['home']]['name'], 'away_runs': g['away_runs'],
             'home_runs': g['home_runs'], 'innings': g['innings']} for g in sorted(games, key=lambda g: g['slot'])]


def _ranked(rows):
    """The TOP best of (sort key, name, value) rows, lowest key first, ties by name, as {'name', 'value'}."""
    return [{'name': name, 'value': value} for _, name, value in sorted(rows)[:TOP]]


def leaders(season, names, teams_played):
    """Season leaders among players (ids >= 100). Batters qualify for avg at 3.1 at-bats per team game, pitchers for
    ERA at one inning per team game. Counting stats leave out zeros."""
    bat = {p: s for p, s in season['bat'].items() if p >= 100}
    pit = {p: s for p, s in season['pit'].items() if p >= 100}
    min_ab, min_outs = 3.1 * teams_played, 3 * teams_played
    avg, era = [], []
    for p, s in bat.items():
        if s['ab'] > 0 and s['ab'] >= min_ab:
            avg.append((-s['h'] / s['ab'], recap.name_of(names, p), _bare('%.3f' % (s['h'] / s['ab']))))
    for p, s in pit.items():
        if s['outs'] > 0 and s['outs'] >= min_outs:
            v = s['er'] * 27 / s['outs']
            era.append((v, recap.name_of(names, p), '%.2f' % v))
    out = {'avg': _ranked(avg)}
    for stat, lines in (('hr', bat), ('rbi', bat), ('sb', bat), ('w', pit), ('so', pit), ('sv', pit)):
        out[stat] = _ranked([(-s[stat], recap.name_of(names, p), str(s[stat])) for p, s in lines.items()
                             if s[stat] > 0])
    out['era'] = _ranked(era)
    return out


def day_facts(assoc, season, names, month, day):
    """What the 'Around the league' column may say about one date: its results, each division's leader, the streaks
    of four or more games, and the season leaders (season to date)."""
    teams = assoc['teams']
    played = sum(1 for g in assoc['games'] if g['played'])
    teams_played = played * 2 / len(teams) if teams else 0.0
    groups = standings(assoc)
    long = []
    for tid, s in streaks(assoc).items():
        if int(s[1:]) >= 4:
            long.append((-int(s[1:]), teams[tid]['name'], s))
    lead = leaders(season, names, teams_played)
    return {
        'association': assoc['name'],
        'date': recap.date_text(month, day),
        'results': day_results(assoc, month, day),
        'division_leaders': [{'league': g['league'], 'division': g['division'], 'team': g['teams'][0]['name'],
                              'record': '%d-%d' % (g['teams'][0]['w'], g['teams'][0]['l']),
                              'lead': g['teams'][1]['gb'] if len(g['teams']) > 1 else '-'} for g in groups],
        'streaks': [{'team': name, 'streak': s} for _, name, s in sorted(long)[:5]],
        'leaders': {k: lead[k][:3] for k in ('hr', 'avg', 'w', 'era')},
    }


SYSTEM = ("You are a newspaper baseball writer covering the association's season. Write the 'Around the league' "
          "column for one date: 100 to 170 words on that day's results and the division leaders. " + recap.RULES)


def prompt(facts):
    """(system, user) for the 'Around the league' column."""
    return SYSTEM, recap.facts_message(facts)


def template(facts):
    """The day's results and division leaders as plain lines; every number in it passes numbers_ok."""
    lines = []
    for r in facts['results']:
        if r['home_runs'] > r['away_runs']:
            pair = (r['home'], r['home_runs'], r['away'], r['away_runs'])
        else:
            pair = (r['away'], r['away_runs'], r['home'], r['home_runs'])
        lines.append('%s %d, %s %d.' % pair)
    if not lines:
        lines.append('No games were played on %s.' % facts['date'])
    for d in facts['division_leaders']:
        group = ' '.join(x for x in (d['league'], d['division']) if x) or 'league'
        lines.append('%s leads the %s at %s.' % (d['team'], group, d['record']))
    return {'headline': 'Around the league: ' + facts['date'], 'body': '\n'.join(lines)}


def write(facts, budget, complete, attempts=2):
    """The 'Around the league' column from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, prompt, template, attempts)
