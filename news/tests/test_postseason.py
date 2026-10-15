"""gamedata.postseason() on a stubbed member table: the bracket comes from the ASN's 'po' record (there are no game
files in the repo, so _members is replaced, the payloads are built from bytes and the ASN file is a placeholder)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402

FLAG = 0x80
ROUND1, ROUND2, ROUND3 = gamedata.PO_SERIES[1], gamedata.PO_SERIES[2], gamedata.PO_SERIES[3]


def block(best, winner, t1, t2, games):
    """A 20-byte series block. games is a list of (away_tid, away_runs, home_tid, home_runs); the wins and the team 2
    flags on the run bytes are derived from it."""
    b = bytearray(20)
    b[0], b[1], b[2], b[3] = best, winner, t1, t2
    wins = {t1: 0, t2: 0}
    for g, (away, away_runs, home, home_runs) in enumerate(games):
        assert {away, home} == {t1, t2} and away_runs != home_runs
        wins[away if away_runs > home_runs else home] += 1
        b[6 + g] = away_runs | (FLAG if away == t2 else 0)
        b[13 + g] = home_runs | (FLAG if home == t2 else 0)
    b[4], b[5] = wins[t1], wins[t2]
    return bytes(b)


def po(state, best=(5, 7, 7), blocks=None, size=283):
    """A po payload with the blocks ({offset: 20 bytes}) laid in."""
    p = bytearray(size)
    p[gamedata.PO_STATE] = state
    p[gamedata.PO_BEST:gamedata.PO_BEST + 3] = bytes(best)
    for off, raw in (blocks or {}).items():
        p[off:off + 20] = raw
    return bytes(p)


def sched(flag):
    """A 17-byte schedule payload with p[15] = flag."""
    p = bytearray(17)
    p[15] = flag
    return bytes(p)


def won(best, t1, t2, pattern):
    """A finished-or-partial series: pattern says who won each game ('1' or '2'), team 1 hosts the odd games. The
    winner byte is set once a team has best // 2 + 1 wins."""
    games = []
    for g, who in enumerate(pattern):
        home, away = (t1, t2) if g % 2 == 0 else (t2, t1)
        win = t1 if who == '1' else t2
        games.append((away, 5 if win == away else 3, home, 5 if win == home else 3))
    need = best // 2 + 1
    winner = t1 if pattern.count('1') == need else t2 if pattern.count('2') == need else 0
    return block(best, winner, t1, t2, games)


@pytest.fixture
def asn(tmp_path, monkeypatch):
    """A function that stubs the member table and returns the ASN path: asn(payload, s=[...]) for a po record."""
    path = tmp_path / 'MLBPA97.ASN'
    path.write_bytes(b'asn')

    def stub(payload, s=()):
        mem = {'s': [(0, x) for x in s]}
        if payload is not None:
            mem['po'] = [(1, payload)]
        monkeypatch.setattr(gamedata, '_members', lambda data: mem)
        return str(path)
    return stub


def test_the_worked_example_decodes_exactly(asn):
    raw = bytes([5, 20, 20, 29, 3, 1,
                 7, 10, 3 | FLAG, 1 | FLAG, 0, 0, 0,
                 6 | FLAG, 2 | FLAG, 2, 6, 0, 0, 0])
    assert raw == block(5, 20, 20, 29, [(20, 7, 29, 6), (20, 10, 29, 2), (29, 3, 20, 2), (29, 1, 20, 6)])
    got = gamedata.postseason(asn(po(0, blocks={ROUND1[0]: raw})))
    s = got['rounds'][0]['series'][0]
    assert s == {'best_of': 5, 'teams': [20, 29], 'wins': [3, 1], 'winner': 20, 'home': 29, 'games': [
        {'away': 20, 'home': 29, 'away_runs': 7, 'home_runs': 6},
        {'away': 20, 'home': 29, 'away_runs': 10, 'home_runs': 2},
        {'away': 29, 'home': 20, 'away_runs': 3, 'home_runs': 2},
        {'away': 29, 'home': 20, 'away_runs': 1, 'home_runs': 6}]}


def test_a_complete_bracket_gives_the_champion_and_every_series_matches_its_games(asn):
    blocks = {}
    for off, (t1, t2) in zip(ROUND1, ((1, 2), (3, 4), (5, 6), (7, 8))):
        blocks[off] = won(5, t1, t2, '1121')
    blocks[ROUND2[0]] = won(7, 1, 3, '1122121')
    blocks[ROUND2[1]] = won(7, 5, 7, '2222')
    blocks[ROUND3[0]] = won(7, 1, 7, '2121212')
    got = gamedata.postseason(asn(po(2, blocks=blocks)))
    assert got['complete'] is True and got['champion'] == 7 and got['best_of'] == [5, 7, 7]
    assert [r['round'] for r in got['rounds']] == [1, 2, 3]
    assert [len(r['series']) for r in got['rounds']] == [4, 2, 1]
    for rnd in got['rounds']:
        for s in rnd['series']:
            t1, t2 = s['teams']
            won_by = [g['away'] if g['away_runs'] > g['home_runs'] else g['home'] for g in s['games']]
            assert s['wins'] == [won_by.count(t1), won_by.count(t2)]
            assert len(s['games']) == sum(s['wins']) and s['winner'] == (t1 if s['wins'][0] > s['wins'][1] else t2)
    assert got['rounds'][2]['series'][0]['winner'] == 7


def test_a_seven_game_world_series_with_team_1_hosting_game_1(asn):
    ws = won(7, 5, 9, '1212122')
    got = gamedata.postseason(asn(po(2, blocks={ROUND3[0]: ws})))
    s = got['rounds'][2]['series'][0]
    assert s['home'] == 5 and s['teams'] == [5, 9] and len(s['games']) == 7
    assert s['games'][0]['home'] == 5 and s['games'][1]['home'] == 9
    assert got['champion'] == 9 and s['wins'] == [3, 4]


def test_a_not_started_bracket(asn):
    blocks = {off: block(5, 0, t1, t1 + 1, []) for off, t1 in zip(ROUND1, (1, 3, 5, 7))}
    got = gamedata.postseason(asn(po(0, blocks=blocks)))
    assert got['complete'] is False and got['champion'] is None
    assert len(got['rounds'][0]['series']) == 4
    for s in got['rounds'][0]['series']:
        assert s['games'] == [] and s['home'] is None and s['wins'] == [0, 0] and s['winner'] is None
    assert got['rounds'][1]['series'] == [] and got['rounds'][2]['series'] == []


def test_the_champion_needs_a_complete_bracket_and_a_decided_final(asn):
    ws = won(7, 5, 9, '1111')
    assert gamedata.postseason(asn(po(1, blocks={ROUND3[0]: ws})))['champion'] is None
    assert gamedata.postseason(asn(po(2, blocks={ROUND3[0]: ws})))['champion'] == 5
    assert gamedata.postseason(asn(po(2, blocks={ROUND3[0]: block(7, 0, 5, 9, [])})))['champion'] is None
    assert gamedata.postseason(asn(po(2)))['champion'] is None


def test_current_follows_the_postseason_schedule_records(asn):
    p = po(2, blocks={ROUND3[0]: won(7, 5, 9, '1111')})
    assert gamedata.postseason(asn(p, s=[sched(0), sched(1), sched(2)]))['current'] is True
    assert gamedata.postseason(asn(p, s=[sched(0), sched(2), sched(0)]))['current'] is False
    assert gamedata.postseason(asn(p))['current'] is False
    assert gamedata.postseason(asn(p, s=[bytes(15)]))['current'] is False


def test_a_shutout_decodes_to_zero_runs_for_the_right_team(asn):
    raw = block(5, 0, 4, 8, [(8, 0, 4, 3), (4, 0, 8, 2)])
    assert raw[6] & FLAG and not raw[13] & FLAG                 # game 1: away is team 2, scoreless, flag set
    assert not raw[7] & FLAG and raw[14] & FLAG                 # game 2: away is team 1, scoreless, flag clear
    got = gamedata.postseason(asn(po(0, blocks={ROUND1[0]: raw})))
    assert got['rounds'][0]['series'][0]['games'] == [
        {'away': 8, 'home': 4, 'away_runs': 0, 'home_runs': 3},
        {'away': 4, 'home': 8, 'away_runs': 0, 'home_runs': 2}]


def test_an_unused_block_is_skipped_whatever_it_holds(asn):
    junk = bytes([0, 99, 0, 0, 9, 9]) + bytes(14)
    got = gamedata.postseason(asn(po(0, blocks={ROUND1[0]: junk, ROUND1[1]: block(5, 0, 1, 2, [])})))
    assert [s['teams'] for s in got['rounds'][0]['series']] == [[1, 2]]


def test_the_highest_team_id_is_accepted(asn):
    got = gamedata.postseason(asn(po(0, blocks={ROUND1[0]: block(5, 0, gamedata.MAX_TEAM - 1, gamedata.MAX_TEAM, [])})))
    assert got['rounds'][0]['series'][0]['teams'] == [33, 34]


def test_no_po_member_is_none(asn, monkeypatch, tmp_path):
    assert gamedata.postseason(asn(None)) is None
    path = tmp_path / 'x.ASN'
    path.write_bytes(b'asn')
    monkeypatch.setattr(gamedata, '_members', lambda data: {'po': []})
    assert gamedata.postseason(str(path)) is None


def test_a_short_payload_is_none(asn):
    good = po(0, blocks={ROUND3[0]: block(7, 0, 5, 9, [])})
    assert gamedata.postseason(asn(good[:243])) is not None
    assert gamedata.postseason(asn(good[:242])) is None
    assert gamedata.postseason(asn(b'')) is None


def test_no_best_of_for_round_1_is_none(asn):
    assert gamedata.postseason(asn(po(2, best=(0, 7, 7)))) is None


def mutated(off, at):
    """A po payload with a played best-of-7 block at off, its bytes at the given positions replaced: {2: 99}."""
    raw = bytearray(block(7, 0, 5, 9, [(9, 4, 5, 6), (9, 1, 5, 2)]))
    for pos, val in at.items():
        raw[pos] = val
    return po(0, best=(7, 7, 7), blocks={off: bytes(raw)})


@pytest.mark.parametrize('at', [
    {2: 0}, {3: 0}, {2: 99}, {3: 99}, {2: gamedata.MAX_TEAM + 1}, {2: 9}, {3: 5},       # ids 0, 99, 35; equal teams
    {4: 5}, {5: 5}, {4: 4, 5: 4}, {4: 1, 5: 7},                                          # wins past best // 2 + 1, or 7
    {1: 7}, {1: 99}, {1: 1},                                                             # a winner who is a third team
])
def test_a_malformed_block_is_none(asn, at):
    assert gamedata.postseason(asn(mutated(ROUND1[0], at))) is None


@pytest.mark.parametrize('off', [ROUND1[3], ROUND2[1], ROUND3[0]])
def test_a_malformed_block_in_any_round_is_none(asn, off):
    assert gamedata.postseason(asn(mutated(off, {5: 5}))) is None
    assert gamedata.postseason(asn(mutated(off, {1: 3}))) is None
    assert gamedata.postseason(asn(mutated(off, {}))) is not None
