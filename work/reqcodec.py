#!/usr/bin/env python3
"""MENU.REQ / DIAL.REQ (shell UI layouts) codec. Field meanings from the BBShell GUI library (the same code is linked
into EZShell, LineUp and Upstats); spec: work/spec/REQ_FORMAT.md. Container and round trip from the req GLM lane
(re/targets/req/lanes/code); the header lists and every gadget field were remapped by Claude from the loaders.

usage: reqcodec.py decode in.REQ out.json
       reqcodec.py encode in.REQ edited.json out.REQ     (in.REQ is not read; kept for the voldat-style contract)

JSON: {"requesters": [{"index", "id", "x", "y", "w", "h", "style", "styleFlags", "labels": [text], "captions": [text],
"rects": [rect], "gadgets": [gadget]}], "_tail"}
  text   {"x", "y", "color", "font", "text"}               Dreqtext
  rect   {"x", "y", "w", "h", "bgColor", "color"}          Dreqrect (filled rectangle; colors are palette slots)
  gadget {"type", "class", "id", "x", "y", "w", "h", "flags", "state", "link", ...class fields}
    class 1 edit field     textColor, activeColor, font, maxLength
    class 2 slider         total, visible, knobW, knobH
    class 4 labelled       font, textColor, activeColor, label
    class 8 cell grid      font, bgColor, selectColor, cellW, cellH
Keys starting with "_" are derived and recomputed. Lists may grow or shrink; the encoder writes requesters back to back
and rebuilds the IDX table.
"""
import json
import struct
import sys

TEXT = '<2h2H'                       # x, y, color, font (+ NUL-terminated text)
RECT = '<4h2H'                       # x, y, w, h, bgColor, color
COMMON = '<BBH4h3H'                  # type, class, id, x, y, w, h, flags, state, link
CLASS = {                            # class -> (struct of the extra words, their names)
    1: ('<4H', ('textColor', 'activeColor', 'font', 'maxLength')),
    2: ('<4H', ('total', 'visible', 'knobW', 'knobH')),
    4: ('<3H', ('font', 'textColor', 'activeColor')),
    8: ('<5H', ('font', 'bgColor', 'selectColor', 'cellW', 'cellH')),
}
COMMON_KEYS = ('type', 'class', 'id', 'x', 'y', 'w', 'h', 'flags', 'state', 'link')


def _fail(msg):
    raise ValueError(msg)


def _cstr(d, p, end):
    e = d.find(b'\0', p, end)
    if e < 0:
        _fail(f'unterminated string at {p}')
    return d[p:e].decode('latin1'), e + 1


def _texts(d, p, end):
    if p + 2 > end:
        _fail(f'text list count past the header at {p}')
    (n,) = struct.unpack_from('<H', d, p); p += 2
    out = []
    for _ in range(n):
        if p + 8 > end:
            _fail(f'text record past the header at {p}')
        x, y, color, font = struct.unpack_from(TEXT, d, p)
        text, p = _cstr(d, p + 8, end)
        out.append({'x': x, 'y': y, 'color': color, 'font': font, 'text': text})
    return out, p


def decode_header(d, a, end):
    if end - a < 16:
        _fail(f'header too short at {a}')
    rid, x, y, w, h, style, styleFlags = struct.unpack_from('<H4hHI', d, a)
    labels, p = _texts(d, a + 16, end)
    captions, p = _texts(d, p, end)
    if p + 2 > end:
        _fail(f'rect count past the header at {p}')
    (n,) = struct.unpack_from('<H', d, p); p += 2
    if p + 12 * n != end:
        _fail(f'header at {a}: {n} rects do not fill the remaining {end - p} bytes')
    rects = []
    for k in range(n):
        rx, ry, rw, rh, bg, color = struct.unpack_from(RECT, d, p + 12 * k)
        rects.append({'x': rx, 'y': ry, 'w': rw, 'h': rh, 'bgColor': bg, 'color': color})
    return {'id': rid, 'x': x, 'y': y, 'w': w, 'h': h, 'style': style, 'styleFlags': styleFlags,
            'labels': labels, 'captions': captions, 'rects': rects}


def decode_gadgets(d, a, end):
    if end - a < 2:
        _fail('GAD section too short')
    (count,) = struct.unpack_from('<H', d, a)
    p = a + 2
    out = []
    for _ in range(count):
        if p + 18 > end:
            _fail(f'gadget past its section at {p}')
        g = dict(zip(COMMON_KEYS, struct.unpack_from(COMMON, d, p)))
        if g['class'] not in CLASS:
            _fail(f'unknown gadget class {g["class"]} at {p}')
        fmt, names = CLASS[g['class']]
        q = p + 18 + struct.calcsize(fmt)
        if q > end:
            _fail(f'gadget fields past its section at {p}')
        g.update(zip(names, struct.unpack_from(fmt, d, p + 18)))
        if g['class'] == 4:
            g['label'], q = _cstr(d, q, end)
        out.append(g)
        p = q
    if p != end:
        _fail(f'GAD section has {end - p} bytes after {count} gadgets')
    return out


def decode(d):
    if len(d) < 12 or d[:4] != b'IDX:':
        _fail('no IDX header')
    idxLen, n = struct.unpack_from('<II', d, 4)
    if idxLen != 4 + 4 * n or 12 + 4 * n > len(d):
        _fail('bad IDX length')
    idx = struct.unpack_from('<%dI' % n, d, 12)
    a = 12 + 4 * n
    reqs, tops = [], []
    while a + 8 <= len(d) and d[a:a + 4] == b'REQ:':
        (L,) = struct.unpack_from('<I', d, a + 4)
        if not L >> 31:
            _fail(f'requester at {a} is not a container')
        end = a + 8 + (L & 0x7fffffff)
        if end > len(d) or d[a + 8:a + 12] != b'REQ:':
            _fail(f'bad requester at {a}')
        (hlen,) = struct.unpack_from('<I', d, a + 12)
        g = a + 16 + hlen
        if g + 8 > end or d[g:g + 4] != b'GAD:':
            _fail(f'bad requester header at {a}')
        (glen,) = struct.unpack_from('<I', d, g + 4)
        if g + 8 + glen != end:
            _fail(f'GAD length mismatch at {a}')
        r = {'index': len(reqs)}
        r.update(decode_header(d, a + 16, g))
        r['gadgets'] = decode_gadgets(d, g + 8, end)
        reqs.append(r)
        tops.append(a)
        a = end
    if not reqs:
        _fail('no requesters')
    if list(idx) != [tops[0]] + [t + 8 for t in tops]:
        _fail('IDX table does not match the requesters')
    return {'requesters': reqs, '_tail': d[a:].decode('latin1')}


def _enc_texts(items):
    out = struct.pack('<H', len(items))
    for t in items:
        out += struct.pack(TEXT, t['x'], t['y'], t['color'], t['font']) + t.get('text', '').encode('latin1') + b'\0'
    return out


def encode_header(r):
    out = struct.pack('<H4hHI', r['id'], r['x'], r['y'], r['w'], r['h'], r['style'], r['styleFlags'])
    out += _enc_texts(r.get('labels', [])) + _enc_texts(r.get('captions', []))
    rects = r.get('rects', [])
    out += struct.pack('<H', len(rects))
    for q in rects:
        out += struct.pack(RECT, q['x'], q['y'], q['w'], q['h'], q['bgColor'], q['color'])
    return out


def encode_gadget(g):
    cl = g['class']
    if cl not in CLASS:
        _fail(f'unknown gadget class {cl}')
    fmt, names = CLASS[cl]
    out = struct.pack(COMMON, *(g[k] for k in COMMON_KEYS)) + struct.pack(fmt, *(g[k] for k in names))
    if cl == 4:
        out += g.get('label', '').encode('latin1') + b'\0'
    return out


def encode(doc):
    blocks = []
    for r in doc['requesters']:
        gad = struct.pack('<H', len(r['gadgets'])) + b''.join(encode_gadget(g) for g in r['gadgets'])
        hdr = encode_header(r)
        body = b'REQ:' + struct.pack('<I', len(hdr)) + hdr + b'GAD:' + struct.pack('<I', len(gad)) + gad
        blocks.append(b'REQ:' + struct.pack('<I', 0x80000000 | len(body)) + body)
    n = len(blocks) + 1
    a = 12 + 4 * n
    tops = []
    for b in blocks:
        tops.append(a)
        a += len(b)
    idx = [tops[0]] + [t + 8 for t in tops]
    return (b'IDX:' + struct.pack('<II', 4 + 4 * n, n) + struct.pack('<%dI' % n, *idx) + b''.join(blocks)
            + doc.get('_tail', '').encode('latin1'))


def main():
    mode = sys.argv[1]
    if mode == 'decode':
        with open(sys.argv[2], 'rb') as fh:
            doc = decode(fh.read())
        with open(sys.argv[3], 'w') as fh:
            json.dump(doc, fh, indent=1)
    elif mode == 'encode':
        with open(sys.argv[3]) as fh:
            doc = json.load(fh)
        with open(sys.argv[4], 'wb') as fh:
            fh.write(encode(doc))
    else:
        _fail(f'unknown mode {mode}')


if __name__ == '__main__':
    main()
