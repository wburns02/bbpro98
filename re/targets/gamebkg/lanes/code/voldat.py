"""Semantic read/write codec for game.bki / game.bko, the shell <-> simulator hand-off of
FPS Baseball Pro '98 (BBShell writes game.in, the simulator answers in game.out; BBShell renames
them after reading).

File layout (both files): a stream of 4-byte tag + u32 little-endian payload length + payload.

game.bki: one "GDI:" chunk (payload 1031 bytes) plus one "ADI:" chunk (12 bytes) per game.
  GDI payload = 2-byte cipher seed + 1029 enciphered body (the file cipher, see decipher() below).
  Plain body: two team blocks of 490 bytes each (home first), then a 49-byte tail.

  Team block (offsets relative to the block start):
    +0    u16 flag / u16 ... / u16 0x0001 / u16 0x0100 / u16 0x0303 / u16 0x0303 (colors/config)
    +12   team name, 33-byte NUL-padded field
    +45   0x00 pad
    +46   manager name, 17-byte NUL-padded field
    +63   team abbreviation, 4-byte field ("ATL\\0...")
    +77   stadium name, 33-byte NUL-padded field
    +110  city, 9-byte field ("ATLANTA.")
    +119  98 bytes of per-player byte triples (uniform colors)
    +217  u16 id region, 240 bytes (120 words):
            25 roster player ids,
            15 zero words,
            lineup/id blocks (batting orders) terminated by 0x0000 / 0xffff markers,
            pitching staff ids
    +457  16 bytes: a 0..63 permutation-like byte table + counters
    +473  league name, 7 bytes ("MLBPA97")
    +480  10 trailing words/values
  Tail (the 49 bytes after the two team blocks):
    +0    21 bytes of status/counters (varies per game)
    +21   the away team's city, 8 chars
    +29   0x00
    +30   the box-score file name the game's box score is written to, 11 bytes ("MLBPA97.HB0")
    +41   6 trailing bytes
  ADI payload = 12 enciphered bytes (decoded with the GDI record's seed): two u32s equal to a
  record checksum and a u32 game number (0x100, 0x101, ...).

game.bko: one "GDO:" chunk per game, plaintext, a sequence of u16 event records. Record sizes in
bytes per type (0..8) are fixed: 4, 82, 30, 14, 6, 8, 8, 10, 12. Type names come from the
simulator's own event-name table (BBSIM.dll 680ba358) and its per-event outcome tables:

  0 "Enter Game"  (4): u16 0 ("EVENT: %s Version: %d" -> ver) then u16 4 = the format version.
  1 "Exit Game"  (82): u16 1, u16 game length in ticks, u16 outs, a line-score block, ...
  2 "Plate Appearance" (30): u16 2, u16 pitcher id, 9 defensive player ids, then 15-u16 tail
      (on-deck batter, batter, and counters).
  3 "Substitution" (14): u16 3, u16 half, u16 player in, u16 ..., u16 8, u16 flag.
  4 "Team" (6): u16 4, u16 half, u16 code (the day1 arrows/outs counters).
  5 "Pitching" (8): u16 5, u16 half, u16 pitcher id, u16 pitch event (the pitch-kind counter:
      0 = ball in play, 15/19/20 = ball/strike kinds, the high bits carry the pitch speed id).
  6 "Batting" (8): u16 6, u16 half, u16 player id, u16 outcome. The outcome indexes the
      simulator's batting-outcome table (AB/1B/2B/3B/HR/RBI/BB/K/HBP/BBI/SH/SF/R/SB/CS/GDP/PO):
        0 at-bat, 1 single, 2 double, 3 triple, 4 home run, 5 RBI, 6 walk, 7 strikeout,
        8 hit by pitch?? , 9 intentional-walk marker (rides on a code-6), 12 run scored,
        13 stolen base.
  7 "Fielding" (10): u16 7, u16 half, u16 fielder id, u16 play kind (0 = putout, 1 = assist,
      3 = ...), u16 fielding position.
  8 "Injury" (12): u16 8, u16 half, u16 player id, u16 ..., u16 code.

Usage:
  python3 voldat.py decode game.bki in.bin out.json
  python3 voldat.py encode game.bki in.bin edited.json out.bin
"""
import json
import struct
import sys

CHUNK = 4
GDI = b'GDI:'
ADI = b'ADI:'
GDO = b'GDO:'
GDI_PAYLOAD = 1031
ADI_PAYLOAD = 12
BODY = GDI_PAYLOAD - 2          # 1029 enciphered/plaintext body bytes
TEAM = 490                      # team block size in the plain body
TAIL = 49                       # tail after the two team blocks (1029 = 490*2 + 49)

# event record payload sizes in bytes for types 0..8 (BBSIM 680b3238 size table)
EVENT_SIZES = (4, 82, 30, 14, 6, 8, 8, 10, 12)


def base_table(lo, hi):
    """The game's cipher table builder (BBShell 68053450 / LineUp 6b023440)."""
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


def forward(seed):
    """plain -> stored table (the base table applied three times)."""
    t = base_table(seed[0], seed[1])
    return bytes(t[t[t[x]]] for x in range(256))


def decipher(data, seed):
    f = forward(seed)
    inv = bytearray(256)
    for x, y in enumerate(f):
        inv[y] = x
    return bytes(inv[b] for b in data)


def encipher(data, seed):
    f = forward(seed)
    return bytes(f[b] for b in data)


def chunks(blob):
    out, off = [], 0
    n = len(blob)
    while off < n:
        if off + 8 > n:
            raise ValueError('trailing bytes after the last chunk')
        tag = blob[off:off + 4]
        ln, = struct.unpack_from('<I', blob, off + 4)
        if off + 8 + ln > n:
            raise ValueError('chunk payload runs past the end of the file')
        out.append((tag, blob[off + 8:off + 8 + ln]))
        off += 8 + ln
    return out


def text_field(raw):
    """NUL-padded fixed-width field -> text (opaque bytes stay opaque)."""
    end = raw.find(b'\x00')
    body = raw if end < 0 else raw[:end]
    return body.decode('latin1')


def pad_field(text, ln):
    b = text.encode('latin1')
    if len(b) > ln:
        raise ValueError('field text %r does not fit %d bytes' % (text, ln))
    return b + b'\x00' * (ln - len(b))


def team_block_decode(blk):
    """One 490-byte team block -> dict. Editable content: texts, roster pids, the head words,
    slot color triples and the slot order table; the lineup/staff rest of the id region stays
    under "_" keys (their ids are covered by the roster)."""
    ids = list(struct.unpack('<120H', blk[217:457]))
    # the roster fills the leading slots contiguously (never 0); the zero words after it are
    # spare roster slots, then the lineup blocks and the staff (kept opaque under _idRest)
    roster_end = ids.index(0) if 0 in ids else len(ids)
    head = list(struct.unpack('<6H', blk[0:12]))
    colors_raw = blk[119:217]
    colors = [list(colors_raw[i:i + 3]) for i in range(0, 96, 3)]
    perm_raw = blk[457:473]
    tail = list(struct.unpack('<5H', blk[480:490]))
    team = dict(
        statusFlags=head[0],
        statusFlag1=head[1],
        structVersion=head[2],
        structFlag=head[3],
        colorPrimary=head[4],
        colorSecondary=head[5],
        name=text_field(blk[12:45]),
        manager=text_field(blk[46:63]),
        abbrev=text_field(blk[63:77]),
        stadium=text_field(blk[77:110]),
        city=text_field(blk[110:119]),
        slotColors=colors,
        slotColorExtra=list(colors_raw[96:98]),
        rosterPids=ids[:roster_end],
        slotOrder=list(perm_raw),
        leagueName=text_field(blk[473:480]),
        blockTailWords=tail,
        _idRest=ids[roster_end:],
    )
    return team


def team_block_encode(team):
    blk = bytearray(TEAM)
    head = [team['statusFlags'], team['statusFlag1'], team['structVersion'], team['structFlag'],
            team['colorPrimary'], team['colorSecondary']]
    struct.pack_into('<6H', blk, 0, *[int(v) & 0xFFFF for v in head])
    blk[12:45] = pad_field(team['name'], 33)
    blk[45:46] = b'\x00'
    blk[46:63] = pad_field(team['manager'], 17)
    blk[63:77] = pad_field(team['abbrev'], 14)
    blk[77:110] = pad_field(team['stadium'], 33)
    blk[110:119] = pad_field(team['city'], 9)
    body = bytearray()
    for c in list(team['slotColors'])[:32]:
        body += bytes(int(v) & 0xFF for v in c[:3])
    body += bytes(int(v) & 0xFF for v in list(team['slotColorExtra'])[:2])
    blk[119:217] = (body + bytearray(98 - len(body)))[:98]
    # the id region = [roster ids (editable)] + [the byte-exact rest]
    n_roster = len(team['rosterPids'])
    if n_roster > 120:
        raise ValueError('roster of %d ids does not fit the 120-word id region' % n_roster)
    region = [int(v) & 0xFFFF for v in team['rosterPids']] + \
        [int(v) & 0xFFFF for v in team['_idRest'][:120 - n_roster]]
    region += [0] * (120 - len(region))
    for i, v in enumerate(region[:120]):
        struct.pack_into('<H', blk, 217 + i * 2, v)
    perm = [int(v) & 0xFF for v in list(team['slotOrder'])[:16]]
    perm += [0] * (16 - len(perm))
    blk[457:473] = bytes(perm)
    blk[473:480] = pad_field(team['leagueName'], 7)
    tw = [int(v) & 0xFFFF for v in list(team['blockTailWords'])[:5]]
    tw += [0] * (5 - len(tw))
    struct.pack_into('<5H', blk, 480, *tw)
    return bytes(blk)


def gdi_decode(payload):
    seed = payload[:2]
    body = decipher(payload[2:], seed)
    away = team_block_decode(body[0:TEAM])
    home = team_block_decode(body[TEAM:TEAM * 2])
    tail = body[TEAM * 2:]
    rec = dict(
        awayTeam=away,
        homeTeam=home,
        cityTail=text_field(tail[23:31]),
        boxFileName=text_field(tail[32:43]),
        _tail0=list(tail[0:23]),
        _tail1=list(tail[31:32]),
        _tail2=list(tail[43:TAIL]),
    )
    return seed, rec


def gdi_encode(seed, rec):
    body = bytearray(BODY)
    body[0:TEAM] = team_block_encode(rec['awayTeam'])
    body[TEAM:TEAM * 2] = team_block_encode(rec['homeTeam'])
    tail = bytearray(TAIL)
    tail[0:23] = bytes(list(rec['_tail0'])[:23])
    tail[23:31] = pad_field(rec['cityTail'], 8)
    tail[31:32] = bytes(list(rec['_tail1'])[:1])
    tail[32:43] = pad_field(rec['boxFileName'], 11)
    tail[43:TAIL] = bytes(list(rec['_tail2'])[:6])
    body[TEAM * 2:] = tail
    return seed + encipher(bytes(body), seed)


def read_events(payload):
    """GDO payload -> list of records as (type, payload-bytes)."""
    out = []
    off = 0
    n = len(payload)
    while off < n:
        if off + 2 > n:
            break
        t, = struct.unpack_from('<H', payload, off)
        if t > 8:
            raise ValueError('unknown event type %d at byte %d' % (t, off))
        by = EVENT_SIZES[t]
        out.append((t, payload[off:off + by]))
        off += by
    return out


def replay(records):
    """Replay the event stream into batting and pitching box-score rows. The batting outcomes
    (codes 0..12) belong to the player named by the Batting record; the base-runner events
    (13 = stolen base, 14 = caught stealing) attach to an existing row and are dropped for a
    player the stream never gives a batting outcome (a pinch runner; box scores carry no such
    row).  Rows whose counted cells are all zero are dropped (a player who appeared without a
    counted stat — a pinch runner, a sac bunt with no other PA — is no box row), matching the
    box-score decoder's own row filter."""
    batters = {}
    pitchers = {}

    def bat(pid):
        return batters.setdefault(pid, dict(pa=0, ab=0, h=0, hr=0, rbi=0, bb=0, so=0, r=0, sb=0, cs=0))

    def pit(pid):
        return pitchers.setdefault(pid, dict(outs=0, bf=0, h=0, hr=0, bb=0, so=0, r=0))

    mound = None            # the pitcher on the mound (the last Pitching record or the PA header)
    cur_batter = None
    for t, body in records:
        if t == 2:
            vals = struct.unpack('<15H', body)
            mound = vals[1]
            cur_batter = vals[11]
            pit(mound)['bf'] += 1
            bat(cur_batter)['pa'] += 1
        elif t == 5:
            vals = struct.unpack('<4H', body)
            mound = vals[2]
        elif t == 6:
            vals = struct.unpack('<4H', body)
            code, pid = vals[3], vals[2]
            prow = pit(mound) if mound is not None else None
            # rows exist for players with a batting outcome or a stolen base; a caught-stealing
            # event merges into an existing row only (the box has no caught-stealing field)
            if code == 14:
                row = batters.get(pid)
                if row is None:
                    continue
            else:
                row = bat(pid)
            if code == 0:
                row['ab'] += 1
            elif code in (1, 2, 3, 4):
                row['h'] += 1
                if prow is not None:
                    prow['h'] += 1
                if code == 4:
                    row['hr'] += 1
                    if prow is not None:
                        prow['hr'] += 1
            elif code == 5:
                row['rbi'] += 1
            elif code == 6:
                row['bb'] += 1
                if prow is not None:
                    prow['bb'] += 1
            elif code == 7:
                row['so'] += 1
                if prow is not None:
                    prow['so'] += 1
            elif code == 9:
                pass            # the intentional-walk marker rides on the code-6 walk
            elif code == 12:
                row['r'] += 1
                if prow is not None:
                    prow['r'] += 1
            elif code == 13:
                row['sb'] += 1
            elif code == 14:
                row['cs'] += 1
        elif t == 7:
            vals = struct.unpack('<5H', body)
            if vals[3] == 0 and mound is not None:
                pit(mound)['outs'] += 1
    box_batters = {pid: row for pid, row in batters.items()
                   if row['ab'] or row['h'] or row['rbi'] or row['bb'] or row['so']
                   or row['r'] or row['sb']}
    box_pitchers = {pid: row for pid, row in pitchers.items()
                    if row['outs'] or row['bf'] or row['h'] or row['hr'] or row['bb']
                    or row['so'] or row['r']}
    return box_batters, box_pitchers


def gdo_decode(payload):
    records = read_events(payload)
    batters, pitchers = replay(records)
    events = []
    for t, body in records:
        vals = struct.unpack('<%dH' % (len(body) // 2), body)
        if t == 0:
            events.append(dict(_type='enter_game', version=vals[1]))
        elif t == 1:
            events.append(dict(_type='exit_game', gameLengthTicks=vals[1], outs=vals[2],
                               lineScoreHalf=vals[3:5],
                               _rest=list(vals[5:])))
        elif t == 2:
            events.append(dict(_type='plate_appearance', pitcherPid=vals[1],
                               defensePids=list(vals[2:11]), onDeckPid=vals[11],
                               batterPid=vals[12], _rest=list(vals[13:])))
        elif t == 3:
            events.append(dict(_type='substitution', half=vals[1], playerPid=vals[2],
                               orderId=vals[3], sequence=vals[4], code=vals[5], flag=vals[6]))
        elif t == 4:
            events.append(dict(_type='team', half=vals[1], code=vals[2]))
        elif t == 5:
            events.append(dict(_type='pitching', half=vals[1], pitcherPid=vals[2],
                               pitchEvent=vals[3]))
        elif t == 6:
            names = {0: 'at_bat', 1: 'single', 2: 'double', 3: 'triple', 4: 'home_run',
                     5: 'rbi', 6: 'walk', 7: 'strikeout', 8: 'steal_attempt', 9: 'intentional_walk',
                     10: 'sac_fly', 11: 'sac_bunt', 12: 'run_scored', 13: 'stolen_base',
                     14: 'caught_stealing', 15: 'double_play', 16: 'putout'}
            events.append(dict(_type='batting', half=vals[1], playerPid=vals[2],
                               outcome=vals[3], _outcomeName=names.get(vals[3], 'unknown')))
        elif t == 7:
            kinds = {0: 'putout', 1: 'assist', 2: 'error', 3: 'double_play'}
            events.append(dict(_type='fielding', half=vals[1], fielderPid=vals[2],
                               play=vals[3], _playName=kinds.get(vals[3], 'unknown'),
                               position=vals[4]))
        elif t == 8:
            # "%s Type:%d Duration:%d Severity:%d": [8, half, playerPid, type, duration, severity]
            events.append(dict(_type='injury', half=vals[1], playerPid=vals[2],
                               genre=vals[3], duration=vals[4], severity=vals[5]))
    return dict(events=events,
                _batters=[dict(pid=pid, **row) for pid, row in sorted(batters.items())],
                _pitchers=[dict(pid=pid, **row) for pid, row in sorted(pitchers.items())])


def gdo_encode(doc):
    sizes = EVENT_SIZES
    out = bytearray()
    for ev in doc['events']:
        t = ev['_type']
        num = {'enter_game': 0, 'exit_game': 1, 'plate_appearance': 2, 'substitution': 3,
               'team': 4, 'pitching': 5, 'batting': 6, 'fielding': 7, 'injury': 8}[t]
        by = sizes[num]
        words = by // 2
        vals = [num]
        if t == 'enter_game':
            vals = [num, ev['version']]
        elif t == 'exit_game':
            vals = [num, ev['gameLengthTicks'], ev['outs']] + list(ev['lineScoreHalf'][:2]) + \
                list(ev['_rest'])
        elif t == 'plate_appearance':
            vals = [num, ev['pitcherPid']] + list(ev['defensePids'][:9]) + \
                [ev['onDeckPid'], ev['batterPid']] + list(ev['_rest'])
        elif t == 'substitution':
            vals = [num, ev['half'], ev['playerPid'], ev['orderId'], ev['sequence'], ev['code'],
                    ev['flag']]
        elif t == 'team':
            vals = [num, ev['half'], ev['code']]
        elif t == 'pitching':
            vals = [num, ev['half'], ev['pitcherPid'], ev['pitchEvent']]
        elif t == 'batting':
            vals = [num, ev['half'], ev['playerPid'], ev['outcome']]
        elif t == 'fielding':
            vals = [num, ev['half'], ev['fielderPid'], ev['play'], ev['position']]
        elif t == 'injury':
            vals = [num, ev['half'], ev['playerPid'], ev['genre'], ev['duration'], ev['severity']]
        vals = [int(v) & 0xFFFF for v in vals[:words]]
        vals += [0] * (words - len(vals))
        out += struct.pack('<%dH' % words, *vals)
    return bytes(out)


def decode(name, blob):
    if name == 'game.bki':
        games = []
        for gi, (tag, payload) in enumerate(chunks(blob)):
            if tag == GDI:
                seed, rec = gdi_decode(payload)
                rec['_cipherSeed'] = list(seed)
                games.append(rec)
            elif tag == ADI:
                games[-1]['_adi'] = list(struct.unpack(
                    '<%dI' % (len(payload) // 4),
                    decipher(payload, bytes(games[-1]['_cipherSeed']))))
        return dict(_kind='game_setup_records', games=games)
    if name == 'game.bko':
        games = []
        for tag, payload in chunks(blob):
            if tag == GDO:
                games.append(gdo_decode(payload))
        return dict(_kind='game_event_streams', games=games)
    raise ValueError('unknown file name %r' % name)


def encode(name, inbin, doc):
    if name == 'game.bki':
        out = bytearray()
        for rec in doc['games']:
            payload = gdi_encode(bytes(rec['_cipherSeed']), rec)
            out += GDI + struct.pack('<I', len(payload)) + payload
            adin = encipher(struct.pack('<3I', *rec['_adi']), bytes(rec['_cipherSeed']))
            out += ADI + struct.pack('<I', ADI_PAYLOAD) + adin
        return bytes(out)
    if name == 'game.bko':
        out = bytearray()
        for g in doc['games']:
            payload = gdo_encode(g)
            out += GDO + struct.pack('<I', len(payload)) + payload
        return bytes(out)
    raise ValueError('unknown file name %r' % name)


def main(argv):
    if argv[1:2] not in (['decode'], ['encode']) or len(argv) < (6 if argv[1] == 'encode' else 5):
        raise SystemExit(__doc__)
    cmd, name, src, dst = argv[1], argv[2], argv[3], argv[4]
    if cmd == 'decode':
        blob = open(src, 'rb').read()
        doc = decode(name, blob)
        with open(dst, 'w') as fh:
            json.dump(doc, fh)
        return
    if cmd == 'encode':
        if len(argv) < 6:
            raise SystemExit(__doc__)
        blob = open(src, 'rb').read()
        with open(dst) as fh:
            doc = json.load(fh)
        out = encode(name, blob, doc)
        with open(argv[5], 'wb') as fh:
            fh.write(out)
        return
    raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
