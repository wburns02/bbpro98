# Task: a decode/encode codec for the front-end shell graphics BMX and FNX (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
The menu shell draws its UI pieces and text from two custom formats that no tool reads yet. They are staged read only in
`/mnt/nvme/bbpro98/targets_data/shellgfx/`:
- `MENUBRS.BMX` (5 KB), `STADIA.BMX` (57 KB): multi-bitmap files. Both start with a directory; entries look like
  `u32 offset, u16 w, u16 h, u16 ?` and the first offset equals the directory size (0xf0 in MENUBRS, 0x46 in STADIA:
  320-pixel-wide stadium banners). The bytes between offsets are fewer than w*h, so the pixels are compressed.
- `0.FNX` .. `5.FNX`: bitmap fonts. Magic `FNX:`, a small header (e.g. `03 00 0c 0b 07 20 60 11 00 ...`: glyph
  height, first/last character?), then a u16 offset table per glyph and glyph data. In `4.FNX` the glyphs are 11 bytes
  apart at height 11, i.e. one byte per row (1 bit per pixel). `5.FNX` is a large font and may use more bits per pixel.
`bb0.pal` there is the shell palette (RIFF PAL) used for the audit sheets. (The shell's PCX art is standard 8-bit PCX
and already solved; `MU0.PLX`/`MU1.PLX` are plain 768-byte RGB palettes.)

## Goal
Write `$LANE/codec.py` (Python 3 stdlib only, under 120 KB):
```
python3 codec.py decode in.bin out/   -> out/manifest.json + one raw file per frame (w*h bytes, 8-bit palette indices)
python3 codec.py encode out/ in.bin   -> rebuilds the original file byte for byte from out/ alone
```
`manifest.json` = `{"frames": [{"w": int, "h": int, "file": "f0000.bin", ...}], "palette": optional 256 [r,g,b], "meta": {small}}`.
Each BMX bitmap is a frame. For a font, each glyph is a frame (1-bit glyphs expand to one byte per pixel, values 0/1
or palette indices); put the character code in the frame entry.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/imgref.py /home/will/bbpro98/re/targets/shellgfx $LANE [--files A,B] [-v]`
It runs your codec in a jail and checks per file: decode works; encode(decode(x)) == x byte for byte; painting a 4x4
block in the largest frame survives encode + decode with every other frame unchanged; decoded size >= the input size
(fonts 0-4: >= 2 x, font 5: >= 1.2 x); frames look like art (>= 35% of horizontally adjacent pixels equal).
PASS = all eight files. Then a vision model judges contact sheets of your frames (garbage = fail), and so does Claude.

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document every format in `$LANE/FORMAT.md` (headers, compression, evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `codec.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/shellgfx/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified. The SIM.DAT
graphics lanes in `/home/will/bbpro98/re/targets/chunkgfx/lanes/` decode a related `FNT:` font and compressed bitmaps;
read their notes too.
