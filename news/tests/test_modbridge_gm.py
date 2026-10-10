"""The offseason trade pages under /news/gm/ through modbridge.process_spool: every route and every 404; the overview
with and without a ledger, preseason and started, and a ledger for an older season (missing); run (the ASN, its backup
and the ledger, once a season, refused once started, while the game holds the files, and when the trade check fails);
accept (written, stale, closed, while the game holds the files, and when the check fails); reject; and the Offseason
trades link on an association page. aigm's read, plan, apply_trade and validate are faked, gamedata's association and
players are stubbed, and create.open_by_anyone is patched. Helpers and fixtures come from test_modbridge.py.
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
from tests.test_modbridge import NAMES, ask, bridge, serve_pages, site   # noqa: E402,F401

GM = '/news/gm/TEST77'
TITLE = 'Offseason trades: 1977 Major Leagues'
OPEN = '1977 Major Leagues is open in the game. Go back to the main menu, then try again.'
TEAMS = {1: {'name': 'Reds'}, 2: {'name': 'Cubs'}}
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
def gm(bridge, site, monkeypatch):
    """The bridge on the site with the association stubbed; aigm's calls answer from fake: its plan and problems (what
    validate returns), and every ASN is read as READS says (b'asn' is the file as it starts, b'after' as a trade
    leaves it)."""
    ctx, spool = bridge
    game, data, backup, donor, proc = site
    stub_gm(monkeypatch)
    monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': [])
    fake = types.SimpleNamespace(plan={'trades': [TRADE], 'proposals': [PROPOSAL]}, problems=[])
    reads = {b'asn': {'windows': {1: [0] * 126, 2: [0] * 126}, 'human': frozenset({1})},
             b'after': {'windows': {1: [1] * 126, 2: [2] * 126}, 'human': frozenset({1})}}
    monkeypatch.setattr(aigm, 'read', lambda asn: reads[asn])
    monkeypatch.setattr(aigm, 'plan', lambda windows, players, year, human=frozenset(): fake.plan)
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
                                "Computer-run teams trade bench players to fill each other's needs. "
                                "Human-run teams only get proposals."]


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

def test_an_association_page_links_to_its_offseason_trades_after_player_development(bridge, monkeypatch):
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
