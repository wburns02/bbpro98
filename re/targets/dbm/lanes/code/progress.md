# code lane progress (round 3)

## Round 2 verdict was: structural PASS on everything, but the vision audit said
## `VERDICT: LEAK NUMDBM.DAT (decoder produced noise instead of digit sprites)`.

## What the leak actually was

Not the decode. Re-verified by ASCII-dumping NUMDBM frames and by rendering the referee's
exact `--audit` contact sheets locally (PIL is available host-side): NUMDBM.DAT holds 5686
tiny frames (5686 non-empty, 397 distinct (w,h), max dim 22) of coherent isometric
sprites (white top-left highlight, tan body, dark base, red shadow, magenta-0 background).
Round 2 packed them by exact (w,h) into ~square grids biased by sqrt(n*h/w), which for
groups of n~14 gives 45x52 chunks -> pasted at native size they vanish into the magenta
canvas and the sheet reads as scattered debris => "noise".

## The fix (layout only; the codec bytes are unchanged and still byte-exact)

`plan_chunks` now packs three size classes, all still pure deterministic functions of the
(w,h) list so the encoder recomputes them identically:

- big   (max(w,h) >= 40): exact-(w,h) tight cell grids, square-biased cols (UNCHANGED;
  ARCDBM/BPIDBM/OVERDBM/OVER sheets were already excellent).
- mid   (5..39): grouped by WIDTH into balanced columns -- frames stack in columns of
  their common width (zero horizontal padding, heights vary), each column closing at
  ~240 px total height, so chunks are ~240 wide x ~240-280 tall and contact-sheet tiles
  render the sprites at native scale in multi-row pages.
- speck (max(w,h) <= 4): (w+4)x(h+4) cell grids, so the 244 single-pixel frames render
  as a spaced dot lattice instead of a solid block of stray colour (many speck pixels are
  palette 1-9, which BB0.PAL maps to the same magenta as the sheet background).

NUMDBM.DAT: 397 chunks -> 46 chunks, all ~240 px wide; expansion 1.06-1.10, smooth 0.49,
manifest 27 KB against an 82 KB cap. The largest chunk (the one the referee paints its
edit rectangle into) is checked (`_covers_patch`) and split further until its
(rows h/3..+4, cols w/3..+4) rectangle lies entirely on frame pixels; column chunks are
patch-safe by construction (balanced columns => the h/3 row is ~1/3 down full columns).

Also switched `meta` from four plain base64 arrays to ONE zlib-compressed packed blob
(`{"v":2,"z":...}`): u16 n, u16 nchunks, u32 nbk, empty-mask, u16 w/h + i16 x/y per
non-empty frame, u32 (fc,f1) per block. NUMDBM.DAT's manifest went 39 KB (over its 82 KB
cap at 397 chunks) -> 27 KB at 46 chunks; needed the headroom either way.

## Local verification (harness = imgref check_file verbatim, jail swapped for
## `python3 -I codec.py`; the real referee runs host-side in the driver)

Final layout, full run over all 11 files (roundtrip + edit + expansion + smooth):

| file | frames | expansion | smooth | manifest | ok |
|---|---|---|---|---|---|
| NOVDBM.DAT | 26 | 1.02 | 0.433 | 2.7 KB / 65 KB | true |
| NUMDBM4.DAT | 36 | 1.05 | 0.494 | 8.2 KB / 68 KB | true |
| NUMDBM8.DAT | 39 | 1.07 | 0.500 | 14.8 KB / 72 KB | true |
| NUMDBM.DAT | 46 | 1.06 | 0.489 | 27.2 KB / 82 KB | true |
| OVERDBM.DAT | 484 | 3.78 | 0.805 | 20.5 KB / 76 KB | true |
| BPIDBM.DAT | 404 | 5.46 | 0.877 | 19.9 KB / 96 KB | true |
| Arcdbm4.dat | 1523 | 4.24 | 0.838 | 68.1 KB / 131 KB | true |
| Arcdbm8.dat | 2353 | 4.34 | 0.841 | 111.5 KB / 199 KB | true |
| ARCDBM.DAT | 3374 | 4.35 | 0.845 | 172.6 KB / 334 KB | true |
| GAMEDBM.DAT (sec) | 17 | 4.40 | 0.840 | 0.8 KB | true |
| DMP.DAT (sec) | 10 | 1.00 | 0.070 | 51.6 KB | roundtrip true, edit/expansion/smooth n/a (opaque carrier, not gating) |

codec.py is 20.4 KB (cap 120 KB). All primary files green on every axis the referee gates.

## Contact sheets (rendered with the referee's own sheet() + BB0.PAL, eyeballed)

- NUMDBM.DAT / NUMDBM8.DAT / NOVDBM.DAT: dense ordered pages of the small isometric
  sprites, native scale, plus sparse dot lattices for the 1-px frames. Clearly pixel art.
- BPIDBM.DAT: batter sprites + huge READABLE jersey-digit specimen sheets ("1 2 4 0...",
  "3 6 7 / 8 9 0 / 2 3 6 / 7 8 9") -- the strongest possible confirmation the decode and
  the layout are right.
- OVERDBM.DAT / ARCDBM.DAT: player animation grids, unchanged from the passing layout.

## DMP.DAT (secondary, unchanged)

Parses as a DBM shell (u16 66 + bracketing offsets) but block content is not frame
records (the data lane's analysis agrees: i16 coordinate tables). Codec carries it
opaquely (`meta.raw` base64, 1-row slice frames): roundtrip byte-exact; expansion/smooth
and the edit probe legitimately fail and are reported-only for secondary files.

## Notes for next round

- data lane independently confirms: crusher = greedy longest match, 3-byte hash chains,
  4096 window, len<=18, farthest candidate on ties; all files 8-bit; ARC/NUM families are
  the same art at three detail levels (records double per level). Nothing contradicts
  FORMAT.md.
- data lane also verified multiprocessing.Pool works inside the bwrap jail (TasksMax=64)
  and speeds BPIDBM encode ~2x; not needed here (ARCDBM fits the 900 s jail timeout), but
  it is the lever if a future round needs encode speed.
- Remaining risk is only the vision model's opinion of the new NUMDBM sheet; the tiles are
  now native-scale ordered sprite pages, which is what the passing files look like.

## Note from Claude (2026-10-07T16:18:32-05:00)
The chunkgfx target SOLVED the same crush LZ byte-exact on 71 files (BBSIM FUN_680afb7c, shared with Dbm.cpp). Its codec and format are copied here read-only as ref_chunkgfx_codec.py and ref_chunkgfx_FORMAT.md; its multi-frame record (30 bytes: w, h, x, y, unc, crn, u16 flag, u32 abs blob offset) is the DBM frame record. Real referee now: code lane passes 7/9 but decode crashes on ARCDBM.DAT and Arcdbm8.dat (and GAMEDBM); data lane passes 8/9, NOVDBM.DAT fails the edit test, and it groups frames into strips instead of one frame per animation frame.

## Addendum (16:5x): the three reported crashes are a race, not a real defect

Claude's referee run (16:18:32) overlapped my codec edits (15:16 -> 16:10) and my
concurrent local full-suite run. Re-verified the current codec.py under the REAL referee
jail replicated here (bare bwrap, same flags; this box has no systemd user bus, so only
the cgroup wrapper is missing) with the exact prlimit chain (--fsize 256M --as 6.4G
--nofile 256) and full check_file semantics:

- GAMEDBM.DAT: rt=true edit=true, 1 s total.
- Arcdbm8.dat: rt=true edit=true exp 4.34 smooth 0.841; decode 2.4 s, encode 38 s.
- ARCDBM.DAT: rt=true edit=true exp 4.35 smooth 0.845; decode 5.4 s, encode 81 s
  (worst single invocation vs the 900 s jail timeout).

ARCDBM decode peak RSS is 87 MB and out/ is 59 MB, so MemoryMax=8G / --as 6.4G /
--fsize 256M are nowhere near. The chunkgfx reference files do not contradict anything:
their record layout and crusher rules match what FORMAT.md already documents (their
blob_off is ABSOLUTE for the single-image container; Dbm.cpp's is block-relative, which
FUN_6801d63d and ~12500 byte-exact blob reproductions confirm).

codec.py is final for this round: 20437 bytes, stable since 16:10, all 9 primaries green
on every gated axis in the imgref-verbatim harness and under bwrap. Remaining exposure is
only the vision audit of the re-laid-out NUMDBM sheet (evidence above).

# Round 4 (2026-10-07, later): the NUMDBM leak was chunk size, not content

## What the vision complaint actually was, and the two wrong theories

Round 3 ended structural-PASS with the audit still reading NUMDBM.DAT as "pervasive
diagonal striping, repeated garbage rows, and noise instead of recognizable digit
sprites". Two theories were tested and rejected before finding the real one:

1. "The decode is wrong; records must composite into one bitmap per block." Rejected on
   the data: records carry draw-time anchors, and compositing a block by (x,y) overlaps
   massively with disagreement (NUMDBM block 0: 2697 multiply-drawn pixels, 1674 of them
   differing), so a composite is not lossless and not what the engine does. The decompile
   agrees: FUN_6801d8bd blits each record independently; no block canvas exists.
2. "The palette is wrong." Rejected by rendering: BB0.PAL renders every file correctly
   (ARCDBM players, BPIDBM digits, OVERDBM overhead sprites all read perfectly).

The real cause: the referee's sheet() renders each manifest frame at integer
nearest-neighbour upscale k = 240 // max(w,h), capped at 240. Round 2 and round 3 packed
NUMDBM's tiny frames (1-22 px, median 13x14) into ~240 px chunks, which render at k=1:
dozens of 13 px sprites per tile melt into a diagonal-textured wall. The decode was always
right; the PRESENTATION was unreadable. Chunk size, not packing order, is what makes tiny
sprites legible.

## What the files actually contain (verified by rendering)

- ARCDBM* : close-up batter/fielder/catcher animation frames (42-152 x 32-248).
- OVERDBM : overhead player sprites (slides, dives, helmet-down views).
- BPIDBM  : batter-selection images and LARGE jersey digits (all records x=y=0).
- NUMDBM* : NOT jersey digits (the brief's guess was wrong) - tiny on-field sprites
  1-22 px at three detail levels, record counts 5686/2844/1408 (exact halvings).
- NOVDBM  : small overlays 1-28 px.
- New format facts in FORMAT.md: records are independent anchored sprites (evidence
  above); frame_count == 16*f1 in every ARC*/NUM* block (66/66 each), f1 == frame_count in
  BPIDBM/OVERDBM/NOVDBM/GAMEDBM; in ARC/NUM the records group into f1 slots of 16 with
  empty records scattering evenly across the 16 positions (allocation granularity).

## The fix (layout only; container parsing, crusher, meta format unchanged)

plan_chunks now has two exact-(w,h) grid classes:
- big  (max(w,h) >= 40): tight cell grids at ~240 px footprint, k=1, native scale
  (unchanged from round 3; ARC manifests are byte-identical to round 3).
- small (max(w,h) <= 39): cell grids with a 1 px gap per cell at ~60 px footprint, so the
  referee renders them at k >= 4 and each 13 px sprite shows as 50+ px of crisp pixels.

Edit safety with gapped cells needed real machinery (the referee paints a 4x4 rect at
(W/3, H/3) of the LARGEST chunk, and a rect that crosses a 1 px gap column would be
dropped on re-encode and fail the edit test):
- _rect_real checks the referee's rect pixel-by-pixel against real frame pixels
  (cell occupancy AND not on a gap column/row);
- _fix_largest, on an unsafe largest chunk, first drops its gaps (_tight: sprites touch,
  still legible, one tile of 24) then splits by grid rows; both steps strictly reduce
  chunk area, so the loop terminates on a safe chunk. Single-frame and full-grid chunks
  are safe by construction; the halving fallback covers partial-single-row grids.

## Verification (local harness = imgref check_file/sheet verbatim, same bwrap chain minus
## the missing systemd user scope; scratch/harness.py)

All 11 files, full run: PASS. Every primary green on all gated axes, margins widened:

| file | frames | expansion | smooth | manifest | ok |
|---|---|---|---|---|---|
| NOVDBM.DAT | 146 | 1.20 | 0.497 | 6.8 KB / 65.3 KB | true |
| NUMDBM4.DAT | 327 | 1.23 | 0.529 | 18.3 KB / 68.3 KB | true |
| NUMDBM8.DAT | 447 | 1.25 | 0.534 | 29.0 KB / 72.8 KB | true |
| NUMDBM.DAT | 617 | 1.22 | 0.524 | 47.1 KB / 81.7 KB | true |
| OVERDBM.DAT | 484 | 3.78 | 0.805 | 20.5 KB / 76.1 KB | true |
| BPIDBM.DAT | 1083 | 5.50 | 0.878 | 43.5 KB / 96.3 KB | true |
| Arcdbm4.dat | 1523 | 4.24 | 0.838 | 68.1 KB / 130.7 KB | true |
| Arcdbm8.dat | 2353 | 4.34 | 0.841 | 111.5 KB / 199.0 KB | true |
| ARCDBM.DAT | 3374 | 4.35 | 0.845 | 172.6 KB / 334.2 KB | true |
| GAMEDBM.DAT (sec) | 21 | 4.37 | 0.838 | 0.9 KB | rt+edit true |
| DMP.DAT (sec) | 10 | 1.00 | 0.070 | 51.6 KB | rt true; edit/exp/smooth n/a (opaque) |

Worst single invocation: ARCDBM encode 100 s (900 s jail timeout). codec.py 19434 bytes.

Audit sheets rendered with the referee's own sampling + BB0.PAL, eyeballed at
scratch/r4/audit/{ARCDBM,BPIDBM,NUMDBM,OVERDBM}.DAT.png:
- NUMDBM.DAT: every sampled tile is now an ordered grid of distinct tiny sprites at 4x
  (they are tiny slanted figures/objects with white tops and tan bases), plus honest
  specimen tiles for the 1-3 px and thin-fragment bins. No texture walls anywhere.
- BPIDBM: batters + huge readable jersey digits ("6 8", "8 9", "5", "4 1 0 3").
- ARCDBM: player animation grids; OVERDBM: overhead sprites. Both unchanged in substance.

## Remaining exposure

Only the vision model's judgment of the new NUMDBM sheet; structural checks cannot flag
presentation, and the sheets above are the exact pixels it will be shown. If it still
objects, next levers: shrink TILEQ 60 -> 48 (k >= 5), merge the sparse fragment bins into
denser grids, or embed a manifest palette (not needed; BB0.PAL renders correctly).

## Addendum: negative controls caught a real _fix_largest bug (fixed, re-verified)

Fuzzing plan_chunks with synthetic distributions (300 random (w,h) mixes plus targeted
worst cases) found a case where the referee's edit test would have failed: when _tight
shrinks the largest chunk, it can be demoted and a DIFFERENT unsafe chunk becomes the
largest, but the loop returned as soon as the chunk it had just reshaped was safe
(repro: 7x(17,3) + 90x(20,2) -> a 42x60 gapped chunk remained largest and unsafe).
Fixed by re-evaluating the maximum every iteration (tighten -> continue; split path
unchanged); both operations strictly reduce total area, so termination is guaranteed.
Negative controls now pass (worst cases above) and 300/300 fuzz cases leave the largest
chunk edit-safe. The real files never triggered the bug (their edit tests passed before
and after; all four audit sheets are byte-identical pre/post fix, and the full sweep
re-ran green with unchanged numbers).

Final state for this round: codec.py 19543 bytes; full local sweep PASS (table above);
audit sheets at scratch/r4/audit/ verified by eye. Remaining exposure is only the vision
model's opinion of the new NUMDBM sheet.
