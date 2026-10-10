"""rookietable: quantiles, the generated/target split and the header, on synthetic PYR files."""
import datetime
import struct

import pytest

from lahman import ratings as RT, rookietable as T


def rec(pid, born, peaks):
    """A record with every mapped class at 1 (pitch 7 and fielding only when given), then peaks on top."""
    pitcher = any(7 <= k <= 13 for k in peaks)
    base = {3: 1, 4: 1, 5: 1, 6: 1} if pitcher else {0: 1, 1: 1, 2: 1, 3: 1}
    peaks = {**base, **peaks}
    r = bytearray(RT.REC)
    struct.pack_into('<H', r, 0, pid)
    struct.pack_into('<I', r, 0x1a, RT.serial(born))
    for k, v in peaks.items():
        r[RT.PEAK + k] = v
    return bytes(r)


def test_quantiles_ends_and_nearest_rank():
    q = T.quantiles(range(101))
    assert len(q) == T.POINTS and q[0] == 0 and q[-1] == 100 and q[10] == 50
    assert T.quantiles([7]) == [7] * T.POINTS
    with pytest.raises(ValueError):
        T.quantiles([])


def test_tables_split_generated_from_target(tmp_path):
    base = [rec(100, datetime.date(1968, 6, 1), {0: 60, 1: 70, 15: 50}),        # 28: target hitter
            rec(101, datetime.date(1975, 6, 1), {0: 99, 1: 99}),                # 21: too young, left out
            rec(102, datetime.date(1967, 1, 1), {6: 66, 7: 80, 8: 40}),         # 30: target pitcher
            rec(50, datetime.date(1968, 1, 1), {0: 5, 15: 9})]                # pid < 100: never a player
    gen = base + [rec(200, datetime.date(1976, 1, 1), {0: 40, 1: 45, 16: 30}),
                  rec(201, datetime.date(1977, 1, 1), {6: 50, 7: 60, 9: 55})]
    hp, gp = tmp_path / 'base.pyr', tmp_path / 'gen.pyr'
    head = bytes([0x12, 0x34]) + bytes(RT.REC - 2)
    RT.write_pyr(str(hp), head, base)
    RT.write_pyr(str(gp), head, gen)
    _, b = RT.read_pyr(str(hp))
    _, g = RT.read_pyr(str(gp))
    tabs, n_gen, n_target = T.tables(b, g, 1997)
    assert (n_gen, n_target) == (2, 2)
    assert tabs['H_CONTACT'] == ([40] * T.POINTS, [60] * T.POINTS)
    assert tabs['H_FIELD'] == ([30] * T.POINTS, [50] * T.POINTS)
    assert tabs['P_PITCH'][0][0] == 55 and tabs['P_PITCH'][0][-1] == 60
    assert tabs['P_PITCH'][1][0] == 40 and tabs['P_PITCH'][1][-1] == 80
    assert tabs['P_CONTROL'] == ([50] * T.POINTS, [66] * T.POINTS)


def test_header_shape():
    tabs = {name: (list(range(T.POINTS)), list(range(10, 10 + T.POINTS))) for name, _, _ in T.CLASSES}
    h = T.header(tabs, 5, 6, 1997)
    assert '#define RQ_POINTS 21' in h and '#define RQ_CLASSES %d' % len(T.CLASSES) in h
    assert h.count('/* h_contact */') == 2 and 'RC_P_PITCH' in h
    assert '{10,11,12,' in h
