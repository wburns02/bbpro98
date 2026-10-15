"""Postseason game stories: match_post, post_facts and post_template on a hand-built bracket, the regular-season facts
unchanged by the split, and Watcher.recaps turning a postseason box score into a recap with its place in the bracket
(gamedata's readers are replaced by dicts, as in test_watch)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import recap     # noqa: E402
import watch     # noqa: E402

TEAMS = {1: {'tid': 1, 'name': 'Ash', 'abbrev': 'ASH', 'city': 'X', 'stadium': 'Ash Park', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [100]},
         2: {'tid': 2, 'name': 'Birch', 'abbrev': 'BIR', 'city': 'X', 'stadium': 'Birch Field', 'manager': 'M',
             'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [200]}}
NAMES = {100: 'Al Winner', 200: 'Bo Loser'}


def game(day, slot, away, home, ar, hr, played=True, innings=9, month=4):
    return {'month': month, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': innings}


def series(best, t1, t2, games):
    """A bracket series from games = [(away, home, away_runs, home_runs)] in played order."""
    gs = [{'away': a, 'home': h, 'away_runs': ar, 'home_runs': hr} for a, h, ar, hr in games]
    wins = {t1: 0, t2: 0}
    for g in gs:
        wins[g['away'] if g['away_runs'] > g['home_runs'] else g['home']] += 1
    need = best // 2 + 1
    winner = t1 if wins[t1] == need else t2 if wins[t2] == need else None
    return {'best_of': best, 'teams': [t1, t2], 'wins': [wins[t1], wins[t2]], 'winner': winner,
            'home': gs[0]['home'] if gs else None, 'games': gs}


def bracket(r1=(), r2=(), r3=()):
    rounds = [{'round': 1, 'series': list(r1)}, {'round': 2, 'series': list(r2)}, {'round': 3, 'series': list(r3)}]
    return {'complete': False, 'current': True, 'best_of': [5, 7, 7], 'champion': None, 'rounds': rounds}


# Ash beat Birch 4-2: Ash wins game 1, Birch game 2, Ash game 3 (2-1), Birch game 4 (2-2), Ash games 5 and 6.
WS_GAMES = [(2, 1, 2, 4), (2, 1, 5, 3), (1, 2, 7, 1), (1, 2, 2, 3), (2, 1, 0, 5), (2, 1, 1, 2)]
WS = series(7, 1, 2, WS_GAMES)


def box_of(away, home, ar, hr):
    """A box score of a game between teams `away` and `home`: the winner's pitcher (tid * 100) has the win."""
    def side(tid, runs, won):
        return {'tid': tid, 'runs': runs, 'hits': runs + 2,
                'batting': [{'ab': 4, 'h': 1, '2b': 0, '3b': 0, 'hr': 0, 'rbi': 0, 'bb': 0, 'so': 0, 'r': 0, 'sb': 0,
                             'pid': tid * 100 + 1}],
                'pitching': [{'outs': 27, 'h': 5, 'r': 2, 'er': 2, 'bb': 1, 'so': 6, 'hr': 0, 'w': int(won),
                              'l': int(not won), 'sv': 0, 'pid': tid * 100}]}
    return {'away': side(away, ar, ar > hr), 'home': side(home, hr, hr > ar)}


def game_box(g):
    return box_of(*g)


def facts_of(i, br=None, sched=None, rnd=3, si=0):
    br = br or bracket(r3=[WS])
    g = br['rounds'][rnd - 1]['series'][si]['games'][i]
    box = box_of(g['away'], g['home'], g['away_runs'], g['home_runs'])
    return recap.post_facts({'name': '1998 Test', 'teams': TEAMS}, box, br, rnd, si, i, NAMES, sched)


# gamedata.postseason_schedule

def srec(flag, month=10, day=20, slot=0, away=1, ar=3, home=2, hr=2, played=True, innings=9, size=17):
    p = bytearray(size)
    p[1:4] = bytes((month, day, slot))
    p[6], p[7], p[10], p[11] = away, ar, home, hr
    p[14], p[15] = (0 if played else 1), flag
    if size > 16:
        p[16] = innings
    return bytes(p)


def test_postseason_schedule_lists_the_flagged_games_in_file_order(tmp_path, monkeypatch):
    path = tmp_path / 'A.ASN'
    path.write_bytes(b'asn')
    recs = [srec(0, month=4, day=1), srec(1, day=21, slot=1, away=2, ar=0, home=1, hr=5), srec(1, played=False, ar=0),
            srec(1, away=0), srec(1, home=gamedata.MAX_TEAM + 1), srec(1, size=16), srec(1, day=19, innings=11)]
    monkeypatch.setattr(gamedata, '_members', lambda data: {'s': [(0, r) for r in recs]})
    assert gamedata.postseason_schedule(str(path)) == [
        {'month': 10, 'day': 21, 'slot': 1, 'away': 2, 'home': 1, 'away_runs': 0, 'home_runs': 5, 'played': True,
         'innings': 9},
        {'month': 10, 'day': 20, 'slot': 0, 'away': 1, 'home': 2, 'away_runs': 0, 'home_runs': 2, 'played': False,
         'innings': 9},
        {'month': 10, 'day': 19, 'slot': 0, 'away': 1, 'home': 2, 'away_runs': 3, 'home_runs': 2, 'played': True,
         'innings': 11}]
    monkeypatch.setattr(gamedata, '_members', lambda data: {})
    assert gamedata.postseason_schedule(str(path)) == []


# match_post

def test_match_post_finds_the_round_series_and_game():
    br = bracket(r1=[series(5, 1, 2, [(1, 2, 9, 8)])], r3=[WS])
    assert recap.match_post(br, game_box(WS_GAMES[2]), set()) == (3, 0, 2)
    assert recap.match_post(br, game_box((1, 2, 9, 8)), set()) == (1, 0, 0)


def test_match_post_skips_used_games_and_takes_rounds_in_order():
    same = (2, 1, 2, 4)
    br = bracket(r1=[series(5, 1, 2, [same, same])], r3=[series(7, 1, 2, [same, same])])
    box = game_box(same)
    assert recap.match_post(br, box, set()) == (1, 0, 0)
    assert recap.match_post(br, box, {(1, 0, 0)}) == (1, 0, 1)
    assert recap.match_post(br, box, {(1, 0, 0), (1, 0, 1)}) == (3, 0, 0)
    assert recap.match_post(br, box, {(1, 0, 0), (1, 0, 1), (3, 0, 0)}) == (3, 0, 1)
    assert recap.match_post(br, box, {(1, 0, 0), (1, 0, 1), (3, 0, 0), (3, 0, 1)}) is None


def test_match_post_needs_the_same_teams_sides_and_score():
    br = bracket(r3=[WS])
    assert recap.match_post(br, game_box((1, 2, 7, 2)), set()) is None          # score
    assert recap.match_post(br, game_box((2, 1, 7, 1)), set()) is None          # sides swapped
    assert recap.match_post(bracket(), game_box(WS_GAMES[0]), set()) is None    # nothing in the bracket
    box = game_box(WS_GAMES[0])
    box['away']['tid'] = None
    assert recap.match_post(br, box, set()) is None


# post_facts

def test_series_records_after_the_first_game():
    f = facts_of(0)
    assert (f['round'], f['game_number'], f['best_of'], f['series_over']) == ('World Series', 1, 7, False)
    assert (f['away']['name'], f['away']['record'], f['home']['name'], f['home']['record']) == (
        'Birch', '0-1', 'Ash', '1-0')
    assert f['winner'] == 'home' and f['home']['stadium'] == 'Ash Park'


def test_series_records_through_each_game_not_after_it():
    assert [(f['away']['record'], f['home']['record']) for f in (facts_of(i) for i in range(3))] == [
        ('0-1', '1-0'), ('1-1', '1-1'), ('2-1', '1-2')]


def test_clinching_game_ends_the_series():
    f = facts_of(5)
    assert f['game_number'] == 6 and f['series_over'] is True
    assert (f['away']['record'], f['home']['record']) == ('2-4', '4-2')
    assert [facts_of(i)['series_over'] for i in range(5)] == [False] * 5


def test_series_over_follows_the_best_of():
    sweep = series(5, 1, 2, [(1, 2, 3, 1), (2, 1, 0, 4), (1, 2, 5, 2)])
    br = bracket(r1=[sweep])
    assert [facts_of(i, br, rnd=1)['series_over'] for i in range(3)] == [False, False, True]
    f = facts_of(2, br, rnd=1)
    assert (f['round'], f['best_of'], f['away']['record'], f['home']['record']) == (
        'Division Series', 5, '3-0', '0-3')


def test_series_index_picks_the_series():
    other = series(5, 1, 2, [(1, 2, 0, 1)])
    f = facts_of(0, bracket(r2=[other, series(7, 1, 2, [(1, 2, 4, 3)])]), rnd=2, si=1)
    assert f['round'] == 'League Championship Series' and f['winner'] == 'away'
    assert (f['away']['record'], f['home']['record']) == ('1-0', '0-1')


def test_no_schedule_game_means_no_date_and_nine_innings():
    f = facts_of(0)
    assert f['date'] is None and f['innings'] == 9


def test_schedule_game_gives_date_and_innings():
    f = facts_of(0, sched=game(20, 0, 2, 1, 2, 4, innings=11, month=10))
    assert f['date'] == 'October 20' and f['innings'] == 11 and 'extra innings' in f['notes']


# post_template

def test_template_after_game_three_has_the_leader_and_the_series_score():
    f = facts_of(2, sched=game(22, 0, 1, 2, 7, 1, month=10))
    t = recap.post_template(f)
    assert t['headline'] == 'Ash 7, Birch 1'
    assert t['body'].startswith('Ash beat Birch 7-1 in Game 3 of the World Series at Birch Field on October 22.')
    assert t['body'].endswith('Ash leads the series 2-1.')


def test_template_tied_series():
    t = recap.post_template(facts_of(1))
    assert t['headline'] == 'Birch 5, Ash 3'
    assert t['body'].endswith('The series is tied 1-1.')


def test_template_clinching_game():
    t = recap.post_template(facts_of(5, sched=game(25, 0, 2, 1, 1, 2, month=10)))
    assert t['body'].endswith('Ash wins the series 4-2.')
    assert 'in Game 6 of the World Series at Ash Park on October 25.' in t['body']


def test_template_names_the_leader_when_the_winner_trails():
    t = recap.post_template(facts_of(3))        # Birch evens it 2-2
    assert t['body'].endswith('The series is tied 2-2.')
    br = bracket(r3=[series(7, 1, 2, [(2, 1, 1, 4), (2, 1, 0, 3), (1, 2, 5, 2)])])      # Ash 2-0, then Ash again
    assert recap.post_template(facts_of(2, br))['body'].endswith('Ash leads the series 3-0.')
    br = bracket(r3=[series(7, 1, 2, [(2, 1, 1, 4), (2, 1, 0, 3), (1, 2, 2, 5)])])       # Birch wins game 3
    assert recap.post_template(facts_of(2, br))['body'].endswith('Ash leads the series 2-1.')


def test_template_without_a_date_has_no_date_clause():
    body = recap.post_template(facts_of(0))['body']
    assert body.startswith('Ash beat Birch 4-2 in Game 1 of the World Series at Ash Park.')
    assert ' on ' not in body


def test_template_numbers_pass_numbers_ok():
    dated = game(20, 0, 2, 1, 2, 4, innings=11, month=10)
    for i in range(len(WS_GAMES)):
        for sched in (None, dated):
            f = facts_of(i, sched=sched)
            t = recap.post_template(f)
            assert recap.numbers_ok(t['body'], f) and recap.numbers_ok(t['headline'], f), (i, t)
    sweep = series(5, 1, 2, [(1, 2, 3, 1), (2, 1, 0, 4), (1, 2, 5, 2)])
    for i in range(3):
        f = facts_of(i, bracket(r1=[sweep]), rnd=1)
        assert recap.numbers_ok(recap.post_template(f)['body'], f)


def test_post_write_uses_the_model_and_falls_back_to_the_template():
    f = facts_of(2, sched=game(22, 0, 1, 2, 7, 1, month=10))
    good = lambda system, user, budget: ('Ash take Game 3\n\nAsh beat Birch 7-1 in Game 3.', {})
    bad = lambda system, user, budget: ('Ash take Game 3\n\nAsh beat Birch 77-1 in Game 3.', {})
    assert recap.post_write(f, None, good)['source'] == 'glm'
    story = recap.post_write(f, None, bad)
    assert (story['source'], story['reason']) == ('template', 'numbers')
    assert story['body'] == recap.post_template(f)['body']


# the regular-season path is unchanged

REG_ASSOC = {'name': '1998 Test', 'teams': TEAMS,
             'games': [game(1, 0, 1, 2, 3, 1), game(2, 0, 2, 1, 0, 5), game(3, 0, 1, 2, 6, 2, innings=11)]}


def reg_box():
    def bat(pid, **k):
        d = {'ab': 4, 'h': 0, '2b': 0, '3b': 0, 'hr': 0, 'rbi': 0, 'bb': 0, 'so': 0, 'r': 0, 'sb': 0, 'pid': pid}
        return dict(d, **k)

    def pit(pid, **k):
        d = {'outs': 27, 'h': 5, 'r': 2, 'er': 2, 'bb': 1, 'so': 6, 'hr': 0, 'w': 0, 'l': 0, 'sv': 0, 'pid': pid}
        return dict(d, **k)
    return {'away': {'tid': 1, 'runs': 6, 'hits': 9, 'batting': [bat(100, h=3, hr=2, rbi=4, r=2), bat(101, h=1)],
                     'pitching': [pit(110, w=1, outs=24), pit(111, sv=1, outs=3)]},
            'home': {'tid': 2, 'runs': 2, 'hits': 5, 'batting': [bat(200, h=3, rbi=1, sb=2)],
                     'pitching': [pit(210, l=1, outs=33)]}}


# Built by the game_facts and template of the commit before the split.
REG_FACTS = {
    'association': '1998 Test', 'date': 'April 3', 'innings': 11,
    'away': {'name': 'Ash', 'abbrev': 'ASH', 'runs': 6, 'hits': 9, 'record': '3-0'},
    'home': {'name': 'Birch', 'abbrev': 'BIR', 'runs': 2, 'hits': 5, 'record': '0-3', 'stadium': 'Birch Field'},
    'winner': 'away',
    'batters': [{'team': 'ASH', 'name': 'Al Winner', 'ab': 4, 'h': 3, '2b': 0, '3b': 0, 'hr': 2, 'rbi': 4, 'bb': 0,
                 'r': 2, 'sb': 0},
                {'team': 'BIR', 'name': 'Bo Loser', 'ab': 4, 'h': 3, '2b': 0, '3b': 0, 'hr': 0, 'rbi': 1, 'bb': 0,
                 'r': 0, 'sb': 2}],
    'decisions': {'win': {'team': 'ASH', 'name': 'Di Starter', 'ip': '8.0', 'h': 5, 'r': 2, 'er': 2, 'bb': 1, 'so': 6},
                  'loss': {'team': 'BIR', 'name': 'Fy Pitcher', 'ip': '11.0', 'h': 5, 'r': 2, 'er': 2, 'bb': 1,
                           'so': 6},
                  'save': {'team': 'ASH', 'name': 'Ed Closer', 'ip': '1.0', 'h': 5, 'r': 2, 'er': 2, 'bb': 1,
                           'so': 6}},
    'notes': ['extra innings', 'Al Winner hit 2 home runs']}
REG_STORY = {
    'headline': 'Ash 6, Birch 2',
    'body': 'Ash beat Birch 6-2 at Birch Field on April 3. It took 11 innings. Al Winner went 3-for-4 with 2 home '
            'runs and 4 RBI. Bo Loser went 3-for-4 with 1 RBI. Di Starter got the win, allowing 2 runs over 8.0 '
            'innings. Ed Closer earned the save over 1.0 innings. Ash is 3-0; Birch is 0-3.'}


def test_game_facts_and_template_of_a_regular_game_are_unchanged():
    names = {100: 'Al Winner', 101: 'Cy Extra', 110: 'Di Starter', 111: 'Ed Closer', 200: 'Bo Loser',
             210: 'Fy Pitcher'}
    facts = recap.game_facts(REG_ASSOC, reg_box(), REG_ASSOC['games'][2], names)
    assert facts == REG_FACTS
    assert recap.template(facts) == REG_STORY


# Watcher.recaps

@pytest.fixture
def world(tmp_path, monkeypatch):
    gd = tmp_path / 'game'
    (gd / 'Assn').mkdir(parents=True)
    (gd / 'Stats').mkdir()
    (gd / 'Assn' / '30L1998.ASN').write_bytes(b'asn')
    st = {'games': [game(1, 0, 1, 2, 3, 1), game(2, 0, 2, 1, 0, 5), game(3, 0, 1, 2, 0, 0, played=False)],
          'boxes': {}, 'bracket': None, 'sched': [], 'asn_paths': []}

    def boxfile(name, box):
        p = gd / 'Stats' / name
        p.write_bytes(json.dumps(box).encode())
        os.utime(p, (1, 1))                 # settled long ago
        st['boxes'][str(p)] = box

    monkeypatch.setattr(gamedata, 'association', lambda path: {'name': '1998 Test', 'teams': TEAMS,
                                                              'games': [dict(g) for g in st['games']]})
    monkeypatch.setattr(gamedata, 'names', lambda path: NAMES)
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: {'bat': {}, 'pit': {}})
    monkeypatch.setattr(gamedata, 'boxscore', lambda path: st['boxes'][str(path)])
    st['boxfile'] = boxfile
    return gd, tmp_path / 'data', st


@pytest.fixture
def post_world(world, monkeypatch):
    gd, data, st = world
    st['bracket'] = bracket(r3=[WS])

    def postseason(path):
        st['asn_paths'].append(os.path.basename(path))
        return st['bracket']

    monkeypatch.setattr(gamedata, 'postseason', postseason)
    monkeypatch.setattr(gamedata, 'postseason_schedule', lambda path: [dict(g) for g in st['sched']])
    return gd, data, st


def recaps_of(data):
    d = data / '30L1998' / 'recaps'
    return [json.loads(p.read_text()) for p in sorted(d.iterdir())] if d.is_dir() else []


def watcher(gd, data, logs):
    return watch.Watcher(str(gd), str(data), None, None, log=logs.append)


def scan_again(w):
    w.seen.clear()
    w.scan()


def unmatched(logs):
    return [m for m in logs if 'matches no unreported' in m]


def test_postseason_box_becomes_a_recap_with_its_place_in_the_bracket(post_world):
    gd, data, st = post_world
    st['sched'] = [game(20 + i, 0, a, h, ar, hr, month=10) for i, (a, h, ar, hr) in enumerate(WS_GAMES)]
    st['boxfile']('30L1998.H10', game_box(WS_GAMES[5]))
    logs = []
    w = watcher(gd, data, logs)
    w.scan()
    [r] = recaps_of(data)
    assert r['post'] == {'round': 3, 'series': 0, 'game': 5}
    assert (r['month'], r['day'], r['slot']) == (10, 25, 0)
    assert (r['source'], r['reason'], r['assn'], r['file']) == ('template', 'off', '30L1998', '30L1998.H10')
    assert r['headline'] == 'Ash 2, Birch 1'
    assert 'in Game 6 of the World Series at Ash Park on October 25.' in r['body']
    assert r['body'].endswith('Ash wins the series 4-2.')
    assert r['facts']['game_number'] == 6 and r['facts']['series_over'] is True
    assert os.listdir(data / '30L1998' / 'pending') == [] and unmatched(logs) == []
    assert st['asn_paths'] and set(st['asn_paths']) == {'30L1998.ASN'}
    assert any('-> ' + r['key'] in m for m in logs)


def test_the_same_bracket_game_is_not_written_twice(post_world):
    gd, data, st = post_world
    st['sched'] = [game(20 + i, 0, a, h, ar, hr, month=10) for i, (a, h, ar, hr) in enumerate(WS_GAMES)]
    box = game_box(WS_GAMES[5])
    st['boxfile']('30L1998.H10', box)
    logs = []
    w = watcher(gd, data, logs)
    w.scan()
    scan_again(w)
    assert len(recaps_of(data)) == 1
    # A second box score of that game (same teams and score) has no bracket game left to be.
    st['boxfile']('30L1998.H11', dict(box, extra=1))
    scan_again(w)
    scan_again(w)
    assert len(recaps_of(data)) == 1 and len(unmatched(logs)) == 1


def test_a_fresh_watcher_reads_the_used_games_from_the_recaps(post_world):
    gd, data, st = post_world
    box = game_box(WS_GAMES[5])
    st['boxfile']('30L1998.H10', box)
    watcher(gd, data, []).scan()
    st['boxfile']('30L1998.H11', dict(box, extra=1))
    logs = []
    scan_again(watcher(gd, data, logs))
    assert len(recaps_of(data)) == 1 and len(unmatched(logs)) == 1


def test_two_games_with_the_same_teams_and_score_map_to_different_games(post_world):
    gd, data, st = post_world
    twice = (2, 1, 2, 4)
    st['bracket'] = bracket(r3=[series(7, 1, 2, [twice, twice, (1, 2, 7, 1)])])
    st['sched'] = [game(20, 0, *twice, month=10), game(21, 0, *twice, month=10), game(22, 0, 1, 2, 7, 1, month=10)]
    st['boxfile']('30L1998.H10', game_box(twice))
    st['boxfile']('30L1998.H11', dict(game_box(twice), extra=1))
    w = watcher(gd, data, [])
    w.scan()
    got = recaps_of(data)
    assert sorted((r['post']['game'], r['day']) for r in got) == [(0, 20), (1, 21)]
    scan_again(w)
    assert len(recaps_of(data)) == 2


def test_no_schedule_record_sorts_after_the_regular_season_and_has_no_date(post_world):
    gd, data, st = post_world
    g = (1, 2, 4, 3)
    st['bracket'] = bracket(r1=[series(5, 1, 2, [(1, 2, 9, 8)]), series(5, 1, 2, [(2, 1, 1, 0), g])])
    st['boxfile']('30L1998.H10', game_box(g))
    w = watcher(gd, data, [])
    w.scan()
    [r] = recaps_of(data)
    assert r['post'] == {'round': 1, 'series': 1, 'game': 1}
    assert (r['month'], r['day'], r['slot']) == (4, 2, 100 + 8 + 1)
    assert r['facts']['date'] is None and ' on ' not in r['body']
    assert r['body'].startswith('Ash beat Birch 4-3 in Game 2 of the Division Series at Birch Field.')
    assert isinstance(r['month'], int) and isinstance(r['day'], int) and isinstance(r['slot'], int)
    scan_again(w)
    assert len(recaps_of(data)) == 1


@pytest.mark.parametrize('rnd,si,gi,slot', [(1, 0, 0, 100), (1, 3, 2, 126), (2, 1, 3, 161), (3, 0, 5, 205)])
def test_slot_without_a_schedule_record_follows_round_series_and_game(post_world, rnd, si, gi, slot):
    gd, data, st = post_world
    target, filler = (1, 2, 13, 12), (2, 1, 0, 1)
    rounds = {1: [], 2: [], 3: []}
    rounds[rnd] = [series(7, 1, 2, [filler])] * si + [series(7, 1, 2, [filler] * gi + [target])]
    st['bracket'] = bracket(rounds[1], rounds[2], rounds[3])
    st['boxfile']('30L1998.H10', game_box(target))
    watcher(gd, data, []).scan()
    [r] = recaps_of(data)
    assert r['post'] == {'round': rnd, 'series': si, 'game': gi}
    assert (r['month'], r['day'], r['slot']) == (4, 2, slot)


def test_box_that_fits_nothing_is_logged_once_and_kept_pending(post_world):
    gd, data, st = post_world
    st['boxfile']('30L1998.H10', game_box((1, 2, 11, 10)))
    logs = []
    w = watcher(gd, data, logs)
    w.scan()
    scan_again(w)
    assert recaps_of(data) == [] and len(os.listdir(data / '30L1998' / 'pending')) == 1
    assert len(unmatched(logs)) == 1 and '30L1998.H10' in unmatched(logs)[0]


def test_no_bracket_is_the_old_behaviour(post_world):
    gd, data, st = post_world
    st['bracket'] = None
    st['boxfile']('30L1998.H10', game_box(WS_GAMES[5]))
    logs = []
    watcher(gd, data, logs).scan()
    assert recaps_of(data) == [] and len(unmatched(logs)) == 1


def test_unreadable_asn_leaves_the_box_waiting(world):
    gd, data, st = world           # gamedata.postseason is the real one, and the ASN file is not one
    st['boxfile']('30L1998.H10', game_box(WS_GAMES[5]))
    logs = []
    watcher(gd, data, logs).scan()
    assert recaps_of(data) == [] and len(unmatched(logs)) == 1
    assert not [m for m in logs if 'Error' in m]


def test_regular_games_still_get_regular_recaps(post_world):
    gd, data, st = post_world
    st['boxfile']('30L1998.H10', game_box((1, 2, 3, 1)))
    st['boxfile']('30L1998.H11', game_box(WS_GAMES[0]))
    watcher(gd, data, []).scan()
    got = {r['file']: r for r in recaps_of(data)}
    assert 'post' not in got['30L1998.H10'] and got['30L1998.H10']['day'] == 1
    assert got['30L1998.H11']['post'] == {'round': 3, 'series': 0, 'game': 0}
