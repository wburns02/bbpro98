#!/usr/bin/env python3
"""Semantic codec for game.bki / game.bko, the BBShell <-> simulator hand-off of FPS Baseball Pro '98.

  python3 voldat.py decode NAME in.bin out.json
  python3 voldat.py encode NAME in.bin edited.json out.bin        NAME = game.bki | game.bko

Layouts are documented in FORMAT.md.  Keys starting with "_" in the JSON are derived (or carry bytes whose meaning is
unknown but which must survive a rebuild); every other value is content and is what the encoder writes.
Python 3 standard library only.
"""
import sys
import json
import struct

# ----------------------------------------------------------------------------------------------------------------
# File cipher (BBShell FUN_68053450 builds the table from the two seed bytes, FUN_680534d0 applies it three times).


def _base_table(lo, hi):
    start = (lo - 1) & 255
    t = [start] * 256
    pos = 0
    v = lo
    for _ in range(256):
        t[pos] = v
        v = (v + 1) & 255
        pos = (pos + hi) & 255
        while t[pos] != start:
            pos = (pos + 1) & 255
    return t


def _forward(seed):
    t = _base_table(seed[0], seed[1])
    return bytes(t[t[t[x]]] for x in range(256))


def encipher(data, seed):
    f = _forward(seed)
    return bytes(f[b] for b in data)


def decipher(data, seed):
    f = _forward(seed)
    inv = bytearray(256)
    for x, y in enumerate(f):
        inv[y] = x
    return bytes(inv[b] for b in data)


# ----------------------------------------------------------------------------------------------------------------
# Chunk stream: 4-byte tag + u32 little-endian payload length + payload.


def read_chunks(blob):
    out, off = [], 0
    while off < len(blob):
        if off + 8 > len(blob):
            raise ValueError('truncated chunk header at %d' % off)
        tag = blob[off:off + 4].decode('latin1')
        ln = struct.unpack_from('<I', blob, off + 4)[0]
        if off + 8 + ln > len(blob):
            raise ValueError('chunk %s at %d overruns the file' % (tag, off))
        out.append((tag, blob[off + 8:off + 8 + ln]))
        off += 8 + ln
    return out


def chunk(tag, payload):
    return tag.encode('latin1') + struct.pack('<I', len(payload)) + bytes(payload)


# ----------------------------------------------------------------------------------------------------------------
# Small field helpers.  Every reader appends to a dict, every writer takes the dict back.


def u8(b, o):
    return b[o]


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def put_int(buf, o, size, v):
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError('integer expected, got %r' % (v,))
    if v < 0 or v >= 1 << (8 * size):
        raise ValueError('value %d does not fit in %d byte(s)' % (v, size))
    buf[o:o + size] = v.to_bytes(size, 'little')


def get_str(b, o, width, d, key):
    raw = bytes(b[o:o + width])
    n = raw.find(b'\0')
    n = width if n < 0 else n
    d[key] = raw[:n].decode('latin1')
    rest = raw[n + 1:]
    if rest.strip(b'\0'):
        d['_%s_residue' % key] = rest.hex()   # bytes after the terminator, kept so the rebuild is lossless


def put_str(buf, o, width, d, key):
    s = d.get(key, '')
    if not isinstance(s, str):
        raise ValueError('%s must be a string' % key)
    raw = s.encode('latin1')
    if len(raw) > width - 1:
        raise ValueError('%s is longer than the %d-byte field' % (key, width - 1))
    field = bytearray(width)
    field[:len(raw)] = raw
    res = d.get('_%s_residue' % key)
    if res:
        tail = bytes.fromhex(res)
        field[len(raw) + 1:len(raw) + 1 + len(tail)] = tail[:width - len(raw) - 1]
    buf[o:o + width] = field


def get_u16s(b, o, n):
    return list(struct.unpack_from('<%dH' % n, b, o))


def put_u16s(buf, o, n, vals, what):
    if not isinstance(vals, list) or len(vals) != n:
        raise ValueError('%s must be a list of %d ids' % (what, n))
    for i, v in enumerate(vals):
        put_int(buf, o + 2 * i, 2, v)


# ----------------------------------------------------------------------------------------------------------------
# game.bki: per game a GDI chunk (game setup, enciphered) followed by an ADI chunk (game date/index, enciphered with
# the same table).  Deciphered GDI = 1029 bytes = away team block (490) + home team block (490) + game block (49).

TEAM_SIZE = 490
GDI_SIZE = 1029
GDI_PAYLOAD = GDI_SIZE + 2
ADI_SIZE = 12

# park geometry: 32 (left, center, right) triples in five bands
BANDS = (('band_1', 6), ('band_2', 8), ('band_3', 8), ('band_4', 6), ('band_5', 4))
OPTIONS = (('injuries', 483), ('fatigue', 484), ('dh_rule', 485), ('use_ratings', 486),
           ('fielding_errors', 487), ('base_stealing', 488), ('pitch_to_center', 489))
LEVELS = (('pitching_level', 8), ('batting_level', 9), ('fielding_level', 10), ('running_level', 11))
STRINGS = (('city', 12, 17), ('nickname', 29, 17), ('manager', 46, 17), ('abbreviation', 63, 5),
           ('short_name', 68, 9), ('stadium', 77, 33), ('park_code', 110, 9))
BULLPEN = (('closer_pids', 417), ('setup_pids', 421), ('middle_relief_pids', 425), ('long_relief_pids', 429))


def decode_team(b):
    t = {}
    t['team_id'] = u8(b, 0)
    t['league_id'] = u8(b, 1)          # 0 NL, 1 AL
    t['division_id'] = u8(b, 2)        # 0 East, 1 Central, 2 West
    t['division_slot'] = u8(b, 3)      # alphabetical position inside the division
    t['computer_manager'] = u8(b, 4)
    t['_spare_5'] = u8(b, 5)
    t['managing_level'] = u8(b, 6)
    t['_spare_7'] = u8(b, 7)
    for k, o in LEVELS:
        t[k] = u8(b, o)
    for k, o, w in STRINGS:
        get_str(b, o, w, t, k)
    geo, o = {}, 119
    for k, n in BANDS:
        geo[k] = [[b[o + 3 * i], b[o + 3 * i + 1], b[o + 3 * i + 2]] for i in range(n)]
        o += 3 * n
    t['park_geometry'] = geo
    t['artificial_turf'] = u8(b, 215)
    t['_spare_216'] = u8(b, 216)
    ids = get_u16s(b, 217, 40)
    t['roster'] = [{'player_pid': ids[i], 'slot_rank': b[433 + i]} for i in range(40)]
    t['batting_order_pids'] = get_u16s(b, 297, 9)
    t['defense_pids'] = get_u16s(b, 315, 9)          # C 1B 2B 3B SS LF CF RF DH(0 = pitcher bats)
    cards = []
    for k in range(2):
        cards.append({'batting_order_pids': get_u16s(b, 333 + 18 * k, 9),
                      'defense_pids': get_u16s(b, 369 + 18 * k, 9)})
    t['lineup_cards'] = cards
    t['starting_pitcher_pid'] = u16(b, 405)
    t['rotation_pids'] = get_u16s(b, 407, 5)
    for k, o in BULLPEN:
        t[k] = get_u16s(b, o, 2)
    get_str(b, 473, 9, t, 'league_name')
    t['controller'] = u8(b, 482)
    t['options'] = {k: u8(b, o) for k, o in OPTIONS}
    return t


def encode_team(t):
    b = bytearray(TEAM_SIZE)
    for key, o in (('team_id', 0), ('league_id', 1), ('division_id', 2), ('division_slot', 3), ('computer_manager', 4),
                   ('_spare_5', 5), ('managing_level', 6), ('_spare_7', 7), ('artificial_turf', 215),
                   ('_spare_216', 216), ('controller', 482)):
        put_int(b, o, 1, t.get(key, 0))
    for k, o in LEVELS:
        put_int(b, o, 1, t[k])
    for k, o, w in STRINGS:
        put_str(b, o, w, t, k)
    o = 119
    for k, n in BANDS:
        rows = t['park_geometry'][k]
        if len(rows) != n:
            raise ValueError('park_geometry.%s needs %d rows' % (k, n))
        for i, row in enumerate(rows):
            if len(row) != 3:
                raise ValueError('park_geometry rows have three values')
            for j in range(3):
                put_int(b, o + 3 * i + j, 1, row[j])
        o += 3 * n
    roster = t['roster']
    if len(roster) != 40:
        raise ValueError('roster must have 40 slots')
    for i, e in enumerate(roster):
        put_int(b, 217 + 2 * i, 2, e['player_pid'])
        put_int(b, 433 + i, 1, e['slot_rank'])
    put_u16s(b, 297, 9, t['batting_order_pids'], 'batting_order_pids')
    put_u16s(b, 315, 9, t['defense_pids'], 'defense_pids')
    if len(t['lineup_cards']) != 2:
        raise ValueError('two lineup cards expected')
    for k, c in enumerate(t['lineup_cards']):
        put_u16s(b, 333 + 18 * k, 9, c['batting_order_pids'], 'card batting_order_pids')
        put_u16s(b, 369 + 18 * k, 9, c['defense_pids'], 'card defense_pids')
    put_int(b, 405, 2, t['starting_pitcher_pid'])
    put_u16s(b, 407, 5, t['rotation_pids'], 'rotation_pids')
    for k, o in BULLPEN:
        put_u16s(b, o, 2, t[k], k)
    put_str(b, 473, 9, t, 'league_name')
    for k, o in OPTIONS:
        put_int(b, o, 1, t['options'][k])
    return bytes(b)


def decode_game_block(b):
    g = {}
    w = {}
    w['wind_direction'] = u8(b, 0)      # 0 in-from-center, 1 in-from-left, 2 left-to-right, 3 out-to-right, ...
    w['wind_speed'] = u8(b, 1)
    w['sky_condition'] = u8(b, 2)       # 0 clear, 1 partly cloudy, 2 cloudy, 3 rain possible, 4 rainout possible
    w['temperature_f'] = u8(b, 3)
    w['rain_kind'] = u8(b, 4)           # 8 = no precipitation
    w['rain_start'] = u8(b, 5)
    w['rain_length'] = u8(b, 6)
    w['wind_shift_count'] = u8(b, 7)
    w['wind_shift_times'] = list(b[8:12])
    w['wind_shift_values'] = list(b[12:16])
    g['weather'] = w
    g['random_seed'] = u16(b, 16)
    g['sim_status'] = u8(b, 18)         # BBShell rewrites this byte (1 or 2) once the game has been run
    g['game_class'] = u8(b, 19)
    g['_spare_1000'] = u8(b, 20)
    g['_spare_1001'] = u8(b, 21)
    g['_spare_1002'] = u8(b, 22)
    get_str(b, 23, 9, g, 'home_park_code')
    get_str(b, 32, 14, g, 'box_score_file')
    g['artificial_turf'] = u8(b, 46)
    g['altitude_ft'] = u16(b, 47)
    return g


def encode_game_block(g):
    b = bytearray(49)
    w = g['weather']
    for key, o in (('wind_direction', 0), ('wind_speed', 1), ('sky_condition', 2), ('temperature_f', 3),
                   ('rain_kind', 4), ('rain_start', 5), ('rain_length', 6), ('wind_shift_count', 7)):
        put_int(b, o, 1, w[key])
    for key, o in (('wind_shift_times', 8), ('wind_shift_values', 12)):
        if len(w[key]) != 4:
            raise ValueError('%s needs four values' % key)
        for i, v in enumerate(w[key]):
            put_int(b, o + i, 1, v)
    put_int(b, 16, 2, g['random_seed'])
    put_int(b, 18, 1, g['sim_status'])
    put_int(b, 19, 1, g['game_class'])
    put_int(b, 20, 1, g.get('_spare_1000', 0))
    put_int(b, 21, 1, g.get('_spare_1001', 0))
    put_int(b, 22, 1, g.get('_spare_1002', 0))
    put_str(b, 23, 9, g, 'home_park_code')
    put_str(b, 32, 14, g, 'box_score_file')
    put_int(b, 46, 1, g['artificial_turf'])
    put_int(b, 47, 2, g['altitude_ft'])
    return bytes(b)


def decode_adi(plain):
    a = {}
    a['game_date_serial'] = u32(plain, 0)
    a['game_date_serial_copy'] = u32(plain, 4)
    a['game_index_in_day'] = u8(plain, 8)       # the box score file name ends in this index (hex digit)
    a['_spare_9'] = u8(plain, 9)
    a['_spare_10'] = u16(plain, 10)
    return a


def encode_adi(a):
    b = bytearray(ADI_SIZE)
    put_int(b, 0, 4, a['game_date_serial'])
    put_int(b, 4, 4, a['game_date_serial_copy'])
    put_int(b, 8, 1, a['game_index_in_day'])
    put_int(b, 9, 1, a.get('_spare_9', 0))
    put_int(b, 10, 2, a.get('_spare_10', 0))
    return bytes(b)


def decode_bki(blob):
    games, cur = [], None
    for tag, p in read_chunks(blob):
        if tag == 'GDI:' and len(p) == GDI_PAYLOAD:
            seed = p[:2]
            plain = decipher(p[2:], seed)
            cur = {'_cipher_seed': list(seed),
                   'away_team': decode_team(plain[:TEAM_SIZE]),
                   'home_team': decode_team(plain[TEAM_SIZE:2 * TEAM_SIZE]),
                   'game_setup': decode_game_block(plain[2 * TEAM_SIZE:])}
            games.append(cur)
        elif tag == 'ADI:' and cur is not None and len(p) == ADI_SIZE and 'adi' not in cur:
            cur['adi'] = decode_adi(decipher(p, cur['_cipher_seed']))
        else:
            raise ValueError('unexpected chunk %s (%d bytes)' % (tag, len(p)))
    return {'games': games}


def encode_bki(doc):
    out = bytearray()
    for g in doc['games']:
        seed = bytes(g['_cipher_seed'])
        if len(seed) != 2:
            raise ValueError('_cipher_seed needs two bytes')
        plain = encode_team(g['away_team']) + encode_team(g['home_team']) + encode_game_block(g['game_setup'])
        out += chunk('GDI:', seed + encipher(plain, seed))
        if 'adi' in g:
            out += chunk('ADI:', encipher(encode_adi(g['adi']), seed))
    return bytes(out)


# ----------------------------------------------------------------------------------------------------------------
# game.bko: per game a GDO chunk = the simulator's event log, a stream of u16 records.  Record types and sizes follow
# FastSim's FEVENT module (FUN_6801f748 prints them, FUN_680201d8..FUN_680203c9 build them).

EVENT_WORDS = {0: 2, 1: 41, 2: 15, 3: 7, 4: 3, 5: 4, 6: 4, 7: 5, 8: 6}
POSITIONS = ('pitcher', 'catcher', 'first_base', 'second_base', 'third_base', 'shortstop', 'left_field',
             'center_field', 'right_field')
RUNNER_SLOTS = ('on_deck', 'at_bat', 'first_base', 'second_base', 'third_base')
PITCH_STATS = ('ab', 'single', 'double', 'triple', 'hr', 'rbi', 'bb', 'so', 'hbp', 'ibb', 'sh', 'sf', 'run', 'sb', 'cs',
               'batters_faced', 'earned_run', 'inherited_runner', 'inherited_scored', 'pitches', 'strikes',
               'wild_pitch')
BAT_STATS = ('ab', 'single', 'double', 'triple', 'hr', 'rbi', 'bb', 'so', 'hbp', 'ibb', 'sh', 'sf', 'run', 'sb', 'cs',
             'gdp')
FIELD_PLAYS = ('putout', 'assist', 'error', 'double_play', 'passed_ball')
TEAM_EVENTS = ('run', 'earned_run', 'triple_play', 'double_play')
SUB_KINDS = ('pinch_hitter', 'pinch_runner', 'relief_pitcher', 'defensive_sub')
SIDES = ('away', 'home')
BLOCK_INNINGS = 30


# FastSim prints the high byte of a pitching/batting code as these four tags (bits 0x1, 0x2, 0x4, 0x8 of the byte)
FLAG_TAGS = ('CL', 'SP', 'PLH', 'BLH')


def flag_names(flags):
    return [FLAG_TAGS[i] for i in range(4) if flags >> i & 1]


def name_of(table, i):
    return table[i] if 0 <= i < len(table) else 'code_%d' % i


def decode_event(w):
    t = w[0]
    if t == 0:
        return {'enter_game': {'version': w[1]}}
    if t == 1:
        e = {'game_seconds': w[1], 'outs': w[2]}
        for k, side in enumerate(SIDES):
            blk = w[3 + 19 * k:22 + 19 * k]
            by = struct.pack('<15H', *blk[:15])[:BLOCK_INNINGS]
            runs = list(by)
            while runs and runs[-1] == 0:
                runs.pop()
            e[side] = {'runs_by_inning': runs, 'runs': blk[15], 'hits': blk[16], 'errors': blk[17],
                       'left_on_base': blk[18]}
        return {'exit_game': e}
    if t == 2:
        return {'plate_appearance': {
            'defense': {POSITIONS[i] + '_pid': w[1 + i] for i in range(9)},
            'runners': {RUNNER_SLOTS[i] + '_pid': w[10 + i] for i in range(5)}}}
    if t == 3:
        return {'substitution': {'team': w[1], 'player_pid': w[2], 'kind': w[3], 'batting_order': w[4],
                                 'position': w[5], 'base_runners': w[6], '_kind_name': name_of(SUB_KINDS, w[3])}}
    if t == 4:
        return {'team_event': {'team': w[1], 'event': w[2], '_event_name': name_of(TEAM_EVENTS, w[2])}}
    if t == 5:
        return {'pitching': {'team': w[1], 'pitcher_pid': w[2], 'stat': w[3] & 255, 'flags': w[3] >> 8,
                             '_stat_name': name_of(PITCH_STATS, w[3] & 255), '_flag_names': flag_names(w[3] >> 8)}}
    if t == 6:
        return {'batting': {'team': w[1], 'batter_pid': w[2], 'stat': w[3] & 255, 'flags': w[3] >> 8,
                            '_stat_name': name_of(BAT_STATS, w[3] & 255), '_flag_names': flag_names(w[3] >> 8)}}
    if t == 7:
        return {'fielding': {'team': w[1], 'fielder_pid': w[2], 'play': w[3], 'position': w[4],
                             '_play_name': name_of(FIELD_PLAYS, w[3])}}
    if t == 8:
        return {'injury': {'team': w[1], 'player_pid': w[2], 'kind': w[3], 'duration': w[4], 'severity': w[5]}}
    raise ValueError('unknown event type %d' % t)


def u16w(v, what):
    if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 65535:
        raise ValueError('%s must be an integer 0..65535, got %r' % (what, v))
    return v


def encode_event(ev):
    if not isinstance(ev, dict) or len(ev) != 1:
        raise ValueError('an event is an object with exactly one event-name key')
    (name, f), = ev.items()
    if name == 'enter_game':
        return [0, u16w(f['version'], 'version')]
    if name == 'exit_game':
        w = [1, u16w(f['game_seconds'], 'game_seconds'), u16w(f['outs'], 'outs')]
        for side in SIDES:
            s = f[side]
            runs = s['runs_by_inning']
            if len(runs) > BLOCK_INNINGS:
                raise ValueError('at most %d innings' % BLOCK_INNINGS)
            by = bytearray(BLOCK_INNINGS)
            for i, r in enumerate(runs):
                if isinstance(r, bool) or not isinstance(r, int) or not 0 <= r <= 255:
                    raise ValueError('runs per inning must be 0..255')
                by[i] = r
            w += list(struct.unpack('<15H', bytes(by)))
            w += [u16w(s['runs'], 'runs'), u16w(s['hits'], 'hits'), u16w(s['errors'], 'errors'),
                  u16w(s['left_on_base'], 'left_on_base')]
        return w
    if name == 'plate_appearance':
        d, r = f['defense'], f['runners']
        return ([2] + [u16w(d[p + '_pid'], 'defense') for p in POSITIONS]
                + [u16w(r[s + '_pid'], 'runners') for s in RUNNER_SLOTS])
    if name == 'substitution':
        return [3] + [u16w(f[k], k) for k in ('team', 'player_pid', 'kind', 'batting_order', 'position',
                                              'base_runners')]
    if name == 'team_event':
        return [4, u16w(f['team'], 'team'), u16w(f['event'], 'event')]
    if name in ('pitching', 'batting'):
        stat, flags = f['stat'], f['flags']
        for v in (stat, flags):
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255:
                raise ValueError('stat and flags are bytes')
        who = 'pitcher_pid' if name == 'pitching' else 'batter_pid'
        return [5 if name == 'pitching' else 6, u16w(f['team'], 'team'), u16w(f[who], who), flags << 8 | stat]
    if name == 'fielding':
        return [7] + [u16w(f[k], k) for k in ('team', 'fielder_pid', 'play', 'position')]
    if name == 'injury':
        return [8] + [u16w(f[k], k) for k in ('team', 'player_pid', 'kind', 'duration', 'severity')]
    raise ValueError('unknown event name %r' % name)


def replay(events):
    """Box score rows from the decoded events (only the events are used)."""
    bat, pit, outs, cur = {}, {}, {}, {}
    zero = ('ab', 'h', 'hr', 'rbi', 'bb', 'so', 'r', 'sb')
    pzero = ('outs', 'bf', 'h', 'hr', 'bb', 'so', 'r')
    for ev in events:
        (name, f), = ev.items()
        if name == 'batting':
            row = bat.setdefault(f['batter_pid'], dict.fromkeys(zero, 0))
            s = f['stat']
            if s == 0:
                row['ab'] += 1
            elif 1 <= s <= 4:
                row['h'] += 1
                if s == 4:
                    row['hr'] += 1
            elif s == 5:
                row['rbi'] += 1
            elif s == 6:
                row['bb'] += 1
            elif s == 7:
                row['so'] += 1
            elif s == 12:
                row['r'] += 1
            elif s == 13:
                row['sb'] += 1
        elif name == 'pitching':
            cur[f['team']] = f['pitcher_pid']
            row = pit.setdefault(f['pitcher_pid'], dict.fromkeys(pzero, 0))
            s = f['stat']
            if s == 15:
                row['bf'] += 1
            elif 1 <= s <= 4:
                row['h'] += 1
                if s == 4:
                    row['hr'] += 1
            elif s == 6:
                row['bb'] += 1
            elif s == 7:
                row['so'] += 1
            elif s == 12:
                row['r'] += 1
        elif name == 'substitution':
            if f['kind'] == 2 or (f['kind'] == 3 and f['position'] == 1):
                cur[f['team']] = f['player_pid']
        elif name == 'fielding':
            if f['play'] == 0 and f['team'] in cur:        # a putout is an out charged to the pitcher on the mound
                p = pit.setdefault(cur[f['team']], dict.fromkeys(pzero, 0))
                p['outs'] += 1
    b = [dict(pid=k, **v) for k, v in bat.items() if any(v.values())]
    p = [dict(pid=k, **v) for k, v in pit.items() if any(v.values())]
    return b, p


def decode_gdo(payload):
    if len(payload) % 2:
        raise ValueError('odd GDO payload')
    w = struct.unpack('<%dH' % (len(payload) // 2), payload)
    i, events = 0, []
    while i < len(w):
        n = EVENT_WORDS.get(w[i])
        if n is None or i + n > len(w):
            raise ValueError('bad event record at word %d' % i)
        events.append(decode_event(w[i:i + n]))
        i += n
    bat, pit = replay(events)
    game = {'events': events, '_batters': bat, '_pitchers': pit}
    last = events[-1].get('exit_game') if events else None
    if last:
        game['_final_score'] = {'away': last['away']['runs'], 'home': last['home']['runs']}
    return game


def decode_bko(blob):
    games = []
    for tag, p in read_chunks(blob):
        if tag != 'GDO:':
            raise ValueError('unexpected chunk %s' % tag)
        games.append(decode_gdo(p))
    return {'games': games}


def encode_bko(doc):
    out = bytearray()
    for g in doc['games']:
        words = []
        for ev in g['events']:
            words += encode_event(ev)
        out += chunk('GDO:', struct.pack('<%dH' % len(words), *words))
    return bytes(out)


# ----------------------------------------------------------------------------------------------------------------


def main(argv):
    if len(argv) >= 5 and argv[1] == 'decode':
        name = argv[2]
        blob = open(argv[3], 'rb').read()
        doc = decode_bki(blob) if name.endswith('.bki') else decode_bko(blob)
        with open(argv[4], 'w') as fh:
            json.dump(doc, fh)
    elif len(argv) >= 6 and argv[1] == 'encode':
        name = argv[2]
        doc = json.load(open(argv[4]))
        out = encode_bki(doc) if name.endswith('.bki') else encode_bko(doc)
        with open(argv[5], 'wb') as fh:
            fh.write(out)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
