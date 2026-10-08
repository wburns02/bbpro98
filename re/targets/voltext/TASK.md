# Task: semantic read/write codecs for the shell string tables: news templates (league, team, player-of-the-week news), assert/error texts, box-score and print-out labels, preference-screen texts, print table layouts, roster texts (FPS Baseball Pro '98, SHELL.VOL DAT entries)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
The shell archive SHELL.VOL is solved (work/volcodec.py unpacks and repacks it). Its DAT entries hold game content:
the shell string tables: news templates (league, team, player-of-the-week news), assert/error texts, box-score and print-out labels, preference-screen texts, print table layouts, roster texts. Codecs that turn each into named, editable JSON and back unlock changing that content.
Files (read only, extracted from SHELL.VOL): `/mnt/nvme/bbpro98/targets_data/voldat/` ASNEWS.DAT, TMNEWS.DAT, PONEWS.DAT, ASSERTXT.DAT, BOXTEXT.DAT, PREFSCRN.DAT, PRINTTBL.DAT, PRINTTXT.DAT, ROSTEXT.DAT.

## Known (verify, do not trust)
Claude found: `u16 total | u16 nsections | u16 offsets...` then NUL-terminated strings, offsets relative to byte 2; with nsections == 1 the offset table starts at byte 4 and its first entry + 2 is where the strings start (ASNEWS, TMNEWS, PONEWS, ASSERTXT, BOXTEXT, PREFSCRN all follow this). PRINTTBL (7), PRINTTXT (8) and ROSTEXT (4) have several sections; PRINTTBL/ROSTEXT also hold numeric tables (column widths? positions?). News strings contain printf-style and game-specific substitution codes: name them in the JSON (which token means player, team, stat).

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
`python3 /home/will/bbpro98/re/targets/voldatref.py /home/will/bbpro98/re/targets/voltext $LANE [-v]`
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
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/voltext/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
