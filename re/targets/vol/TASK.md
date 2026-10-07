# Task: a lossless read/write codec for the VOL archives (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Goal
Write `$LANE/codec.py` (Python 3 stdlib only, under 120 KB) with two commands:
```
python3 codec.py unpack in.bin out/   # out/manifest.json + one file per archive entry
python3 codec.py pack out/ in.bin     # rebuilds the archive from out/ alone
```
`out/manifest.json` = `{"entries": [{"name": "ShelPcx8\\SHELL01.PCX", "file": "e0000.bin"}, ...], "meta": {...}}`.
`name` is the entry's path inside the archive as stored (directory parts joined with a single backslash). Each entry
file holds exactly that entry's bytes (no directory or per-entry header bytes inside it; if entries have their own
headers, put those fields in the entry object or `meta`). `pack` must work for ANY entry sizes and for a removed
entry: recompute every offset, size and count. `meta` stays small (manifest capped at 64 KB + 1% of the input).

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/arcref.py /home/will/bbpro98/re/targets/vol $LANE [--files SHELL1.VOL] [-v]`
It runs your codec in a jail (no network, no files except a copy of the input named `in.bin`) and checks, per file:
unpack works; `pack(unpack(x)) == x` byte for byte; entries cover >= 95% of the file; at least as many entries as the
directory lists; every base name occurs in the file; every .PCX entry starts with 0x0A, every .WAV with RIFF;
growing the largest entry by 1037 bytes and deleting the smallest one survives pack+unpack with every other entry
unchanged. PASS = all primary files pass. Then a model audits the entry listing and your code.

## Files (read only)
`/home/will/bbpro98/BBPRO98_package/game/SHELL.VOL` (pristine, 30 entries: .DAT, .PCX, .REQ),
`/mnt/nvme/bbpro98/work_install/SHELL1.VOL` (41 PCX in `ShelPcx8\`), `/mnt/nvme/bbpro98/work_install/SHELL2.VOL`
(subdirectories `Misc\`, `ShelPcx8\`, ...; PCX + WAV). Secondary: `/mnt/nvme/bbpro98/work_install/SHELL.VOL` (a
modded rebuild of SHELL.VOL; must round-trip).

## What is known (verify, do not trust)
- Header: `VOLM`, u32 1, then u16 fields (`00 01 0a 00` in SHELL1, `00 02 10 00` in SHELL2), then a directory name
  ending in a backslash and NUL (`ShelPcx8\`), a u16 entry count (0x29 = 41 in SHELL1), a u32 offset (0x2e2), then
  per entry `NAME.EXT\0`, u16 (often 0x00ad), u32 offset. After the directory there are ~11 bytes before the first PCX
  header (`0a 05 01 08`), so entries or the directory may carry extra fields.
- The old extractor `/home/will/bbpro98/work/volx.py` is crude and misaligned (its entries start with leftover
  directory bytes) and crashes on SHELL2.VOL; do not trust its offsets.
- The game's reader is EZShell `Utility\Volume.cpp`: decompile `/mnt/nvme/bbpro98/index/EZShell/_all.c` near lines
  44900-45100.

## Tools and budget
- You are GLM-5.3-Flash. Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (header, directory and subdirectory records, entry records, evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `codec.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/vol/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
