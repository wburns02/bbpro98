#!/usr/bin/env python3
"""Semantic codecs for the DAT entries of the FPS Baseball Pro '98 shell
archive SHELL.VOL ("VOLM"): MENU.DAT, WEATHER.DAT, ASNEW.DAT.

decode:     python3 voldat.py decode NAME in.bin out.json
encode:     python3 voldat.py encode NAME in.bin edited.json out.bin
NAME selects the layout: MENU | WEATHER | ASNEW (with or without .DAT).
Layouts are documented in FORMAT.md next to this file.
"""
import json
import struct
import sys

# ---------------------------------------------------------------- helpers
u16 = lambda b, o: struct.unpack_from('<H', b, o)[0]
u32 = lambda b, o: struct.unpack_from('<I', b, o)[0]


def cstr(b, o):
    z = b.find(b'\0', o)
    if z < 0:
        raise ValueError('unterminated string at %d' % o)
    return b[o:z].decode('latin1'), z + 1


def pack_cstr(s):
    return s.encode('latin1') + b'\0'


def pad_name(s, n):
    """NUL-padded name field.  The field is n bytes; a name that fills it
    exactly (n chars) is stored without its NUL (the game terminates at the
    field end), anything longer is truncated to n - 1 chars + NUL."""
    if len(s) >= n:
        return s[:n].encode('latin1')
    return s.encode('latin1') + b'\0' * (n - len(s))


# ================================================================ WEATHER
# One run of length-prefixed records:  TAG u32 size  payload
#   'WeC:' 42  city climate record (decode_city)
#   'WeR:' 14  temperature threshold table: count byte + [lo,hi] pairs
#              (+ pad, 5 pairs max; read by FUN_68064fb0 as 5 [lo,hi] pairs)
#   'WeW:' 26  temperature threshold table (12 pairs, wide)
# One byte 0x64 'd' trails the last record (game buffer garbage; kept).

SEASONS = ['april', 'may', 'june', 'july', 'august', 'september', 'october']
PAYLOAD_SIZE = {b'WeC:': 42, b'WeR:': 14, b'WeW:': 26}
WEC = 42


def decode_threshold(payload):
    n = payload[0]
    return {'_pair_count': n,
            'thresholds': [{'low': payload[1 + 2 * i], 'high': payload[2 + 2 * i]}
                           for i in range(n)],
            '_pad': list(payload[1 + 2 * n:])}


def encode_threshold(t, size):
    out = bytearray([len(t['thresholds']) & 0xff])
    for pair in t['thresholds']:
        out.append(int(pair['low']) & 0xff)
        out.append(int(pair['high']) & 0xff)
    out += bytes(int(x) & 0xff for x in t.get('_pad', []))
    out += b'\0' * max(0, size - len(out))
    return bytes(out[:size])


def decode_city(p, tag):
    return {
        'city_name': p[:22].split(b'\0')[0].decode('latin1'),
        'monthly_mean_temperature_f': dict(zip(SEASONS, p[22:29])),
        'monthly_precipitation_chance_pct': dict(zip(SEASONS, p[29:36])),
        'season_start': p[36],
        'weather_pattern_id': p[37],
        'alternate_pattern_id': p[38],
        'short_threshold_table_id': p[39],
        'wide_threshold_table_id': p[40],
        '_byte_41': p[41],
    }


def encode_city(c):
    p = bytearray(WEC)
    p[:22] = pad_name(c['city_name'], 22)
    temps = c['monthly_mean_temperature_f']
    rain = c['monthly_precipitation_chance_pct']
    for i, s in enumerate(SEASONS):
        p[22 + i] = int(temps[s]) & 0xff
        p[29 + i] = int(rain[s]) & 0xff
    p[36] = int(c['season_start']) & 0xff
    p[37] = int(c['weather_pattern_id']) & 0xff
    p[38] = int(c['alternate_pattern_id']) & 0xff
    p[39] = int(c['short_threshold_table_id']) & 0xff
    p[40] = int(c['wide_threshold_table_id']) & 0xff
    p[41] = int(c.get('_byte_41', 0)) & 0xff
    return bytes(p)


def decode_weather(b):
    off = 0
    cities, short, wide = [], [], []
    while off + 8 <= len(b):
        magic = b[off:off + 4]
        if magic not in PAYLOAD_SIZE or off + 8 + PAYLOAD_SIZE[magic] > len(b):
            break
        size = PAYLOAD_SIZE[magic]
        payload = b[off + 8:off + 8 + size]
        if magic == b'WeC:':
            cities.append(decode_city(payload, off))
        elif magic == b'WeR:':
            short.append(decode_threshold(payload))
        else:
            wide.append(decode_threshold(payload))
        off += 8 + size
    doc = {
        '_file_type': 'per-city weather climate table',
        # the marker spans the city records' header: 'WeC:' + the size byte
        # (42 = '*'); its chars past byte 5 live in the size's high bytes
        'record_marker': b[0:8].split(b'\0')[0].decode('latin1'),
        'cities': cities,
        'short_threshold_tables': short,
        'wide_threshold_tables': wide,
    }
    if off < len(b):
        doc['_trailing_bytes'] = list(b[off:])
    return doc


def encode_weather(doc):
    out = bytearray()
    # the record marker 'WeC:*' is content: 'WeC:' + the size byte plus the
    # size's high bytes; the record walk uses the tag's known payload size
    marker = pack_cstr(doc.get('record_marker', 'WeC:*'))
    hdr = bytearray(b'WeC:' + struct.pack('<I', WEC))
    hdr[:min(len(marker), 8)] = marker[:8]
    for c in doc['cities']:
        out += bytes(hdr) + encode_city(c)
    for t in doc['short_threshold_tables']:
        out += b'WeR:' + struct.pack('<I', 14) + encode_threshold(t, 14)
    for t in doc['wide_threshold_tables']:
        out += b'WeW:' + struct.pack('<I', 26) + encode_threshold(t, 26)
    tail = doc.get('_trailing_bytes')
    out += bytes(int(x) & 0xff for x in tail) if tail else b'\x64'
    return bytes(out)


# ================================================================ ASNEW
# Sentinel-id record blocks + the layout-name pool (evidence: FUN_68004fe0
# reads 0x1a4 = 21*20 bytes, 0x78 = 6*20, 0x138 = 6*52 and a u16 pool
# length; the reader FUN_68005230 walks group steps and name refs):
#   21 league-layout  records of 20B, id 1234 (0x04d2)
#    6 size-variant   records of 20B, id 5678 (0x162e), last a terminator
#    6 schedule-layout records of 52B, id 3456 (0x0d80)
#   u16 nameBytes+1 + separator NUL + name pool ("name\0" * n + final NUL)
# 20B record (each *Name ref is a byte offset into the pool, base = the
#   separator byte; the game adds 0x370 and reads the name):
#   id u16, teamCount u8, leagueCount u8, groupSet0 u8 x3 (per-conference
#     sizes), primaryName u16, altName u16, groupSet1 u8 x3, secondaryName
#     u16, tertiaryName u16  — 2 + 1 + 1 + 3 + 2 + 2 + 3 + 2 + 2 = 18... the
#     record is 20B: [0..1] id, [2] teams, [3] leagues, [4..6] set0, [8..9]
#     primary name ref, [10..11] alt name ref, [12..14] set1, [16..17]
#     secondary ref, [18..19] tertiary ref? widths: 2+1+1+3+2+2+3+2+2 = 18
#     + 2 = 20 with an extra word: [7] is 0 everywhere (padding) — the sets
#     are at [5..7] and [13..15] (the game reads +5 + i*8), refs at 8/10/16/18.
# 52B record: id u16, teamCount u8, layoutFlags u8, three 16-byte schedule
#     order lists (game stride 0x18 per league).
MARK_LEAGUE = 1234
MARK_VARIANT = 5678
MARK_SCHEDULE = 3456


def decode_20b(rec, pool):
    def name_at(ref):
        if ref == 0 or ref - 1 >= len(pool):
            return None
        z = pool.find(b'\0', ref - 1)
        if z < 0:
            return None
        return pool[ref - 1:z].decode('latin1')

    return {
        'team_count': rec[2],
        'league_count': rec[3],
        'primary_group_count': rec[4],
        'primary_group_sizes': [rec[5], rec[6], rec[7]],
        'pool_ref_0': u16(rec, 8),
        'pool_ref_1': u16(rec, 10),
        'extra_group_count': rec[12],
        'extra_group_sizes': [rec[13], rec[14], rec[15]],
        'pool_ref_2': u16(rec, 16),
        'pool_ref_3': u16(rec, 18),
        '_layout_name': name_at(u16(rec, 8)),
        '_alt_layout_name': name_at(u16(rec, 10)),
        '_secondary_layout_name': name_at(u16(rec, 16)),
        '_tertiary_layout_name': name_at(u16(rec, 18)),
    }


def encode_20b(d, name_off):
    r = bytearray(20)
    struct.pack_into('<H', r, 0, int(d['_record_marker']) & 0xffff)
    r[2] = int(d['team_count']) & 0xff
    r[3] = int(d['league_count']) & 0xff
    r[4] = int(d['primary_group_count']) & 0xff
    for i in range(3):
        r[5 + i] = int(d['primary_group_sizes'][i]) & 0xff
    struct.pack_into('<H', r, 8, name_off(d['pool_ref_0']))
    struct.pack_into('<H', r, 10, name_off(d['pool_ref_1']))
    r[12] = int(d['extra_group_count']) & 0xff
    for i in range(3):
        r[13 + i] = int(d['extra_group_sizes'][i]) & 0xff
    struct.pack_into('<H', r, 16, name_off(d['pool_ref_2']))
    struct.pack_into('<H', r, 18, name_off(d['pool_ref_3']))
    return bytes(r)


def decode_52b(rec):
    return {
        'team_count': rec[2],
        'layout_flags': rec[3],
        'league_orders': [list(rec[4:20]), list(rec[20:36]), list(rec[36:52])],
    }


def encode_52b(d):
    r = bytearray(52)
    struct.pack_into('<H', r, 0, int(d['_record_marker']) & 0xffff)
    r[2] = int(d['team_count']) & 0xff
    r[3] = int(d['layout_flags']) & 0xff
    for li, lst in enumerate(d['league_orders']):
        for i in range(16):
            r[4 + 16 * li + i] = int(lst[i]) & 0xff
    return bytes(r)


def decode_asnew(b):
    off = 0
    recs = []
    while off + 20 <= len(b) and u16(b, off) in (MARK_LEAGUE, MARK_VARIANT):
        recs.append(b[off:off + 20])
        off += 20
    schedules = []
    while off + 52 <= len(b) and u16(b, off) == MARK_SCHEDULE:
        schedules.append(b[off:off + 52])
        off += 52
    pool_field = u16(b, off)
    off += 2
    if b[off] != 0:
        raise ValueError('ASNEW: expected NUL separator before the name pool')
    off += 1
    pool = b[off:off + pool_field - 1]
    names = [s.decode('latin1') for s in pool.split(b'\0') if s]
    off += len(pool)
    league_layouts = [decode_20b(r, pool) for r in recs[:21]]
    size_variants = [decode_20b(r, pool) for r in recs[21:]]
    doc = {
        '_file_type': 'new association defaults',
        'league_layouts': league_layouts,
        'size_variants': size_variants,
        'schedule_layouts': [decode_52b(r) for r in schedules],
        'layout_name_pool': names,
    }
    if off < len(b):
        doc['_pool_trailing_bytes'] = list(b[off:])
    return doc


def _add_marker(rec, marker):
    out = {'_record_marker': marker}
    out.update(rec)
    return out


def encode_asnew(doc):
    pool = bytearray()
    # pool refs in the records are 1-based byte offsets into the pool with
    # the separator byte as base (pool index k lives at offset k + 1)
    def name_off(ref):
        ref = int(ref)
        if ref <= 0:
            return 0
        return ref

    out = bytearray()
    for d in doc['league_layouts']:
        out += encode_20b(_add_marker(d, MARK_LEAGUE), name_off)
    for d in doc['size_variants']:
        out += encode_20b(_add_marker(d, MARK_VARIANT), name_off)
    for d in doc['schedule_layouts']:
        out += encode_52b(_add_marker(d, MARK_SCHEDULE))
    for s in doc['layout_name_pool']:
        pool += pack_cstr(s)
    out += struct.pack('<H', len(pool) + 1) + b'\0' + bytes(pool)
    tail = doc.get('_pool_trailing_bytes')
    if tail:
        out += bytes(int(x) & 0xff for x in tail)
    else:
        out += b'\0\0'
    return bytes(out)


# ================================================================= MENU
# 'IDX:' u32 extent (=4+4*n; packaged as 'IDX:x' because the extent's low
#   byte is 0x78='x' in pristine files) u32 n u32 dataOffsets[n] (each
#   points 8 past its 'MUB:' record head; the game opens menu i at
#   offsets[i-1] relative to the record head).
# 'MUB:' u32 size + block data:
#   u16 header (9 words: stride 8, width 41, height 624, top-level item
#     count, 0, 1, 50, 0, 8) + NUL-terminated title + items.
#   item = u16 struct + caption "text\x01accelerator":
#     short form  (8 bytes):  [x, y, commandId, itemFlag]
#     long  form (10 bytes):  [selector, x, y, commandId, itemFlag]
#   The selector (1 byte printed as a \x01 anchor) precedes the x/y pair.
#   Both forms parse when the item flag is 0x0001 (\x01 + NUL); pick the
#   parse that yields the longer caption.

def decode_menu(b):
    if b[:4] != b'IDX:':
        raise ValueError('MENU: not an IDX table')
    n = u32(b, 8)
    offs = [u32(b, 12 + 4 * i) for i in range(n)]
    menus = []
    for k in range(n):
        head = offs[k] - 8
        size = u32(b, head + 4)
        d = b[head + 8:head + 8 + size]
        hdr = [u16(d, 2 * i) for i in range(9)]
        title, tz = cstr(d, 18)
        items = []
        o = tz
        while o < len(d):
            cl8, cl10 = _cap_len(d, o + 8), _cap_len(d, o + 10)
            if cl8 and (not cl10 or cl8 - 2 >= cl10):
                items.append({'x': u16(d, o), 'y': u16(d, o + 2),
                              'command_id': u16(d, o + 4),
                              'item_flag': u16(d, o + 6),
                              'caption': d[o + 8:o + 8 + cl8 - 1].decode('latin1')})
                o += 8 + cl8
            elif cl10:
                items.append({'selector': u16(d, o),
                              'x': u16(d, o + 2), 'y': u16(d, o + 4),
                              'command_id': u16(d, o + 6),
                              'item_flag': u16(d, o + 8),
                              'caption': d[o + 10:o + 10 + cl10 - 1].decode('latin1')})
                o += 10 + cl10
            else:
                raise ValueError('MENU block %d: bad item at %d' % (k, o))
        for it in items:
            cap = it.pop('caption')
            if '\x01' in cap:
                text, accel = cap.split('\x01', 1)
            else:
                text, accel = cap, None
            it['caption'] = text
            it['accelerator'] = accel
        menus.append({'header': {'row_stride': hdr[0], 'width': hdr[1],
                                 'height': hdr[2], 'top_level_items': hdr[3],
                                 'header4': hdr[4], 'header5': hdr[5],
                                 'header6': hdr[6], 'header7': hdr[7],
                                 'header8': hdr[8]},
                      'title': title, 'items': items})
    # the signature string spans the header: 'IDX:' + the extent bytes (the
    # extent's low byte is 'x' = 120 = 4+4n in pristine files)
    z = b.find(b'\0', 0)
    sig_end = min(z, 8) if 0 <= z <= 8 else 8
    return {'_file_type': 'shell menu definitions', 'menus': menus,
            'index_signature': b[:sig_end].decode('latin1')}


def _cap_len(d, o):
    if o >= len(d):
        return None
    k = o
    while k < len(d) and (32 <= d[k] < 127 or d[k] == 1):
        k += 1
    if k > o and k < len(d) and d[k] == 0:
        return k + 1 - o
    return None


def encode_menu(doc):
    n = len(doc['menus'])
    blocks = []
    for m in doc['menus']:
        h = m['header']
        data = bytearray(struct.pack('<9H', h['row_stride'], h['width'], h['height'],
                                     h['top_level_items'], h['header4'],
                                     h['header5'], h['header6'], h['header7'],
                                     h['header8']))
        data += pack_cstr(m['title'])
        for it in m['items']:
            cap = it['caption'] + (('\x01' + it['accelerator'])
                                   if it.get('accelerator') else '')
            if 'selector' in it:
                data += struct.pack('<5H', it['selector'], it['x'], it['y'],
                                    it['command_id'], it['item_flag'])
            else:
                data += struct.pack('<4H', it['x'], it['y'],
                                    it['command_id'], it['item_flag'])
            data += pack_cstr(cap)
        blocks.append(bytes(data))
    # the index signature spans the header: 'IDX:' + the extent bytes; all
    # bytes after 'IDX:' up to the string's NUL are kept verbatim (the
    # extent's upper bytes are only meaningful when their chars are 0)
    sig = pack_cstr(doc.get('index_signature', 'IDX:x'))
    hdr = bytearray(b'IDX:' + b'\0' * 4 + struct.pack('<I', n))
    hdr[:min(len(sig), 4)] = sig[:4]
    hdr[4:min(len(sig), 8)] = sig[4:8]
    out = hdr
    base = 12 + 4 * n
    for blk in blocks:
        out += struct.pack('<I', base + 8)
        base += 8 + len(blk)
    for blk in blocks:
        out += b'MUB:' + struct.pack('<I', len(blk)) + blk
    out += b'\0'
    return bytes(out)


# ---------------------------------------------------------------- drivers
DECODERS = {'MENU': decode_menu, 'WEATHER': decode_weather, 'ASNEW': decode_asnew}
ENCODERS = {'MENU': encode_menu, 'WEATHER': encode_weather, 'ASNEW': encode_asnew}


def norm_name(name):
    base = name.replace('\\', '/').split('/')[-1]
    if base.upper().endswith('.DAT'):
        base = base[:-4]
    return base.upper()


def main():
    if len(sys.argv) < 4:
        sys.exit('usage: voldat.py decode NAME in.bin out.json | '
                 'encode NAME in.bin edited.json out.bin')
    cmd, name = sys.argv[1], norm_name(sys.argv[2])
    if cmd == 'decode':
        b = open(sys.argv[3], 'rb').read()
        json.dump(DECODERS[name](b), open(sys.argv[4], 'w'), indent=1)
    elif cmd == 'encode':
        doc = json.load(open(sys.argv[4]))
        open(sys.argv[5], 'wb').write(ENCODERS[name](from_jsonable(doc)))
    else:
        sys.exit('unknown command %r' % cmd)


def from_jsonable(obj):
    if isinstance(obj, dict):
        if '_bytes_hex' in obj and len(obj) == 1:
            return bytearray.fromhex(obj['_bytes_hex'])
        return {k: from_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_jsonable(v) for v in obj]
    return obj


if __name__ == '__main__':
    main()
