"""Player card renderer: a plain dict in, a 680x450 BMP and clickable hotspots out.

Standard library only. Nothing here knows about players, paths or routing: everything
drawn comes from the card dict, and hotspot paths are passed through unchanged.
"""
import os
import struct

W, H = 680, 450

GREEN = (11, 83, 7)
WHITE = (255, 255, 255)
YELLOW = (254, 254, 2)
TAN = (171, 155, 139)
LIGHT = (215, 207, 195)
DARK = (36, 32, 24)
DARK2 = (80, 72, 52)
GOLD = (207, 175, 139)
GRAY = (176, 176, 176)
BLACK = (0, 0, 0)


class FontError(Exception):
    pass


class Font:
    """One FNX font: height, first, count, widths, glyph bitmaps."""

    def __init__(self, ver, height, first, count, glyphs):
        self.ver = ver
        self.height = height
        self.first = first
        self.count = count
        self.glyphs = glyphs  # [(advance, [row bytes])]: ver 1 rows hold 0/1, ver 3 palette indexes

    def _index(self, ch):
        for code in (ord(ch), ord('?')):
            i = code - self.first
            if 0 <= i < self.count:
                return i
        return None

    def _advance(self, ch):
        i = self._index(ch)
        return 0 if i is None else self.glyphs[i][0]

    def width(self, text):
        return sum(self._advance(ch) for ch in text)


def _u16(data, off):
    if off + 2 > len(data):
        raise FontError('truncated')
    return struct.unpack_from('<H', data, off)[0]


def parse_fnx(data):
    data = bytes(data)
    if data[:4] != b'FNX:' or len(data) < 17:
        raise FontError('not an FNX font')
    ver = _u16(data, 4)
    if ver not in (1, 3):
        raise FontError('unsupported FNX version %d' % ver)
    height, first, count = data[7], data[9], data[10]
    tstart, wstart, dstart = _u16(data, 11), _u16(data, 13), _u16(data, 15)
    if tstart + 2 * count > len(data) or wstart + count > len(data):
        raise FontError('FNX tables run past the end')
    glyphs = []
    for i in range(count):
        width = data[wstart + i]
        stride = (width + 7) // 8 if ver == 1 else width
        off = dstart + _u16(data, tstart + 2 * i)
        if off + height * stride > len(data):
            raise FontError('glyph %d runs past the end' % i)
        rows = []
        for r in range(height):
            base = off + r * stride
            if ver == 1:
                line = data[base:base + stride]
                rows.append(bytes((line[x >> 3] >> (7 - (x & 7))) & 1 for x in range(width)))
            else:
                rows.append(data[base:base + width])
        glyphs.append((width, rows))
    return Font(ver, height, first, count, glyphs)


def parse_pal(data):
    data = bytes(data)
    if len(data) < 24 + 1024 or data[0:4] != b'RIFF' or data[8:16] != b'PAL data':
        raise FontError('not a BB0.PAL palette')
    if _u16(data, 22) != 256:
        raise FontError('palette count is not 256')
    return [tuple(data[o:o + 3]) for o in range(24, 24 + 1024, 4)]


class Fonts:
    def __init__(self, text, title, palette):
        self.text = text
        self.title = title
        self.palette = palette

    @classmethod
    def load(cls, game_dir):
        try:
            names = os.listdir(game_dir)
        except OSError as e:
            raise FontError('cannot list %s: %s' % (game_dir, e)) from e

        def read(want):
            for name in sorted(names):
                if name.lower() == want:
                    try:
                        with open(os.path.join(game_dir, name), 'rb') as f:
                            return f.read()
                    except OSError as e:
                        raise FontError('cannot read %s: %s' % (name, e)) from e
            raise FontError('%s not found in %s' % (want, game_dir))

        return cls(parse_fnx(read('4.fnx')), parse_fnx(read('5.fnx')), parse_pal(read('bb0.pal')))


def _fill(img, x, y, w, h, colour):
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    run = bytes(colour) * (x1 - x0)
    for yy in range(y0, y1):
        o = (yy * W + x0) * 3
        img[o:o + len(run)] = run


def _put(img, x, y, colour):
    if 0 <= x < W and 0 <= y < H:
        o = (y * W + x) * 3
        img[o:o + 3] = bytes(colour)


def _text(img, pal, font, s, x, y, colour, box):
    x0, y0, x1, y1 = box
    for ch in s:
        i = font._index(ch)
        if i is None:
            continue
        adv, rows = font.glyphs[i]
        for r, row in enumerate(rows):
            if not y0 <= y + r < y1:
                continue
            for c, v in enumerate(row):
                if v and x0 <= x + c < x1:
                    _put(img, x + c, y + r, colour if font.ver == 1 else pal[v])
        x += adv


def _fit(font, s, width):
    if font.width(s) <= width:
        return s
    n = total = 0
    for ch in s:
        adv = font._advance(ch)
        if total + adv > width:
            break
        total += adv
        n += 1
    return s[:max(0, n - 2)] + '..'


def _say(img, pal, font, s, x, y, colour, box, right=False):
    """Draw s fitted to box. x is the left edge, or the right edge when right. Returns the drawn width."""
    s = str(s)
    avail = x - box[0] if right else box[2] - x
    if avail <= 0:
        return 0
    s = _fit(font, s, avail)
    if right:
        x -= font.width(s)
    _text(img, pal, font, s, x, y, colour, box)
    return font.width(s)


def _vc(font, top, h):
    return top + (h - font.height) // 2


def _spot(hot, x, y, w, h, path):
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 > x0 and y1 > y0:
        hot.append((x0, y0, x1 - x0, y1 - y0, path))


def _mix(a, b, y):
    return tuple(a[i] + (b[i] - a[i]) * y // 32 for i in range(3))


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _bar_len(v):
    return round((min(80, max(20, v)) - 20) * 244 / 60)


def _picture(p):
    try:
        w, h, rgb = p
        if 0 < w and 0 < h and isinstance(rgb, (bytes, bytearray)) and len(rgb) == w * h * 3:
            return w, h, rgb
    except (TypeError, ValueError):
        pass
    return None


def _cell_text(cells, i):
    return str(cells[i]) if i < len(cells) else ''


def _overview(img, pal, tf, body):
    hot = []
    _fill(img, 12, 100, 128, 158, BLACK)
    _fill(img, 14, 102, 124, 154, LIGHT)
    _fill(img, 16, 104, 120, 150, DARK2)
    pic = _picture(body.get('portrait'))
    if pic:
        w, h, rgb = pic
        n = min(w, 120) * 3
        for y in range(min(h, 150)):
            start = ((104 + y) * W + 16) * 3
            img[start:start + n] = rgb[y * w * 3:y * w * 3 + n]
    else:
        s = _fit(tf, 'No picture', 120)
        _text(img, pal, tf, s, 16 + (120 - tf.width(s)) // 2, _vc(tf, 104, 150), GOLD, (16, 104, 136, 254))

    y = 266
    for label, value in body.get('facts', []):
        if y + 13 > 420:
            break
        _say(img, pal, tf, label, 12, y, YELLOW, (12, y, 82, y + 13))
        _say(img, pal, tf, value, 82, y, WHITE, (82, y, 150, y + 13))
        y += 13

    _fill(img, 160, 100, 511, 14, LIGHT)
    hy = _vc(tf, 100, 14)
    _say(img, pal, tf, 'Rating', 166, hy, BLACK, (166, 100, 330, 114))
    _say(img, pal, tf, 'Now', 366, hy, BLACK, (160, 100, 366, 114), right=True)
    _say(img, pal, tf, 'Peak', 406, hy, BLACK, (160, 100, 406, 114), right=True)
    _say(img, pal, tf, '20', 420, hy, BLACK, (420, 100, 664, 114))
    _say(img, pal, tf, '80', 664, hy, BLACK, (420, 100, 664, 114), right=True)

    t = 116
    tops = []
    for label, now, peak in body.get('ratings', []):
        if t + 15 > 420:
            break
        _fill(img, 160, t + 14, 511, 1, GRAY)
        _say(img, pal, tf, label, 166, _vc(tf, t, 14), YELLOW, (166, t, 330, t + 14))
        for v, x in ((now, 366), (peak, 406)):
            n = _num(v)
            _say(img, pal, tf, '-' if n is None else int(round(n)), x, _vc(tf, t, 14), WHITE,
                 (160, t, x, t + 14), right=True)
        ty = t + 3
        _fill(img, 420, ty, 244, 1, GRAY)
        _fill(img, 420, ty + 8, 244, 1, GRAY)
        _fill(img, 420, ty, 1, 9, GRAY)
        _fill(img, 663, ty, 1, 9, GRAY)
        now_n, peak_n = _num(now), _num(peak)
        if peak_n is not None:
            _fill(img, 420, ty + 1, _bar_len(peak_n), 7, DARK2)
        if now_n is not None:
            _fill(img, 420, ty + 2, _bar_len(now_n), 5, YELLOW)
        tops.append(t)
        t += 15

    y = tops[-1] + 18 if tops else 116
    for label, path in body.get('links', []):
        if y + 15 > 420:
            break
        w = _say(img, pal, tf, label, 166, y, WHITE, (166, y, 668, y + 13))
        if path is not None:        # a link is underlined and clickable; a None path is a plain status line
            _fill(img, 166, y + tf.height, w, 1, WHITE)
            _spot(hot, 166, y, w, 13, path)
        y += 15
    return hot


def _col_widths(tf, cols, rows):
    base = [max([tf.width(str(head))] + [tf.width(_cell_text(r.get('cells', []), i)) for r in rows])
            for i, head in enumerate(cols)]
    for pad in (10, 4):
        widths = [b + pad for b in base]
        if sum(widths) <= 656:
            return widths
    widths[0] = max(0, 656 - sum(widths[1:]))
    return widths


def _table(img, pal, tf, body):
    hot = []
    cols = body.get('columns', [])
    rows = body.get('rows', [])
    top = 98
    if body.get('caption'):
        _say(img, pal, tf, body['caption'], 12, 98, GOLD, (12, 98, 668, 112))
        top = 114
    widths = _col_widths(tf, cols, rows)
    lefts, x = [], 12
    for w in widths:
        lefts.append(x)
        x += w
    total = min(x, 668) - 12            # columns that still do not fit are cut at the table's right edge

    def cell(text, i, y, bh, colour, bold):
        left, w = lefts[i], widths[i]
        if left >= 668:
            return
        box = (left, y, min(left + w, 668), y + bh)
        ty = _vc(tf, y, 13)
        for dx in ((0, 1) if bold else (0,)):
            if i == 0:
                _say(img, pal, tf, text, left + 4 + dx, ty, colour, box)
            else:
                _say(img, pal, tf, text, left + w - 4 + dx, ty, colour, box, right=True)

    _fill(img, 12, top, total, 14, LIGHT)
    for i, head in enumerate(cols):
        cell(head, i, top, 14, BLACK, False)
    y = top + 14
    for row in rows:
        if y + 13 > 404:
            break
        colour = YELLOW if str(row.get('color', 'white')).lower() == 'yellow' else WHITE
        cells = row.get('cells', [])
        for i in range(len(widths)):
            cell(_cell_text(cells, i), i, y, 12, colour, bool(row.get('bold')))
        _fill(img, 12, y + 12, total, 1, GRAY)
        y += 13

    if body.get('note'):
        _say(img, pal, tf, body['note'], 12, 410, WHITE, (12, 410, 550, 428))
    if body.get('prev'):
        w = _say(img, pal, tf, '< Prev', 560, 410, YELLOW, (560, 410, 668, 428))
        _spot(hot, 560, 410, w, 13, body['prev'])
    if body.get('next'):
        w = _say(img, pal, tf, 'Next >', 668, 410, YELLOW, (560, 410, 668, 428), right=True)
        _spot(hot, 668 - w, 410, w, 13, body['next'])
    return hot


def _links(img, pal, tf, body):
    hot = []
    y = 98
    if body.get('caption'):
        _say(img, pal, tf, body['caption'], 12, 98, GOLD, (12, 98, 668, 114))
        y = 116
    for label, path in body.get('items', []):
        if y + 16 > 420:
            break
        if path is None:
            _say(img, pal, tf, label, 12, y, YELLOW, (12, y, 668, y + 16))
        else:
            w = _say(img, pal, tf, label, 12, y, WHITE, (12, y, 668, y + 13))
            _fill(img, 12, y + tf.height, w, 1, WHITE)
            _spot(hot, 12, y, w, 13, path)
        y += 16
    return hot


def render(card, fonts):
    img = bytearray(W * H * 3)
    tf, hf, pal = fonts.text, fonts.title, fonts.palette
    title, tabs, header, body = card['title'], card['tabs'], card['header'], card['body']

    for y in range(33):
        _fill(img, 0, y, W, 1, _mix(DARK, DARK2, y))
    _fill(img, 0, 33, W, 1, BLACK)
    _say(img, pal, hf, title, 12, _vc(hf, 0, 33), GOLD, (12, 0, 668, 33))
    if card.get('subtitle'):
        _say(img, pal, tf, card['subtitle'], 668, _vc(tf, 0, 33), GOLD, (12, 0, 668, 33), right=True)

    _fill(img, 0, 34, W, 21, TAN)
    _fill(img, 0, 55, W, 1, BLACK)
    hot = []
    x = 8
    for label, path, selected in tabs:
        label = str(label)
        tw = tf.width(label) + 24
        _fill(img, x, 37, tw, 19, BLACK)
        _fill(img, x + 1, 38, tw - 2, 17, LIGHT if selected else TAN)
        _text(img, pal, tf, label, x + 12, _vc(tf, 38, 17), BLACK if selected else DARK, (x + 1, 38, x + tw - 1, 55))
        if path and not selected:
            _spot(hot, x, 37, tw, 19, path)
        x += tw + 4

    _fill(img, 0, 56, W, 35, LIGHT)
    _fill(img, 0, 91, W, 1, BLACK)
    for y, line in zip((61, 76), header[:2]):
        _say(img, pal, tf, line, 12, y, BLACK, (12, 56, 668, 91))

    _fill(img, 0, 92, W, 336, GREEN)
    kind = body.get('kind')
    if kind == 'overview':
        hot += _overview(img, pal, tf, body)
    elif kind == 'table':
        hot += _table(img, pal, tf, body)
    elif kind == 'links':
        hot += _links(img, pal, tf, body)
    else:
        _say(img, pal, tf, 'Nothing to show.', 12, 98, WHITE, (12, 98, 668, 428))

    _fill(img, 0, 428, W, 1, BLACK)
    _fill(img, 0, 429, W, 21, TAN)
    box = (12, 429, 668, 450)
    _say(img, pal, tf, card.get('status_left', ''), 12, _vc(tf, 429, 21), DARK, box)
    _say(img, pal, tf, card.get('status_right', ''), 668, _vc(tf, 429, 21), DARK, box, right=True)
    return bmp24(W, H, bytes(img)), hot


def bmp24(w, h, rgb):
    row = w * 3
    if len(rgb) != w * h * 3:
        raise ValueError('rgb is %d bytes, want %d' % (len(rgb), w * h * 3))
    pad = b'\0' * (-row % 4)
    body = bytearray()
    for y in range(h - 1, -1, -1):
        line = rgb[y * row:(y + 1) * row]
        bgr = bytearray(row)
        bgr[0::3] = line[2::3]
        bgr[1::3] = line[1::3]
        bgr[2::3] = line[0::3]
        body += bgr + pad
    size = 54 + len(body)
    return (b'BM' + struct.pack('<IHHI', size, 0, 0, 54)
            + struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0)
            + bytes(body))
