"""The midseason moves pages under /news/gm/<STEM>/moves through modbridge.process_spool: no MOV (or one for another
season, or a malformed one), the lines (pending, due, done, skipped) and the apply link only when a move is due, the
Midseason moves link on the overview, apply (the ASN, its backup and the ledger written, the lock held, refused while
the game holds the files, with nothing due, and when the result has a new problem) and every 404. The ASN is a
synthetic one (test_aigm.make_asn) read through the real roster.py; gamedata's association and players are stubbed and
create.open_by_anyone is patched. Helpers and fixtures come from test_modbridge.py and test_roster.py."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aigm        # noqa: E402
import create      # noqa: E402
import gamedata    # noqa: E402
import modbridge   # noqa: E402
import roster      # noqa: E402
from tests.test_aigm import make_asn   # noqa: E402
from tests.test_modbridge import NAMES, ask, bridge, site   # noqa: E402,F401
from tests.test_roster import two      # noqa: E402

GM = '/news/gm/TEST77'
TITLE = 'Midseason moves: 1977 Major Leagues'
OPEN = '1977 Major Leagues is open in the game. Go back to the main menu, then try again.'
TEAMS = {1: {'name': 'Reds'}, 2: {'name': 'Cubs'}}
NO_MOVES = ['No real midseason moves for this association.']
TAIL = [('Offseason trades', GM + '/'), ('League news', '/news/TEST77/')]


def move(pid, name, frm, to, at):
    return {'pid': pid, 'name': name, 'from': frm, 'to': to, 'at': at}


MOVES = [move(110, 'Ben Bench', 1, 2, 0.5), move(203, 'Sam Second', 2, 1, 0.9), move(201, 'Wes Wrong', 1, 2, 0.3),
         move(111, 'Pete Pitcher', 1, 2, 0.4)]


def doc(moves=MOVES, year=1977):
    return {'kind': 'moves', 'year': year, 'moves': list(moves)}


class World:
    """The bridge on a synthetic game: a real synthetic ASN for TEST77 (teams 1 and 2, windows from test_roster.two),
    the MOV and the ledger helpers, and the schedule (10 games between the teams, `played` of them played)."""

    def __init__(self, ctx, spool, game, data, backup, monkeypatch):
        self.ctx, self.spool, self.game, self.data, self.backup = ctx, spool, game, data, backup
        self.monkeypatch = monkeypatch
        self.windows, self.players = two()
        self.asn_bytes, self.loc = make_asn(self.windows)
        (game / 'Assn' / 'TEST77.ASN').write_bytes(self.asn_bytes)
        monkeypatch.setattr(aigm, 'locate', lambda _data: self.loc)
        self.played = 0
        self.held = []
        monkeypatch.setattr(gamedata, 'association', self.association)
        monkeypatch.setattr(gamedata, 'players', lambda path: self.players)
        monkeypatch.setattr(create, 'open_by_anyone', lambda paths, proc='/proc': self.held)

    def association(self, path):
        games = [{'away': 1, 'home': 2, 'played': i < self.played} for i in range(10)]
        return {'name': NAMES[os.path.basename(path)], 'season_year': 1977, 'teams': TEAMS, 'games': games}

    def page(self, path):
        return ask(self.ctx, self.spool, 'op=news\npath=' + path)

    def write_mov(self, d=None, name='TEST77.MOV'):
        (self.game / 'Assn' / name).write_text(json.dumps(doc() if d is None else d))

    def ledger_file(self):
        return self.data / 'TEST77' / 'moves.json'

    def write_ledger(self, done, year=1977):
        self.ledger_file().parent.mkdir(parents=True, exist_ok=True)
        self.ledger_file().write_text(json.dumps({'kind': 'moves', 'year': year, 'done': done}))

    def ledger(self):
        return json.loads(self.ledger_file().read_text())

    def asn(self):
        return (self.game / 'Assn' / 'TEST77.ASN').read_bytes()

    def backups(self):
        return sorted(self.backup.glob('TEST77-*-gm*')) if self.backup.exists() else []

    def assert_nothing_written(self):
        assert self.asn() == self.asn_bytes
        assert self.backups() == [] and not self.ledger_file().exists()


@pytest.fixture
def world(request, monkeypatch):
    ctx, spool = request.getfixturevalue('bridge')
    game, data, backup, donor, proc = request.getfixturevalue('site')
    return World(ctx, spool, game, data, backup, monkeypatch)


def links_of(head):
    return [tuple(head['link.%d' % i].split('\t')) for i in range(int(head['count']))]


def lines_of(body):
    """The page's lines after its heading (a note, when there is one, comes before the heading)."""
    lines = body.split('\n')
    return lines[next(i for i, line in enumerate(lines) if line and set(line) == {'='}) + 2:]


def note_of(body):
    lines = body.split('\n')
    return lines[0] if lines[0] != TITLE else ''


# the page

def test_no_mov_says_there_are_no_moves_and_offers_no_apply(world):
    head, body = world.page(GM + '/moves')
    assert head['http'] == '200' and head['title'] == TITLE and head['path'] == GM + '/moves'
    assert body.split('\n') == [TITLE, '=' * len(TITLE), ''] + NO_MOVES
    assert links_of(head) == TAIL


@pytest.mark.parametrize('bad', [
    doc(year=1976),                                          # another season
    dict(doc(), kind='trades'),
    {'kind': 'moves', 'year': 1977},                         # no moves list
    doc([move(110, 'Ben Bench', 1, 2, 0.5), {'pid': 'x'}]),   # one malformed move spoils the file
    doc([dict(move(110, 'Ben Bench', 1, 2, 0.5), at='half')]),
    doc([dict(move(110, 'Ben Bench', 1, 2, 0.5), name=7)]),
    doc([dict(move(110, 'Ben Bench', 1, 2, 0.5), to=True)]),
])
def test_a_mov_for_another_season_or_malformed_counts_as_none(world, bad):
    world.played = 10
    world.write_mov(bad)
    head, body = world.page(GM + '/moves')
    assert lines_of(body) == NO_MOVES and links_of(head) == TAIL
    assert ('Midseason moves', GM + '/moves') not in links_of(world.page(GM + '/')[0])


def test_an_unreadable_mov_counts_as_none(world):
    (world.game / 'Assn' / 'TEST77.MOV').write_text('{not json')
    assert lines_of(world.page(GM + '/moves')[1]) == NO_MOVES


def test_an_empty_mov_says_there_are_no_moves(world):
    world.write_mov(doc([]))
    assert lines_of(world.page(GM + '/moves')[1]) == NO_MOVES


def test_a_move_is_pending_until_its_team_has_played_enough(world):
    world.write_mov()
    world.played = 3                                          # moves 0, 1, 2, 3 need 5, 9, 3, 4 games
    head, body = world.page(GM + '/moves')
    assert lines_of(body) == [
        'Ben Bench: Reds to Cubs at 50% of the season (pending)',
        'Sam Second: Cubs to Reds at 90% of the season (pending)',
        'Wes Wrong: Reds to Cubs at 30% of the season (due)',
        'Pete Pitcher: Reds to Cubs at 40% of the season (pending)']
    assert links_of(head) == [('Apply due moves', GM + '/moves/apply')] + TAIL


def test_the_lines_show_done_and_skipped_from_the_ledger(world):
    world.write_mov()
    world.played = 5
    world.write_ledger({'0': {'status': 'done', 'played': 5},
                        '2': {'status': 'skipped', 'reason': '201 is not on the roster of team 1', 'played': 5}})
    head, body = world.page(GM + '/moves')
    assert lines_of(body) == [
        'Ben Bench: Reds to Cubs at 50% of the season (done)',
        'Sam Second: Cubs to Reds at 90% of the season (pending)',
        'Wes Wrong: Reds to Cubs at 30% of the season (skipped: 201 is not on the roster of team 1)',
        'Pete Pitcher: Reds to Cubs at 40% of the season (due)']
    assert links_of(head)[0] == ('Apply due moves', GM + '/moves/apply')


def test_there_is_no_apply_link_when_nothing_is_due(world):
    world.write_mov()
    world.played = 5
    world.write_ledger({'0': {'status': 'done', 'played': 5}, '2': {'status': 'done', 'played': 5},
                        '3': {'status': 'done', 'played': 5}})
    assert links_of(world.page(GM + '/moves')[0]) == TAIL
    world.played = 0
    assert links_of(world.page(GM + '/moves')[0]) == TAIL


def test_a_ledger_of_another_season_or_kind_is_ignored(world):
    world.write_mov()
    world.played = 5
    world.write_ledger({'0': {'status': 'done', 'played': 5}}, year=1976)
    assert lines_of(world.page(GM + '/moves')[1])[0].endswith('(due)')
    world.ledger_file().write_text(json.dumps({'kind': 'gm', 'year': 1977, 'done': {'0': {'status': 'done'}}}))
    assert lines_of(world.page(GM + '/moves')[1])[0].endswith('(due)')
    world.ledger_file().write_text('{torn')
    assert lines_of(world.page(GM + '/moves')[1])[0].endswith('(due)')


def test_the_mov_is_found_without_regard_to_case_and_a_team_without_a_name_is_numbered(world, monkeypatch):
    world.write_mov(doc([move(110, 'Ben Bench', 1, 7, 0.5)]), name='test77.mov')
    assert lines_of(world.page(GM + '/moves')[1]) == ['Ben Bench: Reds to Team 7 at 50% of the season (pending)']


def test_a_name_with_a_line_break_stays_on_one_line(world):
    world.write_mov(doc([move(110, 'Ben\nBench\tJr', 1, 2, 0.5)]))
    assert lines_of(world.page(GM + '/moves')[1]) == ['Ben Bench Jr: Reds to Cubs at 50% of the season (pending)']


# the overview link

def test_the_overview_links_to_the_moves_only_when_a_mov_exists(world):
    assert 'Midseason moves' not in str(links_of(world.page(GM + '/')[0]))
    world.write_mov()
    assert links_of(world.page(GM + '/')[0]) == [
        ('Run computer trades', GM + '/run'), ('Midseason moves', GM + '/moves'),
        ('Player development', '/news/development/TEST77/'), ('League news', '/news/TEST77/')]


# apply

def test_apply_moves_the_due_players_backs_up_the_asn_and_writes_the_ledger(world):
    world.write_mov()
    world.played = 5                                          # moves 0 (5 games), 2 (3) and 3 (4) are due
    head, body = world.page(GM + '/moves/apply')
    assert head['http'] == '200' and head['path'] == GM + '/moves'
    assert note_of(body) == '2 moves made, 1 skipped.'
    after = aigm.read(world.asn())['windows']
    expect = roster.move(roster.move(world.windows, 110, 1, 2, world.players, 1977), 111, 1, 2, world.players, 1977)
    assert after == expect
    assert world.ledger() == {'kind': 'moves', 'year': 1977, 'done': {
        '0': {'status': 'done', 'played': 5},
        '2': {'status': 'skipped', 'reason': '201 is not on the roster of team 1', 'played': 5},
        '3': {'status': 'done', 'played': 5}}}
    (folder,) = world.backups()
    assert (folder / 'TEST77.ASN').read_bytes() == world.asn_bytes
    assert lines_of(body) == ['Ben Bench: Reds to Cubs at 50% of the season (done)',
                    'Sam Second: Cubs to Reds at 90% of the season (pending)',
                    'Wes Wrong: Reds to Cubs at 30% of the season (skipped: 201 is not on the roster of team 1)',
                    'Pete Pitcher: Reds to Cubs at 40% of the season (done)']
    assert links_of(head) == TAIL


def test_apply_changes_only_the_two_windows(world):
    world.write_mov()
    world.played = 5
    world.page(GM + '/moves/apply')
    new, old = world.asn(), world.asn_bytes
    assert len(new) == len(old)
    changed = {i for i in range(len(old)) if old[i] != new[i]}
    inside = set()
    for tid in (1, 2):
        off = world.loc['r'][tid][0]
        inside |= set(range(off + 42, off + 294))
    assert changed and changed <= inside


def test_a_second_apply_has_nothing_due_and_writes_nothing(world):
    world.write_mov()
    world.played = 5
    world.page(GM + '/moves/apply')
    asn, ledger = world.asn(), world.ledger()
    head, body = world.page(GM + '/moves/apply')
    assert head['http'] == '409' and note_of(body) == 'No moves are due.'
    assert world.asn() == asn and world.ledger() == ledger and len(world.backups()) == 1


def test_apply_later_runs_only_the_newly_due_moves(world):
    world.write_mov()
    world.played = 4                                          # moves 2 and 3 are due
    world.page(GM + '/moves/apply')
    world.played = 5
    head, body = world.page(GM + '/moves/apply')
    assert note_of(body) == '1 moves made, 0 skipped.'
    assert sorted(world.ledger()['done']) == ['0', '2', '3']
    assert len(world.backups()) == 2


def test_apply_with_nothing_due_is_refused_and_writes_nothing(world):
    world.write_mov()
    head, body = world.page(GM + '/moves/apply')
    assert head['status'] == 'error' and head['http'] == '409' and note_of(body) == 'No moves are due.'
    world.assert_nothing_written()


def test_apply_is_refused_while_the_game_holds_the_files(world):
    world.write_mov()
    world.played = 5
    world.held = [world.game / 'Assn' / 'TEST77.ASN']
    head, body = world.page(GM + '/moves/apply')
    assert head['http'] == '409' and note_of(body) == OPEN
    world.assert_nothing_written()
    assert links_of(head)[0] == ('Apply due moves', GM + '/moves/apply')


def test_apply_without_a_mov_for_the_season_is_not_found(world):
    world.played = 10
    assert world.page(GM + '/moves/apply')[0]['http'] == '404'
    world.write_mov(doc(year=1976))
    assert world.page(GM + '/moves/apply')[0]['http'] == '404'
    world.assert_nothing_written()


def test_skipped_moves_alone_write_the_ledger_but_not_the_asn(world):
    world.write_mov(doc([move(201, 'Wes Wrong', 1, 2, 0.3)]))
    world.played = 5
    head, body = world.page(GM + '/moves/apply')
    assert head['http'] == '200' and note_of(body) == '0 moves made, 1 skipped.'
    assert world.asn() == world.asn_bytes and world.backups() == []
    assert world.ledger()['done']['0']['status'] == 'skipped'


def test_a_result_with_a_new_problem_writes_nothing(world):
    pitchers = [move(pid, 'P%d' % pid, 1, 2, 0.1) for pid in (115, 116, 117)]      # team 1 would have 4 pitchers
    world.write_mov(doc(pitchers))
    world.played = 5
    head, body = world.page(GM + '/moves/apply')
    assert head['http'] == '500' and note_of(body) == 'Move check failed: team 1 has 4 active pitchers, needs 5'
    world.assert_nothing_written()


def test_apply_runs_under_the_gm_lock_and_hands_roster_the_league(world):
    world.write_mov()
    world.played = 5
    seen = []
    real = roster.apply_due

    def spy(asn, d, assoc, players, year, ledger):
        seen.append((modbridge._GM_LOCK.locked(), d, len(assoc['games']), players is world.players, year, ledger))
        return real(asn, d, assoc, players, year, ledger)

    world.monkeypatch.setattr(roster, 'apply_due', spy)
    world.page(GM + '/moves/apply')
    assert seen == [(True, doc(), 10, True, 1977, None)]
    assert not modbridge._GM_LOCK.locked()


@pytest.mark.parametrize('path', [
    '/news/gm/NOPE/moves', '/news/gm/NOPE/moves/apply', '/news/gm/TEST77/moves/', '/news/gm/TEST77/moves/apply/',
    '/news/gm/TEST77/moves/x', '/news/gm/TEST77/moves/apply/1', '/news/gm/TEST77/moves?x=1', '/news/gm/TEST77/move',
])
def test_every_other_path_is_not_found(world, path):
    world.write_mov()
    world.played = 5
    assert world.page(path)[0]['http'] == '404'
    world.assert_nothing_written()
