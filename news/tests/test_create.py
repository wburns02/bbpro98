"""create.py on synthetic records: the rating and grade maps, validate(), donor(), build_record(), the PYR and PYF
bytes, open_by_anyone() on a fake proc tree, and add_player() on a synthetic association. No game files are read."""
import datetime
import os
import stat
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import create    # noqa: E402
import gamedata  # noqa: E402
import league    # noqa: E402 (work/ is on the path once gamedata is imported)
import scout     # noqa: E402

SEED = (0x6b, 0xe2)       # the cipher seed is per file: PYR bytes 0-1
ASSNS = {'TEST77', 'MLBPA96E'}
NOW = datetime.datetime(2026, 10, 9, 12, 0, 0)
PEAK, CUR, K_ATTR, STAMINA_BYTE = 0x46, 0x5d, 0x76, 0x96
ASN_NAME = '1977 Major Leagues'
SPEC_SS = {'assn': 'TEST77', 'first': 'Ned', 'last': 'Ray', 'pos': 'SS', 'bats': 'L', 'throws': 'R', 'age': 24,
           'grades': {'contact': 60, 'power': 50, 'speed': 40, 'arm': 30, 'fielding': 70}}
SPEC_P = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': 25,
          'grades': {'stamina': 60, 'control': 50, 'strikeout': 70, 'stuff': 60}}


def player(pid, first='Pat', last='Doe', pos=6, born=1972, bats=2, throws=2, cur=None, peak=None, raw=None):
    """One plain record. cur and peak map a rating index (0..22) to its byte; raw maps a file offset to its byte."""
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, datetime.date(born, 7, 1).toordinal() + 365)
    p[0x41], p[0x42], p[0x44] = bats, throws, pos
    for i, v in (cur or {}).items():
        p[CUR + i] = v
    for i, v in (peak or {}).items():
        p[PEAK + i] = v
    for off, v in (raw or {}).items():
        p[off] = v
    return bytes(p)


def pyr_bytes(records, seed=SEED):
    """A PYR file: a header (the seed in bytes 0-1), then each record enciphered with league's cipher."""
    t = league._forward(seed)
    return bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records)


def pyf_bytes(ids, stale=b''):
    """A PYF pool: 'PPD:', n_bytes, count, the ids, then any stale bytes the game leaves behind."""
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids) + stale


def form(**over):
    base = {'assn': 'TEST77', 'first': 'Pat', 'last': "O'Neil-Smith", 'pos': 'SS', 'bats': 'R', 'throws': 'R',
            'age': '24', 'contact': '60', 'power': '50', 'speed': '65', 'arm': '55', 'fielding': '70'}
    base.update(over)
    return base


def pitcher_form(**over):
    base = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': '25',
            'stamina': '60', 'control': '50', 'strikeout': '70', 'stuff': '60'}
    base.update(over)
    return base


@pytest.mark.parametrize('grade', create.GRADES)
def test_rating_round_trips_through_scout_grade(grade):
    assert 1 <= create.rating(grade) <= 99
    assert scout.grade(create.rating(grade)) == grade


def test_stuff_is_the_mean_of_nonzero_pitches():
    rec = bytearray(192)
    rec[CUR + 7], rec[CUR + 9], rec[CUR + 13] = 60, 40, 50
    assert create.stuff(rec) == 50.0
    assert create.stuff(bytes(192)) == 0.0


def test_validate_takes_a_good_hitter_and_ignores_pitching_grades():
    spec, errors = create.validate(form(stamina='99'), ASSNS)
    assert errors == {} and spec['assn'] == 'TEST77'
    assert spec == {'assn': 'TEST77', 'first': 'Pat', 'last': "O'Neil-Smith", 'pos': 'SS', 'bats': 'R', 'throws': 'R',
                    'age': 24, 'grades': {'contact': 60, 'power': 50, 'speed': 65, 'arm': 55, 'fielding': 70}}


def test_validate_takes_a_good_pitcher_and_ignores_hitting_grades():
    spec, errors = create.validate(pitcher_form(contact='52', fielding='85'), ASSNS)
    assert errors == {}
    assert spec['grades'] == {'stamina': 60, 'control': 50, 'strikeout': 70, 'stuff': 60}


@pytest.mark.parametrize('field, value', [
    ('assn', 'NOPE'), ('first', ''), ('last', 'A' * 17), ('first', 'Pat2'), ('first', '<script>'),
    ('last', '  '), ('pos', 'XX'), ('bats', 'X'), ('throws', 'S'), ('age', '16'), ('age', '46'), ('age', '2x'),
    ('contact', '52'), ('contact', '85'), ('speed', ''),
])
def test_validate_rejects_each_bad_field_without_echoing_it(field, value):
    spec, errors = create.validate(form(**{field: value}), ASSNS)
    assert spec is None and field in errors
    assert value.strip() == '' or value not in errors[field]


def test_validate_names_must_be_letters_and_fit_sixteen_characters():
    spec, errors = create.validate(form(first='  Jose  ', last='A' * 16), ASSNS)
    assert errors == {} and spec['first'] == 'Jose' and spec['last'] == 'A' * 16
    assert create.validate(form(last='A' * 17), ASSNS)[1].keys() == {'last'}
    assert create.validate(form(first='Renée'), ASSNS)[1] == {}


def test_validate_reports_a_pitcher_without_pitching_grades():
    spec, errors = create.validate(pitcher_form(stuff=''), ASSNS)
    assert spec is None and set(errors) == {'stuff'}


def test_donor_takes_the_nearest_player():
    far = player(101, cur={0: 20, 1: 90, 2: 90, 3: 90, 19: 20})
    near = player(105, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    assert create.donor([far, near], SPEC_SS, 1996) == near


def test_donor_prefers_the_spec_position():
    other_spot = player(103, pos=3, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    shortstop = player(101, pos=6, cur={0: 20, 1: 90, 2: 90, 3: 90, 19: 20})
    assert create.donor([other_spot, shortstop], SPEC_SS, 1996) == shortstop


def test_donor_falls_back_to_hitters_then_fails_for_a_pitcher():
    pitcher = player(100, pos=1, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    hitter = player(102, pos=3, cur={0: 10, 1: 10, 2: 10, 3: 10, 19: 10})
    assert create.donor([pitcher, hitter], SPEC_SS, 1996) == hitter
    with pytest.raises(ValueError):
        create.donor([hitter], SPEC_P, 1996)


def test_donor_ties_go_to_the_lower_id_and_age_counts():
    a = player(120, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    b = player(110, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    assert create.donor([a, b], SPEC_SS, 1996) == b
    young = player(111, born=1972, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    old = player(112, born=1950, cur={0: 66, 1: 50, 2: 33, 3: 16, 19: 82})
    assert create.donor([old, young], SPEC_SS, 1996) == young


def test_donor_skips_nameless_records_and_ids_below_a_hundred():
    exact = {0: 66, 1: 50, 2: 33, 3: 16, 19: 82}
    assert create.donor([player(50, cur=exact), player(102, first='', last='', cur=exact),
                         player(103, cur={0: 1})], SPEC_SS, 1996) == player(103, cur={0: 1})
    with pytest.raises(ValueError):
        create.donor([player(50, cur=exact)], SPEC_SS, 1996)


DONOR_HIT = player(105, 'Don', 'Or', pos=6, bats=2, throws=2,
                   cur={0: 40, 1: 60, 2: 70, 3: 30, 4: 9, 19: 80},
                   peak={0: 90, 1: 60, 2: 60, 3: 45, 19: 85})
DONOR_PIT = player(300, 'Dan', 'Pit', pos=1, born=1975, bats=1, throws=1,
                   cur={5: 60, 6: 50, 7: 70, 9: 50, 13: 30}, peak={5: 65, 6: 50, 7: 80, 9: 55},
                   raw={K_ATTR: 40})


def test_build_hitter_applies_grades_and_keeps_peak_gaps():
    rec = create.build_record(SPEC_SS, DONOR_HIT, 300, 1996)
    assert struct.unpack_from('<H', rec, 0)[0] == 300
    assert struct.unpack_from('<I', rec, 0x1a)[0] == datetime.date(1972, 7, 1).toordinal() + 365
    assert bytes(rec[30:47]) == b'Ned' + bytes(14) and bytes(rec[47:64]) == b'Ray' + bytes(14)
    assert (rec[64], rec[65], rec[66], rec[68]) == (1, 1, 2, 6)
    assert (rec[CUR], rec[PEAK]) == (66, 99)                  # peak 66 + gap 50, capped at 99
    assert (rec[CUR + 1], rec[PEAK + 1]) == (50, 50)          # gap 0
    assert (rec[CUR + 2], rec[PEAK + 2]) == (33, 33)          # donor peak below current: gap taken as 0
    assert (rec[CUR + 3], rec[PEAK + 3]) == (16, 31)          # gap 15
    assert (rec[CUR + 19], rec[PEAK + 19]) == (82, 87)        # fielding at SS (index 14 + 5), gap 5
    assert rec[CUR + 4] == 9                                  # copied from the donor
    assert rec[STAMINA_BYTE] == 0
    assert bytes(rec[0x8d:]) == bytes(192 - 0x8d)


def test_build_pitcher_shifts_the_donor_pitches_and_leaves_unthrown_ones_zero():
    rec = create.build_record(SPEC_P, DONOR_PIT, 301, 1996)
    assert (rec[64], rec[65], rec[66], rec[68]) == (1, 2, 1, 1)
    assert rec[CUR + 5] == 66 and rec[PEAK + 5] == 71         # stamina 66, donor gap 5
    assert rec[CUR + 6] == 50 and rec[PEAK + 6] == 50         # control 50, gap 0
    assert rec[K_ATTR] == 82                                  # strikeout 70 -> 82, not a peak-carrying byte
    shift = 66 - 50                                           # stuff 60 -> 66 against the donor's mean of 50
    assert (rec[CUR + 7], rec[PEAK + 7]) == (70 + shift, 70 + shift + 10)
    assert (rec[CUR + 9], rec[PEAK + 9]) == (50 + shift, 50 + shift + 5)
    assert (rec[CUR + 13], rec[PEAK + 13]) == (30 + shift, 30 + shift)
    assert all(rec[CUR + i] == 0 for i in (8, 10, 11, 12))    # pitches the donor does not throw
    assert rec[STAMINA_BYTE] == 51 + 66
    assert create.stuff(rec) == pytest.approx(66.0)


def test_build_pitcher_clamps_pitches_to_one_and_ninety_nine():
    donor = player(300, pos=1, cur={7: 90, 9: 30, 13: 20}, peak={7: 90, 9: 30, 13: 20})
    low = dict(SPEC_P, grades=dict(SPEC_P['grades'], stuff=20))
    high = dict(SPEC_P, grades=dict(SPEC_P['grades'], stuff=80))
    assert create.build_record(low, donor, 300, 1996)[CUR + 9] == 1
    assert create.build_record(low, donor, 300, 1996)[CUR + 13] == 1
    assert create.build_record(high, donor, 300, 1996)[CUR + 7] == 99
    assert create.build_record(high, donor, 300, 1996)[CUR + 13] == 72     # 20 + 52.3, rounded


def test_built_players_read_back_through_gamedata(tmp_path):
    hitter = create.build_record(SPEC_SS, DONOR_HIT, 300, 1996)
    pitcher = create.build_record(SPEC_P, DONOR_PIT, 301, 1996)
    path = tmp_path / 'x.PYR'
    path.write_bytes(pyr_bytes([hitter, pitcher]))
    got = gamedata.players(path)
    h = got[300]
    assert (h['name'], h['pos'], h['bats'], h['throws'], h['born']) == ('Ned Ray', 'SS', 'L', 'R', 1972)
    assert [scout.grade(h[k]) for k in ('contact', 'power', 'speed', 'fielding')] == [60, 50, 40, 70]
    p = got[301]
    assert (p['name'], p['pos'], p['bats'], p['throws'], p['born']) == ('Al Ko', 'P', 'R', 'L', 1971)
    assert [scout.grade(p[k]) for k in ('stamina', 'control', 'strikeout')] == [60, 50, 70]
    assert scout.grade(round(create.stuff(pitcher))) == 60


def test_encipher_round_trips_a_pyr_file_and_decipher_checks_size():
    d = pyr_bytes([player(100), player(101, 'Bo', 'Bee')])
    header, recs = create.decipher(d)
    assert header == d[:192] and [r[0] for r in recs] == [100, 101]
    assert create.encipher(header, recs) == d
    for n in (0, 100, 193):
        with pytest.raises(ValueError):
            create.decipher(bytes(n))


def test_pyf_add_keeps_stale_trailing_bytes():
    data = pyf_bytes([100, 101], stale=b'STALE')
    got = create.pyf_add(data, 102)
    assert got == b'PPD:' + struct.pack('<Ih', 8, 3) + struct.pack('<3H', 100, 101, 102) + b'STALE'
    assert create.pyf_ids(got) == [100, 101, 102]


def test_pyf_add_on_an_empty_pool_and_on_no_file():
    assert create.pyf_add(pyf_bytes([]), 103) == pyf_bytes([103])
    fresh = create.pyf_add(None, 100)
    assert fresh == pyf_bytes([100]) == create.pyf_add(b'', 100)
    assert create.pyf_ids(fresh) == [100]


def test_pyf_rejects_bad_files():
    for bad in (b'XXXX' + bytes(6), b'PPD:' + struct.pack('<Ih', 9, 1) + bytes(2), b'PPD:' + struct.pack('<Ih', 2, -1),
                b'PPD:' + struct.pack('<Ih', 4, 1) + bytes(1), b'PPD:', None):
        with pytest.raises(ValueError):
            create.pyf_ids(bad)
    with pytest.raises(ValueError):
        create.pyf_add(b'XXXX' + bytes(6), 100)
    with pytest.raises(ValueError):
        create.pyf_add(None, 70000)


def test_open_by_anyone_reads_fd_links_and_skips_the_rest(tmp_path):
    held = tmp_path / 'game' / 'X.PYR'
    held.parent.mkdir()
    held.write_bytes(b'')
    other = tmp_path / 'other.PYR'
    other.write_bytes(b'')
    proc = tmp_path / 'proc'
    (proc / '123' / 'fd').mkdir(parents=True)
    os.symlink(held, proc / '123' / 'fd' / '3')
    (proc / '124' / 'fd').mkdir(parents=True)
    os.symlink(tmp_path / 'gone', proc / '124' / 'fd' / '4')       # a broken link holds nothing
    (proc / 'self' / 'fd').mkdir(parents=True)
    os.symlink(other, proc / 'self' / 'fd' / '5')                  # not a pid directory
    (proc / '125').mkdir()                                         # no fd directory: skipped
    assert create.open_by_anyone([str(held), str(other), str(tmp_path / 'gone')], str(proc)) == [str(held)]
    assert create.open_by_anyone([str(held)], str(tmp_path / 'nope')) == []


@pytest.fixture
def game(tmp_path, monkeypatch):
    """A game directory with TEST77 (two players, a pool holding both) and a stock donor file."""
    monkeypatch.setattr(create.gamedata, 'association', lambda path: {'name': ASN_NAME, 'teams': {}, 'games': []})
    root = tmp_path / 'game'
    (root / 'Assn').mkdir(parents=True)
    (root / 'Stats').mkdir()
    (root / 'Assn' / 'TEST77.ASN').write_bytes(b'asn')
    (root / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes([player(100, pos=3), player(205, 'Bo', 'Bee', pos=1)]))
    (root / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes([100, 205], stale=b'STALE'))
    (root / 'Stats' / 'TEST77.DAT').write_bytes(b'dat')
    stock = tmp_path / 'stock'
    stock.mkdir()
    donor = stock / 'MLBPA96E.PYR'
    donor.write_bytes(pyr_bytes([DONOR_HIT, DONOR_PIT]))
    proc = tmp_path / 'proc'
    proc.mkdir()
    return root, donor, proc


def test_add_player_appends_the_record_and_pool_id_and_backs_up(game, tmp_path):
    root, donor, proc = game
    before = {f: (root / 'Assn' / f).read_bytes() for f in ('TEST77.PYR', 'TEST77.PYF')}
    backup = tmp_path / 'backup'
    pid, rec = create.add_player(str(root), SPEC_SS, str(donor), str(backup), NOW, str(proc))
    assert pid == 206
    header, recs = create.decipher((root / 'Assn' / 'TEST77.PYR').read_bytes())
    assert [r[0] | r[1] << 8 for r in recs] == [100, 205, 206] and recs[-1] == rec
    assert header == before['TEST77.PYR'][:192]
    assert create.pyf_ids((root / 'Assn' / 'TEST77.PYF').read_bytes()) == [100, 205, 206]
    assert (root / 'Assn' / 'TEST77.PYF').read_bytes().endswith(b'STALE')
    kept = backup / 'TEST77-20261009T120000-206'
    assert (kept / 'TEST77.PYR').read_bytes() == before['TEST77.PYR']
    assert (kept / 'TEST77.PYF').read_bytes() == before['TEST77.PYF']
    assert list(root.rglob('*create-tmp')) == []


def test_add_player_refuses_an_open_association_and_writes_nothing(game, tmp_path):
    root, donor, proc = game
    pyr = root / 'Assn' / 'TEST77.PYR'
    before = pyr.read_bytes(), (root / 'Assn' / 'TEST77.PYF').read_bytes()
    (proc / '99' / 'fd').mkdir(parents=True)
    os.symlink(pyr, proc / '99' / 'fd' / '3')
    backup = tmp_path / 'backup'
    with pytest.raises(create.AssociationOpen) as err:
        create.add_player(str(root), SPEC_SS, str(donor), str(backup), NOW, str(proc))
    assert [os.path.basename(p) for p in err.value.args[0]] == ['TEST77.PYR']
    assert (pyr.read_bytes(), (root / 'Assn' / 'TEST77.PYF').read_bytes()) == before
    assert not backup.exists()


def test_add_player_makes_a_missing_pool_file_and_skips_missing_stats(game, tmp_path):
    root, donor, proc = game
    (root / 'Assn' / 'TEST77.PYF').unlink()
    (root / 'Stats' / 'TEST77.DAT').unlink()
    pid, _ = create.add_player(str(root), SPEC_P, str(donor), str(tmp_path / 'backup'), NOW, str(proc))
    assert pid == 206
    assert create.pyf_ids((root / 'Assn' / 'TEST77.PYF').read_bytes()) == [206]


def test_add_player_on_an_empty_association_starts_at_one_hundred(game, tmp_path):
    root, donor, proc = game
    (root / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes([]))
    pid, _ = create.add_player(str(root), SPEC_SS, str(donor), str(tmp_path / 'backup'), NOW, str(proc))
    assert pid == 100


def test_add_player_keeps_the_pool_file_permission_bits(game, tmp_path):
    root, donor, proc = game
    pyf = root / 'Assn' / 'TEST77.PYF'
    os.chmod(pyf, 0o640)
    create.add_player(str(root), SPEC_SS, str(donor), str(tmp_path / 'backup'), NOW, str(proc))
    assert stat.S_IMODE(os.stat(pyf).st_mode) == 0o640


def test_add_player_needs_the_asn_and_the_pyr(game, tmp_path):
    root, donor, proc = game
    (root / 'Assn' / 'TEST77.PYR').unlink()
    with pytest.raises(ValueError):
        create.add_player(str(root), SPEC_SS, str(donor), str(tmp_path / 'backup'), NOW, str(proc))


def test_donor_year_comes_from_the_donor_asn(game, monkeypatch, tmp_path):
    root, donor, proc = game
    assert create._donor_year(str(donor)) == 1996          # no ASN beside it
    (donor.parent / 'MLBPA96E.ASN').write_bytes(b'asn')
    assert create._donor_year(str(donor)) == 1977          # the stub names 1977 for every ASN
    monkeypatch.setattr(create.gamedata, 'association', lambda path: 1 / 0)
    assert create._donor_year(str(donor)) == 1996          # an ASN that does not parse
