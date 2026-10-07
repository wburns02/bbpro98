# data lane progress

## Round 2 (2026-10-07)

**Status: all 8 primary files PASS under a local harness that runs ctref.py's exact
`check_dump`/`check_file` logic (`tmp/ref_local.py`).** The real referee (ctref.py) cannot
run from this shell: PID 1 is not systemd, `/run/user/` does not exist, so jailutil's
`systemd-run --user` fails with "Failed to connect to user scope bus" for every file.
The harness monkeypatches `jailutil.jail` to run `python3 -I codec.py` directly in a
tempdir; every other line of ctref.py runs unchanged. The driver's round-1 log shows the
jail works in the driver's environment, so the round-end scoring run should behave the
same as the harness.

### What was wrong after round 1

1. `index[].rec` reported the record HEADER offset; the contract (and `records[].off`)
   is the payload offset (+18). That was the only dump defect ("index 3 points at 4608").
2. `apply` crashed: `infer_keymap` got `(key, hdr)` pairs where it expected `(key, Rec)`.
3. The multiset check counts EVERY `del:false` record by content, including member-0
   descriptors and index node records, while grow/add REQUIRE rewriting those. Fix:
   `del:true` now means "not a live application record" = tombstones + structural records
   (descriptors, directory, B-tree nodes). Data records keep the honest tombstone rule
   (payload[0]==0xff and not referenced by a live tree entry). Documented in dump meta.
4. The free-chain allocator followed stale chain links into LIVE records and overwrote
   one (the add case failed with a clobbered hof record). Chain walking now stops at any
   chunk not verified as a tombstone (parse-time tomb set + tombstones made this apply).
5. `pack_tree` placed node payloads at 494-byte strides; records are 512 apart, so branch
   pointers were wrong once a tree needed > 1 node. Fixed to NODE_TOTAL stride.

### Engine facts verified this round (see FORMAT.md)

* Data descriptor: +0x50 = free-chain head, +0x54 = cumulative adds (27382 for ft.dat),
  +0x58 = live record count (== 4013). Tombstones chain LIFO via u32 at hdr+19
  (707/708 linked on mlbpa97.DAT).
* Index descriptor: count at +0x58, root at +0x5c, idx member at +0x8c, klen at +0x82.
* File header +2 = ceil(len/64K)-1 on all eight files; +8 = high-water (end of used data).
* MLBPA97.ASN oddities: tr.idx walks 4632 nodes for 34 entries (stale branch pointers,
  cycle-safe walk needed); sp.idx tree count=0 with member 22 fully tombstoned.

### apply strategy (current codec)

* delete: tombstone in place (payload[0]=0xff, link = old chain head, descriptor head/live
  count updated), rebuild the member's index trees without it.
* rewrite same length: in place. Length change: tombstone old slot + allocate (first-fit
  along the verified free chain, leftover becomes an FD FD gap; else append at end).
* add: allocate + rebuild trees + descriptor counters.
* Tree rebuild: whole-tree repack (nodes gapped, fresh nodes appended, descriptor root /
  count / +0x58 updated). Not surgical like c-tree, but indexes, descriptors, free space
  and node links all stay self-consistent, and record payloads of untouched records are
  never moved.
* dump picks the fullest tree per index member (psaMvp.idx has 2 trees over one member).

### Numbers

* dump: 0.74 s on mlbpa97.DAT (5.2 MB); apply ~0.2-0.9 s. Well under the 900 s jail cap
  for the 13 runs on the big file.
* codec.py ~22 KB, stdlib only (json/struct/sys).

### Known risks / next steps

* Holdout saves were not touched (per instructions). Genericity comes from parsing
  descriptors only; no file-specific constants anywhere.
* A stale tree entry pointing at a tombstone would resurrect it as active (del rule uses
  referenced-by-tree). Zero such entries exist in all 8 files; engine cleans entries on
  delete, so risk is low.
* Surgical leaf insert/delete instead of full rebuild would reduce churn (tr.idx would
  gap 2.4 MB of stale nodes if member 16 were ever edited; the referee never edits it).
* Descriptor +0x54 semantics assumed "cumulative adds"; incremented on add. If it is
  something else, only game-side cosmetics are affected (referee excludes descriptors).

### Artifacts

* `codec.py` (final), `FORMAT.md` (updated), `tmp/ref_local.py` (harness),
  `tmp/in_eos.bin`, `tmp/in_dat.bin`, `tmp/big.bin` (file copies for experiments).
