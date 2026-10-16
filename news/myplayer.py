"""My Player for the news sidecar: follow up to MAX_FOLLOW players of an association and keep a page on each, with a
game log, his milestones, the offseason focus as a training plan and a weekly column. Pure functions over plain dicts;
the watcher (watch.py) reads and writes the files, the bridge (modbridge.py) toggles the follow list and the server
(server.py) shows the pages. The model is reached only through the complete() callable the caller passes in. Prompt
rules and the number check are recap's.

<data>/<STEM>/follow.json is {"kind": "follow", "players": [{"pid", "birth", "since"}]}, oldest first.
<data>/<STEM>/player/<pid>.json is the page data: pid, name, season_year, games, columns, updated, and what
watch.follow_piece adds (team, pos, age, season, career, contract, plan, arc, milestones).
"""
import feed
import recap

KIND = 'follow'
MAX_FOLLOW = 3          # players followed per association; a fourth follow replaces the oldest
FOLLOW_CALLS = 2        # weekly columns asked of the model per scan, across the followed players
WEEK = 6                # games logged after the last column that make the next one
MILESTONES = 20         # milestones kept on a page
SYSTEM = ("You are a newspaper baseball writer following one player through the season: 50 to 90 words on his last "
          "games and his season so far, using only the facts given. Name him as in the facts. " + recap.RULES)
NO_PLAN = 'No offseason plan set.'


def _int(value):
    return value if type(value) is int else None


def _n(obj, key):
    """obj[key] as an int; 0 for a missing key, a value that is not an int (bool included) or an obj not a dict."""
    value = obj.get(key) if isinstance(obj, dict) else None
    return value if type(value) is int else 0


def empty():
    """The follow list with nobody in it: what a missing or bad file reads as."""
    return {'kind': KIND, 'players': []}


def parse(obj):
    """The follow doc in obj (a decoded follow.json) as a new dict: the empty doc unless obj is a dict of kind 'follow'
    with a list of players. An entry that is not a dict with a positive int 'pid' is dropped, and so is an earlier entry
    for a pid a later one repeats. 'birth' is an int or None, 'since' a string ('' when it is not one). Only the newest
    MAX_FOLLOW entries are kept."""
    if not isinstance(obj, dict) or obj.get('kind') != KIND or not isinstance(obj.get('players'), list):
        return empty()
    kept = {}
    for p in obj['players']:
        pid = p.get('pid') if isinstance(p, dict) else None
        if type(pid) is int and pid > 0:
            kept.pop(pid, None)
            kept[pid] = {'pid': pid, 'birth': _int(p.get('birth')),
                         'since': p['since'] if isinstance(p.get('since'), str) else ''}
    return {'kind': KIND, 'players': list(kept.values())[-MAX_FOLLOW:]}


def add(doc, pid, birth, now):
    """A new doc that follows pid (born on birth serial `birth`, None when unknown) since the iso time `now`. Following
    the same (pid, birth) again changes nothing; the same pid with another birth (the id reused by a new player)
    replaces the old entry. The newest entry goes last, and when that makes more than MAX_FOLLOW the oldest are dropped.
    doc is not changed."""
    players = parse(doc)['players']
    if any(p['pid'] == pid and p['birth'] == birth for p in players):
        return {'kind': KIND, 'players': players}
    players = [p for p in players if p['pid'] != pid] + [{'pid': pid, 'birth': birth, 'since': now}]
    return {'kind': KIND, 'players': players[-MAX_FOLLOW:]}


def remove(doc, pid):
    """A new doc without pid; the same list when he was not followed. doc is not changed."""
    return {'kind': KIND, 'players': [p for p in parse(doc)['players'] if p['pid'] != pid]}


def followed(doc):
    """{pid: birth serial or None} for the players doc follows, oldest first."""
    return {p['pid']: p['birth'] for p in parse(doc)['players']}


def matching(follows, births):
    """follows ({pid: birth}) without the players the PYR contradicts. births is {pid: birth serial} (focus.births): a
    pid it does not hold is dropped, and so is one it holds with another birth serial (the id reused by a new player);
    a follow with no birth (None) matches any holder of the pid. births None (the PYR could not be read) drops
    nothing."""
    if births is None:
        return dict(follows)
    return {pid: birth for pid, birth in follows.items()
            if pid in births and (birth is None or births[pid] == birth)}


def game_line(box, game, pid, abbrevs):
    """One game of the log for pid from a box score (gamedata.boxscore) matched to its schedule game, or None when
    he has no batting or pitching line in it. {'month', 'day', 'slot'} come from game; 'opp' is the abbreviation
    abbrevs ({tid: abbrev}) gives for the other side's tid ('' when it has none) and 'home' is True when he has a
    line on the home side; 'bat' and 'pit' are his box lines as given (a pitching line carries 'outs', not 'ip') or
    None."""
    bat = pit = None
    home = False
    for side in ('away', 'home'):
        b = next((x for x in box[side].get('batting', []) if x.get('pid') == pid), None)
        p = next((x for x in box[side].get('pitching', []) if x.get('pid') == pid), None)
        if b is not None or p is not None:
            bat, pit, home = bat or b, pit or p, side == 'home'
    if bat is None and pit is None:
        return None
    other = game['away'] if home else game['home']
    return {'month': game['month'], 'day': game['day'], 'slot': game['slot'], 'opp': abbrevs.get(other, ''),
            'home': home, 'bat': dict(bat) if bat is not None else None, 'pit': dict(pit) if pit is not None else None}


def _when(g):
    return g.get('month'), g.get('day'), g.get('slot')


def append_game(games, line):
    """A new game list with line added, in schedule order, unless the list already has a game with the same (month, day,
    slot). games is not changed."""
    kept = [g for g in games if isinstance(g, dict)]
    if any(_when(g) == _when(line) for g in kept):
        return kept
    return sorted(kept + [line], key=lambda g: tuple(v if type(v) is int else 0 for v in _when(g)))


def new_page(pid, name, year):
    """The page data of a player with no games yet."""
    return {'pid': pid, 'name': name, 'season_year': year, 'games': [], 'columns': []}


def rolled(page, year):
    """True when page holds another season than `year`: both are ints and differ. A page or a year that does not say
    which season it is never rolls."""
    return type(page.get('season_year')) is int and type(year) is int and page['season_year'] != year


def window(games, columns):
    """The games a weekly column covers: those after the newest column's 'through' (month, day), or all of them when
    there is no column. [] while that is fewer than WEEK games."""
    done = None
    last = columns[-1] if columns and isinstance(columns[-1], dict) else None
    through = last.get('through') if last else None
    if isinstance(through, list) and len(through) == 2 and all(type(v) is int for v in through):
        done = tuple(through)
    new = [g for g in games if isinstance(g, dict) and type(g.get('month')) is int and type(g.get('day')) is int
           and (done is None or (g['month'], g['day']) > done)]
    return new if len(new) >= WEEK else []


def through_of(games):
    """[month, day] of the last game of a non-empty game list."""
    last = games[-1]
    return [last['month'], last['day']]


def _avg(h, ab):
    return feed._bare('%.3f' % (h / ab)) if ab else '---'


def _era(er, outs):
    return '%.2f' % (27 * er / outs) if outs else '---'


def week_facts(name, games, season_line, team_record):
    """What a weekly column may say. games are the game-log entries of the window (n = len(games)), season_line is
    {'bat': line or None, 'pit': line or None} (gamedata.season_lines lines) and team_record {'w', 'l'}. 'kind' is 'pit'
    when any game has a pitching line, else 'bat'. A hitter's facts: 'ab', 'h', 'hr', 'rbi' summed over the games'
    batting lines (a missing key counts 0), and 'season_avg' ('.300', '---' without at-bats), 'season_hr', 'season_rbi'.
    A pitcher's: 'ip' (recap.ip of the summed outs), 'era' ('%.2f' of 27 * er / outs, '---' without outs), 'season_ip'
    and 'season_era'."""
    facts = {'name': name, 'kind': 'pit' if any(g.get('pit') is not None for g in games) else 'bat', 'n': len(games),
             'team_w': _n(team_record, 'w'), 'team_l': _n(team_record, 'l')}
    if facts['kind'] == 'pit':
        outs = sum(_n(g.get('pit'), 'outs') for g in games)
        er = sum(_n(g.get('pit'), 'er') for g in games)
        line = season_line.get('pit')
        facts.update(ip=recap.ip(outs), era=_era(er, outs), season_ip=recap.ip(_n(line, 'outs')),
                     season_era=_era(_n(line, 'er'), _n(line, 'outs')))
        return facts
    for key in ('ab', 'h', 'hr', 'rbi'):
        facts[key] = sum(_n(g.get('bat'), key) for g in games)
    line = season_line.get('bat')
    facts.update(season_avg=_avg(_n(line, 'h'), _n(line, 'ab')), season_hr=_n(line, 'hr'),
                 season_rbi=_n(line, 'rbi'))
    return facts


def template(facts):
    """A column built only from the facts: the headline "<Name>'s week" and two sentences, on the games and on the
    season. Every number in it passes recap.numbers_ok."""
    name = facts['name']
    if facts['kind'] == 'pit':
        body = ('%s pitched %s innings over %d games with a %s ERA. %s has a %s ERA over %s innings on the season.'
                % (name, facts['ip'], facts['n'], facts['era'], name, facts['season_era'], facts['season_ip']))
    else:
        body = ("%s went %d for %d with %d home runs and %d RBI over his team's last %d games. %s is hitting %s with "
                '%d home runs and %d RBI on the season.'
                % (name, facts['h'], facts['ab'], facts['hr'], facts['rbi'], facts['n'], name, facts['season_avg'],
                   facts['season_hr'], facts['season_rbi']))
    return {'headline': "%s's week" % name, 'body': body}


def prompt(facts):
    """(system, user) for a weekly column."""
    return SYSTEM, recap.facts_message(facts)


def write(facts, budget, complete, attempts=2):
    """A weekly column from the model, or the template when it cannot give one that checks out."""
    return recap.draft(facts, budget, complete, prompt, template, attempts)


def column(piece, facts, games):
    """The entry for a page's 'columns' from a written piece ({'body', 'source', ...}) over the window `games`."""
    return {'through': through_of(games), 'text': piece['body'], 'source': piece['source'], 'facts': facts}


def plan_text(entry):
    """The page's training plan line for a focus.find entry (or None): 'Offseason training plan: contact' or NO_PLAN."""
    return 'Offseason training plan: %s' % entry['kind'] if entry else NO_PLAN


def milestones(events, pid, limit=MILESTONES):
    """The events of a moves log for pid, newest first (the log is oldest first), at most `limit`."""
    mine = [e for e in events if isinstance(e, dict) and e.get('pid') == pid]
    return mine[::-1][:limit]


def bat_text(line):
    """A batting line as words: '2-for-4, 1 HR, 3 RBI' (a count of 0 is left out). A count not an int reads as 0."""
    text = '%d-for-%d' % (_n(line, 'h'), _n(line, 'ab'))
    for key, label in (('hr', 'HR'), ('rbi', 'RBI'), ('sb', 'SB')):
        if _n(line, key):
            text += ', %d %s' % (_n(line, key), label)
    return text


def pit_text(line):
    """A pitching line as words: '6.1 IP, 2 ER, 7 SO, W'."""
    text = '%s IP, %d ER, %d SO' % (recap.ip(_n(line, 'outs')), _n(line, 'er'), _n(line, 'so'))
    for key, label in (('w', 'W'), ('l', 'L'), ('sv', 'SV')):
        if _n(line, key):
            text += ', ' + label
    return text


def line_text(game):
    """The game-log line of one game: the batting words, then the pitching words, '; ' between; '' for neither."""
    parts = []
    if isinstance(game, dict):
        if isinstance(game.get('bat'), dict):
            parts.append(bat_text(game['bat']))
        if isinstance(game.get('pit'), dict):
            parts.append(pit_text(game['pit']))
    return '; '.join(parts)


def stat_text(line, kind):
    """A season or career line (kind 'bat' or 'pit') as words: a hitter's '.300 AVG, 3 HR, 9 RBI', a pitcher's '3-1,
    3.20 ERA, 40.1 IP, 35 SO' (', 2 SV' after it for saves), then ' in 20 games' when the line counts games. '' when
    line is not a dict or has no at-bats (hitter) or outs (pitcher)."""
    if not isinstance(line, dict):
        return ''
    games = ' in %d games' % _n(line, 'g') if _n(line, 'g') > 0 else ''
    if kind == 'pit':
        if _n(line, 'outs') <= 0:
            return ''
        text = '%d-%d, %s ERA, %s IP, %d SO' % (_n(line, 'w'), _n(line, 'l'), _era(_n(line, 'er'), _n(line, 'outs')),
                                                 recap.ip(_n(line, 'outs')), _n(line, 'so'))
        return text + (', %d SV' % _n(line, 'sv') if _n(line, 'sv') else '') + games
    if _n(line, 'ab') <= 0:
        return ''
    return '%s AVG, %d HR, %d RBI%s' % (_avg(_n(line, 'h'), _n(line, 'ab')), _n(line, 'hr'), _n(line, 'rbi'), games)
