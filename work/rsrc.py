#!/usr/bin/env python3
"""Win32 resources (.rsrc) of the game's PE files: dialogs, menus, string tables, accelerators, version info, bitmaps,
icons, cursors and raw data, read and written. Claude, 2026-10-07.

usage: rsrc.py unpack FILE.dll OUTDIR       -> OUTDIR/manifest.json (decoded dialogs/menus/strings/accelerators/
                                               version) + OUTDIR/res/* (bitmaps as .bmp, the rest as .bin)
       rsrc.py pack OUTDIR IN.dll OUT.dll   -> IN.dll with its resources rebuilt from OUTDIR
       rsrc.py verify FILE...               -> unpack + pack in memory, byte compare
       rsrc.py list FILE

pack lays the resource section out the way its linker did (build(); MS linker, Borland and IExpress layouts are
kept, see work/spec/RSRC_FORMAT.md), so an unedited unpack/pack gives the input back byte for byte. When the new
section is larger than the old one and only .reloc follows .rsrc (every MS-linked game binary), .reloc is moved up
behind it (both are only reached through the data directory, so nothing else points into them) and SizeOfImage grows;
anything after .reloc (overlay) is kept at the end. The PE checksum is recomputed when the input's was valid.
"""
import json, os, struct, sys

TYPES = {1: 'CURSOR', 2: 'BITMAP', 3: 'ICON', 4: 'MENU', 5: 'DIALOG', 6: 'STRING', 7: 'FONTDIR', 8: 'FONT',
         9: 'ACCELERATOR', 10: 'RCDATA', 11: 'MESSAGETABLE', 12: 'GROUP_CURSOR', 14: 'GROUP_ICON', 16: 'VERSION',
         17: 'DLGINCLUDE', 19: 'PLUGPLAY', 20: 'VXD', 21: 'ANICURSOR', 22: 'ANIICON', 23: 'HTML', 24: 'MANIFEST'}
TYPE_IDS = {v: k for k, v in TYPES.items()}


def _fail(msg):
    raise ValueError(msg)


# ---------------------------------------------------------------- PE headers


class PE:
    def __init__(self, d):
        if d[:2] != b'MZ':
            _fail('not an MZ file')
        self.pe = struct.unpack_from('<I', d, 0x3c)[0]
        if d[self.pe:self.pe + 4] != b'PE\0\0':
            _fail('not a PE file')
        self.nsec, = struct.unpack_from('<H', d, self.pe + 6)
        osz, = struct.unpack_from('<H', d, self.pe + 20)
        self.opt = self.pe + 24
        if struct.unpack_from('<H', d, self.opt)[0] != 0x10b:
            _fail('only PE32 is handled')
        self.salign, self.falign = struct.unpack_from('<II', d, self.opt + 32)
        self.dd = self.opt + 96
        self.sec_off = self.opt + osz
        self.secs = []
        for i in range(self.nsec):
            o = self.sec_off + 40 * i
            vs, va, rs, rp = struct.unpack_from('<IIII', d, o + 8)
            self.secs.append({'hdr': o, 'name': d[o:o + 8], 'vsize': vs, 'va': va, 'rsize': rs, 'rptr': rp})

    def datadir(self, d, i):
        return struct.unpack_from('<II', d, self.dd + 8 * i)

    def section_of(self, rva):
        for s in self.secs:
            if s['va'] <= rva < s['va'] + max(s['vsize'], s['rsize']):
                return s
        _fail(f'rva {rva:#x} in no section')


def _align(n, a):
    return (n + a - 1) // a * a


def pe_checksum(d, cks_off):
    s = 0
    n = len(d)
    buf = d + b'\0' * (n & 1)
    for i in range(0, len(buf), 2):
        if i == cks_off or i == cks_off + 2:
            continue
        s += buf[i] | buf[i + 1] << 8
        s = (s & 0xffff) + (s >> 16)
    s = (s & 0xffff) + (s >> 16)
    return (s + n) & 0xffffffff


# ---------------------------------------------------------------- resource tree


def _ustr(sec, off):
    n, = struct.unpack_from('<H', sec, off)
    return sec[off + 2:off + 2 + 2 * n].decode('utf-16-le')


def read_tree(d):
    """(entries, dirs, layout) of the resource section. entries: [{type, name, lang, codepage, reserved, data}], ids
    are ints, names strs. dirs: header fields (characteristics, timestamp, major, minor) of each directory table keyed
    'root', 'T', 'T/N'."""
    pe = PE(d)
    rva, size = pe.datadir(d, 2)
    if not rva:
        return pe, None, [], {}
    s = pe.section_of(rva)
    if s['va'] != rva:
        _fail('resource directory does not start its section')
    sec = d[s['rptr']:s['rptr'] + s['rsize']]

    def table(off):
        ch, ts, mj, mn, nn, ni = struct.unpack_from('<IIHHHH', sec, off)
        ents = []
        for k in range(nn + ni):
            nid, tgt = struct.unpack_from('<II', sec, off + 16 + 8 * k)
            key = _ustr(sec, nid & 0x7fffffff) if nid & 0x80000000 else nid
            ents.append((key, tgt))
        return [ch, ts, mj, mn], ents

    dirs, entries = {}, []
    hdr, types = table(0)
    dirs['root'] = hdr
    for tkey, tt in types:
        if not tt & 0x80000000:
            _fail('type entry is not a directory')
        hdr, names = table(tt & 0x7fffffff)
        dirs[_k(tkey)] = hdr
        for nkey, nt in names:
            if not nt & 0x80000000:
                _fail('name entry is not a directory')
            hdr, langs = table(nt & 0x7fffffff)
            dirs[f'{_k(tkey)}/{_k(nkey)}'] = hdr
            for lkey, lt in langs:
                if lt & 0x80000000:
                    _fail('language entry is a directory')
                drva, dsz, cp, rsv = struct.unpack_from('<IIII', sec, lt)
                o = drva - s['va']
                entries.append({'type': tkey, 'name': nkey, 'lang': lkey, 'codepage': cp, 'reserved': rsv,
                                'data': sec[o:o + dsz], '_at': o})
    entries.sort(key=lambda e: e['_at'])             # the linker's data order (the .res order), not the tree order
    if entries:
        dirs['_data_at'] = entries[0]['_at']
    for i, e in enumerate(entries):
        end = e['_at'] + len(e['data'])
        if i + 1 == len(entries):
            break                                    # the tail after the last datum is the manifest's pad
        nxt = entries[i + 1]['_at']
        if nxt < end:
            _fail('overlapping resource data')
        if sec[end:nxt] != bytes(_align(end, 4) - end):
            e['after'] = sec[end:nxt]                # filler the packer left (IExpress writes "PADDING")
    for e in entries:
        del e['_at']
    return pe, s, entries, dirs


def _k(key):
    return f'#{key}' if isinstance(key, int) else key


def _unk(s):
    return int(s[1:]) if s.startswith('#') else s


def _sortkey(key):
    """Names first (case-insensitive like the linker, then exact), then ids ascending."""
    return (0, key.upper(), key) if isinstance(key, str) else (1, key, '')


def build(entries, dirs, va):
    """The resource section for the entries, based at rva va. Linker layout: directory tables breadth first (root,
    types, names), the data entries, the name strings, then (16-aligned) the data in the order of `entries` (the
    order of the .res file), each datum 4-aligned; the size is padded to 4."""
    tree = {}
    for e in entries:
        tree.setdefault(e['type'], {}).setdefault(e['name'], {})[e['lang']] = e
    tkeys = sorted(tree, key=_sortkey)

    def tsize(n):
        return 16 + 8 * n

    # directory tables
    off = tsize(len(tkeys))
    type_off, name_off = {}, {}
    for t in tkeys:
        type_off[t] = off
        off += tsize(len(tree[t]))
    for t in tkeys:
        for n in sorted(tree[t], key=_sortkey):
            name_off[(t, n)] = off
            off += tsize(len(tree[t][n]))
    # data entries
    leaf_off = {}
    for t in tkeys:
        for n in sorted(tree[t], key=_sortkey):
            for l in sorted(tree[t][n], key=_sortkey):
                leaf_off[(t, n, l)] = off
                off += 16
    # name strings (types first, then names, each once)
    str_off = {}
    for key in [t for t in tkeys] + [n for t in tkeys for n in sorted(tree[t], key=_sortkey)]:
        if isinstance(key, str) and key not in str_off:
            str_off[key] = off
            off += 2 + 2 * len(key)
    at = dirs.get('_data_at', 0)
    off = at if at >= off and at % 4 == 0 else _align(off, 16)    # the data's start as found (Borland: unaligned)
    data_off = {}
    for e in entries:
        key = (e['type'], e['name'], e['lang'])
        if key in data_off:
            _fail(f'duplicate resource {key}')
        data_off[key] = off
        aft = e.get('after', b'')
        off = off + len(e['data']) + len(aft) if aft and (off + len(e['data']) + len(aft)) % 4 == 0 \
            else _align(off + len(e['data']), 4)
    out = bytearray(off)

    def put_table(at, hdr, keys, targets):
        nn = sum(isinstance(k, str) for k in keys)
        struct.pack_into('<IIHHHH', out, at, *hdr, nn, len(keys) - nn)
        for i, (k, tgt) in enumerate(zip(keys, targets)):
            nid = (0x80000000 | str_off[k]) if isinstance(k, str) else k
            struct.pack_into('<II', out, at + 16 + 8 * i, nid, tgt)

    put_table(0, dirs.get('root', [0, 0, 0, 0]), tkeys, [0x80000000 | type_off[t] for t in tkeys])
    for t in tkeys:
        ns = sorted(tree[t], key=_sortkey)
        put_table(type_off[t], dirs.get(_k(t), [0, 0, 0, 0]), ns, [0x80000000 | name_off[(t, n)] for n in ns])
        for n in ns:
            ls = sorted(tree[t][n], key=_sortkey)
            put_table(name_off[(t, n)], dirs.get(f'{_k(t)}/{_k(n)}', [0, 0, 0, 0]), ls,
                      [leaf_off[(t, n, l)] for l in ls])
            for l in ls:
                e = tree[t][n][l]
                struct.pack_into('<IIII', out, leaf_off[(t, n, l)], va + data_off[(t, n, l)], len(e['data']),
                                 e['codepage'], e['reserved'])
                o = data_off[(t, n, l)] + len(e['data'])
                out[o - len(e['data']):o] = e['data']
                aft = e.get('after', b'')
                if aft and (o + len(aft)) % 4 == 0:
                    out[o:o + len(aft)] = aft
    for k, o in str_off.items():
        struct.pack_into('<H', out, o, len(k))
        out[o + 2:o + 2 + 2 * len(k)] = k.encode('utf-16-le')
    return bytes(out)


def replace_rsrc(d, sec_bytes, pad=b'', vsize_extra=0, dd_extra=0):
    """d with its resource section's contents replaced by sec_bytes (pad = the original's bytes after the tree inside
    the raw size, kept when the new tree is the same length). The section's VirtualSize is len(sec_bytes) +
    vsize_extra and DataDirectory[2].Size len(sec_bytes) + dd_extra (both 0 for the linker; IExpress packages page-
    align the one and leave the other unaligned). The checksum is recomputed when the original's was valid."""
    pe = PE(d)
    rva, _ = pe.datadir(d, 2)
    s = pe.section_of(rva)
    idx = pe.secs.index(s)
    after = pe.secs[idx + 1:]
    out = bytearray(d)
    new_vsize = len(sec_bytes) + vsize_extra
    new_rsize = _align(len(sec_bytes), pe.falign)
    fits = new_rsize <= s['rsize'] and (not after or s['va'] + _align(new_vsize, pe.salign) <= after[0]['va'])
    if not fits and (len(after) > 1 or any(a['name'].rstrip(b'\0') != b'.reloc' for a in after)):
        _fail('growing .rsrc is handled only when it is followed by at most .reloc')
    if fits:
        body = sec_bytes + (pad if len(sec_bytes) + len(pad) == s['rsize'] else bytes(s['rsize'] - len(sec_bytes)))
        out[s['rptr']:s['rptr'] + s['rsize']] = body
        struct.pack_into('<I', out, s['hdr'] + 8, new_vsize)
    else:
        tail_start = s['rptr'] + s['rsize']
        reloc = after[0] if after else None
        rl = d[reloc['rptr']:reloc['rptr'] + reloc['rsize']] if reloc else b''
        overlay_from = (reloc['rptr'] + reloc['rsize']) if reloc else tail_start
        overlay = d[overlay_from:]
        body = sec_bytes + bytes(new_rsize - len(sec_bytes))
        out = bytearray(d[:s['rptr']]) + body
        struct.pack_into('<II', out, s['hdr'] + 8, new_vsize, s['va'])
        struct.pack_into('<I', out, s['hdr'] + 16, new_rsize)
        end_va = s['va'] + _align(new_vsize, pe.salign)
        if reloc:
            new_va = max(reloc['va'], end_va)
            rptr = len(out)
            out += rl
            struct.pack_into('<I', out, reloc['hdr'] + 12, new_va)
            struct.pack_into('<I', out, reloc['hdr'] + 20, rptr)
            rrva, rsz = pe.datadir(d, 5)
            if rrva:
                struct.pack_into('<I', out, pe.dd + 8 * 5, rrva - reloc['va'] + new_va)
            end_va = new_va + _align(max(reloc['vsize'], reloc['rsize']), pe.salign)
        out += overlay
        struct.pack_into('<I', out, pe.opt + 56, max(struct.unpack_from('<I', d, pe.opt + 56)[0], end_va))
    struct.pack_into('<I', out, pe.dd + 8 * 2 + 4, len(sec_bytes) + dd_extra)
    cks = struct.unpack_from('<I', d, pe.opt + 64)[0]
    if cks and cks == pe_checksum(d, pe.opt + 64):
        struct.pack_into('<I', out, pe.opt + 64, 0)
        struct.pack_into('<I', out, pe.opt + 64, pe_checksum(bytes(out), pe.opt + 64))
    return bytes(out)


# ---------------------------------------------------------------- typed resources


class R:
    def __init__(self, b, p=0):
        self.b, self.p = b, p

    def u16(self):
        v, = struct.unpack_from('<H', self.b, self.p); self.p += 2; return v

    def s16(self):
        v, = struct.unpack_from('<h', self.b, self.p); self.p += 2; return v

    def u32(self):
        v, = struct.unpack_from('<I', self.b, self.p); self.p += 4; return v

    def wz(self):
        e = self.p
        while self.b[e:e + 2] != b'\0\0':
            e += 2
            if e >= len(self.b):
                _fail('unterminated string')
        s = self.b[self.p:e].decode('utf-16-le'); self.p = e + 2; return s

    def sz_or_ord(self):
        if self.b[self.p:self.p + 2] == b'\xff\xff':
            self.p += 2
            return self.u16()
        return self.wz()

    def align4(self):
        self.p = _align(self.p, 4)


class W:
    def __init__(self):
        self.b = bytearray()

    def u16(self, v): self.b += struct.pack('<H', v & 0xffff)

    def s16(self, v): self.b += struct.pack('<h', v)

    def u32(self, v): self.b += struct.pack('<I', v & 0xffffffff)

    def wz(self, s): self.b += s.encode('utf-16-le') + b'\0\0'

    def sz_or_ord(self, v):
        if isinstance(v, int):
            self.u16(0xffff); self.u16(v)
        else:
            self.wz(v)

    def align4(self):
        self.b += bytes(_align(len(self.b), 4) - len(self.b))


CLASSES = {0x80: 'BUTTON', 0x81: 'EDIT', 0x82: 'STATIC', 0x83: 'LISTBOX', 0x84: 'SCROLLBAR', 0x85: 'COMBOBOX'}
CLASS_IDS = {v: k for k, v in CLASSES.items()}
DS_SETFONT = 0x40


def dec_dialog(b):
    r = R(b)
    ex = b[0:4] == b'\x01\x00\xff\xff'
    dl = {'ex': ex}
    if ex:
        r.p = 4
        dl['help_id'] = r.u32(); dl['exstyle'] = r.u32(); dl['style'] = r.u32()
    else:
        dl['style'] = r.u32(); dl['exstyle'] = r.u32()
    n = r.u16()
    dl['x'], dl['y'], dl['cx'], dl['cy'] = r.s16(), r.s16(), r.s16(), r.s16()
    dl['menu'] = r.sz_or_ord(); dl['class'] = r.sz_or_ord(); dl['title'] = r.wz()
    if dl['style'] & DS_SETFONT:
        dl['font_size'] = r.u16()
        if ex:
            dl['font_weight'] = r.u16(); dl['font_italic'] = b[r.p]; dl['font_charset'] = b[r.p + 1]; r.p += 2
        dl['font'] = r.wz()
    items = []
    for _ in range(n):
        r.align4()
        it = {}
        if ex:
            it['help_id'] = r.u32(); it['exstyle'] = r.u32(); it['style'] = r.u32()
        else:
            it['style'] = r.u32(); it['exstyle'] = r.u32()
        it['x'], it['y'], it['cx'], it['cy'] = r.s16(), r.s16(), r.s16(), r.s16()
        it['id'] = r.u32() if ex else r.u16()
        c = r.sz_or_ord()
        it['class'] = CLASSES.get(c, c) if isinstance(c, int) else c
        if isinstance(c, int) and c not in CLASSES:
            it['class'] = c
        it['text'] = r.sz_or_ord()
        nx = r.u16()
        if nx:
            it['extra'] = b[r.p:r.p + nx].hex(); r.p += nx
        items.append(it)
    dl['items'] = items
    if r.p < len(b):
        dl['_tail'] = b[r.p:].hex()
    return dl


def enc_dialog(dl):
    w = W()
    ex = dl['ex']
    if ex:
        w.u16(1); w.u16(0xffff); w.u32(dl['help_id']); w.u32(dl['exstyle']); w.u32(dl['style'])
    else:
        w.u32(dl['style']); w.u32(dl['exstyle'])
    w.u16(len(dl['items']))
    for k in ('x', 'y', 'cx', 'cy'):
        w.s16(dl[k])
    w.sz_or_ord(dl['menu']); w.sz_or_ord(dl['class']); w.wz(dl['title'])
    if dl['style'] & DS_SETFONT:
        w.u16(dl['font_size'])
        if ex:
            w.u16(dl['font_weight']); w.b += bytes([dl['font_italic'], dl['font_charset']])
        w.wz(dl['font'])
    for it in dl['items']:
        w.align4()
        if ex:
            w.u32(it['help_id']); w.u32(it['exstyle']); w.u32(it['style'])
        else:
            w.u32(it['style']); w.u32(it['exstyle'])
        for k in ('x', 'y', 'cx', 'cy'):
            w.s16(it[k])
        if ex:
            w.u32(it['id'])
        else:
            w.u16(it['id'])
        c = it['class']
        w.sz_or_ord(CLASS_IDS[c] if c in CLASS_IDS else c)
        w.sz_or_ord(it['text'])
        x = bytes.fromhex(it.get('extra', ''))
        w.u16(len(x)); w.b += x
    w.b += bytes.fromhex(dl.get('_tail', ''))
    return bytes(w.b)


MF_POPUP, MF_END = 0x10, 0x80


def dec_menu(b):
    r = R(b)
    ver, hsz = r.u16(), r.u16()
    if ver == 1:
        r.p += hsz
        return {'ex': True, 'help_id': struct.unpack_from('<I', b, 4)[0] if hsz >= 4 else None,
                'header': b[4:4 + hsz].hex(), 'items': _menuex_items(r), **_tail(r, b)}
    if ver != 0:
        _fail(f'menu version {ver}')
    r.p += hsz
    m = {'ex': False, 'header_extra': b[4:4 + hsz].hex(), 'items': _menu_items(r)}
    m.update(_tail(r, b))
    return m


def _tail(r, b):
    return {'_tail': b[r.p:].hex()} if r.p < len(b) else {}


def _menu_items(r):
    out = []
    while True:
        fl = r.u16()
        it = {'flags': fl & ~MF_END}
        if fl & MF_POPUP:
            it['text'] = r.wz()
            it['items'] = _menu_items(r)
        else:
            it['id'] = r.u16()
            it['text'] = r.wz()
        out.append(it)
        if fl & MF_END:
            return out


def _enc_menu_items(w, items):
    for i, it in enumerate(items):
        fl = it['flags'] | (MF_END if i == len(items) - 1 else 0)
        w.u16(fl)
        if fl & MF_POPUP:
            w.wz(it['text'])
            _enc_menu_items(w, it['items'])
        else:
            w.u16(it['id']); w.wz(it['text'])


def _menuex_items(r):
    out = []
    while True:
        it = {'type': r.u32(), 'state': r.u32(), 'id': r.u32()}
        res = r.u16()
        it['text'] = r.wz()
        r.align4()
        if res & 1:
            it['help_id'] = r.u32()
            it['items'] = _menuex_items(r)
        it['flags'] = res & ~0x80
        out.append(it)
        if res & 0x80:
            return out


def _enc_menuex_items(w, items):
    for i, it in enumerate(items):
        w.u32(it['type']); w.u32(it['state']); w.u32(it['id'])
        res = it['flags'] | (0x80 if i == len(items) - 1 else 0) | (1 if 'items' in it else 0)
        w.u16(res); w.wz(it['text']); w.align4()
        if 'items' in it:
            w.u32(it['help_id']); _enc_menuex_items(w, it['items'])


def enc_menu(m):
    w = W()
    if m['ex']:
        h = bytes.fromhex(m['header'])
        w.u16(1); w.u16(len(h)); w.b += h
        _enc_menuex_items(w, m['items'])
    else:
        h = bytes.fromhex(m['header_extra'])
        w.u16(0); w.u16(len(h)); w.b += h
        _enc_menu_items(w, m['items'])
    w.b += bytes.fromhex(m.get('_tail', ''))
    return bytes(w.b)


def dec_strings(b, block):
    """String table block `block` (resource name id): 16 counted UTF-16 strings, ids (block-1)*16 + i."""
    r = R(b)
    out = {}
    for i in range(16):
        n = r.u16()
        s = b[r.p:r.p + 2 * n].decode('utf-16-le'); r.p += 2 * n
        if n:
            out[str((block - 1) * 16 + i)] = s
    res = {'strings': out}
    res.update(_tail(r, b))
    return res


def enc_strings(t, block):
    w = W()
    for i in range(16):
        s = t['strings'].get(str((block - 1) * 16 + i), '')
        w.u16(len(s)); w.b += s.encode('utf-16-le')
    w.b += bytes.fromhex(t.get('_tail', ''))
    return bytes(w.b)


def dec_accel(b):
    out = []
    for o in range(0, len(b) - len(b) % 8, 8):
        fl, key, cmd, pad = struct.unpack_from('<HHHH', b, o)
        out.append({'flags': fl & ~0x80, 'key': key, 'id': cmd, 'pad': pad})
    res = {'entries': out}
    if len(b) % 8:
        res['_tail'] = b[len(b) - len(b) % 8:].hex()
    return res


def enc_accel(a):
    w = W()
    for i, e in enumerate(a['entries']):
        w.u16(e['flags'] | (0x80 if i == len(a['entries']) - 1 else 0)); w.u16(e['key']); w.u16(e['id'])
        w.u16(e['pad'])
    w.b += bytes.fromhex(a.get('_tail', ''))
    return bytes(w.b)


def dec_version(b):
    node, end = _vnode(b, 0)
    if _align(end, 4) < len(b) or end > len(b):
        node['_tail'] = b[end:].hex()
    return node


def _vnode(b, p):
    ln, vl, typ = struct.unpack_from('<HHH', b, p)
    r = R(b, p + 6)
    key = r.wz()
    r.align4()
    node = {'key': key, 'type': typ}
    if typ == 1:
        val = b[r.p:r.p + 2 * vl]
        node['text'] = val.decode('utf-16-le')
        r.p += 2 * vl
    else:
        node['value'] = b[r.p:r.p + vl].hex()
        r.p += vl
    r.align4()
    kids = []
    while r.p < p + ln:
        kid, e = _vnode(b, r.p)
        kids.append(kid)
        r.p = _align(e, 4)
    if kids:
        node['children'] = kids
    return node, p + ln


def _enc_vnode(n):
    w = W()
    w.b += b'\0' * 6
    w.wz(n['key']); w.align4()
    if n['type'] == 1:
        w.b += n['text'].encode('utf-16-le')
        vl = len(n['text'])
    else:
        v = bytes.fromhex(n['value']); w.b += v; vl = len(v)
    for k in n.get('children', []):
        w.align4()
        w.b += _enc_vnode(k)
    struct.pack_into('<HHH', w.b, 0, len(w.b), vl, n['type'])
    return bytes(w.b)


def enc_version(n):
    b = _enc_vnode(n)
    return b + bytes.fromhex(n.get('_tail', ''))


def bmp_file(dib):
    hs, = struct.unpack_from('<I', dib, 0)
    if hs == 12:
        bits, ncol = struct.unpack_from('<H', dib, 10)[0], 0
        pal = (1 << bits) * 3 if bits <= 8 else 0
    else:
        bits, = struct.unpack_from('<H', dib, 14)
        comp, = struct.unpack_from('<I', dib, 16)
        ncol, = struct.unpack_from('<I', dib, 32)
        n = ncol or ((1 << bits) if bits <= 8 else 0)
        pal = 4 * n + (12 if comp == 3 and hs == 40 else 0)
    off = 14 + hs + pal
    return b'BM' + struct.pack('<IHHI', 14 + len(dib), 0, 0, off) + dib


CODECS = {'DIALOG': (dec_dialog, enc_dialog), 'MENU': (dec_menu, enc_menu), 'ACCELERATOR': (dec_accel, enc_accel),
          'VERSION': (dec_version, enc_version)}


def tname(t):
    return TYPES.get(t, f'#{t}') if isinstance(t, int) else t


def decode_entry(e):
    """JSON form of one resource, or None for one kept as a file."""
    t = tname(e['type'])
    try:
        if t == 'STRING':
            v = dec_strings(e['data'], e['name'])
            if enc_strings(v, e['name']) == e['data']:
                return v
        elif t in CODECS:
            dec, enc = CODECS[t]
            v = dec(e['data'])
            if enc(v) == e['data']:
                return v
    except (ValueError, struct.error, UnicodeDecodeError, IndexError, KeyError):
        pass
    return None


def encode_entry(t, name, v):
    if t == 'STRING':
        return enc_strings(v, name)
    return CODECS[t][1](v)


# ---------------------------------------------------------------- unpack / pack


def _fname(e):
    t = tname(e['type']).lstrip('#')
    safe = lambda s: ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(s))
    return f'{safe(t)}_{safe(_k(e["name"]).lstrip("#"))}_{e["lang"]}'


def unpack(d, outdir):
    pe, s, entries, dirs = read_tree(d)
    if s is None:
        _fail('no resources')
    os.makedirs(f'{outdir}/res', exist_ok=True)
    built = build(entries, dirs, s['va'])
    man = {'dirs': dirs, 'pad': d[s['rptr'] + len(built):s['rptr'] + s['rsize']].hex()
           if len(built) <= s['rsize'] else '', 'resources': []}
    if s['vsize'] != len(built):
        man['vsize_extra'] = s['vsize'] - len(built)
    if pe.datadir(d, 2)[1] != len(built):
        man['dd_extra'] = pe.datadir(d, 2)[1] - len(built)
    for e in entries:
        t = tname(e['type'])
        rec = {'type': _k(e['type']) if t.startswith('#') or isinstance(e['type'], str) else t,
               'name': _k(e['name']), 'lang': e['lang'], 'codepage': e['codepage']}
        if e['reserved']:
            rec['reserved'] = e['reserved']
        if e.get('after'):
            rec['after'] = e['after'].hex()
        v = decode_entry(e)
        if v is not None:
            rec['decoded'] = v
        elif t == 'BITMAP':
            rec['file'] = f'res/{_fname(e)}.bmp'
            open(f'{outdir}/{rec["file"]}', 'wb').write(bmp_file(e['data']))
        else:
            rec['file'] = f'res/{_fname(e)}.bin'
            open(f'{outdir}/{rec["file"]}', 'wb').write(e['data'])
        man['resources'].append(rec)
    with open(f'{outdir}/manifest.json', 'w') as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)
    return man


def entries_from(man, outdir):
    out = []
    for rec in man['resources']:
        t = rec['type']
        tkey = TYPE_IDS[t] if t in TYPE_IDS else _unk(t)
        name = _unk(rec['name']) if isinstance(rec['name'], str) else rec['name']
        if 'decoded' in rec:
            data = encode_entry(t, name, rec['decoded'])
        else:
            f = rec['file']
            if '..' in f.split('/') or f.startswith('/'):
                _fail(f'bad file name {f!r}')
            data = open(os.path.join(outdir, f), 'rb').read()
            if t == 'BITMAP':
                if data[:2] != b'BM':
                    _fail(f'{f}: not a .bmp')
                data = data[14:]
        out.append({'type': tkey, 'name': name, 'lang': rec['lang'], 'codepage': rec['codepage'],
                    'reserved': rec.get('reserved', 0), 'data': data, 'after': bytes.fromhex(rec.get('after', ''))})
    return out


def pack(outdir, d):
    man = json.load(open(f'{outdir}/manifest.json'))
    pe, s, _, _ = read_tree(d)
    entries = entries_from(man, outdir)
    sec = build(entries, man['dirs'], s['va'])
    return replace_rsrc(d, sec, bytes.fromhex(man.get('pad', '')), man.get('vsize_extra', 0), man.get('dd_extra', 0))


def main(argv):
    if len(argv) == 4 and argv[1] == 'unpack':
        man = unpack(open(argv[2], 'rb').read(), argv[3])
        print(len(man['resources']), 'resources')
    elif len(argv) == 5 and argv[1] == 'pack':
        open(argv[4], 'wb').write(pack(argv[2], open(argv[3], 'rb').read()))
    elif len(argv) >= 3 and argv[1] == 'verify':
        import tempfile
        bad = 0
        for p in argv[2:]:
            d = open(p, 'rb').read()
            with tempfile.TemporaryDirectory(prefix='rsrcv') as td:
                try:
                    man = unpack(d, td)
                except ValueError as e:
                    print('SKIP', p, e); continue
                try:
                    ok = pack(td, d) == d
                except ValueError as e:
                    print('FAIL', p, e); bad += 1; continue
                nd = sum('decoded' in r for r in man['resources'])
                print('OK  ' if ok else 'MISMATCH', p, len(man['resources']), 'resources,', nd, 'decoded')
                bad += not ok
        return 1 if bad else 0
    elif len(argv) == 3 and argv[1] == 'list':
        _, _, entries, _ = read_tree(open(argv[2], 'rb').read())
        for e in entries:
            print(f'{tname(e["type"]):14s} {_k(e["name"]):>10s} lang {e["lang"]:5d} {len(e["data"]):7d} bytes')
    else:
        sys.stderr.write(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
