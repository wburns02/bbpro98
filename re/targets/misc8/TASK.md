# Task: semantic read/write codecs for the small data files of FPS Baseball Pro '98: HHA.DAT, bb.cfg, StatSets/*.STS, Assn/*.apc, *.pyc, *.pyf

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
Every other data file of the game is solved. These small files hold the hit/home-run animation table, the launcher config, the stat-column sets of the statistics screens, the champions history and two player id lists. Codecs that turn each into named, editable JSON and back finish the data side of the unlock.
Files (read only): `/mnt/nvme/bbpro98/targets_data/misc8/` HHA.DAT, bb.cfg, MLBPA97.apc, MLBPA97.pyc, MLBPA97.pyf and six .STS files. The NAME argument selects the layout: match by extension (any *.STS, *.apc, *.pyc, *.pyf name is that layout).

## Known (verify, do not trust)
- .STS (117 bytes; BBShell StatSet_LoadFile 0x6805d7d0 checks size 0x75): u32 version (must be 1), char name[33] (NUL then stale
  bytes from an older name, e.g. "Vs. Left\0al Avg": keep the tail so the file round-trips), then 0x50 bytes = u32 ids[2][10]:
  block 0 batting, block 1 pitching (BBShell copies ids + view*10 into the Statistics grid; view 1 = pitching). Each block's
  first two u32 and then 8 column stat ids; ids index the stat name pointer table DAT_680906e8 (StatsGrid_InitHeaders).
  Name the first two words from their use (grep g_StatSets / ids in BBShell).
- .apc: tagged chunks "PC0:" u32 payload_len, payload = u16 year, s16 line_count, line_count NUL strings
  ("1997: Colorado  defeat Cleveland  (4-3)"). Loader FUN_6804d7a0 area (BBShell _all.c ~61350), writer FUN_6804d960.
- .pyc / .pyf: one chunk "PPD:" u32 payload_len, payload = u16 count, count u16 player ids (loader BBShell ~67392 keeps
  ids 100 < id < limit). The game rewrites in place without truncating: bytes after the chunk are stale data from an older,
  longer list (keep them as a derived "_" tail; MLBPA97.pyc has count 0 and ~960 stale bytes).
- HHA.DAT: BBSIM FUN_68035f31 (Hranim.cpp): u16 magic 0x6969 ("HHA.DAT file needs to be converted" otherwise), a 0x200-byte
  table read into DAT_681437e8 (64 entries of 8 bytes), then the rest of the file into one buffer that 64 calls of
  FUN_6803634f walk (each returns the size of one animation record). Find what the 64 entries and records are (look at
  the users of DAT_681437e8 and of the parsed records).
- bb.cfg (124 bytes): read/written by EZShell (grep "bb.cfg"): league names "MLBPA97" and small option values.

## Goal
Write `$LANE/voldat.py` (Python 3 stdlib only, under 300 KB; it runs alone in a jail, never import or open other
files) with two commands; NAME is the entry name and selects the layout:
```
python3 voldat.py decode NAME in.bin out.json
python3 voldat.py encode NAME in.bin edited.json out.bin
```
- decode: a JSON object per file that names what the data is. Keys starting with "_" are DERIVED (counts, offsets,
  sizes, padding) and the encoder recomputes them; every other value is CONTENT and must be editable.
- encode: REBUILD the file from edited.json: strings may grow or shrink, so recompute every offset/size/count.
  `encode(x, decode(x)) == x` byte for byte (if the original layout has quirks, keep what you need in "_" keys).
- Raw byte lists, hex strings and control characters inside strings count as opaque data; at most 25% of a file may
  be kept that way. Name fields for what they mean; numbered placeholders fail.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/voldatref.py /home/will/bbpro98/re/targets/misc8 $LANE [-v]`
Per file: every printable NUL-terminated string (>= 4 chars) of the file appears in the decoded content; the opaque
budget; the generic-key cap; round trip; an edit test (random content strings get "Qz" appended and must then be
stored in the file, random non-zero content ints get +1; the re-decode must equal the edited JSON on every content
leaf and re-encode stably). PASS = all files pass. Then a model audits your code and a decode summary, and more random
edits run as a holdout. Decode generically per layout: never hard-code content.

## Tools and budget
- Decompiles: `/mnt/nvme/bbpro98/index/<dll>/_all.c` (grep the file names to find loaders).
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document every layout in `$LANE/FORMAT.md` (header, tables, fields, the evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `voldat.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/misc8/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
