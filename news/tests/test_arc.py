"""arc.py: the career-arc trait against fixed vectors and against src-latest/mods/arc.h compiled with the host cc, the
distribution that keeps league aging flat, the scouting hint at its edges, and watch.py passing birth serials to the
team roster. No game files: the PYR is built in tmp_path."""
import datetime
import json
import os
import random
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import arc       # noqa: E402
import gamedata  # noqa: E402
import watch     # noqa: E402
from tests.test_scout import BORN_1970, pyr_record, write_pyr   # noqa: E402
from tests.test_watch import SCOUT_PLAYERS, TEAMS, game      # noqa: E402

ARC_H = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src-latest', 'mods', 'arc.h')


def serial(y, m, d):
    return datetime.date(y, m, d).toordinal() + 365


# (pid, birth) -> (shift, size) at the defaults (years 3, spread 30). Computed apart from arc.py, with struct.pack and a
# plain loop over FNV-1a 32 (checked against the published vectors for b'a' and b'foobar').
VECTORS = [
    ((100, 0), (2, 80)),
    ((100, 1), (3, 74)),
    ((101, 718195), (2, 101)),
    ((201, 718195), (-3, 89)),
    ((205, 721354), (-3, 121)),
    ((4242, 719529), (2, 78)),
    ((12345, 725006), (-2, 102)),
    ((32767, 4294967295), (-2, 97)),
    ((32767, 0), (0, 113)),
    ((777, 713138), (3, 92)),
    ((300, 719529), (1, 130)),
    ((1000, 726894), (3, 104)),
]
# (pid, birth, years, spread) -> (shift, size) off the defaults
VECTORS_OFF_DEFAULT = [
    ((100, 0, 6, 60), (0, 57)),
    ((101, 718195, 6, 60), (-4, 79)),
    ((205, 721354, 0, 30), (0, 121)),
    ((205, 721354, 3, 0), (-3, 100)),
    ((4242, 719529, 1, 10), (1, 103)),
    ((32767, 0, 6, 0), (1, 100)),
]


@pytest.mark.parametrize('pair, want', VECTORS)
def test_trait_fixed_vectors(pair, want):
    assert arc.trait(*pair) == want


@pytest.mark.parametrize('args, want', VECTORS_OFF_DEFAULT)
def test_trait_fixed_vectors_with_years_and_spread(args, want):
    assert arc.trait(*args) == want


def test_years_zero_gives_no_shift_and_spread_zero_gives_size_100():
    for pid in range(100, 600):
        birth = serial(1960, 1, 1) + pid * 13
        assert arc.trait(pid, birth, years=0)[0] == 0
        assert arc.trait(pid, birth, spread=0)[1] == 100
    assert arc.trait(100, 0, years=-2, spread=-5) == (0, 100)       # below 0 counts as 0, as in arc.h


def test_trait_ranges_follow_years_and_spread():
    rng = random.Random(7)
    for _ in range(2000):
        years, spread = rng.randint(0, 6), rng.randint(0, 60)
        shift, size = arc.trait(rng.randint(100, 32767), rng.getrandbits(32), years, spread)
        assert -years <= shift <= years and 100 - spread <= size <= 100 + spread


def test_distribution_keeps_league_aging_flat():
    """5000 players, birth dates spread over 1950-1979: the mean shift is 0 and the mean size is 100, so the arcs move
    careers around the league mean without moving it."""
    base, span = serial(1950, 1, 1), 30 * 365
    traits = [arc.trait(pid, base + (pid * 7919) % span) for pid in range(100, 5100)]
    shifts, sizes = [t[0] for t in traits], [t[1] for t in traits]
    assert abs(sum(shifts) / len(shifts)) < 0.1
    assert set(shifts) == set(range(-3, 4))
    assert abs(sum(sizes) / len(sizes) - 100) < 1.0
    assert min(sizes) >= 70 and max(sizes) <= 130


# C cross-check

C_HARNESS = r'''
#include <stdio.h>
#include "arc.h"
int main(void) {
    unsigned int pid, birth;
    int years, spread, size, shift;
    while (scanf("%u %u %d %d", &pid, &birth, &years, &spread) == 4) {
        shift = arc_trait((int)pid, birth, years, spread, &size);
        printf("%d %d\n", shift, size);
    }
    return 0;
}
'''


def host_cc():
    return shutil.which('cc') or shutil.which('gcc')


def test_arc_h_includes_nothing_but_stdint():
    with open(ARC_H) as fh:
        includes = [line.strip() for line in fh if line.lstrip().startswith('#include')]
    assert includes == ['#include <stdint.h>']


@pytest.mark.skipif(host_cc() is None, reason='no host C compiler')
def test_arc_h_matches_the_python_trait_on_1000_pairs(tmp_path):
    src, exe = tmp_path / 'harness.c', tmp_path / 'harness'
    src.write_text(C_HARNESS)
    built = subprocess.run([host_cc(), '-std=c99', '-Wall', '-Werror', '-I', os.path.dirname(ARC_H), '-o', str(exe),
                            str(src)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    rng = random.Random(1998)
    cases = [(p[0], p[1], 3, 30) for p, _ in VECTORS]
    cases += [(rng.randint(100, 32767), rng.getrandbits(32), rng.randint(0, 6), rng.randint(0, 60))
              for _ in range(1000 - len(cases) - 200)]
    cases += [(rng.randint(100, 32767), rng.getrandbits(32), 3, 30) for _ in range(200)]
    assert len(cases) == 1000
    run = subprocess.run([str(exe)], input=''.join('%d %d %d %d\n' % c for c in cases), capture_output=True,
                         text=True, timeout=60)
    got = [tuple(map(int, line.split())) for line in run.stdout.splitlines()]
    assert got == [arc.trait(*c) for c in cases]


# hint

@pytest.mark.parametrize('age, text', [(27, None), (28, 'normal aging'), (29, 'normal aging'), (None, None),
                                       (0, None), (40, 'normal aging')])
def test_hint_reads_only_from_age_28(age, text):
    assert arc.hint(0, 100, age) == text


@pytest.mark.parametrize('shift, text', [(3, 'ages well'), (2, 'ages well'), (1, 'normal aging'), (0, 'normal aging'),
                                         (-1, 'normal aging'), (-2, 'early decline risk'),
                                         (-3, 'early decline risk')])
def test_hint_shift_edges(shift, text):
    assert arc.hint(shift, 100, 30) == text


@pytest.mark.parametrize('size, tail', [(130, ', steep decline'), (115, ', steep decline'), (114, ''), (100, ''),
                                        (86, ''), (85, ', gentle decline'), (70, ', gentle decline')])
def test_hint_size_edges(size, tail):
    assert arc.hint(0, size, 30) == 'normal aging' + tail


def test_hint_joins_the_shift_words_and_the_size_words():
    assert arc.hint(2, 115, 28) == 'ages well, steep decline'
    assert arc.hint(-2, 85, 35) == 'early decline risk, gentle decline'
    assert arc.hint(3, 70, 28) == 'ages well, gentle decline'


def test_player_hint_is_the_hint_of_the_trait_at_the_whole_year_age():
    birth = serial(1970, 12, 31)
    want = arc.hint(*arc.trait(101, birth), 28)
    assert want is not None
    assert arc.player_hint(101, birth, 1998) == want            # 1998 - 1970, whatever the month
    assert arc.player_hint(101, serial(1970, 1, 1), 1998) == arc.hint(*arc.trait(101, serial(1970, 1, 1)), 28)
    assert arc.player_hint(101, birth, 1997) is None            # 27: scouts cannot read it yet
    assert arc.player_hint(101, serial(1960, 6, 1), 1990) == arc.hint(*arc.trait(101, serial(1960, 6, 1)), 30)


def test_player_hint_names_the_arc_of_a_known_player():
    assert arc.player_hint(100, serial(1960, 1, 1), 1998) == arc.hint(*arc.trait(100, serial(1960, 1, 1)), 38)
    assert arc.player_hint(101, 718195, 1998) == 'ages well'                    # (2, 101), born 1966
    assert arc.player_hint(205, 721354, 2003) == 'early decline risk, steep decline'     # (-3, 121), born 1975, 28
    assert arc.player_hint(300, 719529, 1998) == 'normal aging, steep decline'          # (1, 130), born 1970, 28
    assert arc.player_hint(201, 718195, 1998) == 'early decline risk'                   # (-3, 89)
    assert arc.player_hint(4242, 719529, 1998) == 'ages well, gentle decline'           # (2, 78)


@pytest.mark.parametrize('birth', [None, 0, -5, 365, 4294967295, 10 ** 12, 'x', 1.5, True])
def test_player_hint_is_none_for_a_birth_that_is_not_a_serial(birth):
    assert arc.player_hint(101, birth, 1998) is None


def test_player_hint_is_none_without_an_integer_year():
    assert arc.player_hint(101, serial(1960, 1, 1), None) is None


# watch.py threads the birth serials in

@pytest.fixture
def league(tmp_path, monkeypatch):
    """(game dir, data dir) for a Watcher over a two-team association whose players() is SCOUT_PLAYERS."""
    gd = tmp_path / 'game'
    (gd / 'Assn').mkdir(parents=True)
    (gd / 'Stats').mkdir()
    (gd / 'Assn' / '30L1998.ASN').write_bytes(b'asn')
    monkeypatch.setattr(gamedata, 'association', lambda path: {'name': '1998 Test', 'teams': TEAMS,
                                                              'games': [game(1, 0, 1, 2, 3, 1, played=False)]})
    monkeypatch.setattr(gamedata, 'names', lambda path: {100: 'Al Winner', 200: 'Bo Loser'})
    monkeypatch.setattr(gamedata, 'season_lines', lambda path, scope=1: {'bat': {}, 'pit': {}})
    monkeypatch.setattr(gamedata, 'players', lambda path: SCOUT_PLAYERS)
    return gd, tmp_path / 'data'


def test_scouting_hands_the_pyr_birth_serials_to_the_roster(league):
    gd, data = league
    write_pyr(gd / 'Assn' / '30L1998.PYR', [pyr_record(100, 'Al', 'Winner', serial=BORN_1970),
                                            pyr_record(200, 'Bo', 'Loser', serial=serial(1975, 3, 3))])
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    ash = json.loads((data / '30L1998' / 'scout' / '1.json').read_text())
    birch = json.loads((data / '30L1998' / 'scout' / '2.json').read_text())
    assert ash['roster']['hitters'][0]['arc'] == arc.player_hint(100, BORN_1970, 1998)
    assert ash['roster']['hitters'][0]['arc'] is not None       # 1998 - 1970 = 28
    assert birch['roster']['pitchers'][0]['arc'] is None        # born 1975: 23, too young to read
    assert 'arc' not in ash['facts']['hitters'][0]              # the prompt facts are unchanged


def test_scouting_survives_a_pyr_it_cannot_read_births_from(league):
    gd, data = league
    (gd / 'Assn' / '30L1998.PYR').write_bytes(b'pyr')           # not a PYR: focus.births raises ValueError
    watch.Watcher(str(gd), str(data), None, None, log=lambda s: None).scan()
    ash = json.loads((data / '30L1998' / 'scout' / '1.json').read_text())
    assert ash['roster']['hitters'][0]['age'] == 28 and ash['roster']['hitters'][0]['arc'] is None
