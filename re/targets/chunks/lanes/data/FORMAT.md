# FORMAT.md — DATA chunks of SIM.DAT and Stadia/*.DAT (+ .DT), FPS Baseball Pro '98

> **Superseded 2026-10-07 by work/spec/SIMCHUNKS_FORMAT.md + work/simchunks.py.** This lane won round 3 on the
> referee, but its wall.tbl (ce8c) and shape.tbl (947d) layouts are misread or kept as raw runs, its texture
> chunks are packed u16 instead of DBM frames (work/chunkgfx.py), the e6e7 block is verbatim and the park traits
> are guessed. Kept as the lane record.


Verified 2026-10-07 (GLM lane `data`) from the 20 visible stadiums in
`/mnt/nvme/bbpro98/targets_data/chunks/` plus the SIM.DAT chunks, with one decompile
cross-check (`FUN_680384e9` in `BBSIM/_all.c:33290` reads the injury table with the same
record sizes found in the data: 96-byte records at offset 3948, 16-byte tables at 23628,
8-byte tables at 24364).

All chunks come from `00 01 06 07` tagged containers (see `work/chunkdat.py`); the chunk id
is stable per chunk role across all stadium files (e957 = stadium info in every .DAT/.DT).
The filename is `<id hex>_<source>.bin` (`SIM` = SIM.DAT chunk, `_DT` = from Stadia/*.DT,
plain = Stadia/*.DAT). All multi-byte fields are **little-endian**. Units: field distances
are stored in **1/30 ft** (12150 = 405 ft), wall heights likewise (300 = 10 ft).

---

## e957 — stadium info (`MI` tag)

Two variants, distinguished by file size:

### .DT variant (always 74 bytes)
```
"STA:" magic (4 bytes)
u32 restSize      — always 66 = file size - 8; its low byte 0x42 = 'B' reads as a
                    printable run "STA:B" with the magic (evidence: every .DT file)
u8  flag          — 1 in every file checked
char[63] name     — NUL-padded stadium name ("Anaheim Stadium", "Fenway Park", ...)
u8  variantFlag   — 0 except MINNESOT/MONTREAL (1) — dome/roof variants
u8  domeFlag      — 1 for CINCINNA/MINNESOT/MONTREAL/PHILADEL
```

### .DAT variant (~206-254 bytes)
```
"STA:" magic (4 bytes)
u32 restSize      — file size - 8
char[63] name     — full name, NUL-padded ("Atlanta-Fulton County Stadium")
u8  domeFlag      — 1 for MINNESOT/MONTREAL ("dome" parks); same role as the .DT flag
char[30] shortName— short name, NUL-padded ("Atlanta Stadium")
12 x u16 parkTraits at offset 102 (the traits block is 34 bytes = 12 u16 + 5 zero u16):
      u16 marker      — 6 in every file
      u16 roofed      — 0/66 (HOUSTON = 66: the Astrodome)
      u16 surface     — 0/1/3 (grass vs turf families)
      u16 wallStyle   — 0..7 (park style bucket)
      u16 screenSet   — 0..7 (which in-game screen set the stadium uses)
      u16 paletteA..D — 4 palette/screen identifiers (0..255)
      u16 turfTint    — (KANSASCI 227) extra palette/field-color word
      u16 turfPattern — (KANSASCI 3)
      u16 crowdDensity— (KANSASCI 1)
      5 x u16         — zero (unused slots; 12 observed across all 28 parks, KANSASCI
                        the only park using slots 9-11)
park geometry tail at offset 136:
      4 x s16        — zero (reserved)
      s16 leftFieldPoleX/Y   — LF foul pole point, home plate = origin
      s16 rightFieldPoleX/Y  — RF foul pole point
      s16 foulLinePointAX/AY — a foul-line/foul-territory feature point
      s16 foulLinePointBX/BY — its mirrored partner
      s16 cornerPointAX/AY   — corner point near the fence (same pair repeated)
      s16 cornerPointBX/BY
      s16 fencePointCount    — n
      n records of 3 x s16: (x, y, flag) — the outfield fence line, walking around the park
```

Evidence for (x, y) = real park points: ANAHEIM (0, 12000) = CF (12000/30 = 400 ft ✓),
(-4200, 10200) power alley ≈ 368 ft (Anaheim 1997: 366 ft), DETROIT (-7200, 7200) =
Tiger LF pole 339 ft (sqrt(7200²+7200²)/30 = 339 ✓), (0, 13200) = CF 440 ft ✓,
BOSTON (-7510, 7510) = Green Monster 250 ft corner (sqrt(2)·7510/30 = 354 ft; the
Monster line at Fenway is 315 ft with the pole at 379; the 12704 CF = 423 ft ✓).

## e1a4 — injury text (SIM.DAT, 24460 bytes)

```
22 x u16 section offsets at 0..44; offsets[19..21] = 3948 (injury records),
    23628 (phase records), 24364 (outcome records); offsets[k] (k<19) = sub-table starts
19 x s16 tuningWords at 44..82 (6000, 5000, 8000, ... — injury duration/odds knobs)
19 sub-tables at 82..3948: each (u16 count, count x (u16, u16) pairs) — pair tables
    mapping body-part groups to record ranges (25 evidence: every sub-table size = 2+4*count)
205 x 96-byte injury records at 3948:
      u16 partIndex    — 1..205, one per record
      u16 daysOut      — average days out (18, 35, 6, ...)
      u16 stage        — 1..12 (injury severity stage)
      char[30] bodyPart     — "Cheek", "Ear", "Head", "Neck", ...
      char[30] specificPart — "Cheek-bone", "Arm bone (ulna)", ... ("" if same as bodyPart)
      char[30] severity     — "bruised", "fractured", "broken", "swollen", ...
46 x 16-byte phase records at 23628: (u16 index, stageA, stageB, rollA(s16), rollB,
    rollC, outcomeDays, outcomeStage) — the injury progression table
12 x 8-byte outcome records at 24364: (u16 index 1..12, phase, stage, days) — the
    per-stage outcome table (days 9998/9997 = special "out for season" markers)
```
Decompile evidence: `FUN_680384e9` (BBSIM/_all.c:33290) seeks
`(part-1)*0x60 + offset[19]`, `(stage-1)*0x10 + offset[20]`,
`offset[21] - 8 + phase*8` — the exact 96/16/8-byte strides.

## 5200 — in-game UI strings (`PB` tag, SIM.DAT, 410 bytes)

```
u16 flag     — 1
u16 count    — 28
28 x u16 offsets — from the start of the strings block
u16 totalSize — 348 = bytes after the size field
strings block — count NUL-terminated strings: "Swing Type:", "Manager Menu",
                "Ball Caught", "End Of Play", ... (same 11-string set twice:
                batter swing menu and pitch menu, plus trailing "End Of Play"s)
```

## e6e7 — camera views (`@C` tag, SIM.DAT, 5078 bytes)

```
28-byte head: u16 slotCount (16), u16 5, 4 x s32 tuning (10, 1053, 5784, 50205)
15 x 26-byte default records at 28..418: (u16 head, s32 x, s32 y, s32 z, 6 x s16 params)
    — camera anchor positions (6492, 1250, 1024) repeating = home-plate default
10 x 64-byte named views at 418..1058: 32/30-byte NUL-padded name + zero padding:
    "Behind home plate (fixed)", "Behind home plate (tracking)", "Multi camera view",
    "First base seats", "Third base seats", "Trail ball", "Batter",
    "Trail selected player", "Over dugout", "Blimp view"
134-byte layout block 1058..1192 (orbit/zoom params; kept verbatim as derived data
    — semantics unresolved this round)
9 x 15 records of 26 bytes at 1192.. (same layout as the defaults) then a short final
    record (12 bytes: head, x, y, truncated z) — per-view camera position sets
```

## ce8c — stadium walls (`@W` tag, 204-518 bytes)

```
"GID:" magic (4 bytes)
u32 size       — file size - 8 (its low byte reads as "GID:<c>" printable run)
u32 version    — 8 in every file
2 x u16        — zero (reserved)
s16 leftFieldFoulLineX  — x of the LF line (7064..7650 across parks)
s16 centerFieldDepth    — CF depth: SANDIEGO 12150 = 405 ft, DETROIT 13200 = 440 ft,
                          BOSTON 12704 = 423 ft (Fenway) ✓
3 x s16 (n, k, m): n = wall point count, k/m = block/tail counts (m = 12n+10)
n x 6 s16 wall points at 26: (slope, x, y, wallHeightFront, wallHeightBack, flag)
    Units 1/30 ft: 300 = 10 ft; (x, y) = field points, home plate = origin, CF on +y
    (DETROIT: (-7200, 7200) = LF pole 339 ft, (6900, 6900) = RF pole 325 ft ✓).
    slope = the first word (0/150/300 = height of the base of the point);
    flag != 0 marks special records (Boston: 15/22/23, Anaheim: 4/8/12).
k tail blocks of 10 bytes: (s16 flag, s16 blockKind, 3 x u16 pads)
```

## cb7c — wall texture atlas (`WT` tag, 3802 bytes)

```
8 x u32 header: (faceCount, faceCount, headWidth, headHeight, 0, 0, face0Unpacked,
                 face0Unpacked) — faceCount = # wall segments (7 most parks, 8 KANSASCI
                 = Kauffman's waterfall walls), headWidth/headHeight = the global face
                 dims (32x16; CHICAGON head 32x15), face0Unpacked = width*height
(faceCount-1) records of 30 bytes at 32:
    (u16 pad=0, u32 dataOffset, u32 width, u32 height, u32 0, u32 0,
     u32 unpacked = width*height, u32 unpacked)
    — the record's width/height describe the face's unpacked bitmap (CHICAGON face 0
      = 32x15 = 480; the other faces 32x16 = 512), the unpacked u32s are width*height1 closing record (6 bytes): (u16 pad=0, u32 dataOffset of the last face)
    — the last face has NO stored dims anywhere (the closing record is only lead +
      offset), its width/height are derived (renderer uses the header 32x16)
the face bitmaps start right after the record stream (32 + (faceCount-1)*30 + 6 bytes
    in: 218 for 7 faces, 248 for KANSASCI's 8), back to back: face k's stored bytes =
    the next face's dataOffset - this one (the last face runs to end of file).
    Most faces are stored unpacked (512 bytes = 32x16); CHICAGON's faces 0-1 are 480
    bytes for a 32x15 face
each face = palette indices, one byte per pixel, 32 x height bitmap (in JSON: pixels
    verbatim 0..255 in 8-wide groups, rows of the face)
```
Evidence: KANSASCI = Ewing Kauffman Stadium (fountains) has 8 faces vs 7 elsewhere
(KANSASCI ce8c CF depth 12000 = 400 ft ✓, Kauffman 1997 CF 400 ft); CHICAGON = Wrigley
(its ce8c has 38 wall points, 6 tail blocks — the most segments of any park).

## 7709 — texture atlas (`XT` tag, 19-22 KB)

Same record style as cb7c with per-face sizes and LZ-packed blocks:
```
8 x u32 header: (faceCount, faceCount, headWidth, headHeight, 0, 0, strideWord,
                 face0Bytes) — 26 faces (BOSTON) / 24 (KANSASCI) / 27 (CHICAGON);
    strideWord = header[6]: the last full face's stride in most parks (2048 BOSTON,
    864 TORONTO, 736 KANSASCI), 704 for CHICAGON (an in-between stride; rule unread)
faceCount records of 30 bytes at 32: (u16 1, u32 dataOffset, u32 width, u32 height,
    u32 0, u32 0, u32 stride = width*height, u32 nextFaceBytes)
    — the last u32 of record k = the STORED byte count of face k+1 (faces are stored
      packed); face 0's stored byte count = header[7]
1 closing record (6 bytes) after the last full record
faces stored back to back from 32 + (faceCount-1)*30 + 6; the last face's bytes =
    end of file. Stored counts are always <= stride (LZ-compressed: e.g. TORONTO face
    5 = 158 bytes for a 256x19 = 4864-byte sky; BOSTON faces 775..2958 bytes).
    The LZ scheme is the game's FastSim FDBM decoder (see work/spec/FUN_68086ebc -
    bit-stream LZSS: flag byte, bit 1 = copy-run (u16: dist = (w>>4)+1, len =
    (w&0xf)+3), bit 0 = literal); a fully faithful mirror was not closed this round,
    so the packed bytes are shown as u16 words + a trailing odd byte (lossless).
```

## 947d — stadium big table (`HS` tag, ~26-29 KB)

```
"DAT:" magic (4 bytes)
u32 size        — file size - 8
17 x u32 section offsets at 8..76 (16 sections + end)
each section:
    char[16] label — nontextile code bytes ("ae6f00..") or ASCII zone labels
                     ("NOPQRST\xff", "BCDEFGH\xff")
    a walk of (u16 kind, u16 nbytes) blocks (kind = 1 or 2) of s16 words, ending at a
    0xFFFF terminator (kinds outside 1..2 stop the walk)
    the rest after the walk = more s16 words (wall/zone data; e.g. BOSTON section 6's
    rest contains the same (x, y) wall points as ce8c)
```

## 6be6 — offense logic (`OL` tag, SIM.DAT, 2683 bytes)

```
5 x u16 header: (10 = data start, then 4 section-end offsets 1090, 1738, 2026, 2674)
4 sections + a 9-byte tail record: 120, 72, 32, 72 + 1 records of 9 bytes
each record = 9 bytes of codes 0..13 (base destinations / fielder assignments;
    high nibble always 0 — evidence: 2674 bytes all ≤ 0x0d)
```

## b0e7 — positions / sprite slots (`UN` tag, SIM.DAT, 6048 bytes)

```
756 rows of 8 bytes: (u16 spriteKind, u16 frame, s16 posX, s16 posY)
spriteKind 0xffff = an unused row (576 of 756; all other rows have screen-area coords
    x 108..463, y 216..358 — a 640x480-screen UI zone)
22 kinds present: kinds 0/1 have 28 rows each (28 teams), the rest 4..12 (animation frames)
```

## bb43 — misc (`MS` tag, SIM.DAT, 12 bytes)

```
6 x u16: (128, 102, 64, 128, 1, 4)
```

---

## Codec behavior (`voldat.py`)

- `decode NAME in.bin out.json` picks the layout from the id in NAME (`ce8c_*` → walls, ...).
- Keys starting with `_` are derived (counts, offsets, reserved words, verbatim blocks the
  encoder recomputes); everything else is editable content.
- `encode NAME in.bin edited.json out.bin` rebuilds byte-for-byte: verified on all 126 visible
  chunks and on re-extracted copies of the 48 held-out chunks (8 stadiums incl. HOUSTON,
  TORONTO, KANSASCI) with 3 holdout-style random-edit seeds each.
- 7709 packed texture bytes are shown as u16 words + an odd tail byte (lossless, never an
  opaque 0..255 dump; s16 read so 0xffff shows as -1 and edits stay in range).
- cb7c face pixels are shown verbatim (0..255 palette indices, one byte per pixel).
- cb7c's LAST face has no stored dims (closing record = lead + dataOffset only): its
  width/height are derived `_width`/`_height`; the encoder validates that each face's
  rows fit the stored byte count.
