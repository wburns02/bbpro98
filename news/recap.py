"""Game stories for the news sidecar: the facts of one played game, the prompt that asks the model for a story about
them, a template story built only from the facts, and the check that every number in a story is one of the facts.
Pure functions; the model is reached only through the complete() callable the caller passes in.
"""
import json
import re

import hive

MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
          'December')
NUMBER = re.compile(r'\d+(?:\.\d+)?')
DIGITS = re.compile(r'\d+')
NUMBER_WORDS = {w: str(n) for n, w in enumerate(
    'two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen '
    'nineteen twenty'.split(), 2)}
WORD = re.compile(r'\b(%s)\b' % '|'.join(NUMBER_WORDS), re.I)
MARKUP = ' \t#*"\'“”‘’'
BAT_KEYS = ('ab', 'h', '2b', '3b', 'hr', 'rbi', 'bb', 'r', 'sb')

RULES = ('The first line is a headline of at most 10 words with no markup. Then one blank line, then the story as '
         'plain prose: no lists, no markdown. Use only the facts given. Never invent innings, plays, quotes, '
         'attendance, weather, injuries, or any number not in the facts. Spell numbers as digits.')
SYSTEM = ("You are a newspaper baseball writer covering the association's season. Write a game story of 80 to 130 "
          'words. ' + RULES)


def ip(outs):
    """Outs as innings pitched: 23 -> '7.2'."""
    return '%d.%d' % divmod(outs, 3)


def date_text(month, day):
    return '%s %d' % (MONTHS[month - 1], day)


def name_of(names, pid):
    return names.get(pid, 'Player %d' % pid)


def in_order(games):
    """The games in schedule order: by (month, day, slot), ties kept in file order."""
    return sorted(games, key=lambda g: (g['month'], g['day'], g['slot']))


def _key(g):
    return g['month'], g['day'], g['slot'], g['away'], g['home']


def outcome(g):
    """(winner, loser) team ids of a played game; None when the game is unplayed or tied."""
    if not g['played'] or g['away_runs'] == g['home_runs']:
        return None
    if g['away_runs'] > g['home_runs']:
        return g['away'], g['home']
    return g['home'], g['away']


def tally(games):
    """{tid: [wins, losses]} over the played games in `games`."""
    wl = {}
    for g in games:
        res = outcome(g)
        if res is not None:
            wl.setdefault(res[0], [0, 0])[0] += 1
            wl.setdefault(res[1], [0, 0])[1] += 1
    return wl


def records(assoc, game):
    """{'away': (w, l), 'home': (w, l)}: each team's record through `game` (itself included), played games only."""
    games = in_order(assoc['games'])
    for i, g in enumerate(games):
        if _key(g) == _key(game):
            wl = tally(games[:i + 1])
            return {side: tuple(wl.get(game[side], (0, 0))) for side in ('away', 'home')}
    raise ValueError('game not on the schedule: %r' % (_key(game),))


def _pitch(abbrev, line, names):
    return {'team': abbrev, 'name': name_of(names, line['pid']), 'ip': ip(line['outs']), 'h': line['h'],
            'r': line['r'], 'er': line['er'], 'bb': line['bb'], 'so': line['so']}


def game_facts(assoc, box, game, names):
    """What a story about one played game may say. `box` is gamedata.boxscore() of that game; `names` maps player
    ids to 'First Last'."""
    return _facts(assoc, box, game, names, records(assoc, game))


def _facts(assoc, box, game, names, recs):
    """game_facts with each side's record given: recs is {'away': (w, l), 'home': (w, l)}. A game with no month has
    no date."""
    away, home = box['away'], box['home']
    if away['runs'] == home['runs']:
        raise ValueError('tied game: nothing to write about')
    teams = assoc['teams']
    sides = {}
    for side, bx in (('away', away), ('home', home)):
        team = teams[game[side]]
        sides[side] = {'name': team['name'], 'abbrev': team['abbrev'], 'runs': bx['runs'], 'hits': bx['hits'],
                       'record': '%d-%d' % recs[side]}
    sides['home']['stadium'] = teams[game['home']]['stadium']

    batters = []
    for side in ('away', 'home'):
        for b in box[side]['batting']:
            if b['h'] >= 3 or b['hr'] >= 1 or b['rbi'] >= 3 or b['sb'] >= 2:
                batters.append(dict(team=sides[side]['abbrev'], name=name_of(names, b['pid']),
                                    **{k: b[k] for k in BAT_KEYS}))
    batters.sort(key=lambda b: (-b['hr'], -b['rbi'], -b['h'], b['name']))

    dec = {'win': None, 'loss': None, 'save': None}
    for side in ('away', 'home'):
        for line in box[side]['pitching']:
            for flag, role in (('w', 'win'), ('l', 'loss'), ('sv', 'save')):
                if line[flag] == 1 and dec[role] is None:
                    dec[role] = _pitch(sides[side]['abbrev'], line, names)

    winner = 'away' if away['runs'] > home['runs'] else 'home'
    loser = 'home' if winner == 'away' else 'away'
    notes = []
    if box[loser]['runs'] == 0:
        notes.append('shutout')
    if game['innings'] > 9:
        notes.append('extra innings')
    if len(box[winner]['pitching']) == 1:
        notes.append('complete game by %s' % name_of(names, box[winner]['pitching'][0]['pid']))
    for side in ('away', 'home'):
        for b in box[side]['batting']:
            if b['hr'] >= 2:
                notes.append('%s hit %d home runs' % (name_of(names, b['pid']), b['hr']))

    date = None if game['month'] is None else date_text(game['month'], game['day'])
    return {'association': assoc['name'], 'date': date, 'innings': game['innings'], 'away': sides['away'],
            'home': sides['home'], 'winner': winner, 'batters': batters[:6], 'decisions': dec, 'notes': notes}


def _walk(value, out):
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        out.add(str(value))
    elif isinstance(value, str):
        out.update(NUMBER.findall(value))
        out.update(DIGITS.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            _walk(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, out)


def allowed_numbers(facts):
    """Every number a story may use: each integer and decimal in the facts, and for a game the run margin and total."""
    out = set()
    _walk(facts, out)
    away, home = facts.get('away'), facts.get('home')
    if isinstance(away, dict) and isinstance(home, dict) and 'runs' in away and 'runs' in home:
        out.add(str(abs(away['runs'] - home['runs'])))
        out.add(str(away['runs'] + home['runs']))
    return out


def _strings(value, out):
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _strings(v, out)
    return out


def _named(facts):
    """Number words that are part of a name or place in the facts ('Three Rivers Stadium', 'Bob Five'), each with a
    neighbouring word from that name: 'Three Rivers' and 'Bob Five' are names in a story, a lone 'three' is not."""
    out = set()
    for s in _strings(facts, []):
        words = s.split()
        for i, w in enumerate(words):
            if WORD.fullmatch(w):
                out.update(' '.join(words[j:j + 2]) for j in (i - 1, i) if 0 <= j and j + 1 < len(words))
    return sorted(out, key=len, reverse=True)


def numbers_ok(text, facts):
    """True when every number in text is in the facts. Number words two to twenty count, except inside a name from
    the facts; 'one' and ordinals do not."""
    allowed = allowed_numbers(facts)
    if any(n not in allowed for n in NUMBER.findall(text)):
        return False
    for name in _named(facts):
        text = text.replace(name, ' ')
    return all(NUMBER_WORDS[w.lower()] in allowed for w in WORD.findall(text))


def facts_message(facts):
    return 'Facts:\n' + json.dumps(facts, indent=1, sort_keys=True)


def prompt(facts):
    """(system, user) for a game story."""
    return SYSTEM, facts_message(facts)


def parse(text):
    """{'headline', 'body'} from a model answer: the first paragraph is the headline, the rest the body. None when
    either is empty or the headline is over 120 characters."""
    lines = text.strip().splitlines()
    cut = next((i for i, line in enumerate(lines) if not line.strip()), None)
    if cut is None:
        return None
    headline = ' '.join(' '.join(lines[:cut]).split()).strip(MARKUP)
    body = '\n'.join(lines[cut + 1:]).strip()
    if not headline or not body or len(headline) > 120:
        return None
    return {'headline': headline, 'body': body}


def _plural(n, noun):
    return '%d %s' % (n, noun if n == 1 else noun + 's')


def _details(facts):
    """The sentences a story gives after its first: the innings, the top batters and the pitching decisions."""
    body = []
    if facts['innings'] > 9:
        body.append('It took %d innings.' % facts['innings'])
    for b in facts['batters'][:3]:
        line = '%s went %d-for-%d' % (b['name'], b['h'], b['ab'])
        extra = []
        if b['hr']:
            extra.append(_plural(b['hr'], 'home run'))
        if b['rbi']:
            extra.append('%d RBI' % b['rbi'])
        if extra:
            line += ' with ' + ' and '.join(extra)
        body.append(line + '.')
    dec = facts['decisions']
    if dec['win']:
        body.append('%s got the win, allowing %s over %s innings.' % (
            dec['win']['name'], _plural(dec['win']['r'], 'run'), dec['win']['ip']))
    if dec['save']:
        body.append('%s earned the save over %s innings.' % (dec['save']['name'], dec['save']['ip']))
    return body


def template(facts):
    """A plain story built only from the facts; every number in it passes numbers_ok."""
    win = facts['winner']
    lose = 'home' if win == 'away' else 'away'
    w, l = facts[win], facts[lose]
    body = ['%s beat %s %d-%d at %s on %s.' % (w['name'], l['name'], w['runs'], l['runs'],
                                                       facts['home']['stadium'], facts['date'])]
    body += _details(facts)
    body.append('%s is %s; %s is %s.' % (facts['away']['name'], facts['away']['record'],
                                         facts['home']['name'], facts['home']['record']))
    return {'headline': '%s %d, %s %d' % (w['name'], w['runs'], l['name'], l['runs']), 'body': ' '.join(body)}


def draft(facts, budget, complete, make_prompt, fallback, attempts=2):
    """Ask complete() for a piece built from facts and check it; after `attempts` misses, or at once when the budget
    is spent, return fallback(facts) marked source 'template' with the last failure's reason."""
    reason = 'error'
    for _ in range(attempts):
        try:
            text, _usage = complete(*make_prompt(facts), budget)
        except hive.BudgetExceeded:
            return dict(fallback(facts), source='template', reason='budget')
        except hive.HiveError:
            reason = 'error'
            continue
        story = parse(text)
        if story is None:
            reason = 'format'
            continue
        if not numbers_ok(story['headline'] + '\n' + story['body'], facts):
            reason = 'numbers'
            continue
        return dict(story, source='glm')
    return dict(fallback(facts), source='template', reason=reason)


def write(facts, budget, complete, attempts=2):
    """A game story from the model, or the template when it cannot give one that checks out."""
    return draft(facts, budget, complete, prompt, template, attempts)


ROUND_NAMES = {1: 'Division Series', 2: 'League Championship Series', 3: 'World Series'}


def match_post(bracket, box, used):
    """(round, series index, game index) of the first bracket game that is this box score: same away and home team,
    same final score, not in `used`. Rounds, series and games are tried in order, so a repeated score maps to the
    earliest game not yet written about. None when no game fits."""
    a, h = box['away'], box['home']
    want = (a['tid'], h['tid'], a['runs'], h['runs'])
    for rnd in bracket['rounds']:
        for si, s in enumerate(rnd['series']):
            for gi, g in enumerate(s['games']):
                got = (g['away'], g['home'], g['away_runs'], g['home_runs'])
                if got == want and (rnd['round'], si, gi) not in used:
                    return rnd['round'], si, gi
    return None


def post_facts(assoc, box, bracket, rnd, si, gi, names, sched=None):
    """What a story about one postseason game may say: game_facts with each side's record being its wins and losses
    in the series through this game, plus the round, the game number and whether the series ended. `sched` is the
    game's postseason_schedule entry, for its date and innings; without it the story has no date and 9 innings."""
    s = next(r for r in bracket['rounds'] if r['round'] == rnd)['series'][si]
    wl = {}
    for g in s['games'][:gi + 1]:
        if g['away_runs'] != g['home_runs']:
            win, lose = (g['away'], g['home']) if g['away_runs'] > g['home_runs'] else (g['home'], g['away'])
            wl.setdefault(win, [0, 0])[0] += 1
            wl.setdefault(lose, [0, 0])[1] += 1
    cur = s['games'][gi]
    recs = {side: tuple(wl.get(cur[side], (0, 0))) for side in ('away', 'home')}
    game = {'away': cur['away'], 'home': cur['home'], 'month': sched['month'] if sched else None,
            'day': sched['day'] if sched else None, 'innings': sched['innings'] if sched else 9}
    over = any(w >= s['best_of'] // 2 + 1 for w, _ in wl.values())
    return dict(_facts(assoc, box, game, names, recs), round=ROUND_NAMES[rnd], game_number=gi + 1,
                best_of=s['best_of'], series_over=over)


def _series_record(side):
    return tuple(int(n) for n in side['record'].split('-'))


def post_template(facts):
    """A plain story for a postseason game, built only from the facts; every number in it passes numbers_ok."""
    win = facts['winner']
    lose = 'home' if win == 'away' else 'away'
    w, l = facts[win], facts[lose]
    first = '%s beat %s %d-%d in Game %d of the %s at %s' % (w['name'], l['name'], w['runs'], l['runs'],
                                                              facts['game_number'], facts['round'],
                                                              facts['home']['stadium'])
    if facts['date'] is not None:
        first += ' on %s' % facts['date']
    body = [first + '.'] + _details(facts)
    (ww, wl), (lw, ll) = _series_record(w), _series_record(l)
    lead, (a, b) = (l, (lw, ll)) if lw > ww else (w, (ww, wl))
    if facts['series_over']:
        body.append('%s wins the series %d-%d.' % (lead['name'], a, b))
    elif ww == lw:
        body.append('The series is tied %d-%d.' % (ww, lw))
    else:
        body.append('%s leads the series %d-%d.' % (lead['name'], a, b))
    return {'headline': '%s %d, %s %d' % (w['name'], w['runs'], l['name'], l['runs']), 'body': ' '.join(body)}


def post_write(facts, budget, complete, attempts=2):
    """A postseason game story from the model, or post_template when it cannot give one that checks out."""
    return draft(facts, budget, complete, prompt, post_template, attempts)
