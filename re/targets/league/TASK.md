# Task: a semantic read/write codec for the league file MLBPA97.ASN (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
The league file holds the whole league state: teams, rosters, the 162-game schedule with results, standings and more.
The container is solved (c-tree Plus superfile, codec `/home/will/bbpro98/work/ctree.py`, format notes
`/home/will/bbpro98/re/targets/ctree/lanes/data/FORMAT.md`). Records are enciphered with the game's byte cipher
(`/home/will/bbpro98/work/fpscipher.py`, key `f5dc`: `T = forward(bytes.fromhex('f5dc'))`, plain = INV[T][cipher]).
What is missing is the meaning of the fields. A codec that turns the league into editable JSON and back unlocks editing
any team, roster, standing and schedule entry.

## Goal
Write `$LANE/league.py` (Python 3 stdlib only, under 200 KB; it runs alone in a jail, so INLINE what you need from
ctree.py and fpscipher.py, never import or open other files) with two commands:
```
python3 league.py decode in.bin out.json
python3 league.py encode in.bin edited.json out.bin
```
`decode` writes at least:
```
{"teams": [{"tid": 1..28, "name": str, "w": int, "l": int, "roster": [player ids], ...}  x 28],
 "games": [{"home": tid, "away": tid, "played": bool, "hr": int, "ar": int, ...}  one per schedule entry],
 ...}
```
- `tid` is the team id the game's box-score files use (1..28). `roster` holds the player ids the box scores use (>= 100).
- Decode as much more of the file as you can (other members and fields, named where you know the meaning); extra keys
  are free, and they are what makes the codec useful.
- `encode` rebuilds the file from `in.bin` with every contract field (name, w, l, home, away, played, hr, ar, roster)
  taken from `edited.json`, using the c-tree record rewrite logic (keep indexes and headers consistent).
  `encode(x, decode(x))` must equal `x` byte for byte. Field edits must happen in place (same file length, no added
  records, no data outside records, record headers and index keys). `work/ctree.py` apply does this for same-length
  rewrites as of 2026-10-07 (it keeps the B-trees when no key changed), so re-copy it if you inlined an older one.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/asnref.py /home/will/bbpro98/re/targets/league $LANE [-v]`
Files (read only): `/mnt/nvme/bbpro98/targets_data/league/day01 .. day09/` (consecutive sim days: `MLBPA97.ASN` plus
that day's box-score files `MLBPA97.H*`), `base/_DEFAULT.ASN`, `base/MLBPA96E.ASN` (fresh leagues). Per file it checks:
schema; sum(w) == sum(l) == number of played games and each team's w+l equals its played games in the schedule; the 28
names; for each consecutive day pair, every team's W and L grow by exactly that day's box-score results and the newly
played games equal that day's box scores (home/away team ids with their runs); every player id a box score credits to a
team is in that team's roster that day or the day before (>= 99%); round trip; and on day05, day09 and _DEFAULT.ASN an
edit test (rename a team keeping the length, +3 wins for another team, +1 run for a played game) that must decode to
exactly the edit, leave a c-tree file the trusted codec parses with consistent indexes and at most 8 changed records,
and store the new name enciphered in a team record.
PASS = every visible file passes. Then a model audits your code and a decode summary, and the same checks run on
held-out days you never see. So decode structures generically: never special-case a file, day, size or team.

## What is known (verify, do not trust)
- ctree.py `dump` lists members (names a, l, d, t, r, s, xs, tr, df, po, sp, each with an .idx index member) and records.
- `t`: 28 records x 256 bytes, the teams. Deciphered, the team name sits at payload offset 18, NUL-terminated; a nearby
  byte looks like the division slot (0..4). Atlanta is the first.
- `r`: 28 records x 294 bytes (rosters?). `s`: 2269 records x 17 bytes = 162*28/2 + 1 (schedule, one header record?).
  `xs`: 28, `tr`: 34, `df`, `po`, `sp`: unknown.
- Claude's probe of `s` (records passed through INV): bytes 6 and 10 each take 28 distinct values exactly 81 times
  (home / away team?). Those values (1, 29, 31, 36, 38, 57, ...) are team codes, not the box-score ids 1..28; the
  mapping code -> tid is yours to find (the team records carry a byte near the name worth checking). Bytes 0x40 are
  frequent, so INV may not be the right decipher for every member; check per member.
- Box-score files `MLBPA97.H*` are tables starting `02 65` (u16 type, u16 ?, u16 count, u16 rec_len, then count
  records). Record length 40 = batting rows, 70 = pitching rows; u16 word 2 is the id (< 100 = a team row, team id;
  bit 15 marks the second team). Team batting row: u16 word 3+13 = runs scored. Team pitching row: words 3+20 / 3+21
  = W / L for that game (1/0). Player rows (id >= 100) list who played. `asnref.py` shows exactly how they are read.
- Day k's new box scores = the H file names present on day k but not on day k-1. W/L, runs and played flags change
  between days only for those games, which makes the field hunt a diff exercise.
- Decompiles: `/mnt/nvme/bbpro98/index/{BBSIM,BBShell,Upstats,...}/_all.c`.

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (every member, its record layout field by field, the evidence for each).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `league.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/league/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
