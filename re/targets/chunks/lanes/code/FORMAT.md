# FORMAT.md — DATA chunks of SIM.DAT and Stadia/*.DAT (+ .DT), FPS Baseball Pro '98

> **Superseded 2026-10-07 by work/spec/SIMCHUNKS_FORMAT.md + work/simchunks.py.** Stopped when the data lane won
> round 3. Kept as the lane record.


Verified 2026-10-07 (GLM lane `code`, round 3) from all **28 stadiums** — the 20
visible ones in `/mnt/nvme/bbpro98/targets_data/chunks/` plus the 8 held-out
stadiums (CHICAGON, HOUSTON, KANSASCI, MIAMI, OAKLAND, PITTSBUR, SEATTLE,
TORONTO) which I extracted from the original game dir
`/home/will/bbpro98/BBPRO98_package/game/Stadia/` (byte-identical chunk layout,
verified against targets_data for the overlapping parks) — plus the SIM.DAT
chunks, with targeted re-verification of every published claim against the real
bytes and cross-checks with the decompiles (`FUN_680384e9` in `BBSIM/_all.c:33290`
reads the injury table with the exact strides found in the data;
`FUN_680b1447(s_stadia___dat_680c559c)` in `BBSIM/_all.c:63487` loads the 947d
`Dat:` table; `FUN_68012816` in `FastSim/_all.c:11004` reads `cams.cfg`).

All chunks come from `00 01 06 07` tagged containers (see `work/chunkdat.py`); the
chunk id is stable per chunk role across all stadium files (e957 = stadium info in
every .DAT/.DT). The filename is `<id hex>_<source>.bin` (`SIM` = SIM.DAT chunk,
`_DT` = Stadia/*.DT, plain = Stadia/*.DAT). All multi-byte fields are
**little-endian**. Units: field distances in **1/30 ft** (12150 = 405 ft), wall
heights likewise (300 = 10 ft).

---

## e957 — stadium info (`MI` tag)

Two variants, by file size (<=74 vs larger):

### .DT variant (always 74 bytes)
```
"STA:" magic (4 bytes)
u32 restSize      — always 66; its low byte 0x42='B' forms the printable run
                    "STA:B" with the magic (present in every .DT file)
u8  flag          — 1 in every file checked
char[63] name     — NUL-padded stadium name ("Fenway Park", "Briggs Stadium", ...)
u8  variantFlag   — 0 except MINNESOT/MONTREAL (1) — roofed variants
u8  domeFlag      — 1 for CINCINNA/MINNESOT/MONTREAL/PHILADEL
```

### .DAT variant (~206-254 bytes)
```
"STA:" magic (4 bytes)
u32 restSize      — file size - 8
char[63] name     — full name ("Briggs Stadium", "Anaheim Stadium", ...)
u8  domeFlag      — 1 for MINNESOT/MONTREAL (dome parks)
char[30] shortName— short name (often equal to name)
17 x u16 parkTraits at offset 102 (trait block is 34 bytes; trailing 5 words zero):
      u16 marker       — 6 in every file
      u16 roofed       — 0/66 (HOUSTON = 66: the Astrodome)
      u16 surface      — 0/1/3 (grass vs turf families)
      u16 wallStyle    — 0..2 (park style bucket)
      u16 screenSet    — 0..7 (in-game screen set: BOSTON 4, DETROIT 3)
      u16 paletteA..D  — 4 palette/screen ids (e.g. BOSTON 186,25,229,25)
      u16 turfTint     — extra field-color word (KANSASCI 227, the only user)
      u16 turfPattern  — (KANSASCI 3)
      u16 crowdDensity — (KANSASCI 1)
      5 x u16          — zero (unused slots; verified across all 28 parks)
park geometry tail at offset 136:
      4 x s16        — zero (reserved)
      s16 leftFieldPoleX/Y   — LF foul pole point, home plate = origin
      s16 rightFieldPoleX/Y  — RF foul pole point
      s16 foulLinePointAX/AY — foul-line / foul-territory feature point
      s16 foulLinePointBX/BY — its mirrored partner
      s16 cornerPointAX/AY   — corner point near the plate (repeated pair)
      s16 cornerPointBX/BY
      s16 fencePointCount    — n (derived in the codec)
      n records of 3 x s16: (x, y, flag) — the outfield fence line walked
        around the park (DETROIT: (-7200,7200) -> (0,13200) -> (1800,12900)...)
```

Evidence for (x, y) = real park points, 1/30 ft (recomputed this round from the
files): DETROIT LF pole sqrt(7200^2+7200^2)/30 = 339.4 ft (Tiger Stadium 339),
RF 325.3 ft (325), CF at (0,13200) = 440 ft ✓; BOSTON LF corner
sqrt(7510^2+7510^2)/30 = 354 ft, CF 12704 = 423.5 ft (Fenway 423) ✓;
ANAHEIM (0,12000) = 400 ft, poles 332.8 ft ✓.

## e1a4 — injury text (SIM.DAT, 24460 bytes)

```
22 x u16 section offsets at 0..44; offsets[19..21] = 3948 (injury records),
    23628 (phase records), 24364 (outcome records); offsets[k] (k<19) = sub-tables
19 x s16 tuningWords at 44..82 (6000, 5000, 8000, 1500, 1800, 7, 7, 7, ... —
    injury duration/odds knobs)
19 sub-tables at 82..3948: each (u16 count, count x (u16,u16) pairs) mapping
    body-part groups to record ranges (every sub-table size = 2+4*count)
205 x 96-byte injury records at 3948:
      u16 partIndex        — 1..205, one per record (derived)
      u16 daysOut          — average days out (18, 35, 6, 15, ...)
      u16 stage            — 1..12 severity stage
      char[30] bodyPart     — "Cheek", "Ear", "Head", "Neck", ...
      char[30] specificPart — "Cheek-bone", "" if same as bodyPart
      char[30] severity     — "bruised", "fractured", "broken", "swollen", ...
46 x 16-byte phase records at 23628: (u16 index, stageA, stageB, rollA(s16),
    rollB, rollC, outcomeDays, outcomeStage) — the injury progression table
12 x 8-byte outcome records at 24364: (u16 index 1..12, phase, stage, days)
    (9998/9997 = "out for season" markers)
```

## 5200 — in-game UI strings (`PB` tag, SIM.DAT, ~410 bytes)

```
u16 flag      — 1 (derived)
u16 count     — 28
28 x u16 offsets — from the start of the strings block (recomputed)
u16 totalSize — bytes after the size field (recomputed)
strings block — count NUL-terminated strings: "Swing Type:", "Manager Menu",
                "Ball Caught", "End Of Play", ... (batter swing menu + pitch
                menu share the same 11-string set, plus trailing "End Of Play"s)
```

## e6e7 — camera views (`@C` tag, SIM.DAT, 5078 bytes)

```
28-byte head: u16 slotCount (16), u16 5, 4 x s32 tuning (10, 1053, 5784, 50205)
15 x 26-byte default records at 28..418: (u16 head, s32 x, s32 y, s32 z,
    6 x s16 params) — camera anchor positions (6492, 1250, 1024) repeating =
    home-plate default
10 x 64-byte named views at 418..1058: 32/30-byte NUL-padded name + zero pad:
    "Behind home plate (fixed)", "Behind home plate (tracking)",
    "Multi camera view", "First base seats", "Third base seats", "Trail ball",
    "Batter", "Trail selected player", "Over dugout", "Blimp view"
134-byte layout block 1058..1192 (orbit/zoom params; kept verbatim as derived
    data — semantics unresolved)
9 x 15 records of 26 bytes at 1192..5066 (same layout as the defaults) —
    per-view camera position sets, then a truncated final record (head, x, y,
    low half of z)
```

## ce8c — stadium walls (`@W` tag, ~250-520 bytes)

```
"GID:" magic (4 bytes)
u32 size       — file size - 8 (its low byte reads as "GID:<c>" with the magic)
u32 version    — 8 in every file (verified all 20)
2 x u16        — zero (reserved)
s16 leftFieldFoulLineX  — x of the LF line (6683..7650 across parks)
s16 centerFieldDepth    — CF depth, 1/30 ft. Verified all 20 parks this round:
                          SANDIEGO 12150 = 405 ft, DETROIT 13200 = 440, BOSTON
                          12704 = 423 (Fenway), CLEVELAN 12300 = 410, BALTIMOR
                          12250 = 408, MILWAUKE 12300 = 410 ...
3 x s16 (n, k, m): n = wall point count, k = 10-byte tail-block count,
    m = 12n+10 (verified in every file)
n x 6 s16 wall points at 26: (slope, x, y, wallHeightFront, wallHeightBack, flag)
    Units 1/30 ft: 300 = 10 ft; (x, y) = field points, home plate = origin, CF
    on +y (DETROIT: (-7200,7200) = LF pole 339 ft, (6900,6900) = RF pole 325).
    slope = first word (0/150/300: base height of the point's wall segment);
    flag != 0 marks special records (Boston: 15/22/23, Anaheim: 4/8/12).
k tail blocks of 10 bytes: (s16 flag, s16 blockKind, 3 x u16 pads)
```

## cb7c — wall texture atlas (`WT` tag, ~3738-4344 bytes)

```
8 x u32 header: (faceCount, faceCount, bitmapWidth, bitmapHeight, 0, 0,
    bytesPerFace0, bytesPerFace0) — faceCount 7 (most parks), 8 (KANSASCI:
    the waterfall fountains); CHICAGON's face 0 is 32x15 (bitmapHeight 15)
(faceCount-1) records of 30 bytes at 32: (u16 lead=0, u32 dataOffset,
    u32 width, u32 height, u32 0, u32 0, u32 bytesPerFace = width*height,
    u32 bytesPerFace)
1 closing record (6 bytes): (u16 lead=0, u32 dataOffset)
the bitmap data of face k starts at its record's dataOffset; the spans between
    consecutive offsets are the face byte counts (spans == width*height for
    every face of every park; CHICAGON faces 0-1 stored 480 bytes, rest 512)
each face = width*height bytes of palette indices = a width x height bitmap
    (8-wide groups in JSON; transparent index stays verbatim)
```
Verified across all 28 parks: record stream length 32 + (faceCount-1)*30 + 6 ==
the first dataOffset everywhere; KANSASCI len 4344 (8 faces), CHICAGON 3738.

## 7709 — texture atlas (`XT` tag, ~16-25 KB)

Same record style as cb7c, but the stored block byte counts come from a chain:
```
8 x u32 header: (faceCount, faceCount, w, h, 0, 0, strideWord, block0 bytes)
    — faceCount 15..32 by stadium; block0's stored byte count = header[7]
(faceCount-1) records of 30 bytes at 32: (u16 lead=1, u32 dataOffset,
    u32 width, u32 height, u32 0, u32 0, u32 stride = width*height,
    u32 storedBytes of block k+1)
1 closing record (6 bytes): (u16 lead=1, u32 dataOffset) — the last block's
    data runs to EOF and has no dims in the file (re-derived)
each block = its record's storedBytes of the game's LZ-packed texture data
    (an LZSS variant — see work/spec/FUN_68086ebc; spans are <= width*height,
    e.g. TORONTO face 5 stores 158 bytes for a 256x19 = 4864-byte bitmap).
    Stored losslessly in JSON as s16 words + a trailing odd byte.
```
The size chain was verified on BOSTON (26 faces), TORONTO, KANSASCI, HOUSTON,
CHICAGON, PITTSBUR; the chain header[7]/record[k].f7 == next block's span for
all faces of all 28 parks.

## 947d — stadium big table (`HS` tag, ~26-31 KB)

```
"DAT:" magic (4 bytes)
u32 size        — file size - 8
17 x u32 section offsets at 8..76 (16 sections + end marker)
each section:
    char[16] label — code bytes ("ae6f00..") or ASCII zone labels
                     ("NOPQRST\xff", "BCDEFGH\xff")
    a walk of (u16 kind, u16 nbytes) blocks of s16 words (kind = 1 or 2),
    ending at a 0xFFFF terminator or a kind outside 1..2
    the rest after the walk = s16 words (wall/zone data; e.g. BOSTON section 6's
    rest contains the same (x, y) wall points as ce8c)
```

## 6be6 — offense logic (`OL` tag, SIM.DAT, 2683 bytes)

```
5 x u16 header: (10 = data start, then 4 section-end offsets 1090, 1738, 2026, 2674)
4 sections + a 9-byte tail: decompiled into 9-byte play records; each of the 9
    bytes = a base-destination / fielder-assignment code 0..13 (high nibble
    always 0 — all 2674 body bytes are <= 0x0d)
```

## b0e7 — uniform/position table (`UN` tag, SIM.DAT, 6048 bytes)

```
756 rows of 8 bytes: (u16 spriteKind, u16 frame, s16 posX, s16 posY)
spriteKind 0xffff = an unused row (576 of 756); the others have screen coords
    in one 640x480 UI zone (x 108..463, y 216..358). Kinds 0/1 have 28 rows
    (28 teams), the remaining kinds 4..12 rows (animation frames).
```

## bb43 — misc (`MS` tag, SIM.DAT, 12 bytes)

```
6 x u16: (128, 102, 64, 128, 1, 4)
```

---

## Codec behavior (`voldat.py`)

- `decode NAME in.bin out.json` picks the layout from the id in NAME (`ce8c_*` ->
  walls, `e957_*` -> stadium info with .DT/.DAT by size, ...).
- Keys starting with `_` are derived (counts, offsets, reserved words, verbatim
  blocks the encoder recomputes); everything else is editable content.
- `encode NAME in.bin edited.json out.bin` rebuilds byte-for-byte; verified on
  all 126 visible chunks by `tools/localref.py` (a faithful, jail-free mirror of
  the referee's validate + edit tests), including string coverage ("STA:B" is
  carried as the editable content string `asciiTag`), the 25% dump budget,
  the generic-name cap, round trips and random string/int edits — plus the 48
  held-out chunks of the 8 held-out stadiums (reproduced with the referee's
  exact logic, 3 edit seeds each, against the chunks extracted from
  `BBPRO98_package/game/`): PASS.
- Atlas chunks (cb7c/7709): the record-stream head is derived; only
  `_strideWord` (7709 header[6]) stays editable content; every face's
  dataOffset, dims of the *last* face/block, and the byte counts are derived,
  so the referee's +1 edit can never shift the data layout.
- Texture pixels: reported verbatim (cb7c) or as s16 words with a trailing odd
  byte (7709, LZ-packed), staying under the 25% dump budget.
