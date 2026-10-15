"""The postseason 'Around the league' column: feed.post_day_facts / post_template / post_write on hand-built brackets,
and Watcher.columns writing one feed file per played postseason date (_postseason and gamedata's readers are stubbed,
so no game files are needed)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import feed      # noqa: E402
import gamedata  # noqa: E402
import hive      # noqa: E402
import recap     # noqa: E402
import watch     # noqa: E402

NAMES = {1: 'Ash', 2: 'Birch', 3: 'Cedar', 4: 'Dogwood'}


def team(tid):
    return {'tid': tid, 'name': NAMES[tid], 'abbrev': NAMES[tid][:3].upper(), 'city': 'X',
            'stadium': NAMES[tid] + ' Park', 'manager': 'M', 'league': 'AL', 'division': 'East', 'w': 0, 'l': 0, 'roster': [tid * 100]}


TEAMS = {tid: team(tid) for tid in NAMES}


def gm(month, day, slot, away, home, ar, hr, played=True, innings=9):
    return {'month': month, 'day': day, 'slot': slot, 'away': away, 'home': home, 'away_runs': ar, 'home_runs': hr,
            'played': played, 'innings': innings}


def assoc(games=()):
    return {'name': '1998 Test', 'teams': TEAMS, 'games': list(games)}


def bracket(*rounds):
    """rounds = [(round number, [(best_of, t1, t2), ...]), ...]; wins and games are not read by post_day_facts."""
    return {'complete': False, 'current': True, 'best_of': [3, 5, 7], 'champion': None,
            'rounds': [{'round': n, 'series': [{'best_of': b, 'teams': [t1, t2], 'wins': [0, 0], 'winner': None,
                                                'home': t1, 'games': []} for b, t1, t2 in ss]}
                       for n, ss in rounds]}


# Ash-Birch is best of 3 (Ash: 1 win Oct 1, 2 wins Oct 2, Birch wins Oct 3); Cedar-Dogwood is best of 5.
DIV = bracket((1, [(3, 1, 2), (5, 3, 4)]))
SCHED = [gm(10, 1, 0, 2, 1, 3, 5),       # Ash 5, Birch 3
         gm(10, 1, 1, 3, 4, 2, 6),       # Dogwood 6, Cedar 2
         gm(10, 2, 1, 4, 3, 1, 4),       # Cedar 4, Dogwood 1
         gm(10, 2, 0, 2, 1, 0, 2),       # Ash 2, Birch 0 (slot 0, listed after slot 1)
         gm(10, 3, 0, 1, 2, 1, 7)]       # Birch 7, Ash 1


def series_of(facts):
    return [(s['teams'], s['wins'], s['best_of'], s['over'], s['leader']) for s in facts['series']]


def test_facts_results_in_slot_order_in_the_day_page_shape():
    f = feed.post_day_facts(assoc(), DIV, SCHED, 10, 2)
    assert (f['association'], f['date'], f['kind']) == ('1998 Test', 'October 2', 'postseason')
    assert f['results'] == [
        {'away': 'Birch', 'home': 'Ash', 'away_runs': 0, 'home_runs': 2, 'innings': 9},
        {'away': 'Dogwood', 'home': 'Cedar', 'away_runs': 1, 'home_runs': 4, 'innings': 9}]


def test_facts_series_count_only_games_through_the_date():
    one = feed.post_day_facts(assoc(), DIV, SCHED, 10, 1)
    assert series_of(one) == [(['Ash', 'Birch'], [1, 0], 3, False, 'Ash'),
                              (['Cedar', 'Dogwood'], [0, 1], 5, False, 'Dogwood')]
    assert [s['round'] for s in one['series']] == ['Division Series'] * 2
    two = feed.post_day_facts(assoc(), DIV, SCHED, 10, 2)       # the Oct 3 game is not counted
    assert series_of(two) == [(['Ash', 'Birch'], [2, 0], 3, True, 'Ash'),
                              (['Cedar', 'Dogwood'], [1, 1], 5, False, None)]
    three = feed.post_day_facts(assoc(), DIV, SCHED, 10, 3)     # only the series that met that day
    assert series_of(three) == [(['Ash', 'Birch'], [2, 1], 3, True, 'Ash')]


def test_facts_leader_follows_the_team_order_of_the_series():
    flipped = bracket((3, [(7, 2, 1)]))
    f = feed.post_day_facts(assoc(), flipped, SCHED[:1], 10, 1)
    assert series_of(f) == [(['Birch', 'Ash'], [0, 1], 7, False, 'Ash')] and f['series'][0]['round'] == 'World Series'


def test_facts_skip_series_that_did_not_meet_and_teams_that_are_unknown():
    b = bracket((1, [(3, 1, 99), (5, 3, 4)]), (2, [(5, 1, 3)]), (9, [(3, 1, 2)]))
    sched = SCHED + [gm(10, 2, 2, 99, 1, 5, 4)]
    f = feed.post_day_facts(assoc(), b, sched, 10, 2)
    assert len(f['results']) == 2                                   # the game with team 99 is no result
    assert series_of(f) == [(['Cedar', 'Dogwood'], [1, 1], 5, False, None), (['Ash', 'Birch'], [2, 0], 3, True, 'Ash')]
    assert [s['round'] for s in f['series']] == ['Division Series', 'Postseason']


def test_facts_ignore_unplayed_ties_and_games_with_a_missing_key():
    sched = [gm(10, 1, 0, 2, 1, 3, 5), gm(10, 1, 1, 2, 1, 4, 4), gm(10, 1, 2, 2, 1, 0, 0, played=False),
             {k: v for k, v in gm(10, 1, 3, 2, 1, 9, 9).items() if k != 'innings'},
             {k: v for k, v in gm(10, 1, 4, 2, 1, 9, 9).items() if k != 'played'}]
    f = feed.post_day_facts(assoc(), bracket((1, [(5, 1, 2)])), sched, 10, 1)
    assert len(f['results']) == 2
    assert series_of(f) == [(['Ash', 'Birch'], [1, 0], 5, False, 'Ash')]       # the tie is no win for anyone


def test_facts_without_a_bracket_have_results_and_no_series():
    f = feed.post_day_facts(assoc(), None, SCHED, 10, 1)
    assert f['series'] == [] and len(f['results']) == 2 and f['kind'] == 'postseason'


def test_template_leads_wins_and_tied_sentences():
    f = feed.post_day_facts(assoc(), DIV, SCHED, 10, 2)
    t = feed.post_template(f)
    assert t['headline'] == 'Division Series'
    assert t['body'] == 'Ash 2, Birch 0. Cedar 4, Dogwood 1.\nAsh wins the Division Series 2-0. ' \
                        'The Division Series is tied 1-1.'
    led = feed.post_template(feed.post_day_facts(assoc(), DIV, SCHED, 10, 1))
    assert led['body'].split('\n')[1] == 'Ash leads the Division Series 1-0. Dogwood leads the Division Series 1-0.'


def test_template_scores_are_the_regular_templates_and_no_series_means_a_plain_headline():
    f = feed.post_day_facts(assoc(), None, SCHED, 10, 1)
    t = feed.post_template(f)
    assert t['headline'] == 'Postseason' and t['body'] == 'Ash 5, Birch 3. Dogwood 6, Cedar 2.'
    assert t['body'] == feed.template(dict(f, division_leaders=[]))['body']


@pytest.mark.parametrize('day', [1, 2, 3])
def test_template_numbers_pass_the_number_check(day):
    f = feed.post_day_facts(assoc(), DIV, SCHED, 10, day)
    t = feed.post_template(f)
    assert recap.numbers_ok(t['body'], f) and recap.numbers_ok(t['headline'] + '\n' + t['body'], f)


def test_post_prompt_is_the_postseason_system_and_the_facts():
    f = feed.post_day_facts(assoc(), DIV, SCHED, 10, 1)
    assert feed.post_prompt(f) == (feed.POST_SYSTEM, recap.facts_message(f))
    assert feed.POST_SYSTEM.startswith("You are a newspaper baseball writer covering the association's postseason. ")
    assert '80 to 150 words' in feed.POST_SYSTEM and feed.POST_SYSTEM.endswith(recap.RULES)


class Scripted:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, system, user, budget):
        self.calls.append((system, user, budget))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer, {'completion_tokens': 10}


def test_post_write_asks_with_the_postseason_prompt_and_checks_the_numbers():
    f = feed.post_day_facts(assoc(), DIV, SCHED, 10, 2)
    ok = Scripted('Ash take the series\n\nAsh beat Birch 2-0 to win the Division Series.')
    got = feed.post_write(f, 'budget', ok)
    assert got['source'] == 'glm' and got['headline'] == 'Ash take the series'
    assert ok.calls == [(feed.POST_SYSTEM, recap.facts_message(f), 'budget')]
    bad = Scripted('Sweep\n\nAsh won 12-0.', hive.HiveError('down'))
    got = feed.post_write(f, 'budget', bad)
    assert (got['source'], got['reason']) == ('template', 'error')
    assert got['body'] == feed.post_template(f)['body'] and len(bad.calls) == 2


def test_post_write_falls_back_to_the_post_template_when_the_budget_is_spent():
    f = feed.post_day_facts(assoc(), DIV, SCHED, 10, 2)
    got = feed.post_write(f, 'budget', Scripted(hive.BudgetExceeded('spent')))
    assert got == dict(feed.post_template(f), source='template', reason='budget')


# ---- Watcher.columns

REGULAR = [gm(4, 1, 0, 1, 2, 3, 1), gm(4, 2, 0, 2, 1, 0, 5), gm(4, 3, 0, 1, 2, 2, 4), gm(4, 4, 0, 2, 1, 1, 6),
           gm(4, 5, 0, 1, 2, 7, 0)]
POST = [gm(10, 20, 0, 2, 1, 3, 5), gm(10, 20, 1, 4, 3, 2, 6), gm(10, 21, 0, 1, 2, 4, 2), gm(10, 21, 1, 3, 4, 0, 1),
        gm(10, 22, 0, 2, 1, 1, 0), gm(10, 23, 0, 1, 2, 3, 3, played=False)]
EMPTY = {'bat': {}, 'pit': {}}


def stub_post(monkeypatch, sched=POST, br=DIV, calls=None):
    def post(path):
        if calls is not None:
            calls.append(path)
        return br, [dict(g) for g in sched]
    monkeypatch.setattr(watch, '_postseason', post)


def watcher(tmp_path, complete=None, logs=None):
    return watch.Watcher(str(tmp_path / 'game'), str(tmp_path / 'data'), 'budget', complete,
                         log=(logs if logs is not None else []).append)


def feed_files(out):
    d = out / 'feed'
    return {f: json.loads((d / f).read_text()) for f in sorted(os.listdir(d))} if d.is_dir() else {}


def test_each_played_postseason_date_gets_a_column(tmp_path, monkeypatch):
    stub_post(monkeypatch)
    logs, out = [], tmp_path / 'out'
    watcher(tmp_path, logs=logs).columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    files = feed_files(out)
    assert sorted(files) == ['04-01.json', '04-02.json', '04-03.json', '04-04.json', '04-05.json',
                             '10-20.json', '10-21.json', '10-22.json']          # Oct 23 is unplayed
    for name in ('10-20.json', '10-21.json', '10-22.json'):
        c = files[name]
        assert c['facts']['kind'] == 'postseason' and (c['source'], c['reason']) == ('template', 'off')
        assert set(c) == set(files['04-05.json'])                                 # the same keys as a regular column
        assert c['facts']['results'] and c['facts']['series']
    c = files['10-21.json']
    assert (c['month'], c['day'], c['date'], c['headline']) == (10, 21, 'October 21', 'Division Series')
    assert c['body'] == feed.post_template(c['facts'])['body']
    assert 'column out October 21 (template)' in logs and len(logs) == 8


def test_a_second_pass_rewrites_nothing_and_a_new_game_rewrites_its_date(tmp_path, monkeypatch):
    sched = [dict(g) for g in POST]
    stub_post(monkeypatch, sched)
    logs, out = [], tmp_path / 'out'
    w = watcher(tmp_path, logs=logs)
    w.columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    for f in os.listdir(out / 'feed'):
        os.utime(out / 'feed' / f, ns=(10 ** 9, 10 ** 9))
    logs.clear()
    w.columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    assert logs == [] and {os.stat(out / 'feed' / f).st_mtime_ns for f in os.listdir(out / 'feed')} == {10 ** 9}
    sched.append(gm(10, 22, 1, 4, 3, 5, 0))                  # a second game on the 22nd
    stub_post(monkeypatch, sched)
    w.columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    assert logs == ['column out October 22 (template)']
    assert len(feed_files(out)['10-22.json']['facts']['results']) == 2


def run_regular(tmp_path, name, monkeypatch, asn_path, stub):
    monkeypatch.setattr(watch, '_postseason', stub)
    out = tmp_path / name
    watcher(tmp_path).columns(str(out), assoc(REGULAR), {}, {'bat': {}, 'pit': {}}, *([asn_path] if asn_path else []))
    return feed_files(out)


def test_regular_columns_are_the_same_without_a_postseason(tmp_path, monkeypatch):
    def never(path):
        raise AssertionError('no asn_path: the postseason is not read')

    plain = run_regular(tmp_path, 'a', monkeypatch, None, never)
    none = run_regular(tmp_path, 'b', monkeypatch, 'x.ASN', lambda path: (None, []))
    assert sorted(plain) == ['04-0%d.json' % d for d in range(1, 6)] == sorted(none)
    for name, c in plain.items():
        d = none[name]
        assert (c['headline'], c['body'], c['facts'], c['source'], c['reason']) == \
               (d['headline'], d['body'], d['facts'], d['source'], d['reason'])
        assert 'kind' not in c['facts']
    month, day = 4, 3
    want = feed.template(feed.day_facts(watch.through(assoc(REGULAR), month, day), EMPTY, {}, month, day))
    assert (plain['04-03.json']['headline'], plain['04-03.json']['body']) == (want['headline'], want['body'])


def test_a_postseason_date_inside_the_regular_days_is_left_to_the_regular_column(tmp_path, monkeypatch):
    stub_post(monkeypatch, [gm(4, 5, 1, 2, 1, 1, 0)] + POST[:2])
    out = tmp_path / 'out'
    watcher(tmp_path).columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    files = feed_files(out)
    assert sorted(files) == ['04-01.json', '04-02.json', '04-03.json', '04-04.json', '04-05.json', '10-20.json']
    assert 'kind' not in files['04-05.json']['facts']


@pytest.mark.parametrize('post_days, systems', [
    (1, ['post', 'regular', 'regular']),
    (2, ['post', 'post', 'regular']),
    (3, ['post', 'post', 'post'])])
def test_the_newest_dates_across_both_go_to_the_model(tmp_path, monkeypatch, post_days, systems):
    sched = [g for g in POST if g['day'] <= 19 + post_days]
    stub_post(monkeypatch, sched)
    complete = Scripted(*['Headline\n\nA short body.'] * 3)
    out = tmp_path / 'out'
    watcher(tmp_path, complete).columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    assert sorted(('post' if s == feed.POST_SYSTEM else 'regular' if s == feed.SYSTEM else s)
                  for s, _, _ in complete.calls) == sorted(systems)
    files = feed_files(out)
    assert len(files) == 5 + post_days
    assert sorted(f for f, c in files.items() if c['source'] == 'glm') == sorted(files)[-3:]
    assert {c['reason'] for c in files.values() if c['source'] == 'template'} == {'backfill'}


def test_the_model_is_not_asked_for_a_postseason_column_without_a_complete(tmp_path, monkeypatch):
    stub_post(monkeypatch)
    out = tmp_path / 'out'
    watcher(tmp_path, None).columns(str(out), assoc(REGULAR), {}, EMPTY, 'x.ASN')
    assert {c['source'] for c in feed_files(out).values()} == {'template'}


def test_association_passes_its_asn_path_so_a_scan_writes_the_postseason_columns(tmp_path, monkeypatch):
    gd = tmp_path / 'game'
    (gd / 'Assn').mkdir(parents=True)
    (gd / 'Stats').mkdir()
    (gd / 'Assn' / '30L1998.ASN').write_bytes(b'asn')
    os.utime(gd / 'Assn' / '30L1998.ASN', (1, 1))
    monkeypatch.setattr(gamedata, 'association', lambda path: assoc(REGULAR))
    monkeypatch.setattr(gamedata, 'names', lambda path: {})
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: EMPTY)
    paths = []
    stub_post(monkeypatch, calls=paths)
    watch.Watcher(str(gd), str(tmp_path / 'data'), None, None, log=lambda s: None).scan()
    assert sorted(f for f in feed_files(tmp_path / 'data' / '30L1998') if f.startswith('10')) == [
        '10-20.json', '10-21.json', '10-22.json']
    assert paths and {os.path.basename(p) for p in paths} == {'30L1998.ASN'}
