"""gamedata.demographics(): the league's age make-up on a synthetic association (association() stubbed, a real
enciphered PYR and .pyf)."""
import datetime
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import league    # noqa: E402 (work/ is on the path once gamedata is imported)


def player(pid, born, first='Pat', last='Doe', pos=2):
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[gamedata.P_POS] = pos
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, born.toordinal() + 365)
    return bytes(p)


def pyr_bytes(records, seed=(0x6b, 0xe2)):
    t = league._forward(seed)
    return bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records)


def pyf_bytes(ids):
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids)


def _stub(monkeypatch, teams):
    monkeypatch.setattr(gamedata, 'association', lambda path: {'teams': teams, 'games': []})


def test_demographics_splits_rostered_free_agents_and_retired(tmp_path, monkeypatch):
    d = datetime.date
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([
        player(100, d(1980, 3, 1)),      # rostered, 27 on July 1 2007
        player(101, d(1975, 8, 1)),      # free agent, 31 (birthday after July 1)
        player(102, d(1960, 1, 1)),      # on neither list: retired
        player(103, d(1984, 7, 1), pos=1),   # rostered pitcher, 23 (birthday on July 1 counts)
    ]))
    (tmp_path / 'TEST.pyf').write_bytes(pyf_bytes([101]))
    _stub(monkeypatch, {1: {'roster': [100]}, 2: {'roster': [103, 555]}})
    got = gamedata.demographics('x.ASN', str(tmp_path / 'TEST.PYR'), str(tmp_path / 'TEST.pyf'), 2007)
    assert got == {'year': 2007, 'rostered': 2, 'mean_age': 25.0, 'le25': 1, 'ge33': 0, 'hist': {23: 1, 27: 1},
                   'fa': 1, 'fa_mean_age': 31.0, 'retired': 1, 'players': 4, 'roster_min': 1, 'pitchers_min': 0}


def test_demographics_pyf_none_or_junk_means_no_free_agents(tmp_path, monkeypatch):
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([player(100, datetime.date(1975, 8, 1))]))
    junk = tmp_path / 'TEST.pyf'
    junk.write_bytes(b'junkjk')
    _stub(monkeypatch, {1: {'roster': [100]}})
    none_case = gamedata.demographics('x.ASN', str(tmp_path / 'TEST.PYR'), None, 2007)
    junk_case = gamedata.demographics('x.ASN', str(tmp_path / 'TEST.PYR'), str(junk), 2007)
    assert (none_case['fa'], none_case['fa_mean_age']) == (0, 0)
    assert junk_case == none_case


def test_demographics_skips_small_ids_and_empty_names(tmp_path, monkeypatch):
    d = datetime.date(1980, 1, 1)
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([player(99, d), player(100, d), player(101, d, first='', last='')]))
    _stub(monkeypatch, {1: {'roster': [100, 101]}})
    got = gamedata.demographics('x.ASN', str(tmp_path / 'TEST.PYR'), None, 2007)
    assert (got['players'], got['rostered'], got['retired']) == (1, 1, 0)


def test_demographics_bad_birth_serial_leaves_the_player_out_of_the_ages(tmp_path, monkeypatch):
    p = bytearray(player(105, datetime.date(1980, 1, 1)))
    struct.pack_into('<I', p, 0x1a, 0xFFFFFFFF)
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([bytes(p), player(100, datetime.date(1980, 1, 1))]))
    _stub(monkeypatch, {1: {'roster': [100]}})
    got = gamedata.demographics('x.ASN', str(tmp_path / 'TEST.PYR'), None, 2007)
    assert (got['players'], got['rostered'], got['hist'], got['retired']) == (2, 1, {27: 1}, 1)
