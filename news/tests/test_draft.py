"""draft.py on synthetic leagues: needs, the need flag, team grades, the class as the public scouts saw it, and the revisit."""
import copy
import os
import statistics
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import contracts  # noqa: E402
import draft      # noqa: E402
import fog        # noqa: E402

YEAR = 1998


def player(name, pos, rating=50, born=1975, seasons=0, **over):
    """A gamedata.players() entry whose rated fields are all `rating` (a hitter's pitching ratings and a pitcher's
    hitting ratings are 0, which means not rated)."""
    pitcher = pos == 'P'
    p = {'name': name, 'pos': pos, 'bats': 'R', 'throws': 'R', 'born': born, 'seasons': seasons,
         'contact': 0 if pitcher else rating, 'power': 0 if pitcher else rating, 'speed': 0 if pitcher else rating,
         'fielding': rating, 'control': rating if pitcher else 0, 'strikeout': rating if pitcher else 0,
         'stamina': rating if pitcher else 0}
    p.update(over)
    return p


def test_grades_are_a_hitters_four_or_a_pitchers_three_on_the_scale():
    assert draft.grades(player('A', 'CF', 99)) == {'contact': 80, 'power': 80, 'speed': 80, 'fielding': 80}
    assert draft.grades(player('A', 'P', 0)) == {'control': 20, 'strikeout': 20, 'stamina': 20}
    assert draft.grades(player('A', 'SS', 50, fielding=None))['fielding'] is None


def test_needs_a_position_whose_best_player_grades_below_45_and_a_position_nobody_plays():
    # rating 38 grades 45, rating 37 grades 40: the mean of the four grades is the player's score
    ok = [player('A', pos, 38) for pos in draft.NEED_POSITIONS] + [player('P%d' % i, 'P', 38) for i in range(11)]
    assert draft.team_needs(ok) == []
    weak = [player('A', pos, 37 if pos in ('C', 'SS') else 38) for pos in draft.NEED_POSITIONS]
    weak += [player('P%d' % i, 'P', 38) for i in range(11)]
    assert draft.team_needs(weak) == ['C', 'SS']
    assert draft.team_needs([p for p in ok if p['pos'] != 'LF']) == ['LF']      # no left fielder at all
    # the best at the position counts, not the worst
    assert draft.team_needs(ok + [player('Scrub', '1B', 0)]) == []
    assert draft.team_needs([dict(p, pos='1B') if p['pos'] == '2B' else p for p in ok]) == ['2B']


def test_needs_arms_when_fewer_than_eleven_pitchers_grade_45_or_better():
    hitters = [player('A', pos, 99) for pos in draft.NEED_POSITIONS]
    arms = [player('P%d' % i, 'P', 38) for i in range(11)]
    assert draft.team_needs(hitters + arms) == []
    assert draft.team_needs(hitters + arms[:10]) == ['P']
    assert draft.team_needs(hitters + arms[:10] + [player('Weak', 'P', 37)]) == ['P']     # grades 40: not counted
    assert draft.team_needs(hitters + arms[:10] + [player('Ace', 'P', 99)]) == []
    assert draft.team_needs([]) == list(draft.NEED_POSITIONS) + ['P']


def test_needs_p_comes_last_after_the_positions_in_order():
    assert draft.team_needs([player('A', 'CF', 99)]) == ['C', '1B', '2B', '3B', 'SS', 'LF', 'RF', 'P']


@pytest.mark.parametrize('values, want', [
    ({1: 10.0}, {1: 'C'}),                                  # one team only
    ({1: 5.0, 2: 5.0, 3: 5.0}, {1: 'C', 2: 'C', 3: 'C'}),   # all equal: no spread
    ({1: 12.0, 2: 8.0}, {1: 'A', 2: 'D'}),                  # two teams sit at z = +1 and -1
    ({}, {}),
])
def test_letters_small_leagues(values, want):
    assert draft.letters(values) == want


def test_letters_bands_by_z_score():
    base = {tid: float(tid) for tid in range(1, 31)}
    got = draft.letters(base)
    mean, sd = statistics.fmean(base.values()), statistics.pstdev(base.values())
    for tid, v in base.items():
        z = (v - mean) / sd
        want = 'A' if z >= 1 else 'B' if z >= 0.33 else 'C' if z >= -0.33 else 'D' if z >= -1 else 'F'
        assert got[tid] == want
    assert set(got.values()) == {'A', 'B', 'C', 'D', 'F'}
    assert got[30] == 'A' and got[1] == 'F' and got[15] == 'C'


def test_letters_a_total_exactly_on_a_band_edge_takes_the_higher_grade():
    # two teams: z is exactly +1 and -1, the edges of A and D
    assert draft.letters({1: 1.0, 2: 3.0}) == {1: 'D', 2: 'A'}
    # three totals 0, 0, 3: mean 1, population sd sqrt(2); z = -0.707 (D) twice and +1.414 (A)
    assert draft.letters({1: 0.0, 2: 0.0, 3: 3.0}) == {1: 'D', 2: 'D', 3: 'A'}
    # six totals 0,0,0,0,0,6: mean 1, sd sqrt(5) = 2.236; z = -0.447 (D) and +2.236 (A)
    assert draft.letters(dict(enumerate([0.0] * 5 + [6.0]))) == {0: 'D', 1: 'D', 2: 'D', 3: 'D', 4: 'D', 5: 'A'}


def test_class_pids_reads_hitters_then_pitchers_and_skips_what_is_not_a_pid():
    rec = {'facts': {'hitters': [{'pid': 3}, {'pid': 'x'}, 'y', {'name': 'no pid'}, {'pid': True}],
                     'pitchers': [{'pid': 9}, {'pid': 5}]}}
    assert draft.class_pids(rec) == [3, 9, 5]
    assert draft.class_pids({'facts': {'hitters': 'x'}}) == []
    assert draft.class_pids({'facts': []}) == [] and draft.class_pids({}) == [] and draft.class_pids(None) == []


# A league of two teams. Ash (1) has a full roster of average men except no catcher (a need) and ten arms; Birch (2) is
# strong everywhere with eleven arms. The class: a catcher and a pitcher on Ash, a shortstop on Birch, a free agent.
def league():
    players, rosters = {}, {1: [], 2: []}
    pid = 1000
    for tid, rating in ((1, 60), (2, 60)):
        for pos in draft.NEED_POSITIONS:
            if tid == 1 and pos == 'C':
                continue
            pid += 1
            players[pid] = player('%d %s' % (tid, pos), pos, rating, seasons=8)
            rosters[tid].append(pid)
        for i in range(10 if tid == 1 else 11):
            pid += 1
            players[pid] = player('%d arm %d' % (tid, i), 'P', rating, seasons=8)
            rosters[tid].append(pid)
    players.update({
        201: player('Cal Catcher', 'C', 70, born=1978),
        202: player('Pat Pitcher', 'P', 60, born=1977),
        203: player('Sam Short', 'SS', 80, born=1979),
        204: player('Fran Free', '1B', 50, born=None),
    })
    rosters[1] += [201, 202]
    rosters[2] += [203]
    return players, rosters, {1: 'Ash', 2: 'Birch'}


def built():
    players, rosters, names = league()
    return draft.build(YEAR, 'A', [201, 202, 203, 204, 999], players, rosters, names), players, rosters, names


def test_build_lists_the_picks_best_value_first_with_fogged_grades_and_values():
    doc, players, rosters, names = built()
    assert doc['year'] == YEAR and doc['revisit'] is None and 999 not in [p['pid'] for p in doc['picks']]
    values = [p['value'] for p in doc['picks']]
    assert values == sorted(values, reverse=True)
    for pick in doc['picks']:
        seen = fog.view(players[pick['pid']], 'A', 0, YEAR, pid=pick['pid'])
        assert pick['grades'] == draft.grades(seen)
        assert pick['value'] == contracts._index(seen) and type(pick['value']) is float
        assert pick['name'] == players[pick['pid']]['name'] and pick['pos'] == players[pick['pid']]['pos']
    # what is shown is the fogged read, not the true one, for at least some pick
    assert any(pick['grades'] != draft.grades(players[pick['pid']]) for pick in doc['picks'])


def test_build_pick_team_age_and_free_agent():
    doc, players, rosters, names = built()
    by = {p['pid']: p for p in doc['picks']}
    assert (by[201]['team'], by[201]['tid'], by[201]['age']) == ('Ash', 1, 20)
    assert (by[203]['team'], by[203]['tid'], by[203]['age']) == ('Birch', 2, 19)
    assert (by[204]['team'], by[204]['tid'], by[204]['age'], by[204]['need']) == ('free agent', None, None, False)
    assert list(by[202]) == ['pid', 'name', 'pos', 'age', 'team', 'tid', 'grades', 'value', 'need']


def test_build_need_is_read_without_the_picks_so_a_pick_can_fill_it():
    doc, players, rosters, names = built()
    by = {p['pid']: p for p in doc['picks']}
    teams = {t['tid']: t for t in doc['teams']}
    # Ash has no catcher before Cal arrives: a need he fills (he is on the roster already, but is left out of the read)
    assert teams[1]['needs'] == ['C', 'P'] and by[201]['need'] is True
    assert by[202]['need'] is True                         # Ash has ten arms: Pat is an arm it needs
    assert teams[2]['needs'] == [] and by[203]['need'] is False


def test_build_teams_are_those_with_picks_best_total_first_graded_among_themselves():
    doc, players, rosters, names = built()
    assert [t['tid'] for t in doc['teams']] == sorted(
        (t['tid'] for t in doc['teams']), key=lambda tid: -next(t['value'] for t in doc['teams'] if t['tid'] == tid))
    by = {p['pid']: p for p in doc['picks']}
    for t in doc['teams']:
        mine = [p for p in doc['picks'] if p['tid'] == t['tid']]
        assert t['picks'] == len(mine) and t['value'] == sum(p['value'] for p in mine)
        assert list(t) == ['tid', 'name', 'picks', 'value', 'grade', 'needs']
    assert {t['tid']: t['picks'] for t in doc['teams']} == {1: 2, 2: 1}
    assert draft.letters({t['tid']: t['value'] for t in doc['teams']}) == {t['tid']: t['grade'] for t in doc['teams']}
    assert by[204]['tid'] is None and len(doc['teams']) == 2        # the free agent adds no team


def test_build_a_league_with_one_team_that_picks_grades_it_c():
    players, rosters, names = league()
    doc = draft.build(YEAR, 'A', [201], players, rosters, names)
    assert [(t['tid'], t['grade']) for t in doc['teams']] == [(1, 'C')]


def test_build_changes_no_true_rating_and_is_deterministic():
    players, rosters, names = league()
    before = copy.deepcopy(players)
    a = draft.build(YEAR, 'A', [201, 202, 203, 204], players, rosters, names)
    assert players == before
    assert a == draft.build(YEAR, 'A', [201, 202, 203, 204], players, rosters, names)
    other = draft.build(YEAR, 'B', [201, 202, 203, 204], players, rosters, names)
    assert {p['pid']: p['grades'] for p in other['picks']} != {p['pid']: p['grades'] for p in a['picks']}
    assert draft.build(YEAR, 'A', [], players, rosters, names)['picks'] == []


def test_build_works_with_nothing_rostered():
    players, rosters, names = league()
    doc = draft.build(YEAR, 'A', [204], players, {1: [], 2: []}, names)
    assert doc['teams'] == [] and doc['picks'][0]['tid'] is None


def line(g=10):
    return {'g': g}


def test_seasons_played_counts_years_with_a_bat_or_pit_line_once():
    archives = [(1997, {'bat': {'5': line()}, 'pit': {}}), (1998, {'bat': {'5': line()}, 'pit': {'5': line()}}),
                (1999, {'bat': {}, 'pit': {'5': line(), '6': line()}}), (2000, {'bat': {'6': line()}}),
                (2001, {'bat': 'x', 'pit': {'5': 'x'}})]
    assert draft.seasons_played(archives, [5, 6, 7], 1998) == {5: 2, 6: 2, 7: 0}
    assert draft.seasons_played(archives, [5], 1997) == {5: 3}      # `since` is inclusive
    assert draft.seasons_played([], [5], 1997) == {5: 0}


def test_revisit_uses_true_grades_now_seasons_and_two_points_a_season():
    doc, players, rosters, names = built()
    later = copy.deepcopy(players)
    later[201].update(contact=99, power=99, speed=99, fielding=99)          # Cal grew
    seasons = {201: 3, 202: 1, 203: 0, 204: 2}
    rev = draft.revisit(doc, YEAR + 3, later, set(), seasons)
    assert rev['year'] == YEAR + 3
    cal = rev['picks']['201']
    assert cal == {'grades': {'contact': 80, 'power': 80, 'speed': 80, 'fielding': 80}, 'seasons': 3,
                   'value': contracts._index(later[201]) + 6, 'gone': False}
    assert rev['picks']['203']['grades'] == draft.grades(players[203]) and rev['picks']['203']['seasons'] == 0
    assert rev['picks']['202']['value'] == contracts._index(players[202]) + 2
    assert sorted(rev['picks']) == ['201', '202', '203', '204']
    assert type(rev['picks']['201']['value']) is float


def test_revisit_a_pick_gone_from_the_pyr_or_retired_keeps_only_its_seasons():
    doc, players, rosters, names = built()
    later = {pid: p for pid, p in players.items() if pid != 202}            # Pat left the file
    rev = draft.revisit(doc, YEAR + 3, later, {203}, {201: 2, 202: 3, 203: 1, 204: 0})     # Sam retired
    assert rev['picks']['202'] == {'grades': {}, 'seasons': 3, 'value': 6.0, 'gone': True}
    assert rev['picks']['203'] == {'grades': {}, 'seasons': 1, 'value': 2.0, 'gone': True}
    assert rev['picks']['201']['gone'] is False and rev['picks']['204']['gone'] is False
    assert rev['picks']['204']['value'] == contracts._index(players[204])      # no seasons: just the index


def test_revisit_regrades_the_same_teams_on_the_sum_of_their_new_values():
    doc, players, rosters, names = built()
    rev = draft.revisit(doc, YEAR + 3, players, set(), {201: 0, 202: 0, 203: 0, 204: 9})
    assert {t['tid'] for t in rev['teams']} == {1, 2} and [list(t) for t in rev['teams']] == [
        ['tid', 'name', 'grade', 'value']] * 2
    by = {t['tid']: t for t in rev['teams']}
    assert by[1]['value'] == sum(contracts._index(players[p]) for p in (201, 202))      # the free agent is no team's
    assert by[2]['value'] == contracts._index(players[203]) and by[1]['name'] == 'Ash'
    assert draft.letters({1: by[1]['value'], 2: by[2]['value']}) == {1: by[1]['grade'], 2: by[2]['grade']}
    # a team whose picks all left is regraded on zero seasons' worth, not dropped
    gone = draft.revisit(doc, YEAR + 3, {}, set(), {})
    assert {t['tid'] for t in gone['teams']} == {1, 2} and all(t['value'] == 0.0 for t in gone['teams'])
    assert all(t['grade'] == 'C' for t in gone['teams'])
    assert doc['revisit'] is None                                                   # the draft itself is not changed
