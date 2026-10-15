import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import recap  # noqa: E402
import watch  # noqa: E402


def game(month=4, day=1, slot=0, away=1, home=2, ar=5, hr=3, played=True):
    return {'month': month, 'day': day, 'slot': slot, 'away': away, 'home': home,
            'away_runs': ar, 'home_runs': hr, 'played': played}


def box(away_tid=1, home_tid=2, away_runs=5, home_runs=3):
    return {'away': {'tid': away_tid, 'runs': away_runs},
            'home': {'tid': home_tid, 'runs': home_runs}}


# recap.name_of

def test_name_of_known_pid():
    assert recap.name_of({101: 'Will Clark', 7: 'Joe'},
                         101) == 'Will Clark'


def test_name_of_unknown_pid():
    assert recap.name_of({}, 42) == 'Player 42'


# recap.in_order

def test_in_order_sorts_by_month_day_slot():
    games = [game(month=5, day=2, slot=1), game(month=4, day=30),
             game(month=5, day=1, slot=3), game(month=5, day=2, slot=0)]
    ordered = recap.in_order(games)
    assert [(g['month'], g['day'], g['slot']) for g in ordered] == \
        [(4, 30, 0), (5, 1, 3), (5, 2, 0), (5, 2, 1)]


def test_in_order_keeps_input_order_for_equal_keys():
    games = [game(day=1, slot=0, away=10, home=20),
             game(day=1, slot=0, away=30, home=40),
             game(day=1, slot=0, away=50, home=60)]
    assert [g['away'] for g in recap.in_order(games)] == [10, 30, 50]


def test_in_order_empty_list():
    assert recap.in_order([]) == []


# recap.outcome

def test_outcome_away_win():
    assert recap.outcome(game(ar=7, hr=2)) == (1, 2)


def test_outcome_home_win():
    assert recap.outcome(game(ar=2, hr=9)) == (2, 1)


def test_outcome_tie_is_none():
    assert recap.outcome(game(ar=4, hr=4)) is None


def test_outcome_unplayed_with_runs_is_none():
    assert recap.outcome(game(ar=6, hr=1, played=False)) is None


# recap.tally

def test_tally_sums_wins_losses_per_team():
    games = [game(ar=5, hr=3),                    # 1 beats 2
             game(day=2, away=2, home=3, ar=1, hr=8),  # 3 beats 2
             game(day=3, away=3, home=1, ar=0, hr=4)]  # 1 beats 3
    assert recap.tally(games) == {1: [2, 0], 2: [0, 2], 3: [1, 1]}


def test_tally_ignores_ties_and_unplayed():
    games = [game(ar=3, hr=3),
             game(day=2, ar=9, hr=0, played=False),
             game(day=3, ar=9, hr=0, played=True)]
    assert recap.tally(games) == {1: [1, 0], 2: [0, 1]}


def test_tally_empty_list():
    assert recap.tally([]) == {}


# gamedata.match_game

def test_match_game_same_teams_same_score():
    assoc = {'games': [game(ar=5, hr=3), game(day=2, away=2, home=1, ar=1, hr=1)]}
    assert gamedata.match_game(assoc, box()) == [assoc['games'][0]]


def test_match_game_score_must_match():
    assoc = {'games': [game(ar=5, hr=3)]}
    assert gamedata.match_game(assoc, box(away_runs=4, home_runs=3)) == []


def test_match_game_reversed_home_away_no_match():
    assoc = {'games': [game(away=2, home=1, ar=3, hr=5)]}
    assert gamedata.match_game(assoc, box()) == []


def test_match_game_unplayed_with_score_no_match():
    assoc = {'games': [game(ar=5, hr=3, played=False)]}
    assert gamedata.match_game(assoc, box()) == []


def test_match_game_duplicate_returns_both_in_schedule_order():
    assoc = {'games': [game(day=3, ar=5, hr=3), game(day=1, ar=5, hr=3)]}
    assert gamedata.match_game(assoc, box()) == [assoc['games'][0], assoc['games'][1]]


# watch.write_json / watch.read_json

def test_write_then_read_round_trip(tmp_path):
    path = str(tmp_path / 'out' / 'recaps' / 'g1.json')
    obj = {'title': 'Cubs 5, Giants 3', 'g': 12, 'nested': {'a': [1, 2]}}
    watch.write_json(path, obj)
    assert watch.read_json(path) == obj


def test_write_json_creates_missing_parent_folders_and_leaves_no_tmp(tmp_path):
    path = str(tmp_path / 'a' / 'b' / 'x.json')
    watch.write_json(path, {'k': 'v'})
    assert os.path.isfile(path)
    assert not os.path.exists(path + '.tmp')


def test_read_json_missing_file_is_none(tmp_path):
    assert watch.read_json(str(tmp_path / 'nope.json')) is None


def test_read_json_invalid_json_is_none(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{"title": ', encoding='utf-8')
    assert watch.read_json(str(path)) is None


def test_read_json_json_list_is_none(tmp_path):
    path = tmp_path / 'list.json'
    path.write_text(json.dumps([1, 2, 3]), encoding='utf-8')
    assert watch.read_json(str(path)) is None


# watch.story_count

def test_story_count_counts_only_json_files(tmp_path):
    recaps = tmp_path / 'recaps'
    recaps.mkdir()
    (recaps / 'a.json').write_text('{}', encoding='utf-8')
    (recaps / 'b.json').write_text('{}', encoding='utf-8')
    (recaps / 'c.txt').write_text('x', encoding='utf-8')
    (recaps / 'd.json.bak').write_text('x', encoding='utf-8')
    assert watch.story_count(str(tmp_path)) == 2


def test_story_count_missing_recaps_folder_is_zero(tmp_path):
    assert watch.story_count(str(tmp_path)) == 0


# watch.now_iso

def test_now_iso_format_has_no_microseconds():
    stamp = watch.now_iso()
    assert re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d', stamp) is not None
