#!/usr/bin/env python3
"""game.bki / game.bko: the shell -> simulator game hand-off (GDI/DIF/ADI chunks) and the simulator's event log (GDO).
Spec: spec/GAMEBK_FORMAT.md. Supersedes the lane codec re/targets/gamebk/lanes/code/voldat.py (#8b winner, round 3).

usage: gamebk.py decode FILE OUT.json      game.bki or game.bko (chosen by the first chunk tag)
       gamebk.py encode IN.json OUT
       gamebk.py verify FILE...            byte-exact decode/encode round trip

JSON keys starting with '_' are derived (labels, box-score replay) and ignored by encode.
"""
import datetime, json, struct, sys

from fpscipher import decipher, encipher


class GamebkError(ValueError):
    pass


def _fail(msg):
    raise GamebkError(msg)


# ---------------------------------------------------------------- chunks (BBShell FUN_68063450 / 68063840 / 68063910)

def parse_chunks(b):
    out, o = [], 0
    while o < len(b):
        if o + 8 > len(b):
            _fail(f'{len(b) - o} trailing bytes after the last chunk')
        tag = b[o:o + 4].decode('latin-1')
        n = struct.unpack_from('<I', b, o + 4)[0]
        if o + 8 + n > len(b):
            _fail(f'chunk {tag!r} at {o} overruns the file')
        out.append((tag, b[o + 8:o + 8 + n]))
        o += 8 + n
    return out


def build_chunks(chunks):
    return b''.join(tag.encode('latin-1') + struct.pack('<I', len(p)) + p for tag, p in chunks)


# ---------------------------------------------------------------- strings

def _stale_tail(raw):
    nul = raw.find(b'\0')
    t = raw[nul + 1:].rstrip(b'\0') if nul >= 0 else b''
    return [nul + 1, t.decode('latin-1')] if t else None


def _get_str(d, key, raw):
    nul = raw.find(b'\0')
    if nul < 0:
        _fail(f'{key}: no NUL in its {len(raw)}-byte field')
    d[key] = raw[:nul].decode('latin-1')
    t = _stale_tail(raw)
    if t:
        d[f'{key}_tail'] = t


def _put_str(d, key, size):
    text = d[key]
    if not isinstance(text, str):
        _fail(f'{key} must be a string')
    raw = text.encode('latin-1')
    if len(raw) >= size:
        _fail(f'{key} {text!r} is longer than {size - 1} characters')
    out = bytearray(raw + b'\0' * (size - len(raw)))
    tail = d.get(f'{key}_tail')
    if tail:
        off, t = tail[0], tail[1].encode('latin-1')
        for i, c in enumerate(t):
            if len(raw) + 1 <= off + i < size:
                out[off + i] = c
    return bytes(out)


def _int(v, lo, hi, what):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        _fail(f'{what} must be an integer {lo}..{hi}, got {v!r}')
    return v


def _hex(v, n, what):
    try:
        b = bytes.fromhex(v)
    except (TypeError, ValueError):
        _fail(f'{what} must be hex')
    if len(b) != n:
        _fail(f'{what} must be {n} bytes, got {len(b)}')
    return b


# ---------------------------------------------------------------- GDI record (0x405 bytes, enciphered after a 2-byte seed)
# Filled by BBShell FUN_68016ce0 / FUN_68016ec0 / FUN_68017000 (setters FUN_68061660, 68061a20, 68061a50, 68061a80,
# 68061b20..68061c50), written by FUN_680620a0; read by BBSIM FUN_68031e2f.

RECORD = 0x405
BLOCK = 0x1ea
SERIAL_EPOCH = 365                       # day serial = proleptic Gregorian ordinal + 365 (as in hcard.py)

# team block strings: (key, offset, size). Source = the league t.dat team record (+0x12, +0x23, +0x34, +0x45, ...).
TEAM_STRS = (('name', 0x0c, 17), ('alt_name', 0x1d, 17), ('manager', 0x2e, 17), ('abbrev', 0x3f, 5),
             ('stadium', 0x4d, 33), ('city8', 0x6e, 9), ('league', 0x1d9, 9))
# team block bytes 4..11 = t.dat team record bytes 5, 0xc, 0xd, 6, 0xe, 0xf, 0x10, 0x11 (FUN_68061660)
TDAT_SRC = (5, 0xc, 0xd, 6, 0xe, 0xf, 0x10, 0x11)


def decode_team(blk):
    t = {'team_id': blk[0], 'league_idx': blk[1], 'div_idx': blk[2], 'div_slot': blk[3],
         'tdat_bytes': {f'0x{s:02x}': blk[4 + i] for i, s in enumerate(TDAT_SRC)}}
    for key, off, size in TEAM_STRS:
        _get_str(t, key, blk[off:off + size])
    t['at_0x44'] = blk[0x44:0x4d].hex()
    t['uniform_palette'] = [list(blk[0x77 + 3 * i:0x7a + 3 * i]) for i in range(32)]
    t['turf'] = blk[0xd7]
    t['at_0xd8'] = blk[0xd8]
    t['roster'] = list(struct.unpack_from('<25H', blk, 0xd9))
    t['order_words'] = list(struct.unpack_from('<102H', blk, 0x10b))
    t['at_0x1d7'] = [blk[0x1d7], blk[0x1d8]]
    t['control'] = blk[0x1e2]
    t['options'] = list(blk[0x1e3:0x1ea])
    return t


def encode_team(t, side):
    w = f'{side} team'
    blk = bytearray(BLOCK)
    for i, k in enumerate(('team_id', 'league_idx', 'div_idx', 'div_slot')):
        blk[i] = _int(t[k], 0, 255, f'{w} {k}')
    tb = t['tdat_bytes']
    for i, s in enumerate(TDAT_SRC):
        blk[4 + i] = _int(tb[f'0x{s:02x}'], 0, 255, f'{w} tdat_bytes 0x{s:02x}')
    for key, off, size in TEAM_STRS:
        blk[off:off + size] = _put_str(t, key, size)
    blk[0x44:0x4d] = _hex(t['at_0x44'], 9, f'{w} at_0x44')
    pal = t['uniform_palette']
    if len(pal) != 32 or any(len(c) != 3 for c in pal):
        _fail(f'{w} uniform_palette must be 32 [r, g, b] triples')
    blk[0x77:0xd7] = bytes(_int(v, 0, 255, f'{w} uniform_palette') for c in pal for v in c)
    blk[0xd7] = _int(t['turf'], 0, 255, f'{w} turf')
    blk[0xd8] = _int(t['at_0xd8'], 0, 255, f'{w} at_0xd8')
    for key, off, n in (('roster', 0xd9, 25), ('order_words', 0x10b, 102)):
        v = t[key]
        if len(v) != n:
            _fail(f'{w} {key} must hold exactly {n} words')
        struct.pack_into(f'<{n}H', blk, off, *(_int(x, 0, 0xffff, f'{w} {key}') for x in v))
    if len(t['at_0x1d7']) != 2:
        _fail(f'{w} at_0x1d7 holds 2 bytes')
    blk[0x1d7:0x1d9] = bytes(_int(x, 0, 255, f'{w} at_0x1d7') for x in t['at_0x1d7'])
    blk[0x1e2] = _int(t['control'], 0, 255, f'{w} control')
    if len(t['options']) != 7:
        _fail(f'{w} options holds 7 bytes')
    blk[0x1e3:0x1ea] = bytes(_int(x, 0, 255, f'{w} options') for x in t['options'])
    return bytes(blk)


RAIN_KEYS = ('kind', 'start_out', 'span_outs', 'delay_count')


def decode_record(r):
    g = {'away': decode_team(r[:BLOCK]), 'home': decode_team(r[BLOCK:2 * BLOCK])}
    t = r[2 * BLOCK:]                                     # tail, record offset 0x3d4
    g['weather'] = {'wind_direction': t[0], 'wind_mph': t[1], 'sky': t[2], 'temperature_f': t[3],
                    'rain': dict(zip(RAIN_KEYS, t[4:8]), delay_outs=list(t[8:12]), delay_minutes=list(t[12:16]))}
    g['sim_seed'] = struct.unpack_from('<H', r, 0x3e4)[0]
    g['mode'] = r[0x3e6]
    g['game_type'] = r[0x3e7]
    g['month'] = r[0x3e8]
    g['preset_lineups'] = r[0x3e9]
    g['one_pitch'] = r[0x3ea]
    _get_str(g, 'stadium_file', r[0x3eb:0x3f4])
    _get_str(g, 'box_file', r[0x3f4:0x400])
    g['at_0x400'] = [r[0x400], r[0x401]]
    g['stadium_flag'] = r[0x402]
    g['at_0x403'] = struct.unpack_from('<H', r, 0x403)[0]
    return g


def encode_record(g):
    r = bytearray(RECORD)
    r[:BLOCK] = encode_team(g['away'], 'away')
    r[BLOCK:2 * BLOCK] = encode_team(g['home'], 'home')
    w = g['weather']
    rain = w['rain']
    r[0x3d4:0x3dc] = bytes(_int(v, 0, 255, f'weather {k}') for k, v in (
        ('wind_direction', w['wind_direction']), ('wind_mph', w['wind_mph']), ('sky', w['sky']),
        ('temperature_f', w['temperature_f'])) + tuple((k, rain[k]) for k in RAIN_KEYS))
    for key, off in (('delay_outs', 0x3dc), ('delay_minutes', 0x3e0)):
        if len(rain[key]) != 4:
            _fail(f'rain {key} holds exactly 4 entries')
        r[off:off + 4] = bytes(_int(x, 0, 255, f'rain {key}') for x in rain[key])
    struct.pack_into('<H', r, 0x3e4, _int(g['sim_seed'], 0, 0xffff, 'sim_seed'))
    for key, off in (('mode', 0x3e6), ('game_type', 0x3e7), ('month', 0x3e8), ('preset_lineups', 0x3e9),
                     ('one_pitch', 0x3ea), ('stadium_flag', 0x402)):
        r[off] = _int(g[key], 0, 255, key)
    r[0x3eb:0x3f4] = _put_str(g, 'stadium_file', 9)
    r[0x3f4:0x400] = _put_str(g, 'box_file', 12)
    if len(g['at_0x400']) != 2:
        _fail('at_0x400 holds 2 bytes')
    r[0x400:0x402] = bytes(_int(x, 0, 255, 'at_0x400') for x in g['at_0x400'])
    struct.pack_into('<H', r, 0x403, _int(g['at_0x403'], 0, 0xffff, 'at_0x403'))
    return bytes(r)


def decode_adi(b):
    if len(b) != 12:
        _fail(f'ADI chunk is {len(b)} bytes, expected 12')
    serial, copy = struct.unpack_from('<II', b, 0)
    date = datetime.date.fromordinal(serial - SERIAL_EPOCH)
    return {'year': date.year, 'month': date.month, 'day': date.day, '_day_serial': serial,
            'copy_serial': None if copy == serial else copy,
            'game_index': b[8], 'at_9': b[9], 'at_10': struct.unpack_from('<H', b, 10)[0]}


def encode_adi(a):
    try:
        serial = datetime.date(a['year'], a['month'], a['day']).toordinal() + SERIAL_EPOCH
    except (TypeError, ValueError) as e:
        _fail(f'ADI date: {e}')
    copy = serial if a.get('copy_serial') is None else _int(a['copy_serial'], 0, 0xffffffff, 'ADI copy_serial')
    return struct.pack('<IIBBH', serial, copy, _int(a['game_index'], 0, 255, 'ADI game_index'),
                       _int(a['at_9'], 0, 255, 'ADI at_9'), _int(a['at_10'], 0, 0xffff, 'ADI at_10'))


def decode_bki(b):
    games = []
    for tag, p in parse_chunks(b):
        if tag == 'GDI:':
            if len(p) != 2 + RECORD:
                _fail(f'GDI chunk is {len(p)} bytes, expected {2 + RECORD}')
            g = {'seed': p[:2].hex(), 'order': ['GDI']}
            g.update(decode_record(decipher(p[2:], p[:2])))
            games.append(g)
            continue
        if not games:
            _fail(f'{tag!r} chunk before the first GDI chunk')
        g, seed = games[-1], bytes.fromhex(games[-1]['seed'])
        if tag == 'ADI:' and 'adi' not in g:
            g['adi'] = decode_adi(decipher(p, seed))
        elif tag == 'DIF:' and 'dif' not in g:
            if len(p) != 72:
                _fail(f'DIF chunk is {len(p)} bytes, expected 72')
            g['dif'] = decipher(p, seed).hex()
        else:
            _fail(f'unexpected chunk {tag!r} in game {len(games)}')
        g['order'].append(tag[:3])
    return {'file': 'game.bki', 'games': games}


def encode_bki(doc):
    chunks = []
    for i, g in enumerate(doc['games']):
        seed = _hex(g['seed'], 2, f'game {i + 1} seed')
        order = g.get('order') or ['GDI'] + [k.upper() for k in ('dif', 'adi') if g.get(k) is not None]
        if order[0] != 'GDI' or sorted(order[1:]) != sorted(k.upper() for k in ('dif', 'adi') if g.get(k) is not None):
            _fail(f'game {i + 1} order {order} does not match its chunks')
        for k in order:
            if k == 'GDI':
                chunks.append(('GDI:', seed + encipher(encode_record(g), seed)))
            elif k == 'ADI':
                chunks.append(('ADI:', encipher(encode_adi(g['adi']), seed)))
            else:
                chunks.append(('DIF:', encipher(_hex(g['dif'], 72, f'game {i + 1} dif'), seed)))
    return build_chunks(chunks)


# ---------------------------------------------------------------- GDO event log (BBSIM Event.cpp)
# Record sizes in bytes, type word included: BBSIM DAT_680b3238. Labels: the debug printer FUN_68027ae8 and its tables.

SIZES = {0: 4, 1: 82, 2: 30, 3: 14, 4: 6, 5: 8, 6: 8, 7: 10, 8: 12}
TYPES = ('start', 'score', 'pa', 'sub', 'team', 'pitch', 'bat', 'field', 'injury')
SIDES = ('away', 'home')
PITCH = ('AB', 'B1', 'B2', 'B3', 'HR', 'RBI', 'BB', 'K', 'HBP', 'BBI', 'SH', 'SF', 'R', 'SB', 'CS', 'BFP', 'ER', 'IR',
         'IRS', 'PT', 'KT', 'WP')                                                 # 0x680ba458
PITCH_FLAGS = (('CL', 0x100), ('SP', 0x200), ('PLH', 0x400), ('BLH', 0x800))     # 0x680ba658/650/644/63c
BAT = ('AB', 'B1', 'B2', 'B3', 'HR', 'RBI', 'BB', 'K', 'HBP', 'BBI', 'SH', 'SF', 'R', 'SB', 'CS', 'GDP', 'PO')  # 0x680ba4b0
FIELD = ('PO', 'A', 'E', 'DP', 'PB')                                              # 0x680ba4f8
SUB = ('PH', 'PR', 'RP', 'DS')                                                    # 0x680ba438
TEAM = ('RUN', 'ER', 'TP', 'DP', 'AB')                                            # 0x680ba448
LINE = ('runs', 'hits', 'errors', 'left_on_base')


def _label(table, v):
    return table[v] if v < len(table) else v


def _code(table, v, what):
    if isinstance(v, str):
        if v not in table:
            _fail(f'unknown {what} {v!r} (one of {", ".join(table)})')
        return table.index(v)
    return _int(v, 0, 0xffff, what)


def _side(v):
    return SIDES[v] if v < 2 else v


def _decode_line(w):
    return {'innings': list(struct.pack('<15H', *w[:15])), **dict(zip(LINE, w[15:19]))}


def _encode_line(d, what):
    inn = d['innings']
    if len(inn) != 30:
        _fail(f'{what} innings holds exactly 30 runs-per-inning bytes')
    b = bytes(_int(x, 0, 255, f'{what} innings') for x in inn)
    return list(struct.unpack('<15H', b)) + [_int(d[k], 0, 0xffff, f'{what} {k}') for k in LINE]


def decode_event(w):
    t = w[0]
    e = {'t': TYPES[t]}
    if t == 0:
        e['version'] = w[1]
    elif t == 1:
        e.update(game_seconds=w[1], outs=w[2], away=_decode_line(w[3:22]), home=_decode_line(w[22:41]))
    elif t == 2:
        e.update(fielders=w[1:10], on_deck=w[10], batter=w[11], runners=w[12:15])
    elif t == 3:
        e.update(side=_side(w[1]), pid=w[2], kind=_label(SUB, w[3]), bo=w[4], position=w[5], br=w[6])
    elif t == 4:
        e.update(side=_side(w[1]), event=_label(TEAM, w[2]))
    elif t == 5:
        e.update(side=_side(w[1]), pid=w[2], result=_label(PITCH, w[3] & 0xff),
                 flags=[n for n, bit in PITCH_FLAGS if w[3] & bit])
        if w[3] & 0xf000:
            e['flags_high'] = w[3] >> 12
    elif t == 6:
        e.update(side=_side(w[1]), pid=w[2], result=_label(BAT, w[3]))
    elif t == 7:
        e.update(side=_side(w[1]), pid=w[2], play=_label(FIELD, w[3]), position=w[4])
    elif t == 8:
        e.update(side=_side(w[1]), pid=w[2], type=w[3], duration=w[4], severity=w[5])
    return e


def encode_event(e, i):
    what = f'event {i}'
    if e.get('t') not in TYPES:
        _fail(f'{what}: unknown type {e.get("t")!r} (one of {", ".join(TYPES)})')
    t = TYPES.index(e['t'])
    u = lambda k: _int(e[k], 0, 0xffff, f'{what} {k}')
    side = lambda: _code(SIDES, e['side'], f'{what} side')
    if t == 0:
        w = [u('version')]
    elif t == 1:
        w = [u('game_seconds'), u('outs')] + _encode_line(e['away'], f'{what} away') + \
            _encode_line(e['home'], f'{what} home')
    elif t == 2:
        if len(e['fielders']) != 9 or len(e['runners']) != 3:
            _fail(f'{what}: pa needs 9 fielders and 3 runners')
        w = [_int(x, 0, 0xffff, f'{what} pid') for x in e['fielders'] + [e['on_deck'], e['batter']] + e['runners']]
    elif t == 3:
        w = [side(), u('pid'), _code(SUB, e['kind'], f'{what} kind'), u('bo'), u('position'), u('br')]
    elif t == 4:
        w = [side(), _code(TEAM, e['event'], f'{what} event')]
    elif t == 5:
        r = _code(PITCH, e['result'], f'{what} result')
        if r > 0xff:
            _fail(f'{what}: pitch result must fit a byte')
        for f in e['flags']:
            if f not in dict(PITCH_FLAGS):
                _fail(f'{what}: unknown pitch flag {f!r}')
        w = [side(), u('pid'), r | sum(dict(PITCH_FLAGS)[f] for f in e['flags']) |
             _int(e.get('flags_high', 0), 0, 15, f'{what} flags_high') << 12]
    elif t == 6:
        w = [side(), u('pid'), _code(BAT, e['result'], f'{what} result')]
    elif t == 7:
        w = [side(), u('pid'), _code(FIELD, e['play'], f'{what} play'), u('position')]
    else:
        w = [side(), u('pid'), u('type'), u('duration'), u('severity')]
    w = [t] + w
    assert len(w) * 2 == SIZES[t]
    return struct.pack(f'<{len(w)}H', *w)


def decode_events(p):
    out, o = [], 0
    while o < len(p):
        if o + 2 > len(p):
            _fail(f'odd trailing byte in the event log at {o}')
        t = struct.unpack_from('<H', p, o)[0]
        if t not in SIZES:
            _fail(f'unknown event type {t} at byte {o}')
        n = SIZES[t]
        if o + n > len(p):
            _fail(f'event type {t} at byte {o} overruns the log')
        out.append(decode_event(list(struct.unpack_from(f'<{n // 2}H', p, o))))
        o += n
    return out


def replay(events):
    """Box score rows from the log alone (rules checked row for row against every box file of the sample days)."""
    bat, pit, cur = {}, {}, {}
    B = lambda pid: bat.setdefault(pid, dict(pid=pid, ab=0, h=0, hr=0, rbi=0, bb=0, so=0, r=0, sb=0))
    P = lambda pid: pit.setdefault(pid, dict(pid=pid, outs=0, bf=0, h=0, hr=0, bb=0, so=0, r=0))
    other = {'away': 'home', 'home': 'away'}
    for e in events:
        if e['t'] == 'pitch':
            cur[e['side']] = e['pid']
            if e['result'] == 'BFP':
                P(e['pid'])['bf'] += 1
        elif e['t'] == 'bat':
            b, res, p = B(e['pid']), e['result'], cur.get(other.get(e['side']))
            key = {'AB': 'ab', 'RBI': 'rbi', 'BB': 'bb', 'K': 'so', 'R': 'r', 'SB': 'sb'}.get(res)
            if res in ('B1', 'B2', 'B3', 'HR'):
                key = 'h'
            if key is None:
                continue
            b[key] += 1
            if res == 'HR':
                b['hr'] += 1
            if p is not None and key in ('h', 'bb', 'so', 'r'):
                P(p)[key] += 1
                if res == 'HR':
                    P(p)['hr'] += 1
        elif e['t'] == 'field' and e['play'] == 'PO' and cur.get(e['side']) is not None:
            P(cur[e['side']])['outs'] += 1
    keep = lambda rows, skip: [r for r in rows.values() if any(v for k, v in r.items() if k not in skip)]
    return keep(bat, ('pid',)), keep(pit, ('pid',))


def decode_bko(b):
    games = []
    for tag, p in parse_chunks(b):
        if tag != 'GDO:':
            _fail(f'unexpected chunk {tag!r} in game.bko')
        ev = decode_events(p)
        bat, pit = replay(ev)
        games.append({'events': ev, '_batters': bat, '_pitchers': pit})
    return {'file': 'game.bko', 'games': games}


def encode_bko(doc):
    return build_chunks([('GDO:', b''.join(encode_event(e, i) for i, e in enumerate(g['events'])))
                         for g in doc['games']])


# ---------------------------------------------------------------- top level

def decode(b):
    if b[:4] == b'GDO:':
        return decode_bko(b)
    if b[:4] == b'GDI:':
        return decode_bki(b)
    _fail(f'not a game.bki/game.bko file (first tag {b[:4]!r})')


def encode(doc):
    if doc.get('file') == 'game.bko':
        return encode_bko(doc)
    if doc.get('file') == 'game.bki':
        return encode_bki(doc)
    _fail('JSON "file" must be "game.bki" or "game.bko"')


def main():
    a = sys.argv[1:]
    try:
        if a[:1] == ['decode'] and len(a) == 3:
            with open(a[2], 'w') as fh:
                json.dump(decode(open(a[1], 'rb').read()), fh, indent=1)
        elif a[:1] == ['encode'] and len(a) == 3:
            out = encode(json.load(open(a[1])))
            with open(a[2], 'wb') as fh:
                fh.write(out)
        elif a[:1] == ['verify'] and len(a) > 1:
            bad = 0
            for f in a[1:]:
                b = open(f, 'rb').read()
                try:
                    ok = encode(json.loads(json.dumps(decode(b)))) == b
                except GamebkError as e:
                    ok = False
                    print(f, 'ERROR', e)
                bad += not ok
                print(f, 'OK' if ok else 'MISMATCH')
            sys.exit(1 if bad else 0)
        else:
            sys.exit(__doc__)
    except GamebkError as e:
        sys.exit(f'gamebk.py: {e}')


if __name__ == '__main__':
    main()
