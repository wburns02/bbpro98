#!/usr/bin/env python3
"""Semantic read/write codec for the FPS Baseball Pro '98 league file (MLBPA97.ASN).

The file is a c-tree Plus superfile whose records are enciphered per member with the
game's byte cipher (seed f5dc).  Members t/r/xs (and a/l/d) store enciphered bytes,
members s/tr/df/po store plain bytes.  See FORMAT.md in this directory for the
field-by-field layout and the evidence.

decode: python3 league.py decode in.bin out.json
encode: python3 league.py encode in.bin edited.json out.bin

encode copies in.bin and rewrites only the records whose fields differ in edited.json, so
encode(x, decode(x)) == x byte for byte and an edit touches exactly the records that carry the
edited fields (indexes stay valid because no key byte and no record length changes).
Writable: teams name/manager/abbrev/stadium/city8/field_ac/w/l/roster, games and specials, association
name/trophy/day1/day2, leagues idx/name/abbrev/divisions, divisions league_idx/div_idx/name/teams,
transactions, playoff, sp, draft.  Strings are written strcpy style (string + NUL, stale tail kept)
and must fit their field.  Every edit is read back after the rewrite: an edit to a field encode
cannot write (stored_name, roster_window, keys, derived team league_idx/division) or to
the record count fails with an error instead of being dropped.
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

# string fields: (offset, bytes incl. the NUL).  A shorter string is written strcpy style: string + NUL, the stale
# tail after it is kept (the game leaves the same garbage there).
ASN_NAME, ASN_TROPHY, ASN_STR = 0x12, 0x33, 33     # a.dat: association name, trophy (edit gadgets 16 / 65, maxLength 32)
T_MANAGER, T_ABBREV, T_STADIUM, T_CITY8 = (0x34, 17), (0x45, 4), (0x53, 30), (0x74, 9)   # t.dat (stadium NUL can land at 0x70; 0x71 = data)
L_NAME, L_ABBREV = (4, 33), (0x25, 3)              # l.dat; divisions list at 0x2a..0x2c
D_NAME = (3, 17)                                   # d.dat; team ids at 0x14..0x1d
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
    tr_recs = []
    for off, p in _live(d, by_mem, 16):
        if len(p) < 21:
            continue
        tr_recs.append((off, p))
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
        # manager: char[17] at 0x34 (16 chars, 'Marcel Lachemann'); the bytes before it are stale in day files and
        # the tail after the NUL keeps old names ('Art Howe\0lins'), so no printable-run scan
        t['manager'] = _cstr(t['p'], T_MANAGER[0], T_MANAGER[1] - 1)
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
    divisions, recs = [], {'d': [], 'l': [], 'a': []}
    for off, raw in _live(d, by_mem, 6):
        if raw[0] == TEMPLATE_KEY:
            continue
        p = _dec(raw)
        recs['d'].append((off, p))
        divisions.append({
            'key': raw[0], 'league_idx': p[1], 'div_idx': p[2],
            'name': _cstr(p, 3, 16),
            'teams': [x for x in p[20:30] if 1 <= x <= 28],
        })
    leagues = []
    for off, raw in _live(d, by_mem, 4):
        if raw[0] == TEMPLATE_KEY:
            continue
        p = _dec(raw)
        recs['l'].append((off, p))
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
    doc['association'] = []
    for off, raw in _live(d, by_mem, 2):
        if raw[0] == TEMPLATE_KEY or len(raw) < ASN_TROPHY + ASN_STR:
            continue
        p = _dec(raw)
        recs['a'].append((off, p))
        doc['association'].append({'key': raw[0], 'day1': _u32(p, 10), 'day2': _u32(p, 14),
                                   'name': _cstr(p, ASN_NAME, ASN_STR - 1),
                                   'trophy': _cstr(p, ASN_TROPHY, ASN_STR - 1)})
    doc['_recs'] = recs
    doc['_tr'] = tr_recs
    df = _live(d, by_mem, 18)
    doc['_df'] = df[0] if df else None
    doc['_po'] = _live(d, by_mem, 20)
    doc['_sp'] = _live(d, by_mem, 22)
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


class EditError(ValueError):
    pass


def _put_str(p, field, val, what):
    """strcpy val into p at field = (offset, size incl. NUL); the tail after the NUL is left as it was."""
    at, size = field
    if not isinstance(val, str):
        raise EditError(f'{what}: not a string')
    vb = val.encode('latin-1')
    if len(vb) >= size or 0 in vb:
        raise EditError(f'{what}: {val!r} longer than {size - 1} bytes (or holds a NUL)')
    if _cstr(p, at, size - 1) != val:
        p[at:at + len(vb) + 1] = vb + b'\0'


def _int(v, lo, hi, what):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise EditError(f'{what}: {v!r} not an int in {lo}..{hi}')
    return v


def _put_enc(buf, off, old, p):
    if bytes(p) != old:
        buf[off:off + len(p)] = _enc(bytes(p))


def _patch_team(buf, t, js):
    p = bytearray(t['p'])
    off = t['off']
    name = js.get('name')
    if isinstance(name, str) and name != t['name']:
        nb = name.encode('latin-1')
        if len(nb) >= NAME_FIELD:
            raise EditError(f'team {t["tid"]} name: longer than {NAME_FIELD - 1} bytes')
        p[0x12:0x12 + NAME_FIELD] = nb + bytes(NAME_FIELD - len(nb))
    if 'manager' in js and js['manager'] != t['manager']:
        _put_str(p, T_MANAGER, js['manager'], f'team {t["tid"]} manager')
    for key, field in (('abbrev', T_ABBREV), ('stadium', T_STADIUM), ('city8', T_CITY8)):
        if key in js:
            _put_str(p, field, js[key], f'team {t["tid"]} {key}')
    if 'field_ac' in js and js['field_ac'] != t['field_ac']:
        struct.pack_into('<I', p, 0xac, _int(js['field_ac'], 0, 0xffffffff, f'team {t["tid"]} field_ac'))
    if 'w' in js or 'l' in js:
        w = _int(js.get('w', t['w']), 0, 255, 'w'); l = _int(js.get('l', t['l']), 0, 255, 'l')
        if (w != t['w'] or l != t['l']):
            if t['xs_off'] is None:
                raise EditError(f'team {t["tid"]}: no xs.dat record for w/l')
            xs = bytearray(t['xs_raw'])
            xs[1] = w
            xs[2] = l
            buf[t['xs_off']:t['xs_off'] + 16] = _enc(xs)
    ros = js.get('roster')
    if (isinstance(ros, list) and t['r_off'] is not None
            and sorted({int(x) for x in ros}) != sorted(t['roster'])):
        rp = bytearray(t['r_p'])
        ids = sorted({_int(x, 100, 9999, 'roster id') for x in ros})
        if len(ids) > 126:
            raise EditError(f'team {t["tid"]} roster: {len(ids)} ids, the r.dat window holds 126')
        ids += [0] * (126 - len(ids))
        struct.pack_into('<126H', rp, 42, *ids)
        buf[t['r_off']:t['r_off'] + len(rp)] = _enc(rp)
    _put_enc(buf, off, t['p'], p)


def _patch_assn(buf, rec, js):
    off, old = rec
    p = bytearray(old)
    _put_str(p, (ASN_NAME, ASN_STR), js.get('name'), 'association name')
    _put_str(p, (ASN_TROPHY, ASN_STR), js.get('trophy'), 'association trophy')
    for o, k in ((10, 'day1'), (14, 'day2')):
        struct.pack_into('<I', p, o, _int(js.get(k), 0, 0xffffffff, f'association {k}'))
    _put_enc(buf, off, old, p)


def _patch_league(buf, rec, js):
    off, old = rec
    p = bytearray(old)
    p[1] = _int(js.get('idx'), 0, 255, 'league idx')
    _put_str(p, L_NAME, js.get('name'), 'league name')
    _put_str(p, L_ABBREV, js.get('abbrev'), 'league abbrev')
    dv = js.get('divisions')
    if not isinstance(dv, list) or len(dv) > 3:
        raise EditError('league divisions: list of at most 3 division keys')
    p[0x2a:0x2d] = bytes([_int(x, 1, 255, 'league division') for x in dv] + [0] * (3 - len(dv)))
    _put_enc(buf, off, old, p)


def _patch_division(buf, rec, js):
    off, old = rec
    p = bytearray(old)
    p[1] = _int(js.get('league_idx'), 0, 255, 'division league_idx')
    p[2] = _int(js.get('div_idx'), 0, 255, 'division div_idx')
    _put_str(p, D_NAME, js.get('name'), 'division name')
    tm = js.get('teams')
    if not isinstance(tm, list) or len(tm) > 10:
        raise EditError('division teams: list of at most 10 team ids')
    p[0x14:0x1e] = bytes([_int(x, 1, 28, 'division team') for x in tm] + [0] * (10 - len(tm)))
    _put_enc(buf, off, old, p)


def _patch_tr(buf, rec, js):
    off, old = rec
    p = bytearray(old)
    struct.pack_into('<I', p, 2, _int(js.get('day'), 0, 0xffffffff, 'transaction day'))
    p[20] = _int(js.get('kind'), 0, 255, 'transaction kind')
    for k, base in ((1, 6), (2, 13)):
        for o, f in ((0, 'pid'), (2, 'f'), (4, 'g')):
            struct.pack_into('<H', p, base + o, _int(js.get(f'{f}{k}'), 0, 0xffff, f'transaction {f}{k}'))
        p[base + 6] = _int(js.get(f'team{k}'), 0, 255, f'transaction team{k}')
    buf[off:off + len(p)] = p


def _hexbytes(h, n, what):
    try:
        b = bytes.fromhex(h)
    except (TypeError, ValueError):
        raise EditError(f'{what}: not hex')
    if len(b) != n:
        raise EditError(f'{what}: {len(b)} bytes, the record holds {n}')
    return b


def _patch_playoff(buf, rec, js):
    off, old = rec
    p = bytearray(old)
    hd = js.get('head')
    if not isinstance(hd, list) or len(hd) != 4:
        raise EditError('playoff head: list of 4 bytes')
    p[0:4] = bytes(_int(x, 0, 255, 'playoff head') for x in hd)
    struct.pack_into('<H', p, 4, _int(js.get('f4'), 0, 0xffff, 'playoff f4'))
    struct.pack_into('<I', p, 6, _int(js.get('day'), 0, 0xffffffff, 'playoff day'))
    p[10:] = _hexbytes(js.get('hex'), len(old) - 10, 'playoff hex')
    buf[off:off + len(p)] = p


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


def _diff(a, b, path=''):
    """Paths where two decoded json values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f'{path}.{k}')
            else:
                out += _diff(a[k], b[k], f'{path}.{k}')
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f'{path} (length {len(a)} -> {len(b)}: records cannot be added or removed)']
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diff(x, y, f'{path}[{i}]')
        return out
    return [] if a == b else [path]


def _norm(js):
    """Order-free fields compared as sets."""
    js = json.loads(json.dumps(js))
    for t in js.get('teams', []):
        if isinstance(t.get('roster'), list):
            t['roster'] = sorted(set(t['roster']))
    return js


def encode_bytes(d, js):
    """Apply every edit in js (a decode() document) to the file bytes d.  Raises EditError on an edit this codec
    cannot write, or one that does not read back: the output is decoded again and every path that differs between
    the original decode and js must equal js there."""
    buf = bytearray(d)
    doc = parse_container(d)
    base = build_json(doc)
    want = _norm(js)
    edits = _diff(_norm(base), want)
    if not edits:
        return bytes(buf)

    def pairs(key, recs):
        got = js.get(key, [])
        if len(got) != len(recs):
            raise EditError(f'{key}: {len(got)} records, the file has {len(recs)} (records cannot be added or removed)')
        return [(r, g) for r, g, b in zip(recs, got, base[key]) if g != b]

    by_tid = {t['tid']: t for t in doc['teams']}
    for jt, bt in zip(js.get('teams', []), base['teams']):
        if jt != bt:
            t = by_tid.get(jt.get('tid'))
            if t is None or jt.get('tid') != bt['tid']:
                raise EditError('teams: tid changed or reordered')
            _patch_team(buf, t, jt)
    for key, recs in (('games', doc['games']), ('specials', doc['specials'])):
        for g, jg in pairs(key, recs):
            _patch_game(buf, g, jg)
    for key, recs, fn in (('association', doc['_recs']['a'], _patch_assn), ('leagues', doc['_recs']['l'], _patch_league),
                          ('divisions', doc['_recs']['d'], _patch_division), ('transactions', doc['_tr'], _patch_tr),
                          ('playoff', doc['_po'], _patch_playoff)):
        for rec, jr in pairs(key, recs):
            if jr.get('key', None) is not None and key in ('association', 'leagues', 'divisions'):
                if jr['key'] != base[key][recs.index(rec)]['key']:
                    raise EditError(f'{key}: key is the index key and cannot change')
            fn(buf, rec, jr)
    for (off, old), jr in pairs('sp', doc['_sp']):
        buf[off:off + len(old)] = _hexbytes(jr.get('hex'), len(old), 'sp hex')
    if base.get('draft') != js.get('draft'):
        if doc['_df'] is None or not isinstance(js.get('draft', {}).get('values'), list):
            raise EditError('draft: no df.dat record / values not a list')
        off, old = doc['_df']
        vals = js['draft']['values']
        if len(vals) != len(base['draft']['values']):
            raise EditError('draft values: length is fixed')
        p = bytearray(old)
        for i, v in enumerate(vals):
            struct.pack_into('<H', p, 2 * i, _int(v, 0, 0xffff, 'draft value'))
        buf[off:off + len(p)] = p

    got = _norm(build_json(parse_container(bytes(buf))))
    bad = []
    for path in edits:
        if _diff(_pick(got, path), _pick(want, path)):
            bad.append(path)
    if bad:
        raise EditError('edits this codec cannot write (or that do not read back): ' + ', '.join(bad[:20])
                        + (f' (+{len(bad) - 20} more)' if len(bad) > 20 else ''))
    return bytes(buf)


def _pick(js, path):
    import re
    cur = js
    for name, idx in re.findall(r'\.([^.\[ ]+)|\[(\d+)\]', path.split(' (')[0]):
        try:
            cur = cur[int(idx)] if idx else cur[name]
        except (KeyError, IndexError, TypeError):
            return KeyError
    return cur


def cmd_encode(inp, jsonp, outp):
    with open(inp, 'rb') as fh:
        d = fh.read()
    with open(jsonp, 'r') as fh:
        js = json.load(fh)
    try:
        out = encode_bytes(d, js)
    except EditError as e:
        sys.stderr.write(f'league.py encode: {e}\n')
        return 1
    with open(outp, 'wb') as fh:
        fh.write(out)
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
