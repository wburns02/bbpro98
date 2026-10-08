#!/usr/bin/env python3
"""Codec for three SHELL.VOL data entries of FPS Baseball Pro '98: MENU.DAT, WEATHER.DAT, ASNEW.DAT.

usage: python3 volmisc.py decode NAME in.bin out.json
       python3 volmisc.py encode NAME in.bin edited.json out.bin     (in.bin is not read)

NAME picks the layout: MENU* = shell menu bars, WEATHER* = city climates, anything else = ASNEW.DAT (new-association
league layouts). Layouts: work/spec/VOLMISC_FORMAT.md. Keys starting with "_" are derived or unread bytes; encode
rebuilds every byte from the JSON.
"""
import json
import struct
import sys


def cstr_at(b, p):
    """NUL-terminated string at p -> (text, offset after the NUL)."""
    e = b.index(b'\0', p)
    return b[p:e].decode('latin-1'), e + 1


def put_cstr(text, what):
    raw = text.encode('latin-1')
    if b'\0' in raw:
        raise ValueError(f'{what}: NUL inside {text!r}')
    return raw + b'\0'


# ---------------------------------------------------------------- MENU.DAT
# BBShell: the menu bar object DAT_6808db48 (ctor FUN_68046870, vtable 0x680817e0). FUN_68046a60 opens "menu_dat";
# FUN_68046b50(n) seeks IDX offset[n - 1] and calls vtable[0] = 0x68046e30 (bar), which builds one popup per item:
# type 0 -> class 0x68082020 (FUN_68077050), type 1 -> class 0x68081fe0 (FUN_68076d90); both parse with the same
# reader (0x68077190 / 0x68076ed0) and read their entries with 0x680777a0: type 0 command 0x6807d980,
# 1 separator 0x6807d6c0 (no data), 2 text slot 0x6807d7b0 (a command whose blank text the shell fills at runtime).

def caption(s):
    """'text\\x01Ctrl+W' -> {'text', 'shortcut'} (the shortcut is the right-aligned accelerator label)."""
    text, sep, short = s.partition('\x01')
    return {'text': text, 'shortcut': short} if sep else {'text': text}


def caption_bytes(d, what):
    s = d['text'] + ('\x01' + d['shortcut'] if 'shortcut' in d else '')
    return put_cstr(s, what)


def hotkey_fields(b, p):
    mods, scan, mnem = struct.unpack_from('<hHh', b, p)
    return {'hotkey_mods': mods, 'hotkey_scancode': scan, 'mnemonic': mnem}


def hotkey_bytes(d):
    return struct.pack('<hHh', d['hotkey_mods'], d['hotkey_scancode'], d['mnemonic'])


def menu_decode(b):
    if b[:4] != b'IDX:':
        raise ValueError('MENU.DAT must start with IDX:')
    ext, count = struct.unpack_from('<II', b, 4)
    if ext != 4 + 4 * count:
        raise ValueError(f'IDX extent {ext} does not match {count} menus')
    offs = struct.unpack_from(f'<{count}I', b, 12)
    p = 12 + 4 * count
    menus = []
    for m in range(count):
        if b[p:p + 4] != b'MUB:':
            raise ValueError(f'menu {m + 1}: no MUB: tag at {p:#x}')
        size = struct.unpack_from('<I', b, p + 4)[0]
        q = p + 8
        if offs[m] != q:
            raise ValueError(f'menu {m + 1}: IDX offset {offs[m]:#x} is not its block at {q:#x}')
        x, y, w, n = struct.unpack_from('<4H', b, q)
        q += 8
        popups = []
        for _ in range(n):
            cls, = struct.unpack_from('<H', b, q)
            if cls not in (0, 1):
                raise ValueError(f'menu {m + 1}: popup class {cls} at {q:#x}')
            pop = {'popup_class': cls, **hotkey_fields(b, q + 2)}
            nent, = struct.unpack_from('<H', b, q + 8)
            s, q = cstr_at(b, q + 10)
            pop['title'] = caption(s)
            ents = []
            for _ in range(nent):
                t, = struct.unpack_from('<H', b, q)
                q += 2
                if t == 1:
                    ents.append({'separator': True})
                    continue
                if t not in (0, 2):
                    raise ValueError(f'menu {m + 1}: entry type {t} at {q - 2:#x}')
                e = hotkey_fields(b, q)
                s, q = cstr_at(b, q + 6)
                e['caption'] = caption(s)
                if t == 2:
                    e['text_slot'] = True
                ents.append(e)
            pop['entries'] = ents
            popups.append(pop)
        if q != p + 8 + size:
            raise ValueError(f'menu {m + 1}: block ends at {q:#x}, its size says {p + 8 + size:#x}')
        menus.append({'bar_x': x, 'bar_y': y, 'bar_width': w, 'popups': popups})
        p = q
    return {'menus': menus, '_trailer': b[p:].hex()}


def menu_encode(d):
    blocks = []
    for mi, m in enumerate(d['menus']):
        out = bytearray(struct.pack('<4H', m['bar_x'], m['bar_y'], m['bar_width'], len(m['popups'])))
        for pop in m['popups']:
            out += struct.pack('<H', pop['popup_class']) + hotkey_bytes(pop)
            out += struct.pack('<H', len(pop['entries'])) + caption_bytes(pop['title'], f'menu {mi + 1} title')
            for e in pop['entries']:
                if e.get('separator'):
                    out += struct.pack('<H', 1)
                    continue
                out += struct.pack('<H', 2 if e.get('text_slot') else 0) + hotkey_bytes(e)
                out += caption_bytes(e['caption'], f'menu {mi + 1} entry')
        blocks.append(bytes(out))
    count = len(blocks)
    head = 12 + 4 * count
    offs, body = [], bytearray()
    for blk in blocks:
        offs.append(head + len(body) + 8)
        body += b'MUB:' + struct.pack('<I', len(blk)) + blk
    return (b'IDX:' + struct.pack('<II', 4 + 4 * count, count) + struct.pack(f'<{count}I', *offs) + bytes(body)
            + bytes.fromhex(d.get('_trailer', '')))


# ---------------------------------------------------------------- WEATHER.DAT
# BBShell weather object, loaded by FUN_680651a0(city): FUN_68063450 seeks the n-th chunk with a tag (1-based), then
# reads the city chunk field by field and fetches its rain table (WeR, 14 bytes -> +0x3e) and its calm-wind table
# (WeW, 26 bytes -> +0x4e). The daily roll is FUN_680653a0: FUN_68064f30 month 4..10, FUN_68064f60 temperature,
# FUN_68064fb0 sky, FUN_68065070 wind speed, FUN_680650f0 wind direction.

CITY, RAIN, WIND = b'WeC:', b'WeR:', b'WeW:'
SIZES = {CITY: 42, RAIN: 14, WIND: 26}


def pairs(raw):
    return [[raw[i], raw[i + 1]] for i in range(0, len(raw), 2)]


def pairs_bytes(ps, n, what):
    if len(ps) != n:
        raise ValueError(f'{what}: needs {n} [lo, hi] pairs, got {len(ps)}')
    return bytes(v for pr in ps for v in pr)


def weather_decode(b):
    p, cities, rain, wind, order = 0, [], [], [], []
    while p + 8 <= len(b) and b[p:p + 4] in SIZES:
        tag, n = b[p:p + 4], struct.unpack_from('<I', b, p + 4)[0]
        if n != SIZES[tag]:
            raise ValueError(f'{tag!r} chunk at {p:#x} has size {n}, expected {SIZES[tag]}')
        r = b[p + 8:p + 8 + n]
        if tag == CITY:
            raw = r[:22]
            nul = raw.find(b'\0')
            if nul < 0 or raw[nul:].strip(b'\0'):
                raise ValueError(f'city at {p:#x}: name field is not NUL-padded')
            c = {'name': raw[:nul].decode('latin-1'), 'mean_temp_f': list(r[22:29]), 'precip_pct': list(r[29:36]),
                 'rain_table': r[36], 'wind_dice': r[37], 'wind_offset': r[38], 'calm_wind_table': r[39],
                 'elevation_ft': struct.unpack_from('<H', r, 40)[0]}
            cities.append(c)
        elif tag == RAIN:
            rain.append(pairs(r))
        else:
            wind.append(pairs(r))
        order.append(tag[2:3].decode())
        p += 8 + n
    runs = []
    for t in order:
        if runs and runs[-1][0] == t:
            runs[-1][1] += 1
        else:
            runs.append([t, 1])
    doc = {'cities': cities, 'rain_tables': rain, 'calm_wind_tables': wind, '_trailer': b[p:].hex()}
    if [r[0] for r in runs] != ['C', 'R', 'W'][:len(runs)]:
        doc['_chunk_order'] = ''.join(order)
    return doc


def weather_encode(d):
    chunks = {'C': [], 'R': [], 'W': []}
    for i, c in enumerate(d['cities']):
        name = c['name'].encode('latin-1')
        if len(name) > 21 or b'\0' in name:
            raise ValueError(f'city {i}: name {c["name"]!r} is longer than 21 characters')
        for k in ('mean_temp_f', 'precip_pct'):
            if len(c[k]) != 7:
                raise ValueError(f'city {i}: {k} needs 7 values (April..October)')
        r = (name.ljust(22, b'\0') + bytes(c['mean_temp_f']) + bytes(c['precip_pct'])
             + bytes([c['rain_table'], c['wind_dice'], c['wind_offset'], c['calm_wind_table']])
             + struct.pack('<H', c['elevation_ft']))
        chunks['C'].append(CITY + struct.pack('<I', 42) + r)
    for i, t in enumerate(d['rain_tables']):
        chunks['R'].append(RAIN + struct.pack('<I', 14) + pairs_bytes(t, 7, f'rain table {i + 1}'))
    for i, t in enumerate(d['calm_wind_tables']):
        chunks['W'].append(WIND + struct.pack('<I', 26) + pairs_bytes(t, 13, f'calm-wind table {i + 1}'))
    order = d.get('_chunk_order')
    if order and sorted(order) == sorted('C' * len(chunks['C']) + 'R' * len(chunks['R']) + 'W' * len(chunks['W'])):
        it = {k: iter(v) for k, v in chunks.items()}
        body = b''.join(next(it[t]) for t in order)
    else:
        body = b''.join(chunks['C'] + chunks['R'] + chunks['W'])
    return body + bytes.fromhex(d.get('_trailer', ''))


# ---------------------------------------------------------------- ASNEW.DAT
# BBShell FUN_68004fe0 (new-association dialog) reads 21 x 20 bytes -> dlg+0x1c, 6 x 20 -> +0x1c0, 6 x 52 -> +0x238,
# a u16 length and that many pool bytes -> +0x370. Name refs are offsets into the pool (FUN_68005220); the pool starts
# with a NUL, so ref 0 is the empty string. FUN_68005180(teams) picks league layout (teams - 8) / 2, FUN_68005230
# shows option 0 or 1 of it, FUN_68005370 shows the division layout of each league; the association build
# (around line 4069 of the BBShell decompile) fills league k from default-team record (teams - 8) / 2 at +4 + 16k,
# or from record 5 when the league uses its division option 1.

N_LEAGUE, N_DIV, N_TEAMS = 21, 6, 6


def layout_decode(r, name):
    tag, teams, nopt = struct.unpack_from('<HBB', r, 0)
    opts = []
    for k in range(2):
        o = 4 + 8 * k
        cnt = r[o]
        sizes = list(r[o + 1:o + 4])
        ref1, ref2 = struct.unpack_from('<HH', r, o + 4)
        opts.append({'count': cnt, 'sizes': sizes, 'label': name(ref1), 'label2': name(ref2)})
    return {'record_tag': tag, 'teams': teams, 'option_count': nopt, 'options': opts}


def asnew_decode(b):
    pool_at = 20 * (N_LEAGUE + N_DIV) + 52 * N_TEAMS
    plen, = struct.unpack_from('<H', b, pool_at)
    pool = b[pool_at + 2:pool_at + 2 + plen]
    if len(pool) != plen or not pool or pool[0] != 0 or pool[-1] != 0:
        raise ValueError('ASNEW.DAT name pool must start and end with a NUL')
    starts = [0] + [i + 1 for i in range(len(pool) - 1) if pool[i] == 0]

    def name(ref):
        if ref not in starts:
            raise ValueError(f'name ref {ref} is not the start of a pool string')
        return cstr_at(pool, ref)[0]
    lay = [layout_decode(b[20 * i:20 * i + 20], name) for i in range(N_LEAGUE + N_DIV)]
    teams = []
    for i in range(N_TEAMS):
        r = b[20 * (N_LEAGUE + N_DIV) + 52 * i:][:52]
        tag, nt, x3 = struct.unpack_from('<HBB', r, 0)
        lg = [list(r[4 + 16 * k:20 + 16 * k]) for k in range(3)]
        for t in lg:
            while t and t[-1] == 0:
                t.pop()
        teams.append({'record_tag': tag, 'teams': nt, 'at_0x3': x3, 'league_teams': lg})
    return {'league_layouts': lay[:N_LEAGUE], 'division_layouts': lay[N_LEAGUE:], 'default_teams': teams,
            '_pool_order': [cstr_at(pool, s)[0] for s in starts[1:]], '_trailer': b[pool_at + 2 + plen:].hex()}


def asnew_encode(d):
    lays = d['league_layouts'] + d['division_layouts']
    if len(d['league_layouts']) != N_LEAGUE or len(d['division_layouts']) != N_DIV or len(d['default_teams']) != N_TEAMS:
        raise ValueError(f'ASNEW.DAT holds {N_LEAGUE} league layouts, {N_DIV} division layouts, {N_TEAMS} team lists')
    used = []
    for L in lays:
        for o in L['options']:
            for s in (o['label'], o['label2']):
                if s and s not in used:
                    used.append(s)
    names = [s for s in d.get('_pool_order', []) if s in used]
    names += [s for s in used if s not in names]
    pool, ref = bytearray(b'\0'), {'': 0}
    for s in names:
        ref[s] = len(pool)
        pool += put_cstr(s, 'ASNEW name')
    out = bytearray()
    for i, L in enumerate(lays):
        if len(L['options']) != 2:
            raise ValueError(f'layout {i}: needs 2 options')
        out += struct.pack('<HBB', L['record_tag'], L['teams'], L['option_count'])
        for o in L['options']:
            if len(o['sizes']) != 3:
                raise ValueError(f'layout {i}: sizes needs 3 values')
            out += bytes([o['count']] + o['sizes']) + struct.pack('<HH', ref[o['label']], ref[o['label2']])
    for i, t in enumerate(d['default_teams']):
        out += struct.pack('<HBB', t['record_tag'], t['teams'], t['at_0x3'])
        if len(t['league_teams']) != 3 or any(len(x) > 16 for x in t['league_teams']):
            raise ValueError(f'default team list {i}: 3 leagues of at most 16 teams')
        for x in t['league_teams']:
            out += bytes(x).ljust(16, b'\0')
    return bytes(out) + struct.pack('<H', len(pool)) + bytes(pool) + bytes.fromhex(d.get('_trailer', ''))


def kind(name):
    n = name.upper()
    if n.startswith('MENU'):
        return menu_decode, menu_encode
    if n.startswith('WEATHER'):
        return weather_decode, weather_encode
    return asnew_decode, asnew_encode


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
