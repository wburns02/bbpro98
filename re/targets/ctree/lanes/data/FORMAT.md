# FPS Baseball Pro '98 c-tree Plus container format (verified against bytes)

Applies to: `Assn/MLBPA97.eos`, `Assn/_DEFAULT.ASN`, `Assn/MLBPA96E.ASN`, `Assn/MLBPA97.ASN`,
`SCHEDTMP.DAT`, `Stats/_DEFAULT.DAT`, `Stats/mlbpa96e.dat`, `Stats/mlbpa97.DAT`.
These are FairCom c-tree Plus **superfiles**: one OS file hosting numbered "members"
(data members with variable-length records + index members with B-trees), here wrapped in a
custom on-disk layout (the game talks to it only through FPS_CT.dll).

## File header (512 bytes, offset 0)

```
+0x00  u32  physical file size - 1; the physical size is a multiple of 0x8000 and
            everything past the last used byte is 0xff. (Read as u16@0 = ffff/7fff
            plus u32@2 = size in 64K units this looked like a magic and a chunk
            count; it is one u32. Writing a chunk count at +2 makes the engine see
            EOF early and overwrite appended nodes.)
+0x08  u32  last used byte (eos 0x983d < file size); the engine appends at +1
+0x0c  u32  512 (sector/block size)
+0x10  u32  0x0b/0x0f/0x31 = highest member number (eos 11, ASN 15, DAT 49)
+0x14  u32  member count + 1 (12 / 17 / 50)
+0x28  8B   81 00 00 02 00 00 00 80  (constant in all eight files)
+0x30  ...  06 02 04 02 e0 01 ee 01 ... (unknown, same in all)
```

## Stream layout

After the header the file is one flat stream of length-prefixed blocks:

| block | magic | header | length |
|-------|-------|--------|--------|
| FE FE kind-1 (member segment start) | `fe fe` | u32 A=len, u32 B, u32 member, u32 ptr1, u32 ptr2, u32 0, u32 H | A (31, 34 or 512 bytes); records start at +A |
| FE FE kind-2 (member definition)    | `fe fe` | same, then `FC!DEF` at +30 | A = 2048; next block at +2048 |
| FA FA record | `fa fa` | u32 total, u32 payload_len, u32 member, u32 prev-record-hdr (same member, back chain) | total = payload_len + 18 |
| FD FD free gap | `fd fd` | u32 total (= 18+fill), u32 0, u32 0, u16 0, then 0xff fill | total |

* FE FE kind-1 `ptr1/ptr2` point at the member's kind-2 (FC!DEF) block (self for member 0).
* Kind-2 blocks contain `FC!DEF` + u32 size + u32 timestamp + the serialized IFIL/DODA
  definition and end with the host-relative member name, e.g. `ASSN\MLBPA97.eos!psaMvp`.
* Empty members reserve a 512-byte kind-1 block (A=0x200) filled with 0xff.
* Free gaps: 18-byte header then 0xff fill; gap length ends exactly where the next block starts.

## Records (FA FA)

`fa fa | u32 total | u32 payload_len | u32 member | u32 prev_hdr`

* `member` = superfile member number. Even = data members, odd = their index members,
  0 = control (descriptor records), 1 = directory.
* `prev_hdr` = file offset of the previous record **header** of the same member (0 = chain
  start). Not perfectly maintained by the engine (~3% of records diverge from stream order).
* **Tombstones** (verified on mlbpa97.DAT member 4, 708 of 4721 records): a deleted record
  keeps its FA FA header, sets `payload[0] = 0xff` and stores a u32 free-chain link at
  `payload+1` (file offset hdr+19). 707/708 links point at another tombstone of the same
  member; the chain is LIFO per member through the descriptor (below).
* Live records of the stat members start with payload words from {0,1,2,3,16,17}, so
  `payload[0] == 0xff` never collides with live data there.

## Member descriptors (records of member 0)

Every member has a 192-byte (data) or 192/320-byte (index) descriptor record in member 0;
the name is the base member name padded to 0x40 with spaces (`ft.dat`, `ft.idx`, ...).

**data member descriptor** (verified against mlbpa97.DAT where member 4 = ft.dat has 4013
live + 708 tombstone records):
```
+0x40 u32 reclen-1 (repeated at +0x48)
+0x44 u32 delete-chain head: hdr of the most recently tombstoned record (0 = none);
          links continue through the tombstone at hdr+19 (payload[1:5])
+0x4c u32 offset of this member's kind-1 FE FE block
+0x50 u32 hdr of the member's last record
+0x54 u32 records added so far (cumulative; 27382 for ft.dat >> current 4721)
+0x58 u32 live (non-tombstone) record count  == 4013 for ft.dat
+0x68 81 00 00 00
+0x6c u32 record length
+0x70 u32 (3)
+0x84 u32 self (payload offset)
```

**index member descriptor**: `name` (0x40) then one 0x80-byte tree def per B-tree
(def t starts at +0x40 + t*0x80; absolute offsets below are for tree 0):
```
+0x40 u32 493 (node payload size - 1), repeated at +0x48
+0x4c u32 offset of this member's kind-1 FE FE block
+0x58 u32 entry count (live records of the data member)
+0x5c u32 root node PAYLOAD offset (0 only if the tree is empty)
+0x68 81 00 ee 01, +0x70 u32 3 on every multi-level tree (def+0x30)
+0x74 u16 leaf high-key offset hk (def+0x34): a leaf holds hk // (4 + klen) entries
          and keeps its high key at entry offset hk (all-FF on the rightmost leaf)
+0x7c u16 0x0220, +0x7e u16 4
+0x80 u16 1, +0x82 u16 key length in bytes
+0x84 u32 0
+0x88 u32 leftmost leaf (def+0x48; equals the root only for a one-node tree), +0x8c u32 index member number
+0x90 u32 self / second def starts here for 320-byte (2-tree) descriptors
```
Cross-checks that hold on every member of all eight files: descriptor entry count ==
walked tree entries == live (payload[0]!=0xff) record count of the data member.

## B-tree nodes (FA FA records of an index member, payload 494)

```
+0x00 u32 next leaf payload offset, +0x04 u32 prev leaf payload offset
+0x08 u16 entry count
+0x0a u16 bytes used by entries (= count * entry size, entry size = 4 + klen)
+0x0c u32 0, +0x10 u16 (0x0100 leaf / 0x0000 branch observed)
+0x12 entries: [u32 ptr][key bytes (klen)]
```
* Leaf: `ptr` = record **header** offset (payload = ptr + 18), key = key bytes for that record.
* Branch: `ptr` = child node **payload** offset; entry key = separator (last key of that
  child's subtree), all-FF on the rightmost path. Branch nodes chain `next` within their
  level with prev 0. Every index node record the game writes has prev_hdr = 0. Discriminate: child iff `d[ptr-18:ptr-16] == fa fa` and that record's
  member == this index member (data records carry the even member number, so no collision).
* In-order traversal yields keys in ascending order (verified 4013/4013 on mlbpa97.DAT
  member 5).
* Stale pointer graphs: the engine leaves dead branch pointers behind (MLBPA97.ASN tr.idx
  walks 4632 nodes for 34 entries; sp.idx has 36 orphan nodes with descriptor count 0).
  A cycle-safe walk with a seen-set is required; it still terminates at the right entries.
* Key content: usually record bytes at fixed offsets, e.g. psaMvp tree1 key = payload[0:6],
  psaMvp tree2 key = payload[2:4] + 00 00 + payload[4:6], SCHEDTMP key = payload[0:4].
  The codec infers the byte map (offset or constant per position) from a live tree's
  (key, record) pairs; a wrong-but-consistent map still yields a valid tree.

## Evidence

* All counts cross-check: descriptors' entry counts == walked tree entries == live record
  counts on every member of all eight files.
* FE FE block lengths confirmed by next-block positions; FD FD gap ends == next block start.
* Delete chain: descriptor +0x44 head links through tombstone payload[1:5] u32s. (An earlier
  draft put the head at +0x50, which is the member's last record.)
* Tombstones: never referenced by a live tree entry, never with a stale index entry.
* File header: u32@0 + 1 == file length and u32@8 == last used byte on every game-written file;
  corrected 2026-10-08 against mlbpa96e.dat, mlbpa97.DAT, _DEFAULT.DAT and FPS_CT.dll's search path.
  work/ctree.py is the maintained codec; codec.py here is the superseded lane draft.
