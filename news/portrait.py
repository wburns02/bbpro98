"""Generated sepia baseball card portraits: a deterministic head and shoulders in ink outlines and hatch shading.

portrait(seed, ...) returns (W, H, rgb): rows top down, 3 bytes a pixel, every pixel one of SHADES steps of the sepia
ramp. The picture is drawn as shade levels on a W by H grid, back to front, then mapped through ramp(). Same inputs,
same bytes: random.Random(seed) is the only source of variety, and the shapes use integer tests and plain float
arithmetic (no trig, so no platform libm differences). Bad inputs fall back to their defaults and never raise.
"""
import math
import random

W, H = 120, 150
SHADES = 16
DARK, LIGHT = (38, 30, 20), (238, 224, 196)
NEIGH = ((1, 0), (-1, 0), (0, 1), (0, -1))

# 5x7 glyphs for A-Z and 0-9, rows top down, '1' is ink
FONT = {
    'A': '01110 10001 10001 11111 10001 10001 10001',
    'B': '11110 10001 10001 11110 10001 10001 11110',
    'C': '01110 10001 10000 10000 10000 10001 01110',
    'D': '11110 10001 10001 10001 10001 10001 11110',
    'E': '11111 10000 10000 11110 10000 10000 11111',
    'F': '11111 10000 10000 11110 10000 10000 10000',
    'G': '01110 10001 10000 10111 10001 10001 01111',
    'H': '10001 10001 10001 11111 10001 10001 10001',
    'I': '01110 00100 00100 00100 00100 00100 01110',
    'J': '00111 00010 00010 00010 00010 10010 01100',
    'K': '10001 10010 10100 11000 10100 10010 10001',
    'L': '10000 10000 10000 10000 10000 10000 11111',
    'M': '10001 11011 10101 10101 10001 10001 10001',
    'N': '10001 10001 11001 10101 10011 10001 10001',
    'O': '01110 10001 10001 10001 10001 10001 01110',
    'P': '11110 10001 10001 11110 10000 10000 10000',
    'Q': '01110 10001 10001 10001 10101 10010 01101',
    'R': '11110 10001 10001 11110 10100 10010 10001',
    'S': '01111 10000 10000 01110 00001 00001 11110',
    'T': '11111 00100 00100 00100 00100 00100 00100',
    'U': '10001 10001 10001 10001 10001 10001 01110',
    'V': '10001 10001 10001 10001 10001 01010 00100',
    'W': '10001 10001 10001 10101 10101 10101 01010',
    'X': '10001 10001 01010 00100 01010 10001 10001',
    'Y': '10001 10001 10001 01010 00100 00100 00100',
    'Z': '11111 00001 00010 00100 01000 10000 11111',
    '0': '01110 10001 10011 10101 11001 10001 01110',
    '1': '00100 01100 00100 00100 00100 00100 01110',
    '2': '01110 10001 00001 00010 00100 01000 11111',
    '3': '11111 00010 00100 00010 00001 10001 01110',
    '4': '00010 00110 01010 10010 11111 00010 00010',
    '5': '11111 10000 11110 00001 00001 10001 01110',
    '6': '00110 01000 10000 11110 10001 10001 01110',
    '7': '11111 00001 00010 00100 01000 01000 01000',
    '8': '01110 10001 10001 01110 10001 10001 01110',
    '9': '01110 10001 10001 01111 00001 00010 01100',
}


def ramp(t):
    """Sepia colour for t in 0..1 (0 darkest, 1 lightest), clamped."""
    t = min(1.0, max(0.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(DARK, LIGHT))


PAL = tuple(ramp(k / (SHADES - 1)) for k in range(SHADES))


def ellipse(cx, cy, rx, ry):
    """Pixels whose centres lie inside an ellipse centred on pixel (cx, cy)."""
    return {(x, y)
            for y in range(int(cy - ry) - 1, int(cy + ry) + 2)
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2)
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1}


def polygon(pts):
    """Pixels inside a polygon: scanline fill, even-odd, sampled at pixel centres."""
    out = set()
    for y in range(math.floor(min(p[1] for p in pts)), math.ceil(max(p[1] for p in pts)) + 1):
        xs = []
        for (x0, y0), (x1, y1) in zip(pts, pts[-1:] + pts[:-1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            out.update((x, y) for x in range(math.ceil(a), math.floor(b) + 1))
    return out


def line(x0, y0, x1, y1):
    """Bresenham pixels from (x0, y0) to (x1, y1), both ends in."""
    pts = set()
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.add((x0, y0))
        if (x0, y0) == (x1, y1):
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def thick(x0, y0, x1, y1, w=1):
    """A line w pixels wide: a square brush stamped along the Bresenham line."""
    lo = -(w // 2)
    return {(x + dx, y + dy) for x, y in line(x0, y0, x1, y1)
            for dx in range(lo, lo + w) for dy in range(lo, lo + w)}


def inset(pts, n=1):
    """The shape with its outline stripped n times."""
    for _ in range(n):
        pts = {(x, y) for x, y in pts if all((x + dx, y + dy) in pts for dx, dy in NEIGH)}
    return pts


def edge(pts):
    """The outline of a shape: its pixels with a 4-neighbour outside it."""
    return pts - inset(pts)


class Canvas:
    """A W by H grid of shade levels. Shapes are pixel sets, painted in the order they are drawn."""

    def __init__(self, px):
        self.px = px

    def paint(self, pts, level):
        for x, y in pts:
            if 0 <= x < W and 0 <= y < H:
                self.px[y * W + x] = level


def _background(phase):
    """Levels 13 down to 11 over the height, corners darkened up to 2 by an oval, every 4th diagonal one darker."""
    px = []
    for y in range(H):
        base = 13 - round(2 * y / (H - 1))
        for x in range(W):
            d2 = ((x - 60) / 60) ** 2 + ((y - 75) / 75) ** 2
            dark = min(2, max(0, int((d2 - 0.9) * 3)))
            if (x + y + phase) % 4 == 0:
                dark += 1
            px.append(max(0, base - dark))
    return px


def _int(v, default, lo, hi):
    """v as an int clamped to lo..hi; default for None or anything that is not a number."""
    if v is None:
        return default
    try:
        return min(hi, max(lo, int(v)))
    except (TypeError, ValueError, OverflowError):
        return default


def portrait(seed, age=28, pos='', power=None, speed=None, bats='R', throws='R', era=1998, letter=''):
    """(W, H, rgb bytes): top-down rows, 3 bytes per pixel, len == W*H*3.

    Pitchers ('P') get a sleeve stripe on the throwing-arm shoulder: throws 'R' puts it on the viewer's left.
    letter is one character drawn on the cap if it is A-Z or 0-9.
    """
    try:
        seed = int(seed) & 0xFFFFFFFF
    except (TypeError, ValueError, OverflowError):
        seed = 0
    age = _int(age, 28, 16, 50)
    power = _int(power, 50, 20, 80)
    speed = _int(speed, 50, 20, 80)
    bats = bats if bats in ('L', 'R', 'S') else 'R'
    throws = 'L' if throws == 'L' else 'R'
    era = _int(era, 1998, 1870, 2030)
    letter = letter[:1] if isinstance(letter, str) else ''
    pitcher = pos == 'P'

    # every random draw happens here, in this order, so each input moves only what it should
    rng = random.Random(seed)
    head_w, head_h, hatch, mus, beard, mus_w, mouth_w, smile, eye_l, eye_r, side_r = [rng.random() for _ in range(11)]

    turn = {'L': 3, 'R': -3, 'S': 0}[bats]          # the head and shoulders move this many px
    side = (1 if turn > 0 else -1) if turn else (1 if side_r < 0.5 else -1)
    shade = -side                                   # the shadow falls away from the turn
    bx = 60 + turn
    k = (power - 20) / 60                           # 0 at power 20, 1 at 80
    sw = round(34 + 14 * k)                         # shoulder half-width
    nw = round(14 + 8 * k)                          # neck width
    hw = 17 + round(4 * (0.5 * k + 0.5 * head_w))   # head half-width, 17..21
    hh = 22 + int(4 * head_h)                       # head half-height, 22..25
    cap_base = 66 - hh + 4                          # the cap's lower edge, just above the forehead
    chin = 66 + hh
    crown_h, brim = (12, 5) if era < 1920 else (15, 8) if era < 1970 else (17, 10)
    tall = era >= 1970
    p_mus = 0.35 if era < 1920 else 0.08 if era < 1970 else 0.45 if era < 1990 else 0.15 if era <= 2005 else 0.25
    p_beard = 0.0 if era < 1970 else 0.05 if era < 2000 else 0.3

    c = Canvas(_background(int(4 * hatch)))

    if speed >= 65:                                 # motion streaks behind the shoulders
        for y in (118, 126):
            c.paint(line(bx + shade * (sw + 3), y, bx + shade * (sw + 12), y - 2), 9)

    body = ellipse(bx, 116, sw, 8) | polygon([(bx - sw, 116), (bx + sw, 116),
                                              (bx + sw + 4, H + 1), (bx - sw - 4, H + 1)])
    c.paint(body, 12)
    shadow_edge = bx + shade * sw
    c.paint({p for p in body if abs(p[0] - shadow_edge) <= 10 and (p[0] + p[1]) % 3 == 0}, 9)
    c.paint(edge(body), 1)
    if pitcher:                                     # sleeve stripe on the throwing arm's shoulder
        s = -1 if throws == 'R' else 1
        c.paint(thick(bx + s * (sw - 5), 114, bx + s * (sw - 11), 128, 3) & body, 4)

    nx0, nx1 = bx - nw // 2, bx + (nw + 1) // 2
    c.paint({(x, y) for x in range(nx0, nx1) for y in range(80, 113)}, 8)
    c.paint({(x, y) for x in range(nx0, nx1) for y in range(chin + 1, chin + 5)}, 6)   # shadow under the jaw

    if era < 1915:                                  # fold-down collar: two triangles
        for s in (-1, 1):
            tri = polygon([(bx + s, 107), (bx + s * (nw // 2 + 8), 110), (bx + 2 * s, 118)])
            c.paint(tri, 13)
            c.paint(edge(tri), 1)
    elif era < 1960:                                # button front: a placket and two buttons
        c.paint(line(bx, 112, bx, H - 1), 3)
        for y in (122, 134):
            c.paint(ellipse(bx, y, 1, 1), 1)
    else:                                           # V-neck with piping
        for s in (-1, 1):
            c.paint(line(bx + s * (nw // 2 + 2), 113, bx, 122), 3)

    for ex in (bx - hw, bx + hw):
        if turn * (ex - bx) <= 0:                   # the far ear is hidden behind the head
            ear = ellipse(ex, 66, 3, 4)
            c.paint(ear, 9)
            c.paint(edge(ear), 1)

    head = ellipse(bx, 66, hw, hh)
    c.paint(head, 10)
    c.paint({p for p in head - inset(head, 5) if (p[0] - bx) * shade > 0}, 8)   # shadow band, 4px inside the outline
    c.paint(edge(head), 1)

    eyes = ((bx - 6, eye_l), (bx + 5, eye_r))
    for ex, r in eyes:
        if r < 0.5:
            c.paint(thick(ex - 1, 64, ex + 1, 64), 1)   # a short dash
        else:
            c.paint(ellipse(ex, 64, 1, 1), 1)           # a dot
    brow = 1 + max(0, (age - 22) // 8)                  # thicker brows at older ages
    for ex, _ in eyes:
        c.paint(thick(ex - 3, 61, ex, 59, brow) | thick(ex, 59, ex + 3, 61, brow), 2)
    nx = bx + side
    c.paint(line(nx, 67, nx, 72) | line(nx - 1, 73, nx + 1, 73), 4)
    if age >= 32:                                       # age lines
        for i in range(min(3, max(1, (age - 30) // 4))):
            y = cap_base + 2 + 3 * i
            c.paint(thick(bx - 7, y, bx + 7, y), 6)
        for s in (-1, 1):
            c.paint(line(bx + 3 * s, 74, bx + 5 * s, 79), 6)

    if mus < p_mus:
        c.paint(ellipse(bx, 76, 4.5 + 2 * mus_w, 2), 2)
    if beard < p_beard:
        c.paint({p for p in inset(head, 1) if p[1] >= 82 and (p[0] + p[1]) % 2 == 0}, 4)
    m = 3 + int(3 * mouth_w)                            # mouth 7..11 px wide
    d = 2 if smile >= 0.5 else 1                        # the corners lift: a slight smile
    c.paint(line(bx - m, 80 - d, bx, 81) | line(bx, 81, bx + m, 80 - d), 3)

    temple = 2 if age < 38 else 12                      # sideburns, grey from 38
    c.paint({p for p in inset(head, 1) if abs(p[0] - bx) >= hw - 3 and cap_base < p[1] <= 60}, temple)

    cap_rx = hw + 1
    crown = {p for p in ellipse(bx, cap_base, cap_rx, crown_h) if p[1] <= cap_base}
    c.paint(crown, 3)
    c.paint(edge(crown), 0)
    if tall:                                            # two-tone seam
        seam = ellipse(bx, cap_base, cap_rx * 0.6, crown_h * 0.6)
        c.paint({p for p in edge(seam) if p in crown and p[1] <= cap_base - 2}, 5)
    c.paint(ellipse(bx, cap_base - crown_h + 1, 1, 1), 1)            # button
    x0, x1 = bx + side * (hw - 3), bx + side * (hw + brim)           # the brim points toward the turn
    by = cap_base - 1
    if tall:                                            # long curved brim
        bri = polygon([(x0, by), (x1, by + 1), (x1, by + 3), (bx + side * (hw + brim // 2), by + 4), (x0, by + 3)])
    else:
        bri = polygon([(x0, by), (x1, by), (x1, by + 3), (x0, by + 3)])
    c.paint(bri, 3)
    c.paint(edge(bri), 0)
    glyph = FONT.get(letter)
    if glyph:                                           # the team letter, centred on the crown front
        y0 = cap_base - crown_h // 2 - 3
        c.paint({(bx - 2 + col, y0 + r) for r, row in enumerate(glyph.split())
                 for col, ink in enumerate(row) if ink == '1'}, 13)

    out = bytearray()
    for level in c.px:
        out.extend(PAL[level])
    return W, H, bytes(out)
