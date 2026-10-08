#!/usr/bin/env python3
"""HMI HMP music (the 13 HMIMIDIP chunks of SIM.DAT: org1.hmi, chgorg1-3.hmi, chgtpt1-4.hmi, 4 unnamed).
Spec: spec/HMP_FORMAT.md. The Win95 build never plays them: BBSIM FUN_6806ed8b, the call that would start one
(FUN_6803924e, charge cues 3 and up), is an empty function. Cues 0-2 play WAV sounds instead.

usage: hmp.py decode IN.hmi OUT.json        events as hex, header tables by name
       hmp.py encode IN.json OUT.hmi
       hmp.py tomid IN.hmi OUT.mid          standard MIDI file, type 1, one MTrk per HMP track
       hmp.py frommid IN.mid OUT.hmi [--template ORIG.hmi]   header tables and pad from the template
       hmp.py verify FILE...                byte-exact decode/encode and hmi -> mid -> hmi round trips
Chunks come out of SIM.DAT with chunkdat.py unpack and go back with chunkdat.py pack.
"""
import json, struct, sys


class HmpError(ValueError):
    pass


def _fail(msg):
    raise HmpError(msg)


MAGIC = b'HMIMIDIP'
V2 = b'013195'
DATA = {b'': 0x308, V2: 0x388}             # first track header (v1, v2)
NCHAN, NTRK, NDEV = 16, 32, 5


# ---------------------------------------------------------------- variable-length numbers

def hmp_vlq_read(b, o):
    """HMP delta: 7 bits per byte, least significant first, the last byte has bit 7 set."""
    v = s = 0
    while True:
        if o >= len(b):
            _fail('delta runs past the track')
        c = b[o]; o += 1
        v |= (c & 0x7f) << s; s += 7
        if c & 0x80:
            return v, o


def hmp_vlq(v):
    out = bytearray()
    while v >= 0x80:
        out.append(v & 0x7f); v >>= 7
    out.append(v | 0x80)
    return bytes(out)


def smf_vlq_read(b, o):
    v = 0
    while True:
        if o >= len(b):
            _fail('number runs past the track')
        c = b[o]; o += 1
        v = v << 7 | c & 0x7f
        if not c & 0x80:
            return v, o


def smf_vlq(v):
    out = [v & 0x7f]
    v >>= 7
    while v:
        out.append(v & 0x7f | 0x80); v >>= 7
    return bytes(reversed(out))


# ---------------------------------------------------------------- MIDI events (shared by HMP and SMF tracks)

def read_event(b, o, status, vlq_read):
    """One event after its delta: returns (event bytes with explicit status, new offset, running status).
    Meta and sysex lengths are standard MIDI numbers in both formats."""
    c = b[o]
    if c == 0xff:
        n, p = vlq_read(b, o + 2)
        if p + n > len(b):
            _fail(f'meta event at {o} runs past the track')
        return b[o:p + n], p + n, status
    if c in (0xf0, 0xf7):
        n, p = vlq_read(b, o + 1)
        if p + n > len(b):
            _fail(f'sysex at {o} runs past the track')
        return b[o:p + n], p + n, None
    if c & 0x80:
        status, o = c, o + 1
    elif status is None:
        _fail(f'data byte {c:#x} at {o} with no running status')
    n = 1 if status & 0xf0 in (0xc0, 0xd0) else 2
    if o + n > len(b) or any(x & 0x80 for x in b[o:o + n]):
        _fail(f'bad data bytes for status {status:#x} at {o}')
    return bytes([status]) + b[o:o + n], o + n, status


def _ev_bytes(ev, what):
    try:
        b = bytes.fromhex(ev)
    except (TypeError, ValueError):
        _fail(f'{what}: event must be hex')
    if not b or not b[0] & 0x80:
        _fail(f'{what}: event must start with a status byte')
    try:
        whole = read_event(b, 0, None, smf_vlq_read)[0]
    except (HmpError, IndexError):
        whole = None
    if whole != b:
        _fail(f'{what}: {ev!r} is not exactly one MIDI event')
    return b


# ---------------------------------------------------------------- HMP file

def decode(b):
    if b[:8] != MAGIC:
        _fail('not an HMP file (no HMIMIDIP)')
    ver = b[8:14] if b[8:14] == V2 else b''
    if any(b[8 + len(ver):0x20]):
        _fail('unexpected bytes in the signature field')
    flen, = struct.unpack_from('<I', b, 0x20)
    ntrk, div, rate, secs = struct.unpack_from('<4I', b, 0x30)
    d = {'version': ver.decode(), 'division': div, 'tick_rate': rate, 'seconds': secs,
         'at_0x24': b[0x24:0x30].hex(),
         'channel_priority': list(struct.unpack_from(f'<{NCHAN}I', b, 0x40)),
         'track_devices': [list(struct.unpack_from(f'<{NDEV}I', b, 0x80 + 4 * NDEV * t)) for t in range(NTRK)],
         'header_tail': b[0x300:DATA[ver]].hex()}
    o, tracks = DATA[ver], []
    for t in range(ntrk):
        idx, n, chan = struct.unpack_from('<3I', b, o)
        if n < 12 or o + n > flen:
            _fail(f'track {t}: length {n} at {o} overruns the file')
        body, p, st, evs = b[o + 12:o + n], 0, None, []
        while p < len(body):
            dt, q = hmp_vlq_read(body, p)
            if body[p:q] != hmp_vlq(dt):
                _fail(f'track {t}: non-canonical delta at {p}')
            ev, p, st = read_event(body, q, st, smf_vlq_read)
            evs.append([dt, ev.hex(' ')])
        if _encode_track_body(evs, t) != body:
            _fail(f'track {t}: uses running status or non-canonical meta lengths (not seen in the game data)')
        tracks.append({'index': idx, 'channel': chan, 'events': evs})
        o += n
    if o != flen:
        _fail(f'tracks end at {o}, header says {flen}')
    d['tracks'] = tracks
    d['pad'] = b[flen:].hex()
    return d


def _encode_track_body(evs, t):
    out = bytearray()
    for i, (dt, ev) in enumerate(evs):
        if not isinstance(dt, int) or dt < 0:
            _fail(f'track {t} event {i}: delta must be a non-negative integer')
        out += hmp_vlq(dt) + _ev_bytes(ev, f'track {t} event {i}')
    return bytes(out)


def encode(d):
    ver = d['version'].encode()
    if ver not in DATA:
        _fail('version must be "" or "013195"')
    head = bytearray(DATA[ver])
    head[:8] = MAGIC
    head[8:8 + len(ver)] = ver
    head[0x24:0x30] = bytes.fromhex(d['at_0x24'])
    struct.pack_into('<4I', head, 0x30, len(d['tracks']), d['division'], d['tick_rate'], d['seconds'])
    if len(d['channel_priority']) != NCHAN or len(d['track_devices']) != NTRK:
        _fail(f'channel_priority holds {NCHAN} words and track_devices {NTRK} rows')
    struct.pack_into(f'<{NCHAN}I', head, 0x40, *d['channel_priority'])
    for t, row in enumerate(d['track_devices']):
        if len(row) != NDEV:
            _fail(f'track_devices row {t} holds {NDEV} words')
        struct.pack_into(f'<{NDEV}I', head, 0x80 + 4 * NDEV * t, *row)
    tail = bytes.fromhex(d['header_tail'])
    if len(tail) != DATA[ver] - 0x300:
        _fail(f'header_tail must be {DATA[ver] - 0x300} bytes')
    head[0x300:] = tail
    body = bytearray()
    for t, tr in enumerate(d['tracks']):
        tb = _encode_track_body(tr['events'], t)
        body += struct.pack('<3I', tr['index'], 12 + len(tb), tr['channel']) + tb
    out = head + body
    struct.pack_into('<I', out, 0x20, len(out))
    return bytes(out) + bytes.fromhex(d.get('pad', ''))


# ---------------------------------------------------------------- standard MIDI

def to_mid(d):
    """Type 1 SMF; HMP track n -> MTrk n. HMP ticks run at tick_rate per second, so a quarter of `division` ticks
    lasts division / tick_rate seconds (192 / 120 = 1.6 s); track 0 gets that tempo."""
    trks = []
    for t, tr in enumerate(d['tracks']):
        out = bytearray()
        if t == 0:
            out += b'\x00\xff\x51\x03' + struct.pack('>I', round(d['division'] * 1_000_000 / d['tick_rate']))[1:]
        for dt, ev in tr['events']:
            out += smf_vlq(dt) + bytes.fromhex(ev)
        trks.append(b'MTrk' + struct.pack('>I', len(out)) + out)
    return b'MThd' + struct.pack('>IHHH', 6, 1, len(trks), d['division']) + b''.join(trks)


def from_mid(b, template=None):
    if b[:4] != b'MThd':
        _fail('not a standard MIDI file')
    hl, fmt, ntrk, div = struct.unpack_from('>IHHH', b, 4)
    if div & 0x8000:
        _fail('SMPTE time division is not supported')
    o, tracks, tempo, total = 8 + hl, [], 500_000, 0
    for t in range(ntrk):
        if b[o:o + 4] != b'MTrk':
            _fail(f'MTrk {t} missing')
        n, = struct.unpack_from('>I', b, o + 4)
        body, p, st, evs, tick, chan = b[o + 8:o + 8 + n], 0, None, [], 0, None
        while p < len(body):
            dt, p = smf_vlq_read(body, p)
            ev, p, st = read_event(body, p, st, smf_vlq_read)
            tick += dt
            if t == 0 and ev[:2] == b'\xff\x51' and not evs:
                tempo = int.from_bytes(ev[3:6], 'big')
                continue                                    # the HMP header carries the tempo
            if chan is None and ev[0] < 0xf0:
                chan = ev[0] & 0x0f
            evs.append([dt, ev.hex(' ')])
        tracks.append({'index': t, 'channel': 9 if chan is None else chan, 'events': evs})
        total = max(total, tick)
        o += 8 + n
    d = dict(template) if template else {
        'version': '013195', 'at_0x24': '00' * 12, 'channel_priority': [0] + [9] * 9 + [0] * 6,
        'track_devices': [[0] * NDEV for _ in range(NTRK)], 'header_tail': '00' * 0x88, 'pad': ''}
    if template and len(template['tracks']) == len(tracks):   # keep the template's track numbers and channels
        for tr, old in zip(tracks, template['tracks']):
            tr.update(index=old['index'], channel=old['channel'])
    rate = round(div * 1_000_000 / tempo)                  # later tempo changes are not carried (HMP has none)
    d.update(division=div, tick_rate=rate, tracks=tracks)
    if not template:
        d['seconds'] = total // rate
    return d


# ---------------------------------------------------------------- main

def main():
    a = sys.argv[1:]
    try:
        if a[:1] == ['decode'] and len(a) == 3:
            json.dump(decode(open(a[1], 'rb').read()), open(a[2], 'w'), indent=1)
        elif a[:1] == ['encode'] and len(a) == 3:
            open(a[2], 'wb').write(encode(json.load(open(a[1]))))
        elif a[:1] == ['tomid'] and len(a) == 3:
            open(a[2], 'wb').write(to_mid(decode(open(a[1], 'rb').read())))
        elif a[:1] == ['frommid'] and len(a) in (3, 5) and (len(a) == 3 or a[3] == '--template'):
            tpl = decode(open(a[4], 'rb').read()) if len(a) == 5 else None
            open(a[2], 'wb').write(encode(from_mid(open(a[1], 'rb').read(), tpl)))
        elif a[:1] == ['verify'] and len(a) > 1:
            bad = 0
            for f in a[1:]:
                b = open(f, 'rb').read()
                try:
                    d = decode(b)
                    ok1 = encode(json.loads(json.dumps(d))) == b
                    ok2 = encode(from_mid(to_mid(d), d)) == b
                except HmpError as e:
                    ok1 = ok2 = False
                    print(f, 'ERROR', e)
                bad += not (ok1 and ok2)
                print(f, 'json', 'OK' if ok1 else 'MISMATCH', 'mid', 'OK' if ok2 else 'MISMATCH')
            sys.exit(1 if bad else 0)
        else:
            sys.exit(__doc__)
    except HmpError as e:
        sys.exit(f'hmp.py: {e}')


if __name__ == '__main__':
    main()
