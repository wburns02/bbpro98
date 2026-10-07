# Task: a semantic read/write codec for the stats database mlbpa97.DAT (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
`Stats/*.DAT` holds every player's and team's stats: season, career, last season, a recent window, splits, fielding.
The container is solved (c-tree Plus, `/home/will/bbpro98/work/ctree.py`, notes in
`/home/will/bbpro98/re/targets/ctree/lanes/data/FORMAT.md`). The stat records are plaintext u16 words. What is missing
is the meaning of most record types and fields, and a writer. The goal is a codec that turns the stats into named,
editable JSON and back, so any stat in the game can be read or changed.

## Goal
Write `$LANE/stats.py` (Python 3 stdlib only, under 200 KB; it runs alone in a jail, so INLINE what you need from
ctree.py, never import or open other files) with:
```
python3 stats.py decode in.bin out.json
python3 stats.py encode in.bin edited.json out.bin
```
`decode` writes `{"records": [...], ...}` with one entry per stat record (every active c-tree record whose payload is
22, 36, 40, 70 or 150 bytes of u16 words with word0 in {0,1,2,3,16,17} and word1 == 2):
`{"off": payload offset, "scope": word0, "pid": word2, "kind": str, "period": str, "fields": {name: value, ...}, ...}`.
- `fields` = payload words 3.. in order, one meaningful name per word (placeholder names fail the referee and the audit).
- kind `bat` = 40-byte batting line, fields named exactly
  `ab h1b h2b h3b hr rbi bb so ibb hbp sh sf g r sb cs gidp`; kind `pit` = 70-byte pitching line with `outs`, `w`, `l`,
  `er` at field positions 18, 20, 21, 26 (name the other 28 too).
- period `season` = this season, `career` = career. Label every other group too (kinds and periods are yours to name:
  `recent`, `last_season`, `team`, `fielding`, `split_vs_lhp`, ...). Add any keys you like (split key, position, ...),
  and decode anything else in the file you understand as extra top-level keys.
- `encode` rewrites every record's words from `edited.json` (matched by `off`), in place, same file length.
  `encode(x, decode(x))` must equal `x` byte for byte.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/statsref.py /home/will/bbpro98/re/targets/stats $LANE [-v]`
Files (read only): `/mnt/nvme/bbpro98/targets_data/stats/day01 .. day09/` (consecutive sim days: `mlbpa97.DAT`, that
day's box scores `MLBPA97.H*`, and the league file `MLBPA97.ASN`), `base/_DEFAULT.DAT`, `base/mlbpa96e.dat`.
Per file: every stat record listed once with the payload words; names as above, at most 25% generic names overall;
for each consecutive day pair, every bat/pit line you label season or career changes by exactly the sum of that day's
box-score rows for its id (players and teams), and every player in a box score has one; every record that changed
since the previous day has a kind and period other than "unknown"; round trip; on day05, day09 and mlbpa96e.dat an
edit test (+2 HR, +1 W, +1 to the first field of a 22/36/150-byte record) that the trusted c-tree reader must see in
exactly those 3 records, with the file length unchanged and no stray bytes.
PASS = every visible file passes. Then a model audits your names and code (placeholder names fail), and the same checks
run on held-out days.

## What is known (verify, do not trust)
- Claude's probe: scope 1 batting/pitching lines change by exactly the day's box-score rows (the season line);
  scope 2 likewise (career; 1645 batting lines incl. players not on a roster); scope 0 also, until games drop out
  after about a week (a rolling recent window: negative deltas from day 8); scope 3 never changes and is the only
  scope in mlbpa96e.dat (last season). Scopes 16/17 carry 28 ids (teams) with every record length. Team rows in the
  box scores have id < 100 (team id, bit 15 = second team).
- Box-score files `MLBPA97.H*`: tables of `02 65` headers (u16 type, u16 ?, u16 count, u16 rec_len) with records of
  the same u16 layout as the stats lines (rec 40 = batting, 70 = pitching; word 2 = id). `statsref.py` and
  `asnref.py` show exactly how they are read. Look for other tables in them (fielding?) too.
- Per player and scope there is one 40 and one 70 line, one 150-byte line (72 fields: 9 positions x 8 fielding
  counts?), and several 22-byte (8 fields: the first 8 batting columns?) and 36-byte (15 fields) lines: splits. Some
  22-byte lines equal the parent's first 8 columns. Find the split key (vs LHP/RHP, home/away, month, situation ...).
- `/home/will/bbpro98/work/bbstats.py` reads 40/70 lines; `work/league.py` decodes the league file (rosters, schedule
  with dates, home/away), useful to work out split keys from that day's games.
- Decompiles: `/mnt/nvme/bbpro98/index/{BBSIM,BBShell,Upstats,...}/_all.c`.

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (every record type and split, every field, the evidence for each).

Stop when the referee prints PASS and every record type and field has a meaningful name, or when you are out of ideas
for this round. Always leave `stats.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/stats/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
