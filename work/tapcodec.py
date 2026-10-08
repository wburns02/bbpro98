#!/usr/bin/env python3
"""Instant-replay tapes: hilights/*.tap and the MLBPA97.NQ0 tape container.
Spec: work/spec/TAP_FORMAT.md. Writer: BBSIM Vcr (FUN_680737fc save, FUN_680736c4 load, FUN_6807adde snapshot,
FUN_68079aee frame); reader FUN_68079e75 checks the checksum, FUN_6807ac99 restores the snapshot.

usage: tapcodec.py decode NAME in out.json
       tapcodec.py encode NAME in edited.json out     (in is not read; kept for the voldat contract)

NAME ending in .NQ0 is the container (u16 version, then [u16 0x4000|id][u32 length][tape file] per entry);
anything else is one tape file.

Every frame decodes to its full 408-byte state record. The file stores frame 0 whole and every later frame as the
u32 words that changed since the previous frame, so encode re-deltas by comparison and an edit to one frame carries
into the next frames only where those frames keep the old value.
"""
import datetime
import json
import struct
import sys

TAPE_VERSION = 0x2b
SNAPSHOT_SIZE = 0x41b
RECORD_SIZE = 0x198


def _fail(msg):
    raise ValueError(msg)


# ---------------------------------------------------------------- field layouts
# A node is a struct code ('B', 'b', 'H', 'h', 'I', 'i'), ('str', size), ('list', n, node) or a list of (key, node).

INT = {'B': 1, 'b': 1, 'H': 2, 'h': 2, 'I': 4, 'i': 4}

# Names for the fields first stored as at_0x.. (struct.at_0x<offset> -> name). Decode writes the name; encode also
# accepts the old at_0x key, so JSON written before the naming still encodes.
TAPNAMES = {
    'actor.at_0x2e': 'animation_frame_index',
    'camera.at_0x58': 'camera_save_probe_word',
    'camera.at_0x5b': 'camera_extent_bound',
    'camera.at_0x61': 'camera_look_target',
    'camera.at_0x67': 'camera_target_roll_word',
    'ball.at_0x50': 'ball_pitch_segment_flag',
    'ball.at_0x52': 'ball_flight_time',
    'ball.at_0x44': 'catch_point',
    'ball.at_0x40': 'blend_start_point',
    'ball.at_0x4c': 'exit_point',
    'sim.at_0xe92': 'sim_event_flags',
    'sim.at_0xea8': 'current_fielder_index',
    'fielders.at_0x2a5': 'fielder_assignment_id',
    'fielders.at_0x2a9': 'fielder_cover_flag',
    'offense.at_0x2b9': 'runner_new_base',
    'offense.at_0x2a9': 'runner_base_copy',
    'offense.at_0x2ad': 'fielder_assign_base',
    'offense.at_0x2b1': 'runner_logic_state',
    'record.at_0x1d': 'umpire_crew_spare_word',
    'pitch.at_0x3390': 'pitch_marker_frames',
    'pitch.at_0x3394': 'pitch_sway_offset',
    'state.at_0x00': 'inning_brick_header',
    'snapshot.at_0x7e': 'playing_surface',
    'ball_flight.at_0xe70': 'ball_flight_frame_index',
    'path.at_0xe78': 'catch_height_frame',
    'path.at_0xe7c': 'first_bounce_frame',
    'path.at_0xe80': 'roll_start_frame',
    'path.at_0xe84': 'wall_bounce_frame',
    'path.at_0xe88': 'leaves_park_frame',
}


def _n(struct_name, old, node):
    """a layout entry for a field once called old: (name, node, old)"""
    return (TAPNAMES.get(f'{struct_name}.{old}', old), node, old)


def _get(d, struct_name, old, path):
    """the value of the field once called old, under its name or the old key"""
    k = TAPNAMES.get(f'{struct_name}.{old}', old)
    if k in d: return d[k]
    if old in d: return d[old]
    _fail(f'{path}: missing {k}')

ACTOR = [('x', 'h'), ('y', 'h'), ('z', 'H'), ('heading', 'h'), ('animation', 'B'), _n('actor', 'at_0x2e', 'B')]
PERSON = [('first_name', ('str', 17)), ('last_name', ('str', 17)), ('number', 'H')]

CAMERA = [_n('camera', 'at_0x58', 'H'), _n('camera', 'at_0x5b', 'H'), ('angle_0x11', 'H'), ('angle_0x15', 'H'),
          ('position', ('list', 3, 'i')), _n('camera', 'at_0x61', ('list', 3, 'H')), _n('camera', 'at_0x67', 'H')]

RECORD = [
    ('ball', [('state', 'H'), _n('ball', 'at_0x50', 'H'), _n('ball', 'at_0x52', 'H'), ('position', ('list', 3, 'h')),
              ('velocity', ('list', 3, 'h')), _n('ball', 'at_0x44', 'I'), _n('ball', 'at_0x40', 'I'),
              _n('ball', 'at_0x4c', 'I')]),
    ('sim', [_n('sim', 'at_0xe92', 'H'), _n('sim', 'at_0xea8', 'I'), ('global_b80b4', 'H')]),
    ('fielding_0x2f', 'I'),
    ('fielders', ('list', 9, ACTOR + [_n('fielders', 'at_0x2a5', 'I'), _n('fielders', 'at_0x2a9', 'I')])),
    ('offense', ('list', 5, ACTOR + [_n('offense', o, 'I') for o in ('at_0x2b9', 'at_0x2a9', 'at_0x2ad', 'at_0x2b1')])),
    ('umpires', ('list', 6, ACTOR)),
    _n('record', 'at_0x1d', 'H'),
    ('pitch', [_n('pitch', 'at_0x3390', 'I'), _n('pitch', 'at_0x3394', 'H')]),
    ('global_ec180', 'B'),
    ('global_ec194', ('list', 3, 'B')),
    ('stack_pad', 'H'),
]

TEAM_STATE = [('runs', 'B'), ('linescore', ('list', 30, 'B')), ('hits', 'B'), ('errors', 'B'),
              ('left_on_base', 'B')]

TEAM_RECORD = [('team_id', 'B'), ('setup_5', 'B'), ('name', ('str', 17)), ('alt_name', ('str', 17)),
               ('manager', ('str', 17)), ('abbrev', ('str', 5)), ('unused_0x44', ('str', 9)),
               ('stadium', ('str', 33)), ('city8', ('str', 9)), ('uniform_palette', ('list', 32, ('list', 3, 'B')))]


def _size(node):
    if isinstance(node, str):
        return INT[node]
    if isinstance(node, tuple):
        return node[1] if node[0] == 'str' else node[1] * _size(node[2])
    return sum(_size(e[1]) for e in node)


assert _size(RECORD) == RECORD_SIZE and _size(TEAM_RECORD) == 0xcd and _size(CAMERA) == 28


def _dec(node, b, p, path):
    if isinstance(node, str):
        return struct.unpack_from('<' + node, b, p)[0], p + INT[node]
    if isinstance(node, tuple) and node[0] == 'str':
        raw = b[p:p + node[1]]
        text, _, pad = raw.partition(b'\0')
        if pad.strip(b'\0'):
            _STALE[path] = raw.hex()
        return text.decode('latin1'), p + node[1]
    if isinstance(node, tuple):
        out = []
        for i in range(node[1]):
            v, p = _dec(node[2], b, p, f'{path}[{i}]')
            out.append(v)
        return out, p
    out = {}
    for e in node:
        out[e[0]], p = _dec(e[1], b, p, f'{path}.{e[0]}')
    return out, p


def _enc(node, v, out, path):
    if isinstance(node, str):
        if isinstance(v, bool) or not isinstance(v, int):
            _fail(f'{path}: expected an integer, got {v!r}')
        try:
            out += struct.pack('<' + node, v)
        except struct.error:
            _fail(f'{path}: {v} does not fit {node}')
    elif isinstance(node, tuple) and node[0] == 'str':
        if not isinstance(v, str):
            _fail(f'{path}: expected a string')
        data = v.encode('latin1')
        if len(data) >= node[1]:
            _fail(f'{path}: "{v}" is longer than {node[1] - 1} characters')
        raw = data + b'\0' * (node[1] - len(data))
        stale = _STALE.get(path)
        if stale is not None:
            old = bytes.fromhex(stale)
            if old.partition(b'\0')[0] == data:
                raw = old
        out += raw
    elif isinstance(node, tuple):
        if not isinstance(v, list) or len(v) != node[1]:
            _fail(f'{path}: expected a list of {node[1]}')
        for i, x in enumerate(v):
            _enc(node[2], x, out, f'{path}[{i}]')
    else:
        if not isinstance(v, dict):
            _fail(f'{path}: expected an object')
        for e in node:
            k = e[0] if e[0] in v or len(e) < 3 else e[2]   # (name, node, old at_0x key)
            if k not in v:
                _fail(f'{path}: missing {e[0]}')
            _enc(e[1], v[k], out, f'{path}.{k}')


_STALE = {}     # path -> raw hex of fixed strings with bytes after their NUL (kept as "_stale_strings")


def _unpack(node, b, path):
    v, p = _dec(node, b, 0, path)
    if p != len(b):
        _fail(f'{path}: size mismatch')
    return v


def _pack(node, v, path):
    out = bytearray()
    _enc(node, v, out, path)
    return bytes(out)


# ---------------------------------------------------------------- checksum (FUN_680ac5f3)

def checksum(data):
    """CRC-16/XMODEM polynomial shifted through a 32-bit register that is never masked to 16 bits."""
    c = 0
    for x in data:
        for bit in (0x80, 0x40, 0x20, 0x10, 8, 4, 2, 1):
            hi = c & 0x8000
            c = (c << 1) & 0xffffffff
            if x & bit:
                c |= 1
            if hi:
                c ^= 0x1021
    return c


# ---------------------------------------------------------------- snapshot (FUN_6807adde)

def _trim(scores):
    n = len(scores)
    while n > 9 and scores[n - 1] == 0:
        n -= 1
    return scores[:n]


def _date_serial(y, m, d):
    return (datetime.date(y, m, 1).toordinal() + d - 1) + 365


def decode_snapshot(s):
    st = {}
    st['batting_side'], st[TAPNAMES.get('state.at_0x00', 'at_0x00')] = struct.unpack_from('<HH', s, 0)
    teams = []
    for k in range(2):
        t = _unpack(TEAM_STATE, s[4 + 0x22 * k:4 + 0x22 * (k + 1)], f'state.teams[{k}]')
        t['linescore'] = _trim(t['linescore'])
        teams.append(t)
    st['teams'] = teams
    st['balls'], st['strikes'], st['outs'], st['inning'], st['clock'] = struct.unpack_from('<BBBBH', s, 0x48)
    g = s[78:78 + 0x1c3]
    recs = [_unpack(TEAM_RECORD, g[k * 0xcd:(k + 1) * 0xcd], f'team_records[{k}]') for k in range(2)]
    t = g[0x19a:]
    game = {'game_mode': t[0], 'setup_mode': t[1], 'setup_0x3e8': t[2]}
    game['stadium_file'] = _dec(('str', 14), t, 3, 'game.stadium_file')[0]
    game['association_file'] = _dec(('str', 14), t, 17, 'game.association_file')[0]
    serial, month0, day0, year = struct.unpack_from('<IBBH', t, 31)
    game['date'] = {'year': year, 'month': month0 + 1, 'day': day0 + 1}
    game['_day_serial'] = serial
    try:
        ok = _date_serial(year, month0 + 1, day0 + 1) == serial
    except ValueError:
        ok = False
    if not ok:
        game['_raw_date'] = t[31:39].hex()
    game['low_rating'] = [t[39], t[40]]
    p = 78 + 0x1c3
    stadium_dat = _dec(('str', 14), s, p, 'stadium_dat')[0]
    p += 14
    people = [_unpack(PERSON, s[p + 36 * i:p + 36 * (i + 1)], f'people[{i}]') for i in range(14)]
    p += 14 * 36
    tail = struct.unpack_from('<I', s, p)[0]
    return {'state': st, 'team_records': recs, 'game': game, 'stadium_dat': stadium_dat,
            'fielders': people[:9], 'offense': people[9:], TAPNAMES.get('snapshot.at_0x7e', 'at_0x7e'): tail}


def encode_snapshot(d):
    st = d['state']
    out = bytearray(struct.pack('<HH', st['batting_side'], _get(st, 'state', 'at_0x00', 'state')))
    if len(st['teams']) != 2:
        _fail('state.teams: expected 2')
    for k, t in enumerate(st['teams']):
        t = dict(t)
        ls = list(t['linescore'])
        if len(ls) > 30:
            _fail('linescore: more than 30 innings')
        t['linescore'] = ls + [0] * (30 - len(ls))
        out += _pack(TEAM_STATE, t, f'state.teams[{k}]')
    out += _pack([(k, 'B') for k in ('balls', 'strikes', 'outs', 'inning')] + [('clock', 'H')], st, 'state')
    if len(d['team_records']) != 2:
        _fail('team_records: expected 2')
    for k, r in enumerate(d['team_records']):
        out += _pack(TEAM_RECORD, r, f'team_records[{k}]')
    g = d['game']
    out += _pack([(k, 'B') for k in ('game_mode', 'setup_mode', 'setup_0x3e8')], g, 'game')
    out += _pack(('str', 14), g['stadium_file'], 'game.stadium_file')
    out += _pack(('str', 14), g['association_file'], 'game.association_file')
    if '_raw_date' in g:
        out += bytes.fromhex(g['_raw_date'])
    else:
        dt = g['date']
        y, m, dd = dt['year'], dt['month'], dt['day']
        if not 1 <= m <= 12 or not 1 <= dd <= 31:
            _fail('game.date: month 1..12 and day 1..31')
        out += struct.pack('<IBBH', _date_serial(y, m, dd), m - 1, dd - 1, y)
    lr = g['low_rating']
    out += _pack(('list', 2, 'B'), lr, 'game.low_rating')
    out += _pack(('str', 14), d['stadium_dat'], 'stadium_dat')
    if len(d['fielders']) != 9 or len(d['offense']) != 5:
        _fail('expected 9 fielders and 5 offense persons')
    for i, person in enumerate(d['fielders'] + d['offense']):
        out += _pack(PERSON, person, f'people[{i}]')
    out += _pack('I', _get(d, 'snapshot', 'at_0x7e', 'snapshot'), 'at_0x7e')
    if len(out) != SNAPSHOT_SIZE:
        _fail('snapshot size mismatch')
    return bytes(out)


# ---------------------------------------------------------------- frames (FUN_68079aee)

PATH_OLD = ('at_0xe78', 'at_0xe7c', 'at_0xe80', 'at_0xe84', 'at_0xe88')


def decode_frames(tape, nframes):
    p, prev, frames = SNAPSHOT_SIZE, None, []
    for f in range(nframes):
        fr = {'camera': _unpack(CAMERA, tape[p:p + 28], f'frames[{f}].camera')}
        p += 28
        flag, e70 = struct.unpack_from('<BI', tape, p)
        p += 5
        flight = {TAPNAMES.get('ball_flight.at_0xe70', 'at_0xe70'): e70}
        if flag not in (0, 1):
            flight['_flag'] = flag
        if flag == 1:
            n, e78, e7c, e80, e84, e88 = struct.unpack_from('<6I', tape, p)
            p += 24
            pts = struct.unpack_from('<%di' % (3 * n + 3), tape, p)
            p += 4 * (3 * n + 3)
            flight['path'] = {**{TAPNAMES.get(f'path.{o}', o): v for o, v in zip(PATH_OLD, (e78, e7c, e80, e84, e88))},
                              'points': [list(pts[i:i + 3]) for i in range(0, len(pts), 3)]}
        fr['ball_flight'] = flight
        if f == 0:
            rec = bytearray(tape[p:p + RECORD_SIZE])
            p += RECORD_SIZE
        else:
            k = struct.unpack_from('<I', tape, p)[0]
            p += 4
            if k > RECORD_SIZE // 4:
                _fail(f'frame {f}: {k} changed words')
            rec = bytearray(prev)
            last = -1
            for _ in range(k):
                w, v = struct.unpack_from('<II', tape, p)
                p += 8
                if w <= last or w >= RECORD_SIZE // 4:
                    _fail(f'frame {f}: delta words out of order')
                if struct.unpack_from('<I', rec, 4 * w)[0] == v:
                    _fail(f'frame {f}: delta word {w} does not change')
                last = w
                struct.pack_into('<I', rec, 4 * w, v)
        if len(rec) != RECORD_SIZE:
            _fail(f'frame {f}: truncated')
        fr['record'] = _unpack(RECORD, bytes(rec), f'frames[{f}].record')
        frames.append(fr)
        prev = rec
    if p != len(tape):
        _fail(f'{len(tape) - p} bytes after the last frame')
    return frames


def encode_frames(frames):
    out, prev = bytearray(), None
    for f, fr in enumerate(frames):
        out += _pack(CAMERA, fr['camera'], f'frames[{f}].camera')
        fl = fr['ball_flight']
        path = fl.get('path')
        flag = 1 if path is not None else fl.get('_flag', 0)
        if flag == 1 and path is None:
            _fail(f'frames[{f}]: flag 1 needs a path')
        out += struct.pack('<B', flag) + _pack('I', _get(fl, 'ball_flight', 'at_0xe70', f'frames[{f}].ball_flight'),
                                               f'frames[{f}].ball_flight.at_0xe70')
        if path is not None:
            pts = path['points']
            if not pts or any(not isinstance(q, list) or len(q) != 3 for q in pts):
                _fail(f'frames[{f}]: path points must be [x, y, z] triples, at least one')
            out += _pack([('n', 'I')] + [_n('path', o, 'I') for o in PATH_OLD],
                         dict(path, n=len(pts) - 1), f'frames[{f}].ball_flight.path')
            out += _pack(('list', 3 * len(pts), 'i'), [c for q in pts for c in q], f'frames[{f}].ball_flight.points')
        rec = _pack(RECORD, fr['record'], f'frames[{f}].record')
        if prev is None:
            out += rec
        else:
            ch = [(w, struct.unpack_from('<I', rec, 4 * w)[0]) for w in range(RECORD_SIZE // 4)
                  if rec[4 * w:4 * w + 4] != prev[4 * w:4 * w + 4]]
            out += struct.pack('<I', len(ch)) + b''.join(struct.pack('<II', w, v) for w, v in ch)
        prev = rec
    return bytes(out)


# ---------------------------------------------------------------- tape file

def decode_tape(b):
    _STALE.clear()
    if len(b) < 0x5c or struct.unpack_from('<H', b, 0)[0] != TAPE_VERSION:
        _fail('not a replay tape')
    caption = _dec(('str', 80), b, 2, 'caption')[0]
    nframes, length, ck = struct.unpack_from('<HII', b, 0x52)
    tape = b[0x5c:]
    if len(tape) != length:
        _fail(f'tape length {length} != {len(tape)} bytes stored')
    if checksum(tape) != ck:
        _fail('checksum mismatch')
    if length < SNAPSHOT_SIZE:
        _fail('tape shorter than the snapshot')
    doc = {'caption': caption, 'snapshot': decode_snapshot(tape[:SNAPSHOT_SIZE]),
           'frames': decode_frames(tape, nframes)}
    doc['_frame_count'] = nframes
    doc['_tape_length'] = length
    doc['_checksum'] = ck
    if _STALE:
        doc['_stale_strings'] = dict(_STALE)
    return doc


def encode_tape(doc):
    _STALE.clear()
    _STALE.update(doc.get('_stale_strings', {}))
    frames = doc['frames']
    if not isinstance(frames, list) or len(frames) > 0xffff:
        _fail('frames must be a list of at most 65535')
    tape = encode_snapshot(doc['snapshot']) + encode_frames(frames)
    head = struct.pack('<H', TAPE_VERSION) + _pack(('str', 80), doc['caption'], 'caption')
    return head + struct.pack('<HII', len(frames), len(tape), checksum(tape)) + tape


# ---------------------------------------------------------------- NQ0 container

def decode_nq0(b):
    if len(b) < 2:
        _fail('container too short')
    version, p, entries = struct.unpack_from('<H', b, 0)[0], 2, []
    while p < len(b):
        if p + 6 > len(b):
            _fail('truncated entry header')
        tag, ln = struct.unpack_from('<HI', b, p)
        if tag & 0xc000 != 0x4000:
            _fail(f'entry tag {tag:#x} lacks the 0x4000 mark')
        body = b[p + 6:p + 6 + ln]
        if len(body) != ln:
            _fail('truncated entry')
        entries.append({'id': tag & 0x3fff, 'tape': decode_tape(body)})
        p += 6 + ln
    return {'version': version, 'tapes': entries}


def encode_nq0(doc):
    out = bytearray(_pack('H', doc['version'], 'version'))
    for i, e in enumerate(doc['tapes']):
        if not isinstance(e.get('id'), int) or not 0 <= e['id'] < 0x4000:
            _fail(f'tapes[{i}].id: 0..16383')
        body = encode_tape(e['tape'])
        out += struct.pack('<HI', 0x4000 | e['id'], len(body)) + body
    return bytes(out)


def _is_nq0(name):
    return name.upper().endswith('.NQ0')


def main():
    if len(sys.argv) == 5 and sys.argv[1] == 'decode':
        with open(sys.argv[3], 'rb') as fh:
            b = fh.read()
        doc = decode_nq0(b) if _is_nq0(sys.argv[2]) else decode_tape(b)
        with open(sys.argv[4], 'w') as fh:
            json.dump(doc, fh, indent=1)
    elif len(sys.argv) == 6 and sys.argv[1] == 'encode':
        with open(sys.argv[4]) as fh:
            doc = json.load(fh)
        out = encode_nq0(doc) if _is_nq0(sys.argv[2]) else encode_tape(doc)
        with open(sys.argv[5], 'wb') as fh:
            fh.write(out)
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
