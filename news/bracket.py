"""The postseason page of a season for the news sidecar: the bracket gamedata.postseason() reads from the ASN, as plain
facts (team names, series, games) and a template story. No model: the page is the bracket. Pure functions over dicts.
"""
import recap

ROUND_NAMES = recap.ROUND_NAMES      # one table: the postseason recaps and the bracket page name rounds alike


def _name(assoc, tid):
    team = assoc['teams'].get(tid)
    return team['name'] if team else 'team %s' % tid


def _series(assoc, s):
    return {'teams': [_name(assoc, t) for t in s['teams']], 'wins': list(s['wins']), 'best_of': s['best_of'],
            'winner': _name(assoc, s['winner']) if s['winner'] else None,
            'games': [{'away': _name(assoc, g['away']), 'home': _name(assoc, g['home']),
                       'away_runs': g['away_runs'], 'home_runs': g['home_runs']} for g in s['games']]}


def facts(assoc, b, season):
    """The bracket b with team names for ids. A series whose teams are not both known yet (a 0 or None) is left out,
    and a round left with no series."""
    rounds = []
    for r in b['rounds']:
        series = [_series(assoc, s) for s in r['series'] if len(s['teams']) == 2 and all(s['teams'])]
        if series:
            rounds.append({'round': r['round'], 'name': ROUND_NAMES.get(r['round'], 'Round %s' % r['round']),
                           'series': series})
    return {'association': assoc['name'], 'season': season, 'complete': b['complete'],
            'champion': _name(assoc, b['champion']) if b['champion'] else None, 'rounds': rounds}


def played(f):
    """True when any series of facts f has a game."""
    return any(s['games'] for r in f['rounds'] for s in r['series'])


def _sentence(s, round_name):
    a, b = s['teams']
    wa, wb = s['wins']
    if s['winner'] is not None:
        if s['winner'] == b:
            a, b, wa, wb = b, a, wb, wa
        return '%s beat %s %d-%d in the %s.' % (a, b, wa, wb, round_name)
    if not s['games']:
        return '%s and %s meet in the %s.' % (a, b, round_name)
    if wa == wb:
        return '%s and %s are tied %d-%d in the %s.' % (a, b, wa, wb, round_name)
    if wb > wa:
        a, b, wa, wb = b, a, wb, wa
    return '%s leads %s %d-%d in the %s.' % (a, b, wa, wb, round_name)


def template(f):
    """{'headline', 'body'}: one paragraph per round, one sentence per series."""
    headline = ('%s win the %s World Series' % (f['champion'], f['season']) if f['champion']
                else '%s postseason' % f['season'])
    body = '\n\n'.join(' '.join(_sentence(s, r['name']) for s in r['series']) for r in f['rounds'])
    return {'headline': headline, 'body': body}


SYSTEM = ("You are a newspaper baseball writer. Write the wrap of the association's postseason: 150 to "
          "250 words on how the champion got there, round by round, ending with the World Series. " + recap.RULES)


def prompt(f):
    """(system, user) for the wrap."""
    return SYSTEM, recap.facts_message(f)


def write(f, budget, complete, attempts=2):
    """The wrap from the model, or the template when it cannot give one that checks out."""
    return recap.draft(f, budget, complete, prompt, template, attempts)
