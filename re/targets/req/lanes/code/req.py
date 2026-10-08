#!/usr/bin/env python3
"""Codec for FPS Baseball Pro '98 shell UI layout files MENU.REQ / DIAL.REQ.

A file is a directory of requesters (screens and dialogs).  Each requester is a
"REQ:" container holding a header (the requester itself: id, position, size,
styles, title captions and decorative frame indicators) and a "GAD:" section
holding its gadgets (buttons, list columns, scroll bars, ...).

File layout (evidence in FORMAT.md):
  "IDX:" u32 (4 + 4n) | u32 n | u32 idx[n]
      idx[0] = byte offset of the first requester container,
      idx[k] = offset of requester k-1 + 8 (points at the inner "REQ:" tag).
      n - 1 requesters follow back to back, then the tail bytes (one NUL in the
      shipped files).
  Requester: "REQ:" u32 (0x80000000 | bodyLen) containing exactly two sections:
    "REQ:" u32 hlen - the header, then "GAD:" u32 glen - the gadget section.
  Header:
    u16 id                     requester number (sequential in the shipped files)
    s16 x, y, w, h             position/size in 640x480 screen pixels
    u16 boxStyle               0x0a (dialog) or 0x0f (full screen / border kind)
    u32 titleFlags             0x40000 = draw title, +8 = draw dialog frame
    u16 spare                  always 0 in the shipped files
    u16 captionCount           number of title captions (0..5)
    captions, one per count:
        s16 textX, textY       position inside the requester
        u16 titleClass         0 = menu-screen title, 1 = dialog title
        u16 titleFont          0 = small, 5 = large title font
        char text[] + NUL      the caption text
    frame indicators (DIAL panels draw lines/arrows from these):
        repeating 12 bytes: u16 entry (shape kind), s16 x, y, w, h, u16 flags
        followed by a u16 terminator (0x0b when indicators exist, else 0).
  Gadget section: u16 count + count records:
        u8 type   control kind (button, column body, column header, ...)
        u8 class  record class: 4 = labelled, 1/2 = list/link, 8 = list box
        u16 id    gadget id (unique per requester; the game uses it for hit
                  tests and chain links)
        s16 x, y, w, h    position/size relative to the requester
        then by class:
        class 4: 12 bytes: u16 hitFlags (0x40 = clickable, 0x50/0x60 seen),
                 u16 textFlags (0x24 = text, 4 = no text), u16 linkA (usually 0
                 or a related gadget id), s16 labelY (label y offset),
                 s16 dataB, u16 dataC - then the NUL-terminated label.
        class 1: 14 bytes: u16 hitFlags (0x40/0), u16 argKind (4), u16 focusItem
                 (row/list item id), u16 drawStyle (0x0c), u16 destClass (0x0d),
                 u16 mapsTo (gadget id the click updates), u16 spare (0x20/0x18).
        class 2: 14 bytes: u16 hitFlags (0x42/2 = scroll), u16 argKind (4),
                 u16 linkTo (gadget id at the other end of the scroll bar),
                 s16 scrollPage (0x64 = 100%), u16 drawStyle (0x0a/0x0c),
                 u16 valClass (0x11), u16 mapsTo (linked gadget id).
        class 8: 16 bytes: u16 hitFlags (0x40), u16 argKind (4/0x24), u16 param
                 (row id / first row / column settings), u16 argKind2 (4),
                 u16 rowStep (1), s16 colGap (3/0x0c/2), u16 colWidth (body
                 width or header width), u16 tailKind (0x0b/0x0c/0x0d/0x11).

Decoded JSON: {"requesters": [{"index", "id", "x", "y", "w", "h", "boxStyle",
"titleFlags", "captionCount", "captions": [{"textX", "textY", "titleClass",
"titleFont", "text"}], "frameIndicators": [{"entry", "x", "y", "w", "h",
"flags"}], "gadgets": [{"type", "class", "id", "x", "y", "w", "h", "hitFlags",
...per-class fields..., "label" (class 4 only)}]}], "tailLen"}.
Keys starting with "_" (the derived lengths) are recomputed by the encoder and
are accepted (and ignored) as input, so an edited caption/gadget object may be
copied freely.  The encoder always writes the canonical layout: requesters back
to back, IDX recomputed, the tail bytes kept.
"""
import json
import struct
import sys

FIXED_TAIL = {1: 14, 2: 14, 4: 12, 8: 16}


def _fail(msg):
    raise ValueError(msg)


# ---------------------------------------------------------------- decoding

def _caption(d, p, end):
    if p + 8 > end:
        _fail(f'caption runs past the header at {p}')
    textX, textY, titleClass, titleFont = struct.unpack_from('<2h2H', d, p)
    e = d.find(b'\0', p + 8, end)
    if e < 0:
        _fail(f'caption text unterminated at {p}')
    text = d[p + 8:e].decode('latin1')
    return ({'textX': textX, 'textY': textY, 'titleClass': titleClass,
             'titleFont': titleFont, 'text': text}, e + 1)


def decode_header(d, a, end):
    if end - a < 20:
        _fail(f'header too short at {a}')
    rid, x, y, w, h = struct.unpack_from('<H4h', d, a)
    boxStyle, titleFlags, spare, captionCount = struct.unpack_from('<HIHH', d, a + 10)
    p = a + 20
    caps = []
    for _ in range(captionCount):
        cap, p = _caption(d, p, end)
        caps.append(cap)
    inds = []
    tail = bytes(d[p:end])
    if len(tail) >= 2 and (len(tail) - 2) % 12 == 0:
        n = (len(tail) - 2) // 12
        for k in range(n):
            entry, ex, ey, ew, eh, efl = struct.unpack_from('<H2h3H', tail, 12 * k)
            inds.append({'entry': entry, 'x': ex, 'y': ey, 'w': ew, 'h': eh, 'flags': efl})
        term = struct.unpack_from('<H', tail, 12 * n)[0]
        tail = tail[12 * n + 2:]
        meta = term
    else:
        meta = struct.unpack_from('<H', tail, 0)[0] if len(tail) >= 2 else 0
        tail = tail[2:] if len(tail) >= 2 else b''
    return (rid, x, y, w, h, boxStyle, titleFlags, spare, caps, inds, tail, meta)


def decode_gadgets(d, a, end):
    if end - a < 2:
        _fail('GAD section too short')
    (count,) = struct.unpack_from('<H', d, a)
    p = a + 2
    gad = []
    for _ in range(count):
        if p + 12 > end:
            _fail(f'gadget runs past its section at {p}')
        gtype, gclass = d[p], d[p + 1]
        if gclass not in FIXED_TAIL:
            _fail(f'unknown gadget class {gclass} at {p}')
        gid, x, y, w, h = struct.unpack_from('<H4h', d, p + 2)
        q = p + 12 + FIXED_TAIL[gclass]
        if q > end:
            _fail(f'gadget tail runs past its section at {p}')
        tail = bytes(d[p + 12:q])
        rec = {'type': gtype, 'class': gclass, 'id': gid, 'x': x, 'y': y, 'w': w, 'h': h}
        if gclass == 4:
            e = d.find(b'\0', q, end)
            if e < 0:
                _fail(f'gadget label unterminated at {q}')
            rec['label'] = d[q:e].decode('latin1')
            hf, tf, linkA, labelY, dataB, dataC = struct.unpack_from('<2H2h2H', tail, 0)
            rec.update(hitFlags=hf, textFlags=tf, linkA=linkA, labelY=labelY,
                       dataB=dataB, dataC=dataC)
            q = e + 1
        elif gclass == 1:
            hf, argKind, focusItem, drawStyle, destClass, mapsTo, spare = struct.unpack_from('<7H', tail, 0)
            rec.update(hitFlags=hf, argKind=argKind, focusItem=focusItem,
                       drawStyle=drawStyle, destClass=destClass, mapsTo=mapsTo, spare=spare)
        elif gclass == 2:
            hf, argKind, linkTo, scrollPage, drawStyle, valClass, mapsTo = struct.unpack_from('<7H', tail, 0)
            rec.update(hitFlags=hf, argKind=argKind, linkTo=linkTo, scrollPage=scrollPage,
                       drawStyle=drawStyle, valClass=valClass, mapsTo=mapsTo)
        else:  # class 8
            hf, argKind, param, argKind2, rowStep, colGap, colWidth, tailKind = struct.unpack_from('<8H', tail, 0)
            rec.update(hitFlags=hf, argKind=argKind, param=param, argKind2=argKind2,
                       rowStep=rowStep, colGap=colGap, colWidth=colWidth, tailKind=tailKind)
        gad.append(rec)
        p = q
    if p != end:
        _fail(f'GAD section has {end - p} trailing bytes after {count} gadgets')
    return gad


def decode(d):
    if len(d) < 12 or d[:4] != b'IDX:':
        _fail('no IDX header')
    idxLen, n = struct.unpack_from('<II', d, 4)
    if idxLen != 4 + 4 * n or 12 + 4 * n > len(d):
        _fail('bad IDX length')
    idx = struct.unpack_from('<%dI' % n, d, 12)
    a = 12 + 4 * n
    reqs = []
    tops = []
    while a + 8 <= len(d) and d[a:a + 4] == b'REQ:':
        (L,) = struct.unpack_from('<I', d, a + 4)
        if not L >> 31:
            _fail(f'requester at {a} is not a container')
        L &= 0x7fffffff
        end = a + 8 + L
        if end > len(d) or d[a + 8:a + 12] != b'REQ:':
            _fail(f'bad requester at {a}')
        (hlen,) = struct.unpack_from('<I', d, a + 12)
        g = a + 16 + hlen
        if hlen < 20 or g + 8 > end or d[g:g + 4] != b'GAD:':
            _fail(f'bad requester header at {a}')
        (glen,) = struct.unpack_from('<I', d, g + 4)
        if g + 8 + glen != end:
            _fail(f'GAD length mismatch at {a}')
        rid, x, y, w, h, boxStyle, titleFlags, spare, caps, inds, htail, hterm = decode_header(d, a + 16, g)
        if htail:
            _fail(f'{len(htail)} unparsed header bytes in requester {len(reqs)}')
        gad = decode_gadgets(d, g + 8, end)
        reqs.append({'index': len(reqs), 'id': rid, 'x': x, 'y': y, 'w': w, 'h': h,
                     'boxStyle': boxStyle, 'titleFlags': titleFlags, '_spare': spare,
                     'captionCount': len(caps), 'captions': caps,
                     'frameIndicators': inds, 'frameTerm': hterm, 'gadgets': gad})
        tops.append(a)
        a = end
    if not reqs:
        _fail('no requesters')
    want = [tops[0]] + [t + 8 for t in tops]
    if list(idx) != want:
        _fail('IDX table does not match the requesters')
    return {'requesters': reqs, '_tail': bytes(d[a:]).decode('latin1')}


# ---------------------------------------------------------------- encoding

def encode_caption(cap, out):
    out += struct.pack('<2h2H', cap['textX'], cap['textY'], cap['titleClass'], cap['titleFont'])
    out += cap.get('text', '').encode('latin1') + b'\0'
    return out


def encode_header(r):
    caps = r.get('captions', [])
    out = struct.pack('<H4h', r['id'], r['x'], r['y'], r['w'], r['h'])
    out += struct.pack('<HIHH', r['boxStyle'], r['titleFlags'], r.get('_spare', 0), len(caps))
    for cap in caps:
        out = encode_caption(cap, out)
    inds = r.get('frameIndicators', [])
    for ind in inds:
        out += struct.pack('<H2h3H', ind['entry'], ind['x'], ind['y'], ind['w'], ind['h'], ind['flags'])
    out += struct.pack('<H', r.get('frameTerm', 0x0b if inds else 0))
    return out


def encode_gadget(g, out):
    gclass = g['class']
    if gclass not in FIXED_TAIL:
        _fail(f'unknown gadget class {gclass}')
    out += struct.pack('<BBH4h', g['type'], gclass, g['id'], g['x'], g['y'], g['w'], g['h'])
    if gclass == 4:
        out += struct.pack('<2H2h2H', g['hitFlags'], g['textFlags'], g['linkA'],
                           g['labelY'], g['dataB'], g['dataC'])
        out += g.get('label', '').encode('latin1') + b'\0'
    elif gclass == 1:
        out += struct.pack('<7H', g['hitFlags'], g['argKind'], g['focusItem'],
                           g['drawStyle'], g['destClass'], g['mapsTo'], g['spare'])
    elif gclass == 2:
        out += struct.pack('<7H', g['hitFlags'], g['argKind'], g['linkTo'],
                           g['scrollPage'], g['drawStyle'], g['valClass'], g['mapsTo'])
    else:
        out += struct.pack('<8H', g['hitFlags'], g['argKind'], g['param'], g['argKind2'],
                           g['rowStep'], g['colGap'], g['colWidth'], g['tailKind'])
    return out


def encode(doc, tail):
    blocks = []
    for r in doc['requesters']:
        gad = struct.pack('<H', len(r['gadgets'])) + b''.join(encode_gadget(g, b'') for g in r['gadgets'])
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
    return b'IDX:' + struct.pack('<II', 4 + 4 * n, n) + struct.pack('<%dI' % n, *idx) + b''.join(blocks) + tail


def main():
    mode, inPath = sys.argv[1], sys.argv[2]
    with open(inPath, 'rb') as fh:
        data = fh.read()
    if mode == 'decode':
        doc = decode(data)
        outPath = sys.argv[3]
        with open(outPath, 'w') as fh:
            json.dump(doc, fh)
    elif mode == 'encode':
        with open(sys.argv[3]) as fh:
            doc = json.load(fh)
        out = encode(doc, doc.get('_tail', '').encode('latin1'))
        with open(sys.argv[4], 'wb') as fh:
            fh.write(out)
    else:
        _fail(f'unknown mode {mode}')


if __name__ == '__main__':
    main()
