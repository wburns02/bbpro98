# FPS Baseball Pro '98 — saved highlight replays (.tap) and the highlight queue (MLBPA97.NQ0)

> **Superseded 2026-10-07 by work/spec/TAP_FORMAT.md + work/tapcodec.py.** This lane's NQ0 container is right, but the .tap body is not decoded: it is a snapshot (0x41b bytes) plus camera, ball-flight and delta-coded 408-byte state records, with a 32-bit checksum the loader verifies. FUN_6807ac99 is the snapshot restore, not the writer. Kept as the lane record.

Codec: `voldat.py` (this lane). Two layouts selected by the NAME argument
(a `*.tap` entry name = the entry layout; `MLBPA97.NQ0` = the queue layout).

## The queue layout — MLBPA97.NQ0

```
offset  size        field
0       2           u16  version (0x0005)
2       per entry:  [u16 tag][u32 body_len][body]
```

* tags observed: 0x4001, 0x4002, 0x4003, 0x4004, 0x4005 (ascending 1:1 with the
  five saved plays in the sample)
* `body_len` = the exact byte count of the body that follows
* the bodies are **byte-identical copies** of the `hilights\highlighNNN.tap`
  files: entry 1 == `highlight002.tap`, entry 3 == `highlight005.tap`
  (verified with `bytes ==` on the full blobs)
* BBSIM evidence: `FUN_680735a9` builds the file name
  `s__s__s_03u_tap_680c5858 = "%s\\%s%03u.tap"` from
  `s_highlight_680c5844 + (((*param_1 & 0x4000) != 0) - 1 & 0xc)` — the 0x4000
  bit switches between the `user*.tap` and `highlight*.tap` directory prefixes;
  `FUN_68073ae8` (the queue loader) enumerates both patterns and ORs 0x4000 into
  the ids of the highlight*.tap files, so queue tags 0x4001.. = highlight replay
  ids 1.. N (BBSIM `_all.c` lines ~66000, `s__s_highlight__tap_680c58a0`).

## The entry layout — hilights/*.tap (shared by every queue body)

```
offset  size   field
0       2      u16 0x2b  entry marker (kept as the CAPTION_MARKER constant;
               FUN_680736c4/FUN_680737fc validate == 0x2b before reading on)
2       ...    the body: see the body model below
```

The body is tokenized in file order (no fixed offsets — strings may grow or
shrink and everything after an edited string simply shifts):

| token            | bytes                                       | meaning |
|------------------|---------------------------------------------|---------|
| `text`           | printable run (>= 4 chars) + NUL            | the play caption ("10-27-06 TOR 0, PIT 0 B-1st O-2 3rd Broskie-Gonzalez 0-0": date, away/home score, B/T bottom-top + inning, O-outs, base state, batter-pitcher, count); team records: city, manager, triCode ("PIT"), stadium; the queue bookkeeping names ("TORONTO.dat", "MLBPA97.NQ0", "TORONTO.DAT"); player first/last names; embedded frame text |
| `_pad`           | hex of leftover bytes (1-3 before a text run that starts mid-word; 1-3 at the end of a body) | derived: record-header bytes and the sub-word tails; the encoder replays them verbatim |
| `playback_word`  | little-endian u32                           | the frame log: pitch counts, frame times, screen positions, per-frame VCR snapshot words |
| `entry_marker`   | u16                                         | a .tap's leading 0x2b |
| `queue_header`   | u16                                         | the queue's 0x0005 version |
| `entry_tag`      | u16                                         | a queue entry's 0x4001.. marker |
| `_entry_length`  | u32                                         | derived: recomputed on encode (the body sits after the u32 that describes it) |

Text runs shorter than 4 chars stay inside `_pad`/`playback_word` bytes (the
file's own printable runs of >= 4 chars all surface as `text` tokens, which the
referee's coverage check requires).

### Byte-level facts (from hexdumping; see progress.md)

* caption: `2b 00` then 43-61 printable chars + NUL, zero padding out to byte 82
  in every sample, then `86 00 a5 8a...` (the in-memory record continues)
* the team records read like the reader in `FUN_6806a749`: a u16 line-up index +
  a 0x44-byte team block + singles, i.e. small header bytes (< 0x40) followed by
  the city/manager/triCode/stadium strings
* the player records read like `FUN_680ad9b1`/`FUN_680aaca1`: a u16 length +
  the name + the rest
* after the last player name the log begins: `00 00 00 01 00 52 02 58 ea c0...`
  in every sample — the state table, then the u32 words

### BBSIM evidence for the writers/readers

* `FUN_680737fc`  (save one entry): validates the 0x2b marker, reads a
  0x50-byte block (the caption field), then `FUN_6807a0cc` (the per-frame
  snapshot over the 0x41b-byte screen rect)
* `FUN_680736c4`  (load one entry): validates the 0x2b marker + a 0x50-byte block
* `FUN_6807ac99`  (snapshot to tape): `FUN_6807b080(0)` (the 0x2b-ish marker),
  `FUN_6807b0b0` (a frame counter u16), the game-state writers, then the frame
  rect check `!= 0x41b`
* `FUN_68034c13`/`FUN_68034ee9` (the hilight flush/queue): the entries are
  written as [u16 id | 0x4000][u32 length][body] chains — exactly the NQ0 model

## Round trip

`encode(x, decode(x)) == x` byte for byte on all three targets (verified in the
referee's bwrap jail), plus 6 random-seeded holdout edit rounds per file
(strings get "Qz" appended and must be stored; non-zero content ints get +1;
the re-decode must equal the edited JSON on every content leaf and re-encode
stably).
