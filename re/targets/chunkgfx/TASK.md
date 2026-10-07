# Task: a decode/encode codec for the compressed graphics inside SIM.DAT and Stadia/*.DAT (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
SIM.DAT and the 28 stadium files are tagged-chunk containers (solved: `/home/will/bbpro98/work/chunkdat.py`). Their raw
images are solved too (38-byte header `u32 frames=1, u32 1, u32 w, u32 h, u32 0, u32 0, u32 w*h, u32 w*h, u32 flags`,
`u16`, then w*h palette indices). Three kinds of chunk are still opaque and are staged one chunk per file in
`/mnt/nvme/bbpro98/targets_data/chunkgfx/` (read only; `index.json` lists them by kind):
- `SCR:` full screens (640x480 overlays, e.g. `SIM_28_OL.bin`): magic `SCR:`, sizes, then compressed rows.
- Multi-frame bitmaps (`*_RG`, `*_JS`, `*_KS`, `*_WT`, `*_XT`): same 9-u32 header but frames > 1, followed by per-frame
  headers (width, height, raw size, compressed size, flags) and compressed streams.
- `FNT:` bitmap fonts (`SIM_00_X_`, `SIM_05_IB`, `SIM_07_PB`, `SIM_25_AG`, `SIM_39_NR`... see index.json).
Palettes are the `PAL:` chunks (16-byte header + 768 RGB bytes); `sim.pal` there is the SIM.DAT field palette as a RIFF
PAL for the audit sheets.

## Goal
Write `$LANE/codec.py` (Python 3 stdlib only, under 120 KB):
```
python3 codec.py decode in.bin out/   -> out/manifest.json + one raw file per frame (w*h bytes, 8-bit palette indices)
python3 codec.py encode out/ in.bin   -> rebuilds the original chunk byte for byte from out/ alone
```
`manifest.json` = `{"frames": [{"w": int, "h": int, "file": "f0000.bin", ...}], "palette": optional 256 [r,g,b], "meta": {small}}`.
For a font, each glyph is a frame (1-bit glyphs expand to one byte per pixel, values 0/1 or palette indices).

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/imgref.py /home/will/bbpro98/re/targets/chunkgfx $LANE [--files A,B] [-v]`
It runs your codec in a jail and checks per file: decode works; encode(decode(x)) == x byte for byte; painting a 4x4
block in the largest frame survives encode + decode with every other frame unchanged; decoded size >= 0.9 x the input;
frames look like art (>= 35% of horizontally adjacent pixels equal). Font files need decoded size >= 2 x the input
(their glyphs are 1-bit packed). PASS = all primary files. Then a vision model
judges contact sheets of your frames (garbage = fail).

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document every format in `$LANE/FORMAT.md` (headers, compression, evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `codec.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/chunkgfx/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified. The DBM sprite
lanes in `/home/will/bbpro98/re/targets/dbm/lanes/` work on a related "crushed bitmap" format; read their notes too.
