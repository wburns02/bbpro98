"""c-tree writer semantics the game depends on: B-tree layout from pack_tree and the file header, descriptor and
index def fields do_apply sets. The do_apply tests use the stats template the game wrote and skip without it."""
import os
import struct

import pytest

import ctree
from ctree import NODE_PAY, NODE_TOTAL, REC_HDR, FAFA

TEMPLATE_DAT = '/mnt/nvme/bbpro98/lahman/templates/T16_2L/16NEW001.DAT'


def node(buf):
    nxt, prv, cnt, used = struct.unpack_from('<IIHH', buf, 0)
    return nxt, prv, cnt, used


def items(n, klen=6):
    return [(struct.pack('>I', i).rjust(klen, b'\0'), 0x1000 + i * 64) for i in range(n)]


# ---------------------------------------------------------------- pack_tree

def test_single_leaf():
    its = items(10)
    pls, root, leaf, levels = ctree.pack_tree(its, 6, 5000, 460)
    assert (len(pls), root, leaf, levels) == (1, 5000, 5000, 1)
    nxt, prv, cnt, used = node(pls[0])
    assert (nxt, prv, cnt, used) == (0, 0, 10, 100)
    assert struct.unpack_from('<H', pls[0], 0x10)[0] == 0x0100       # leaf flag
    assert pls[0][0x12 + 460:0x12 + 466] == b'\xff' * 6               # rightmost leaf: all-FF high key
    for k, (key, hdr) in enumerate(its):
        o = 0x12 + k * 10
        assert struct.unpack_from('<I', pls[0], o)[0] == hdr
        assert pls[0][o + 4:o + 10] == key
    assert all(len(p) == NODE_PAY for p in pls)


def test_leaf_cap_is_high_key_offset_over_entry_size():
    hk = 460
    cap = hk // 10                                                     # 46, the stats tables' leaf size
    its = items(cap * 3 + 5)
    pls, root, leaf, levels = ctree.pack_tree(its, 6, 0, hk)
    assert levels == 2
    leaves = [p for p in pls if struct.unpack_from('<H', p, 0x10)[0] == 0x0100]
    assert [node(p)[2] for p in leaves] == [cap, cap, cap, 5]
    assert leaf == 0 and root == NODE_TOTAL * len(leaves)


def test_leaf_chain_and_high_keys():
    its = items(100)
    pls, root, leaf, levels = ctree.pack_tree(its, 6, 1000, 460)
    by_off = {1000 + i * NODE_TOTAL: p for i, p in enumerate(pls)}
    off, seen, prev = leaf, [], 0
    while off:
        p = by_off[off]
        nxt, prv, cnt, used = node(p)
        assert prv == prev
        ks = [p[0x12 + k * 10 + 4:0x12 + k * 10 + 10] for k in range(cnt)]
        hi = p[0x12 + 460:0x12 + 466]
        assert hi == (ks[-1] if nxt else b'\xff' * 6)
        seen += ks
        prev, off = off, nxt
    assert seen == [k for k, _ in its]


def test_internal_nodes_ff_rightmost_and_next_chain():
    hk = 20                                                            # cap 2: forces three levels
    its = items(9)
    pls, root, leaf, levels = ctree.pack_tree(its, 6, 1000, hk)
    assert levels == 4
    by_off = {1000 + i * NODE_TOTAL: p for i, p in enumerate(pls)}
    internal = {o: p for o, p in by_off.items() if struct.unpack_from('<H', p, 0x10)[0] == 0}
    assert root in internal
    for o, p in internal.items():
        nxt, prv, cnt, used = node(p)
        assert prv == 0
        assert used == cnt * 10
    # The root-to-rightmost-leaf path is keyed all-FF; every other separator is its subtree's last key.
    o = root
    while o in internal:
        p = internal[o]
        cnt = node(p)[2]
        last = 0x12 + (cnt - 1) * 10
        assert p[last + 4:last + 10] == b'\xff' * 6
        o = struct.unpack_from('<I', p, last)[0]
    assert node(by_off[o])[0] == 0                                     # landed on the rightmost leaf
    # Walk down each level's leftmost node and follow next across the level: covers every node once.
    level_heads, o = [], root
    while True:
        level_heads.append(o)
        p = by_off[o]
        if struct.unpack_from('<H', p, 0x10)[0] == 0x0100:
            break
        o = struct.unpack_from('<I', p, 0x12)[0]
    count = 0
    for h in level_heads:
        while h:
            count += 1
            h = node(by_off[h])[0]
    assert count == len(pls)


def test_bad_high_key_offset_rejected():
    with pytest.raises(ValueError):
        ctree.pack_tree(items(3), 6, 0, 8)                             # below one entry
    with pytest.raises(ValueError):
        ctree.pack_tree(items(3), 6, 0, NODE_PAY)                      # high key would run off the node


# ---------------------------------------------------------------- do_apply on a game-written file

@pytest.fixture(scope='module')
def template():
    if not os.path.exists(TEMPLATE_DAT):
        pytest.skip('stats template absent')
    return open(TEMPLATE_DAT, 'rb').read()


def stat_payload(scope, pid, nwords):
    return struct.pack('<%dH' % (3 + nwords), scope, 2, pid, *range(nwords))


def adds(src, n):
    _, _, members, *_ = ctree.parse(src)
    data = {m['name'].rsplit('.', 1)[0]: i for i, m in enumerate(members) if m['kind'] == 'data'}
    width = {}
    recs, by_mem, *_ = ctree.parse(src)
    for name, i in data.items():
        rs = [r for r in by_mem.get(members[i]['num'], []) if src[r.off] != 0xFF]
        width[name] = (rs[0].pl - 6) // 2 if rs else 20
    out = []
    for pid in range(n):
        for name in ('bt', 'pt', 'ft'):
            if name in data:
                out.append({'op': 'add', 'm': data[name],
                            'data': stat_payload(2, 100 + pid, width[name]).hex()})
    return out


@pytest.fixture(scope='module')
def applied(template):
    edits = adds(template, 300)
    return ctree.do_apply(template, edits), edits


def test_no_edits_returns_source(template):
    assert ctree.do_apply(template, []) is template


def test_header_words(applied):
    out, _ = applied
    assert len(out) % 0x8000 == 0
    assert struct.unpack_from('<I', out, 0)[0] == len(out) - 1
    last = struct.unpack_from('<I', out, 8)[0]
    assert out[last + 1:] == b'\xff' * (len(out) - last - 1)
    # The last used byte closes a record: scanning the records ends exactly there.
    end = max(r.hdr + r.total for r in ctree.scan_records(out))
    assert end == last + 1


def test_trees_hold_every_record_sorted(template, applied):
    out, edits = applied
    recs, by_mem, members, idxinfo, idxdesc, datadesc, *_ = ctree.parse(out)
    checked = 0
    for idxmem, (trees, datam, base) in idxinfo.items():
        live = {r.hdr for r in by_mem.get(datam, []) if out[r.off] != 0xFF}
        for tr in trees:
            if not tr.klen:
                continue
            keys = [k for k, _ in tr.entries]
            assert keys == sorted(keys)
            assert {p for _, p in tr.entries} == live
            assert tr.count == len(live)
            checked += 1
    assert checked
    n_added = sum(1 for e in edits)
    assert sum(len([r for r in by_mem.get(d, []) if out[r.off] != 0xFF])
               for _, (_, d, _) in idxinfo.items()) >= n_added


def test_index_defs_and_descriptors(applied):
    out, _ = applied
    recs, by_mem, members, idxinfo, idxdesc, datadesc, *_ = ctree.parse(out)
    nodemem = {r.hdr: r.mem for r in recs}
    for idxmem, (trees, datam, base) in idxinfo.items():
        drec = datadesc.get(datam)
        if drec is not None and by_mem.get(datam):
            assert struct.unpack_from('<I', out, drec.off + 0x50)[0] == max(r.hdr for r in by_mem[datam])
        for tr in trees:
            if not tr.klen or not tr.root:
                continue
            db = tr.desc.off + tr.defbase
            leftmost = struct.unpack_from('<I', out, db + 0x48)[0]
            o = tr.root
            depth = 1
            while struct.unpack_from('<H', out, o + 0x10)[0] != 0x0100:
                o = struct.unpack_from('<I', out, o + 0x12)[0]
                depth += 1
            assert leftmost == o
            if depth > 1:
                assert struct.unpack_from('<I', out, db + 0x30)[0] >= 3
            for np in tr.nodes:
                h = np - REC_HDR
                assert out[h:h + 2] == FAFA and nodemem[h] == idxmem
                assert struct.unpack_from('<I', out, h + 14)[0] == 0          # node records: prev 0


def test_reapply_grows_and_stays_valid(applied):
    out, _ = applied
    again = ctree.do_apply(out, adds(out, 50))
    assert len(again) % 0x8000 == 0
    assert struct.unpack_from('<I', again, 0)[0] == len(again) - 1
    recs, by_mem, members, idxinfo, *_ = ctree.parse(again)
    for idxmem, (trees, datam, base) in idxinfo.items():
        live = {r.hdr for r in by_mem.get(datam, []) if again[r.off] != 0xFF}
        for tr in trees:
            if tr.klen:
                assert {p for _, p in tr.entries} == live
