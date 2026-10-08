# DMP.DAT: motion paths of FPS Baseball Pro '98 (BBSIM dmp.cpp / FastSim FDMP.cpp)

Evidence keys: `FUN_680xxxxx` = addresses in `/mnt/nvme/bbpro98/index/BBSIM/_all.c`;
`FS_ FUN_680xxxxx` = the FastSim twin in `/mnt/nvme/bbpro98/index/FastSim/_all.c`.
Data facts were measured on `/mnt/nvme/bbpro98/work_install/DMP.DAT` (38,424 bytes).

## 1. Container

    u16 path_count                      (= 66 in the shipped file)
    u32 file_offset[path_count + 1]     absolute byte offsets; offsets[0] = 2 + 4*(n+1);
                                        offsets[n] = file length
    path_count path blobs, blob i spanning offsets[i] .. offsets[i+1]

Loader `FUN_68024001` (this = manager `{int count; pathobj* array}`): reads the u16
count, aborts with "Invalid number of motion paths in DMP file" unless it equals the
expected 66 (the caller `FUN_680037a7` passes 0x42); reads the offset table with
`FUN_680af7ea`, then for each i seeks to `offsets[i]` (`FUN_680af8da`) and copies
`offsets[i+1] - offsets[i]` (masked 0xffff) bytes into path object i.
FastSim twin: FS_FUN_6801ccf1 (`s___FastSim_FDMP_cpp_6808e3f8`, same strings).

## 2. Path object (0xf86 = 3974 bytes)

Constructor `FUN_68023f28`: `_vector_constructor_iterator_(this+6, 0x3e, 0x40,
FUN_68024340)` = 64 frame elements of 0x3e = 62 bytes after a 6-byte header, then
`*this = 0` (keyframe_count = 0).

| offset | type | meaning |
|-------:|------|---------|
| +0 | u16 | keyframe_count (read back by `FUN_680060c0`; Sync.cpp iterates it) |
| +2 | u16 | header word A: read from the file, 0 in all 66 shipped paths; no reader found in either decompile |
| +4 | u16 | header word B: same status as A |
| +6 | 64 x 62 bytes | keyframes |

A path may hold 0 keyframes (path 24 ships empty; the blob is just the 6 header bytes).

## 3. Keyframe (62 bytes = 0x3e)

Frame constructor `FUN_68024340`: `_vector_constructor_iterator_(this, 6, 10, ctor)`
= array of 10 six-byte point objects, then a trailing u16 member set to 0.

| offset | type | meaning |
|-------:|------|---------|
| +0 .. +59 | 10 x (s16 x, s16 y, s16 z) | body points, order below |
| +60 (word 31) | u16 | keyframe_event_bits: 0x1 = catch, 0x2 = throw, 0x4 = tag |

`FS_FUN_68006270`/`FUN_680062c0` (FastSim) show a point is 3 s16 (negate all
three for mirroring); `FUN_680061e0(p, i) = p + i*6` indexes them.
Sync.cpp `FUN_680727c0` computes the keyframe address as `path + 6 + k*0x3e`,
and `FUN_68072730` / `FUN_68072760` / `FUN_68072790` AND the keyframe's trailing
u16 with 1 / 2 / 4 (shared bit-test helper `FUN_68002c20`: `(*p & bits) == bits`).
`FUN_68071312` then records:

| sync record offset | meaning | evidence |
|-------:|---------|----------|
| +0x00 | play id | |
| +0x04 | catch keyframe index, -1 if none | getter `FUN_68071493` errors "Invalid catch frame" |
| +0x08 | throw keyframe index | `FUN_680714e0`: "Invalid throw frame" |
| +0x0c | tag keyframe index | `FUN_6807152d`: "Invalid tag frame" |
| +0x10 | catch y - 60 clamped at 0 (scaled by `FUN_68002930`) | |
| +0x14 | catch y + 60 | catch window: y +- 0x3c |
| +0x18 | catch point (x,y,z) = point 2 of the catch keyframe | |
| +0x1e | throw point = point 1 of the throw keyframe | |
| +0x24 | tag point = point 2 of the tag keyframe | |

FastSim's FSYNC.cpp twin: FS_FUN_6805b4a8 (66 x 0x2a table) + FS_FUN_6805af32,
identical layout and point choices.

## 4. The 10 body points

The frame holds the endpoints of 5 rigid two-point segments: index i and i+5.
Pair lengths are constant across every keyframe of every path (measured sd ~ 1
unit over the whole file): (0,5) = 56.8, (1,6) = 33.7, (2,7) = 33.8,
(3,8) = 49.2, (4,9) = 49.5.

| index | name | evidence |
|------:|------|----------|
| 0 | pelvis (body root) | the mover stepper `FUN_68003c86` copies point 0's x and y into the mover at `+0x22`/`+0x24` each tick and negates the x under the mirror bit |
| 1 | throw hand | Sync.cpp stores point 1 as the throw position at throw keyframes |
| 2 | glove hand | point 2 is stored at catch and tag keyframes |
| 3 | throw-side foot | same x side as point 1 (see axis note) |
| 4 | glove-side foot | same x side as point 2 |
| 5 | head | far end of the rigid pelvis pair; highest rest height (~147) |
| 6 | throw elbow | rigid pair of point 1 |
| 7 | glove elbow | rigid pair of point 2 |
| 8 | throw-side knee | rigid pair of point 3, rest z ~ 50 (~1/3 of standing height) |
| 9 | glove-side knee | rigid pair of point 4 |

Left/right handedness is not decidable from the file (the engine's mirror bit
negates x at runtime: `FUN_68003c86`/`FUN_68003a26` negate the point x when
`FUN_68006410` = bit-test 1 fires), so sides are named after the hands
Sync.cpp identifies, not left/right. The throw-hand side carries positive x in
the shipped clips (mean x of point 1 > point 2 in 63 of the 64 non-empty paths;
paths 48/49 differ by < 2 units).

## 5. Axes and units

* z is height: feet sit at z ~ 0 (min -2, sensor noise), standing head ~ 147,
  max in file 263. Never meaningfully negative.
* y is the clip's forward axis: delivery/throw clips stride toward +y
  (path 0: both feet finish ~140 units forward of their start).
* x is across the player; the mirror bit flips it for the other handedness.
* Scale: ~1.2 cm per unit if the standing figure (head 147, feet 0) is a
  ~1.8 m player. Deriving exact world scale needs the renderer's transform,
  which is outside both decompiles' DMP readers.

## 6. Playback (who reads paths)

* `FUN_680063b0(manager, id)` returns `array + id*0xf86` (bounds-checked,
  fallback `DAT_680f86d8`); FastSim twin FS_FUN_68006360 (manager `DAT_6809f2c8`).
* Mover objects (e.g. the stepper `FUN_68003c86`) hold: path id `+0x1e`,
  active flag `+0x26`, step `+0x2a` (+1 forward / -1 backward, ping-pong at the
  ends), keyframe cursor `+0x2e` (s16). `FUN_68003fe3(mover, u16)` sets the cursor.
* `FUN_680060e0` / `FUN_68006210` / `FUN_68006310` read (and interpolate between)
  neighbouring keyframes' points; `FUN_68005d50` / `FUN_68006180` are point += / -=.
* Path index = animation slot id: the DMP load (`FUN_680037a7`) is followed by
  loads of arcdbm4/8, numdbm4/8, arcdbm, numdbm, overdbm, novdbm with the same
  expected count 66, and Sync.cpp (`FUN_68071888`, from `s___BBSim_Sync_cpp`) builds
  one 42-byte catch/throw/tag record per slot. Which play state picks which slot
  id lives in the play/animation data (numdbm), not in DMP.DAT itself.
* The sync consumer `FUN_68071a67` switches on base-out state (cases 5,6,10,13 /
  7,8,11,12 / 9 / 14 / 0x12) and compares the mover cursor against the sync
  getters (e.g. case 9: when `FUN_68006530() - 1 == cursor` it calls
  `FUN_68003f1b(6)`).

## 7. Shipped-file census

66 paths, keyframe counts 0..23, all header words A/B = 0.
Duplicates (byte-identical reuse): 0=9, 1=6, 3=10, 4=5, 7=8, 16=19, 20=38,
21=32, 26=29, 28=31, and 50=58, 51=59, 52=60, 53=61, 54=62, 55=63, 56=64, 57=65
(the 50..57 block is reused wholesale in 58..65).

| path | frames | catch kf | throw kf | tag kf | duplicate of |
|-----:|-------:|---------:|---------:|-------:|-------------|
| 0 | 10 | 4 | - | - | - |
| 1 | 3 | 2 | - | - | - |
| 2 | 9 | 5 | - | - | - |
| 3 | 9 | 5 | - | - | - |
| 4 | 10 | 4 | - | - | - |
| 5 | 10 | 4 | - | - | 4 |
| 6 | 3 | 2 | - | - | 1 |
| 7 | 7 | 5 | - | - | - |
| 8 | 7 | 5 | - | - | 7 |
| 9 | 10 | 4 | - | - | 0 |
| 10 | 9 | 5 | - | - | 3 |
| 11 | 12 | 5 | - | - | - |
| 12 | 6 | 5 | - | - | - |
| 13 | 8 | 4 | - | - | - |
| 14 | 12 | 4 | - | 8 | - |
| 15 | 9 | - | - | 6 | - |
| 16 | 7 | - | - | 3 | - |
| 17 | 10 | - | - | 0 | - |
| 18 | 9 | - | - | 3 | - |
| 19 | 7 | - | - | 3 | 16 |
| 20 | 12 | - | - | - | - |
| 21 | 7 | - | - | - | - |
| 22 | 1 | - | - | - | - |
| 23 | 7 | - | - | - | - |
| 24 | 0 | - | - | - | - |
| 25 | 14 | - | 8 | - | - |
| 26 | 7 | - | - | - | - |
| 27 | 14 | - | - | - | - |
| 28 | 11 | - | - | - | - |
| 29 | 7 | - | - | - | 26 |
| 30 | 3 | - | 2 | - | - |
| 31 | 11 | - | - | - | 28 |
| 32 | 7 | - | - | - | 21 |
| 33 | 1 | - | - | - | - |
| 34 | 10 | - | 5 | - | - |
| 35 | 9 | - | 4 | - | - |
| 36 | 11 | - | 4 | - | - |
| 37 | 12 | - | 6 | - | - |
| 38 | 12 | - | - | - | 20 |
| 39 | 12 | - | - | - | - |
| 40 | 7 | - | - | - | - |
| 41 | 10 | - | - | - | - |
| 42 | 11 | - | - | - | - |
| 43 | 1 | - | - | - | - |
| 44 | 1 | - | - | - | - |
| 45 | 7 | - | - | - | - |
| 46 | 9 | - | - | - | - |
| 47 | 10 | - | - | - | - |
| 48 | 9 | - | - | - | - |
| 49 | 11 | - | - | - | - |
| 50 | 19 | - | - | - | - |
| 51 | 7 | - | - | - | - |
| 52 | 6 | - | - | - | - |
| 53 | 8 | - | - | - | - |
| 54 | 23 | - | - | - | - |
| 55 | 18 | - | - | - | - |
| 56 | 1 | - | - | - | - |
| 57 | 17 | - | - | - | - |
| 58 | 19 | - | - | - | 50 |
| 59 | 7 | - | - | - | 51 |
| 60 | 6 | - | - | - | 52 |
| 61 | 8 | - | - | - | 53 |
| 62 | 23 | - | - | - | 54 |
| 63 | 18 | - | - | - | 55 |
| 64 | 1 | - | - | - | 56 |
| 65 | 17 | - | - | - | 57 |
