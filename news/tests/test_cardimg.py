"""cardimg on synthetic fonts and palettes: FNX/PAL parsing, BMP output, the card layout and hotspots."""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cardimg  # noqa: E402
from cardimg import (BLACK, DARK, DARK2, GOLD, GRAY, GREEN, LIGHT, TAN, WHITE, YELLOW,  # noqa: E402
                     FontError, Fonts, bmp24, parse_fnx, parse_pal, render)


def build_fnx(ver, height, first, glyphs):
    """glyphs: [(advance, stored bytes for all height rows)]. Offsets are relative to dstart."""
    count = len(glyphs)
    tstart = 17
    wstart = tstart + 2 * count
    dstart = wstart + count
    offs, data = bytearray(), bytearray()
    for _, raw in glyphs:
        offs += struct.pack('<H', len(data))
        data += raw
    head = b'FNX:' + struct.pack('<HBBBBBHHH', ver, 0, height, 0, first, count, tstart, wstart, dstart)
    return head + bytes(offs) + bytes(w for w, _ in glyphs) + bytes(data)


def text_font():
    # ver 1: a 4x7 block at the top-left of every glyph, space blank; advance 6
    glyphs = [(6, bytes(0 if (r >= 7 or 0x20 + i == 0x20) else 0xF0 for r in range(11))) for i in range(96)]
    return build_fnx(1, 11, 0x20, glyphs)


def title_font():
    # ver 3: index 0xCE in a 6x12 block at the top-left, space blank; advance 10
    block = b''.join(bytes([0xCE] * 6 + [0] * 4) if r < 12 else bytes(10) for r in range(20))
    glyphs = [(10, bytes(200) if i == 0 else block) for i in range(95)]
    return build_fnx(3, 20, 0x20, glyphs)


def pal_entry(i):
    r, g, b = GOLD if i == 0xCE else (i, 255 - i, i // 2)
    return bytes((r, g, b, 0))


def build_pal(count=256):
    body = b''.join(pal_entry(i) for i in range(256))
    rest = b'PAL data' + struct.pack('<IHH', 4 + len(body), 0x0300, count) + body
    return b'RIFF' + struct.pack('<I', len(rest)) + rest


def read_bmp(data):
    assert data[:2] == b'BM'
    off = struct.unpack_from('<I', data, 10)[0]
    w, h = struct.unpack_from('<ii', data, 18)
    stride = (w * 3 + 3) // 4 * 4

    def at(x, y):
        o = off + (h - 1 - y) * stride + x * 3
        b, g, r = data[o:o + 3]
        return (r, g, b)

    return w, h, at


@pytest.fixture
def game(tmp_path):
    (tmp_path / '4.fnx').write_bytes(text_font())
    (tmp_path / '5.FNX').write_bytes(title_font())
    (tmp_path / 'bb0.pal').write_bytes(build_pal())
    return str(tmp_path)


@pytest.fixture
def fonts(game):
    return Fonts.load(game)


def draw(fonts, **kw):
    card = {'title': 'Player', 'tabs': [], 'header': [], 'body': {'kind': 'none'}}
    card.update(kw)
    bmp, hot = render(card, fonts)
    w, h, at = read_bmp(bmp)
    return w, h, at, hot


# FNX and PAL parsing

def test_fnx_metrics_and_unknown_chars(fonts):
    assert fonts.text.height == 11 and fonts.text.ver == 1
    assert fonts.title.height == 20 and fonts.title.ver == 3
    assert fonts.text.width('AB') == 12
    assert fonts.title.width('ABC') == 30
    assert fonts.text.width('é') == 6  # outside the font: drawn as '?'
    lone = parse_fnx(build_fnx(1, 11, 0x41, [(6, bytes(11))]))  # 'A' only, no '?'
    assert lone.width('z') == 0


def test_bad_fnx_raises_font_error():
    good = text_font()
    bad_magic = b'FNXX' + good[4:]
    bad_ver = good[:4] + struct.pack('<H', 2) + good[6:]
    for data in (bad_magic, bad_ver, good[:-1], b'FNX:\x01\x00'):
        with pytest.raises(FontError):
            parse_fnx(data)


def test_palette_parse_and_errors():
    pal = parse_pal(build_pal())
    assert len(pal) == 256
    assert pal[0xCE] == GOLD and pal[3] == (3, 252, 1)
    with pytest.raises(FontError):
        parse_pal(build_pal()[:-1])
    with pytest.raises(FontError):
        parse_pal(build_pal(count=255))
    with pytest.raises(FontError):
        parse_pal(b'RIFX' + build_pal()[4:])


def test_fonts_load_case_insensitive_and_missing(tmp_path):
    (tmp_path / '4.FNX').write_bytes(text_font())
    (tmp_path / '5.fnx').write_bytes(title_font())
    (tmp_path / 'BB0.PAL').write_bytes(build_pal())
    loaded = Fonts.load(str(tmp_path))
    assert loaded.text.ver == 1 and loaded.title.ver == 3 and len(loaded.palette) == 256
    (tmp_path / 'BB0.PAL').unlink()
    with pytest.raises(FontError):
        Fonts.load(str(tmp_path))
    with pytest.raises(FontError):
        Fonts.load(str(tmp_path / 'nope'))


# BMP

def test_bmp24_header_bgr_and_padding():
    red, blue = bytes((255, 0, 0)), bytes((0, 0, 255))
    data = bmp24(3, 2, red * 3 + blue * 3)  # top row red, bottom row blue
    assert data[:2] == b'BM'
    size, _, _, off = struct.unpack_from('<IHHI', data, 2)
    assert off == 54 and size == len(data) == 54 + 2 * 12
    assert struct.unpack_from('<iiHHI', data, 18) == (3, 2, 1, 24, 0)
    assert data[54:57] == b'\xff\x00\x00'   # first file row is the bottom row: blue as BGR
    assert data[63:66] == bytes(3)          # 9 data bytes, 3 pad bytes
    assert data[66:69] == b'\x00\x00\xff'   # second file row: red as BGR


def test_bmp24_rejects_wrong_length():
    with pytest.raises(ValueError):
        bmp24(3, 2, bytes(17))


# Render

def test_render_size_and_bands(fonts):
    w, h, at, hot = draw(fonts)
    assert (w, h) == (680, 450)
    assert at(0, 0) == DARK and at(0, 32) == DARK2 and at(0, 33) == BLACK
    assert at(0, 34) == TAN and at(0, 55) == BLACK
    assert at(0, 56) == LIGHT and at(0, 91) == BLACK
    assert at(600, 92) == GREEN and at(600, 427) == GREEN
    assert at(0, 428) == BLACK and at(0, 429) == TAN and at(679, 449) == TAN
    assert hot == []


def test_title_glyph_uses_palette(fonts):
    fonts.palette[0xCE] = (1, 2, 3)
    _, _, at, _ = draw(fonts, title='A')
    assert at(12, 6) == (1, 2, 3)     # 6x12 block at x 12..17, rows 6..17
    assert at(17, 17) == (1, 2, 3)
    assert at(18, 6) != (1, 2, 3)


def test_subtitle_gold_and_right_aligned(fonts):
    _, _, at, _ = draw(fonts, subtitle='X')
    assert at(662, 11) == GOLD        # 'X' ink at x 662..665, rows 11..17
    assert at(666, 11) != GOLD


def test_tabs_and_hotspots(fonts):
    tabs = [('Roster', '/r', False), ('Stats', '/s', True), ('Bio', '', False), ('Pics', None, False)]
    _, _, at, hot = draw(fonts, tabs=tabs)
    assert hot == [(8, 37, 60, 19, '/r')]   # selected tab, empty path and None path give none
    assert at(8, 37) == BLACK and at(9, 40) == TAN
    assert at(74, 40) == LIGHT              # selected tab interior, x 72..125


def test_header_and_status_lines(fonts):
    _, _, at, _ = draw(fonts, header=['Line one', 'Line two', 'Three'], status_left='L', status_right='R')
    assert at(12, 61) == BLACK and at(12, 76) == BLACK
    assert at(12, 434) == DARK and at(662, 434) == DARK


def test_ratings_bar_lengths(fonts):
    ratings = [('A', 20, None), ('B', 50, None), ('C', 80, None), ('D', None, None),
               ('E', 95, None), ('F', None, 50)]
    _, _, at, _ = draw(fonts, body={'kind': 'overview', 'ratings': ratings})

    def run(y, colour):
        n = 0
        while n < 244 and at(420 + n, y) == colour:
            n += 1
        return n

    mid = [116 + 15 * k + 7 for k in range(6)]  # middle of each track
    assert [run(y, YELLOW) for y in mid[:5]] == [0, 122, 244, 0, 244]
    assert run(mid[5], DARK2) == 122


def test_portrait_top_left_at_16_104(fonts):
    rgb = bytes((1, 2, 3)) + bytes((4, 5, 6)) + bytes((7, 8, 9)) + bytes((10, 11, 12))
    _, _, at, _ = draw(fonts, body={'kind': 'overview', 'portrait': (2, 2, rgb)})
    assert at(16, 104) == (1, 2, 3)
    assert at(17, 104) == (4, 5, 6)
    assert at(16, 105) == (7, 8, 9)
    assert at(12, 100) == BLACK and at(14, 102) == LIGHT


def test_no_portrait_fills_dark2_and_says_so(fonts):
    _, _, at, _ = draw(fonts, body={'kind': 'overview'})
    assert at(16, 104) == DARK2
    assert any(at(x, y) == GOLD for x in range(16, 136) for y in range(104, 254))


SHRINK = {'kind': 'table', 'columns': ['A' * 45, 'B' * 40, 'C' * 20],
          'rows': [{'cells': ['x' * 10, 'y' * 10, 'z' * 5]}]}
CUT = {'kind': 'table', 'columns': ['A' * 60, 'B' * 40, 'C' * 30], 'caption': 'cap',
       'rows': [{'cells': ['q' * 60, 'r' * 40, 's' * 30], 'color': 'yellow'}]}


@pytest.mark.parametrize('body, total, hy', [(SHRINK, 642, 100), (CUT, 656, 116)])
def test_table_fits_668(fonts, body, total, hy):
    _, _, at, _ = draw(fonts, body=body)
    assert at(12 + total - 1, hy) == LIGHT and at(12 + total, hy) == GREEN
    for y in range(92, 428):
        for x in list(range(0, 12)) + list(range(668, 680)):
            assert at(x, y) == GREEN, (x, y)


def test_table_rows_stop_before_404(fonts):
    rows = [{'cells': ['r%d' % k]} for k in range(30)]
    _, _, at, _ = draw(fonts, body={'kind': 'table', 'columns': ['Year'], 'rows': rows})
    assert at(12, 112 + 13 * 21 + 12) == GRAY   # row 21: 385..397, ends by 404
    assert at(12, 112 + 13 * 22 + 12) == GREEN  # row 22 would end at 411


def test_table_prev_next_hotspots(fonts):
    _, _, _, hot = draw(fonts, body={'kind': 'table', 'columns': [], 'rows': [], 'prev': '/p', 'next': '/n'})
    assert hot == [(560, 410, 36, 13, '/p'), (632, 410, 36, 13, '/n')]


def test_links_hotspots_and_y420_cutoff(fonts):
    items = [('Heading', None)] + [('Link %d' % k, '/l%d' % k) for k in range(25)]
    _, _, at, hot = draw(fonts, body={'kind': 'links', 'items': items})
    assert len(hot) == 19                       # items start at 98 step 16; the 20th line would end at 436
    assert hot[0] == (12, 114, 36, 13, '/l0')
    assert hot[-1] == (12, 402, 42, 13, '/l18')  # 'Link 18' is seven characters
    assert at(12, 125) == WHITE                 # underline one row under the text
    assert at(12, 418) == GREEN                 # the next item is not drawn


def test_fit_cuts_to_whole_chars_with_dots(fonts):
    assert cardimg._fit(fonts.text, 'x' * 120, 538) == 'x' * 87 + '..'
    assert cardimg._fit(fonts.text, 'short', 538) == 'short'


def test_unknown_kind_says_nothing_to_show(fonts):
    _, _, at, hot = draw(fonts, body={'kind': 'mystery'})
    assert at(12, 98) == WHITE and at(300, 300) == GREEN
    assert hot == []


def test_missing_keys_and_odd_values(fonts):
    with pytest.raises(KeyError):
        render({'title': 'x', 'tabs': [], 'header': []}, fonts)
    card = {'title': 5, 'tabs': [(None, None, 0)], 'header': [7],
            'body': {'kind': 'overview', 'ratings': [('r', 'abc', 2.5)], 'facts': [(1, None)],
                     'portrait': 'junk'}}
    bmp, hot = render(card, fonts)
    assert bmp[:2] == b'BM' and hot == []



def test_table_too_wide_even_after_the_cut_stays_inside_the_body(fonts):
    """Fifty columns cannot fit even with column 0 cut to nothing: no body pixel outside x 12..668 changes."""
    body = {'kind': 'table', 'columns': ['C%d' % i for i in range(50)], 'rows': [{'cells': ['x'] * 50}]}
    _, _, at, _ = draw(fonts, body=body)
    for y in range(92, 428):
        for x in list(range(0, 12)) + list(range(669, 680)):
            assert at(x, y) == cardimg.GREEN, (x, y)
