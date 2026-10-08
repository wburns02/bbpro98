#!/usr/bin/env python3
"""H-file lineup card codec for FPS Baseball Pro '98.

usage:
    python3 hcard.py decode gamefile out.json
    python3 hcard.py encode gamefile edited.json outfile

The first table of a box score from Stats (2698 bytes: header + seed[2] +
ciphertext[2696]) is the game's lineup card.  decode() turns it into JSON,
encode() rebuilds it from an edited JSON, changing only the bytes the edited
fields own and re-enciphering with the SAME seed.

Structure (offsets side-local; side 0 = away at 0x000, side 1 = home at 0x533):

  +0x00  u16  box-score team id in BOTH bytes (1..28; ALL 986 side blocks have
              the tid duplicated in the low and the high byte)
  +0x02  9B   association name (NUL-padded)
  +0x0b  34B  team name (NUL-padded)
  +0x2d  5B   team abbrev (NUL-padded)
  +0x32  40 x 21-byte player slots (u16 pid, 0 = empty; see below)
  +0x37a u8   lineup_entries n (9..18) = starters + subs who appear in the order
  +0x37b n u16 batting order, starters first, then batted subs in entry order
  +0x3cc n B  bat_slot: one byte per order entry (see FORMAT.md)
  +0x3f0 3B   zero bytes
  +0x3f3 u8   pitchers count
  +0x3f4 m u16 pitchers in mound order, STARTER FIRST

  player slot (21 bytes at +0x32 + 21*i):
    +0  u16 pid (0 = empty)
    +2  u16 positions_mask: bits 0..8 = the positions this player played this
        game (bit 0 = P ... bit 8 = RF); bits 9/10/11 = DH / pinch hitter /
        (rare) extra-hitter-ish role flags, preserved verbatim.  A player is a
        USED PITCHER iff bit 0 is set.  Bench = 0.
    +4  u16 starting_role: the position this player held at first pitch
        (bitmask, same bit numbering; 0 = did not start; the starting pitcher
        has 1, relievers 0)
    +6  u16 role_code | pitch_count<<8: low byte = the role code (position
        number 1..9, 10 = DH, 11 = pinch hitter, 12 = the rare 12 code;
        0 = bench), always the lowest set bit of positions_mask; high byte =
        a pitch-count-like per-player figure for pitchers (unconfirmed)
    +8  13B zero

Game tail at 0xa66: marker, home city, game id, day serial, temperature, more.
Full layout and evidence: FORMAT.md next to this file.
"""
import sys, json, struct

SIDE, NSLOT, SLOT, SLOT0 = 0x533, 40, 21, 0x32
BLOB = 2698                       # enciphered card record, ciphertext = 2696
SERIAL = 0xa72                    # u32 day serial inside the card body
POS = ['p', 'c', '1b', '2b', '3b', 'ss', 'lf', 'cf', 'rf']   # mask bits 0..8
# season calendar: the u32 day serial counts days; April 1 of the season year
# has serial 733132 = season day 1 (verified against 95/95 visible schedule games).
SEASON_BASE = 733132              # serial of April 1
SEASON_MONTH = 4


# ------------------------------------------------------------------ cipher

def base_table(lo, hi):
    """Substitution table from the two seed bytes (FPS Baseball's own builder)."""
    start = (lo - 1) & 255
    t = [start] * 256
    pos = 0
    v = lo
    for _ in range(256):
        t[pos] = v                # place the next value at the cursor
        v = (v + 1) & 255
        pos = (pos + hi) & 255    # stride step
        while t[pos] != start:    # skip occupied slots
            pos = (pos + 1) & 255
    return t


def forward(seed):
    """seed = the two stored seed bytes; plain -> stored = base table^3."""
    t = base_table(seed[0], seed[1])
    return bytes(t[t[t[x]]] for x in range(256))


def encipher(data, seed):
    f = forward(seed)
    return bytes(f[b] for b in data)


def decipher(data, seed):
    f = forward(seed)
    inv = bytearray(256)
    for x, y in enumerate(f):
        inv[y] = x
    return bytes(inv[b] for b in data)


# ------------------------------------------------------------------ helpers

def txt(raw):
    """NUL-padded latin-1 field -> str."""
    return raw.split(b'\0')[0].decode('latin1')


def bytes_txt(s, n):
    """str -> NUL-padded bytes of length n (truncating if longer)."""
    b = s.encode('latin1')[:n]
    return b + b'\0' * (n - len(b))


def mask_to_positions(mask):
    return [POS[i] for i in range(len(POS)) if mask >> i & 1]


def positions_to_mask(positions):
    m = 0
    for p in positions:
        m |= 1 << POS.index(p)
    return m


# ------------------------------------------------------------------ card I/O

def load_card(path):
    blob = open(path, 'rb').read()
    if len(blob) < BLOB or blob[:2] != b'\x02\x65' or blob[6:8] != b'\x8a\x0a':
        raise SystemExit('not an H file with a lineup card')
    seed = blob[8:10]
    body = decipher(blob[10:BLOB], seed)
    return blob, seed, body


def parse_side(body, k):
    o = k * SIDE
    slots = []
    for i in range(NSLOT):
        so = o + SLOT0 + SLOT * i
        pid, mask, starting_role, role_word = struct.unpack_from('<HHHH', body, so)
        slots.append({
            'pid': pid,
            'positions_mask': mask,         # played this game; bits 0..8 P..RF, 9-11 role flags
            'starting_role': starting_role, # position held at first pitch (0 = not a starter)
            'role_code': role_word & 0xff,  # 1..9 position, 10 DH, 11 PH, 0 bench
            'pitch_count': role_word >> 8,  # pitcher-only pitch-count-like figure
            'spare': body[so + 8:so + SLOT].hex(),   # slot bytes 8..20; all zero in every file
        })
    p = o + 0x37a
    n = body[p]
    order = [struct.unpack_from('<H', body, p + 1 + 2 * i)[0] for i in range(n)]
    bat_slot = list(body[o + 0x3cc: o + 0x3cc + n])
    pc = o + 0x3f3
    pitchers = [struct.unpack_from('<H', body, pc + 1 + 2 * i)[0] for i in range(body[pc])]
    players = []
    for i, sl in enumerate(slots):
        if not sl['pid']:
            continue
        pid = sl['pid']
        in_order = pid in order
        entry = order.index(pid) if in_order else None
        players.append({
            'pid': pid,
            'positions': mask_to_positions(sl['positions_mask'] & 0x1ff),
            'dh': bool(sl['positions_mask'] & 0x200),        # mask bit 9: DH (in batting order, no fielding)
            'pinch_hit': bool(sl['positions_mask'] & 0x400), # mask bit 10: pinch-hitter role flag
            'role_flag12': bool(sl['positions_mask'] & 0x800),  # mask bit 11: rare third role flag
            'starter': bool(sl['starting_role']),            # position held at first pitch
            'starting_position': mask_to_positions(sl['starting_role']),
            'role_code': sl['role_code'],
            'pitch_count': sl['pitch_count'],
            'slot': i,
            'bat_order': entry + 1 if in_order else None,    # 1-based order position, None = did not bat
            'bat_slot': bat_slot[entry] if in_order else None,
        })
    return {
        'side': ('away', 'home')[k],
        'team_id': body[o],                                  # box-score tid (1..28)
        'team_id_dup': body[o + 1],                          # == team_id in all 986 side blocks
        'assoc': txt(body[o + 2:o + 0x0b]),
        'name': txt(body[o + 0x0b:o + 0x2d]),
        'abbrev': txt(body[o + 0x2d:o + 0x32]),
        'players': players,
        'pitchers': pitchers,                                # mound order, starter first
        'batting_order': order,                              # all order entries, starters first
        'bat_order_starters': order[:9],
        'bat_order_subs': order[9:],                         # subs who batted later, entry order
        'bat_slot': bat_slot,                                # per-order-entry byte (see FORMAT.md)
        'raw_slots': body[o + SLOT0: o + 0x37a].hex(),       # the 40 player slots, verbatim
        'raw_team_head': body[o:o + SLOT0].hex(),            # team fields + spare bytes before slots
        'raw_after_order': body[o + 0x37a + 1 + 2 * n: o + 0x3cc].hex(),
        'raw_after_posmap': body[o + 0x3cc + n: o + 0x3f3].hex(),
        'raw_after_pitchers': body[o + 0x3f4 + 2 * len(pitchers): o + SIDE].hex(),
    }


def parse_card(body):
    city = txt(body[0xa67:0xa70])
    return {
        'game': {
            'month': 0,                                     # resolved from the day serial in cmd_decode
            'day': struct.unpack_from('<I', body, SERIAL)[0],
            'home_city': city,                              # the home team's city8 (tail 0xa67, 9 bytes)
            'record_marker_0xa66': body[0xa66],             # always 1
            'game_id': struct.unpack_from('<H', body, 0xa70)[0],
            # u16 game identifier at 0xa70: 97 distinct values for 97 distinct
            # games (range 7849..14301); not attendance or a box-score sum.
            'temperature_f': body[0xa76],                   # game-time temperature in F (51..78 observed)
            'weather_code': body[0xa77],                    # sky/game-condition code?, unconfirmed
            'time_field_a': body[0xa78],                    # game-time related, unconfirmed
            'time_field_b': body[0xa79],                    # game-length related, unconfirmed
            'schedule_slot': body[0xa7a],                   # 0..9, unconfirmed
            'inning_like_0xa7c': body[0xa7c],               # 1..7
            'attendance_digit_a': body[0xa7d],              # 1..4
            'attendance_related_b': body[0xa7e],            # 0..31
            'attendance_related_c': body[0xa7f],            # 1..242
        },
        'sides': [parse_side(body, 0), parse_side(body, 1)],
    }


# ------------------------------------------------------------------ rebuild

def rebuild_side(sd, k, body):
    """Rebuild side k from the decoded JSON side dict, preserving every
    unedited byte (flags, spare blocks, stale tails) verbatim."""
    out = bytearray(SIDE)
    o = k * SIDE

    def put(rel_off, data):
        out[rel_off:rel_off + len(data)] = data

    def orig(rel, n):
        return body[o + rel: o + rel + n]

    # team header: tid + dup + names; only name/abbrev/assoc are editable
    tid = sd['team_id'] & 0xff
    struct.pack_into('<H', out, 0, tid | tid << 8)
    put(2, orig(2, 0x0b - 2))
    put(0x0b, bytes_txt(sd.get('name', txt(orig(0x0b, 0x2d - 0x0b))), 0x22))
    put(0x2d, bytes_txt(sd['abbrev'], 5))                       # editable field
    put(0x32, bytes.fromhex(sd['raw_slots']))                   # roster slots verbatim
    # slot-level edits: only the positions mask (bits 0..8) of named players
    players = {p['pid']: p for p in sd['players']}
    n_slots = sd['raw_slots'] and len(sd['raw_slots']) // 2 // SLOT or 0
    for i in range(n_slots):
        so = SLOT0 + SLOT * i
        pid = struct.unpack_from('<H', out, so)[0]
        p = players.get(pid)
        if p is not None and p.get('positions') is not None:
            keep = struct.unpack_from('<H', out, so + 2)[0] & ~0x1ff & 0xffff
            struct.pack_into('<H', out, so + 2, keep | positions_to_mask(p['positions']))
    # order region
    n = len(sd['batting_order'])
    put(0x37a, bytes([n]) + b''.join(struct.pack('<H', pid) for pid in sd['batting_order']))
    put(0x37a + 1 + 2 * n, bytes.fromhex(sd['raw_after_order']))
    put(0x3cc, bytes(sd['bat_slot']))
    put(0x3cc + n, bytes.fromhex(sd['raw_after_posmap']))
    # pitchers list
    pc = 0x3f3
    put(pc, bytes([len(sd['pitchers'])]) + b''.join(struct.pack('<H', pid) for pid in sd['pitchers']))
    put(0x3f4 + 2 * len(sd['pitchers']), bytes.fromhex(sd['raw_after_pitchers']))
    return out


def build_card(doc, body0):
    out = bytearray(body0)
    g = doc['game']
    for k, sd in enumerate(doc['sides']):
        out[k * SIDE:(k + 1) * SIDE] = rebuild_side(sd, k, body0)
    orig_day = struct.unpack_from('<I', body0, SERIAL)[0]
    # date -> serial via the season calendar (733132 = April 1, season day 1)
    if g.get('month', 0) == SEASON_MONTH and isinstance(g.get('day'), int) and 1 <= g['day'] <= 30:
        day = SEASON_BASE - 1 + g['day']
    else:
        day = orig_day                                      # outside the calibrated window: keep the serial
    struct.pack_into('<I', out, SERIAL, day)
    out[0xa67:0xa70] = bytes_txt(g.get('home_city', txt(body0[0xa67:0xa70])), 9)
    out[0xa70:0xa72] = struct.pack('<H', g.get('game_id', struct.unpack_from('<H', body0, 0xa70)[0]))
    out[0xa76] = g.get('temperature_f', body0[0xa76])
    for off, key in ((0xa66, 'record_marker_0xa66'), (0xa77, 'weather_code'),
                     (0xa78, 'time_field_a'), (0xa79, 'time_field_b'), (0xa7a, 'schedule_slot'),
                     (0xa7c, 'inning_like_0xa7c'),
                     (0xa7d, 'attendance_digit_a'), (0xa7e, 'attendance_related_b'),
                     (0xa7f, 'attendance_related_c')):
        if key in g:
            out[off] = g[key]
    return bytes(out)


# ------------------------------------------------------------------ commands

def cmd_decode(inp, outp):
    blob, seed, body = load_card(inp)
    doc = parse_card(body)
    serial = struct.unpack_from('<I', body, SERIAL)[0]
    if SEASON_BASE <= serial < SEASON_BASE + 30:            # April of the season year
        doc['game']['month'] = SEASON_MONTH
        doc['game']['day'] = serial - SEASON_BASE + 1
    else:
        doc['game']['month'] = 0                            # outside the calibrated window: serial only
        doc['game']['day'] = serial
    with open(outp, 'w') as fh:
        json.dump(doc, fh, indent=1)


def cmd_encode(inp, jsonp, outp):
    blob, seed, body = load_card(inp)
    with open(jsonp) as fh:
        doc = json.load(fh)
    new_body = build_card(doc, body)
    enc = encipher(new_body, seed)
    with open(outp, 'wb') as fh:
        fh.write(blob[:10] + enc + blob[BLOB:])


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == 'decode' and len(sys.argv) == 4:
        cmd_decode(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == 'encode' and len(sys.argv) == 5:
        cmd_encode(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
