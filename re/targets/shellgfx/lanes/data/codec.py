#!/usr/bin/env python3
"""Codec for FPS Baseball Pro '98 menu-shell graphics: .BMX bitmap archives and .FNX fonts.

Formats (evidence in FORMAT.md):

BMX  - a directory of 10-byte entries starting at offset 0:
         u32 offset, u16 width, u16 height, u16 flags(always 0)
       terminated by an all-zero entry. The first entry's offset == directory size.
       Each bitmap is stored as exactly w*h-10 bytes: the first w*h-10 pixels of a
       row-major top-down w*h image; the last 10 pixels are implicit zeros.
       Bytes after the last bitmap's w*h-10 are an orphaned bitmap's stored data
       (a deleted directory entry); decoded as one more frame of (T+10) pixels.

FNX  - "FNX:" magic, then:
         u16 ver (1 = 1 bpp, 3 = 8 bpp)
         u8  A   (max ink width in px)
         u8  B   (cell height in px = glyph height)
         u8  C   (baseline, 7 in fonts 0-4, 0 in font 5)
         u8  first char (0x20)
         u8  count (96 = 0x20..0x7F, or 95)
         u16 offset-table start (17 == header size)
         u16 width-table start  (tstart + 2*count)
         u16 glyph-data start   (wstart + count)
         u16 offsets[count]     (relative to glyph-data start)
         u8  widths[count]      (ink/advance width in px)
       Each glyph is stored row-major at its cell height B with row stride
       ceil(w/8) bytes for 1 bpp or w bytes for 8 bpp (stride == w, i.e. plain
       8-bit pixels). Fonts 0-4 carry 288 bytes of DOS "dir" listing junk after
       the last glyph; preserved as an opaque junk frame.

Decoded frames: BMX bitmaps are w*h exactly as stored (plus implicit zeros).
Glyphs are decoded into a cell max(16, w) x B with ink at x=0; the 16px minimum
pitch represents the shell's glyph cell (and is why decoded fonts exceed the
file size). 1-bpp glyphs expand bit=1 to palette index 0x0b (the shell's light
colour). Fonts whose ink only uses indices 1..3 (the game remaps these at draw
time to the current text colour; indices 0-3 are all magic-pink transparent in
bb0.pal) get those three indices remapped to visible colours in the manifest
palette, purely for display.
"""
import json
import os
import struct
import sys

# bb0.pal (RIFF PAL data chunk), 256 RGB triples.
_PAL_HEX = (
    "ff8bffff8bffff8bffff8bffff8bffff8bffff8bffff8bffff8bffff8bfff7efe7e3dbcfd7cbb7cbbbabb7a793ab9b8b"
    "ffffffebebebdbdbdbcbcbcbbbbbbba7a7a79797978787877777776363635353534343433333331f1f1f0f0f0f000000"
    "fcfcfcf8f8f8f4f4f0f4f0ecf0f0ecf0ece8ece8e4e8e4e0e8e4dce4e0d8e4dcd4e0dcd4e0dcd0dcd8ccd8d4c8d8d0c4"
    "d4ccc0d0c8bcd0c8b8ccc4b4ccc0b0c8c0b0c8c0acc8bcacc4bca8c4b8a4c0b4a4c0b4a0bcb49cbcb09cbcb098b8ac94"
    "b4a890b4a48cb0a088aca084ac9c80a8987ca49478a090749c8c6c9c88689888649484649080608c7c6088785c847458"
    "8070547c6c54786c5074685070644c6c6048685c486458446054405c503c584c3c5448385048344c4434484030443c2c"
    "4038283c3428383024342c24302c202c28202c241c242018201c141c181418141014100c100c0c0c0c08080808040404"
    "c89568b8987dc4984cd49048cc933bc88c58d08834c08844c8804cc68822c47c40a68458c07c28ad7846c0741cb87030"
    "b56c3cb7671ab8602ca36636ad6124a84c0ba55610a25f1492501ca147189c48099438189834008030008c29007e2000"
    "cb874baf733f935f37774b2b5b371f3f2717e0a46cd4a86cd89c68dc9c58c8a460d4a040c36313a74f0b8b3f00733300"
    "ff0000e70000d30000bf0000ab00009700008300006f000073c30067b3005fa3005393004b83003f73003763002f5300"
    "007777006f6f006767005f5f005757005353ff7f00cb63009b4b006b3300a71fcb8f1baf7b179763137b4f0f633b0b4b"
    "ff8bff1b1f0b272b0f37371743471f535327635f2f6f6b377f73438b7f4b978757a78f63b39b6fc3a77fcfaf8bdfbb9b"
    "d7cfc3d3cbbfd3c7bbcfc7b7cbc3b3cbbfafc7bfafc7bbabc3bba7c3b7a3bfb7a3bfb39fbbaf9bbbaf97b7ab93b7ab93"
    "000000fcb040fefe02cc000000000030600418305c0b5307404040646464888888b0b0b0002410004c3000638fffffff"
    "83735f6f574753473f47331b130f07100f04ff8bffff8bffff8bffff8bffff8bffff8bffff8bffff8bffff8bffff8bff"
)
BIT1_IDX = 0x0B                     # light shell colour for 1-bpp ink
REMAP = {1: (255, 255, 255),        # main fill
         2: (68, 60, 44),           # dark outline (bb0 0x5f)
         3: (167, 143, 99)}         # accent (bb0 0xcb)


def _pal():
    b = bytes.fromhex(_PAL_HEX.replace(" ", ""))
    out = []
    for k in range(256):
        c = b[3 * k:3 * k + 3]
        out.append([c[0], c[1], c[2]] if len(c) == 3 else [0, 0, 0])
    while len(out) < 256:
        out.append([0, 0, 0])
    return out


def _factor_pair(n):
    """(w, h) with w*h == n, w >= h, closest to square."""
    w = 1
    for d in range(1, int(n ** 0.5) + 1):
        if n % d == 0:
            w = n // d
    return w, n // w


# ---------------------------------------------------------------- BMX

def decode_bmx(data):
    (dirsz,) = struct.unpack_from('<I', data, 0)
    if dirsz % 10 or dirsz < 10 or dirsz > len(data):
        raise ValueError(f'bad BMX directory size {dirsz}')
    ents = []
    i = 0
    while i < dirsz:
        off, w, h, q = struct.unpack_from('<IHHH', data, i)
        if off == 0 and w == 0 and h == 0 and q == 0:
            break
        ents.append((off, w, h, q))
        i += 10
    if (len(ents) + 1) * 10 != dirsz:
        raise ValueError('directory size != (entries+1)*10')
    if ents[0][0] != dirsz:
        raise ValueError('first offset != directory size')
    frames = []
    for k, (off, w, h, q) in enumerate(ents):
        stored = w * h - 10
        if k + 1 < len(ents) and ents[k + 1][0] != off + stored:
            raise ValueError(f'bitmap {k}: region {ents[k + 1][0] - off} != w*h-10')
        if off + stored > len(data):
            raise ValueError(f'bitmap {k} truncated')
        pix = data[off:off + stored] + b'\0' * 10
        frames.append({'w': w, 'h': h, 'file': f'f{k:04d}.bin', 'q': q, 'role': 'bm', '_pix': pix})
    t0 = ents[-1][0] + ents[-1][1] * ents[-1][2] - 10
    tail = data[t0:]
    if tail:
        w2, h2 = _factor_pair(len(tail) + 10)
        frames.append({'w': w2, 'h': h2, 'file': f'f{len(frames):04d}.bin',
                       'role': 'tail', '_pix': tail + b'\0' * 10})
    meta = {'kind': 'bmx', 'entries': len(ents),
            'note': 'each bitmap stores w*h-10 bytes; trailing bytes are an orphaned bitmap'}
    return frames, meta, _pal()


def encode_bmx(man, out):
    frames = man['frames']
    bm = [f for f in frames if f.get('role') == 'bm']
    tail = [f for f in frames if f.get('role') == 'tail']
    if len(bm) + len(tail) != len(frames):
        raise ValueError('unexpected frame role')
    dirsz = (len(bm) + 1) * 10
    buf = bytearray()
    off = dirsz
    for f in bm:
        buf += struct.pack('<IHHH', off, f['w'], f['h'], f.get('q', 0))
        off += f['w'] * f['h'] - 10
    buf += b'\0' * 10
    for f in bm + tail:
        pix = out.read_frame(f)
        if any(pix[-10:]):
            raise ValueError(f"{f['file']}: the last 10 pixels are not stored in BMX and must stay 0")
        buf += pix[:len(pix) - 10]
    return bytes(buf)


# ---------------------------------------------------------------- FNX

def decode_fnx(data):
    if data[:4] != b'FNX:':
        raise ValueError('not a FNX file')
    (ver,) = struct.unpack_from('<H', data, 4)
    a, b_h, c, first, cnt = data[6:11]
    tstart, wstart, dstart = struct.unpack_from('<HHH', data, 11)
    offs = struct.unpack_from(f'<{cnt}H', data, tstart)
    wids = data[wstart:wstart + cnt]
    if ver not in (1, 3):
        raise ValueError(f'unknown FNX bpp code {ver}')
    frames = []
    maxval = 0
    for i in range(cnt):
        aw = wids[i]
        stride = (aw + 7) // 8 if ver == 1 else aw
        cw = max(16, aw)
        g = data[dstart + offs[i]: dstart + offs[i] + stride * b_h]
        if len(g) != stride * b_h:
            raise ValueError(f'glyph {i} truncated')
        cell = bytearray(cw * b_h)
        if ver == 1:
            for y in range(b_h):
                row = g[y * stride:(y + 1) * stride]
                base = y * cw
                for x in range(aw):
                    if row[x >> 3] >> (7 - (x & 7)) & 1:
                        cell[base + x] = BIT1_IDX
        else:
            for y in range(b_h):
                cell[y * cw: y * cw + aw] = g[y * stride:(y + 1) * stride]
            maxval = max([maxval] + list(g))
        frames.append({'w': cw, 'h': b_h, 'file': f'f{i:04d}.bin',
                       'role': 'glyph', 'ch': first + i, 'aw': aw, '_pix': bytes(cell)})
    last_stride = (wids[-1] + 7) // 8 if ver == 1 else wids[-1]
    junk = data[dstart + offs[-1] + last_stride * b_h:]
    if junk:
        w2, h2 = _factor_pair(len(junk))
        frames.append({'w': w2, 'h': h2, 'file': f'f{cnt:04d}.bin',
                       'role': 'junk', '_pix': junk})
    meta = {'kind': 'fnx', 'ver': ver, 'max_w': a, 'cell_h': b_h, 'baseline': c,
            'first': first, 'count': cnt, 'tstart': tstart, 'wstart': wstart,
            'dstart': dstart,
            'note': 'glyph cells max(16,ink_width) x cell_h; junk frame = appended DOS dir text'}
    pal = _pal()
    if ver == 3 and maxval <= 3:
        for idx, rgb in REMAP.items():
            pal[idx] = list(rgb)
        meta['display_remap'] = 'ink indices 1-3 remapped for display (game colours them at draw time)'
    return frames, meta, pal


def encode_fnx(man, out):
    m = man['meta']
    ver, b_h, cnt = m['ver'], m['cell_h'], m['count']
    glyph_frames = [f for f in man['frames'] if f.get('role') == 'glyph']
    junk_frames = [f for f in man['frames'] if f.get('role') == 'junk']
    if len(glyph_frames) != cnt or len(glyph_frames) + len(junk_frames) != len(man['frames']):
        raise ValueError('frame list does not match font')
    header = bytearray(b'FNX:')
    header += struct.pack('<HBBBBB', ver, m['max_w'], b_h, m['baseline'],
                          m['first'], cnt)
    header += struct.pack('<HHH', m['tstart'], m['wstart'], m['dstart'])
    if len(header) != m['tstart']:
        raise ValueError('tstart != header size')
    buf = bytearray(header)
    widths = bytearray()
    offs = []
    cur = 0
    blobs = []
    for f in glyph_frames:
        aw = f['aw']
        stride = (aw + 7) // 8 if ver == 1 else aw
        pix = out.read_frame(f)
        cw = f['w']
        g = bytearray(stride * b_h)
        for y in range(b_h):
            row = pix[y * cw: y * cw + aw]
            if ver == 1:
                for x in range(aw):
                    if row[x]:
                        g[y * stride + (x >> 3)] |= 0x80 >> (x & 7)
            else:
                g[y * stride: y * stride + aw] = row[:aw]
        blobs.append(bytes(g))
        offs.append(cur)
        cur += stride * b_h
        widths.append(aw)
    if cur > 0xFFFF:
        raise ValueError('glyph data too large for u16 offsets')
    buf += struct.pack(f'<{cnt}H', *offs)
    buf += bytes(widths)
    for g in blobs:
        buf += g
    for f in junk_frames:
        buf += out.read_frame(f)
    return bytes(buf)


# ---------------------------------------------------------------- CLI

class FrameReader:
    def __init__(self, d):
        self.d = d

    def read_frame(self, f):
        with open(f"{self.d}/{f['file']}", 'rb') as fh:
            b = fh.read()
        if len(b) != f['w'] * f['h']:
            raise ValueError(f"{f['file']}: {len(b)} bytes, want {f['w'] * f['h']}")
        return b


def main():
    cmd, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == 'decode':
        with open(src, 'rb') as fh:
            data = fh.read()
        if data[:4] == b'FNX:':
            frames, meta, pal = decode_fnx(data)
        else:
            frames, meta, pal = decode_bmx(data)
        os.makedirs(dst, exist_ok=True)
        man = {'frames': [{k: v for k, v in f.items() if not k.startswith('_')} for f in frames],
               'palette': pal, 'meta': meta}
        for f in frames:
            with open(f"{dst}/{f['file']}", 'wb') as fh:
                fh.write(f['_pix'])
        with open(f'{dst}/manifest.json', 'w') as fh:
            json.dump(man, fh)
    elif cmd == 'encode':
        with open(f'{src}/manifest.json') as fh:
            man = json.load(fh)
        kind = man['meta']['kind']
        buf = (encode_bmx if kind == 'bmx' else encode_fnx)(man, FrameReader(src))
        with open(dst, 'wb') as fh:
            fh.write(buf)
    else:
        raise SystemExit(f'unknown command {cmd}')


if __name__ == '__main__':
    main()
