# Task: a lossless read/write codec for the DBM bitmap archives (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Goal
Write `$LANE/codec.py` (Python 3 stdlib only, under 120 KB) with two commands:
```
python3 codec.py decode in.bin out/    # writes out/manifest.json + one raw file per frame
python3 codec.py encode out/ in.bin    # rebuilds the container from out/ alone
```
`out/manifest.json` = `{"palette": [[r,g,b] x 256] (optional), "frames": [{"w": W, "h": H, "file": "f0000.raw"}, ...], "meta": {...}}`.
Each frame file is exactly W*H bytes: one 8-bit palette index per pixel, row-major, top row first. Put every non-pixel
field the encoder needs (offsets you cannot recompute, flags, hotspots, per-frame headers) in `meta` or in the frame
entries, but keep `manifest.json` small: it is capped at 64 KB + 2% of the input size, and `out/` may hold nothing but
the manifest and the listed frame files. Frames must be the real decoded pixels; the encoder must really re-compress
them, because the referee edits a frame and checks that the edit survives.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/imgref.py /home/will/bbpro98/re/targets/dbm $LANE [--files NUMDBM4.DAT] [-v]`
For every file it runs your codec in a jail (no network, no files except a copy of the input named `in.bin`) and checks:
decode works; `encode(decode(x)) == x` byte for byte; an edited frame survives encode+decode and nothing else changes;
decoded pixels expand the file (expansion >= 1.0) and look like pixel art (>= 35% of horizontal neighbours equal).
PASS = all primary files pass. Then a vision model looks at contact sheets of the frames (rendered with the game
palette `BB0.PAL` unless you supply one): noise or stripes fail. Use `--files` with the small files while developing;
ARCDBM.DAT is 13.5 MB, so make the codec reasonably fast.

## Files (read only): `/mnt/nvme/bbpro98/work_install/`
`ARCDBM.DAT` 13.5 MB, `Arcdbm8.dat` 6.75 MB, `Arcdbm4.dat` 3.34 MB (exact halvings: likely the same art at three
detail levels, or 16/8/4-bit variants), `NUMDBM.DAT`/`NUMDBM8.DAT`/`NUMDBM4.DAT` (same pattern; likely jersey
numbers), `BPIDBM.DAT` 1.6 MB, `OVERDBM.DAT`, `NOVDBM.DAT`, and secondary `GAMEDBM.DAT`, `DMP.DAT` (must round-trip,
may not be images). Palettes: `BB0.PAL` (RIFF PAL), `*.PLX` (768 bytes, likely 256 x RGB, maybe 6-bit).

## What is known (verify, do not trust)
- Header: `u16 count` (0x42 = 66 bitmaps for ARC/NUM/OVER/NOV/DMP, 0x48 = 72 for BPIDBM), then a u32 offset table
  starting at byte 2 (first entry 0x10e = 2 + 67*4 for count 66, so likely count+1 offsets with an end sentinel).
- The game engine is `BBSIM.dll`. Its decompile is `/mnt/nvme/bbpro98/index/BBSIM/_all.c` (+ `_functions.tsv`).
  The DBM code is the `.\BBSim\Dbm.cpp` module, roughly lines 17100-17850: `FUN_6801ea00` opens a DBM and checks the
  bitmap count ("Invalid number of bitmaps in DBM", "Could not open DBM file"); the decompressor ("uncrush") raises
  "DBMImage uncrush bug" / "Crushed DBM too large for vm buf" at lines ~17225-17440. The callers at lines ~1798-1810
  and ~10153 choose arcdbm4/8 vs arcdbm by a detail setting. Porting the uncrush routine exactly is the fastest route.
- Other modules nearby: `Anim.cpp`, `Actor.cpp`, `Batter2d.cpp` consume the frames (animation sequences, hotspots).

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (header, offset table, per-bitmap header, compression scheme, evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `codec.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/dbm/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
