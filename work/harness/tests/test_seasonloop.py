"""seasonloop's offseason pieces: demographics() on a synthetic association (association() stubbed, a real enciphered
PYR and .pyf), and notice() on the reference screenshots when they are present."""
import datetime
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import seasonloop  # noqa: E402
import league      # noqa: E402 (work/ is on the path once gamedata is imported)


def player(pid, born, first='Pat', last='Doe', pos=2):
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[seasonloop.gamedata.P_POS] = pos
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, born.toordinal() + 365)
    return bytes(p)


def pyr_bytes(records, seed=(0x6b, 0xe2)):
    t = league._forward(seed)
    return bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records)


def pyf_bytes(ids):
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids)


def test_demographics_splits_rostered_free_agents_and_retired(tmp_path, monkeypatch):
    d = datetime.date
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([
        player(100, d(1980, 3, 1)),      # rostered, 27 on July 1 2007
        player(101, d(1975, 8, 1)),      # free agent, 31 (birthday after July 1)
        player(102, d(1960, 1, 1)),      # on neither list: retired
        player(103, d(1984, 7, 1), pos=1),   # rostered pitcher, 23 (birthday on July 1 counts)
    ]))
    (tmp_path / 'TEST.pyf').write_bytes(pyf_bytes([101]))
    (tmp_path / 'TEST.ASN').write_bytes(b'asn')
    monkeypatch.setattr(seasonloop.gamedata, 'association',
                        lambda path: {'teams': {1: {'roster': [100]}, 2: {'roster': [103, 555]}}, 'games': []})
    got = seasonloop.demographics(str(tmp_path), 'TEST', 2007)
    assert got == {'year': 2007, 'rostered': 2, 'mean_age': 25.0, 'le25': 1, 'ge33': 0, 'hist': {23: 1, 27: 1},
                   'fa': 1, 'fa_mean_age': 31.0, 'retired': 1, 'players': 4, 'roster_min': 1, 'pitchers_min': 0}


def test_demographics_without_a_free_agent_file(tmp_path, monkeypatch):
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([player(100, datetime.date(1970, 1, 1))]))
    (tmp_path / 'TEST.ASN').write_bytes(b'asn')
    monkeypatch.setattr(seasonloop.gamedata, 'association', lambda path: {'teams': {}, 'games': []})
    got = seasonloop.demographics(str(tmp_path), 'TEST', 2007)
    assert (got['rostered'], got['fa'], got['retired'], got['mean_age']) == (0, 0, 1, 0)
    assert (got['roster_min'], got['pitchers_min']) == (0, 0)


def test_demographics_counts_pitchers_per_team(tmp_path, monkeypatch):
    d = datetime.date(1980, 1, 1)
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([player(100, d, pos=1), player(101, d, pos=1),
                                                   player(102, d), player(103, d, pos=1)]))
    (tmp_path / 'TEST.ASN').write_bytes(b'asn')
    monkeypatch.setattr(seasonloop.gamedata, 'association',
                        lambda path: {'teams': {1: {'roster': [100, 101, 102]}, 2: {'roster': [103, 102]}}, 'games': []})
    got = seasonloop.demographics(str(tmp_path), 'TEST', 2007)
    assert (got['roster_min'], got['pitchers_min']) == (2, 1)


@pytest.mark.skipif(not all(os.path.exists(os.path.join(seasonloop.REFS, f)) for f in seasonloop.NOTICES.values()),
                    reason='reference screenshots absent')
def test_each_notice_reference_is_recognised_and_a_plain_screen_is_not():
    for kind, ref in seasonloop.NOTICES.items():
        assert seasonloop.notice(os.path.join(seasonloop.REFS, ref)) == kind
    for plain in ('f_assn.png', 'f_update.png'):
        if os.path.exists(os.path.join(seasonloop.REFS, plain)):
            assert seasonloop.notice(os.path.join(seasonloop.REFS, plain)) is None
