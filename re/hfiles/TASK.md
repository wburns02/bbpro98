# Task: decode the per-game box score files `Stats/MLBPA97.Hxx` (FPS Baseball Pro '98)

You are the decoder builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current oracle score).

## Goal
Write `$LANE/hdecode.py`. Contract: `python3 hdecode.py <path-to-H-file>` prints ONE JSON object:
```
{"batters":  [{"pid": int, "ab": int, "h": int, "hr": int, "rbi": int, "bb": int, "so": int, "r": int, "sb": int}, ...],
 "pitchers": [{"pid": int, "outs": int, "bf": int, "h": int, "hr": int, "bb": int, "so": int, "r": int}, ...]}
```
Each player who appeared in that game, with his line for that game only. `pid` = the player id used in `Stats/mlbpa97.DAT` and `Assn/MLBPA97.PYR`.

## The referee (do not edit it, do not copy its truth into the decoder)
`python3 /home/will/bbpro98/re/hfiles/check_hdecode.py $LANE/hdecode.py [-v] [--days 2-3]`
It runs your decoder in a jail (no network, no files except a copy of the game file named `game.bin`) on every game file from snapshot days 2..7 and compares against the true per-player stat changes for that day. `-v` prints every mismatch. PASS = batting cell accuracy >= 0.99 with <= 1% missing/extra players. Pitching is scored too: get it to >= 0.99 after batting passes. After that the driver scores held-out days 8..10, which you cannot see: a decoder that special-cases days 2..7 fails there.

Hard rules for `hdecode.py`: it may read ONLY the file given on its command line (plus the Python stdlib). It must not read anything under `/mnt/nvme/bbpro98/re/asnseq`, any `.DAT`/`.ASN`/`.PYR`, or the referee, and must not embed tables of stat values. The jail enforces the first part (other paths simply do not exist when it runs); a Haiku auditor and the holdout catch the rest. During DEVELOPMENT you may use any file to work out the format.

## Data
- You run in a sandbox: only your lane workspace `$LANE/` is writable (its `runs/` is read-only; the referee and everything else is read-only), everything else listed here is read-only, and other paths do not exist. Your previous rounds' logs are in `runs/`.
- Snapshots (read only): `/mnt/nvme/bbpro98/re/asnseq/day01..day07/` (08..10 are the holdout and are not mounted) (each has `Stats/` and `Assn/`). Day N's NEW game files are those not present (or changed) on day N-1. File names: `MLBPA97.H<day hex digit><game idx>`, e.g. day 2 = `H20..H2C` (13 games). One file per game, ~10 KB each.
- Truth helper for development: `/home/will/bbpro98/re/hfiles/check_hdecode.py` exposes `lines(day)`, `delta(...)`, `hfiles(day)` (import it). The truth for a day is the sum over that day's games, so a day with one game per team gives exact per-player game lines (each team plays at most once per day in this data).
- Player names: `sys.path.insert(0,'/home/will/bbpro98/work'); import bbstats; bbstats.names('/mnt/nvme/bbpro98/re/asnseq/day07/Assn/MLBPA97.PYR')` -> {pid: name}. Useful for spotting the roster/name area if names are present.
- Stats line layout: `/home/will/bbpro98/work/NOTES_stats_format.md`.

## What is known about the H files (verify, do not trust)
- Raw byte histogram is dominated by 0x31; the file starts `02 65 ff ff 01 00 8a 0a 63 04 ...`. Plain XOR with 0x31 does NOT give clean zeros, so it may be a rolling/keyed XOR, an additive cipher, or a simple compression (RLE/LZ) of mostly-zero records. Compare same-offset bytes across many files and look at runs.
- The file extension is built with a `".%c%c%c"` format string found in `BBShell.dll` and `Upstats.dll`. The code that WRITES or READS these files is the fastest route to the encoding: decompiles with Ghidra names are at `/mnt/nvme/bbpro98/index/<Binary>/_all.c` (+ `_functions.tsv`). Look for `.%c%c%c` usage, fopen/CreateFile callers, and XOR/rotate loops near them.
- The ASN also has 34-byte `fa fa 22` records at 0x30000..0x6D500 that may be lineups; only use them if the H files stall.

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem (e.g. "here are 20 aligned byte columns and the truth values, what is the cipher"), you may get a second opinion from DeepSeek: write a self-contained task file and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`. Paste all data it needs into the task file; it cannot see files.
- Do not run Wine or the game. Do not touch `/mnt/nvme/bbpro98/work_install` or any live install. Do not git push. Do not edit anything outside `$LANE/`.
- Write the format as you learn it into `$LANE/HFILE_FORMAT.md` (offsets, field meanings, the encoding, evidence for each claim).

Stop when the referee prints PASS and pitching is >= 0.99, or when you are out of ideas for this round. Always leave `hdecode.py` runnable and `progress.md` updated.

## Parallel lanes
Three GLM lanes work on this at the same time, each with a different primary route, in `/home/will/bbpro98/re/hfiles/lanes/{code,data,struct}/`. At the start of every round read the other lanes' `progress.md` and `HFILE_FORMAT.md` (read-only to you) and reuse anything verified. Keep your own notes short and factual so they can do the same. The first lane whose decoder passes the referee, the audit and the holdout ends all lanes.
