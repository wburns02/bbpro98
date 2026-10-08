#!/usr/bin/env python3
"""Build a widened SHELL.VOL from the pristine one.
usage: build_wide_vol.py PRISTINE_VOL OUT_VOL [--namew 0x60] [--colw 0x26] [--extra 4] [--labels A,B,C,D]
Edits the League Statistics requester of MENU.REQ (id 15, IDX slot 13): narrows the Name column and the 8 stat
columns, and appends EXTRA body + header columns. The edit goes through work/reqcodec.py (lengths, counts and the
IDX table rebuilt) and work/volcodec.py (directory offsets and the entry's stored size rebuilt).

The first version of this script patched bytes in place, called the entry DIAL.REQ (it read each directory record's
offset as the next name's), and moved the biggest requester to the end of the file to stay under a "~0xfe9x block
start limit". That limit was the VOL entry header's size field, which it left at the pristine value: the game's
member stream stops at that size, so any requester whose bytes ran past it failed to load. With the size rebuilt,
nothing has to move."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import liveguard
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import argparse, json, tempfile
import reqcodec, volcodec

ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('dst')
num = lambda s: int(s, 0)
ap.add_argument('--namew', type=num, default=0x60); ap.add_argument('--colw', type=num, default=0x26)
ap.add_argument('--extra', type=int, default=4); ap.add_argument('--bodybase', type=num, default=0x1e)
ap.add_argument('--hdrbase', type=num, default=0x28); ap.add_argument('--labels', default='EX1,EX2,EX3,EX4,EX5,EX6')
ap.add_argument('--last', type=int, help='ignored (the old block-move workaround)')
a = ap.parse_args()

with tempfile.TemporaryDirectory(prefix='widevol') as td:
    volcodec.unpack(a.src, td)
    man = json.load(open(f'{td}/manifest.json'))
    ent = [e for e in man['entries'] if e['name'] == 'MENU.REQ']
    assert len(ent) == 1
    path = f'{td}/{ent[0]["file"]}'
    doc = reqcodec.decode(open(path, 'rb').read())
    r = doc['requesters'][12]
    assert r['id'] == 15 and len(r['gadgets']) == 29, 'not the pristine League Statistics requester'
    gs = r['gadgets']

    def one(**kw):
        hit = [g for g in gs if all(g[k] == v for k, v in kw.items())]
        assert len(hit) == 1, kw
        return hit[0]

    g = one(type=3, **{'class': 8}, id=0x0a, x=0x30, y=0x6e); g['w'] = g['cellW'] = a.namew     # Name column body
    one(type=0x12, **{'class': 4}, id=0x14, x=0x30, y=0x60)['w'] = a.namew                       # Name header
    x0 = 0x30 + a.namew
    for n in range(8):
        x = x0 + n * a.colw
        g = one(type=4, **{'class': 8}, id=0x0b + n, x=0xd7 + 49 * n, y=0x6e, w=0x32)
        g['x'], g['w'], g['cellW'] = x, a.colw, a.colw
        g = one(type=0x13, **{'class': 4}, id=0x15 + n, x=0xd7 + 49 * n, y=0x60, w=0x32)
        g['x'], g['w'] = x, a.colw
    E, labels = a.extra, a.labels.split(',')
    NB = [a.bodybase + k for k in range(E)]; NH = [a.hdrbase + k for k in range(E)]
    # ids must be new among the stat column gadgets; wide5 (--bodybase 0x30 --hdrbase 0x1d, what patch_ext.py expects)
    # reuses 0x1d, also the id of the trailing type-0 gadget, and works
    cols = {g['id'] for g in gs if (g['type'], g['class']) in ((4, 8), (0x13, 4))}
    assert not cols & set(NB + NH), 'new gadget ids collide'
    xs = [x0 + (8 + k) * a.colw for k in range(E)]
    assert xs[-1] + a.colw <= 0x267 + 0x0d, 'overflow panel'
    body = [dict(type=4, **{'class': 8}, id=NB[k], x=xs[k], y=0x6e, w=a.colw, h=0x14a, flags=0x40, state=4,
                 link=0x12 if k == 0 else NB[k - 1], font=4, bgColor=1, selectColor=0xc, cellW=a.colw, cellH=0xb)
            for k in range(E)]
    head = [dict(type=0x13, **{'class': 4}, id=NH[k], x=xs[k], y=0x60, w=a.colw, h=0xf, flags=0x50, state=4,
                 link=NH[k + 1] if k + 1 < E else 0x13, font=0, textColor=1, activeColor=2,
                 label=labels[k].ljust(6)[:6])
            for k in range(E)]
    g = one(type=0x13, **{'class': 4}, id=0x1c); assert g['link'] == 0x13; g['link'] = NH[0]   # header chain
    pb = gs.index(one(type=0x0d, **{'class': 4}, id=4))      # status bar: bodies go before it
    ph = gs.index(one(type=9, **{'class': 4}, id=5))         # panel: headers go before it
    assert pb < ph
    gs[ph:ph] = head; gs[pb:pb] = body
    new = reqcodec.encode(doc)
    assert reqcodec.decode(new)['requesters'][12]['gadgets'] == gs
    open(path, 'wb').write(new)
    volcodec.pack(td, a.dst)

print('MENU.REQ requester 15 now has', len(gs), 'gadgets; wrote', a.dst)
