"""Generated sepia baseball card portraits: a deterministic head and shoulders in ink outlines and hatch shading.

portrait(seed, ...) returns (W, H, rgb): rows top down, 3 bytes a pixel, every pixel one of SHADES steps of the sepia
ramp. The picture is drawn as shade levels on a W by H grid, back to front, then mapped through ramp(). Same inputs,
same bytes: random.Random(seed) is the only source of variety, and the shapes use integer tests and plain float
arithmetic (square roots are exact in IEEE, so there are no platform libm differences). Bad inputs fall back to their
defaults and never raise.
"""
import math
import random

W, H = 120, 150
SHADES = 16
DARK, LIGHT = (38, 30, 20), (238, 224, 196)
NEIGH = ((1, 0), (-1, 0), (0, 1), (0, -1))
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))   # ordered dither, thresholds (n + 0.5) / 16

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
    out = set()
    for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
        v = (y - cy) / ry
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            u = (x - cx) / rx
            if u * u + v * v <= 1:
                out.add((x, y))
    return out


def head(cx, cy, hw, hh, jaw):
    """Head pixels row by row: a round oval, or a lower half that is boxy ('square') or tapered ('narrow')."""
    out = set()
    for dy in range(-hh, hh + 1):
        t = dy / hh
        t2 = t * t
        if t > 0 and jaw == 'square':                  # half = (1 - t^4)^(1/4), by square roots: a boxy jaw
            half = 1.06 * math.sqrt(math.sqrt(max(0.0, 1 - t2 * t2)))
        else:
            half = math.sqrt(max(0.0, 1 - t2))
            if t > 0 and jaw == 'narrow':
                half *= 1 - 0.16 * t                   # tapers to a narrow chin
        w = int(hw * half)
        out.update((x, cy + dy) for x in range(cx - w, cx + w + 1))
    return out


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


def shoulders(bx, sw, nw):
    """The jersey: a trapezius curve from the neck base (y 97) out to the shoulder point (y 118), then down."""
    n = nw // 2 + 3                                    # the curve starts just outside the neck
    top = []
    for i in range(9):
        t = i / 8
        top.append((n + (sw - n) * t, 97 + 21 * (0.45 * t + 0.55 * t * t)))
    left = [(bx - x, y) for x, y in top]
    right = [(bx + x, y) for x, y in top]
    return polygon(left + [(bx - sw - 2, H + 1), (bx + sw + 2, H + 1)] + right[::-1])


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


def hair_mass(c, pts, face, base, streak):
    """A hair mass: base fill, every other row (y even) lighter, and a level 2 outline on its far edge."""
    c.paint(pts, base)
    c.paint({p for p in pts if p[1] % 2 == 0}, streak)
    c.paint({p for p in edge(pts) if any((p[0] + dx, p[1] + dy) not in pts and
             (p[0] + dx, p[1] + dy) not in face for dx, dy in NEIGH)}, 2)


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
    """Levels 13 down to 11 over the height, corners darkened up to 2 by a smooth oval, every 4th diagonal one darker.

    Each pixel is dithered between the two levels it falls between, so the steps have no edges to see.
    """
    px = []
    for y in range(H):
        base = 13 - 2 * y / (H - 1)
        dy = (y - 75) / 75
        for x in range(W):
            dx = (x - 60) / 60
            s = min(1.0, max(0.0, (dx * dx + dy * dy - 0.75) / 0.6))
            v = base - 2 * s * s * (3 - 2 * s)         # smoothstep: no ring edge
            lvl = math.floor(v + (BAYER[y % 4][x % 4] + 0.5) / 16)
            if (x + y + phase) % 4 == 0:
                lvl -= 1
            px.append(max(0, lvl))
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
    (head_w, head_h, hatch, mus, beard, mus_w, mouth_w, smile, eye_l, eye_r, side_r,
     jaw_v, nose_v, gap_v, ear_v, fringe_v, grey_v) = [rng.random() for _ in range(17)]

    turn = {'L': 3, 'R': -3, 'S': 0}[bats]           # the head and shoulders move this many px
    side = (1 if turn > 0 else -1) if turn else (1 if side_r < 0.5 else -1)   # the way the face points
    shade = -side                                    # the shadow falls away from the turn
    bx = 60 + turn
    k = (power - 20) / 60                            # 0 at power 20, 1 at 80
    sw = round(34 + 14 * k)                          # shoulder half-width
    nw = round(14 + 8 * k)                           # neck width
    cy = 65                                          # head centre
    hw = 17 + round(4 * (0.5 * k + 0.5 * head_w))    # head half-width, 17..21
    hh = 22 + int(4 * head_h)                        # head half-height, 22..25
    chin = cy + hh
    cap_base = cy - hh + 4                           # the cap's lower edge, just above the forehead
    jaw = ('narrow', 'round', 'square')[min(2, int(jaw_v * 3))]
    nose_len = 5 + int(5 * nose_v)                   # 5..9
    gap = 10 + int(4 * gap_v)                        # eyes 10..13 px apart
    ear_r = 3 + int(2 * ear_v)                       # ear half-width 3..4
    crown_h, brim = (12, 5) if era < 1920 else (15, 8) if era < 1970 else (17, 10)
    tall = era >= 1970
    p_mus = 0.35 if era < 1920 else 0.08 if era < 1970 else 0.45 if era < 1990 else 0.15 if era <= 2005 else 0.25
    p_beard = 0.0 if era < 1970 else 0.05 if era < 2000 else 0.3
    if age >= 44:                                    # hair greys from 38, greyer from 44
        hair, streak = 8, 6
    elif age >= 38:
        hair, streak = 7, 5
    else:
        hair, streak = 2, 2
    receded = age >= 44 and grey_v >= 0.4            # a receding hairline: no fringe, shorter sideburns
    fringe = None                                    # depth: about 30% wear one under the cap
    if fringe_v < 0.3 and not receded:
        fringe = 3 if age >= 44 and grey_v < 0.4 else 6   # from 44, some get a lighter, shorter one

    c = Canvas(_background(int(4 * hatch)))

    if speed >= 65:                                  # motion streaks behind the shoulders
        for y in (118, 126):
            c.paint(line(bx + shade * (sw + 3), y, bx + shade * (sw + 12), y - 2), 9)

    body = shoulders(bx, sw, nw)
    c.paint(body, 12)
    shadow_edge = bx + shade * sw
    c.paint({p for p in body if abs(p[0] - shadow_edge) <= 10 and (p[0] + p[1]) % 3 == 0}, 9)
    c.paint(edge(body), 1)
    if pitcher:                                      # sleeve stripe on the throwing arm's shoulder
        s = -1 if throws == 'R' else 1
        c.paint(thick(bx + s * (sw - 5), 114, bx + s * (sw - 11), 128, 3) & body, 4)

    face = head(bx, cy, hw, hh, jaw)
    inner = inset(face, 1)
    # hair: a tuft at each temple under the cap, over the ears' tops; the sideburns below are drawn on the face
    hair_mass(c, {p for p in ellipse(bx, cap_base + 5, hw + 2, 12) if p[1] > cap_base}, face, hair, streak)

    nx0, nx1 = bx - nw // 2, bx + (nw + 1) // 2
    c.paint({(x, y) for x in range(nx0, nx1) for y in range(cy, 97)}, 8)            # neck, to the jersey's neckline
    c.paint({(x, y) for x in range(nx0, nx1) for y in range(chin + 1, chin + 4)}, 6)   # shadow under the jaw
    c.paint({(x, y) for x in range(nx0, nx1) for y in range(chin + 1, 97)
             if (x - bx) * shade >= nw // 2 - 2}, 6)                                  # shadow side of the neck

    if era < 1915:                                   # fold-down collar: two triangles at the neck base
        for s in (-1, 1):
            tri = polygon([(bx + s, 97), (bx + s * (nw // 2 + 4), 97), (bx + 2 * s, 111)])
            c.paint(tri, 13)
            c.paint(edge(tri), 1)
    elif era < 1960:                                 # button front: a placket and two buttons
        c.paint(line(bx, 98, bx, H - 1), 3)
        for y in (118, 132):
            c.paint(ellipse(bx, y, 1, 1), 1)
    else:                                            # V-neck with piping
        for s in (-1, 1):
            c.paint(line(bx + s * (nw // 2), 98, bx, 110), 3)

    for ex in (bx - hw, bx + hw):
        if turn * (ex - bx) <= 0:                    # the far ear is hidden behind the head
            ear = ellipse(ex, cy + 1, ear_r, ear_r + 1)
            c.paint(ear, 9)
            c.paint(edge(ear), 1)

    c.paint(face, 10)
    c.paint({p for p in ellipse(bx + shade * (hw - 7), cy + 8, 4, 2) if p in face}, 9)   # cheek shadow, under the cheekbone
    c.paint({p for p in face - inset(face, 5) if (p[0] - bx) * shade > 0}, 8)           # jaw shadow, 4px inside outline
    c.paint({p for p in ellipse(bx + side * (hw * 2 // 5), cap_base + 6, 3, 1.5) if p in face and p[1] > cap_base}, 11)
    c.paint(edge(face), 1)

    eyes = ((bx - (gap + 1) // 2, eye_l), (bx + gap // 2, eye_r))
    for ex, r in eyes:
        if r < 0.5:
            c.paint(thick(ex - 1, cy - 1, ex + 1, cy - 1), 1)    # a short dash
        else:
            c.paint(ellipse(ex, cy - 1, 1, 1), 1)                # a dot
    brow = 1 + max(0, (age - 22) // 12)                          # thicker brows at older ages
    for ex, _ in eyes:
        c.paint(thick(ex - 3, 61, ex, 59, brow) | thick(ex, 59, ex + 3, 61, brow), 2)
    nx = bx + side
    nose_end = 66 + nose_len
    c.paint(line(nx, 67, nx, nose_end) | line(nx - 1, nose_end + 1, nx + 1, nose_end + 1), 4)
    if age >= 32:                                                # age lines
        for i in range(min(3, max(1, (age - 30) // 4))):
            y = cap_base + 2 + 3 * i
            c.paint(thick(bx - 7, y, bx + 7, y), 6)
        for s in (-1, 1):
            c.paint(line(bx + 3 * s, 74, bx + 5 * s, 79), 6)

    if mus < p_mus:
        c.paint(ellipse(bx, 77.5, 4.5 + 2 * mus_w, 1.2), 2)
    if beard < p_beard:
        c.paint({p for p in inner if p[1] >= 82 and (p[0] + p[1]) % 2 == 0}, 4)
    m = 3 + int(3 * mouth_w)                                     # mouth 7..11 px wide
    d = 2 if smile >= 0.5 else 1                                 # the corners lift: a slight smile
    c.paint(line(bx - m, 80 - d, bx, 81) | line(bx, 81, bx + m, 80 - d), 3)

    sb_end = 68 if receded else 70                   # the receding hairline wears the sideburns 2px shorter
    hair_mass(c, {p for p in inner if abs(p[0] - bx) >= hw - 2 and cap_base < p[1] <= sb_end},
              face, hair, streak)                    # sideburns to the lobe
    if fringe:
        hair_mass(c, {p for p in inner if cap_base < p[1] <= cap_base + fringe - 3 * abs(p[0] - bx) // hw},
                  face, hair, streak)

    cap_rx = hw + 1
    crown = {p for p in ellipse(bx, cap_base, cap_rx, crown_h) if p[1] <= cap_base}
    c.paint(crown, 3)
    c.paint(edge(crown), 0)
    if tall:                                                     # two-tone seam
        seam = ellipse(bx, cap_base, cap_rx * 0.6, crown_h * 0.6)
        c.paint({p for p in edge(seam) if p in crown and p[1] <= cap_base - 2}, 5)
    c.paint(ellipse(bx, cap_base - crown_h + 1, 1, 1), 1)        # button
    x0, x1 = bx + side * (hw - 3), bx + side * (hw + brim)       # the brim points toward the turn
    by = cap_base - 1
    if tall:                                                     # long curved brim
        bri = polygon([(x0, by), (x1, by + 1), (x1, by + 3), (bx + side * (hw + brim // 2), by + 4), (x0, by + 3)])
    else:
        bri = polygon([(x0, by), (x1, by), (x1, by + 3), (x0, by + 3)])
    c.paint(bri, 3)
    c.paint(edge(bri), 0)
    glyph = FONT.get(letter)
    if glyph:                                                    # the team letter, centred on the crown front
        y0 = cap_base - crown_h // 2 - 3
        c.paint({(bx - 2 + col, y0 + r) for r, row in enumerate(glyph.split())
                 for col, ink in enumerate(row) if ink == '1'}, 13)

    out = bytearray()
    for level in c.px:
        out.extend(PAL[level])
    return W, H, bytes(out)
