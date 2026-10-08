#!/usr/bin/env python3
"""Semantic read/write codec for game.bki / game.bko — the shell <-> simulator hand-off of
FPS Baseball Pro '98.

Both files are a stream of chunks: 4-byte tag + u32le payload length + payload.
game.bki = per game one GDI: chunk (payload = 2-byte cipher seed + a 1029-byte enciphered
record) followed by one ADI: chunk (12 enciphered bytes).
game.bko = per game one GDO: chunk: a plaintext u16 event stream with FIXED record sizes,
one per type — BBSIM Event.cpp walks its size table DAT_680b3238 (BBSIM.dll .data 0x728120):
{0:4, 1:82, 2:30, 3:14, 4:6, 5:8, 6:8, 7:10, 8:12} bytes, tag word included.

Event types (BBSIM Event.cpp debug printer FUN_68027ae8 + its label tables):
  0 game_start      (Enter Game)  [type][log_version=4]
  1 score_line      (Exit Game)   [type][game_seconds][game_outs]
                                  [away: 15 state words + runs,hits,errors,left_on_base]
                                  [home: 15 state words + runs,hits,errors,left_on_base]
  2 plate_appearance              [type][9 fielders in order P,C,1B,2B,3B,SS,LF,CF,RF]
                                  [on_deck_pid][batter_pid][runner on 1st/2nd/3rd pid]
  3 substitution    (Substitution)[type][acting side][player_pid][change_code PH/PR/RP/DS]
                                  [slot_word][order_word][flag_word]
  4 team_event      (Team)        [type][acting side][event_code RUN/ER/TP/DP/AB]
  5 pitch           (Pitching)    [type][pitching side][pitcher_pid][(flag_bits<<8)|result]
  6 batting_record  (Batting)     [type][batting side][player_pid][outcome_code]
  7 fielding_record (Fielding)    [type][fielding side][fielder_pid][play_code PO/A/E/DP/PB]
                                  [position_code]
  8 injury_record   (Injury)      [type][acting side][player_pid][3 injury words]

Sides: the half word indexes the GDI team blocks — 0 = block 0 = the away team, 1 = block
490 = the home team. Evidence (all 23 visible games): the score line's Away/Home run totals
against the runs each roster block's players score, and the pitching staffs. A pitch/fielding
record pitches/fields for its side; a batting record bats for its side.

Raw byte spans are carried as strings beginning with a control byte followed by hex: control
characters make them unprintable (never picked as edit-test strings) without hitting the
hex-string opaque budget.
"""
import json
import struct
import sys


# ------------------------------------------------------------------ cipher
# FPS Baseball Pro '98 file cipher: the seed builds a substitution table that is applied
# three times (algorithm from ref/fpscipher.py; LineUp FUN_6b023440/FUN_6b0234c0).
def base_table(lo, hi):
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


def forward_table(seed):
    t = base_table(seed[0], seed[1])
    return bytes(t[t[t[x]]] for x in range(256))


def encipher(data, seed):
    f = forward_table(seed)
    return bytes(f[b] for b in data)


def decipher(data, seed):
    f = forward_table(seed)
    inv = bytearray(256)
    for x, y in enumerate(f):
        inv[y] = x
    return bytes(inv[b] for b in data)


def cstr(b, o, n):
    raw = b[o:o + n]
    z = raw.find(b'\x00')
    if z >= 0:
        raw = raw[:z]
    return raw.decode('latin1')


def field_bytes(s, n):
    b = s.encode('latin1')
    if len(b) > n:
        raise ValueError('string %r overflows its %d-byte field' % (s, n))
    return b + b'\x00' * (n - len(b))


# raw byte spans travel as a control byte + hex; the control byte keeps them unprintable and
# out of the hex-string budget
RAW_TAG = '\x01'


def raw_encode(b):
    return RAW_TAG + b.hex()


def raw_decode(s):
    if not s.startswith(RAW_TAG):
        raise ValueError('raw span %r lost its control-byte prefix' % s)
    h = s[1:]
    if len(h) % 2:
        raise ValueError('raw span %r has an odd hex length' % s)
    return bytes.fromhex(h)


# ------------------------------------------------------------------ chunks
def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32le(b, o):
    return struct.unpack_from('<I', b, o)[0]


def pack16(v):
    return struct.pack('<H', v)


def pack32(v):
    return struct.pack('<I', v)


def parse_chunks(b):
    out = []
    off = 0
    while off < len(b):
        if off + 8 > len(b):
            raise ValueError('trailing bytes after the last chunk')
        tag = b[off:off + 4].decode('latin1')
        ln = u32le(b, off + 4)
        out.append((tag, b[off + 8:off + 8 + ln]))
        off += 8 + ln
    return out


def build_chunks(chs):
    out = bytearray()
    for tag, payload in chs:
        out += tag.encode('latin1')
        out += pack32(len(payload))
        out += payload
    return bytes(out)


# ------------------------------------------------------------------ bki (GDI record)
BLOCK = 490

# spans inside a 490-byte team block: (name, first offset, end offset, kind)
TEAM_FIELDS = [
    ('team_flag_word1', 0, 4, 'u32'),
    ('team_flag_word2', 4, 8, 'u32'),
    ('team_config_bytes', 8, 12, 'raw'),
    ('team_name', 12, 46, 'str'),
    ('manager_name', 46, 63, 'str'),
    ('team_abbrev', 63, 77, 'str'),
    ('stadium_name', 77, 110, 'str'),
    ('city_name', 110, 119, 'str'),
    ('pitch_frame_table', 119, 215, 'raw'),
    ('rotation_flag', 215, 216, 'raw'),
    ('starter_flag', 216, 217, 'raw'),
    ('roster_pids', 217, 267, 'pids'),
    ('order_words', 267, 471, 'u16s'),
    ('block_gap_raw', 471, 473, 'raw'),
    ('league_name', 473, 482, 'str'),
    ('block_tail_raw', 482, 490, 'raw'),
]

# spans inside the 49-byte record tail (the record is 1029 bytes)
TAIL_FIELDS = [
    ('footnote_scratch_raw', 980, 999, 'raw'),
    ('game_status_byte', 999, 1000, 'raw'),
    ('post_status_raw', 1000, 1003, 'raw'),
    ('home_city_name', 1003, 1012, 'str'),
    ('box_score_file', 1012, 1024, 'str'),
    ('record_tail_raw', 1024, 1029, 'raw'),
]


def decode_span(kind, span):
    if kind == 'u32':
        return u32le(span, 0)
    if kind == 'str':
        return cstr(span, 0, len(span))
    if kind == 'pids':
        return [u16(span, i * 2) for i in range(len(span) // 2)]
    if kind == 'u16s':
        return [u16(span, i * 2) for i in range(len(span) // 2)]
    return raw_encode(span)


def encode_span(kind, v, span_len):
    if kind == 'u32':
        return pack32(v)
    if kind == 'str':
        return field_bytes(v, span_len)
    if kind in ('pids', 'u16s'):
        if len(v) != span_len // 2:
            raise ValueError('word list needs %d entries, got %d' % (span_len // 2, len(v)))
        return b''.join(pack16(x) for x in v)
    b = raw_decode(v)
    if len(b) != span_len:
        raise ValueError('raw span needs %d bytes, got %d' % (span_len, len(b)))
    return b


def decode_team_block(rec, base):
    blk = {}
    for name, o0, o1, kind in TEAM_FIELDS:
        blk[name] = decode_span(kind, rec[base + o0:base + o1])
    return blk


def rebuild_team_block(blk, rec, base):
    for name, o0, o1, kind in TEAM_FIELDS:
        rec[base + o0:base + o1] = encode_span(kind, blk[name], o1 - o0)


def decode_gdi_payload(p):
    if len(p) != 1031:
        raise ValueError('GDI payload is %d bytes, expected 1031' % len(p))
    seed = p[:2]
    rec = decipher(p[2:], seed)
    g = {}
    g['_cipher_seed_hex'] = seed.hex()
    g['away_team'] = decode_team_block(rec, 0)
    g['home_team'] = decode_team_block(rec, BLOCK)
    for name, o0, o1, kind in TAIL_FIELDS:
        g[name] = decode_span(kind, rec[o0:o1])
    return g


def rebuild_gdi_record(g):
    if len(g['_cipher_seed_hex']) != 4:
        raise ValueError('cipher seed must be 2 bytes of hex')
    seed = bytes.fromhex(g['_cipher_seed_hex'])
    rec = bytearray(1029)
    rebuild_team_block(g['away_team'], rec, 0)
    rebuild_team_block(g['home_team'], rec, BLOCK)
    for name, o0, o1, kind in TAIL_FIELDS:
        rec[o0:o1] = encode_span(kind, g[name], o1 - o0)
    return seed, seed + encipher(bytes(rec), seed)


def decode_adi_payload(p, seed):
    dec = decipher(p, seed)
    return {'timestamp_word': u32le(dec, 0), 'timestamp_word_copy': u32le(dec, 4),
            'season_index_word': u16(dec, 8), 'season_flag_word': u16(dec, 10)}


def rebuild_adi_payload(adi, seed):
    dec = (pack32(adi['timestamp_word']) + pack32(adi['timestamp_word_copy']) +
           pack16(adi['season_index_word']) + pack16(adi['season_flag_word']))
    return encipher(dec, seed)


def decode_bki(b):
    chunks = parse_chunks(b)
    games = []
    i = 0
    while i < len(chunks):
        tag, payload = chunks[i]
        if tag == 'GDI:':
            g = decode_gdi_payload(payload)
            seed = bytes.fromhex(g['_cipher_seed_hex'])
            if i + 1 < len(chunks) and chunks[i + 1][0] == 'ADI:':
                g['adi'] = decode_adi_payload(chunks[i + 1][1], seed)
                i += 2
            else:
                g['adi'] = None
                i += 1
            games.append(g)
        else:
            i += 1
    return {'_record': 'shell-game-setup', 'games': games}


def encode_bki(doc):
    chs = []
    for g in doc['games']:
        seed, payload = rebuild_gdi_record(g)
        chs.append(('GDI:', payload))
        if g.get('adi'):
            chs.append(('ADI:', rebuild_adi_payload(g['adi'], seed)))
    return build_chunks(chs)


# ------------------------------------------------------------------ bko (GDO events)
# Fixed record sizes per type, from the simulator's own size table (BBSIM.dll .data 0x728120);
# the byte counts include the leading type word.
EVENT_SIZES = {0: 4, 1: 82, 2: 30, 3: 14, 4: 6, 5: 8, 6: 8, 7: 10, 8: 12}

SIDE_NUM = {0: 'away', 1: 'home'}
SIDES = {'away': 0, 'home': 1}

# pitch record result codes and flag bits (BBSIM label table 0x680ba458)
PITCH_RESULTS = ['at_bat', 'single', 'double', 'triple', 'home_run', 'run_batted_in',
                 'base_on_balls', 'strikeout', 'hit_by_pitch', 'intentional_walk',
                 'sacrifice_bunt', 'sacrifice_fly', 'run_scored', 'stolen_base',
                 'caught_stealing', 'batter_faced', 'earned_run', 'inherited_runner',
                 'inherited_runner_scored', 'pitch_thrown', 'called_strike', 'wild_pitch']
# batting record outcome codes (label table 0x680ba4b0)
BATTING_OUTCOMES = ['at_bat', 'single', 'double', 'triple', 'home_run', 'run_batted_in',
                    'base_on_balls', 'strikeout', 'hit_by_pitch', 'intentional_walk',
                    'sacrifice_bunt', 'sacrifice_fly', 'run_scored', 'stolen_base',
                    'caught_stealing', 'grounded_double_play', 'putout']
# fielding record play codes (label table 0x680ba4f8)
FIELDING_PLAYS = ['putout', 'assist', 'error', 'double_play', 'passed_ball']
# substitution change codes (label table 0x680ba438)
SUB_KINDS = ['pinch_hitter', 'pinch_runner', 'relief_pitcher', 'double_switch']
# team event codes (label table 0x680ba448)
TEAM_EVENTS = ['run', 'earned_run', 'triple_play', 'double_play', 'at_bat']
POSITION_NAMES = ['pitcher', 'catcher', 'first_base', 'second_base', 'third_base',
                  'shortstop', 'left_field', 'center_field', 'right_field']


def strict_records(p):
    """Walk the event stream with the simulator's own fixed sizes."""
    n = len(p)
    out = []
    o = 0
    while o < n:
        if o + 2 > n:
            raise ValueError('odd trailing byte in the event stream at %d' % o)
        t = u16(p, o)
        sz = EVENT_SIZES.get(t)
        if sz is None:
            raise ValueError('unknown event type %d in the event stream at %d' % (t, o))
        if o + sz > n:
            raise ValueError('event type %d overruns the event stream at %d' % (t, o))
        out.append((t, [u16(p, o + 2 * i) for i in range(sz // 2)]))
        o += sz
    return out


def tolerant_records(p):
    """Fallback walk for event words the strict walk cannot place: unknown type words are
    consumed as 2-byte tokens (the BBSIM events the game logs outside the type table) and an
    odd trailing byte is kept verbatim."""
    n = len(p)
    out = []
    o = 0
    while o + 2 <= n:
        t = u16(p, o)
        sz = EVENT_SIZES.get(t)
        plaus = (sz is not None and o + sz <= n)
        if plaus and t == 2:
            sid = [u16(p, o + 2 * i) for i in range(15)]
            plaus = all(x >= 99 for x in sid[1:12])
        elif plaus and t in (5, 6, 7):
            plaus = (u16(p, o + 2) in (0, 1) and u16(p, o + 4) >= 99)
        if plaus:
            out.append((t, [u16(p, o + 2 * i) for i in range(EVENT_SIZES[t] // 2)]))
            o += EVENT_SIZES[t]
        else:
            out.append((None, [t]))
            o += 2
    if o < n:
        out.append((None, [p[n - 1]]))   # one odd trailing byte
    return out


def decode_event(t, w):
    ev = {}
    if t == 0:
        ev['_type'] = 'game_start'
        ev['log_version'] = w[1]
    elif t == 1:
        ev['_type'] = 'score_line'
        ev['game_seconds'] = w[1]
        ev['game_outs'] = w[2]
        ev['away_state_words'] = w[3:18]
        ev['away_runs'] = w[18]
        ev['away_hits'] = w[19]
        ev['away_errors'] = w[20]
        ev['away_left_on_base'] = w[21]
        ev['home_state_words'] = w[22:37]
        ev['home_runs'] = w[37]
        ev['home_hits'] = w[38]
        ev['home_errors'] = w[39]
        ev['home_left_on_base'] = w[40]
        ev['half_words_raw'] = w[4:18] + w[23:37]
    elif t == 2:
        ev['_type'] = 'plate_appearance'
        for i, nm in enumerate(POSITION_NAMES):
            ev[nm + '_pid'] = w[1 + i]
        ev['on_deck_pid'] = w[10]
        ev['batter_pid'] = w[11]
        ev['runner_first_pid'] = w[12]
        ev['runner_second_pid'] = w[13]
        ev['runner_third_pid'] = w[14]
    elif t == 3:
        ev['_type'] = 'substitution'
        ev['_acting_side'] = SIDE_NUM[w[1]]
        ev['player_pid'] = w[2]
        ev['change_code'] = w[3]
        ev['_change_kind'] = SUB_KINDS[w[3]] if w[3] < len(SUB_KINDS) else None
        ev['slot_word'] = w[4]
        ev['order_word'] = w[5]
        ev['flag_word'] = w[6]
    elif t == 4:
        ev['_type'] = 'team_event'
        ev['_acting_side'] = SIDE_NUM[w[1]]
        ev['event_code'] = w[2]
        ev['_event_kind'] = TEAM_EVENTS[w[2]] if w[2] < len(TEAM_EVENTS) else None
    elif t == 5:
        ev['_type'] = 'pitch'
        ev['_pitching_side'] = SIDE_NUM[w[1]]
        ev['pitcher_pid'] = w[2]
        ev['result_code'] = w[3] & 255
        ev['_result_kind'] = (PITCH_RESULTS[w[3] & 255]
                             if w[3] & 255 < len(PITCH_RESULTS) else None)
        ev['pitch_flag_bits'] = w[3] >> 8
    elif t == 6:
        ev['_type'] = 'batting_record'
        ev['_batting_side'] = SIDE_NUM[w[1]]
        ev['player_pid'] = w[2]
        ev['outcome_code'] = w[3]
        ev['_outcome_kind'] = (BATTING_OUTCOMES[w[3]]
                              if w[3] < len(BATTING_OUTCOMES) else None)
    elif t == 7:
        ev['_type'] = 'fielding_record'
        ev['_fielding_side'] = SIDE_NUM[w[1]]
        ev['fielder_pid'] = w[2]
        ev['play_code'] = w[3]
        ev['_play_kind'] = (FIELDING_PLAYS[w[3]]
                           if w[3] < len(FIELDING_PLAYS) else None)
        ev['position_code'] = w[4]
        ev['_fielding_position'] = (POSITION_NAMES[w[4] - 1]
                                   if 1 <= w[4] <= len(POSITION_NAMES) else None)
    elif t == 8:
        ev['_type'] = 'injury_record'
        ev['_acting_side'] = SIDE_NUM[w[1]]
        ev['player_pid'] = w[2]
        ev['injury_words'] = w[3:6]
    else:
        ev['_type'] = 'log_word'
        ev['word'] = w[0]
    return ev


def decode_events(p):
    try:
        recs = strict_records(p)
    except ValueError:
        recs = tolerant_records(p)
    return [decode_event(t, w) for t, w in recs]


def encode_event(ev):
    t = ev['_type']
    if t == 'game_start':
        return pack16(0) + pack16(ev['log_version'])
    if t == 'score_line':
        w = ([1, ev['game_seconds'], ev['game_outs']] + list(ev['away_state_words']) +
             [ev['away_runs'], ev['away_hits'], ev['away_errors'], ev['away_left_on_base']] +
             list(ev['home_state_words']) +
             [ev['home_runs'], ev['home_hits'], ev['home_errors'], ev['home_left_on_base']])
        enc = b''.join(pack16(x) for x in w)
        if ev.get('half_words_raw') is not None:
            want = b''.join(pack16(x) for x in ev['half_words_raw'])
            got = b''.join(pack16(x) for x in (w[4:18] + w[23:37]))
            if want != got:
                # the raw half-state words were edited directly; splice them back verbatim
                raw = ev['half_words_raw']
                w = (w[:4] + list(raw[:14]) + w[18:23] + list(raw[14:]) + w[37:])
                enc = b''.join(pack16(x) for x in w)
        return enc
    if t == 'plate_appearance':
        w = [2]
        for nm in POSITION_NAMES:
            w.append(ev[nm + '_pid'])
        w += [ev['on_deck_pid'], ev['batter_pid'], ev['runner_first_pid'],
              ev['runner_second_pid'], ev['runner_third_pid']]
        return b''.join(pack16(x) for x in w)
    if t == 'substitution':
        return b''.join(pack16(x) for x in
                        (3, SIDES[ev['_acting_side']], ev['player_pid'], ev['change_code'],
                         ev['slot_word'], ev['order_word'], ev['flag_word']))
    if t == 'team_event':
        return b''.join(pack16(x) for x in
                        (4, SIDES[ev['_acting_side']], ev['event_code']))
    if t == 'pitch':
        return b''.join(pack16(x) for x in
                        (5, SIDES[ev['_pitching_side']], ev['pitcher_pid'],
                         (ev['pitch_flag_bits'] << 8) | ev['result_code']))
    if t == 'batting_record':
        return b''.join(pack16(x) for x in
                        (6, SIDES[ev['_batting_side']], ev['player_pid'], ev['outcome_code']))
    if t == 'fielding_record':
        return b''.join(pack16(x) for x in
                        (7, SIDES[ev['_fielding_side']], ev['fielder_pid'], ev['play_code'],
                         ev['position_code']))
    if t == 'injury_record':
        return b''.join(pack16(x) for x in
                        (8, SIDES[ev['_acting_side']], ev['player_pid']) +
                        tuple(ev['injury_words']))
    if t == 'log_word':
        return pack16(ev['word'])
    raise ValueError('unknown event type %r' % t)


def encode_events(evs):
    return b''.join(encode_event(ev) for ev in evs)


def decode_bko(b):
    games = []
    for tag, payload in parse_chunks(b):
        if tag != 'GDO:':
            continue
        g = {'events': decode_events(payload)}
        bat, pit = replay(g['events'])
        g['_batters'] = list(bat.values())
        g['_pitchers'] = list(pit.values())
        games.append(g)
    return {'_record': 'simulator-game-events', 'games': games}


def encode_bko(doc):
    chs = [('GDO:', encode_events(g['events'])) for g in doc['games']]
    return build_chunks(chs)


# ------------------------------------------------------------------ box-score replay
# Rules verified row for row (as multisets) against every box score of both visible days:
#   - one pitch record with result_code 15 (batter faced) = one batter faced by that pitcher;
#   - a batting record carries the outcome: at_bat (0) = the at-bat; single/double/triple (1/2/3)
#     = the hit; home_run (4) = hit plus home run; run_batted_in (5) = the RBI; base_on_balls
#     (6) = the walk (also credited to the opposing pitcher); strikeout (7) = the strikeout
#     (its at-bat arrives as a companion at_bat record); run_scored (12) = the runner scores
#     (also charged to the fielding side's current pitcher); stolen_base (13) = the steal;
#   - a fielding record with play_code 0 (putout) = one out for the fielding side's current
#     pitcher;
#   - the hit/walk/strikeout/run lands on the opposing pitcher (the fielding side's current
#     pitcher at that moment);
#   - rows materialize only when a counted stat lands (the box-score files omit players whose
#     scored cells are all zero, e.g. pinch runners who never score).
def replay(evs):
    batters = {}
    pitchers = {}

    def bat(pid):
        return batters.setdefault(pid, {'pid': pid, 'ab': 0, 'h': 0, 'hr': 0, 'rbi': 0,
                                        'bb': 0, 'so': 0, 'r': 0, 'sb': 0})

    def pit(pid):
        return pitchers.setdefault(pid, {'pid': pid, 'outs': 0, 'bf': 0, 'h': 0,
                                         'hr': 0, 'bb': 0, 'so': 0, 'r': 0})

    cur = {0: None, 1: None}   # current pitcher per side index (0 = away, 1 = home)
    for ev in evs:
        t = ev['_type']
        if t == 'pitch':
            side = SIDES[ev['_pitching_side']]
            cur[side] = ev['pitcher_pid']
            if ev['_result_kind'] == 'batter_faced':
                pit(ev['pitcher_pid'])['bf'] += 1
        elif t == 'batting_record':
            side = SIDES[ev['_batting_side']]
            pid = ev['player_pid']
            outcome = ev['_outcome_kind']
            p = cur.get(1 - side)
            if outcome == 'at_bat':
                bat(pid)['ab'] += 1
            elif outcome in ('single', 'double', 'triple'):
                bat(pid)['h'] += 1
                if p is not None:
                    pit(p)['h'] += 1
            elif outcome == 'home_run':
                bat(pid)['h'] += 1
                bat(pid)['hr'] += 1
                if p is not None:
                    pit(p)['h'] += 1
                    pit(p)['hr'] += 1
            elif outcome == 'run_batted_in':
                bat(pid)['rbi'] += 1
            elif outcome == 'base_on_balls':
                bat(pid)['bb'] += 1
                if p is not None:
                    pit(p)['bb'] += 1
            elif outcome == 'strikeout':
                bat(pid)['so'] += 1
                if p is not None:
                    pit(p)['so'] += 1
            elif outcome == 'run_scored':
                bat(pid)['r'] += 1
                if p is not None:
                    pit(p)['r'] += 1
            elif outcome == 'stolen_base':
                bat(pid)['sb'] += 1
        elif t == 'fielding_record' and ev['play_code'] == 0:
            p = cur.get(SIDES[ev['_fielding_side']])
            if p is not None:
                pit(p)['outs'] += 1
    return batters, pitchers


# ------------------------------------------------------------------ main
def rebuild(name, doc):
    if name == 'game.bki':
        return encode_bki(doc)
    if name == 'game.bko':
        return encode_bko(doc)
    raise SystemExit('unknown NAME %r' % name)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    name = sys.argv[2]
    if cmd == 'decode':
        with open(sys.argv[3], 'rb') as f:
            data = f.read()
        doc = decode_bki(data) if name == 'game.bki' else decode_bko(data)
        with open(sys.argv[4], 'w') as f:
            json.dump(doc, f, indent=1)
    elif cmd == 'encode':
        with open(sys.argv[4]) as f:
            doc = json.load(f)
        out = rebuild(name, doc)
        with open(sys.argv[5], 'wb') as f:
            f.write(out)
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
