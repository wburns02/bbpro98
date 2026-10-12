"""portrait.py: the same bytes for the same inputs, the 16 sepia shades, bad inputs that never raise, the picture each
input is meant to change, and portrait_sheet.py's BMP. The picture is checked by what it shows, not by exact bytes."""
import importlib
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import portrait  # noqa: E402

W, H = portrait.W, portrait.H
LEVEL = {portrait.ramp(k / 15): k for k in range(16)}
SHEET = os.path.join(HERE, 'portrait_sheet.py')


def level(img, x, y):
    i = (y * W + x) * 3
    return LEVEL[tuple(img[2][i:i + 3])]


def row_bytes(img, y):
    return img[2][y * W * 3:(y + 1) * W * 3]


def differing_rows(a, b):
    return {y for y in range(H) if row_bytes(a, y) != row_bytes(b, y)}


def mean_dark_x(img):
    xs = [x for y in range(50, 91) for x in range(W) if level(img, x, y) <= 3]
    return sum(xs) / len(xs)


def test_same_inputs_give_same_bytes():
    kw = dict(age=34, pos='P', power=65, speed=70, bats='L', throws='R', era=1955, letter='B')
    assert portrait.portrait(42, **kw) == portrait.portrait(42, **kw)


def test_same_bytes_after_a_fresh_import():
    before = portrait.portrait(42, era=1978, bats='S')
    reloaded = importlib.reload(portrait)
    assert reloaded.portrait(42, era=1978, bats='S') == before


def test_different_seeds_give_different_pictures():
    pictures = {portrait.portrait(s)[2] for s in range(20)}
    assert len(pictures) == 20


def test_returns_size_and_rgb_bytes():
    w, h, data = portrait.portrait(1)
    assert (w, h) == (120, 150)
    assert isinstance(data, bytes) and len(data) == 120 * 150 * 3


def test_ramp_endpoints_and_clamp():
    assert portrait.ramp(0) == (38, 30, 20)
    assert portrait.ramp(1) == (238, 224, 196)
    assert portrait.ramp(-1) == portrait.ramp(0)
    assert portrait.ramp(2) == portrait.ramp(1)


def test_sixteen_shades_run_dark_to_light():
    shades = [portrait.ramp(k / 15) for k in range(16)]
    assert len(set(shades)) == 16
    assert all(a[0] < b[0] for a, b in zip(shades, shades[1:]))


def test_every_pixel_is_one_of_the_sixteen_shades():
    for kw in ({}, dict(pos='P', bats='L', era=1978, power=80, speed=80, letter='C'), dict(era=1890, age=50)):
        data = portrait.portrait(77, **kw)[2]
        used = set(zip(data[0::3], data[1::3], data[2::3]))
        assert used <= set(LEVEL)
        assert len(used) >= 8


def test_monochrome_sepia():
    data = portrait.portrait(5, pos='P', letter='N')[2]
    assert all(r >= g >= b for r, g, b in zip(data[0::3], data[1::3], data[2::3]))


def test_bad_inputs_never_raise():
    bad = [dict(age=None), dict(age=-5), dict(age=200), dict(age='old'),
           dict(pos=None), dict(pos='XYZ'),
           dict(power=None), dict(power=0), dict(power=999), dict(power='high'), dict(speed=None),
           dict(bats=None), dict(bats='Q'), dict(throws=None),
           dict(era=None), dict(era=1500), dict(era=3000),
           dict(letter=None), dict(letter='!'), dict(letter='NYY'), dict(letter=7)]
    for kw in bad:
        w, h, data = portrait.portrait(3, **kw)
        assert (w, h, len(data)) == (120, 150, 120 * 150 * 3), kw
    for seed in (-1, 2 ** 70, None):
        assert len(portrait.portrait(seed)[2]) == 120 * 150 * 3


def test_defaults_and_clamps_give_the_same_picture():
    base = dict(seed=9, pos='P', era=1955)
    pairs = [
        (dict(age=None), dict(age=28)), (dict(age=-5), dict(age=16)), (dict(age=200), dict(age=50)),
        (dict(power=None), dict(power=50)), (dict(power=0), dict(power=20)), (dict(power=999), dict(power=80)),
        (dict(speed=None), dict(speed=50)), (dict(era=None), dict(era=1998)),
        (dict(era=1500), dict(era=1870)), (dict(era=3000), dict(era=2030)),
        (dict(letter='NYY'), dict(letter='N')), (dict(letter='!'), dict(letter='')),
        (dict(bats='Q'), dict(bats='R')), (dict(throws=None), dict(throws='R')),
        (dict(seed=-1), dict(seed=0xFFFFFFFF)), (dict(seed=2 ** 70), dict(seed=0)),
    ]
    for odd, even in pairs:
        assert portrait.portrait(**{**base, **odd}) == portrait.portrait(**{**base, **even}), odd


def run_width(img, y):
    xs = [x for x in range(W) if level(img, x, y) <= 1]     # the shoulder outline
    return xs[-1] - xs[0]


def test_power_widens_the_shoulders():
    weak, strong = portrait.portrait(12, power=20), portrait.portrait(12, power=80)
    assert weak != strong
    assert run_width(strong, 140) > run_width(weak, 140)


def test_era_changes_the_cap():
    old, new = portrait.portrait(14, era=1900), portrait.portrait(14, era=2010)
    assert any(20 <= y <= 45 for y in differing_rows(old, new))


def test_age_lines_show_on_the_forehead():
    young, old = portrait.portrait(14, age=22), portrait.portrait(14, age=45)
    assert any(44 <= y <= 56 for y in differing_rows(young, old))


def test_bats_turn_the_head():
    left, right = portrait.portrait(11, bats='L'), portrait.portrait(11, bats='R')
    assert left != right
    assert mean_dark_x(left) > mean_dark_x(right)


def test_letter_changes_only_the_cap():
    plain, lettered = portrait.portrait(3), portrait.portrait(3, letter='N')
    rows = differing_rows(plain, lettered)
    assert rows and all(20 <= y <= 50 for y in rows)


def test_face_is_drawn_darker_than_the_background():
    img = portrait.portrait(21)
    assert max(level(img, x, y) for x in range(55, 66) for y in range(61, 72)) <= 10


def test_corners_are_darker_than_the_background_top():
    img = portrait.portrait(8)
    top = level(img, 60, 10)
    for x, y in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
        assert level(img, x, y) < top


def test_pitchers_wear_a_sleeve_stripe_on_the_throwing_side():
    assert portrait.portrait(4, pos='P', throws='L') != portrait.portrait(4, pos='P', throws='R')
    assert portrait.portrait(4, pos='SS', throws='L') == portrait.portrait(4, pos='SS', throws='R')
    assert portrait.portrait(4, pos='P') != portrait.portrait(4, pos='SS')


def test_speed_streaks_start_at_65():
    assert portrait.portrait(6, speed=75) != portrait.portrait(6, speed=30)
    assert portrait.portrait(6, speed=64) == portrait.portrait(6)


def test_contact_sheet_writes_a_bmp(tmp_path):
    out = tmp_path / 'sheet.bmp'
    subprocess.run([sys.executable, SHEET, str(out)], check=True)
    data = out.read_bytes()
    assert data[:2] == b'BM'
    assert struct.unpack_from('<I', data, 2)[0] == len(data)
    assert struct.unpack_from('<ii', data, 18) == (6 * 120 + 5 * 2, 4 * 150 + 3 * 2)
