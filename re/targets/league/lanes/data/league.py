#!/usr/bin/env python3
"""Semantic read/write codec for the FPS Baseball Pro '98 league file (MLBPA97.ASN).

The file is a c-tree Plus superfile whose records are enciphered per member with the
game's byte cipher (seed f5dc).  Members t/r/xs (and a/l/d) store enciphered bytes,
members s/tr/df/po store plain bytes.  See FORMAT.md in this directory for the
field-by-field layout and the evidence.

decode: python3 league.py decode in.bin out.json
encode: python3 league.py encode in.bin edited.json out.bin

encode copies in.bin and rewrites only the bytes that differ from edited.json, so
encode(x, decode(x)) == x byte for byte and an edit touches exactly the records that
carry the edited fields (indexes stay valid because no key byte and no record length
changes).
"""
import json
import struct
import sys

# ---------------------------------------------------------------- FPS cipher (seed f5dc)

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
    return bytes([t[t[t[x]]] for x in range(256)])


_T = _forward((0xf5, 0xdc))
_INV = bytearray(256)
for _x, _y in enumerate(_T):
    _INV[_y] = _x
_INV = bytes(_INV)


def _dec(buf):
    return bytes(_INV[b] for b in buf)


def _enc(buf):
    return bytes(_T[b] for b in buf)


NAME_FIELD = 32                # team name field at payload 0x12..0x31 (31 chars + NUL); manager follows at 0x32

TEMPLATE_KEY = 100             # raw key byte of unused template records (T[deciphered 0x51])

# ---------------------------------------------------------------- container walk


def _scan(d):
    """Sequential FA FA record walk: (hdr_offset, payload_len, member)."""
    recs = []
    i, n = 0, len(d)
    while i < n - 20:
        if d[i] == 0xfa and d[i + 1] == 0xfa:
            tot, pl = struct.unpack_from('<II', d, i + 2)
            if tot == pl + 18 and 0 < pl < 2000 and i + 18 + pl <= n:
                recs.append((i, pl, struct.unpack_from('<I', d, i + 10)[0]))
                i += tot
                continue
        i += 1
    return recs


def _live(d, by_mem, mem):
    """Live (payload[0] != 0xff) records of one member as (payload_offset, raw_bytes)."""
    out = []
    for off, pl in by_mem.get(mem, ()):
        if d[off + 18] == 0xff:
            continue
        out.append((off + 18, bytes(d[off + 18:off + 18 + pl])))
    return out


def _cstr(p, at, cap):
    end = p.find(0, at)
    if end < 0 or end > at + cap:
        end = min(at + cap, len(p))
    return p[at:end].decode('latin-1', 'replace')


def _runs(p, lo, hi, minlen):
    """Printable ascii runs of at least minlen bytes in p[lo:hi], in file order."""
    out, cur = [], bytearray()
    for b in p[lo:hi]:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= minlen:
                out.append(cur.decode('latin-1'))
            cur = bytearray()
    if len(cur) >= minlen:
        out.append(cur.decode('latin-1'))
    return out


# ---------------------------------------------------------------- decode helpers


def _u16(p, o):
    return struct.unpack_from('<H', p, o)[0]


def _u32(p, o):
    return struct.unpack_from('<I', p, o)[0]


def _game_json(p):
    return {
        'month': p[1], 'day': p[2], 'slot': p[3],
        'aux0': _u16(p, 4),
        'away': p[6], 'ar': p[7], 'aux1': _u16(p, 8),
        'home': p[10], 'hr': p[11], 'aux2': _u16(p, 12),
        'played': p[14] == 0,
        'flag15': p[15], 'innings': p[16],
    }


def _roster_of(p):
    """Every u16 >= 100 in the id window of a r.dat record (offset 42..292)."""
    return sorted({v for v in struct.unpack_from('<126H', p, 42) if 100 <= v <= 9999})


def parse_container(d):
    """One pass over the file producing every member's decoded records.

    Enciphered members (a, l, d, t, r, xs) carry the plain record key in raw byte 0
    (T[deciphered byte 0]: team records 1..28, leagues 1..2, divisions 1..6, and 100
    for the unused template records shipped in fresh files).
    """
    by_mem = {}
    for off, pl, mem in _scan(d):
        by_mem.setdefault(mem, []).append((off, pl))

    doc = {}
    # --- teams (t.dat): the raw key byte is the team id used everywhere else
    teams = []
    for off, raw in _live(d, by_mem, 8):
        if 1 <= raw[0] <= 28:
            p = _dec(raw)
            teams.append({'off': off, 'tid': raw[0], 'p': p})
    teams.sort(key=lambda t: t['tid'])
    for t in teams:
        t['stored_name'] = _cstr(t['p'], 0x12, NAME_FIELD)
        t['name'] = t['stored_name']

    # --- per-team members keyed by the raw team id
    xs_map = {raw[0]: (off, _dec(raw)) for off, raw in _live(d, by_mem, 14) if 1 <= raw[0] <= 28}
    r_map = {raw[0]: (off, _dec(raw)) for off, raw in _live(d, by_mem, 10) if 1 <= raw[0] <= 28}

    # --- transactions (tr.dat, plain) feed extra roster ids
    tr_pids = {}
    transactions = []
    for off, p in _live(d, by_mem, 16):
        if len(p) < 21:
            continue
        rec = {'day': _u32(p, 2), 'kind': p[20]}
        for k, base in ((1, 6), (2, 13)):
            pid = _u16(p, base)
            team = p[base + 6]
            rec['pid%d' % k] = pid
            rec['f%d' % k] = _u16(p, base + 2)
            rec['g%d' % k] = _u16(p, base + 4)
            rec['team%d' % k] = team
            if pid >= 100 and 1 <= team <= 28:
                tr_pids.setdefault(team, set()).add(pid)
        transactions.append(rec)

    for t in teams:
        tid = t['tid']
        xs = xs_map.get(tid, (None, None))[1]
        rr = r_map.get(tid, (None, None))[1]
        t['w'] = xs[1] if xs is not None else 0
        t['l'] = xs[2] if xs is not None else 0
        t['xs_off'] = xs_map.get(tid, (None, None))[0]
        t['xs_raw'] = xs
        t['r_off'] = r_map.get(tid, (None, None))[0]
        t['r_p'] = rr
        t['roster'] = sorted(set(_roster_of(rr)) | tr_pids.get(t['tid'], set())) if rr is not None else []
        t['window_roster'] = _roster_of(rr) if rr is not None else []
        t['abbrev'] = _cstr(t['p'], 0x45, 3)
        t['stadium'] = _cstr(t['p'], 0x53, 30)
        t['city8'] = _cstr(t['p'], 0x74, 8)
        mgr = _runs(t['p'], 0x30, 0x45, 4)
        mgr = mgr[-1].strip() if mgr else ''
        # day-file team records carry a stray template byte before the manager name
        if len(mgr) > 2 and mgr[0].islower() and mgr[1].isupper():
            mgr = mgr[1:]
        t['manager'] = mgr
        t['field_ac'] = _u32(t['p'], 0xac) if len(t['p']) >= 0xb0 else 0

    # --- schedule (s.dat, plain).  Regular-season games: two real team ids and no
    # special marker (byte 15, 2 = the all-star placeholder whose "teams" are 0).
    # Every other live record lands in "specials" so encode can still reproduce it.
    games, specials = [], []
    for off, p in _live(d, by_mem, 12):
        if len(p) < 17:
            continue
        rec = _game_json(p)
        if 1 <= p[6] <= 28 and 1 <= p[10] <= 28 and p[15] == 0:
            games.append({'off': off, 'p': p, 'rec': rec})
        else:
            specials.append({'off': off, 'p': p, 'rec': rec})

    # --- leagues / divisions
    divisions = []
    for off, raw in _live(d, by_mem, 6):
        if raw[0] == TEMPLATE_KEY:
            continue
        p = _dec(raw)
        divisions.append({
            'key': raw[0], 'league_idx': p[1], 'div_idx': p[2],
            'name': _cstr(p, 3, 16),
            'teams': [x for x in p[20:25] if 1 <= x <= 28],
        })
    leagues = []
    for off, raw in _live(d, by_mem, 4):
        if raw[0] == TEMPLATE_KEY:
            continue
        p = _dec(raw)
        leagues.append({
            'key': raw[0], 'idx': p[1],
            'name': _cstr(p, 4, 22), 'abbrev': _cstr(p, 0x25, 2),
            'divisions': [x for x in p[0x2a:0x2d] if x],
        })

    doc['teams'] = teams
    doc['games'] = games
    doc['specials'] = specials
    doc['divisions'] = divisions
    doc['leagues'] = leagues
    doc['transactions'] = transactions
    doc['association'] = [
        {'key': raw[0], 'day1': _u32(_dec(raw), 10) if len(raw) >= 18 else 0,
         'day2': _u32(_dec(raw), 14) if len(raw) >= 18 else 0,
         'strings': _runs(_dec(raw), 0, len(raw), 4)}
        for off, raw in _live(d, by_mem, 2) if raw[0] != TEMPLATE_KEY]
    df = _live(d, by_mem, 18)
    if df:
        dp = df[0][1]
        doc['draft'] = {'values': [struct.unpack_from('<H', dp, i)[0] for i in range(0, len(dp) - 1, 2)]}
    else:
        doc['draft'] = {}
    doc['playoff'] = [
        {'head': list(p[0:4]), 'f4': _u16(p, 4) if len(p) >= 6 else 0,
         'day': _u32(p, 6) if len(p) >= 10 else 0, 'hex': p[10:].hex()}
        for off, p in _live(d, by_mem, 20)]
    doc['sp'] = [{'hex': p.hex()} for off, p in _live(d, by_mem, 22)]
    return doc


def build_json(doc):
    divisions = doc['divisions']
    out_teams = []
    for t in doc['teams']:
        div = next((dv for dv in divisions if t['tid'] in dv['teams']), None)
        out_teams.append({
            'tid': t['tid'], 'name': t['name'], 'w': t['w'], 'l': t['l'],
            'roster': t['roster'],
            'stored_name': t['stored_name'],
            'abbrev': t['abbrev'], 'manager': t['manager'], 'stadium': t['stadium'],
            'city8': t['city8'], 'key': t['tid'],
            'league_idx': div['league_idx'] if div else None,
            'division': div['name'] if div else None,
            'field_ac': t['field_ac'],
            'roster_window': t['window_roster'],
        })
    out = {'teams': out_teams,
           'games': [g['rec'] for g in doc['games']],
           'specials': [s['rec'] for s in doc['specials']],
           'leagues': doc['leagues'],
           'divisions': divisions,
           'association': doc['association'],
           'transactions': doc['transactions'],
           'playoff': doc['playoff'],
           'sp': doc['sp']}
    if doc.get('draft'):
        out['draft'] = doc['draft']
    return out


def cmd_decode(inp, outp):
    with open(inp, 'rb') as fh:
        d = fh.read()
    doc = build_json(parse_container(d))
    with open(outp, 'w') as fh:
        json.dump(doc, fh)
    return 0


# ---------------------------------------------------------------- encode


def _patch_team(buf, t, js):
    p = bytearray(t['p'])
    off = t['off']
    name = js.get('name')
    if isinstance(name, str) and name != t['name']:
        nb = name.encode('latin-1', 'replace')[:NAME_FIELD - 1]
        p[0x12:0x12 + NAME_FIELD] = nb + bytes(NAME_FIELD - len(nb))
    if 'w' in js or 'l' in js:
        w = int(js.get('w', t['w'])); l = int(js.get('l', t['l']))
        if t['xs_off'] is not None and (w != t['w'] or l != t['l']):
            xs = bytearray(t['xs_raw'])
            xs[1] = w & 0xff
            xs[2] = l & 0xff
            buf[t['xs_off']:t['xs_off'] + 16] = _enc(xs)
    ros = js.get('roster')
    if (isinstance(ros, list) and t['r_off'] is not None
            and sorted({int(x) for x in ros}) != sorted(t['roster'])):
        rp = bytearray(t['r_p'])
        ids = sorted({int(x) for x in ros})[:126]
        ids += [0] * (126 - len(ids))
        struct.pack_into('<126H', rp, 42, *[i & 0xffff for i in ids])
        buf[t['r_off']:t['r_off'] + len(rp)] = _enc(rp)
    if bytes(p) != t['p']:
        buf[off:off + len(p)] = _enc(p)


def _patch_game(buf, g, js):
    p = bytearray(g['p'])
    src = g['rec']
    vals = {
        1: int(js.get('month', src['month'])), 2: int(js.get('day', src['day'])),
        3: int(js.get('slot', src['slot'])),
        6: int(js.get('away', src['away'])), 7: int(js.get('ar', src['ar'])),
        10: int(js.get('home', src['home'])), 11: int(js.get('hr', src['hr'])),
        14: 0 if js.get('played', src['played']) else 1,
        15: int(js.get('flag15', src['flag15'])), 16: int(js.get('innings', src['innings'])),
    }
    for o, v in vals.items():
        p[o] = v & 0xff
    for o, key in ((4, 'aux0'), (8, 'aux1'), (12, 'aux2')):
        struct.pack_into('<H', p, o, int(js.get(key, src[key])) & 0xffff)
    if bytes(p) != g['p']:
        off = g['off']
        buf[off:off + len(p)] = p


def cmd_encode(inp, jsonp, outp):
    with open(inp, 'rb') as fh:
        buf = bytearray(fh.read())
    with open(jsonp, 'r') as fh:
        js = json.load(fh)
    doc = parse_container(bytes(buf))

    by_tid = {t['tid']: t for t in doc['teams']}
    for jt in js.get('teams', []):
        t = by_tid.get(int(jt.get('tid', 0)))
        if t is not None:
            _patch_team(buf, t, jt)
    for jg, g in zip(js.get('games', []), doc['games']):
        _patch_game(buf, g, jg)
    for jg, g in zip(js.get('specials', []), doc['specials']):
        _patch_game(buf, g, jg)

    with open(outp, 'wb') as fh:
        fh.write(bytes(buf))
    return 0


def main(argv):
    if len(argv) >= 4 and argv[1] == 'decode':
        return cmd_decode(argv[2], argv[3])
    if len(argv) >= 5 and argv[1] == 'encode':
        return cmd_encode(argv[2], argv[3], argv[4])
    sys.stderr.write('usage: league.py decode in.bin out.json | encode in.bin edited.json out.bin\n')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
