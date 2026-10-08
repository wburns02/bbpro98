#!/usr/bin/env python3
"""Box-score lineup card codec: the enciphered first record of Stats/<assn>.Hxx. Spec: work/spec/HCARD_FORMAT.md.

usage: hcard.py decode in.H out.json
       hcard.py encode in.H edited.json out.H      (in.H supplies the seed and the plaintext box tables)

Every byte of the 0xa88-byte card body is a named field. Upstats builds the card when a game is posted (FUN_6c002850
team blocks and slots, FUN_6c001980 substitutions, FUN_6c002b00 game facts, FUN_6c002fa0/FUN_6c003320/FUN_6c003550
per-event counters); BBShell reads it back for the box-score screen (FUN_680264c0 decipher, FUN_680117a0 copy,
FUN_6800fe70 game data, FUN_68010080 linescore, FUN_680104c0 notes).

JSON: {"game": {...}, "sides": [away, home]}; see the spec for every key. Keys starting with "_" are derived and
ignored by encode. Lists keep their on-disk capacity limits: 40 player slots, 40 lineup entries, 40 pitchers,
25 pitched-to notes, 30 innings, 4 rain delays.
"""
import datetime
import json
import struct
import sys

HEAD = b'\x02\x65\xff\xff\x01\x00\x8a\x0a'    # record tag, unk, count 1, record size 0xa8a (seed + body)
BODY = 0xa88
SIDE = 0x533
SLOT = 21
NSLOT = 40
TAIL = 2 * SIDE                                # 0xa66
SERIAL_EPOCH = 365                             # day serial = proleptic Gregorian ordinal + 365 (FUN_68049250)
POS = ('p', 'c', '1b', '2b', '3b', 'ss', 'lf', 'cf', 'rf', 'dh', 'ph', 'pr')   # mask bits 0..11, role codes 1..12
WIND = ('in from center', 'in from left', 'left to right', 'out to right', 'out to center', 'out to left',
        'right to left', 'in from right')
SLOT_COUNTS = ('pitches', 'strikes', 'pickoffs', 'season_holds', 'season_saves', 'season_wins', 'season_losses')


def _fail(msg):
    raise ValueError(msg)


# ---------------------------------------------------------------- cipher (work/fpscipher.py, applied three times)

def _table(seed):
    lo, hi = seed
    start = (lo - 1) & 255
    t = [start] * 256
    pos, v = 0, lo
    for _ in range(256):
        t[pos] = v
        v = (v + 1) & 255
        pos = (pos + hi) & 255
        while t[pos] != start:
            pos = (pos + 1) & 255
    return bytes(t[t[t[x]]] for x in range(256))


def decipher(data, seed):
    f = _table(seed)
    inv = bytearray(256)
    for x, y in enumerate(f):
        inv[y] = x
    return bytes(inv[b] for b in data)


def encipher(data, seed):
    f = _table(seed)
    return bytes(f[b] for b in data)


# ---------------------------------------------------------------- helpers

def _str(b):
    return b.split(b'\0')[0].decode('latin1')


def _put_str(out, off, size, s, what):
    raw = s.encode('latin1')
    if len(raw) >= size:
        _fail(f'{what} "{s}" is longer than {size - 1} characters')
    out[off:off + size] = raw + b'\0' * (size - len(raw))


def _names(mask, lo, hi):
    return [POS[i] for i in range(lo, hi) if mask >> i & 1]


def _mask(names, allowed):
    m = 0
    for n in names:
        if n not in allowed:
            _fail(f'unknown position/role "{n}"')
        m |= 1 << POS.index(n)
    return m


def _unused(s, a, b):
    """Bytes past a list's count: zero in every posted card, kept if not."""
    return s[a:b].hex() if any(s[a:b]) else None


# ---------------------------------------------------------------- decode

def decode_side(body, k):
    s = body[k * SIDE:(k + 1) * SIDE]
    players = []
    for i in range(NSLOT):
        o = 0x32 + SLOT * i
        pid, mask, start, role = struct.unpack_from('<HHHB', s, o)
        counts = struct.unpack_from('<7H', s, o + 7)
        if not pid:
            if any(s[o:o + SLOT]):
                _fail(f'side {k}: empty slot {i} holds data')
            continue
        if mask >> 12 or start >> 12 or role > 12:
            _fail(f'side {k}: slot {i} has unknown flag bits')
        players.append({'slot': i, 'pid': pid, 'positions': _names(mask, 0, 9), 'roles': _names(mask, 9, 12),
                        'started_at': _names(start, 0, 12), 'role': POS[role - 1] if role else None,
                        **dict(zip(SLOT_COUNTS, counts))})
    n = s[0x37a]
    m = s[0x3f3]
    c = s[0x444]
    if n > 40 or m > 40 or c > 25:
        _fail(f'side {k}: list count out of range ({n}, {m}, {c})')
    order = struct.unpack_from('<%dH' % n, s, 0x37b)
    side = {
        'side': ('away', 'home')[k],
        'team_id': s[0],
        'box_team_row': s[1],
        'association': _str(s[2:0xb]),
        'name': _str(s[0xb:0x1c]),
        'alt_name': _str(s[0x1c:0x2d]),
        'abbrev': _str(s[0x2d:0x32]),
        'players': players,
        'lineup': [{'pid': p, 'spot': s[0x3cb + i] + 1} for i, p in enumerate(order)],
        'pitchers': list(struct.unpack_from('<%dH' % m, s, 0x3f4)),
        'pitched_to': [dict(zip(('pid', 'entered_at_out', 'batters', 'outs'), struct.unpack_from('<4H', s, 0x445 + 8 * j)))
                       for j in range(c)],
        'runs': struct.unpack_from('<H', s, 0x50d)[0],
        'linescore': list(s[0x50f:0x52d]),
        'left_on_base': struct.unpack_from('<H', s, 0x52d)[0],
        'double_plays': struct.unpack_from('<H', s, 0x52f)[0],
        'triple_plays': struct.unpack_from('<H', s, 0x531)[0],
    }
    while len(side['linescore']) > 9 and side['linescore'][-1] == 0:
        side['linescore'].pop()
    for key, a, b in (('_unused_lineup', 0x37b + 2 * n, 0x3cb), ('_unused_spots', 0x3cb + n, 0x3f3),
                      ('_unused_pitchers', 0x3f4 + 2 * m, 0x444), ('_unused_pitched_to', 0x445 + 8 * c, 0x50d)):
        u = _unused(s, a, b)
        if u is not None:
            side[key] = u
    return side


def decode_game(body):
    t = body[TAIL:]
    serial = struct.unpack_from('<I', t, 0xc)[0]
    date = datetime.date.fromordinal(serial - SERIAL_EPOCH)
    secs = struct.unpack_from('<H', t, 0xa)[0]
    return {
        'game_type': t[0],
        'home_city': _str(t[1:0xa]),
        'time_of_game_seconds': secs,
        '_time_of_game': '%d:%02d' % (secs // 3600, secs // 60 % 60),
        'year': date.year, 'month': date.month, 'day': date.day,
        '_day_serial': serial,
        '_weekday': date.strftime('%A'),
        'outs': struct.unpack_from('<H', t, 0x10)[0],
        'wind_direction': t[0x12],
        '_wind_direction': WIND[t[0x12]] if t[0x12] < len(WIND) else None,
        'wind_mph': t[0x13],
        'sky': t[0x14],
        'temperature_f': t[0x15],
        'rain': {'kind': t[0x16], 'start_out': t[0x17], 'span_outs': t[0x18], 'delay_count': t[0x19],
                 'delay_outs': list(t[0x1a:0x1e]), 'delay_minutes': list(t[0x1e:0x22])},
    }


def decode(blob):
    if len(blob) < 10 + BODY or blob[:8] != HEAD:
        _fail('not a box-score file with a lineup card')
    body = decipher(blob[10:10 + BODY], blob[8:10])
    return {'game': decode_game(body), 'sides': [decode_side(body, 0), decode_side(body, 1)]}


# ---------------------------------------------------------------- encode

def encode_side(sd, k):
    s = bytearray(SIDE)
    s[0] = sd['team_id']
    s[1] = sd['box_team_row']
    _put_str(s, 2, 9, sd['association'], 'association')
    _put_str(s, 0xb, 17, sd['name'], 'name')
    _put_str(s, 0x1c, 17, sd.get('alt_name', ''), 'alt_name')
    _put_str(s, 0x2d, 5, sd['abbrev'], 'abbrev')
    used = set()
    for p in sd['players']:
        i = p['slot']
        if not 0 <= i < NSLOT or i in used:
            _fail(f'side {k}: bad or repeated slot {i}')
        if not p['pid']:
            _fail(f'side {k}: slot {i} has pid 0')
        used.add(i)
        mask = _mask(p['positions'], POS[:9]) | _mask(p.get('roles', []), POS[9:])
        role = POS.index(p['role']) + 1 if p.get('role') else 0
        struct.pack_into('<HHHB7H', s, 0x32 + SLOT * i, p['pid'], mask, _mask(p.get('started_at', []), POS), role,
                         *(p.get(x, 0) for x in SLOT_COUNTS))
    lineup, pitchers, notes = sd['lineup'], sd['pitchers'], sd.get('pitched_to', [])
    if len(lineup) > 40 or len(pitchers) > 40 or len(notes) > 25 or len(sd['linescore']) > 30:
        _fail(f'side {k}: a list is over its capacity')
    s[0x37a] = len(lineup)
    for i, e in enumerate(lineup):
        struct.pack_into('<H', s, 0x37b + 2 * i, e['pid'])
        s[0x3cb + i] = e['spot'] - 1
    s[0x3f3] = len(pitchers)
    struct.pack_into('<%dH' % len(pitchers), s, 0x3f4, *pitchers)
    s[0x444] = len(notes)
    for j, e in enumerate(notes):
        struct.pack_into('<4H', s, 0x445 + 8 * j, e['pid'], e['entered_at_out'], e['batters'], e['outs'])
    struct.pack_into('<H', s, 0x50d, sd['runs'])
    s[0x50f:0x50f + len(sd['linescore'])] = bytes(sd['linescore'])
    struct.pack_into('<3H', s, 0x52d, sd['left_on_base'], sd['double_plays'], sd['triple_plays'])
    for key, a in (('_unused_lineup', 0x37b + 2 * len(lineup)), ('_unused_spots', 0x3cb + len(lineup)),
                   ('_unused_pitchers', 0x3f4 + 2 * len(pitchers)), ('_unused_pitched_to', 0x445 + 8 * len(notes))):
        if sd.get(key):
            raw = bytes.fromhex(sd[key])
            s[a:a + len(raw)] = raw
    return bytes(s)


def encode_game(g):
    t = bytearray(BODY - TAIL)
    t[0] = g['game_type']
    _put_str(t, 1, 9, g['home_city'], 'home_city')
    serial = datetime.date(g['year'], g['month'], 1).toordinal() + g['day'] - 1 + SERIAL_EPOCH
    struct.pack_into('<HIH', t, 0xa, g['time_of_game_seconds'], serial, g['outs'])
    r = g['rain']
    t[0x12:0x1a] = bytes((g['wind_direction'], g['wind_mph'], g['sky'], g['temperature_f'],
                          r['kind'], r['start_out'], r['span_outs'], r['delay_count']))
    if len(r['delay_outs']) != 4 or len(r['delay_minutes']) != 4:
        _fail('rain delay_outs and delay_minutes hold exactly 4 entries')
    t[0x1a:0x22] = bytes(r['delay_outs'] + r['delay_minutes'])
    return bytes(t)


def encode(blob, doc):
    if len(blob) < 10 + BODY or blob[:8] != HEAD:
        _fail('not a box-score file with a lineup card')
    body = encode_side(doc['sides'][0], 0) + encode_side(doc['sides'][1], 1) + encode_game(doc['game'])
    return blob[:10] + encipher(body, blob[8:10]) + blob[10 + BODY:]


def main():
    if len(sys.argv) == 4 and sys.argv[1] == 'decode':
        with open(sys.argv[2], 'rb') as fh:
            doc = decode(fh.read())
        with open(sys.argv[3], 'w') as fh:
            json.dump(doc, fh, indent=1)
    elif len(sys.argv) == 5 and sys.argv[1] == 'encode':
        with open(sys.argv[2], 'rb') as fh:
            blob = fh.read()
        with open(sys.argv[3]) as fh:
            doc = json.load(fh)
        with open(sys.argv[4], 'wb') as fh:
            fh.write(encode(blob, doc))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
