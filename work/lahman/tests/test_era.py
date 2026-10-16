"""Era run knobs: load_era, the z blend, rating offsets, Model.set_era and build.py --era. Synthetic data only: a Norm
built from hand rows, a Model with hand weights and one donor per role, duck-typed seasons; no database or game file."""
import json
import os
import sqlite3
import struct

import pytest

from lahman import build as B, ratings as RT

ZERO = {'ref_year': 1996, 'alpha': {'bat': 0.0, 'pit': 0.0}, 'offset': {n: 0.0 for n in RT.ERA_NAMES}}
PERSON = {'birth_year': 1900, 'birth_month': 5, 'birth_day': 5, 'first': 'Ann', 'last': 'Tester', 'bats': 'R',
          'throws': 'R'}


def write(tmp_path, cfg, name='era.json'):
    p = tmp_path / name
    p.write_text(json.dumps(cfg))
    return str(p)


# ---------------------------------------------------------------- load_era

def test_missing_path_is_all_zero(tmp_path):
    assert RT.load_era(str(tmp_path / 'nope.json'), 1927) == ZERO
    assert RT.load_era(None, 1927) == ZERO


def test_shipped_default_is_fitted_for_early_years_and_zero_from_1969():
    path = os.path.join(os.path.dirname(os.path.abspath(B.__file__)), 'era.json')
    assert B.ERA == path
    assert RT.load_era(path, 1969) == ZERO
    assert RT.load_era(path, 1996) == ZERO
    assert RT.load_era(path, 1998) == ZERO
    early = RT.load_era(path, 1927)
    assert early['alpha'] == {'bat': 1.0, 'pit': 1.0}
    assert early['offset']['PH'] == -30.0 and early['offset']['CH'] > 0


def test_base_values_and_missing_keys_mean_zero(tmp_path):
    p = write(tmp_path, {'ref_year': 1990, 'alpha': {'bat': 0.3}, 'offset': {'CH': 4}})
    era = RT.load_era(p, 2000)
    assert era['ref_year'] == 1990
    assert era['alpha'] == {'bat': 0.3, 'pit': 0.0}
    assert era['offset'] == dict(ZERO['offset'], CH=4.0)
    assert all(isinstance(v, float) for v in era['offset'].values())


def test_by_year_later_entry_wins_per_key(tmp_path):
    p = write(tmp_path, {'alpha': {'bat': 0.2}, 'offset': {'CH': 1, 'SP': 5}, 'by_year': [
        {'from': 1900, 'to': 1950, 'alpha': {'bat': 0.5, 'pit': 0.4}, 'offset': {'CH': 3}},
        {'from': 1920, 'to': 1930, 'alpha': {'bat': 0.9}},
        {'from': 1920, 'to': 1930, 'alpha': {'bat': 0.7}, 'offset': {'PH': -2}},
        {'from': 1960, 'to': 1970, 'offset': {'SP': -9}}]})
    e25 = RT.load_era(p, 1925)
    assert e25['alpha'] == {'bat': 0.7, 'pit': 0.4}                      # the last entry names bat, the first pit
    assert e25['offset']['CH'] == 3.0 and e25['offset']['PH'] == -2.0 and e25['offset']['SP'] == 5.0
    assert RT.load_era(p, 1900)['alpha']['bat'] == 0.5                  # from is inclusive
    assert RT.load_era(p, 1930)['alpha']['bat'] == 0.7                  # to is inclusive
    assert RT.load_era(p, 1950)['alpha']['bat'] == 0.5
    assert RT.load_era(p, 1951)['alpha'] == {'bat': 0.2, 'pit': 0.0}    # no entry holds it: the base
    assert RT.load_era(p, 1965)['offset']['SP'] == -9.0


@pytest.mark.parametrize('cfg, key', [
    ({'alpha': {'bat': 1.01}}, 'alpha.bat'),
    ({'alpha': {'pit': -0.01}}, 'alpha.pit'),
    ({'offset': {'CH': 30.5}}, 'offset.CH'),
    ({'offset': {'K': -31}}, 'offset.K'),
    ({'offset': {'XX': 1}}, 'offset.XX'),
    ({'offset': {'FLD': 1}}, 'offset.FLD'),
    ({'alpha': {'both': 0.5}}, 'alpha.both'),
    ({'alpha': {'bat': 'x'}}, 'alpha.bat'),
    ({'alpha': {'bat': True}}, 'alpha.bat'),
    ({'alpha': {'bat': float('nan')}}, 'alpha.bat'),
    ({'by_year': [{'from': 1, 'to': 2}, {'from': 3, 'to': 4, 'alpha': {'bat': 2}}]}, 'by_year[1].alpha.bat'),
    ({'by_year': [{'from': 1, 'to': 2, 'offset': {'ZZ': 1}}]}, 'by_year[0].offset.ZZ'),
])
def test_bad_values_raise_naming_the_key(tmp_path, cfg, key):
    with pytest.raises(ValueError, match=key.replace('[', r'\[').replace(']', r'\]')):
        RT.load_era(write(tmp_path, cfg), 1990)


def test_every_entry_is_checked_even_when_it_misses_the_year(tmp_path):
    p = write(tmp_path, {'by_year': [{'from': 1800, 'to': 1801, 'offset': {'CH': 99}}]})
    with pytest.raises(ValueError, match='by_year'):
        RT.load_era(p, 1990)


@pytest.mark.parametrize('cfg', [[], {'ref_year': '1996'}, {'by_year': {}}, {'by_year': [3]},
                                 {'by_year': [{'from': 1950, 'to': 1940}]}, {'by_year': [{'from': 'a', 'to': 2}]}])
def test_malformed_files_raise(tmp_path, cfg):
    with pytest.raises(ValueError):
        RT.load_era(write(tmp_path, cfg), 1990)


def test_range_edges_are_allowed(tmp_path):
    p = write(tmp_path, {'alpha': {'bat': 1, 'pit': 0}, 'offset': {'CH': 30, 'K': -30}})
    era = RT.load_era(p, 1990)
    assert era['alpha'] == {'bat': 1.0, 'pit': 0.0} and era['offset']['CH'] == 30.0 and era['offset']['K'] == -30.0


# ---------------------------------------------------------------- blend

def hit_line(h, hr, bb=50, so=80, d2=25):
    return dict(AB=500, H=h, HR=hr, BB=bb, SO=so, G=140, SB=5, CS=2, SF=4, HBP=3, SH=1, **{'2B': d2, '3B': 3})


def pit_line(so, bb, ip_outs=600, h=190, er=70):
    return dict(IPouts=ip_outs, G=30, GS=30, BB=bb, SO=so, HR=20, H=h, ER=er, SV=0, GF=0, CG=3)


def hit_norm(lines):
    return RT.Norm([RT.hit_feats(b)[0] for b in lines], RT.FEAT_H)


def pit_norm(lines):
    return RT.Norm([RT.pit_feats(q)[0] for q in lines], RT.FEAT_P)


OWN_H = hit_norm([hit_line(150, 15), hit_line(135, 8), hit_line(160, 25), hit_line(120, 5)])
REF_H = hit_norm([hit_line(140, 30, bb=60), hit_line(150, 42, bb=70), hit_line(165, 20), hit_line(130, 12)])
OWN_P = pit_norm([pit_line(180, 50), pit_line(120, 70), pit_line(150, 60), pit_line(90, 80)])
REF_P = pit_norm([pit_line(200, 45, h=170), pit_line(160, 55), pit_line(110, 75), pit_line(140, 65)])


def test_blend_z_endpoints_and_midpoint():
    own = {'a': -1.0, 'b': 2.0}
    ref = {'a': 3.0, 'b': 0.5}
    assert RT.blend_z(own, ref, 0) is own
    assert RT.blend_z(own, ref, 1.0) == ref
    mid = RT.blend_z(own, ref, 0.5)
    assert mid == {'a': 1.0, 'b': 1.25}
    q = RT.blend_z(own, ref, 0.25)
    assert q['a'] == pytest.approx(0.0) and q['b'] == pytest.approx(1.625)


def test_model_blend_uses_ref_norm_with_the_same_shrinkage():
    f, pa = RT.hit_feats(hit_line(170, 35))
    own = OWN_H.z(f, RT.FEAT_H, pa, RT.SHRINK_H)
    ref = REF_H.z(f, RT.FEAT_H, pa, RT.SHRINK_H)
    assert own != ref
    m = RT.Model()
    for a, want in ((0.0, own), (1.0, ref)):
        m.era = dict(ZERO, alpha={'bat': a, 'pit': 0.0})
        got = m._era_z(own, REF_H, f, RT.FEAT_H, pa, RT.SHRINK_H, 'bat')
        assert got == want
    m.era = dict(ZERO, alpha={'bat': 0.5, 'pit': 0.0})
    got = m._era_z(own, REF_H, f, RT.FEAT_H, pa, RT.SHRINK_H, 'bat')
    assert all(got[x] == pytest.approx((own[x] + ref[x]) / 2) for x in RT.FEAT_H)
    # the hitter alpha does not touch pitchers, and no sample (f None) or no ref leaves z alone
    assert m._era_z(own, REF_H, f, RT.FEAT_H, pa, RT.SHRINK_H, 'pit') is own
    assert m._era_z({}, REF_H, None, RT.FEAT_H, 0, RT.SHRINK_H, 'bat') == {}
    assert m._era_z(own, None, f, RT.FEAT_H, pa, RT.SHRINK_H, 'bat') is own


# ---------------------------------------------------------------- a fake model, donors and seasons

def donor(pos, ch=60, ph=55, sp=50, en=60, co=60, k=55):
    r = bytearray(RT.REC)
    struct.pack_into('<H', r, 0, 7)
    r[68] = pos
    for i, v in ((RT.CH, ch), (RT.PH, ph), (RT.SP, sp), (RT.EN, en), (RT.CO, co)):
        r[RT.CUR + i] = v
        r[RT.PEAK + i] = min(99, v + 4)
    r[RT.K_ATTR] = k
    r[RT.GF_ATTR] = 40
    if pos == 1:
        for i, v in zip(RT.PITCHES, (50, 60, 0, 40, 0, 0, 50)):
            r[RT.CUR + i] = v
            r[RT.PEAK + i] = min(99, v + 3) if v else 0
    return bytes(r)


def fake_model():
    m = RT.Model()
    m.w = {'CH': [60.0, 9.0, 1.0], 'PH': [55.0, 5.0, 4.0], 'SP': [50.0, 3.0, 2.0, 1.0], 'GF': [45.0, 6.0],
           'EN': [50.0, 2.0, 30.0], 'CO': [55.0, -8.0], 'K': [55.0, 9.0], 'ST': [55.0, 1.0, -3.0, 4.0, -2.0]}
    m.raw_mu = {'IPG': 6.0, 'GSr': 0.5}
    m.donors_h = [(3, 28, (60, 55, 50), donor(3))]
    m.donors_p = [(28, (60, 60, 55, 53.3), donor(1))]
    return m


class FakeSeason:
    """Duck-types the Season calls rate() makes; one hitter 'h' and one pitcher 'p', one all-league norm each."""
    def __init__(self, nh, np_, year=1927):
        self.year, self.leagues = year, RT.lahdb.MLB_LEAGUES
        self.bat = {'h': hit_line(170, 35)}
        self.pit = {'p': pit_line(210, 40, h=160, er=55)}
        self.fld, self.nf = {}, {}
        self.nh, self.np_ = {'': nh}, {'': np_}

    def norm(self, table, pid):
        return table['']

    def primary(self, pid):
        return 'P' if pid == 'p' else '1B'

    def games_at(self, pid):
        return {'P' if pid == 'p' else '1B': 100}

    def ref_norms(self):
        return {'h': self.nh[''], 'p': self.np_['']}


def rate(m, s, pid):
    return m.rate(s, pid, PERSON, 101, 2)


def test_zero_config_changes_nothing():
    s = FakeSeason(OWN_H, OWN_P)
    plain = fake_model()
    base = {pid: rate(plain, s, pid) for pid in ('h', 'p')}
    for era in (None, ZERO):
        m = fake_model()
        m.set_era(era, season=s)
        assert (m.ref_h, m.ref_p) == (None, None)             # nothing built for alpha 0
        assert {pid: rate(m, s, pid) for pid in ('h', 'p')} == base
        z = {'AVG': 0.7, 'ISO': 1.1, 'HR': 0.2, 'SBA': -0.3, 'SBg': 0.1, 'T': 0.4}
        for name in RT.TARGETS:
            assert m.predict(name, z, {'IPG': 6.5, 'GSr': 0.8}, 100, 30) == plain.predict(name, z, {'IPG': 6.5, 'GSr': 0.8},
                                                                                         100, 30)


def test_alpha_one_rates_like_the_ref_season():
    own = FakeSeason(OWN_H, OWN_P)
    ref = FakeSeason(REF_H, REF_P, year=1996)
    want = {pid: rate(fake_model(), ref, pid) for pid in ('h', 'p')}   # a season whose own norm is the ref norm
    plain = {pid: rate(fake_model(), own, pid) for pid in ('h', 'p')}
    assert plain['h'] != want['h'] and plain['p'] != want['p']
    m = fake_model()
    m.set_era(dict(ZERO, alpha={'bat': 1.0, 'pit': 1.0}), season=ref)
    assert {pid: rate(m, own, pid) for pid in ('h', 'p')} == want
    m.set_era(dict(ZERO, alpha={'bat': 1.0, 'pit': 0.0}), season=ref)  # only hitters blend
    got = {pid: rate(m, own, pid) for pid in ('h', 'p')}
    assert got['h'] == want['h'] and got['p'] == plain['p']
    m.set_era(dict(ZERO, alpha={'bat': 0.0, 'pit': 1.0}), season=ref)
    got = {pid: rate(m, own, pid) for pid in ('h', 'p')}
    assert got['h'] == plain['h'] and got['p'] == want['p']


def test_alpha_half_lands_between():
    own = FakeSeason(OWN_H, OWN_P)
    ref = FakeSeason(REF_H, REF_P, year=1996)
    lo = rate(fake_model(), own, 'h')[RT.CUR + RT.CH]
    hi = rate(fake_model(), ref, 'h')[RT.CUR + RT.CH]
    m = fake_model()
    m.set_era(dict(ZERO, alpha={'bat': 0.5, 'pit': 0.0}), season=ref)
    mid = rate(m, own, 'h')[RT.CUR + RT.CH]
    assert min(lo, hi) <= mid <= max(lo, hi) and lo != hi


def test_offset_shifts_only_its_own_target():
    z = {'AVG': 0.7, 'ISO': 1.1, 'HR': 0.2, 'SBA': -0.3, 'SBg': 0.1, 'T': 0.4, 'BB9': 0.5, 'K9': 0.9}
    raw = {'IPG': 6.5, 'GSr': 0.8}
    plain = fake_model()
    for name in ('CH', 'PH', 'SP', 'GF', 'EN', 'CO', 'K'):
        m = fake_model()
        m.set_era(dict(ZERO, offset=dict(ZERO['offset'], **{name: 6.5})))
        for other in ('CH', 'PH', 'SP', 'GF', 'EN', 'CO', 'K'):
            diff = m.predict(other, z, raw, 100, 30) - plain.predict(other, z, raw, 100, 30)
            assert diff == pytest.approx(6.5 if other == name else 0.0)


def test_offset_goes_in_before_the_clamp():
    """Intercept 70.3 plus 0.3 rounds to 71; clamping first would give 70. A big offset still stops at the 1..99 rails."""
    blank = B.BlankSeason(1927, '1B')
    m = fake_model()
    m.w['CH'] = [70.3, 0.0, 0.0]
    assert rate(m, blank, None)[RT.CUR + RT.CH] == 70
    m.set_era(dict(ZERO, offset=dict(ZERO['offset'], CH=0.3)))
    assert rate(m, blank, None)[RT.CUR + RT.CH] == 71
    m.set_era(dict(ZERO, offset=dict(ZERO['offset'], CH=30.0)))
    assert rate(m, blank, None)[RT.CUR + RT.CH] == 99
    m.w['CH'] = [10.0, 0.0, 0.0]
    m.set_era(dict(ZERO, offset=dict(ZERO['offset'], CH=-30.0)))
    assert rate(m, blank, None)[RT.CUR + RT.CH] == 1


def test_stuff_offset_moves_every_pitch_rating():
    blank = B.BlankSeason(1927, 'P')
    m = fake_model()
    base = rate(m, blank, None)
    m.set_era(dict(ZERO, offset=dict(ZERO['offset'], ST=5.0)))
    up = rate(m, blank, None)
    for i in RT.PITCHES:
        if base[RT.CUR + i]:
            assert up[RT.CUR + i] - base[RT.CUR + i] == 5
        else:
            assert up[RT.CUR + i] == 0
    assert up[RT.CUR + RT.CO] == base[RT.CUR + RT.CO]         # the other targets stay put


# ---------------------------------------------------------------- set_era

def test_set_era_takes_the_ref_norms_from_the_season_without_a_second_pass(monkeypatch):
    built = []
    monkeypatch.setattr(RT, 'Season', lambda con, year, leagues=None: built.append(year))
    ref = FakeSeason(REF_H, REF_P, year=1996)
    m = fake_model()
    m.set_era(dict(ZERO, alpha={'bat': 0.4, 'pit': 0.4}), season=ref)
    assert built == [] and m.ref_h is REF_H and m.ref_p is REF_P


def test_set_era_builds_the_ref_season_once_per_model(monkeypatch):
    built = []

    class Stub:
        def __init__(self, con, year, leagues=None):
            built.append(year)

        def ref_norms(self):
            return {'h': REF_H, 'p': REF_P}
    monkeypatch.setattr(RT, 'Season', Stub)
    m = fake_model()
    era = dict(ZERO, alpha={'bat': 0.4, 'pit': 0.0})
    other = FakeSeason(OWN_H, OWN_P, year=1927)
    with pytest.raises(ValueError, match='1996'):
        m.set_era(era, season=other)                          # not the ref year and no database
    m.set_era(era, season=other, con=object())
    m.set_era(era, season=other, con=object())
    assert built == [1996] and m.ref_h is REF_H
    ref = FakeSeason(REF_H, REF_P, year=1996)
    ref.leagues = ('NN2', 'NAL')                              # a Negro leagues season is not the majors' 1996
    m2 = fake_model()
    m2.set_era(era, season=ref, con=object())
    assert built == [1996, 1996]


def test_season_ref_norms_are_the_whole_year_norms():
    s = RT.Season.__new__(RT.Season)
    s.nh, s.np_ = {'': OWN_H, 'AL': REF_H}, {'': OWN_P}
    assert s.ref_norms() == {'h': OWN_H, 'p': OWN_P}


# ---------------------------------------------------------------- build.py --era

@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    """B.main with a one-table database and build() replaced by a recorder that notes what was printed before it ran."""
    db = tmp_path / 'lah.sqlite'
    con = sqlite3.connect(db)
    con.execute('create table teams (yearID int, lgID text)')
    con.executemany('insert into teams values (?, ?)', [(1927, 'AL'), (1927, 'NL'), (1996, 'AL')])
    con.commit()
    con.close()
    calls = []

    def fake_build(*a, **kw):
        calls.append((a, kw, capsys.readouterr().out))
    monkeypatch.setattr(B, 'build', fake_build)

    def run(*extra):
        args = ['--year', '1927', '--install', str(tmp_path), '--db', str(db)] + list(extra)
        assert B.main(args) == 0
        return calls[-1]
    return run


def test_cli_default_era_is_the_shipped_fit(cli):
    a, kw, out = cli()
    line = out.splitlines()[-1]
    assert line.startswith('era: year=1927 alpha bat=1.0 pit=1.0 offsets=')
    assert kw['era'] == RT.load_era(B.ERA, 1927)


def test_cli_era_file_prints_one_line_before_building(cli, tmp_path):
    p = write(tmp_path, {'alpha': {'bat': 0.5}, 'offset': {'CH': 3, 'K': -2.5},
                         'by_year': [{'from': 1927, 'to': 1927, 'alpha': {'pit': 0.25}}]})
    a, kw, out = cli('--era', p)
    lines = [x for x in out.splitlines() if x.startswith('era:')]
    assert lines == ["era: year=1927 alpha bat=0.5 pit=0.25 offsets={'CH': 3.0, 'K': -2.5}"]
    assert kw['era']['alpha'] == {'bat': 0.5, 'pit': 0.25}


def test_cli_rejects_a_bad_or_missing_era_file(cli, tmp_path, capsys):
    bad = write(tmp_path, {'offset': {'CH': 99}})
    for path in (bad, str(tmp_path / 'absent.json')):
        with pytest.raises(SystemExit) as e:
            cli('--era', path)
        assert e.value.code == 2
    assert 'offset.CH' in capsys.readouterr().err
