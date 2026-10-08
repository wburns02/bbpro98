"""Codec for game.bki (BBShell -> sim: GDI/ADI setup records) and game.bko (sim -> BBShell: GDO event streams)
of FPS Baseball Pro '98.

usage: python3 voldat.py decode NAME in.bin out.json
       python3 voldat.py encode NAME in.bin edited.json out.bin        NAME = game.bki | game.bko

Layouts and evidence: FORMAT.md in this directory. Stdlib only; reads nothing but its arguments.
"""
import json
import struct
import sys

# ---------------------------------------------------------------- file cipher (ref/fpscipher.py, copied)


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
    return [t[t[t[x]]] for x in range(256)]


def _encipher(data, seed):
    f = _forward(seed)
    return bytes(f[b] for b in data)


def _decipher(data, seed):
    f = _forward(seed)
    inv = [0] * 256
    for x, y in enumerate(f):
        inv[y] = x
    return bytes(inv[b] for b in data)


# ---------------------------------------------------------------- chunk stream (tag, u32 length, payload)


def _chunks(blob):
    out, off = [], 0
    while off < len(blob):
        if off + 8 > len(blob):
            raise ValueError('trailing bytes after the last chunk')
        tag = blob[off:off + 4]
        n = struct.unpack_from('<I', blob, off + 4)[0]
        if off + 8 + n > len(blob):
            raise ValueError('chunk %r overruns the file' % tag)
        out.append((tag, blob[off + 8:off + 8 + n]))
        off += 8 + n
    return out


def _chunk(tag, payload):
    return tag + struct.pack('<I', len(payload)) + payload


# ---------------------------------------------------------------- shared string helpers


def _str_field(b, off, width):
    """NUL-terminated string in a fixed-width field. The field tail after the NUL is returned as a list of
    bytes when any of it is non-zero (leftover buffer bytes: kept so the rebuild is byte exact), else None."""
    raw = bytes(b[off:off + width])
    z = raw.find(b'\0')
    if z < 0:
        return raw.decode('latin1'), None
    tail = raw[z + 1:]
    return raw[:z].decode('latin1'), (list(tail) if tail.strip(b'\0') else None)


def _put_str(out, off, width, s, tail=None):
    raw = s.encode('latin1')
    if len(raw) > width:
        raise ValueError('string %r does not fit a %d-byte field' % (s, width))
    fill = [] if len(raw) == width else [0] + list(tail or [])
    fill = (fill + [0] * width)[:width - len(raw)]
    out[off:off + width] = raw + bytes(fill)


def _ints(b, off, n):
    return list(b[off:off + n])


# ================================================================ game.bki: GDI / ADI records
# GDI payload = 2 cipher seed bytes + 1029 record bytes enciphered with that seed.
# The record is two 490-byte team blocks (away at 0, home at 490) and a 49-byte tail.
# ADI payload = 12 bytes enciphered with the same seed.

REC_LEN = 1029
TEAM_LEN = 490
TEAM_BASES = (('away_team', 0), ('home_team', 490))


# (key, offset, width) of the NUL-terminated string fields of a team block
TEAM_STRINGS = (('team_name', 12, 34), ('manager', 46, 17), ('abbreviation', 63, 14), ('stadium', 77, 33),
                ('city', 110, 9), ('league', 473, 8))


def _team_decode(b):
    t = {}
    t['team_code'] = _ints(b, 0, 4)
    t['header_tail'] = _ints(b, 4, 8)
    junk = {}
    for key, off, width in TEAM_STRINGS:
        t[key], tail = _str_field(b, off, width)
        if tail is not None:
            junk[key] = tail
    tun = _ints(b, 119, 98)
    t['tuning_rows'] = [tun[i:i + 3] for i in range(0, 96, 3)]
    t['tuning_tail'] = tun[96:98]
    t['roster_pids'] = list(struct.unpack_from('<40H', b, 217))
    t['lineup_segments'] = _segments_decode(struct.unpack_from('<68H', b, 297))
    t['depth_table'] = _ints(b, 433, 40)
    t['team_flags'] = _ints(b, 481, 9)
    if junk:
        t['_junk_after_nul'] = junk
    return t


def _team_encode(t):
    b = bytearray(TEAM_LEN)
    b[0:4] = bytes(t['team_code'])
    b[4:12] = bytes(t['header_tail'])
    junk = t.get('_junk_after_nul', {})
    for key, off, width in TEAM_STRINGS:
        _put_str(b, off, width, t[key], junk.get(key))
    rows = [x for r in t['tuning_rows'] for x in r] + list(t['tuning_tail'])
    if len(rows) != 98:
        raise ValueError('tuning table must be 98 bytes')
    b[119:217] = bytes(rows)
    if len(t['roster_pids']) != 40:
        raise ValueError('roster table must list 40 slots')
    struct.pack_into('<40H', b, 217, *t['roster_pids'])
    words = _segments_encode(t['lineup_segments'])
    if len(words) != 68:
        raise ValueError('lineup region must be 68 words')
    struct.pack_into('<68H', b, 297, *words)
    b[433:473] = bytes(t['depth_table'])
    b[481:490] = bytes(t['team_flags'])
    return bytes(b)


def _segments_decode(words):
    """Split the lineup/staff words on their 0 or 0xffff separators. Each segment keeps its own end word;
    the last segment has end None (the region simply stops)."""
    segs, cur = [], []
    for w in words:
        if w in (0, 65535):
            segs.append({'pids': cur, 'end': w})
            cur = []
        else:
            cur.append(w)
    segs.append({'pids': cur, 'end': None})
    return segs


def _segments_encode(segs):
    words = []
    for i, s in enumerate(segs):
        words += list(s['pids'])
        if i < len(segs) - 1:
            if s['end'] not in (0, 65535):
                raise ValueError('segment end must be 0 or 65535')
            words.append(s['end'])
    return words


TAIL_STRINGS = (('home_city_echo', 1003, 9), ('box_score_file', 1012, 12))


def _tail_decode(d):
    t = {
        'game_code': _ints(d, 980, 4),
        'schedule_params': _ints(d, 984, 12),
        'game_seed': struct.unpack_from('<H', d, 996)[0],
        'shell_status': d[998],
        'ready_flag': d[999],
        'tail_flags': _ints(d, 1000, 3),
        'tail_words': _ints(d, 1024, 5),
    }
    junk = {}
    for key, off, width in TAIL_STRINGS:
        t[key], tail = _str_field(d, off, width)
        if tail is not None:
            junk[key] = tail
    if junk:
        t['_junk_after_nul'] = junk
    return t


def _tail_encode(d, t):
    junk = t.get('_junk_after_nul', {})
    for key, off, width in TAIL_STRINGS:
        _put_str(d, off, width, t[key], junk.get(key))
    d[980:984] = bytes(t['game_code'])
    d[984:996] = bytes(t['schedule_params'])
    struct.pack_into('<H', d, 996, t['game_seed'])
    d[998] = t['shell_status']
    d[999] = t['ready_flag']
    d[1000:1003] = bytes(t['tail_flags'])
    d[1024:1029] = bytes(t['tail_words'])


def _record_decode(rec):
    game = {}
    for key, base in TEAM_BASES:
        game[key] = _team_decode(rec[base:base + TEAM_LEN])
    game['record_tail'] = _tail_decode(rec)
    return game


def _record_encode(game):
    rec = bytearray(REC_LEN)
    for key, base in TEAM_BASES:
        rec[base:base + TEAM_LEN] = _team_encode(game[key])
    _tail_encode(rec, game['record_tail'])
    return bytes(rec)


def _adi_decode(a):
    return {
        'day_key': struct.unpack_from('<I', a, 0)[0],
        'day_key_copy': struct.unpack_from('<I', a, 4)[0],
        'game_no': struct.unpack_from('<H', a, 8)[0],
        'adi_flag': struct.unpack_from('<H', a, 10)[0],
    }


def _adi_encode(d):
    return struct.pack('<IIHH', d['day_key'], d['day_key_copy'], d['game_no'], d['adi_flag'])


ADI_LEN = 12
DIF_LEN = 72   # optional per-game block: BBSIM reads it right after the record, into its game-setup struct at +0x409


def _raw_chunk(tag, payload):
    return {'tag': tag.hex(), 'payload': list(payload)}


def bki_decode(blob):
    """A game is a GDI: chunk followed by its ADI: (and optional DIF:) chunks, up to the next GDI:. Chunks the
    codec does not know are kept verbatim; the order of a game's chunks is kept in its derived '_layout'."""
    games, leading, game, seed = [], [], None, None
    for tag, payload in _chunks(blob):
        if tag == b'GDI:':
            if len(payload) != 2 + REC_LEN:
                raise ValueError('GDI: chunk of %d bytes, expected %d' % (len(payload), 2 + REC_LEN))
            seed = payload[:2]
            game = {'cipher_seed': seed[0] | (seed[1] << 8)}
            game.update(_record_decode(_decipher(payload[2:], seed)))
            game['_layout'] = []
            games.append(game)
        elif game is None:
            leading.append(_raw_chunk(tag, payload))
        elif tag == b'ADI:' and len(payload) == ADI_LEN and 'adi' not in game:
            game['adi'] = _adi_decode(_decipher(payload, seed))
            game['_layout'].append('ADI:')
        elif tag == b'DIF:' and len(payload) == DIF_LEN and 'dif_block' not in game:
            game['dif_block'] = _ints(_decipher(payload, seed), 0, DIF_LEN)
            game['_layout'].append('DIF:')
        else:
            game.setdefault('_other_chunks', []).append(_raw_chunk(tag, payload))
            game['_layout'].append('other')
    doc = {'games': games}
    if leading:
        doc['_leading_chunks'] = leading
    return doc


def bki_encode(doc):
    out = bytearray()
    for c in doc.get('_leading_chunks', []):
        out += _chunk(bytes.fromhex(c['tag']), bytes(c['payload']))
    for game in doc['games']:
        v = game['cipher_seed']
        seed = bytes([v & 255, v >> 8])
        out += _chunk(b'GDI:', seed + _encipher(_record_encode(game), seed))
        others = list(game.get('_other_chunks', []))
        layout = game.get('_layout', ['ADI:'] + ['other'] * len(others))
        for item in layout:
            if item == 'ADI:':
                out += _chunk(b'ADI:', _encipher(_adi_encode(game['adi']), seed))
            elif item == 'DIF:':
                out += _chunk(b'DIF:', _encipher(bytes(game['dif_block']), seed))
            elif item == 'other':
                c = others.pop(0)
                out += _chunk(bytes.fromhex(c['tag']), bytes(c['payload']))
        for c in others:
            out += _chunk(bytes.fromhex(c['tag']), bytes(c['payload']))
    return bytes(out)


# ================================================================ game.bko: GDO event streams
# GDO payload = u16 little-endian words. Each record starts with its type word; sizes come from the sim's
# event-size table (BBSIM DAT_680b3238). Type names and field order follow the sim's event formatter
# (BBSIM FUN_68027ae8) and its label tables.

EVENT_WORDS = {0: 2, 1: 41, 2: 15, 3: 7, 4: 3, 5: 4, 6: 4, 7: 5, 8: 6}
KIND = {0: 'enter_game', 1: 'exit_game', 2: 'plate_appearance', 3: 'substitution', 4: 'team_stat',
        5: 'pitching_stat', 6: 'batting_stat', 7: 'fielding_stat', 8: 'injury'}
KIND_ID = {v: k for k, v in KIND.items()}
TEAM_STAT = ['RUN', 'ER', 'TP', 'DP', 'AB', 'B1', 'B2', 'B3']
PITCH_STAT = ['AB', 'B1', 'B2', 'B3', 'HR', 'RBI', 'BB', 'K', 'HBP', 'BBI', 'SH', 'SF', 'R', 'SB', 'CS', 'BFP',
              'ER', 'IR', 'IRS', 'PT', 'KT', 'WP', 'AB', 'B1', 'B2', 'B3']
BAT_STAT = ['AB', 'B1', 'B2', 'B3', 'HR', 'RBI', 'BB', 'K', 'HBP', 'BBI', 'SH', 'SF', 'R', 'SB', 'CS', 'GDP']
FIELD_STAT = ['PO', 'A', 'E', 'DP', 'PB']
SUB_KIND = ['PH', 'PR', 'RP', 'DS']
POSITION = ['', 'P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', '', '', 'D', 'B']
FIELD_SLOTS = ['pitcher', 'catcher', 'first_base', 'second_base', 'third_base', 'shortstop', 'left_field',
               'center_field', 'right_field']
PITCH_FLAGS = [(0x800, 'batter_lefty'), (0x400, 'pitcher_lefty'), (0x200, 'starter'), (0x100, 'closer')]


def _name(table, i):
    return table[i] if i < len(table) and table[i] else None


def _ev_decode(w):
    t = w[0]
    if t == 0:
        return {'enter_game': {'version': w[1]}}
    if t == 1:
        return {'exit_game': {
            'game_seconds': w[1], 'total_outs': w[2], 'unnamed_words_3_17': list(w[3:18]),
            'teams': [
                {'runs': w[18], 'hits': w[19], 'errors': w[20], 'left_on_base': w[21],
                 'unnamed_words_22_36': list(w[22:37])},
                {'runs': w[37], 'hits': w[38], 'errors': w[39], 'left_on_base': w[40]},
            ]}}
    if t == 2:
        f = {slot: w[1 + k] for k, slot in enumerate(FIELD_SLOTS)}
        f.update({'on_deck': w[10], 'batter': w[11], 'runner_on_first': w[12],
                  'runner_on_second': w[13], 'runner_on_third': w[14]})
        return {'plate_appearance': f}
    if t == 3:
        return {'substitution': {'team': w[1], 'player': w[2], 'sub_kind': w[3], 'batting_order': w[4],
                                 'position': w[5], 'br_field': w[6],
                                 '_kind_name': _name(SUB_KIND, w[3]), '_position_name': _name(POSITION, w[5])}}
    if t == 4:
        return {'team_stat': {'team': w[1], 'stat_index': w[2], '_stat_name': _name(TEAM_STAT, w[2])}}
    if t in (5, 6):
        table = PITCH_STAT if t == 5 else BAT_STAT
        f = {'team': w[1], ('pitcher' if t == 5 else 'batter'): w[2],
             'stat_index': w[3] & 255, 'flags': w[3] >> 8, '_stat_name': _name(table, w[3] & 255)}
        if t == 5:
            f['_flag_names'] = [n for bit, n in PITCH_FLAGS if w[3] & bit]
        return {'pitching_stat' if t == 5 else 'batting_stat': f}
    if t == 7:
        return {'fielding_stat': {'team': w[1], 'fielder': w[2], 'stat_index': w[3],
                                  'position_index': w[4], '_stat_name': _name(FIELD_STAT, w[3]),
                                  '_position_name': _name(POSITION, w[4])}}
    if t == 8:
        return {'injury': {'team': w[1], 'player': w[2], 'injury_type': w[3], 'duration': w[4],
                           'severity': w[5]}}
    raise ValueError('unknown event type %d' % t)


def _ev_encode(ev):
    (kind, f), = ev.items()
    t = KIND_ID[kind]
    if t == 0:
        w = [0, f['version']]
    elif t == 1:
        teams = f['teams']
        w = [1, f['game_seconds'], f['total_outs']] + list(f['unnamed_words_3_17'])
        w += [teams[0]['runs'], teams[0]['hits'], teams[0]['errors'], teams[0]['left_on_base']]
        w += list(teams[0]['unnamed_words_22_36'])
        w += [teams[1]['runs'], teams[1]['hits'], teams[1]['errors'], teams[1]['left_on_base']]
    elif t == 2:
        w = [2] + [f[slot] for slot in FIELD_SLOTS]
        w += [f['on_deck'], f['batter'], f['runner_on_first'], f['runner_on_second'], f['runner_on_third']]
    elif t == 3:
        w = [3, f['team'], f['player'], f['sub_kind'], f['batting_order'], f['position'], f['br_field']]
    elif t == 4:
        w = [4, f['team'], f['stat_index']]
    elif t in (5, 6):
        who = f['pitcher'] if t == 5 else f['batter']
        if f['stat_index'] > 255 or f['flags'] > 255:
            raise ValueError('stat_index and flags are bytes')
        w = [t, f['team'], who, f['stat_index'] | (f['flags'] << 8)]
    elif t == 7:
        w = [7, f['team'], f['fielder'], f['stat_index'], f['position_index']]
    elif t == 8:
        w = [8, f['team'], f['player'], f['injury_type'], f['duration'], f['severity']]
    else:
        raise ValueError('bad kind')
    if len(w) != EVENT_WORDS[t]:
        raise ValueError('event %s has %d words, expects %d' % (kind, len(w), EVENT_WORDS[t]))
    return w


def _gdo_decode(payload):
    if len(payload) % 2:
        raise ValueError('GDO payload is not whole u16 words')
    w = struct.unpack('<%dH' % (len(payload) // 2), payload)
    evs, i = [], 0
    while i < len(w):
        n = EVENT_WORDS.get(w[i])
        if n is None or i + n > len(w):
            raise ValueError('bad event type %d at word %d' % (w[i], i))
        evs.append(_ev_decode(w[i:i + n]))
        i += n
    return evs


BAT_ROW = ('ab', 'h', 'hr', 'rbi', 'bb', 'so', 'r', 'sb')
PIT_ROW = ('outs', 'bf', 'h', 'hr', 'bb', 'so', 'r')


def _replay(evs):
    """Box-score rows rebuilt from the events alone.

    A row exists when the player has a non-zero value in one of the row's own fields (batter: ab h hr rbi bb so r
    sb; pitcher: outs bf h hr bb so r). That rule drops a pinch runner whose only stat is a caught stealing (CS is
    not a row field; visible game day2 #0 pid 2019), and it never writes an all-zero row (none in 23 visible games).
    The sim calls the same appearance code for every substitute, so appearance alone cannot be the rule.

    Batter fields: AB -> ab; B1, B2, B3, HR -> h (HR also -> hr); RBI -> rbi; BB -> bb; K -> so; R -> r; SB -> sb.
    Pitcher fields: BFP -> bf; B1, B2, B3, HR -> h (HR also -> hr); BB -> bb; K -> so; R -> r.
    Pitcher outs: each PO putout is charged to the defensive pitcher of its fielding team. The sim keeps that
    pitcher in defensive slot 1 (BBSIM/Upstats FUN_6c003550 charges the PO to slot 1); slot 1 is the starter at
    first and changes on a relief substitution (sub_kind RP, Upstats FUN_6c001980 writes slot 1 directly).
    Any pitching event also names the team's pitcher, so `cur` follows both. A putout before a team's first
    pitching event belongs to its starter, the first pitcher the stream names for that team.
    """
    bat, pit, cur = {}, {}, {}
    first = {}
    rp = SUB_KIND.index('RP')
    for ev in evs:
        (kind, f), = ev.items()
        if kind == 'pitching_stat':
            first.setdefault(f['team'], f['pitcher'])

    def brow(pid):
        return bat.setdefault(pid, {'pid': pid, 'ab': 0, 'h': 0, 'hr': 0, 'rbi': 0, 'bb': 0, 'so': 0, 'r': 0,
                                    'sb': 0})

    def prow(pid):
        return pit.setdefault(pid, {'pid': pid, 'outs': 0, 'bf': 0, 'h': 0, 'hr': 0, 'bb': 0, 'so': 0, 'r': 0})

    for ev in evs:
        (kind, f), = ev.items()
        if kind == 'pitching_stat':
            code = f['_stat_name']
            p = prow(f['pitcher'])
            cur[f['team']] = f['pitcher']
            if code == 'BFP':
                p['bf'] += 1
            elif code in ('B1', 'B2', 'B3', 'HR'):
                p['h'] += 1
                p['hr'] += code == 'HR'
            elif code == 'BB':
                p['bb'] += 1
            elif code == 'K':
                p['so'] += 1
            elif code == 'R':
                p['r'] += 1
        elif kind == 'batting_stat':
            code = f['_stat_name']
            b = brow(f['batter'])
            if code == 'AB':
                b['ab'] += 1
            elif code in ('B1', 'B2', 'B3', 'HR'):
                b['h'] += 1
                b['hr'] += code == 'HR'
            elif code == 'RBI':
                b['rbi'] += 1
            elif code == 'BB':
                b['bb'] += 1
            elif code == 'K':
                b['so'] += 1
            elif code == 'R':
                b['r'] += 1
            elif code == 'SB':
                b['sb'] += 1
        elif kind == 'substitution' and f['sub_kind'] == rp:
            cur[f['team']] = f['player']
        elif kind == 'fielding_stat' and f['_stat_name'] == 'PO':
            owner = cur.get(f['team'], first.get(f['team']))
            if owner is not None:
                prow(owner)['outs'] += 1
    bat_rows = [b for b in bat.values() if any(b[k] for k in BAT_ROW)]
    pit_rows = [p for p in pit.values() if any(p[k] for k in PIT_ROW)]
    key = lambda r: r['pid']
    return sorted(bat_rows, key=key), sorted(pit_rows, key=key)


def bko_decode(blob):
    games, others = [], []
    for tag, payload in _chunks(blob):
        if tag == b'GDO:':
            evs = _gdo_decode(payload)
            batters, pitchers = _replay(evs)
            games.append({'events': evs, '_batters': batters, '_pitchers': pitchers})
        else:
            # not a game record: kept verbatim, with the number of games that precede it
            others.append(dict(_raw_chunk(tag, payload), before_game=len(games)))
    doc = {'games': games}
    if others:
        doc['_other_chunks'] = others
    return doc


def bko_encode(doc):
    out = bytearray()
    others = list(doc.get('_other_chunks', []))
    for k, game in enumerate(doc['games']):
        for c in [c for c in others if c['before_game'] == k]:
            out += _chunk(bytes.fromhex(c['tag']), bytes(c['payload']))
            others.remove(c)
        words = []
        for ev in game['events']:
            words += _ev_encode(ev)
        out += _chunk(b'GDO:', struct.pack('<%dH' % len(words), *words))
    for c in others:
        out += _chunk(bytes.fromhex(c['tag']), bytes(c['payload']))
    return bytes(out)


# ================================================================ command line


def main(argv):
    if len(argv) not in (5, 6) or argv[1] not in ('decode', 'encode'):
        raise SystemExit(__doc__)
    cmd, name = argv[1], argv[2]
    if name not in ('game.bki', 'game.bko'):
        raise SystemExit('NAME must be game.bki or game.bko')
    is_bki = name == 'game.bki'
    if cmd == 'decode' and len(argv) == 5:
        blob = open(argv[3], 'rb').read()
        doc = bki_decode(blob) if is_bki else bko_decode(blob)
        with open(argv[4], 'w') as fh:
            json.dump(doc, fh)
    elif cmd == 'encode' and len(argv) == 6:
        doc = json.load(open(argv[4]))
        out = bki_encode(doc) if is_bki else bko_encode(doc)
        with open(argv[5], 'wb') as fh:
            fh.write(out)
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
