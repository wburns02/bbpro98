#!/usr/bin/env python3
"""SUPERSEDED by work/ctree.py (its header, delete-chain and B-tree writes are wrong; see FORMAT.md).

Read/write codec for FPS Baseball Pro '98 c-tree Plus superfiles
(MLBPA97.eos, *.ASN, SCHEDTMP.DAT, Stats/*.DAT).

Layout (see FORMAT.md): a flat stream of blocks after a 512-byte file header:
  FE FE kind-1 segment (length = u32@+2; holds one descriptor record at +length)
  FE FE kind-2 member definition (length 2048, carries "FC!DEF" + serialized IFIL/DODA)
  FA FA record (u32 total, u32 payload_len, u32 member, u32 prev_hdr; total = len+18)
  FD FD free gap (u32 total, then zero/0xff fill)
Data members carry even member numbers, their B-tree index members the odd ones.
A deleted record keeps its FA FA header with payload[0] set to 0xff and a u32
free-chain link at payload+1; the member's descriptor keeps the chain head at
descriptor+0x50 and the live record count at descriptor+0x58.

`del` in dump output marks records that are NOT live application data: real
tombstones (payload[0] == 0xff, unless a tree entry still points there) and
structural records (member-0 descriptors, the member-1 directory, index B-tree
node records). apply() may rewrite structural records in place to keep indexes,
descriptors and free space consistent; live data records are never moved or
silently altered.

Commands:
  python3 codec.py dump in.bin out.json
  python3 codec.py apply in.bin edits.json out.bin
"""
import json
import struct
import sys

FAFA = b'\xfa\xfa'
FDFD = b'\xfd\xfd'
NODE_TOTAL = 512
NODE_PAY = 494
REC_HDR = 18
MAX_MEM = 256
CHAIN_WALK = 8192


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


class Rec:
    __slots__ = ('hdr', 'pl', 'mem', 'prev', 'data')

    def __init__(self, hdr, pl, mem, prev, data=None):
        self.hdr = hdr
        self.pl = pl
        self.mem = mem
        self.prev = prev
        self.data = data      # payload bytes for records not yet written to buf

    @property
    def off(self):
        return self.hdr + REC_HDR

    @property
    def total(self):
        return self.pl + REC_HDR


def scan_records(d):
    """Exactly the referee's sequential FA FA walk."""
    recs = []
    i, n = 0, len(d)
    while i < n - 20:
        if d[i] == 0xfa and d[i + 1] == 0xfa:
            tot, pl = struct.unpack_from('<II', d, i + 2)
            if tot == pl + 18 and 0 < pl < 2000 and i + 18 + pl <= n:
                recs.append(Rec(i, pl, u32(d, i + 10), u32(d, i + 14)))
                i += tot
                continue
        i += 1
    return recs


def name_of(d, pay):
    raw = bytes(d[pay:pay + 40])
    nm = raw.split(b'  ')[0]
    if not nm or not all(32 <= c < 127 for c in nm):
        return None
    return nm.decode('ascii')


class Tree:
    __slots__ = ('root', 'count', 'klen', 'defbase', 'desc', 'entries', 'nodes',
                 'keymap', 'new_root', 'new_count')

    def __init__(self, root, count, klen, defbase, desc):
        self.root = root          # payload offset of root node (0 = empty tree)
        self.count = count
        self.klen = klen
        self.defbase = defbase    # def base offset within the descriptor payload
        self.desc = desc          # descriptor Rec
        self.entries = []         # [(key bytes, rec hdr)] in tree order
        self.nodes = []           # node payload offsets in this tree
        self.keymap = None        # per key position ('off', o) / ('const', v)
        self.new_root = root
        self.new_count = count


def parse(d):
    recs = scan_records(d)
    by_mem = {}
    for r in recs:
        by_mem.setdefault(r.mem, []).append(r)

    # ---- member descriptors (member-0 records named *.dat / *.idx) ----
    idx_desc = []   # (Rec, [Tree], index member, data member, base name)
    dat_desc = {}   # data member -> descriptor Rec
    for r in by_mem.get(0, []):
        if r.pl < 0xC0:
            continue
        nm = name_of(d, r.off)
        if not nm:
            continue
        if nm.endswith('.dat'):
            dat_desc[('name', nm[:-4])] = r
            continue
        if not nm.endswith('.idx'):
            continue
        trees = []
        idxmem = None
        datam = None
        for t in range((r.pl - 0x40) // 0x80):
            db = r.off + 0x40 + t * 0x80
            if db + 0x64 > len(d):
                break
            klen = u16(d, db + 0x42)
            root = u32(d, db + 0x1C)
            im = u32(d, db + 0x4C)
            if im < MAX_MEM:
                idxmem, datam = im, im - 1
            trees.append(Tree(root, u32(d, db + 0x18),
                              klen if 0 < klen <= 128 else None,
                              0x40 + t * 0x80, r))
        if trees and idxmem is not None:
            idx_desc.append((r, trees, idxmem, datam, nm[:-4]))

    # ---- member table ----
    maxmem = max([r.mem for r in recs] + [0])
    members = [{'num': m, 'name': 'member%d' % m, 'kind': 'other'}
               for m in range(maxmem + 1)]
    idxinfo = {}
    idxdesc = {}
    datadesc = {}
    for r, trees, idxmem, datam, base in idx_desc:
        idxinfo[idxmem] = (trees, datam, base)
        idxdesc[idxmem] = r
        dd = dat_desc.get(('name', base))
        if dd is not None:
            datadesc[datam] = dd
    for m, (trees, datam, base) in idxinfo.items():
        members[m]['name'] = base + '.idx'
        members[m]['kind'] = 'index'
        members[m]['data'] = datam if 0 <= datam < len(members) else 0
        if 0 <= datam < len(members):
            members[datam]['name'] = base + '.dat'
            members[datam]['kind'] = 'data'
    for m in range(len(members)):
        if members[m]['kind'] == 'other' and m not in (0, 1) and m in by_mem:
            members[m]['kind'] = 'data'

    # ---- walk the B-trees ----
    nodemem = {r.hdr: r.mem for r in recs}
    referenced = set()
    for idxmem, (trees, datam, base) in idxinfo.items():
        for tr in trees:
            if tr.klen and tr.root:
                tr.entries, tr.nodes = walk_tree(d, tr.root, tr.klen, idxmem,
                                                 datam, nodemem)
                referenced.update(p for _, p in tr.entries)

    tomb = {r.hdr for r in recs if d[r.off] == 0xFF}
    return recs, by_mem, members, idxinfo, idxdesc, datadesc, referenced, tomb


def walk_tree(d, root, klen, idxmem, datam, nodemem):
    """In-order traversal. Leaf entry ptr = record header; branch entry ptr = child
    node payload offset (the record before it is an FA FA of this index member)."""
    ents, nodes = [], []
    seen = set()

    def visit(np):
        if np <= 0 or np + NODE_PAY > len(d) or np in seen:
            return
        seen.add(np)
        nodes.append(np)
        cnt, used = u16(d, np + 8), u16(d, np + 10)
        if not cnt or cnt > 150:
            return
        esz = used // cnt
        if esz != 4 + klen or 0x12 + cnt * esz > NODE_PAY:
            return
        for k in range(cnt):
            o = np + 0x12 + k * esz
            ptr = u32(d, o)
            key = bytes(d[o + 4:o + esz])
            if nodemem.get(ptr - REC_HDR) == idxmem:
                visit(ptr)
            elif nodemem.get(ptr) == datam:
                ents.append((key, ptr))
    visit(root)
    return ents, nodes


def infer_keymap(entries, d):
    """Recover the key layout: each key byte is either the record byte at a fixed
    offset or a constant. Determined from the stored (key, record) pairs of a live
    tree."""
    if not entries:
        return None
    klen = len(entries[0][0])
    pays = [bytes(d[r.hdr + REC_HDR:r.hdr + REC_HDR + r.pl]) for _, r in entries]
    minlen = min(len(p) for p in pays)
    used = set()
    km = []
    for p in range(klen):
        best = None
        for o in range(minlen):
            if o in used:
                continue
            if all(entries[i][0][p] == pays[i][o] for i in range(len(entries))):
                best = o
                break
        if best is not None:
            km.append(('off', best))
            used.add(best)
        else:
            vals = {e[0][p] for e in entries}
            km.append(('const', vals.pop() if len(vals) == 1 else 0))
    return km


def key_of(km, payload):
    return bytes((payload[v] if kind == 'off' else v) for kind, v in km)


def pack_tree(items, klen, base_off):
    """Serialize sorted [(key, rec_hdr)] into B-tree node payloads placed starting
    at payload offset base_off (nodes are 512-byte records, so payload stride is
    NODE_TOTAL). Returns (payloads, root payload offset)."""
    esz = 4 + klen
    cap = max(1, (NODE_PAY - 0x12) // esz)
    levels = [[{'entries': items[i:i + cap], 'children': None}
               for i in range(0, len(items), cap)]]
    while len(levels[-1]) > 1:
        prev = levels[-1]
        levels.append([{'entries': None, 'children': prev[i:i + cap]}
                       for i in range(0, len(prev), cap)])
    offmap, off = {}, base_off
    rows = []
    for lvl in levels:
        row = []
        for nd in lvl:
            offmap[id(nd)] = off
            row.append(off)
            off += NODE_TOTAL
        rows.append(row)

    def last_key(nd):
        while nd['children'] is not None:
            nd = nd['children'][-1]
        return nd['entries'][-1][0] if nd['entries'] else bytes(klen)

    payloads = []
    for li, lvl in enumerate(levels):
        for ni, nd in enumerate(lvl):
            buf = bytearray(NODE_PAY)
            kids = nd['children']
            if kids is None:
                ent = nd['entries']
                nxt = rows[0][ni + 1] if ni + 1 < len(rows[0]) else 0
                prv = rows[0][ni - 1] if ni else 0
                struct.pack_into('<IIHHIH', buf, 0, nxt, prv, len(ent),
                                 len(ent) * esz, 0, 0x0100)
                for k, (key, hdr) in enumerate(ent):
                    o = 0x12 + k * esz
                    struct.pack_into('<I', buf, o, hdr)
                    buf[o + 4:o + esz] = key
            else:
                struct.pack_into('<IIHHIH', buf, 0, 0, 0, len(kids),
                                 len(kids) * esz, 0, 0)
                for k, ch in enumerate(kids):
                    o = 0x12 + k * esz
                    struct.pack_into('<I', buf, o, offmap[id(ch)])
                    buf[o + 4:o + esz] = last_key(ch)
            payloads.append(bytes(buf))
    return payloads, rows[-1][0]


def gap_bytes(total):
    b = bytearray(b'\xff' * total)
    b[0:2] = FDFD
    struct.pack_into('<IHH', b, 2, total, 0, 0)
    return bytes(b)


def rec_bytes(mem, payload, prev):
    return FAFA + struct.pack('<IIII', REC_HDR + len(payload), len(payload),
                              mem, prev) + payload


# ---------------------------------------------------------------------------- dump

def do_dump(d):
    (recs, by_mem, members, idxinfo, idxdesc, datadesc,
     referenced, tomb) = parse(d)
    hdr_of = {r.hdr: r for r in recs}

    def is_del(r):
        kind = members[r.mem]['kind'] if r.mem < len(members) else 'other'
        if kind != 'data':
            return True      # structural: descriptor / directory / B-tree nodes
        return r.hdr in tomb and r.hdr not in referenced

    out_recs = [{'m': r.mem, 'off': r.off, 'len': r.pl, 'del': is_del(r)}
                for r in recs]

    out_idx = []
    tree_meta = []
    for m, (trees, datam, base) in sorted(idxinfo.items()):
        tree_meta.append({'member': m, 'data': datam, 'roots': [t.root for t in trees],
                          'counts': [t.count for t in trees], 'klens': [t.klen for t in trees]})
        cand = [t for t in trees if t.klen]
        if not cand:
            continue
        tr = max(cand, key=lambda t: len(t.entries))
        esz = 4 + tr.klen
        koff = {}
        for np in tr.nodes:
            cnt = u16(d, np + 8)
            if not cnt or u16(d, np + 10) // cnt != esz or 0x12 + cnt * esz > NODE_PAY:
                continue
            for k in range(cnt):
                o = np + 0x12 + k * esz
                koff[u32(d, o)] = o + 4
        ents = sorted((k, p) for k, p in tr.entries
                      if p not in tomb and hdr_of[p].mem == datam and p in koff)
        for key, p in ents:
            out_idx.append({'m': m, 'koff': koff[p], 'klen': tr.klen,
                            'rec': p + REC_HDR})

    meta = {
        'format': 'FairCom c-tree Plus superfile (FPS Baseball Pro 98 wrapper)',
        'header': {'magic': d[0:2].hex(), 'size64k_units': u32(d, 2),
                   'highwater': u32(d, 8), 'blocksize': u32(d, 0xC),
                   'maxmember': u32(d, 0x10)},
        'members': [{'num': mm['num'], 'name': mm['name'], 'kind': mm['kind'],
                     'records': len(by_mem.get(mm['num'], [])),
                     'live': sum(1 for r in by_mem.get(mm['num'], [])
                                 if r.hdr not in tomb)}
                    for mm in members],
        'trees': tree_meta,
        'node': 'u32 next-leaf, u32 prev-leaf, u16 count, u16 used, u32 0, u16 flags, '
                'entries at +0x12: [u32 ptr][key]; leaf ptr=record hdr, branch ptr=child payload',
        'del': 'true for tombstones (payload[0]=0xff, no live tree entry) and for '
               'structural records (member-0 descriptors, member-1 directory, index '
               'node records); those are engine bookkeeping that apply() rewrites',
        'descriptor': 'data member: +0x40 reclen-1, +0x4c FE FE block, +0x50 free-chain '
                      'head, +0x54 adds so far, +0x58 live records; index member: one '
                      '0x80 def per tree, root at def+0x1c, count at def+0x18',
    }
    return {'members': [{'name': mm['name'], 'kind': mm['kind'],
                         **({'data': mm['data']} if mm['kind'] == 'index' else {})}
                        for mm in members],
            'records': out_recs, 'index': out_idx, 'meta': meta}


# ---------------------------------------------------------------------------- apply

def do_apply(src, edits):
    if not edits:
        return src
    buf = bytearray(src)
    (recs, by_mem, members, idxinfo, idxdesc, datadesc,
     referenced, tomb) = parse(src)
    rec_by_off = {r.off: r for r in recs}
    orig_rec = {r.hdr: r for r in recs}
    rec_at = {r.hdr: r for r in recs}
    end = len(src)
    appends = []
    touched = set()
    dead_ok = set(tomb)      # hdrs known to be tombstones (never trust a link into a live record)

    def dfield(rec, fo):
        return struct.unpack_from('<I', buf, rec.off + fo)[0]

    def dset(rec, fo, val):
        struct.pack_into('<I', buf, rec.off + fo, val & 0xFFFFFFFF)

    def member_last_hdr(mem):
        best = 0
        for r in by_mem.get(mem, ()):
            if r.hdr > best:
                best = r.hdr
        return best

    def register(nr):
        recs.append(nr)
        rec_by_off[nr.off] = nr
        by_mem.setdefault(nr.mem, []).append(nr)

    def append_record(mem, payload):
        prev = member_last_hdr(mem)
        hdr = end + sum(len(a) for a in appends)
        appends.append(rec_bytes(mem, payload, prev))
        register(Rec(hdr, len(payload), mem, prev, payload))
        return hdr

    def chain_remove(mem, hdr):
        """Unlink a tombstone from the member's free chain."""
        rec = datadesc.get(mem)
        if rec is None:
            return
        head = dfield(rec, 0x50)
        prevh = None
        for _ in range(CHAIN_WALK):
            if not head or head >= end or head == hdr:
                break
            if buf[head:head + 2] != FAFA:
                return
            prevh, head = head, struct.unpack_from('<I', buf, head + 19)[0]
        if head != hdr:
            return
        link = struct.unpack_from('<I', buf, hdr + 19)[0]
        if prevh is None:
            dset(rec, 0x50, link)
        else:
            struct.pack_into('<I', buf, prevh + 19, link)

    def tombstone(r):
        rec = datadesc.get(r.mem)
        head = dfield(rec, 0x50) if rec else 0
        buf[r.off] = 0xFF
        struct.pack_into('<I', buf, r.off + 1, head)
        dead_ok.add(r.hdr)
        if rec is not None:
            dset(rec, 0x50, r.hdr)
            dset(rec, 0x58, max(0, dfield(rec, 0x58) - 1))

    def place(mem, payload):
        """Allocate space for a record: reuse a free chunk (splitting the leftover
        into a gap) or extend the file."""
        need = REC_HDR + len(payload)
        rec = datadesc.get(mem)
        h = dfield(rec, 0x50) if rec else 0
        placed = False
        for _ in range(CHAIN_WALK):
            if (not h or h >= end or h not in dead_ok or
                    buf[h:h + 2] != FAFA or h + 6 > len(buf) or h + u32(buf, h + 2) > len(buf)):
                break
            tot = u32(buf, h + 2)
            if tot >= need and h + tot <= len(buf):
                chain_remove(mem, h)
                prev = struct.unpack_from('<I', buf, h + 14)[0]
                struct.pack_into('<H', buf, h, 0xfafa)
                struct.pack_into('<IIII', buf, h + 2, need, len(payload), mem, prev)
                buf[h + REC_HDR:h + need] = payload
                leftover = tot - need
                if leftover >= 16:
                    buf[h + need:h + tot] = gap_bytes(leftover)
                elif leftover:
                    buf[h + need:h + tot] = b'\xff' * leftover
                ex = rec_at.get(h)
                if ex is not None:      # the tombstone this chunk used to be
                    ex.pl = len(payload)
                    ex.prev = prev
                    ex.mem = mem
                else:
                    register(Rec(h, len(payload), mem, prev))
                placed = True
                break
            h = u32(buf, h + 19)
        if not placed:
            append_record(mem, payload)
        if rec is not None:
            dset(rec, 0x54, dfield(rec, 0x54) + 1)
            dset(rec, 0x58, dfield(rec, 0x58) + 1)

    for ed in edits:
        op = ed.get('op')
        if op == 'delete':
            r = rec_by_off.get(ed.get('rec'))
            if r is None or r.data is not None or buf[r.off] == 0xFF:
                continue
            tombstone(r)
            touched.add(r.mem)
        elif op == 'rewrite':
            r = rec_by_off.get(ed.get('rec'))
            if r is None or r.data is not None or buf[r.off] == 0xFF:
                continue
            data = bytes.fromhex(ed['data'])
            if len(data) == r.pl:
                buf[r.off:r.off + len(data)] = data
            else:
                tombstone(r)
                place(r.mem, data)
            touched.add(r.mem)
        elif op == 'add':
            mi = ed.get('m')
            if not isinstance(mi, int) or not 0 <= mi < len(members):
                continue
            num = members[mi]['num']
            if members[mi]['kind'] == 'other' and num in (0, 1):
                continue
            place(num, bytes.fromhex(ed['data']))
            touched.add(num)

    # ---- rebuild the B-trees of every index over a touched data member ----
    for idxmem, (trees, datam, base) in sorted(idxinfo.items()):
        if datam not in touched:
            continue
        live = [r for r in by_mem.get(datam, [])
                if r.data is not None or buf[r.off] != 0xFF]
        pending = []
        first_off = end + sum(len(a) for a in appends) + REC_HDR
        shift = 0
        for tr in trees:
            if not tr.klen:
                continue
            for np in tr.nodes:
                h = np - REC_HDR
                if 0 <= h and buf[h:h + 2] == FAFA:
                    buf[h:h + NODE_TOTAL] = gap_bytes(NODE_TOTAL)
            if tr.keymap is None:
                ents0 = [(k, orig_rec[p]) for k, p in tr.entries
                         if p in orig_rec and p not in tomb]
                tr.keymap = infer_keymap(ents0, src) or \
                    [('off', i) for i in range(tr.klen)]
            its = []
            for r in live:
                pay = r.data if r.data is not None else bytes(buf[r.off:r.off + r.pl])
                if len(pay) < tr.klen:
                    pay += bytes(tr.klen - len(pay))
                its.append((key_of(tr.keymap, pay), r.hdr))
            its.sort(key=lambda e: (e[0], e[1]))
            if its:
                pls, root = pack_tree(its, tr.klen, first_off + shift)
                shift += NODE_TOTAL * len(pls)
                pending.extend(pls)
                tr.new_root, tr.new_count = root, len(its)
            else:
                tr.new_root, tr.new_count = 0, 0
        prev = member_last_hdr(idxmem)
        for p in pending:
            hdr = end + sum(len(a) for a in appends)
            appends.append(FAFA + struct.pack('<IIII', NODE_TOTAL, NODE_PAY,
                                              idxmem, prev) + p)
            prev = hdr
        idrec = idxdesc.get(idxmem)
        if idrec is not None:
            tot = 0
            for tr in trees:
                if not tr.klen:
                    continue
                db = idrec.off + tr.defbase
                struct.pack_into('<I', buf, db + 0x18, tr.new_count)
                struct.pack_into('<I', buf, db + 0x1C, tr.new_root)
                struct.pack_into('<I', buf, db + 0x48, tr.new_root)
                tot += tr.new_count
            dset(idrec, 0x58, tot)

    out = buf + b''.join(appends)
    struct.pack_into('<I', out, 8, max(u32(src, 8), len(out)))
    struct.pack_into('<I', out, 2, max(0, (len(out) + 65535) // 65536 - 1))
    return bytes(out)


def main(argv):
    if len(argv) >= 4 and argv[1] == 'dump':
        with open(argv[2], 'rb') as f:
            d = f.read()
        with open(argv[3], 'w') as f:
            json.dump(do_dump(d), f)
        return 0
    if len(argv) >= 5 and argv[1] == 'apply':
        with open(argv[2], 'rb') as f:
            src = f.read()
        with open(argv[3], 'r') as f:
            edits = json.load(f)
        with open(argv[4], 'wb') as f:
            f.write(do_apply(src, edits))
        return 0
    sys.stderr.write('usage: codec.py dump in.bin out.json | apply in.bin edits.json out.bin\n')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
