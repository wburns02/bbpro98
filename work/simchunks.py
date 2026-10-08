#!/usr/bin/env python3
"""Data chunks of SIM.DAT and Stadia/*.DAT / *.DT (the 00 01 06 07 containers of work/chunkdat.py), as JSON.
Spec: work/spec/SIMCHUNKS_FORMAT.md. Layouts from the BBSIM / FastSim loaders (Claude, 2026-10-07); the chunks GLM
data lane (re/targets/chunks/lanes/data) found the record sizes of most tables.

usage: simchunks.py decode NAME in.bin out.json        NAME starts with the chunk id, e.g. 947d_ANAHEIM.bin
       simchunks.py encode NAME in.bin edited.json out.bin    (in.bin is not read)

The chunk id is the low half of the container key, a hash of the chunk's file name (chunkdat.py):
  947d shape.tbl  stadium 3D models          ce8c wall.tbl   ground polygons and outfield walls
  e957 info.dat   stadium info               e1a4 injury.dat injuries
  e6e7 cams.cfg   camera views               5200 bpi.str    in-game menu strings
  6be6 logic.dat  fielding logic tables      b0e7 numbers.inf uniform number placement
  bb43 sndvol.cfg sound volumes
The texture chunks cb7c txfill.dbm and 7709 txmap.dbm are multi-frame bitmaps: work/chunkgfx.py.
Keys starting with "_" are derived or kept for a byte-exact rebuild; the rest is content.
"""
import json
import struct
import sys


def _fail(msg):
    raise ValueError(msg)


def _u(fmt, d, p):
    return struct.unpack_from(fmt, d, p)


def _cfix(d, p, n):
    """Fixed NUL-padded string: (text, stale bytes after the NUL or None)."""
    raw = d[p:p + n]
    e = raw.find(b'\0')
    if e < 0:
        return raw.decode('latin1'), None
    tail = raw[e:]
    return raw[:e].decode('latin1'), (None if not tail.strip(b'\0') else tail.decode('latin1'))


def _efix(text, stale, n):
    b = text.encode('latin1')
    if len(b) > n:
        _fail(f'{text!r} longer than {n} bytes')
    if stale is not None and len(b) + len(stale) == n:
        return b + stale.encode('latin1')
    return b.ljust(n, b'\0')


def _ff(v):
    """0xff = none, as null."""
    return None if v == 0xff else v


def _unff(v):
    return 0xff if v is None else v


# ------------------------------------------------------------------ offset-table resources (GID: wall.tbl, DAT: shape.tbl)
def _tables(d, magic):
    """'XXX:' u32 size, then the payload: u32 offsets (from the payload start) ending with 0, then the records.
    Loader: BBSIM FUN_680a8926 (GID:) / FUN_680a7e26 (DAT:) turn the offsets into pointers and count them."""
    if d[:4] != magic or _u('<I', d, 4)[0] != len(d) - 8:
        _fail(f'not a {magic.decode()} resource')
    P = d[8:]
    offs, p = [], 0
    while True:
        (o,) = _u('<I', P, p)
        p += 4
        if o == 0:
            return P, offs
        offs.append(o)


def _wrap(magic, recs, tail=b''):
    """Lay the records out after the offset table (the shipped order)."""
    head = 4 * (len(recs) + 1)
    offs, a = [], head
    for r in recs:
        offs.append(a)
        a += len(r)
    P = struct.pack('<%dI' % (len(recs) + 1), *offs, 0) + b''.join(recs) + tail
    return magic + struct.pack('<I', len(P)) + P


# wall.tbl: BBSIM Ts_grnd.cpp. The field is a set of convex ground polygons. Each edge is a half-plane: point (x, y)
# and a normal (s8, 128 = 1.0). The file stores the outward normal (a position is inside when every edge has
# normal . (pos - point) <= 0, FUN_680a82f0 via FUN_680a8364); the JSON has the inward one (the negation), which
# keeps the full s8 range editable. A polygon's edges are first_edge .. first_edge + edge_count - 1, 0-based in the
# ground's edge list. An edge shared with another
# polygon names its twin (1-based); the unshared edges are the walls (FUN_680a866d walks them), with a wall height at
# the edge's start and end point (FUN_680a8fff interpolates; units 1/30 ft, 300 = 10 ft). Polygon height:
# base_height + slope * (normal . (pos - point of edge slope_edge)) >> 12 (FUN_680a83e9). The ground is flat in every
# shipped park (slope 0).
def dec_wall(d):
    P, offs = _tables(d, b'GID:')
    grounds = []
    for k, r in enumerate(offs):
        xr, yr, ne, npoly, opoly = _u('<hhhhH', P, r)
        if opoly != 10 + 12 * ne:
            _fail('wall.tbl: polygon table not after the edges')
        edges = []
        for i in range(ne):
            nx, ny, x, y, h0, h1, twin = _u('<bbhhhhh', P, r + 10 + 12 * i)
            edges.append({'x': x, 'y': y, 'inward_normal_x': -nx, 'inward_normal_y': -ny, 'wall_height_start': h0,
                          'wall_height_end': h1, 'twin_edge': twin})
        polys = []
        for i in range(npoly):
            first, n, slope, base, at6, sedge = _u('<hBBhhh', P, r + opoly + 10 * i)
            polys.append({'first_edge': first, 'edge_count': n, 'slope': slope, 'base_height': base,
                          'at_0x6': at6, 'slope_edge': sedge})
        grounds.append({'x_extent': xr, 'y_extent': yr, 'edges': edges, 'polygons': polys})
        end = r + opoly + 10 * npoly
        if end != (offs[k + 1] if k + 1 < len(offs) else len(P)):
            _fail('wall.tbl: bytes between grounds')
    return {'grounds': grounds}


def enc_wall(doc):
    recs = []
    for g in doc['grounds']:
        es, ps = g['edges'], g['polygons']
        b = struct.pack('<hhhhH', g['x_extent'], g['y_extent'], len(es), len(ps), 10 + 12 * len(es))
        for e in es:
            b += struct.pack('<bbhhhhh', -e['inward_normal_x'], -e['inward_normal_y'], e['x'], e['y'], e['wall_height_start'],
                             e['wall_height_end'], e['twin_edge'])
        for q in ps:
            b += struct.pack('<hBBhhh', q['first_edge'], q['edge_count'], q['slope'], q['base_height'], q['at_0x6'],
                             q['slope_edge'])
        recs.append(b)
    return _wrap(b'GID:', recs)


# shape.tbl: BBSIM Ts_model.cpp. 3D models of the park (stands, walls, foul poles ...). Model: flags (0x40 sort parts
# by depth, FUN_680a92ca; 0x80 has instance states), default state bytes, levels, bounding radius (+0xc; visibility
# test FUN_680a90e0) and box. Only the first level is drawn. Part: state slot (0xff none) whose value picks the variant
# (FUN_680a9cb0, clamped) or hides the part when 0xff (FUN_680aa7b0); depth vertex / depth reference vertex for the
# sort (0xff = none, stored as null); its vertices (s16 x, y, z; parts may share one list). Variant kind 0 = a
# polygon list. Polygon (FUN_680a6381):
# flags bits 0-1 type (0 always drawn, 1 back-face tested against vertex normal_vertex, 2 never), 0x80, 0x10 shade,
# 0x08; color, color2 (0xf4 / 0xf5 = crowd, drawn by the crowd renderer); 0xff-terminated vertex indices.
# Bytes 3 and 4 of each polygon are cleared by the loader (FUN_680a7e26) and kept as _runtime.
def dec_shape(d):
    P, offs = _tables(d, b'DAT:')
    models = []
    for k, r in enumerate(offs):
        nxt = offs[k + 1] if k + 1 < len(offs) else len(P)
        fl, b1, w2, nst, ost, nlev, olev, rad, x0, y0, z0, x1, y1, z1 = _u('<BBHhHhH7h', P, r)
        m = {'flags': fl, 'at_0x1': b1, 'at_0x2': w2, 'radius': rad, 'box_min': [x0, y0, z0],
             'box_max': [x1, y1, z1], 'states': list(P[r + ost:r + ost + nst]) if nst else [], 'levels': []}
        if not nst:
            m['_state_off'] = ost
        owner = {}                                        # vertex list offset -> (index of the first part using it, n)
        npart_all = 0
        for li in range(nlev):
            l0, npart, opart = _u('<hhH', P, r + olev + 6 * li)
            parts = []
            for pi in range(npart):
                st, dv, dr, nv, ov, nvar, ovar, a10, a12 = _u('<BBBBHhHhh', P, r + opart + 14 * pi)
                pt = {'state_slot': _ff(st), 'depth_vertex': _ff(dv), 'depth_ref_vertex': _ff(dr),
                      'vertices': [list(_u('<3h', P, r + ov + 6 * i)) for i in range(nv)],
                      'at_0xa': a10, 'at_0xc': a12, 'variants': []}
                if ov in owner:
                    if owner[ov][1] != nv:
                        _fail('shape.tbl: a shared vertex list with two lengths')
                    pt['_shares'] = owner[ov][0]
                else:
                    owner[ov] = (npart_all, nv)
                npart_all += 1
                for vi in range(nvar):
                    kind, v1, npoly, opoly, v6 = _u('<BBhHh', P, r + ovar + 8 * vi)
                    if kind != 0:
                        _fail(f'shape.tbl: variant kind {kind}')
                    polys = []
                    for qi in range(npoly):
                        qf, c1, c2, r3, r4, nvx, oidx = _u('<BBBBBBH', P, r + opoly + 8 * qi)
                        e = P.index(b'\xff', r + oidx)
                        q = {'flags': qf, 'color': c1, 'color2': c2, 'normal_vertex': _ff(nvx),
                             'vertices': list(P[r + oidx:e])}
                        if r3 or r4:
                            q['_runtime'] = [r3, r4]
                        polys.append(q)
                    pt['variants'].append({'at_0x1': v1, 'at_0x6': v6, 'polygons': polys})
                parts.append(pt)
            m['levels'].append({'at_0x0': _ff(l0), 'parts': parts})
        if _enc_model(m) != P[r:nxt]:
            _fail(f'shape.tbl: model {k} is not in the shipped layout')
        models.append(m)
    return {'models': models}


def _enc_model(m):
    """Shipped layout: header (26), levels, then per level: its parts, the vertex lists they use first, and per part
    its variants, each variant's polygons followed by their index lists; the state bytes last. A part keeps sharing
    the vertex list of the part _shares names (a part index counted over all levels) while the two lists are equal."""
    levels = m['levels']
    out = bytearray(26)
    lev_at = len(out)
    out += bytes(6 * len(levels))
    allparts = [pt for lev in levels for pt in lev['parts']]
    vl_at = []                                            # vertex list offset of each part, by global part index
    g = 0
    for li, lev in enumerate(levels):
        parts = lev['parts']
        part_at = len(out)
        out += bytes(14 * len(parts))
        l0 = lev['at_0x0']
        struct.pack_into('<hhH', out, lev_at + 6 * li, 0xff if l0 is None else l0, len(parts), part_at)
        for pt in parts:
            sh = pt.get('_shares')
            if isinstance(sh, int) and 0 <= sh < len(vl_at) and allparts[sh]['vertices'] == pt['vertices']:
                vl_at.append(vl_at[sh])
            else:
                vl_at.append(len(out))
                for v in pt['vertices']:
                    out += struct.pack('<3h', *v)
        for pi, pt in enumerate(parts):
            var_at = len(out)
            out += bytes(8 * len(pt['variants']))
            for vi, var in enumerate(pt['variants']):
                polys = var['polygons']
                poly_at = len(out)
                out += bytes(8 * len(polys))
                struct.pack_into('<BBhHh', out, var_at + 8 * vi, 0, var['at_0x1'], len(polys), poly_at, var['at_0x6'])
                for qi, q in enumerate(polys):
                    r3, r4 = q.get('_runtime', [0, 0])
                    struct.pack_into('<BBBBBBH', out, poly_at + 8 * qi, q['flags'], q['color'], q['color2'], r3, r4,
                                     _unff(q['normal_vertex']), len(out))
                    if 0xff in q['vertices']:
                        _fail('shape.tbl: vertex index 255 ends the list')
                    out += bytes(q['vertices']) + b'\xff'
            struct.pack_into('<BBBBHhHhh', out, part_at + 14 * pi, _unff(pt['state_slot']), _unff(pt['depth_vertex']),
                             _unff(pt['depth_ref_vertex']), len(pt['vertices']), vl_at[g + pi], len(pt['variants']),
                             var_at, pt['at_0xa'], pt['at_0xc'])
        g += len(parts)
    st = m['states']
    st_at = len(out) if st else m.get('_state_off', 0)
    out += bytes(st)
    struct.pack_into('<BBHhHhH7h', out, 0, m['flags'], m['at_0x1'], m['at_0x2'], len(st), st_at, len(levels), lev_at,
                     m['radius'], *m['box_min'], *m['box_max'])
    return bytes(out)


def enc_shape(doc):
    return _wrap(b'DAT:', [_enc_model(m) for m in doc['models']])


# info.dat (Stadia/<park>.DAT, the sim's copy) and the shell's <park>.DT (74 bytes). Both "STA:" u32 size.
# .DAT: name[63] (8), dome (71), short_name[30] (72); BBSIM FUN_6806f2eb / FastSim read these 0x5e bytes into the
# stadium object (+0x12). Then BBSIM FUN_6806c898 (Smodel.cpp, seek 0x66) = FastSim 52208: s16 version (must be 6),
# sky color (0 = default 0x47/0x4f; DAT_681ec12c), field_pattern (stored +1 at stadium +0x82: 1 turf, 2 mow lines, 3 checkered, 4 circles), at_0x6c (stadium +0x20),
# color-cycle frames (FUN_68074849, one step per 1000 ticks), crowd colors (FUN_6807491f paints polygon color 0xf4
# with pair 1 and 0xf5 with pair 2), 4 palette cycles (start, count, step; FUN_6806d066 rotates them), the foul poles
# (+8, +0x18), two side pairs read by FUN_68019330 (dugouts) and FUN_68061c40 (on-deck circles), then the fence
# outline (n x (x, y, flag)), which no loader reads.
# .DT (BBShell 20565 / EZShell 15289): u8 version 1, name[63], dome, turf (the shell's stadium +0x2c / +0x30).
def _xy(d, p):
    x, y = _u('<hh', d, p)
    return {'x': x, 'y': y}


def dec_info(d):
    if d[:4] != b'STA:' or _u('<I', d, 4)[0] != len(d) - 8:
        _fail('not a STA: resource')
    if len(d) == 74:
        if d[8] != 1:
            _fail('stadium .DT version is not 1')
        name, st = _cfix(d, 9, 63)
        doc = {'_kind': 'shell .DT', 'name': name, 'dome': d[72], 'turf': d[73]}
        if st is not None:
            doc['_name_tail'] = st
        return doc
    name, st1 = _cfix(d, 8, 63)
    short, st2 = _cfix(d, 72, 30)
    ver, sky, a6a, a6c, ncyc = _u('<5h', d, 102)
    if ver != 6:
        _fail('stadium info version is not 6')
    c = _u('<4h', d, 112)
    (n,) = _u('<h', d, 168)
    if 170 + 6 * n != len(d):
        _fail('stadium info: bytes after the fence outline')
    doc = {'_kind': 'sim info', 'name': name, 'dome': d[71], 'short_name': short, 'sky_color': sky,
           'field_pattern': a6a, 'at_0x6c': a6c, 'color_cycle_frames': ncyc,
           'crowd_colors': [[c[0], c[1]], [c[2], c[3]]],
           'palette_cycles': [dict(zip(('start', 'count', 'step'), _u('<3h', d, 120 + 6 * i))) for i in range(4)],
           'left_field_pole': _xy(d, 144), 'right_field_pole': _xy(d, 148),
           'dugouts': [_xy(d, 152), _xy(d, 156)], 'on_deck_circles': [_xy(d, 160), _xy(d, 164)],
           'fence': [dict(zip(('x', 'y', 'flag'), _u('<3h', d, 170 + 6 * i))) for i in range(n)]}
    for k, t in (('_name_tail', st1), ('_short_name_tail', st2)):
        if t is not None:
            doc[k] = t
    return doc


def enc_info(doc):
    if 'turf' in doc:
        P = bytes([1]) + _efix(doc['name'], doc.get('_name_tail'), 63) + bytes([doc['dome'], doc['turf']])
    else:
        P = _efix(doc['name'], doc.get('_name_tail'), 63) + bytes([doc['dome']])
        P += _efix(doc['short_name'], doc.get('_short_name_tail'), 30)
        P += struct.pack('<5h', 6, doc['sky_color'], doc['field_pattern'], doc['at_0x6c'], doc['color_cycle_frames'])
        P += struct.pack('<4h', *doc['crowd_colors'][0], *doc['crowd_colors'][1])
        if len(doc['palette_cycles']) != 4:
            _fail('stadium info: 4 palette cycles')
        for pc in doc['palette_cycles']:
            P += struct.pack('<3h', pc['start'], pc['count'], pc['step'])
        for pt in [doc['left_field_pole'], doc['right_field_pole'], *doc['dugouts'], *doc['on_deck_circles']]:
            P += struct.pack('<hh', pt['x'], pt['y'])
        P += struct.pack('<h', len(doc['fence']))
        for f in doc['fence']:
            P += struct.pack('<3h', f['x'], f['y'], f['flag'])
    return b'STA:' + struct.pack('<I', len(P)) + P


# cams.cfg: BBSIM Cams.cpp (FUN_680143a4 load, FUN_680145a3 / FUN_68014a4a save; the game rewrites it). The current
# view (0..5 one camera record each, 6 = multi camera, records 6..14) with its target and multi-camera index, the 15
# camera records, then 10 saved slots (current slot, used flags, names, view / target / multi, 15 records each).
CAM = ('x', 'y', 'pitch', 'roll', 'at_0xc', 'heading', 'distance', 'z', 'zoom')
CAMF = '<iihhhhiih'                                       # 26 bytes; distance is clamped to 30..60000 on load


def _cams(d, p):
    return [dict(zip(CAM, _u(CAMF, d, p + 26 * i))) for i in range(15)], p + 390


def dec_cams(d):
    if len(d) != 5078:
        _fail('cams.cfg is 5078 bytes')
    ver, view, tgt, multi = _u('<Hiii', d, 0)
    cams, p = _cams(d, 14)
    (cur,) = _u('<i', d, 404)
    slots = []
    for i in range(10):
        name, st = _cfix(d, 418 + 64 * i, 64)
        sl = {'used': d[408 + i], 'name': name, 'view': _u('<i', d, 1058 + 4 * i)[0],
              'target': _u('<i', d, 1098 + 4 * i)[0], 'multi_camera': _u('<i', d, 1138 + 4 * i)[0],
              'cameras': _cams(d, 1178 + 390 * i)[0]}
        if st is not None:
            sl['_name_tail'] = st
        slots.append(sl)
    return {'version': ver, 'view': view, 'target': tgt, 'multi_camera': multi, 'cameras': cams,
            'current_slot': cur, 'slots': slots}


def enc_cams(doc):
    pc = lambda cs: b''.join(struct.pack(CAMF, *(c[k] for k in CAM)) for c in cs)
    sl = doc['slots']
    if len(sl) != 10 or len(doc['cameras']) != 15 or any(len(s['cameras']) != 15 for s in sl):
        _fail('cams.cfg: 15 cameras and 10 slots of 15')
    out = struct.pack('<Hiii', doc['version'], doc['view'], doc['target'], doc['multi_camera']) + pc(doc['cameras'])
    out += struct.pack('<i', doc['current_slot']) + bytes(s['used'] for s in sl)
    out += b''.join(_efix(s['name'], s.get('_name_tail'), 64) for s in sl)
    for k in ('view', 'target', 'multi_camera'):
        out += struct.pack('<10i', *(s[k] for s in sl))
    return out + b''.join(pc(s['cameras']) for s in sl)


# injury.dat: BBSIM FUN_68038227 / FUN_68038583. 22 s16 offsets (19 category tables, the injuries, the durations, the
# after rolls; contiguous, so derived), 19 default odds (replaced at load by settings 0x354 + i, FUN_68002cd0), the
# category tables (cumulative threshold against rand 1..999 -> injury number), 205 injuries of 96 bytes (number = i + 1,
# 1-based duration and after-roll indexes, part / detail / condition text of 30), 46 durations (days = base + n dice
# of `sides`; below reroll_below the second dice set is rolled instead) and 12 after rolls (n dice of `sides` + base;
# 9998 / 9997 bases give the 9999 / 9998 markers).
def _dice(t):
    return {'dice': t[0], 'sides': t[1], 'base': t[2]}


def _undice(x):
    return struct.pack('<3h', x['dice'], x['sides'], x['base'])


def dec_injury(d):
    offs = _u('<22h', d, 0)
    odds = list(_u('<19h', d, 44))
    p, cats = 82, []
    for i in range(19):
        if offs[i] != p:
            _fail('injury.dat: category tables not contiguous')
        (n,) = _u('<h', d, p)
        t = _u('<%dh' % (2 * n), d, p + 2)
        cats.append([{'threshold': t[2 * j], 'injury': t[2 * j + 1]} for j in range(n)])
        p += 2 + 4 * n
    nrec = (offs[20] - offs[19]) // 96
    ndur = (offs[21] - offs[20]) // 16
    naft = (len(d) - offs[21]) // 8
    if offs[19] != p or offs[19] + 96 * nrec != offs[20] or offs[20] + 16 * ndur != offs[21] or \
            offs[21] + 8 * naft != len(d):
        _fail('injury.dat: tables not contiguous')
    injuries = []
    for i in range(nrec):
        r = offs[19] + 96 * i
        num, dur, aft = _u('<3h', d, r)
        if num != i + 1:
            _fail('injury.dat: injury numbers not 1..n')
        rec = {'duration': dur, 'after_roll': aft}
        for j, f in enumerate(('part', 'detail', 'condition')):
            t, st = _cfix(d, r + 6 + 30 * j, 30)
            rec[f] = t
            if st is not None:
                rec['_' + f + '_tail'] = st
        injuries.append(rec)
    durs = []
    for i in range(ndur):
        t = _u('<8h', d, offs[20] + 16 * i)
        if t[0] != i + 1:
            _fail('injury.dat: duration numbers not 1..n')
        durs.append({'roll': _dice(t[1:4]), 'reroll_below': t[4], 'reroll': _dice(t[5:8])})
    afts = []
    for i in range(naft):
        t = _u('<4h', d, offs[21] + 8 * i)
        if t[0] != i + 1:
            _fail('injury.dat: after-roll numbers not 1..n')
        afts.append(_dice(t[1:4]))
    return {'default_odds': odds, 'categories': cats, 'injuries': injuries, 'durations': durs, 'after_rolls': afts}


def enc_injury(doc):
    if len(doc['categories']) != 19 or len(doc['default_odds']) != 19:
        _fail('injury.dat: 19 categories')
    cat = b''
    offs = []
    for c in doc['categories']:
        offs.append(82 + len(cat))
        cat += struct.pack('<h', len(c)) + b''.join(struct.pack('<hh', e['threshold'], e['injury']) for e in c)
    rec = b''
    for i, r in enumerate(doc['injuries']):
        rec += struct.pack('<3h', i + 1, r['duration'], r['after_roll'])
        rec += b''.join(_efix(r[f], r.get('_' + f + '_tail'), 30) for f in ('part', 'detail', 'condition'))
    dur = b''.join(struct.pack('<h', i + 1) + _undice(x['roll']) + struct.pack('<h', x['reroll_below']) +
                   _undice(x['reroll']) for i, x in enumerate(doc['durations']))
    aft = b''.join(struct.pack('<h', i + 1) + _undice(x) for i, x in enumerate(doc['after_rolls']))
    a = 82 + len(cat)
    offs += [a, a + len(rec), a + len(rec) + len(dur)]
    return struct.pack('<22h', *offs) + struct.pack('<19h', *doc['default_odds']) + cat + rec + dur + aft


# logic.dat: BBSIM Act.cpp FUN_68001b9b. Fielding assignments: 5 u16 section offsets, then 9-byte rows, one job per
# fielder (byte k -> fielder k's job, +0x2ad, FUN_680010ef / FUN_6802cf75). Job codes are the "COVER_1B" name table.
FIELDERS = ('1B', '2B', '3B', 'SS', 'P', 'C', 'RF', 'CF', 'LF')
JOBS = ('COVER_1B', 'COVER_2B', 'COVER_3B', 'COVER_HOME', 'BACKUP_1B', 'BACKUP_2B', 'BACKUP_3B', 'BACKUP_HOME',
        'BACKUP_RF', 'BACKUP_CF', 'BACKUP_LF', 'BACKUP_BOTH', 'CUTOFF', 'RELAY', 'DO_LOGIC')
RUNNERS = ('No runners', 'Runner on 1st', 'Runner on 2nd', 'Runners on 1st & 2nd', 'Runner on 3rd',
           'Runners on 1st & 3rd', 'Runners on 2nd & 3rd', 'Bases loaded')
EVENTS = ('STRIKE_OUT', 'WALK_ON_BALLS', 'INTENTIONAL_WALK', 'PICKOFF_1B', 'PICKOFF_2B', 'PICKOFF_3B', 'WILD_PITCH',
          'RUNNER_STEALING', 'BATTER_HIT')
# section: (name, outer keys, inner keys, ball directions); row index = (outer * len(inner) + inner) * len(dirs) + dir
LOGIC = (('infield', RUNNERS, ('Grounder', 'Linedrive', 'Popfly'), ('1B', '2B', '3B', 'SS', 'P')),
         ('outfield', RUNNERS, ('Single', 'Extra Base', 'Fly'), ('RF', 'CF', 'LF')),
         ('bunt', RUNNERS, None, ('1B', '3B', 'P', 'C')),
         ('special', EVENTS, None, RUNNERS),
         ('batting_practice', None, None, None))


def _logic_keys(outer, inner, dirs):
    ks = [()]
    for lv in (outer, inner, dirs):
        if lv:
            ks = [k + (x,) for k in ks for x in lv]
    return ks


def dec_logic(d):
    offs = _u('<5H', d, 0)
    doc = {'_jobs': {str(i): j for i, j in enumerate(JOBS)}}
    p = 10
    for si, (name, outer, inner, dirs) in enumerate(LOGIC):
        if offs[si] != p:
            _fail('logic.dat: sections not contiguous')
        sec = {}
        for path in _logic_keys(outer, inner, dirs):
            row = dict(zip(FIELDERS, d[p:p + 9]))
            p += 9
            if not path:
                sec = row
                continue
            t = sec
            for k in path[:-1]:
                t = t.setdefault(k, {})
            t[path[-1]] = row
        doc[name] = sec
    if p != len(d):
        _fail('logic.dat: bytes after the last section')
    return doc


def enc_logic(doc):
    offs, body = [], b''
    for name, outer, inner, dirs in LOGIC:
        offs.append(10 + len(body))
        for path in _logic_keys(outer, inner, dirs):
            row = doc[name]
            for k in path:
                row = row[k]
            body += bytes(row[f] for f in FIELDERS)
    return struct.pack('<5H', *offs) + body


# numbers.inf: BBSIM FUN_6800b2fd reads it whole, FUN_6800fa2b reads rows. Uniform number placement: row =
# (animation - 0x15) * 28 + side * 14 + frame, animation from FUN_6800adb0 (0x15..0x2f), side = player +0x8d, frame
# < 14. Row: font (index into DAT_680b8370), first glyph frame (digit glyph = frame + digit * 3 * k, +1 / +2 for the
# left / right digit of two), x, y. Unused rows (-1, 0, 0, 0) are null.
def dec_numbers(d):
    if len(d) != 756 * 8:
        _fail('numbers.inf is 756 rows of 8 bytes')
    anims = []
    for a in range(27):
        sides = []
        for s in range(2):
            fr = []
            for f in range(14):
                t = _u('<4h', d, 8 * (a * 28 + s * 14 + f))
                fr.append(None if t == (-1, 0, 0, 0) else dict(zip(('font', 'glyph_frame', 'x', 'y'), t)))
            sides.append(fr)
        anims.append({'_animation': 0x15 + a, 'side_0': sides[0], 'side_1': sides[1]})
    return {'animations': anims}


def enc_numbers(doc):
    out = b''
    if len(doc['animations']) != 27:
        _fail('numbers.inf: 27 animations')
    for an in doc['animations']:
        for s in ('side_0', 'side_1'):
            if len(an[s]) != 14:
                _fail('numbers.inf: 14 frames per side')
            for r in an[s]:
                out += struct.pack('<4h', -1, 0, 0, 0) if r is None else \
                    struct.pack('<4h', r['font'], r['glyph_frame'], r['x'], r['y'])
    return out


# bpi.str: a Utility/Strpool.cpp string pool (FUN_680adbfe): u16 version 1, u16 count, count u16 offsets from the
# strings, u16 total bytes, the NUL-terminated strings back to back.
def dec_strpool(d):
    ver, n = _u('<HH', d, 0)
    offs = _u('<%dH' % n, d, 4)
    (tot,) = _u('<H', d, 4 + 2 * n)
    base = 6 + 2 * n
    if base + tot != len(d):
        _fail('string pool size')
    strs, p = [], 0
    for o in offs:
        if o != p:
            _fail('string pool strings not back to back')
        e = d.index(b'\0', base + p)
        strs.append(d[base + p:e].decode('latin1'))
        p = e + 1 - base
    if p != tot:
        _fail('bytes after the last string')
    return {'version': ver, 'strings': strs}


def enc_strpool(doc):
    offs, body = [], b''
    for t in doc['strings']:
        offs.append(len(body))
        body += t.encode('latin1') + b'\0'
    n = len(offs)
    return struct.pack('<HH%dHH' % n, doc['version'], n, *offs, len(body)) + body


# sndvol.cfg: 6 u16. BBSIM.dll still has the name (VA 0x680c5070) but nothing reads it: the volumes now come from the
# [Sounds] settings (SoundsOn, ActionVol, ...). Dead chunk.
def dec_sndvol(d):
    if len(d) != 12:
        _fail('sndvol.cfg is 12 bytes')
    return {'unused_values': list(_u('<6H', d, 0))}


def enc_sndvol(doc):
    return struct.pack('<6H', *doc['unused_values'])


def _textures(*_):
    _fail('cb7c / 7709 are DBM bitmaps: use work/chunkgfx.py')


LAYOUTS = {'ce8c': (dec_wall, enc_wall), '947d': (dec_shape, enc_shape), 'e957': (dec_info, enc_info),
           'e6e7': (dec_cams, enc_cams), 'e1a4': (dec_injury, enc_injury), '6be6': (dec_logic, enc_logic),
           'b0e7': (dec_numbers, enc_numbers), '5200': (dec_strpool, enc_strpool), 'bb43': (dec_sndvol, enc_sndvol),
           'cb7c': (_textures, _textures), '7709': (_textures, _textures)}


def _layout(name):
    cid = name.split('/')[-1][:4].lower()
    if cid not in LAYOUTS:
        _fail(f'unknown chunk id {cid}')
    return LAYOUTS[cid]


def decode(name, d):
    return _layout(name)[0](d)


def encode(name, doc):
    return _layout(name)[1](doc)


def main():
    mode, name = sys.argv[1], sys.argv[2]
    if mode == 'decode':
        with open(sys.argv[3], 'rb') as fh:
            doc = decode(name, fh.read())
        with open(sys.argv[4], 'w') as fh:
            json.dump(doc, fh, indent=1)
    elif mode == 'encode':
        with open(sys.argv[4]) as fh:
            doc = json.load(fh)
        with open(sys.argv[5], 'wb') as fh:
            fh.write(encode(name, doc))
    else:
        _fail(f'unknown mode {mode}')


if __name__ == '__main__':
    main()
