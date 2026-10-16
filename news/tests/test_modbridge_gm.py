"""The offseason trade pages under /news/gm/ through modbridge.process_spool: every route and every 404; the overview
with and without a ledger, preseason and started, and a ledger for an older season (missing); run (the ASN, its backup
and the ledger, once a season, refused once started, while the game holds the files, and when the trade check fails);
accept (written, stale, closed, while the game holds the files, and when the check fails); reject; and the Offseason
trades link on an association page. aigm's read, plan, apply_trade and validate are faked, gamedata's association and
players are stubbed, and create.open_by_anyone is patched. Helpers and fixtures come from test_modbridge.py.
The trade deadline pages under /news/gm/<STEM>/deadline (the Trade deadline link, the page, run, accept, reject, every
404), first with aigm's deadline_plan and apply_deadline and roster's problems and apply faked, then end to end on a
synthetic ASN with the real aigm and roster.
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aigm        # noqa: E402
import create      # noqa: E402
import gamedata    # noqa: E402
import modbridge   # noqa: E402
import roster      # noqa: E402
from tests.test_aigm import make_asn   # noqa: E402
from tests.test_aigm_deadline import YEAR, ace_of, bench_of, deal, pid_of   # noqa: E402
from tests.test_aigm_deadline import league as deadline_league   # noqa: E402
from tests.test_modbridge import NAMES, ask, bridge, serve_pages, site   # noqa: E402,F401

GM = '/news/gm/TEST77'
TITLE = 'Offseason trades: 1977 Major Leagues'
OPEN = '1977 Major Leagues is open in the game. Go back to the main menu, then try again.'
TEAMS = {1: {'name': 'Reds'}, 2: {'name': 'Cubs'}}
REAL_READ = aigm.read       # the fixtures below replace aigm.read; the end to end tests put this back
PLAYERS = {100: {'name': 'Pat Doe', 'pos': '2B', 'born': 1952, 'contact': 60, 'power': 0, 'speed': 0, 'stamina': 0,
                 'control': 0, 'strikeout': 0, 'fielding': 0},
           205: {'name': 'Bo Bee', 'pos': '1B', 'born': 1948, 'contact': 50, 'power': 0, 'speed': 0, 'stamina': 0,
                 'control': 0, 'strikeout': 0, 'fielding': 0},
           300: {'name': 'Cy Young', 'pos': 'SS', 'born': 1955, 'contact': 60, 'power': 0, 'speed': 0, 'stamina': 0,
                 'control': 0, 'strikeout': 0, 'fielding': 0},
           310: {'name': 'Al Ames', 'pos': 'LF', 'born': 1950, 'contact': 60, 'power': 0, 'speed': 0, 'stamina': 0,
                 'control': 0, 'strikeout': 0, 'fielding': 0}}
TRADE = {'a': 1, 'b': 2, 'a_gives': 100, 'b_gives': 205, 'a_pos': 'SS', 'b_pos': '1B', 'b_drops': None,
         'a_drops': None, 'gain': 12.5}
PROPOSAL = {'a': 1, 'b': 2, 'a_gives': 300, 'b_gives': 310, 'a_pos': 'SS', 'b_pos': 'LF', 'b_drops': None,
            'a_drops': None, 'gain': 9.0}
NAMED_TRADE = dict(TRADE, a_name='Reds', b_name='Cubs', a_gives_name='Pat Doe', b_gives_name='Bo Bee')
NAMED_OPEN = dict(PROPOSAL, a_name='Reds', b_name='Cubs', a_gives_name='Cy Young', b_gives_name='Al Ames',
                  status='open')
NAMED_REJECTED = dict(NAMED_OPEN, status='rejected')
NOT_FOUND = [
    '/news/gm/NOPE/',                       # no association with that STEM
    '/news/gm/NOPE/run',
    '/news/gm/TEST77/bogus',
    '/news/gm/TEST77/run/',
    '/news/gm/TEST77/run?x=1',
    '/news/gm/TEST77/accept',
    '/news/gm/TEST77/accept/',
    '/news/gm/TEST77/accept/0',             # proposals start at 1
    '/news/gm/TEST77/accept/x',
    '/news/gm/TEST77/accept/1000',          # not three digits
    '/news/gm/TEST77/reject/0',
    '/news/gm/TEST77/reject/9',
    '/news/gm/TEST77/accept/1',             # no ledger for this season yet
    '/news/gm/TEST77/reject/1',
    '/news/gm/',
    '/news/gm',
]


def stub_gm(monkeypatch, year=1977, started=False):
    def association(path):
        return {'name': NAMES[os.path.basename(path)], 'season_year': year, 'teams': TEAMS,
                'games': [{'played': started}]}
    monkeypatch.setattr(gamedata, 'association', association)
    monkeypatch.setattr(gamedata, 'players', lambda path: PLAYERS)


@pytest.fixture
def gm(bridge, site, monkeypatch):   # noqa: F811 (the fixtures are imported)
    """The bridge on the site with the association stubbed; aigm's calls answer from fake: its plan and problems (what
    validate returns), and every ASN is read as READS says (b'asn' is the file as it starts, b'after' as a trade
    leaves it)."""
    ctx, spool = bridge
    game, data, backup, donor, proc = site
    stub_gm(monkeypatch)
    monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': [])
    fake = types.SimpleNamespace(plan={'trades': [TRADE], 'proposals': [PROPOSAL]}, problems=[], plan_kw=None)
    reads = {b'asn': {'windows': {1: [0] * 126, 2: [0] * 126}, 'human': frozenset({1})},
             b'after': {'windows': {1: [1] * 126, 2: [2] * 126}, 'human': frozenset({1})}}
    monkeypatch.setattr(aigm, 'read', lambda asn: reads[asn])
    def plan(windows, players, year, human=frozenset(), **kw):
        fake.plan_kw = kw
        return fake.plan
    monkeypatch.setattr(aigm, 'plan', plan)
    monkeypatch.setattr(aigm, 'apply_trade', lambda asn, trade: b'after')
    monkeypatch.setattr(aigm, 'validate', lambda before, after, players: list(fake.problems))
    return types.SimpleNamespace(ctx=ctx, spool=spool, game=game, data=data, backup=backup, fake=fake,
                                 monkeypatch=monkeypatch)


def page(ctx, spool, path):
    return ask(ctx, spool, 'op=news\npath=' + path)


def links_of(head):
    return [tuple(head['link.%d' % i].split('\t')) for i in range(int(head['count']))]


def asn_file(g):
    return g.game / 'Assn' / 'TEST77.ASN'


def ledger_file(g):
    return g.data / 'TEST77' / 'gm.json'


def ledger_of(g):
    return json.loads(ledger_file(g).read_text())


def write_ledger(g, season=1977, trades=(), proposals=()):
    (g.data / 'TEST77').mkdir(parents=True, exist_ok=True)
    ledger_file(g).write_text(json.dumps({'kind': 'gm', 'season_year': season, 'created': '1977-03-01T09:00:00',
                                          'trades': list(trades), 'proposals': list(proposals)}))


def backups(g):
    return sorted(g.backup.glob('TEST77-*-gm')) if g.backup.exists() else []


def assert_nothing_written(g, asn=b'asn'):
    assert asn_file(g).read_bytes() == asn
    assert backups(g) == []


# the overview

def test_the_preseason_overview_offers_the_run(gm):
    head, body = page(gm.ctx, gm.spool, GM + '/')
    assert head == {'status': 'ok', 'http': '200', 'path': GM + '/', 'title': TITLE, 'count': '3',
                    'link.0': 'Run computer trades\t' + GM + '/run',
                    'link.1': 'Player development\t/news/development/TEST77/',
                    'link.2': 'League news\t/news/TEST77/'}
    assert body.split('\n') == [TITLE, '=' * len(TITLE), '', 'No trades yet this season.',
                                "Computer-run teams trade bench players to fill each other's needs.",
                                'Human-run teams only get proposals.']


def test_the_started_overview_says_when_trades_run_and_offers_no_run(gm, monkeypatch):
    stub_gm(monkeypatch, started=True)
    head, body = page(gm.ctx, gm.spool, GM + '/')
    assert links_of(head) == [('Player development', '/news/development/TEST77/'), ('League news', '/news/TEST77/')]
    assert body.split('\n')[3:] == ['No trades yet this season.',
                                    'Trades run in the preseason, before the first game.']


def test_the_overview_lists_the_season_trades_and_each_proposal_with_its_status(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN, NAMED_REJECTED])
    head, body = page(gm.ctx, gm.spool, GM + '/')
    assert body.split('\n')[3:] == ['Trades made (1):', 'Reds trade Pat Doe to Cubs for Bo Bee', '',
                                    'Proposals for your teams:',
                                    '1. Reds get Al Ames, Cubs get Cy Young (open)',
                                    '2. Reds get Al Ames, Cubs get Cy Young (rejected)']
    assert links_of(head) == [('Accept 1', GM + '/accept/1'), ('Reject 1', GM + '/reject/1'),
                              ('Player development', '/news/development/TEST77/'), ('League news', '/news/TEST77/')]


def test_a_season_with_no_proposals_says_none(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[])
    head, body = page(gm.ctx, gm.spool, GM + '/')
    assert body.split('\n')[3:] == ['Trades made (1):', 'Reds trade Pat Doe to Cubs for Bo Bee', '',
                                    'Proposals for your teams:', 'None.']


def test_a_ledger_for_an_older_season_counts_as_missing(gm):
    write_ledger(gm, season=1976, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    head, body = page(gm.ctx, gm.spool, GM + '/')
    assert body.split('\n')[3] == 'No trades yet this season.'
    assert ('Run computer trades', GM + '/run') in links_of(head)


def test_the_stem_is_read_without_case(gm):
    head, _ = page(gm.ctx, gm.spool, '/news/gm/test77/')
    assert head['http'] == '200' and head['title'] == TITLE and head['path'] == GM + '/'


def test_every_page_repeats_its_title_as_an_underlined_heading_after_any_note(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    head, body = page(gm.ctx, gm.spool, GM + '/')
    assert body.split('\n')[:3] == [TITLE, '=' * len(TITLE), '']
    head, body = page(gm.ctx, gm.spool, GM + '/accept/1')
    assert body.split('\n')[:2] == ['Trade made.', ''] and body.split('\n')[2:5] == [TITLE, '=' * len(TITLE), '']


@pytest.mark.parametrize('path', NOT_FOUND)
def test_every_other_path_is_plain_not_found_and_writes_nothing(gm, path):
    head, body = page(gm.ctx, gm.spool, path)
    assert head == {'status': 'error', 'http': '404', 'path': path, 'title': 'Not found', 'count': '0'}
    assert body == 'Not found.'
    assert not ledger_file(gm).exists() and backups(gm) == [] and asn_file(gm).read_bytes() == b'asn'


# run

def test_run_writes_the_asn_its_backup_and_the_ledger(gm):
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '200' and body.split('\n')[0] == '1 trades made.'
    assert asn_file(gm).read_bytes() == b'after'
    (folder,) = backups(gm)
    assert (folder / 'TEST77.ASN').read_bytes() == b'asn'
    led = ledger_of(gm)
    assert led['kind'] == 'gm' and led['season_year'] == 1977 and 'created' in led
    assert led['trades'] == [NAMED_TRADE]
    assert led['proposals'] == [NAMED_OPEN]


def test_a_second_run_is_refused_and_writes_nothing(gm):
    page(gm.ctx, gm.spool, GM + '/run')
    before = ledger_file(gm).read_text()
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == 'Trades already ran this season.'
    assert asn_file(gm).read_bytes() == b'after' and len(backups(gm)) == 1
    assert ledger_file(gm).read_text() == before


def test_a_started_season_is_refused_and_writes_nothing(gm, monkeypatch):
    stub_gm(monkeypatch, started=True)
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == 'The season has started.'
    assert_nothing_written(gm)
    assert not ledger_file(gm).exists()


def test_a_run_with_no_trades_writes_only_the_ledger(gm):
    gm.fake.plan = {'trades': [], 'proposals': [PROPOSAL]}
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '200' and body.split('\n')[0] == '0 trades made.'
    assert_nothing_written(gm)
    assert ledger_of(gm)['trades'] == [] and ledger_of(gm)['proposals'] == [NAMED_OPEN]


def test_a_run_replaces_an_older_seasons_ledger(gm):
    write_ledger(gm, season=1976, trades=[NAMED_TRADE])
    head, _ = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '200' and ledger_of(gm)['season_year'] == 1977


def test_run_refused_while_the_game_holds_its_files_writes_nothing(gm):
    gm.monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': [str(asn_file(gm))])
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == OPEN
    assert_nothing_written(gm)
    assert not ledger_file(gm).exists()


def test_run_whose_check_fails_writes_nothing(gm):
    gm.fake.problems = ['team 1 has 4 active pitchers, needs 5']
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '500' and body.split('\n')[0] == 'Trade check failed: team 1 has 4 active pitchers, needs 5'
    assert_nothing_written(gm)
    assert not ledger_file(gm).exists()


# accept, reject

def test_accept_writes_the_trade_and_marks_the_proposal_accepted(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    head, body = page(gm.ctx, gm.spool, GM + '/accept/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Trade made.'
    assert asn_file(gm).read_bytes() == b'after'
    assert len(backups(gm)) == 1 and (backups(gm)[0] / 'TEST77.ASN').read_bytes() == b'asn'
    assert ledger_of(gm)['proposals'][0]['status'] == 'accepted'
    assert '1. Reds get Al Ames, Cubs get Cy Young (accepted)' in body.split('\n')


def test_accept_of_a_stale_proposal_writes_no_asn_and_marks_it_stale(gm, monkeypatch):
    def gone(asn, trade):
        raise aigm.SwapError('300 is not on the active roster of team 1')
    monkeypatch.setattr(aigm, 'apply_trade', gone)
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    head, body = page(gm.ctx, gm.spool, GM + '/accept/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Proposal 1 is out of date.'
    assert_nothing_written(gm)
    assert ledger_of(gm)['proposals'][0]['status'] == 'stale'


@pytest.mark.parametrize('status', ['accepted', 'rejected', 'stale'])
def test_accept_or_reject_of_a_closed_proposal_is_refused(gm, status):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[dict(NAMED_OPEN, status=status)])
    for action in ('accept', 'reject'):
        head, body = page(gm.ctx, gm.spool, GM + '/%s/1' % action)
        assert head['http'] == '409' and body.split('\n')[0] == 'Proposal 1 is %s.' % status
    assert ledger_of(gm)['proposals'][0]['status'] == status
    assert asn_file(gm).read_bytes() == b'asn'


def test_accept_refused_while_the_game_holds_its_files_writes_nothing(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    gm.monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': [str(asn_file(gm))])
    head, body = page(gm.ctx, gm.spool, GM + '/accept/1')
    assert head['http'] == '409' and body.split('\n')[0] == OPEN
    assert_nothing_written(gm)
    assert ledger_of(gm)['proposals'][0]['status'] == 'open'


def test_accept_whose_check_fails_writes_nothing_and_stays_open(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    gm.fake.problems = ['the active players changed']
    head, body = page(gm.ctx, gm.spool, GM + '/accept/1')
    assert head['http'] == '500' and body.split('\n')[0] == 'Trade check failed: the active players changed'
    assert_nothing_written(gm)
    assert ledger_of(gm)['proposals'][0]['status'] == 'open'


def test_reject_marks_the_proposal_and_writes_no_asn(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    head, body = page(gm.ctx, gm.spool, GM + '/reject/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Proposal rejected.'
    assert_nothing_written(gm)
    assert ledger_of(gm)['proposals'][0]['status'] == 'rejected'
    assert ('Accept 1', GM + '/accept/1') not in links_of(head)


def test_other_open_proposals_stay_open_after_an_accept(gm):
    write_ledger(gm, trades=[NAMED_TRADE], proposals=[NAMED_OPEN, dict(NAMED_OPEN, a_gives=100, status='open')])
    head, _ = page(gm.ctx, gm.spool, GM + '/accept/1')
    assert [p['status'] for p in ledger_of(gm)['proposals']] == ['accepted', 'open']
    assert ('Accept 2', GM + '/accept/2') in links_of(head)


# the link on an association page

def test_an_association_page_links_to_its_offseason_trades_after_player_development(bridge, monkeypatch):  # noqa: F811
    ctx, spool = bridge
    serve_pages(monkeypatch, {'/news/TEST77/': (200, b'<title>1977 Major Leagues</title><p>hi</p>', ())})
    head, _ = page(ctx, spool, '/news/TEST77/')
    assert links_of(head) == [('Player development', '/news/development/TEST77/'),
                              ('Offseason trades', '/news/gm/TEST77/')]


def test_ledger_entry_shapes_are_checked():
    import modbridge
    good = {'a': 1, 'b': 2, 'a_gives': 110, 'b_gives': 210, 'a_drops': None, 'b_drops': 216,
            'a_name': 'A', 'b_name': 'B', 'a_gives_name': 'x', 'b_gives_name': 'y'}
    assert modbridge._entry_ok(good)
    assert modbridge._entry_ok(dict(good, status='open'), True)
    assert not modbridge._entry_ok(dict(good, status='maybe'), True)
    assert not modbridge._entry_ok(dict(good, a_gives='110'))
    assert not modbridge._entry_ok(dict(good, b_drops=1.5))
    assert not modbridge._entry_ok({k: v for k, v in good.items() if k != 'a_name'})
    assert not modbridge._entry_ok([good])


@pytest.mark.parametrize('text', ['{"kind": "gm", "season_year": 1977, "trades": [{"a": 1}], "proposals": []}',
                                  '{"kind": "gm", "season_year": 1977, "tr', '[1, 2]', '{"kind": "other"}',
                                  '{"kind": "gm", "season_year": "1976"}', ''])
def test_an_unusable_ledger_refuses_the_run_and_writes_nothing(gm, text):
    ledger_file(gm).parent.mkdir(parents=True, exist_ok=True)
    ledger_file(gm).write_text(text)
    head, body = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '409'
    assert body.split('\n')[0] == modbridge.BAD_LEDGER_TEXT % 'TEST77'
    assert_nothing_written(gm)
    assert ledger_file(gm).read_text() == text


def test_a_readable_older_seasons_ledger_still_lets_the_run_go(gm):
    write_ledger(gm, season=1976, trades=[], proposals=[])
    head, _ = page(gm.ctx, gm.spool, GM + '/run')
    assert head['http'] == '200' and ledger_of(gm)['season_year'] == 1977


# the offseason run hands the planner the stem and the salaries

def test_the_run_plans_with_the_stem_and_no_salaries_without_a_contracts_file(gm):
    page(gm.ctx, gm.spool, GM + '/run')
    assert gm.fake.plan_kw == {'stem': 'TEST77', 'salaries': None}


def test_the_run_plans_with_the_salaries_of_contracts_json(gm):
    (gm.data / 'TEST77').mkdir(parents=True)
    (gm.data / 'TEST77' / 'contracts.json').write_text(json.dumps({'contracts': {
        '100': {'salary': 1500000, 'team': 1}, '205': {'salary': 250000.5, 'team': 2}, '300': {'team': 1},
        '310': {'salary': '9', 'team': 1}, 'x': {'salary': 5}, '999': 'no', '7': {'salary': True}}}))
    page(gm.ctx, gm.spool, GM + '/run')
    assert gm.fake.plan_kw == {'stem': 'TEST77', 'salaries': {100: 1500000, 205: 250000.5}}


@pytest.mark.parametrize('text', ['', '{"contracts": 3}', '[1]', '{"contracts": {}}', '{"contracts": {"1": {}}}'])
def test_an_unusable_contracts_file_gives_no_salaries(gm, text):
    (gm.data / 'TEST77').mkdir(parents=True)
    (gm.data / 'TEST77' / 'contracts.json').write_text(text)
    page(gm.ctx, gm.spool, GM + '/run')
    assert gm.fake.plan_kw['salaries'] is None


# the trade deadline

DL = GM + '/deadline'
DL_TITLE = 'Trade deadline: 1977 Major Leagues'
DL_CLOSED = 'The deadline is open when the league has played 55 to 65 percent of its games.'
DL_TRADE = {'c': 1, 'r': 2, 'vet': 205, 'prospect': 100, 'gain': 12.5, 'kind': 'deadline'}
DL_PROPOSAL = {'c': 1, 'r': 2, 'vet': 310, 'prospect': 300, 'gain': 9.0, 'kind': 'deadline'}
NAMED_DL_TRADE = dict(DL_TRADE, c_name='Reds', r_name='Cubs', vet_name='Bo Bee', prospect_name='Pat Doe')
NAMED_DL_OPEN = dict(DL_PROPOSAL, c_name='Reds', r_name='Cubs', vet_name='Al Ames', prospect_name='Cy Young',
                     status='open')
NAMED_DL_REJECTED = dict(NAMED_DL_OPEN, status='rejected')
AFTER = {1: [1] * 126, 2: [2] * 126}
DL_NOT_FOUND = [
    '/news/gm/NOPE/deadline',
    '/news/gm/NOPE/deadline/run',
    '/news/gm/TEST77/deadline/',
    '/news/gm/TEST77/deadline/bogus',
    '/news/gm/TEST77/deadline/run/',
    '/news/gm/TEST77/deadline/run?x=1',
    '/news/gm/TEST77/deadline/accept',
    '/news/gm/TEST77/deadline/accept/',
    '/news/gm/TEST77/deadline/accept/0',
    '/news/gm/TEST77/deadline/accept/x',
    '/news/gm/TEST77/deadline/accept/1000',
    '/news/gm/TEST77/deadline/reject/0',
    '/news/gm/TEST77/deadline/accept/1',    # no ledger for this season yet
    '/news/gm/TEST77/deadline/reject/1',
]


def stub_dl(monkeypatch, played=12, total=20, year=1977, teams=TEAMS):
    """The association with `total` games between teams 1 and 2, `played` of them played (12 of 20 is in the window)."""
    games = [{'away': 1, 'home': 2, 'played': i < played} for i in range(total)]

    def association(path):
        return {'name': NAMES[os.path.basename(path)], 'season_year': year, 'teams': teams, 'games': games}
    monkeypatch.setattr(gamedata, 'association', association)


def dl_ledger_file(g):
    return g.data / 'TEST77' / 'deadline.json'


def dl_ledger_of(g):
    return json.loads(dl_ledger_file(g).read_text())


def write_dl_ledger(g, season=1977, trades=(), proposals=()):
    (g.data / 'TEST77').mkdir(parents=True, exist_ok=True)
    dl_ledger_file(g).write_text(json.dumps({'kind': 'deadline', 'season_year': season,
                                             'created': '1977-07-01T09:00:00', 'trades': list(trades),
                                             'proposals': list(proposals)}))


@pytest.fixture
def dl(gm):
    """gm with the league inside the deadline window and aigm's deadline_plan and apply_deadline, and roster's problems
    and apply, answering from fake: its deadline plan, its problems for the windows after a trade (AFTER) and the error
    apply_deadline raises (a SwapError, or None). plan_kw is what deadline_plan was called with."""
    mp, fake = gm.monkeypatch, gm.fake
    stub_dl(mp)
    fake.dl_plan = {'trades': [DL_TRADE], 'proposals': [DL_PROPOSAL]}
    fake.dl_problems, fake.dl_error, fake.dl_calls, fake.dl_kw = [], None, [], None

    def deadline_plan(windows, players, year, teams, human=frozenset(), stem=None):
        fake.dl_kw = {'year': year, 'teams': teams, 'human': human, 'stem': stem}
        return fake.dl_plan

    def apply_deadline(windows, trade, players, year):
        fake.dl_calls.append(dict(trade))
        if fake.dl_error:
            raise fake.dl_error
        return {tid: list(w) for tid, w in AFTER.items()}
    mp.setattr(aigm, 'deadline_plan', deadline_plan)
    mp.setattr(aigm, 'apply_deadline', apply_deadline)
    mp.setattr(roster, 'problems',
               lambda windows, players: list(fake.dl_problems) if windows.get(1) == [1] * 126 else [])
    mp.setattr(roster, 'apply', lambda asn, windows: b'after')
    return gm


def test_the_overview_links_to_the_deadline_while_its_window_is_open(dl):
    head, _ = page(dl.ctx, dl.spool, GM + '/')
    assert links_of(head) == [('Trade deadline', DL), ('Player development', '/news/development/TEST77/'),
                              ('League news', '/news/TEST77/')]       # games have been played: no preseason run


def test_the_overview_links_to_the_deadline_once_it_has_a_ledger_whatever_the_window(gm, monkeypatch):
    stub_dl(monkeypatch, played=20)
    head, _ = page(gm.ctx, gm.spool, GM + '/')
    assert ('Trade deadline', DL) not in links_of(head)
    write_dl_ledger(gm)
    head, _ = page(gm.ctx, gm.spool, GM + '/')
    assert ('Trade deadline', DL) in links_of(head)


def test_the_deadline_page_offers_the_run_inside_the_window(dl):
    head, body = page(dl.ctx, dl.spool, DL)
    assert head == {'status': 'ok', 'http': '200', 'path': DL, 'title': DL_TITLE, 'count': '3',
                    'link.0': 'Run deadline trades\t' + DL + '/run', 'link.1': 'Offseason trades\t' + GM + '/',
                    'link.2': 'League news\t/news/TEST77/'}
    assert body.split('\n') == [DL_TITLE, '=' * len(DL_TITLE), '', 'No deadline trades yet this season.',
                                "Contending teams buy rebuilding teams' veterans for prospects.",
                                'Human-run teams only get proposals.']


@pytest.mark.parametrize('played', [0, 10, 14, 20])
def test_the_deadline_page_offers_no_run_outside_the_window(gm, monkeypatch, played):
    stub_dl(monkeypatch, played=played)
    head, body = page(gm.ctx, gm.spool, DL)
    assert links_of(head) == [('Offseason trades', GM + '/'), ('League news', '/news/TEST77/')]
    assert body.split('\n')[3:] == ['No deadline trades yet this season.', DL_CLOSED]


def test_the_deadline_page_lists_the_trades_and_each_proposal_with_its_status(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN, NAMED_DL_REJECTED])
    head, body = page(dl.ctx, dl.spool, DL)
    assert body.split('\n')[3:] == ['Trades made (1):', 'Reds trade Pat Doe to Cubs for Bo Bee', '',
                                    'Proposals for your teams:',
                                    '1. Reds get Al Ames, Cubs get Cy Young (open)',
                                    '2. Reds get Al Ames, Cubs get Cy Young (rejected)']
    assert links_of(head) == [('Accept 1', DL + '/accept/1'), ('Reject 1', DL + '/reject/1'),
                              ('Offseason trades', GM + '/'), ('League news', '/news/TEST77/')]


def test_a_season_with_no_deadline_proposals_says_none(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[])
    _, body = page(dl.ctx, dl.spool, DL)
    assert body.split('\n')[3:] == ['Trades made (1):', 'Reds trade Pat Doe to Cubs for Bo Bee', '',
                                    'Proposals for your teams:', 'None.']


def test_a_ledger_for_an_older_season_counts_as_missing_for_the_deadline(dl):
    write_dl_ledger(dl, season=1976, trades=[NAMED_DL_TRADE])
    head, body = page(dl.ctx, dl.spool, DL)
    assert body.split('\n')[3] == 'No deadline trades yet this season.'
    assert ('Run deadline trades', DL + '/run') in links_of(head)


def test_the_offseason_ledger_does_not_touch_the_deadline(dl):
    write_ledger(dl, trades=[NAMED_TRADE], proposals=[NAMED_OPEN])
    _, body = page(dl.ctx, dl.spool, DL)
    assert body.split('\n')[3] == 'No deadline trades yet this season.'
    head, _ = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '200' and ledger_of(dl)['trades'] == [NAMED_TRADE]


@pytest.mark.parametrize('path', DL_NOT_FOUND)
def test_every_other_deadline_path_is_plain_not_found_and_writes_nothing(dl, path):
    head, body = page(dl.ctx, dl.spool, path)
    assert head == {'status': 'error', 'http': '404', 'path': path, 'title': 'Not found', 'count': '0'}
    assert body == 'Not found.'
    assert not dl_ledger_file(dl).exists() and backups(dl) == [] and asn_file(dl).read_bytes() == b'asn'


# deadline run

def test_the_deadline_run_writes_the_asn_its_backup_and_the_ledger(dl):
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '200' and body.split('\n')[0] == '1 deadline trades made.'
    assert asn_file(dl).read_bytes() == b'after'
    (folder,) = backups(dl)
    assert (folder / 'TEST77.ASN').read_bytes() == b'asn'
    led = dl_ledger_of(dl)
    assert led['kind'] == 'deadline' and led['season_year'] == 1977 and 'created' in led
    assert led['trades'] == [NAMED_DL_TRADE] and led['proposals'] == [NAMED_DL_OPEN]
    assert dl.fake.dl_calls == [DL_TRADE]
    assert dl.fake.dl_kw == {'year': 1977, 'teams': TEAMS, 'human': frozenset({1}), 'stem': 'TEST77'}
    assert not ledger_file(dl).exists()                         # the offseason ledger is its own


def test_a_second_deadline_run_is_refused_and_writes_nothing(dl):
    page(dl.ctx, dl.spool, DL + '/run')
    before = dl_ledger_file(dl).read_text()
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == 'Deadline trades already ran this season.'
    assert asn_file(dl).read_bytes() == b'after' and len(backups(dl)) == 1
    assert dl_ledger_file(dl).read_text() == before


@pytest.mark.parametrize('played', [0, 10, 14, 20])
def test_a_deadline_run_outside_the_window_is_refused_and_writes_nothing(dl, played):
    stub_dl(dl.monkeypatch, played=played)
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == modbridge.NO_WINDOW_TEXT
    assert_nothing_written(dl)
    assert not dl_ledger_file(dl).exists() and dl.fake.dl_kw is None


def test_a_deadline_run_with_no_trades_writes_only_the_ledger(dl):
    dl.fake.dl_plan = {'trades': [], 'proposals': [DL_PROPOSAL]}
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '200' and body.split('\n')[0] == '0 deadline trades made.'
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['trades'] == [] and dl_ledger_of(dl)['proposals'] == [NAMED_DL_OPEN]


def test_a_deadline_trade_that_no_longer_fits_is_left_out(dl):
    dl.fake.dl_error = aigm.SwapError('205 is not on the roster of team 2')
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '200' and body.split('\n')[0] == '0 deadline trades made.'
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['trades'] == []


def test_a_deadline_run_replaces_an_older_seasons_ledger(dl):
    write_dl_ledger(dl, season=1976, trades=[NAMED_DL_TRADE])
    head, _ = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '200' and dl_ledger_of(dl)['season_year'] == 1977


def test_deadline_run_refused_while_the_game_holds_its_files_writes_nothing(dl):
    dl.monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': [str(asn_file(dl))])
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == OPEN
    assert_nothing_written(dl)
    assert not dl_ledger_file(dl).exists()


def test_a_deadline_run_with_a_new_roster_problem_writes_nothing(dl):
    dl.fake.dl_problems = ['team 2 has 4 active pitchers, needs 5']
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '500' and body.split('\n')[0] == 'Trade check failed: team 2 has 4 active pitchers, needs 5'
    assert_nothing_written(dl)
    assert not dl_ledger_file(dl).exists()


def test_a_deadline_run_ignores_a_problem_the_file_already_had(dl):
    dl.monkeypatch.setattr(roster, 'problems', lambda windows, players: ['team 2 has 4 active pitchers, needs 5'])
    head, _ = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '200' and asn_file(dl).read_bytes() == b'after'


def test_a_deadline_run_whose_windows_cannot_be_written_writes_nothing(dl):
    def apply(asn, windows):
        raise ValueError('team 3 has no live r record')
    dl.monkeypatch.setattr(roster, 'apply', apply)
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '500' and body.split('\n')[0] == 'Trade check failed: team 3 has no live r record'
    assert_nothing_written(dl)
    assert not dl_ledger_file(dl).exists()


@pytest.mark.parametrize('text', ['{"kind": "deadline", "season_year": 1977, "trades": [{"c": 1}], "proposals": []}',
                                  '{"kind": "deadline", "season_year": 1977, "tr', '[1, 2]', '{"kind": "gm"}',
                                  '{"kind": "deadline", "season_year": "1976"}', ''])
def test_an_unusable_deadline_ledger_refuses_the_run_and_writes_nothing(dl, text):
    dl_ledger_file(dl).parent.mkdir(parents=True, exist_ok=True)
    dl_ledger_file(dl).write_text(text)
    head, body = page(dl.ctx, dl.spool, DL + '/run')
    assert head['http'] == '409' and body.split('\n')[0] == modbridge.BAD_DEADLINE_TEXT % 'TEST77'
    assert_nothing_written(dl)
    assert dl_ledger_file(dl).read_text() == text


def test_deadline_ledger_entry_shapes_are_checked():
    good = {'c': 1, 'r': 2, 'vet': 205, 'prospect': 100, 'c_name': 'A', 'r_name': 'B', 'vet_name': 'x',
            'prospect_name': 'y'}
    assert modbridge._deadline_entry_ok(good)
    assert modbridge._deadline_entry_ok(dict(good, status='open'), True)
    assert not modbridge._deadline_entry_ok(dict(good, status='maybe'), True)
    assert not modbridge._deadline_entry_ok(good, True)
    assert not modbridge._deadline_entry_ok(dict(good, vet='205'))
    assert not modbridge._deadline_entry_ok({k: v for k, v in good.items() if k != 'vet_name'})
    assert not modbridge._deadline_entry_ok([good])


# deadline accept, reject

def test_deadline_accept_writes_the_trade_and_marks_the_proposal_accepted(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN])
    head, body = page(dl.ctx, dl.spool, DL + '/accept/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Trade made.'
    assert asn_file(dl).read_bytes() == b'after'
    assert len(backups(dl)) == 1 and (backups(dl)[0] / 'TEST77.ASN').read_bytes() == b'asn'
    assert dl_ledger_of(dl)['proposals'][0]['status'] == 'accepted'
    assert dl.fake.dl_calls == [NAMED_DL_OPEN]
    assert '1. Reds get Al Ames, Cubs get Cy Young (accepted)' in body.split('\n')


def test_deadline_accept_of_a_stale_proposal_writes_no_asn_and_marks_it_stale(dl):
    dl.fake.dl_error = aigm.SwapError('310 is not on the roster of team 2')
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN])
    head, body = page(dl.ctx, dl.spool, DL + '/accept/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Proposal 1 is out of date.'
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['proposals'][0]['status'] == 'stale'


@pytest.mark.parametrize('status', ['accepted', 'rejected', 'stale'])
def test_deadline_accept_or_reject_of_a_closed_proposal_is_refused(dl, status):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[dict(NAMED_DL_OPEN, status=status)])
    for action in ('accept', 'reject'):
        head, body = page(dl.ctx, dl.spool, DL + '/%s/1' % action)
        assert head['http'] == '409' and body.split('\n')[0] == 'Proposal 1 is %s.' % status
    assert dl_ledger_of(dl)['proposals'][0]['status'] == status
    assert asn_file(dl).read_bytes() == b'asn'


def test_deadline_accept_refused_while_the_game_holds_its_files_writes_nothing(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN])
    dl.monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': [str(asn_file(dl))])
    head, body = page(dl.ctx, dl.spool, DL + '/accept/1')
    assert head['http'] == '409' and body.split('\n')[0] == OPEN
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['proposals'][0]['status'] == 'open'


def test_deadline_accept_with_a_new_roster_problem_writes_nothing_and_stays_open(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN])
    dl.fake.dl_problems = ['team 1 has 8 active hitters, needs 9']
    head, body = page(dl.ctx, dl.spool, DL + '/accept/1')
    assert head['http'] == '500' and body.split('\n')[0] == 'Trade check failed: team 1 has 8 active hitters, needs 9'
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['proposals'][0]['status'] == 'open'


def test_deadline_accept_whose_windows_cannot_be_written_writes_nothing_and_stays_open(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN])

    def apply(asn, windows):
        raise ValueError('an id does not fit 16 bits')
    dl.monkeypatch.setattr(roster, 'apply', apply)
    head, body = page(dl.ctx, dl.spool, DL + '/accept/1')
    assert head['http'] == '500' and body.split('\n')[0] == 'Trade check failed: an id does not fit 16 bits'
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['proposals'][0]['status'] == 'open'


def test_deadline_reject_marks_the_proposal_and_writes_no_asn(dl):
    write_dl_ledger(dl, trades=[NAMED_DL_TRADE], proposals=[NAMED_DL_OPEN])
    head, body = page(dl.ctx, dl.spool, DL + '/reject/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Proposal rejected.'
    assert_nothing_written(dl)
    assert dl_ledger_of(dl)['proposals'][0]['status'] == 'rejected'
    assert ('Accept 1', DL + '/accept/1') not in links_of(head)


def test_other_deadline_proposals_stay_open_after_an_accept(dl):
    write_dl_ledger(dl, trades=[], proposals=[NAMED_DL_OPEN, dict(NAMED_DL_OPEN, vet=205)])
    head, _ = page(dl.ctx, dl.spool, DL + '/accept/1')
    assert [p['status'] for p in dl_ledger_of(dl)['proposals']] == ['accepted', 'open']
    assert ('Accept 2', DL + '/accept/2') in links_of(head)


# the deadline end to end: a synthetic ASN, the real aigm and roster

@pytest.fixture
def real(gm):
    """build(human=(), edit=None) puts a synthetic ASN of teams 1 (a 60-40 contender) and 2 (a 40-60 rebuilder) in the
    game, with deadline_league's rosters and the deal that makes (team 1's bench LF 109 for team 2's 1B 202), the
    league inside the deadline window, and the real aigm and roster doing the work. edit(windows, players) may change
    the rosters first. Returns (players, windows)."""
    def build(human=(), edit=None):
        mp = gm.monkeypatch
        players, windows = deadline_league((1, 2))
        deal(players)
        if edit:
            edit(windows, players)
        data, loc = make_asn(windows, human)
        mp.setattr(aigm, 'locate', lambda _data: loc)
        mp.setattr(aigm, 'read', REAL_READ)
        asn_file(gm).write_bytes(data)
        teams = {1: {'name': 'Reds', 'w': 60, 'l': 40, 'league': 'N', 'division': 'E'},
                 2: {'name': 'Cubs', 'w': 40, 'l': 60, 'league': 'N', 'division': 'E'}}
        stub_dl(mp, year=YEAR, teams=teams)
        mp.setattr(gamedata, 'players', lambda path: players)
        return players, windows
    return build


def windows_in(g):
    return aigm.read(asn_file(g).read_bytes())['windows']


def test_a_deadline_run_moves_the_veteran_to_the_contender_and_the_prospect_to_the_rebuilder(gm, real):
    players, before = real()
    vet, pro = pid_of(2, '1B'), bench_of(1)
    head, body = page(gm.ctx, gm.spool, DL + '/run')
    assert head['http'] == '200' and body.split('\n')[0] == '1 deadline trades made.'
    after = windows_in(gm)
    assert vet in after[1][:25] and vet not in after[2] and pro in after[2][:25] and pro not in after[1]
    assert after[1][aigm.ALIGNS[0] + 1] == vet
    assert roster.problems(after, players) == []
    assert len(backups(gm)) == 1
    (trade,) = dl_ledger_of(gm)['trades']
    assert (trade['c'], trade['r'], trade['vet'], trade['prospect']) == (1, 2, vet, pro)
    assert (trade['c_name'], trade['vet_name'], trade['prospect_name']) == ('Reds', '1B 50', 'LF 40')


def test_a_human_contender_gets_a_proposal_that_accept_writes_through_roster_move(gm, real):
    players, before = real(human=(1,))
    vet, pro = pid_of(2, '1B'), bench_of(1)
    page(gm.ctx, gm.spool, DL + '/run')
    assert windows_in(gm) == before and dl_ledger_of(gm)['trades'] == []
    assert [(p['c'], p['r'], p['vet'], p['prospect'], p['status']) for p in dl_ledger_of(gm)['proposals']] == \
        [(1, 2, vet, pro, 'open')]
    head, body = page(gm.ctx, gm.spool, DL + '/accept/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Trade made.'
    after = windows_in(gm)
    assert after == roster.move(roster.move(before, vet, 2, 1, players, YEAR), pro, 1, 2, players, YEAR)
    assert vet in after[1][:25] and pro in after[2][:25]
    assert dl_ledger_of(gm)['proposals'][0]['status'] == 'accepted'


def test_accept_of_a_proposal_whose_players_have_moved_is_stale_and_writes_nothing(gm, real):
    real(human=(1,))
    page(gm.ctx, gm.spool, DL + '/run')
    led = dl_ledger_of(gm)
    led['proposals'][0]['vet'] = pid_of(1, 'RF')                # not on team 2 (the proposal's rebuilder)
    dl_ledger_file(gm).write_text(json.dumps(led))
    before = asn_file(gm).read_bytes()
    head, body = page(gm.ctx, gm.spool, DL + '/accept/1')
    assert head['http'] == '200' and body.split('\n')[0] == 'Proposal 1 is out of date.'
    assert asn_file(gm).read_bytes() == before and backups(gm) == []
    assert dl_ledger_of(gm)['proposals'][0]['status'] == 'stale'


def test_accept_of_a_proposal_that_would_leave_a_new_problem_is_refused(gm, real):
    def thin(windows, players):
        for i in (14, 15):                                      # team 2 keeps five pitchers: the rotation
            windows[2][i] = 0
        windows[2][aigm.BULLPEN[0]:aigm.BULLPEN[0] + 2] = [0, 0]
    real(human=(1,), edit=thin)
    page(gm.ctx, gm.spool, DL + '/run')
    led = dl_ledger_of(gm)
    led['proposals'][0].update(vet=ace_of(2))                   # a pitcher goes to team 1 for a hitter: team 2 has four
    dl_ledger_file(gm).write_text(json.dumps(led))
    before = asn_file(gm).read_bytes()
    head, body = page(gm.ctx, gm.spool, DL + '/accept/1')
    assert head['http'] == '500' and body.split('\n')[0].startswith('Trade check failed: team ')
    assert asn_file(gm).read_bytes() == before and backups(gm) == []
    assert dl_ledger_of(gm)['proposals'][0]['status'] == 'open'
