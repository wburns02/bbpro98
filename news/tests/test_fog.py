"""fog.py: the noise a scout adds to a rating, its size by service seasons, the rating and view built on it."""
import copy
import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fog  # noqa: E402


def draw(assn, viewer, pid, key, year):
    """The contract's noise before scaling, written out again here."""
    d = hashlib.sha256(('%s|%s|%s|%s|%s' % (assn, viewer, pid, key, year)).encode()).digest()
    return max(-2.5, min(2.5, (d[0] + d[1] + d[2] - 382.5) / 127.9))


@pytest.mark.parametrize('seasons, want', [
    (None, 8), (-3, 8), (0, 8), (1, 8), (2, 6), (3, 6), (4, 4), (6, 4), (7, 2), (8, 2), (20, 2),
])
def test_sd_steps_at_one_two_three_four_six_and_seven_seasons(seasons, want):
    assert fog.sd(seasons) == want


@pytest.mark.parametrize('seasons, want', [(None, 4), (1, 4), (2, 3), (3, 3), (4, 2), (6, 2), (7, 1), (30, 1)])
def test_own_scouts_halve_it_with_a_floor_of_one(seasons, want):
    assert fog.sd(seasons, own=True) == want


def test_noise_is_the_scaled_hash_draw_and_the_same_every_time():
    for pid in (100, 101, 777):
        for seasons in (None, 3, 9):
            want = round(draw('30L1998', 0, pid, 'power', 1998) * fog.sd(seasons))
            assert fog.noise('30L1998', 0, pid, 'power', 1998, seasons) == want
            assert fog.noise('30L1998', 0, pid, 'power', 1998, seasons) == want
    # pinned: the answer must not drift between runs, machines or versions
    assert fog.noise('30L1998', 0, 200, 'control', 1998, None) == -9
    assert fog.noise('30L1998', 0, 200, 'control', 1998, 10) == -2
    assert fog.noise('30L1998', 0, 100, 'power', 1998, None) == 8


def test_noise_is_bounded_by_two_and_a_half_sd_and_uses_the_whole_range():
    for seasons, bound in ((0, 20), (2, 15), (5, 10), (9, 5)):
        got = [fog.noise('A', 0, pid, 'contact', 1998, seasons) for pid in range(2000)]
        assert max(got) <= bound and min(got) >= -bound
        assert max(got) >= bound - 2 and min(got) <= 2 - bound      # the tails are reached (sd 2.5 clamps)
        assert sum(abs(v) for v in got) > 0
    own = [fog.noise('A', 0, pid, 'contact', 1998, 0, own=True) for pid in range(2000)]
    assert max(own) <= 10 and min(own) >= -10 and max(own) >= 8


def test_noise_changes_with_each_argument():
    base = [fog.noise('A', 0, pid, 'speed', 1998, 0) for pid in range(200)]
    for other in (
            [fog.noise('B', 0, pid, 'speed', 1998, 0) for pid in range(200)],
            [fog.noise('A', 5, pid, 'speed', 1998, 0) for pid in range(200)],
            [fog.noise('A', 0, pid, 'power', 1998, 0) for pid in range(200)],
            [fog.noise('A', 0, pid, 'speed', 1999, 0) for pid in range(200)],
            [fog.noise('A', 0, pid + 1, 'speed', 1998, 0) for pid in range(200)]):
        assert other != base
    assert len(set(base)) > 10        # not one number for the whole league


def test_rating_adds_the_noise_and_clamps_to_one_to_ninety_nine():
    for pid in range(50):
        n = fog.noise('A', 0, pid, 'contact', 1998, 0)
        assert fog.rating(50, 'A', 0, pid, 'contact', 1998, 0) == 50 + n
        assert fog.rating(1, 'A', 0, pid, 'contact', 1998, 0) == max(1, 1 + n)
        assert 1 <= fog.rating(1, 'A', 0, pid, 'contact', 1998, 0) <= 99
        assert 1 <= fog.rating(99, 'A', 0, pid, 'contact', 1998, 0) <= 99
    ups = [fog.rating(99, 'A', 0, pid, 'contact', 1998, 0) for pid in range(200)]
    downs = [fog.rating(1, 'A', 0, pid, 'contact', 1998, 0) for pid in range(200)]
    assert max(ups) == 99 and 1 in downs                # both ends are hit and held


def test_a_rating_of_zero_is_not_rated_and_stays_zero():
    assert all(fog.rating(0, 'A', 0, pid, 'strikeout', 1998, 0) == 0 for pid in range(200))
    assert fog.rating(None, 'A', 0, 1, 'fielding', 1998, 0) is None


def test_view_fogs_every_graded_rating_and_nothing_else():
    p = {'name': 'Al', 'pos': 'RF', 'bats': 'L', 'throws': 'R', 'born': 1970, 'contact': 90, 'power': 60,
         'speed': 70, 'stamina': 0, 'control': 0, 'strikeout': 0, 'fielding': 50, 'seasons': 1}
    before = copy.deepcopy(p)
    v = fog.view(p, 'A', 0, 1998, pid=100)
    assert p == before and v is not p                  # a copy: the true entry is untouched
    for key in ('contact', 'power', 'speed', 'fielding'):
        assert v[key] == fog.rating(p[key], 'A', 0, 100, key, 1998, 1)
    assert [v[k] for k in ('stamina', 'control', 'strikeout')] == [0, 0, 0]     # not rated for a hitter
    assert {k: v[k] for k in ('name', 'pos', 'bats', 'throws', 'born', 'seasons')} == {
        k: p[k] for k in ('name', 'pos', 'bats', 'throws', 'born', 'seasons')}
    assert any(v[k] != p[k] for k in ('contact', 'power', 'speed', 'fielding'))


def test_view_keeps_a_missing_fielding_and_skips_keys_the_entry_lacks():
    assert fog.view({'pos': 'P', 'control': 50, 'fielding': None}, 'A', 0, 1998, pid=1)['fielding'] is None
    got = fog.view({'name': 'X', 'control': 50}, 'A', 0, 1998, pid=1)
    assert sorted(got) == ['control', 'name']


def test_view_needs_a_player_identity_and_takes_it_from_pid_then_the_entry():
    p = {'name': 'Al', 'pos': 'SS', 'contact': 50, 'seasons': 0}
    assert fog.view(p, 'A', 0, 1998, pid=7)['contact'] == fog.rating(50, 'A', 0, 7, 'contact', 1998, 0)
    assert fog.view(dict(p, pid=9), 'A', 0, 1998)['contact'] == fog.rating(50, 'A', 0, 9, 'contact', 1998, 0)
    assert fog.view(p, 'A', 0, 1998)['contact'] == fog.rating(50, 'A', 0, 'Al', 'contact', 1998, 0)
    # two players of the same name and seasons but different pids are not read with one shared error
    reads = {fog.view(p, 'A', 0, 1998, pid=pid)['contact'] for pid in range(300, 340)}
    assert len(reads) > 5


def test_veterans_are_read_more_closely_than_rookies_and_own_scouts_more_closely_still():
    def spread(seasons, own=False):
        vals = [fog.view({'pos': 'SS', 'contact': 50, 'seasons': seasons}, 'A', 0, 1998, own, pid)['contact'] - 50
                for pid in range(1000)]
        return max(abs(v) for v in vals)
    assert spread(0) > spread(3) > spread(5) > spread(9)
    assert spread(0, own=True) < spread(0) and spread(9, own=True) < spread(9)
    assert spread(None) == spread(0)


def test_the_public_view_is_not_another_viewers():
    p = {'pos': 'SS', 'contact': 50, 'seasons': 0}
    assert ([fog.view(p, 'A', 0, 1998, pid=i)['contact'] for i in range(100)]
            != [fog.view(p, 'A', 3, 1998, pid=i)['contact'] for i in range(100)])
