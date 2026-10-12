"""Contact sheet for a person to look at: 24 portraits in a 6 by 4 grid with 2 px gaps, as a 24-bit BMP.

    python3 news/tests/portrait_sheet.py OUT.bmp

Not a test. It writes OUT.bmp and nothing else.
"""
import os
import struct
import sys

sys.dont_write_bytecode = True                  # no __pycache__ from a picture script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import portrait  # noqa: E402

COLS, ROWS, GAP = 6, 4, 2
SETS = [
    # era 1890..2024 x age 19..41 cover all 24 cells; the rest vary position, bats, power, speed and letter
    dict(seed=1000, era=1890, age=19, pos='P', power=20, speed=30, bats='L', throws='L', letter='N'),
    dict(seed=1001, era=1925, age=19, pos='SS', power=50, speed=75, bats='R', throws='R', letter='B'),
    dict(seed=1002, era=1955, age=19, pos='C', power=80, speed=30, bats='S', throws='R', letter='C'),
    dict(seed=1003, era=1978, age=19, pos='1B', power=20, speed=75, bats='L', throws='R', letter=''),
    dict(seed=1004, era=1998, age=19, pos='P', power=50, speed=30, bats='R', throws='L', letter='N'),
    dict(seed=1005, era=2024, age=19, pos='CF', power=80, speed=75, bats='S', throws='R', letter='B'),
    dict(seed=1006, era=1890, age=27, pos='2B', power=80, speed=30, bats='R', throws='R', letter='C'),
    dict(seed=1007, era=1925, age=27, pos='P', power=20, speed=75, bats='S', throws='L', letter=''),
    dict(seed=1008, era=1955, age=27, pos='LF', power=50, speed=30, bats='L', throws='R', letter='N'),
    dict(seed=1009, era=1978, age=27, pos='3B', power=80, speed=75, bats='R', throws='R', letter='B'),
    dict(seed=1010, era=1998, age=27, pos='P', power=50, speed=30, bats='L', throws='R', letter='C'),
    dict(seed=1011, era=2024, age=27, pos='RF', power=20, speed=75, bats='S', throws='R', letter=''),
    dict(seed=1012, era=1890, age=34, pos='DH', power=80, speed=30, bats='R', throws='R', letter='N'),
    dict(seed=1013, era=1925, age=34, pos='P', power=20, speed=30, bats='R', throws='L', letter='B'),
    dict(seed=1014, era=1955, age=34, pos='CF', power=50, speed=75, bats='L', throws='R', letter='C'),
    dict(seed=1015, era=1978, age=34, pos='C', power=80, speed=75, bats='R', throws='R', letter=''),
    dict(seed=1016, era=1998, age=34, pos='SS', power=20, speed=30, bats='S', throws='R', letter='N'),
    dict(seed=1017, era=2024, age=34, pos='P', power=50, speed=75, bats='L', throws='L', letter='B'),
    dict(seed=1018, era=1890, age=41, pos='1B', power=80, speed=30, bats='L', throws='R', letter='C'),
    dict(seed=1019, era=1925, age=41, pos='2B', power=20, speed=75, bats='R', throws='R', letter=''),
    dict(seed=1020, era=1955, age=41, pos='P', power=80, speed=30, bats='S', throws='R', letter='N'),
    dict(seed=1021, era=1978, age=41, pos='LF', power=50, speed=30, bats='R', throws='R', letter='B'),
    dict(seed=1022, era=1998, age=41, pos='RF', power=20, speed=30, bats='L', throws='R', letter='C'),
    dict(seed=1023, era=2024, age=41, pos='3B', power=50, speed=75, bats='S', throws='R', letter=''),
]


def sheet():
    """The grid as top-down RGB rows: (width, height, bytes)."""
    w, h = portrait.W, portrait.H
    sw, sh = COLS * w + (COLS - 1) * GAP, ROWS * h + (ROWS - 1) * GAP
    px = bytearray(b'\xff' * (sw * sh * 3))     # white gaps
    for i, kw in enumerate(SETS):
        _, _, rgb = portrait.portrait(**kw)
        x0, y0 = (i % COLS) * (w + GAP), (i // COLS) * (h + GAP)
        for y in range(h):
            at = ((y0 + y) * sw + x0) * 3
            px[at:at + w * 3] = rgb[y * w * 3:(y + 1) * w * 3]
    return sw, sh, bytes(px)


def bmp(w, h, px):
    """A 24-bit BMP: bottom-up BGR rows, each padded to 4 bytes."""
    stride = w * 3
    pad = b'\0' * (-stride % 4)
    body = bytearray()
    for y in range(h - 1, -1, -1):
        row = px[y * stride:(y + 1) * stride]
        bgr = bytearray(stride)
        bgr[0::3] = row[2::3]
        bgr[1::3] = row[1::3]
        bgr[2::3] = row[0::3]
        body += bgr + pad
    header = struct.pack('<2sIHHI', b'BM', 54 + len(body), 0, 0, 54)
    info = struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0)
    return header + info + bytes(body)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write('usage: portrait_sheet.py OUT.bmp\n')
        return 2
    w, h, px = sheet()
    with open(argv[1], 'wb') as f:
        f.write(bmp(w, h, px))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
