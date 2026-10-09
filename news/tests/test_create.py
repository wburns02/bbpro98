"""create.py on synthetic records: the rating and grade maps, the archetypes and their budgets, validate_who() and
validate_ratings(), donor(), build_record(), scouting_report(), comparable(), the PYR and PYF bytes, open_by_anyone() on a
fake proc tree, and add_player() on a synthetic association. No game files are read."""
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
R = create.rating
GAP_MSG = 'At %d a ceiling can be at most %d above Now.'
SS_NOW = {'contact': 60, 'power': 50, 'speed': 40, 'arm': 30, 'fielding': 70}
SS_CEIL = {'contact': 65, 'power': 50, 'speed': 45, 'arm': 35, 'fielding': 70}
SPEC_SS = {'assn': 'TEST77', 'first': 'Ned', 'last': 'Ray', 'pos': 'SS', 'bats': 'L', 'throws': 'R', 'age': 24,
           'archetype': 'glove', 'mode': 'sandbox', 'now': SS_NOW, 'ceiling': SS_CEIL, 'pitches': {}}
SPEC_P = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': 25,
          'archetype': 'ace', 'mode': 'sandbox',
          'now': {'stamina': 60, 'control': 50, 'hold': 50, 'strikeout': 70},
          'ceiling': {'stamina': 65, 'control': 50, 'hold': 50},
          'pitches': {'FB': (70, 75), 'SL': (50, 55)}}


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


HIT_FORM = {'assn': 'TEST77', 'first': 'Pat', 'last': "O'Neil-Smith", 'pos': 'SS', 'bats': 'R', 'throws': 'R',
            'age': '24', 'archetype': 'regular', 'mode': 'realistic',
            'now_contact': '60', 'ceil_contact': '60', 'now_power': '50', 'ceil_power': '50',
            'now_speed': '65', 'ceil_speed': '65', 'now_arm': '55', 'ceil_arm': '55',
            'now_fielding': '70', 'ceil_fielding': '70'}


def form(**over):
    """A valid hitter's form: realistic, age 24, every Ceiling equal to its Now (50 of 100 budget points spent)."""
    return dict(HIT_FORM, **over)


def pitcher_form(pitches=(('FB', '70', '75'), ('SL', '50', '55')), **over):
    """A valid pitcher's form: realistic, age 25, with the given (slot, now, ceiling) pitches and the rest 'none'."""
    base = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': '25',
            'archetype': 'ace', 'mode': 'realistic',
            'now_stamina': '60', 'ceil_stamina': '60', 'now_control': '50', 'ceil_control': '50',
            'now_hold': '50', 'ceil_hold': '50', 'now_strikeout': '70'}
    for slot in create.PITCH_SLOTS:
        base['p_%s_now' % slot] = 'none'
        base['p_%s_ceil' % slot] = 'none'
    for slot, now, ceil in pitches:
        base['p_%s_now' % slot] = now
        base['p_%s_ceil' % slot] = ceil
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


@pytest.mark.parametrize('key', list(create.ARCHETYPES))
def test_every_archetype_is_one_role_with_its_ratings(key):
    arch = create.ARCHETYPES[key]
    assert arch['role'] in ('hit', 'pit') and arch['blurb'].endswith('.')
    assert set(arch['now']) == set(create.ROLE_RATINGS[arch['role']])
    assert set(arch['ceiling']) == set(create.ROLE_RATINGS[arch['role']]) - {'strikeout'}
    assert all(arch['ceiling'][r] >= arch['now'][r] for r in arch['ceiling'])
    if arch['role'] == 'hit':
        assert arch['pitches'] == {}
    else:
        assert set(arch['pitches']) <= set(create.PITCH_SLOTS) and 2 <= len(arch['pitches']) <= 5


def test_archetype_fields_prefill_every_value_as_text():
    ace = create.archetype_fields('ace')
    assert ace['now_strikeout'] == '70' and 'ceil_strikeout' not in ace
    assert (ace['now_stamina'], ace['ceil_stamina']) == ('65', '70')
    assert (ace['p_FB_now'], ace['p_FB_ceil']) == ('75', '80')
    assert (ace['p_CB_now'], ace['p_CB_ceil']) == ('none', 'none')
    assert all(isinstance(v, str) for v in ace.values())
    hit = create.archetype_fields('contact')
    assert not [k for k in hit if k.startswith('p_')] and hit['ceil_fielding'] == '60'
    with pytest.raises(KeyError):
        create.archetype_fields('nope')


@pytest.mark.parametrize('key', list(create.ARCHETYPES))
def test_every_archetype_passes_validation_at_22_in_realistic_mode(key):
    role = create.ARCHETYPES[key]['role']
    who = dict(form(), archetype=key, pos='P' if role == 'pit' else 'SS', age='22', **create.archetype_fields(key))
    spec, errors = create.validate(who, ASSNS)
    assert errors == {} and spec['archetype'] == key


def test_prospect_at_27_is_over_the_gap_on_every_ceiling_and_passes_in_sandbox():
    fields = create.archetype_fields('prospect')
    spec, errors = create.validate(form(archetype='prospect', age='27', **fields), ASSNS)
    assert spec is None
    assert {k: v for k, v in errors.items() if k.startswith('ceil_')} == {
        'ceil_' + r: GAP_MSG % (27, 5) for r in create.HIT_RATINGS}
    assert create.validate(form(archetype='prospect', age='27', mode='sandbox', **fields), ASSNS)[1] == {}


@pytest.mark.parametrize('age, limit', [(17, 25), (22, 25), (23, 15), (26, 15), (27, 5), (30, 5), (31, 0), (45, 0)])
def test_max_gap_falls_with_age(age, limit):
    assert create.max_gap(age) == limit


def test_budget_counts_points_above_fifty():
    assert create.budget(SPEC_SS) == {'now': 30, 'ceiling': 35, 'now_max': 50, 'ceiling_max': 100}
    assert create.budget(SPEC_P) == {'now': 50, 'ceiling': 65, 'now_max': 80, 'ceiling_max': 110}


@pytest.mark.parametrize('grade, word', [(80, 'elite'), (79, 'plus-plus'), (70, 'plus-plus'), (65, 'plus'),
                                         (55, 'above average'), (50, 'average'), (45, 'fringe'),
                                         (40, 'below average'), (35, 'well below average'), (25, 'poor'),
                                         (20, 'poor')])
def test_grade_word_names_each_floor(grade, word):
    assert create.grade_word(grade) == word


def test_validate_who_takes_the_first_step_and_types_the_age():
    who, errors = create.validate_who(form(), ASSNS)
    assert errors == {}
    assert who == {'assn': 'TEST77', 'first': 'Pat', 'last': "O'Neil-Smith", 'pos': 'SS', 'bats': 'R', 'throws': 'R',
                   'age': 24, 'archetype': 'regular', 'mode': 'realistic'}


def test_validate_who_refuses_an_archetype_of_the_other_role():
    who, errors = create.validate_who(form(pos='P', archetype='contact'), ASSNS)
    assert who is None and errors == {'archetype': 'Pick an archetype for this position.'}
    assert create.validate_who(form(archetype='nope'), ASSNS)[1] == {
        'archetype': 'Pick an archetype for this position.'}


def test_validate_who_skips_the_archetype_when_the_position_is_bad():
    who, errors = create.validate_who(form(pos='XX', archetype='contact'), ASSNS)
    assert who is None and set(errors) == {'pos'}


def test_validate_who_needs_a_known_mode():
    assert create.validate_who(form(mode='turbo'), ASSNS)[1] == {'mode': 'Pick realistic or sandbox.'}


@pytest.mark.parametrize('field, value', [
    ('assn', 'NOPE'), ('first', ''), ('last', 'A' * 17), ('first', 'Pat2'), ('first', '<script>'),
    ('last', '  '), ('pos', 'XX'), ('bats', 'X'), ('throws', 'S'), ('age', '16'), ('age', '46'), ('age', '2x'),
])
def test_validate_who_rejects_each_bad_field_without_echoing_it(field, value):
    who, errors = create.validate_who(form(**{field: value}), ASSNS)
    assert who is None and field in errors
    assert value.strip() == '' or value not in errors[field]


def test_validate_who_names_must_be_letters_and_fit_sixteen_characters():
    who, errors = create.validate_who(form(first='  Jose  ', last='A' * 16), ASSNS)
    assert errors == {} and who['first'] == 'Jose' and who['last'] == 'A' * 16
    assert create.validate_who(form(last='A' * 17), ASSNS)[1].keys() == {'last'}
    assert create.validate_who(form(first='Renée'), ASSNS)[1] == {}


def test_validate_takes_a_good_hitter_and_ignores_pitching_grades():
    spec, errors = create.validate(form(now_stamina='99', p_FB_now='none'), ASSNS)
    assert errors == {} and spec['assn'] == 'TEST77' and spec['archetype'] == 'regular'
    assert spec['now'] == {'contact': 60, 'power': 50, 'speed': 65, 'arm': 55, 'fielding': 70}
    assert spec['ceiling'] == spec['now'] and spec['pitches'] == {}


def test_validate_takes_a_good_pitcher_and_ignores_hitting_grades():
    spec, errors = create.validate(pitcher_form(now_contact='52', ceil_fielding='85'), ASSNS)
    assert errors == {}
    assert spec['now'] == {'stamina': 60, 'control': 50, 'hold': 50, 'strikeout': 70}
    assert spec['ceiling'] == {'stamina': 60, 'control': 50, 'hold': 50}
    assert spec['pitches'] == {'FB': (70, 75), 'SL': (50, 55)}


@pytest.mark.parametrize('field, value', [('now_contact', '52'), ('ceil_contact', '85'), ('now_arm', ''),
                                          ('ceil_fielding', 'x')])
def test_each_bad_grade_is_named_without_echo(field, value):
    spec, errors = create.validate(form(**{field: value}), ASSNS)
    assert spec is None and errors[field] == create.GRADE_MSG
    assert value.strip() == '' or value not in errors[field]


def test_strikeout_has_a_now_grade_and_no_ceiling():
    assert create.validate(pitcher_form(now_strikeout='1'), ASSNS)[1] == {'now_strikeout': create.GRADE_MSG}
    spec, errors = create.validate(pitcher_form(ceil_strikeout='80'), ASSNS)
    assert errors == {} and 'strikeout' not in spec['ceiling']


def test_a_ceiling_below_its_now_is_named():
    assert create.validate(form(now_contact='60', ceil_contact='55'), ASSNS)[1] == {
        'ceil_contact': 'Ceiling must be at least Now.'}
    assert create.validate(pitcher_form(ceil_control='45'), ASSNS)[1] == {'ceil_control': 'Ceiling must be at least Now.'}


def test_a_pitch_needs_both_grades_or_neither():
    rest = (('SL', '50', '55'), ('CU', '50', '55'))          # two more pitches, so the count is not the problem
    assert create.validate(pitcher_form(pitches=(('FB', '70', 'none'),) + rest), ASSNS)[1] == {
        'p_FB': 'Give each pitch both grades, or neither.'}
    assert create.validate(pitcher_form(pitches=(('FB', 'none', '75'),) + rest), ASSNS)[1] == {
        'p_FB': 'Give each pitch both grades, or neither.'}


def test_a_pitch_grade_must_read_as_one_and_its_ceiling_cannot_be_under_its_now():
    rest = (('SL', '50', '55'), ('CU', '50', '55'))
    assert create.validate(pitcher_form(pitches=(('FB', 'abc', '75'),) + rest), ASSNS)[1] == {
        'p_FB': create.GRADE_MSG}
    assert create.validate(pitcher_form(pitches=(('FB', '75', '70'),) + rest), ASSNS)[1] == {
        'p_FB': 'Ceiling must be at least Now.'}


@pytest.mark.parametrize('slots, ok', [
    ([('FB', '50', '50')], False),
    ([('FB', '50', '50'), ('SL', '50', '50')], True),
    ([(s, '50', '50') for s in ('FB', 'CB', 'SI', 'SL', 'CU')], True),
    ([(s, '50', '50') for s in create.PITCH_SLOTS[:6]], False),
])
def test_a_pitcher_throws_two_to_five_pitches(slots, ok):
    _, errors = create.validate(pitcher_form(pitches=slots, mode='sandbox'), ASSNS)
    assert ('pitches' not in errors) is ok
    if not ok:
        assert errors['pitches'] == 'Pick 2 to 5 pitches.'


def test_realistic_mode_names_the_gap_on_each_rating_it_is_over():
    spec, errors = create.validate(form(age='27', now_contact='60', ceil_contact='70'), ASSNS)
    assert spec is None and errors == {'ceil_contact': GAP_MSG % (27, 5)}
    spec, errors = create.validate(pitcher_form(age='31'), ASSNS)
    assert spec is None and errors == {'p_FB': GAP_MSG % (31, 0), 'p_SL': GAP_MSG % (31, 0)}


def test_realistic_mode_names_the_budget_it_is_over():
    now80 = {'now_' + r: '80' for r in create.HIT_RATINGS}
    now80.update({'ceil_' + r: '80' for r in create.HIT_RATINGS})
    assert create.validate(form(**now80), ASSNS)[1] == {
        'budget': 'Over the realistic budget: Now uses 150 of 50 points.'}
    ceil75 = {'now_' + r: '50' for r in create.HIT_RATINGS}
    ceil75.update({'ceil_' + r: '75' for r in create.HIT_RATINGS})
    assert create.validate(form(age='22', **ceil75), ASSNS)[1] == {
        'budget': 'Over the realistic budget: Ceiling uses 125 of 100 points.'}


def test_sandbox_skips_the_gap_and_the_budget():
    now80 = {'now_' + r: '80' for r in create.HIT_RATINGS}
    now80.update({'ceil_' + r: '80' for r in create.HIT_RATINGS})
    spec, errors = create.validate(form(mode='sandbox', age='27', **now80), ASSNS)
    assert errors == {} and spec is not None
    assert create.validate(pitcher_form(mode='sandbox', age='31'), ASSNS)[1] == {}


def test_validate_is_none_when_either_part_has_errors():
    spec, errors = create.validate(form(assn='NOPE'), ASSNS)
    assert spec is None and set(errors) == {'assn'}
    spec, errors = create.validate(form(now_contact='52'), ASSNS)
    assert spec is None and set(errors) == {'now_contact'}


def test_donor_takes_the_nearest_player():
    far = player(101, cur={0: 20, 1: 90, 2: 90, 3: 90, 19: 20})
    near = player(105, cur={0: R(60), 1: R(50), 2: R(40), 3: R(30), 19: 82})
    assert create.donor([far, near], SPEC_SS, 1996) == near


def test_donor_prefers_the_spec_position():
    other_spot = player(103, pos=3, cur={0: R(60), 1: R(50), 2: R(40), 3: R(30), 19: 82})
    shortstop = player(101, pos=6, cur={0: 20, 1: 90, 2: 90, 3: 90, 19: 20})
    assert create.donor([other_spot, shortstop], SPEC_SS, 1996) == shortstop


def test_donor_falls_back_to_hitters_then_fails_for_a_pitcher():
    pitcher = player(100, pos=1, cur={0: R(60), 1: R(50), 2: R(40), 3: R(30), 19: 82})
    hitter = player(102, pos=3, cur={0: 10, 1: 10, 2: 10, 3: 10, 19: 10})
    assert create.donor([pitcher, hitter], SPEC_SS, 1996) == hitter
    with pytest.raises(ValueError):
        create.donor([hitter], SPEC_P, 1996)


def test_donor_ties_go_to_the_lower_id_and_age_counts():
    cur = {0: R(60), 1: R(50), 2: R(40), 3: R(30), 19: 82}
    a = player(120, cur=cur)
    b = player(110, cur=cur)
    assert create.donor([a, b], SPEC_SS, 1996) == b
    young = player(111, born=1972, cur=cur)
    old = player(112, born=1950, cur=cur)
    assert create.donor([old, young], SPEC_SS, 1996) == young


def test_donor_skips_nameless_records_and_ids_below_a_hundred():
    exact = {0: R(60), 1: R(50), 2: R(40), 3: R(30), 19: 82}
    assert create.donor([player(50, cur=exact), player(102, first='', last='', cur=exact),
                         player(103, cur={0: 1})], SPEC_SS, 1996) == player(103, cur={0: 1})
    with pytest.raises(ValueError):
        create.donor([player(50, cur=exact)], SPEC_SS, 1996)


DONOR_HIT = player(105, 'Don', 'Or', pos=6, bats=2, throws=2,
                   cur={0: 40, 1: 60, 2: 70, 3: 30, 4: 9, 7: 60, 19: 80},
                   peak={0: 90, 1: 60, 2: 60, 3: 45, 7: 70, 19: 85})
DONOR_PIT = player(300, 'Dan', 'Pit', pos=1, born=1975, bats=1, throws=1,
                   cur={5: 60, 6: 50, 7: 70, 9: 50, 13: 30}, peak={5: 65, 6: 50, 7: 80, 9: 55},
                   raw={K_ATTR: 40})


def test_build_hitter_sets_current_and_peak_from_now_and_ceiling():
    rec = create.build_record(SPEC_SS, DONOR_HIT, 300, 1996)
    assert struct.unpack_from('<H', rec, 0)[0] == 300
    assert struct.unpack_from('<I', rec, 0x1a)[0] == datetime.date(1972, 7, 1).toordinal() + 365
    assert bytes(rec[30:47]) == b'Ned' + bytes(14) and bytes(rec[47:64]) == b'Ray' + bytes(14)
    assert (rec[64], rec[65], rec[66], rec[68]) == (1, 1, 2, 6)
    assert (rec[CUR], rec[PEAK]) == (R(60), R(65))              # contact: now 60, ceiling 65
    assert (rec[CUR + 1], rec[PEAK + 1]) == (R(50), R(50))      # power: no growth
    assert (rec[CUR + 2], rec[PEAK + 2]) == (R(40), R(45))      # speed
    assert (rec[CUR + 3], rec[PEAK + 3]) == (R(30), R(35))      # arm
    assert (rec[CUR + 19], rec[PEAK + 19]) == (R(70), R(70))    # fielding at SS (index 14 + 5)
    assert rec[CUR + 4] == 9                                    # hold runners: copied from the donor
    assert rec[STAMINA_BYTE] == 0


def test_build_hitter_has_no_pitch_bytes_whatever_the_donor_throws():
    rec = create.build_record(SPEC_SS, DONOR_HIT, 300, 1996)
    assert DONOR_HIT[CUR + 7] == 60 and DONOR_HIT[PEAK + 7] == 70     # the donor has a pitch
    assert all(rec[CUR + i] == 0 and rec[PEAK + i] == 0 for i in range(7, 14))
    assert bytes(rec[0x8d:]) == bytes(192 - 0x8d)


def test_build_pitcher_sets_thrown_pitches_and_zeroes_the_rest():
    rec = create.build_record(SPEC_P, DONOR_PIT, 301, 1996)
    assert (rec[64], rec[65], rec[66], rec[68]) == (1, 2, 1, 1)
    assert (rec[CUR + 5], rec[PEAK + 5]) == (R(60), R(65))       # stamina now 60, ceiling 65
    assert (rec[CUR + 6], rec[PEAK + 6]) == (R(50), R(50))       # control
    assert (rec[CUR + 4], rec[PEAK + 4]) == (R(50), R(50))       # hold
    assert rec[K_ATTR] == R(70)                                  # strikeout: one byte, no peak
    assert (rec[CUR + 7], rec[PEAK + 7]) == (R(70), R(75))       # fastball
    assert (rec[CUR + 10], rec[PEAK + 10]) == (R(50), R(55))     # slider: slot 3, index 7 + 3
    assert all(rec[CUR + i] == 0 and rec[PEAK + i] == 0 for i in (8, 9, 11, 12, 13))
    assert rec[STAMINA_BYTE] == min(255, 51 + R(60))
    assert create.stuff(rec) == pytest.approx((R(70) + R(50)) / 2)


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


def test_scouting_report_lists_the_hitting_ratings_in_order():
    spec = dict(SPEC_SS, now={'contact': 60, 'power': 50, 'speed': 40, 'arm': 30, 'fielding': 70},
                ceiling={'contact': 70, 'power': 50, 'speed': 45, 'arm': 30, 'fielding': 70})
    assert create.scouting_report(spec) == [
        'Contact is plus, with room to grow to plus-plus.',
        'Power is average.',
        'Speed is below average, with room to grow to fringe.',
        'Arm is well below average.',
        'Fielding is plus-plus.',
    ]


def test_scouting_report_lists_ratings_then_thrown_pitches_in_slot_order():
    spec = dict(SPEC_P, pitches={'SL': (50, 55), 'FB': (70, 75)})
    lines = create.scouting_report(spec)
    assert [line.split(' ')[0] for line in lines[:4]] == ['Stamina', 'Control', 'Hold', 'Strikeout']
    assert lines[4:] == ['Fastball: 70 now, 75 at the ceiling.', 'Slider: 50 now, 55 at the ceiling.']


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


SS_CUR = {0: R(60), 1: R(50), 2: R(40), 3: R(30), 19: R(70)}     # an exact match for SPEC_SS's Now grades


@pytest.fixture
def league_game(tmp_path, monkeypatch):
    """A writer for a TEST77 with the given player records, pool ids and rosters: write(records, pool, teams)."""
    def write(records, pool, teams=None):
        root = tmp_path / 'league'
        (root / 'Assn').mkdir(parents=True, exist_ok=True)
        (root / 'Assn' / 'TEST77.ASN').write_bytes(b'asn')
        (root / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes(records))
        (root / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes(pool))
        monkeypatch.setattr(create.gamedata, 'association',
                            lambda path: {'name': ASN_NAME, 'teams': teams or {}, 'games': []})
        return str(root)
    return write


def test_comparable_takes_the_nearest_real_player_at_the_position(league_game):
    far = player(130, 'Bo', 'Bee', pos=6, born=1952, cur={**SS_CUR, 0: R(60) + 10})
    near = player(120, 'Ann', 'Ace', pos=6, born=1952, cur=SS_CUR)
    other_spot = player(105, pos=4, born=1952, cur=SS_CUR)
    root = league_game([far, near, other_spot], [130, 120, 105], {1: {'abbrev': 'BOS', 'roster': [120]}})
    assert create.comparable(root, 'TEST77', SPEC_SS, 1977) == {
        'pid': 120, 'name': 'Ann Ace', 'team': 'BOS', 'age': 25, 'distance': 0}


def test_comparable_breaks_a_tie_to_the_lower_id_and_names_a_free_agent(league_game):
    a = player(130, 'Bo', 'Bee', pos=6, born=1952, cur={**SS_CUR, 0: R(60) + 10})
    b = player(110, 'Cy', 'Dee', pos=6, born=1952, cur={**SS_CUR, 0: R(60) + 10})
    root = league_game([a, b], [130, 110])
    assert create.comparable(root, 'TEST77', SPEC_SS, 1977) == {
        'pid': 110, 'name': 'Cy Dee', 'team': None, 'age': 25, 'distance': 10}


def test_comparable_pool_is_the_roster_or_the_free_agent_pool(league_game):
    stranger = player(120, 'Ann', 'Ace', pos=6, born=1952, cur=SS_CUR)
    assert create.comparable(league_game([stranger], []), 'TEST77', SPEC_SS, 1977) is None


def test_comparable_matches_pitchers_on_their_arsenal(league_game):
    arm = player(300, 'Al', 'Ko', pos=1, born=1952, cur={5: R(60), 6: R(50), 7: R(70), 9: R(50)},
                 raw={K_ATTR: R(70)})
    root = league_game([arm], [300])
    assert create.comparable(root, 'TEST77', SPEC_P, 1977) == {
        'pid': 300, 'name': 'Al Ko', 'team': None, 'age': 25, 'distance': 0}


def test_comparable_is_none_on_missing_or_unreadable_files(league_game, tmp_path):
    assert create.comparable(str(tmp_path / 'nowhere'), 'TEST77', SPEC_SS, 1977) is None
    root = league_game([player(120, pos=6, cur=SS_CUR)], [120])
    (tmp_path / 'league' / 'Assn' / 'TEST77.PYF').write_bytes(b'junk')
    assert create.comparable(root, 'TEST77', SPEC_SS, 1977) is None


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
