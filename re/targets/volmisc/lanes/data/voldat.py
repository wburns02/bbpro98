#!/usr/bin/env python3
"""Semantic codecs for SHELL.VOL DAT entries of FPS Baseball Pro '98:
   MENU.DAT (shell menu definitions), WEATHER.DAT (city climate table),
   ASNEW.DAT (new-association defaults).

   Layouts are documented in FORMAT.md next to this file.

   decode NAME in.bin out.json     -> named/editable JSON ("_" keys = derived)
   encode NAME in.bin edited.json out.bin
"""
import json, struct, sys

# ---------------------------------------------------------------- helpers
u8  = lambda b, o: b[o]
u16 = lambda b, o: struct.unpack_from('<H', b, o)[0]
u32 = lambda b, o: struct.unpack_from('<I', b, o)[0]

def cstr(b, o):
    z = b.find(b'\0', o)
    if z < 0:
        raise ValueError('unterminated string at %d' % o)
    return b[o:z].decode('latin1'), z + 1

def pack_cstr(s):
    return s.encode('latin1') + b'\0'

# ================================================================ WEATHER
# Tagged record stream (game walks it with FUN_68063450).  Each record…
#   record-header C-string, exposed as content: 4-byte tag ('WeC:'/'WeR:'/
#   'WeW:') + one character whose code is the payload size (0x2a=42 for WeC,
#   14 for WeR, 26 for WeW), then NUL + 2 pad bytes, then the payload:
#   WeC: city[fixed 22-byte NUL-padded field] + 20 climate bytes (mean temp
#        Apr..Oct x7, rain chance x7, aux x4, elevation u16)
#   WeR: 14 range-table bytes (lead 1 = Jan, 6 pair-bounds, tail 100)
#   WeW: 26 range-table bytes (lead 1, 12 pair-bounds, tail 100)
# The head prints as the C-string 'WeC:*' etc. (the 5th char is the size), so
# it is content; the encoder pads to NUL+2 after it.
# One stray 0x64 after the last record (kept in _tail_padding).

def decode_weather(b):
    off = 0
    cities, ranges, wide = [], [], []
    while off + 8 <= len(b):
        hdr, p = cstr(b, off)
        if hdr[:4] not in ('WeC:', 'WeR:', 'WeW:') or len(hdr) < 5:
            break
        kind = hdr[:4]
        size = ord(hdr[4])
        expected = {'WeC:': 42, 'WeR:': 14, 'WeW:': 26}[kind]
        if size != expected:
            break
        body_at = p + 2
        payload = b[body_at:body_at+size]
        if len(payload) < size:
            break
        if kind == 'WeC:':
            name = bytes(payload[:22]).split(b'\0')[0].decode('latin1')
            climate = payload[22:42]
            cities.append({
                'record_header': hdr,
                'city': name,
                'mean_temp_f': list(climate[0:7]),        # Apr..Oct daily mean (F)
                'rain_chance_pct': list(climate[7:14]),   # Apr..Oct, multiples of 5
                'aux_values': list(climate[14:18]),
                'elevation_ft': u16(climate, 18),
            })
        elif kind == 'WeR:':
            ranges.append({'record_header': hdr, 'range_values': list(payload)})
        else:
            wide.append({'record_header': hdr, 'range_values': list(payload)})
        off = body_at + size
    return {
        '_file_type': 'city weather climate table',
        'cities': cities,
        'season_range_records': ranges,       # 6 pair boundaries per record
        'expanded_range_records': wide,       # 12 pair boundaries per record
        '_tail_padding': bytearray(b[off:]),
    }

def encode_weather(doc):
    out = bytearray()
    for c in doc['cities']:
        hdr = c.get('record_header', 'WeC:' + chr(42))
        if not (isinstance(hdr, str) and hdr.startswith('WeC:') and len(hdr) >= 5):
            raise ValueError('city record_header must start with WeC:')
        v = bytearray(20)
        for i, x in enumerate(c['mean_temp_f']):
            v[i] = int(x) & 0xff
        for i, x in enumerate(c['rain_chance_pct']):
            v[7+i] = int(x) & 0xff
        for i, x in enumerate(c['aux_values']):
            v[14+i] = int(x) & 0xff
        struct.pack_into('<H', v, 18, int(c['elevation_ft']) & 0xffff)
        city = c['city'].encode('latin1')
        city = city[:22]
        city = city if len(city) == 22 else city + b'\0'
        city = city.ljust(22, b'\0')
        payload = city + bytes(v)
        out += pack_cstr(hdr) + b'\0\0' + payload
    for r in doc['season_range_records']:
        body = bytes(int(x) & 0xff for x in r['range_values'])
        out += pack_cstr(r.get('record_header', 'WeR:' + chr(len(body)))) + b'\0\0' + body
    for r in doc['expanded_range_records']:
        body = bytes(int(x) & 0xff for x in r['range_values'])
        out += pack_cstr(r.get('record_header', 'WeW:' + chr(len(body)))) + b'\0\0' + body
    out += doc['_tail_padding']
    return bytes(out)

# ================================================================ ASNEW
# Three blocks of fixed-size records (sentinel ids 1234 / 5678 / 3456):
#   A-block 420 bytes: 21 x 20B league-layout records  (id u16 = 1234)
#   B-block 120 bytes: 5 x 20B variant + 1 terminator  (id u16 = 5678)
#   C-block 312 bytes: 6 x 52B schedule layouts        (id u16 = 3456)
# then u16 name-pool length, the NUL-terminated layout-name pool, 2 NULs.
# 20B record: id u16, n u8, leagues u8, team counts x3, strength u8,
#             strength_flag u8, strength_alt u8, spare u8,
#             division_count u8 + division sizes x3, value u8 + 3 spare.
# 52B record: id u16, team_count u8, flag u8, three 16-byte order lists.

def _decode_ab(rec):
    return {
        'record_marker': u16(rec, 0),
        'variant_flag': u8(rec, 2),
        'leagues': u8(rec, 3),
        'team_counts': [u8(rec, 4), u8(rec, 5), u8(rec, 6)],
        'strength': u8(rec, 7),
        'strength_flag': u8(rec, 8),
        'strength_alt': u8(rec, 9),
        'spare_a': u8(rec, 10),
        'divisions': [u8(rec, 11), u8(rec, 12), u8(rec, 13), u8(rec, 14)],
        'value': u8(rec, 15),
        '_pad_bytes': bytearray(rec[16:20]),
    }

def encode_ab(doc):
    r = bytearray(20)
    struct.pack_into('<H', r, 0, int(doc['record_marker']) & 0xffff)
    r[2] = int(doc['variant_flag']) & 0xff
    r[3] = int(doc['leagues']) & 0xff
    for i in range(3):
        r[4+i] = int(doc['team_counts'][i]) & 0xff
    r[7] = int(doc['strength']) & 0xff
    r[8] = int(doc['strength_flag']) & 0xff
    r[9] = int(doc['strength_alt']) & 0xff
    r[10] = int(doc['spare_a']) & 0xff
    for i in range(4):
        r[11+i] = int(doc['divisions'][i]) & 0xff
    r[15] = int(doc['value']) & 0xff
    r[16:20] = doc['_pad_bytes']
    return bytes(r)

def decode_asnew(b):
    off = 0
    league_layouts = []
    for _ in range(21):
        league_layouts.append(_decode_ab(b[off:off+20]))
        off += 20
    size_variants = []
    for _ in range(5):
        size_variants.append(_decode_ab(b[off:off+20]))
        off += 20
    terminator = _decode_ab(b[off:off+20])
    off += 20
    schedule_layouts = []
    for _ in range(6):
        r = b[off:off+52]
        schedule_layouts.append({
            'record_marker': u16(r, 0),
            'team_count': u8(r, 2),
            'layout_flag': u8(r, 3),
            'order_lists': [list(r[4:20]), list(r[20:36]), list(r[36:52])],
        })
        off += 52
    pool_len = u16(b, off); off += 2
    off += 1                        # separator NUL before the name pool
    pool = b[off:off+pool_len]; off += pool_len
    names = [s.decode('latin1') for s in pool.split(b'\0') if s]
    pool_pad = len(pool) - sum(len(s) + 1 for s in names)
    return {
        '_file_type': 'new association defaults',
        'league_layouts': league_layouts,
        'size_variants': size_variants,
        'terminator_record': terminator,
        'schedule_layouts': schedule_layouts,
        'layout_name_pool': names,
        '_pool_pad_bytes': pool_pad,
        '_pool_tail_padding': bytearray(b[off:]),
    }

def encode_asnew(doc):
    out = bytearray()
    for d in doc['league_layouts']:
        out += encode_ab(d)
    for d in doc['size_variants']:
        out += encode_ab(d)
    out += encode_ab(doc['terminator_record'])
    pool = bytearray()
    for s in doc['layout_name_pool']:
        pool += pack_cstr(s)
    pool += b'\0' * doc['_pool_pad_bytes']
    for d in doc['schedule_layouts']:
        r = bytearray(52)
        struct.pack_into('<H', r, 0, int(d['record_marker']) & 0xffff)
        r[2] = int(d['team_count']) & 0xff
        r[3] = int(d['layout_flag']) & 0xff
        for li, lst in enumerate(d['order_lists']):
            for i in range(16):
                r[4+16*li+i] = int(lst[i]) & 0xff
        out += bytes(r)
    out += struct.pack('<H', len(pool)) + b'\0' + bytes(pool) + doc['_pool_tail_padding']
    return bytes(out)

# ================================================================= MENU
# The file head is the C-string 'IDX:x' (4-byte magic, 'x' filler, NUL, u16
# pad to 8 bytes), then u32 menu-count + count u32 offsets, each pointing 8
# past its 'MUB:' record head.  MUB record: u32 size + data:
#   u16a=8, u16b=41(0x29), u16c=624, u16 count(4|6), u16=0, u16=1,
#   u16=0x32, u16=0, u16=8, u16=8, title C-string ('Main'),
#   item records: lead u16 + optional way u16 + kind/id/attr u16s +
#   optional ref u16, then caption C-string with \x01 accelerator marker.

def decode_menu(b):
    sig, hp = cstr(b, 0)
    head_end = max(8, hp + 2)
    n = u32(b, head_end)
    offs = [u32(b, head_end+4+4*i) for i in range(n)]
    menus = []
    for k in range(n):
        head = offs[k] - 8
        size = u32(b, head + 4)
        d = b[head+8:head+8+size]
        hdr = {
            'bytes_per_row': u16(d, 0),
            'columns': u16(d, 2),
            'row_height': u16(d, 4),
            'border_style': u16(d, 6),
            'has_help_u16': u16(d, 8),
            'lead_marker': u16(d, 10),
            'title_width': u16(d, 12),
            'title_flag': u16(d, 14),
            'title_cols': u16(d, 16),
        }
        title, o = cstr(d, 18)
        items = []
        while o < size:
            lead = u16(d, o)
            o2 = o + 2
            form = {'lead': lead}
            # 8-byte form first: a 10-byte item can never pass (its 4th word's
            # high byte is 0x00/0xff, never a printable caption start)
            if o + 8 <= size and _capstart(d, o+8):
                form['target_kind'] = u16(d, o2); o2 += 2
                form['target_id'] = u16(d, o2); o2 += 2
                form['target_flags'] = u16(d, o2); o2 += 2
            else:
                if o + 10 > size:
                    raise ValueError('menu %d: truncated item at %d' % (k, o))
                form['target_kind'] = u16(d, o2); o2 += 2
                form['target_id'] = u16(d, o2); o2 += 2
                form['target_flags'] = u16(d, o2); o2 += 2
                form['target_ref'] = u16(d, o2); o2 += 2
            cap, e = cstr(d, o2)
            cs = _capstart(d, o2)
            form['caption_text'], form['accelerator'] = (cap.split('\x01', 1) + [None])[:2]
            items.append(form)
            o = cs
        menus.append({'header': hdr, 'title': title, 'items': items})
    last_end = offs[-1] - 8 + 8 + u32(b, offs[-1] - 4)
    return {
        '_file_type': 'shell menu definitions (signature string is on-disk content)',
        'signature': sig,
        'menus': menus,
        '_file_padding': bytearray(b[last_end:]),
    }

def _capstart(d, o):
    if o >= len(d):
        return None
    k = o
    has = False
    while k < len(d) and (32 <= d[k] < 127 or d[k] == 1):
        if 32 <= d[k] < 127:
            has = True
        k += 1
    if k < len(d) and d[k] == 0 and has and k > o:
        return k + 1
    return None

def encode_menu(doc):
    sig = doc.get('signature', 'IDX:x')
    sig_bytes = bytearray(pack_cstr(sig))
    head_len = max(8, len(sig_bytes) + 2)
    sig_bytes += b'\0' * (head_len - len(sig_bytes))
    out = bytearray(sig_bytes)
    n = len(doc['menus'])
    blocks = []
    for m in doc['menus']:
        f = m['header']
        data = bytearray(18)
        struct.pack_into('<H', data, 0, int(f['bytes_per_row']) & 0xffff)
        struct.pack_into('<H', data, 2, int(f['columns']) & 0xffff)
        struct.pack_into('<H', data, 4, int(f['row_height']) & 0xffff)
        struct.pack_into('<H', data, 6, int(f['border_style']) & 0xffff)
        struct.pack_into('<H', data, 8, int(f['has_help_u16']) & 0xffff)
        struct.pack_into('<H', data, 10, int(f['lead_marker']) & 0xffff)
        struct.pack_into('<H', data, 12, int(f['title_width']) & 0xffff)
        struct.pack_into('<H', data, 14, int(f['title_flag']) & 0xffff)
        struct.pack_into('<H', data, 16, int(f['title_cols']) & 0xffff)
        data += pack_cstr(m['title'])
        for it in m['items']:
            cap = it['caption_text']
            if it.get('accelerator'):
                cap += '\x01' + it['accelerator']
            words = [int(it['lead']) & 0xffff, int(it['target_kind']) & 0xffff,
                     int(it['target_id']) & 0xffff, int(it['target_flags']) & 0xffff]
            if 'target_ref' in it:
                words += [int(it['target_ref']) & 0xffff]
            for w in words:
                data += struct.pack('<H', w & 0xffff)
            data += pack_cstr(cap)
        blocks.append(bytes(data))
    base = head_len + 4 + 4*n
    out += struct.pack('<I', n)
    for blk in blocks:
        out += struct.pack('<I', base + 8)
        base += 8 + len(blk)
    for idx, blk in enumerate(blocks):
        out += b'MUB:' + struct.pack('<I', len(blk)) + blk
    out += doc.get('_file_padding', bytearray(b'\x00'))
    return bytes(out)

# ---------------------------------------------------------------- drivers
DECODERS = {'MENU': decode_menu, 'WEATHER': decode_weather, 'ASNEW': decode_asnew}
ENCODERS = {'MENU': encode_menu, 'WEATHER': encode_weather, 'ASNEW': encode_asnew}

def jsonable(obj):
    if isinstance(obj, bytearray):
        return {'_bytes_hex': obj.hex()}
    raise TypeError(repr(type(obj)))

def from_jsonable(obj):
    if isinstance(obj, dict):
        if '_bytes_hex' in obj and len(obj) == 1:
            return bytearray.fromhex(obj['_bytes_hex'])
        return {k: from_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_jsonable(v) for v in obj]
    return obj

def norm_name(name):
    base = name.replace('\\', '/').split('/')[-1]
    if base.upper().endswith('.DAT'):
        base = base[:-4]
    return base.upper()

def main():
    cmd, name = sys.argv[1], norm_name(sys.argv[2])
    if cmd == 'decode':
        b = open(sys.argv[3], 'rb').read()
        doc = DECODERS[name](b)
        json.dump(doc, open(sys.argv[4], 'w'), indent=1, default=jsonable)
    elif cmd == 'encode':
        b = open(sys.argv[3], 'rb').read()
        doc = json.load(open(sys.argv[4]))
        raw = ENCODERS[name](from_jsonable(doc))
        open(sys.argv[5], 'wb').write(raw)
    else:
        sys.exit('usage: voldat.py decode|encode NAME in.bin [edited.json] out')

if __name__ == '__main__':
    main()
