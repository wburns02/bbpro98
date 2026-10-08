# Task: a semantic read/write codec for the data chunks of SIM.DAT and the stadium files (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
SIM.DAT and the 28 Stadia/<CITY>.DAT (+ .DT) files are `00 01 06 07` chunk containers (container codec done:
/home/will/bbpro98/work/chunkdat.py, read it). Images, palettes, fonts, screens and music inside them are solved.
What is left are the DATA chunks below: decoding them lets us change park dimensions, walls, cameras, injuries and
in-game texts. The files in /mnt/nvme/bbpro98/targets_data/chunks/ are those chunks, one per file, named
`<chunk id hex>_<source>.bin` (`_DT` = from the .DT file, `SIM` = from SIM.DAT).

| id | tag | where | what we know (verified by Claude) |
|---|---|---|---|
| ce8c | @W | each stadium | `"GID:" u32 len`, then s16 words: `8, 0, 0, 0, X, CF, n, k, m`, then n records of 6 s16 `(?, x, y, h1, h2, flag)`. Units 1/30 ft: CF = center-field depth (San Diego 12150 = 405 ft, Tiger Stadium 13200 = 440, Fenway 12704 ~ 423), (x, y) are field points with home plate at the origin and CF on +y (Tiger: (-7200, 7200) = LF pole 339 ft, (6900, 6900) = RF pole 325 ft); h1/h2 look like wall heights (300 = 10 ft); flag != 0 marks a few special records. |
| e957 | MI | each stadium .DAT (and .DT, 74 bytes) | `"STA:" u32 len`, stadium name twice, numbers (coordinates?) |
| 947d | HS | each stadium | `"DAT:" u32 len`, offset table + data, ~28 KB |
| cb7c | WT | each stadium | 3802 bytes, starts `7, 7, 32, 16` (u32) |
| 7709 | XT | each stadium | ~20 KB, starts `26, 26, 64, 32` (u32); may be a compressed or tiled image-like table |
| e6e7 | @C | SIM.DAT | camera views: "Behind home plate (fixed)", "Trail ball", ... |
| e1a4 | MI | SIM.DAT | injury table: "Cheek", "Cheek-bone", "bruised", "fractured", ... with an offset table |
| 5200 | PB | SIM.DAT | in-game UI strings: "Swing Type:", "Manager Menu", ... with an offset table |
| bb43 | MS | SIM.DAT | 12 bytes |
| 6be6 | OL | SIM.DAT | 2683 bytes, starts with an offset table |
| b0e7 | UN | SIM.DAT | 6048 bytes, repeating ffff pattern |

## Goal
Write `$LANE/voldat.py` (Python 3 stdlib only, under 300 KB; it runs alone in a jail, never import or open other
files):
```
python3 voldat.py decode NAME in.bin out.json        NAME = the file name, e.g. ce8c_BOSTON.bin (pick the layout by the id)
python3 voldat.py encode NAME in.bin edited.json out.bin
```
- `decode`: a JSON object that names what the data is. Values under keys starting with `_` are DERIVED (counts,
  offsets, sizes, padding the encoder recomputes); every other leaf is CONTENT and must be editable.
- `encode` rebuilds the chunk from edited.json; `encode(x, decode(x)) == x` byte for byte.
- Name things for what they are (fence point, wall height in feet, camera position, injury body part, severity,
  days out, ...). Numbered placeholders (f12, w3, unk7) for most keys fail the generic-name check; byte lists / hex
  strings for more than 25% of a chunk fail the dump budget; long unnamed word lists fail the audit.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/voldatref.py /home/will/bbpro98/re/targets/chunks $LANE [-v]`
on the 126 visible chunks (20 stadiums + SIM.DAT): string coverage (text chunks), dump budget, generic-name cap, round
trip, and random edits (strings get "Qz" appended, ints +1) that must re-decode to the edited JSON. Then a model
audits your code and a decode summary, and the same checks run on the chunks of 8 held-out stadiums. Decode
generically: never hard-code chunk data, counts or offsets, and never key a layout on a stadium name.

## Tools and budget
- Decompiles: `/mnt/nvme/bbpro98/index/{BBSIM,FastSim,Baseball,...}/_all.c` (grep the chunk ids as hex constants).
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (every chunk, table and field, with the evidence: code addresses or data
  facts such as real park dimensions).

Stop when the referee prints PASS and your names are backed by evidence, or when you are out of ideas for this round.
Always leave `voldat.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/chunks/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
