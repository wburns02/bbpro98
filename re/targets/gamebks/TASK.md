# Task: semantic read/write codec for game.bki / game.bko, the shell <-> simulator hand-off of FPS Baseball Pro '98

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
Before each simulated day BBShell writes `game.in` (one setup record per game: teams, managers, stadium, rosters,
lineups, pitching staff) for the simulator; the simulator answers in `game.out` (one result record per game: the
play-by-play event stream). BBShell renames them to `game.bki` / `game.bko` after reading. A codec for both lets us
read every simulated game event by event and rewrite what the simulator is told to play.

Files (read only): `/mnt/nvme/bbpro98/targets_data/gamebk/day1/` and `day2/`: `game.bki`, `game.bko`, the day's box
scores `MLBPA97.H??` and `boxscores.json` (those box scores already decoded: per file
`batters: [{pid, ab, h, hr, rbi, bb, so, r, sb}]`, `pitchers: [{pid, outs, bf, h, hr, bb, so, r}]`).
`/mnt/nvme/bbpro98/targets_data/gamebk/ref/`: `fpscipher.py` + `CIPHER.md`, the game's file cipher (solved).

## Known (verify, do not trust)
- Both files are a stream of chunks: 4-byte tag + u32 little-endian payload length + payload.
- game.bki: per game a `GDI:` chunk (payload 1031 bytes) then an `ADI:` chunk (12 bytes). GDI payload = 2-byte cipher
  seed + 1029 bytes enciphered with the file cipher (`decipher(payload[2:], payload[:2])` in ref/fpscipher.py; copy the
  algorithm into your codec, it must not import other files). Deciphered GDI (day1 game 0): home/away team blocks, each
  with u32/u8 flags, team name ("Atlanta", 33-byte field), manager ("Bobby Cox"), abbreviation ("ATL"), stadium
  ("Atlanta-Fulton County Stadium"), city ("ATLANTA."), a block of per-player byte triples, then u16 player ids: the
  25-man roster, lineups (batting orders separated by 0x0000 / 0xffff), the pitching staff, a 0..63 permutation-like
  byte table, the league name "MLBPA97"; the record ends with the box-score file name ("MLBPA97.HB0") the game's box
  score is written to. BBShell writes a status byte at +1000 of each record. ADI meaning is open.
- game.bko: per game a `GDO:` chunk, plaintext, 8-11 KB: a sequence of u16 event records. Each plate appearance
  starts with an event header (e.g. `02 00`) then the 9 defensive player ids, the batter, the pitcher (day1 game 0's
  first PA: pitcher 400 = 0x0190 faces batter 0x03c5 = 965), followed by pitch/outcome records such as
  `05 00 01 00 <pitcher> <code>` and `06 00 ...`, `07 00 ...`. Name every event type from what it does.
- The game index matches between the files: GDI game i names box file X, GDO game i is the same game.

## Goal
Write `$LANE/voldat.py` (Python 3 stdlib only, under 300 KB; it runs alone in a jail, never import or open other
files) with two commands; NAME is `game.bki` or `game.bko`:
```
python3 voldat.py decode NAME in.bin out.json
python3 voldat.py encode NAME in.bin edited.json out.bin
```
- decode: `{"games": [...], ...}`, one entry per game in file order. Keys starting with "_" are DERIVED and the encoder
  recomputes or ignores them; every other value is CONTENT and must be editable.
- game.bko games: the decoded event list (named event types and fields) AND `"_batters"` / `"_pitchers"`: the box
  score rows computed by REPLAYING your decoded events (rows `{pid, ab, h, hr, rbi, bb, so, r, sb}` and
  `{pid, outs, bf, h, hr, bb, so, r}`; extra keys allowed). Never copy them from anywhere: there are no box scores
  inside game.bko, only events.
- game.bki games: named fields; every player id under a key containing "pid" or "player" (at most 64 distinct ids per
  game: rosters + lineups + staff of both teams; never label non-player words as players).
- encode: REBUILD the file from edited.json (re-encipher GDI), `encode(x, decode(x)) == x` byte for byte.
- Raw byte lists, hex strings and control characters inside strings count as opaque data; at most 25% of a file may
  be kept that way. Name fields for what they mean; numbered placeholders fail.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/gamebkref.py /home/will/bbpro98/re/targets/gamebk $LANE [-v]`
Per day: game counts; the opaque budget and generic-key cap; round trip; every box score of
the day must equal one game's `_batters`/`_pitchers` rows exactly (rows compared as multisets; the error names the
closest game and how many batter rows match); every box score's players must all appear under pid/player keys of one
game.bki game; an edit test (random content strings get "Qz", random non-zero content ints +1; the re-decode must equal
the edited JSON on every content leaf and re-encode stably; edited game.bki may grow by only a few bytes).
PASS = both visible days pass. Then a model audits your code and a decode summary, and unseen sim days run as a holdout
(their box scores must come out of your replay too). Decode generically: never hard-code content.

## Tools and budget
- Decompiles: `/mnt/nvme/bbpro98/index/<dll>/_all.c` (BBShell: rename near line 80818, GDI reader near 80560, GDO
  reader near 81615; the simulator side is in BBSIM / FastSim: grep "game.in", "game.out", "GDI", "GDO").
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document both layouts and every event type in `$LANE/FORMAT.md` (header, records, fields, the evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `voldat.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/gamebk/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
