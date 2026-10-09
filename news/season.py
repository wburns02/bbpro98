"""Season pieces for the news sidecar: the season preview (last season's stats of each team's players, written once per
association) and the season awards (each league's MVP and Cy Young candidates and the division champions, written once
every regular-season game is played). Pure functions over the dicts gamedata.py returns; the model is reached only
through the complete() callable the caller passes in. Prompt rules and the number check are recap's.
"""
import feed
import recap

MIN_AB = 100            # preview hitter: at-bats last season
MIN_OUTS = 150          # preview pitcher: outs last season (50 innings)
AB_PER_GAME = 3.1       # awards MVP: at-bats per team game
OUTS_PER_GAME = 3       # awards Cy Young: outs per team game (one inning)
SAVES = 10              # awards Cy Young: this many saves qualifies a pitcher whatever his innings
CANDIDATES = 3

PREVIEW_SYSTEM = ("You are a newspaper baseball writer. Write the season preview for the association: 200 to 320 "
                  "words on the divisions, the teams and the players to watch, using last season's numbers given. "
                  + recap.RULES)
AWARDS_SYSTEM = ("You are a newspaper baseball writer. Write the season awards story: in each league the first "
                 "MVP and first Cy Young candidate listed are the winners; name the runners-up and the division "
                 "champions. 180 to 300 words. " + recap.RULES)


def complete(assoc):
    """True when the schedule has games and every one of them is played: the regular season is over."""
    return bool(assoc['games']) and all(g['played'] for g in assoc['games'])


def _players(assoc):
    """{tid: [pid, ...]}: each player under the first team (ascending tid) whose roster lists him. Ids < 100 are team
    lines, not players; a player on no roster is in no list."""
    out, seen = {}, set()
    for tid in sorted(assoc['teams']):
        for pid in assoc['teams'][tid]['roster']:
            if pid >= 100 and pid not in seen:
                seen.add(pid)
                out.setdefault(tid, []).append(pid)
    return out


def _label(*parts):
    """The non-empty parts joined by a space; 'The league' when there are none."""
    return ' '.join(p for p in parts if p) or 'The league'


def _era(s):
    return s['er'] * 27 / s['outs']


def _hitter(pids, last, names):
    """The hitter with the most home runs (ties: more RBI, then name) among those with MIN_AB at-bats last season."""
    qualified = [p for p in pids if p in last['bat'] and last['bat'][p]['ab'] >= MIN_AB]
    if not qualified:
        return None
    pid = min(qualified, key=lambda p: (-last['bat'][p]['hr'], -last['bat'][p]['rbi'], recap.name_of(names, p)))
    s = last['bat'][pid]
    return {'name': recap.name_of(names, pid), 'avg': feed._bare('%.3f' % (s['h'] / s['ab'])), 'hr': s['hr'],
            'rbi': s['rbi']}


def _pitcher(pids, last, names):
    """The pitcher with the most wins (ties: lower ERA, then name) among those with MIN_OUTS outs last season."""
    qualified = [p for p in pids if p in last['pit'] and last['pit'][p]['outs'] >= MIN_OUTS]
    if not qualified:
        return None
    pid = min(qualified, key=lambda p: (-last['pit'][p]['w'], _era(last['pit'][p]), recap.name_of(names, p)))
    s = last['pit'][pid]
    return {'name': recap.name_of(names, pid), 'w': s['w'], 'l': s['l'], 'era': '%.2f' % _era(s), 'so': s['so']}


def preview_facts(assoc, last, names):
    """What the season preview may say: the association, its opening day, and each division (in standings order) with
    each team's manager and stadium and the hitter and pitcher last season's stats name."""
    teams, players = assoc['teams'], _players(assoc)
    opening = min(((g['month'], g['day']) for g in assoc['games']), default=None)
    divisions = []
    for d in feed.standings(assoc):
        rows = []
        for row in d['teams']:
            t, pids = teams[row['tid']], players.get(row['tid'], [])
            rows.append({'name': t['name'], 'manager': t['manager'], 'stadium': t['stadium'],
                         'hitter': _hitter(pids, last, names), 'pitcher': _pitcher(pids, last, names)})
        divisions.append({'league': d['league'], 'division': d['division'], 'teams': rows})
    return {'association': assoc['name'], 'teams': len(teams), 'games': len(assoc['games']),
            'opening_day': recap.date_text(*opening) if opening else None, 'divisions': divisions}


def preview_template(facts):
    """The season preview built only from the facts: an opening paragraph, then one paragraph per division."""
    if facts['opening_day']:
        first = 'The %s season opens on %s with %d teams and %d games on the schedule.' % (
            facts['association'], facts['opening_day'], facts['teams'], facts['games'])
    else:
        first = 'The %s season has no games on the schedule.' % facts['association']
    paragraphs = [first]
    for d in facts['divisions']:
        sentences = [_label(d['league'], d['division']) + ':']
        for t in d['teams']:
            s = '%s, managed by %s.' % (t['name'], t['manager'])
            if t['hitter']:
                h = t['hitter']
                s += ' %s hit %d home runs with %d RBI last season.' % (h['name'], h['hr'], h['rbi'])
            if t['pitcher']:
                p = t['pitcher']
                s += ' %s went %d-%d with a %s ERA.' % (p['name'], p['w'], p['l'], p['era'])
            sentences.append(s)
        paragraphs.append(' '.join(sentences))
    return {'headline': 'The season ahead', 'body': '\n'.join(paragraphs)}


def _batter(pid, team, season, names, team_games):
    """(sort key, candidate) for an MVP candidate, or None when he does not qualify."""
    b = season['bat'].get(pid)
    if not b or b['ab'] <= 0 or b['ab'] < AB_PER_GAME * team_games:
        return None
    tb = b['h'] + b['h2b'] + 2 * b['h3b'] + 3 * b['hr']
    score = (b['h'] + b['bb']) * tb / (b['ab'] + b['bb'])
    name = recap.name_of(names, pid)
    return (-score, name), {'name': name, 'team': team['name'], 'avg': feed._bare('%.3f' % (b['h'] / b['ab'])),
                            'hr': b['hr'], 'rbi': b['rbi'], 'r': b['r'], 'sb': b['sb'],
                            'runs_created': int(round(score))}


def _pitcher_candidate(pid, team, season, names, team_games):
    """(sort key, candidate) for a Cy Young candidate, or None when he does not qualify."""
    p = season['pit'].get(pid)
    if not p or p['outs'] <= 0 or not (p['outs'] >= OUTS_PER_GAME * team_games or p['sv'] >= SAVES):
        return None
    score = 5 * p['outs'] / 27 - p['er'] + p['so'] / 12 + 2.5 * p['sv'] + 6 * p['w'] - 2 * p['l']
    name = recap.name_of(names, pid)
    return (-score, name), {'name': name, 'team': team['name'], 'w': p['w'], 'l': p['l'],
                            'era': '%.2f' % _era(p), 'so': p['so'], 'sv': p['sv'], 'ip': recap.ip(p['outs'])}


def awards_facts(assoc, season, names):
    """What the season awards may say, once the regular season is played out: per league, its MVP and Cy Young
    candidates (best first) and its division champions. Raises ValueError while any game is unplayed."""
    if not complete(assoc):
        raise ValueError('the regular season is not over: every game must be played')
    teams, players = assoc['teams'], _players(assoc)
    played = sum(1 for g in assoc['games'] if g['played'])
    team_games = played * 2 / len(teams)
    groups = feed.standings(assoc)
    leagues = []
    for lg in dict.fromkeys(d['league'] for d in groups):           # in order of first appearance
        champions = [{'division': d['division'], 'team': d['teams'][0]['name'],
                      'record': '%d-%d' % (d['teams'][0]['w'], d['teams'][0]['l'])}
                     for d in groups if d['league'] == lg]
        mine = [(pid, teams[tid]) for tid in sorted(teams) if teams[tid]['league'] == lg
                for pid in players.get(tid, [])]
        bat = [x for x in (_batter(pid, t, season, names, team_games) for pid, t in mine) if x]
        pit = [x for x in (_pitcher_candidate(pid, t, season, names, team_games) for pid, t in mine) if x]
        leagues.append({'league': lg, 'champions': champions,
                        'mvp': [c for _, c in sorted(bat, key=lambda r: r[0])[:CANDIDATES]],
                        'cy_young': [c for _, c in sorted(pit, key=lambda r: r[0])[:CANDIDATES]]})
    return {'association': assoc['name'], 'leagues': leagues}


def awards_template(facts):
    """The season awards built only from the facts: one paragraph per league."""
    paragraphs = []
    for lg in facts['leagues']:
        sentences = [_label(lg['league']) + ':']
        if lg['mvp']:
            m = lg['mvp'][0]
            sentences.append('%s of the %s is the MVP, batting %s with %d home runs and %d RBI.' % (
                m['name'], m['team'], m['avg'], m['hr'], m['rbi']))
        if lg['cy_young']:
            c = lg['cy_young'][0]
            sentences.append('%s of the %s wins the Cy Young at %d-%d with a %s ERA.' % (
                c['name'], c['team'], c['w'], c['l'], c['era']))
        if lg['champions']:
            sentences.append('Champions: %s.' % ', '.join('%s (%s)' % (c['team'], c['record'])
                                                          for c in lg['champions']))
        paragraphs.append(' '.join(sentences))
    return {'headline': 'Season awards', 'body': '\n'.join(paragraphs)}


def preview_prompt(facts):
    """(system, user) for the season preview."""
    return PREVIEW_SYSTEM, recap.facts_message(facts)


def awards_prompt(facts):
    """(system, user) for the season awards."""
    return AWARDS_SYSTEM, recap.facts_message(facts)


def write_preview(facts, budget, complete, attempts=2):
    """The season preview from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, preview_prompt, preview_template, attempts)


def write_awards(facts, budget, complete, attempts=2):
    """The season awards from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, awards_prompt, awards_template, attempts)
