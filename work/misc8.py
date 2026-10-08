#!/usr/bin/env python3
"""Codec for the small FPS Baseball Pro '98 data files: bb.cfg, HHA.DAT, *.STS, *.apc, *.pyc / *.pyf.

usage: python3 misc8.py decode NAME in.bin out.json
       python3 misc8.py encode NAME in.bin edited.json out.bin     (in.bin is not read)

NAME picks the layout: *.cfg = bb.cfg (shell settings), *.STS = statistics screen set, *.apc = champions history,
*.pyc / *.pyf = player id list, anything else = HHA.DAT (home-run animation table). Layouts: work/spec/MISC8_FORMAT.md.
Keys starting with "_" are derived or stale bytes; encode rebuilds every byte from the JSON.
"""
import json
import struct
import sys


def cstr(raw):
    return raw.split(b'\0', 1)[0].decode('latin-1')


def put_str(text, size, what):
    b = text.encode('latin-1')
    if len(b) >= size:
        raise ValueError(f'{what}: {text!r} is longer than {size - 1} characters')
    return b + b'\0' * (size - len(b))


def stale_tail(raw):
    """[offset, text] of the bytes after a fixed string's NUL (left over from an older, longer value; trailing zeros
    dropped), or None."""
    nul = raw.find(b'\0')
    t = raw[nul + 1:].rstrip(b'\0') if nul >= 0 else b''
    return [nul + 1, t.decode('latin-1')] if t else None


def put_str_stale(text, tail, size, what):
    """A fixed string written over its old buffer: the stale bytes that lie past the new NUL stay where they were."""
    out = bytearray(put_str(text, size, what))
    if tail:
        off, t = tail[0], tail[1].encode('latin-1')
        n = len(text.encode('latin-1')) + 1
        for i, c in enumerate(t):
            if n <= off + i < size:
                out[off + i] = c
    return bytes(out)


# ---------------------------------------------------------------- bb.cfg (0x7c bytes)
# BBShell keeps it in DAT_68091610, load/save FUN_68062620. EZShell has its own default copy (DAT_6a038220).

CFG_SIZE = 0x7c
SIDE_LEVELS = ('level_0x4', 'level_0x5', 'level_0x6', 'level_0x7')


def cfg_decode(b):
    if len(b) != CFG_SIZE:
        raise ValueError(f'bb.cfg must be {CFG_SIZE} bytes, got {len(b)}')
    u8 = lambda o: b[o]
    u16 = lambda o: struct.unpack_from('<H', b, o)[0]
    u32 = lambda o: struct.unpack_from('<I', b, o)[0]
    d = {'version': u16(0),
         'association': cstr(b[0x02:0x10]),
         'favorite_team': u16(0x10),
         'exhibition_sides': [{'team': u16(0x12 + 0x10 * k), 'association': cstr(b[0x14 + 0x10 * k:0x22 + 0x10 * k])}
                              for k in range(2)],
         'exhibition_selector': u16(0x32),
         'use_custom_stadium': u8(0x34),
         'custom_stadium_file': cstr(b[0x35:0x43]),
         'custom_stadium_type': u8(0x43),
         'side_controls': []}
    for k in range(2):
        o = 0x44 + 0x10 * k
        d['side_controls'].append({
            'controller': u16(o),
            'mode_0x2': u8(o + 2),
            'toggle_0x3': u8(o + 3),
            **{name: u8(o + 4 + i) for i, name in enumerate(SIDE_LEVELS)},
            'toggles_0x8': list(b[o + 8:o + 0xf]),
            'at_0xf': u8(o + 0xf)})
    d.update({'option_0x64': u8(0x64), 'option_0x65': u8(0x65), 'option_0x66': u8(0x66), 'option_0x67': u8(0x67),
              'option_0x68': u8(0x68), 'option_0x69': u8(0x69), 'game_option_3e9': u8(0x6a), 'at_0x6b': u8(0x6b),
              'at_0x6c': u8(0x6c), 'game_option_3ea': u8(0x6d), 'at_0x6e': u8(0x6e), 'shell_music': u8(0x6f),
              'start_screen': u32(0x70), 'at_0x74': u32(0x74), 'print_to_file': u32(0x78)})
    tails = {k: stale_tail(b[o:o + 14]) for k, o in (('association', 2), ('side0', 0x14), ('side1', 0x24),
                                                     ('custom_stadium_file', 0x35))}
    tails = {k: v for k, v in tails.items() if v}
    if tails:
        d['_stale'] = tails
    return d


def cfg_encode(d):
    st = d.get('_stale', {})
    out = bytearray(CFG_SIZE)
    struct.pack_into('<H', out, 0, d['version'])
    out[0x02:0x10] = put_str_stale(d['association'], st.get('association'), 14, 'association')
    struct.pack_into('<H', out, 0x10, d['favorite_team'])
    sides = d['exhibition_sides']
    if len(sides) != 2:
        raise ValueError('exhibition_sides needs 2 entries')
    for k, s in enumerate(sides):
        struct.pack_into('<H', out, 0x12 + 0x10 * k, s['team'])
        out[0x14 + 0x10 * k:0x22 + 0x10 * k] = put_str_stale(s['association'], st.get(f'side{k}'), 14, 'association')
    struct.pack_into('<H', out, 0x32, d['exhibition_selector'])
    out[0x34] = d['use_custom_stadium']
    out[0x35:0x43] = put_str_stale(d['custom_stadium_file'], st.get('custom_stadium_file'), 14, 'custom_stadium_file')
    out[0x43] = d['custom_stadium_type']
    if len(d['side_controls']) != 2:
        raise ValueError('side_controls needs 2 entries')
    for k, s in enumerate(d['side_controls']):
        o = 0x44 + 0x10 * k
        struct.pack_into('<H', out, o, s['controller'])
        out[o + 2] = s['mode_0x2']
        out[o + 3] = s['toggle_0x3']
        for i, name in enumerate(SIDE_LEVELS):
            out[o + 4 + i] = s[name]
        if len(s['toggles_0x8']) != 7:
            raise ValueError('toggles_0x8 needs 7 bytes')
        out[o + 8:o + 0xf] = bytes(s['toggles_0x8'])
        out[o + 0xf] = s['at_0xf']
    for o, k in ((0x64, 'option_0x64'), (0x65, 'option_0x65'), (0x66, 'option_0x66'), (0x67, 'option_0x67'),
                 (0x68, 'option_0x68'), (0x69, 'option_0x69'), (0x6a, 'game_option_3e9'), (0x6b, 'at_0x6b'),
                 (0x6c, 'at_0x6c'), (0x6d, 'game_option_3ea'), (0x6e, 'at_0x6e'), (0x6f, 'shell_music')):
        out[o] = d[k]
    struct.pack_into('<3I', out, 0x70, d['start_screen'], d['at_0x74'], d['print_to_file'])
    return bytes(out)


# ---------------------------------------------------------------- .STS (0x75 bytes)
# BBShell StatSet load 0x6805d7d0: size must be 0x75, u32 version 1, name[33], then u32 ids[2][10] (0x50 bytes).
# StatsGrid_InitHeaders copies ids + view*10 (view 0 batting, 1 pitching) into the grid's 10 columns.

STS_SIZE = 0x75


def sts_decode(b):
    if len(b) != STS_SIZE:
        raise ValueError(f'.STS must be {STS_SIZE} bytes, got {len(b)}')
    ver, = struct.unpack_from('<I', b, 0)
    if ver != 1:
        raise ValueError(f'.STS version must be 1, got {ver}')
    ids = struct.unpack_from('<20I', b, 0x25)
    d = {'name': cstr(b[4:0x25]), 'batting_columns': list(ids[:10]), 'pitching_columns': list(ids[10:])}
    t = stale_tail(b[4:0x25])
    if t:
        d['_name_tail'] = t
    return d


def sts_encode(d):
    out = struct.pack('<I', 1) + put_str_stale(d['name'], d.get('_name_tail'), 33, 'name')
    for k in ('batting_columns', 'pitching_columns'):
        if len(d[k]) != 10:
            raise ValueError(f'{k} needs 10 stat ids')
        out += struct.pack('<10I', *d[k])
    return out


# ---------------------------------------------------------------- .apc (champions history)
# BBShell reader FUN_6804d7a0, writer FUN_6804d960. Chunks "PC0:" u32 len, payload u16 year, s16 n, n C strings.

def apc_decode(b):
    seasons, o = [], 0
    while o < len(b):
        if b[o:o + 4] != b'PC0:':
            raise ValueError(f'.apc: no PC0: chunk at {o:#x}')
        n, = struct.unpack_from('<I', b, o + 4)
        p = b[o + 8:o + 8 + n]
        if len(p) != n or n < 4:
            raise ValueError(f'.apc: bad chunk length at {o:#x}')
        year, cnt = struct.unpack_from('<Hh', p)
        parts = p[4:].split(b'\0')
        if cnt < 0 or len(parts) != cnt + 1 or parts[-1]:
            raise ValueError(f'.apc: chunk at {o:#x} is not {cnt} strings')
        seasons.append({'year': year, 'lines': [s.decode('latin-1') for s in parts[:-1]]})
        o += 8 + n
    return {'seasons': seasons}


def apc_encode(d):
    out = b''
    for s in d['seasons']:
        p = struct.pack('<Hh', s['year'], len(s['lines']))
        for ln in s['lines']:
            t = ln.encode('latin-1')
            if b'\0' in t:
                raise ValueError('.apc line holds a NUL')
            p += t + b'\0'
        out += b'PC0:' + struct.pack('<I', len(p)) + p
    return out


# ---------------------------------------------------------------- .pyc / .pyf (player id list)
# BBShell FUN_6805be80 opens (no truncate), FUN_6805bf50 rewrites the 10-byte header in place, FUN_6805bfa0 appends
# one id (len += 2, count += 1); the loader FUN_68053b70 reads the ids. Bytes past the list are an older, longer list.

def pyl_decode(b):
    if len(b) < 10 or b[:4] != b'PPD:':
        raise ValueError('player list must start with PPD:')
    n, cnt = struct.unpack_from('<Ih', b, 4)
    if cnt < 0 or n != 2 + 2 * cnt or len(b) < 10 + 2 * cnt:
        raise ValueError('player list header does not match its ids')
    tail = b[10 + 2 * cnt:]
    d = {'player_ids': list(struct.unpack_from(f'<{cnt}H', b, 10))}
    if tail:
        d['stale_player_ids'] = list(struct.unpack_from(f'<{len(tail) // 2}H', tail))
        if len(tail) % 2:
            d['_stale_last_byte'] = tail[-1]
    return d


def pyl_encode(d):
    ids = d['player_ids']
    out = b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack(f'<{len(ids)}H', *ids)
    stale = d.get('stale_player_ids', [])
    out += struct.pack(f'<{len(stale)}H', *stale)
    if '_stale_last_byte' in d:
        out += bytes([d['_stale_last_byte']])
    return out


# ---------------------------------------------------------------- HHA.DAT (home-run animations)
# BBSIM FUN_68035f31 (Hranim.cpp): u16 0x6969, 64 x {u16 frames, u16 variants, u32 record pointer}, then each
# animation's frames x variants cells of 22 bytes. FUN_680361ba fetches cell (frame, variant) at
# (frames * variant + frame) * 22; FUN_68036985 copies it to the sprite (+0x16..+0x2a) and offsets x/y by the
# sprite position.

HHA_MAGIC = 0x6969
CELL = struct.Struct('<HHhhHH4hH')


def hha_decode(b):
    if len(b) < 0x202 or struct.unpack_from('<H', b)[0] != HHA_MAGIC:
        raise ValueError('HHA.DAT must start with 0x6969')
    anims, o = [], 0x202
    for e in range(64):
        frames, variants, ptr = struct.unpack_from('<HHI', b, 2 + 8 * e)
        grid = []
        for v in range(variants):
            row = []
            for f in range(frames):
                if o + 22 > len(b):
                    raise ValueError('HHA.DAT is shorter than its table')
                c = CELL.unpack_from(b, o)
                o += 22
                cell = {'shape': c[0], 'frame': c[1], 'x': c[2], 'y': c[3], 'width': c[4], 'height': c[5],
                        'flag_0x14': c[10]}
                if any(c[6:10]):
                    cell['_rect'] = list(c[6:10])
                row.append(cell)
            grid.append(row)
        a = {'variants': grid, '_record_ptr': ptr}
        if not frames:
            a['_frames'] = 0
        anims.append(a)
    if o != len(b):
        raise ValueError(f'HHA.DAT has {len(b) - o} bytes past the last animation')
    return {'animations': anims}


def hha_encode(d):
    anims = d['animations']
    if len(anims) != 64:
        raise ValueError('HHA.DAT needs 64 animations')
    head, body = struct.pack('<H', HHA_MAGIC), b''
    for a in anims:
        grid = a['variants']
        frames = len(grid[0]) if grid else a.get('_frames', 0)
        if any(len(r) != frames for r in grid):
            raise ValueError('every variant of an animation needs the same number of frames')
        head += struct.pack('<HHI', frames, len(grid), a.get('_record_ptr', 0))
        for r in grid:
            for c in r:
                body += CELL.pack(c['shape'], c['frame'], c['x'], c['y'], c['width'], c['height'],
                                  *c.get('_rect', (0, 0, 0, 0)), c['flag_0x14'])
    return head + body


def kind(name):
    n = name.lower()
    if n.endswith('.cfg'):
        return cfg_decode, cfg_encode
    if n.endswith('.sts'):
        return sts_decode, sts_encode
    if n.endswith('.apc'):
        return apc_decode, apc_encode
    if n.endswith('.pyc') or n.endswith('.pyf'):
        return pyl_decode, pyl_encode
    return hha_decode, hha_encode


def main(argv):
    if len(argv) == 5 and argv[1] == 'decode':
        with open(argv[3], 'rb') as f:
            doc = kind(argv[2])[0](f.read())
        with open(argv[4], 'w') as f:
            json.dump(doc, f, indent=1)
    elif len(argv) == 6 and argv[1] == 'encode':
        with open(argv[4]) as f:
            doc = json.load(f)
        with open(argv[5], 'wb') as f:
            f.write(kind(argv[2])[1](doc))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
