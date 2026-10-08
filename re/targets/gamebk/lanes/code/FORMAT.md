# game.bki / game.bko format (FPS Baseball Pro '98 shell <-> simulator hand-off)

> Superseded 2026-10-08 by work/spec/GAMEBK_FORMAT.md and work/gamebk.py. Corrections: team name is two 17-byte
> strings (+0x0c name, +0x1d alt name); +0x77 is the 32-colour uniform palette, not a pitch-frame table; the
> score-line state words are 30 u8 runs per inning; the DIF: chunk exists (this codec drops it).

Lane: `code` · round 3 · codec: `voldat.py` (stdlib-only, ~23 KB)

## File container

Both files are a stream of chunks:

```
chunk := tag[4] ("GDI:" | "ADI:" | "GDO:") + u32le payload_length + payload
```

game.bki = per game one `GDI:` chunk (payload 1031 B) followed by one `ADI:` chunk (12 B).
game.bko = per game one `GDO:` chunk (plaintext event stream, 7-15 KB). Game order matches
between the files (each box score of the day equals exactly one GDO game's replayed rows;
verified for all 23 games of both visible days).

Evidence: BBShell `_all.c` — chunk helpers `FUN_680633b0` (open), `FUN_68063450` (read chunk
with 4-byte tag compare, e.g. `DAT_6808c89c`), `FUN_68063840` (write tag + length placeholder),
`FUN_68063910` (backpatch the length); the rename of `game.in`/`game.out` to
`game.bki`/`game.bko` at `FUN_68061390` (lines 80818-80823).

## GDI record (payload = 2-byte cipher seed + 1029 enciphered bytes)

`decipher(payload[2:], payload[:2])` with the file cipher (seed → substitution table applied
three times; algorithm in `voldat.py`, from `ref/fpscipher.py`). Evidence: legible team names,
manager, stadium, league, box file name after deciphering (both days).

Deciphered record (1029 bytes) = two 490-byte team blocks + a 49-byte tail:

| offset | size | field |
|---|---|---|
| 0 | 490 | away team block (block 0 = the away team, see sides below) |
| 490 | 490 | home team block |
| 980 | 19 | footnote scratch (raw) |
| 999 | 1 | game status byte (raw; 0xff until BBShell writes 1..3 after a played game) |
| 1000 | 3 | post-status scratch (raw) |
| 1003 | 9 | home city name (stored truncated: "HOUSTON.", "NEWYORKN") |
| 1012 | 12 | box-score file name ("MLBPA97.HB0\0\0\0") — the game-index binding |
| 1024 | 5 | record tail scratch (raw) |

Block order evidence (all 23 games): the sum of runs scored by each block's roster equals the
score line's Away total for block 0 and Home total for block 490; the +1003 city copy matches
block 490's city; the first plate appearance's pitcher (the home team's starter, pitching the
top of the 1st) is in block 490's roster and the first batter is in block 0's.

### Team block (base 0 / 490)

| rel | size | field |
|---|---|---|
| +0 | 4 | flag word 1 (u32) |
| +4 | 4 | flag word 2 (u32) |
| +8 | 4 | config bytes (raw) |
| +12 | 34 | team name ("Atlanta") |
| +46 | 17 | manager name ("Bobby Cox") |
| +63 | 14 | team abbreviation ("ATL") |
| +77 | 33 | stadium name ("Atlanta-Fulton County Stadium") |
| +110 | 9 | city name (truncated: "ATLANTA.", "LOSANGEL") |
| +119 | 96 | pitch-frame table (raw triples; values look like camera angles: 52,52,128,48,48,116…) |
| +215 | 1 | rotation flag (raw) |
| +216 | 1 | starter flag (raw) |
| +217 | 50 | 25 × u16 player ids (the 25-man roster) |
| +267 | 204 | 102 × u16 order/pen words (below) |
| +471 | 2 | block gap (raw) |
| +473 | 9 | league name ("MLBPA97") |
| +482 | 8 | block tail (raw) |

The +267 order/pen words split on 0x0000/0xffff separators: 15 zero words, then
the starting batting order (9 u16 pids), then 8-word order copies (vs LHP/RHP and with a
[a 0x65535 separator]), the pitching staff head (starter pid twice + 3 words), and a 25-word
tail that mixes staff/pen pids with non-player words (sentence fragments like 11018, 6162).
Only the roster (50 pids) is required to cover every box-score pid (verified all 23 games);
the pen words are kept verbatim.

### ADI chunk (12 bytes)

Enciphered with the GDI seed. Deciphered: 8-byte timestamp word (twice), u16 season index,
u16 season flag (0x0000/0x0001). Evidence: `d72f0b00` twice per day changes between days
(d72f/d82f), the low u16 counts the game index.

## GDO record (plaintext u16 event stream, sizes fixed per type)

The key structural fact — **the event stream has FIXED record sizes** (`EVENT_SIZES` in
`voldat.py`): BBSIM Event.cpp walks its own table `DAT_680b3238` (BBSIM.dll `.data` at
0x728120), indexed by type word:

| type | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| size (bytes) | 4 | 82 | 30 | 14 | 6 | 8 | 8 | 10 | 12 |

(tag word included). The payload opens with the type-0 game_start `[0][4]`. This walk
terminates exactly on all 23 visible payloads with zero padding. The type names and every
code table come from the simulator's own debug printer `FUN_68027ae8` + its label tables in
BBSIM.dll `.data`:

- type names (0x680ba358, 17 B each): 0 Enter Game, 1 Exit Game, 2 Plate Appearance,
  3 Substitution, 4 Team, 5 Pitching, 6 Batting, 7 Fielding, 8 Injury
- half names (0x680ba3f8): 0 Away, 1 Home
- pitch results (0x680ba458): 0 AB, 1 B1, 2 B2, 3 B3, 4 HR, 5 RBI, 6 BB, 7 K, 8 HBP, 9 BBI,
  10 SH, 11 SF, 12 R, 13 SB, 14 CS, 15 BFP, 16 ER, 17 IR, 18 IRS, 19 PT, 20 KT, 21 WP
- batting outcomes (0x680ba4b0): 0..13 as above, 14 CS, 15 GDP, 16 PO
- fielding plays (0x680ba4f8): 0 PO, 1 A, 2 E, 3 DP, 4 PB
- substitution kinds (0x680ba438): 0 PH, 1 PR, 2 RP, 3 DS; team events (0x680ba448):
  0 RUN, 1 ER, 2 TP, 3 DP, 4 AB
- positions (0x680ba408): 1 P, 2 C, 3 1B, 4 2B, 5 3B, 6 SS, 7 LF, 8 CF, 9 RF

### Sides

The half word indexes the GDI team blocks: **0 = block 0 = the away team, 1 = block 490 =
the home team**. A pitch (T5) or fielding (T7) record's half = the fielding team; a batting
(T6) record's half = the batting team. Evidence: the T7 puts of a half sum exactly to the
outs of the pitchers in that team's staff; the T6 at-bats of a half equal that team's box AB.

### Event fields

| type | name | fields (word 0 = the type) |
|---|---|---|
| 0 | game_start | `log_version` (= 4) |
| 1 | score_line | `game_seconds` (word 1, printed h:mm:ss), `game_outs`, then per half [15 state words, `runs`, `hits`, `errors`, `left_on_base`] — away first (word 3), home at word 22 |
| 2 | plate_appearance | 9 fielder pids in position order, `on_deck_pid` (word 10), `batter_pid` (word 11), `runner_first/second/third_pid` (words 12-14, 0 = empty) |
| 3 | substitution | half, `player_pid`, `change_code` (PH=0/PR=1/RP=2/DS=3), `slot_word`, `order_word`, `flag_word` |
| 4 | team_event | half, `event_code` (RUN/ER/TP/DP/AB) |
| 5 | pitch | `pitching` half, `pitcher_pid`, `(flag_bits<<8)\|result_code` |
| 6 | batting_record | `batting` half, `player_pid`, `outcome_code` |
| 7 | fielding_record | `fielding` half, `fielder_pid`, `play_code`, `position_code` (1-9) |
| 8 | injury_record | half, `player_pid`, 3 injury words |

Evidence for the T2 layout: the game-record sprintf (Event.cpp case 2) prints words 1-9 as the
fielders with position labels and words 10-14 with runner labels OD, AB, 1B, 2B, 3B — word 10
= on-deck, word 11 = the batter, 12-14 = the runners. The T6 marks match word 11's pid for the
batter's own events in every bundle.

### T5 pitch semantics (against the box)

- `15` (BFP, "batter faced") opens a plate appearance: the count of code-15 pitches per
  pitcher = the box `bf` exactly (all 23 games, every pitcher).
- `19` (PT)/`20` (KT) = a pitch thrown / a called strike: individual pitch markers.
- `0..13` mirror the T6 batting outcome that follows them (the pitch outcome marker).

### T6 batting semantics (the box-score marks)

| code | meaning | box effect |
|---|---|---|
| 0 (AB) | the at-bat token | ab += 1 |
| 1/2/3 (B1/B2/B3) | single/double/triple | h += 1 (the ab arrives as the companion code 0) |
| 4 (HR) | home run | h += 1, hr += 1 (companion code 0 = the ab) |
| 5 (RBI) | run batted in | rbi += 1 |
| 6 (BB) | base on balls | bb += 1 (also charged to the opposing pitcher) |
| 7 (K) | strikeout | so += 1 (its ab arrives as the companion code 0; no h) |
| 8 (HBP) | hit by pitch | no box effect (the ab arrives as the companion code 0) |
| 9 (BBI) | intentional walk | no box effect (a walk walks as code 6 + 9; the box bb counts 6) |
| 10 (SH) / 11 (SF) | sacrifice | the ab companion never follows (no ab) |
| 12 (R) | the pid scores | r += 1, also charged to the fielding side's current pitcher |
| 13 (SB) | stolen base | sb += 1 (can appear inside the NEXT batter's PA) |
| 14 (CS) / 16 (PO) | caught stealing / pickoff | no box effect (not seen on the visible days; emission sites verified in the decompile) |
| 15 (BFP) | runner-advance scratch (runner context) | no box effect |

The code-0 companions pair with the outcome: a K emits `[6,h,pid,7]` then `[6,h,pid,0]`; a hit
emits the outcome then `[6,h,pid,0]`; a walk emits only code 6. Verified: the count of code-0
T6 records per batter = the box ab exactly (all 23 games), so counting ab from code 0 (and
never from 7) is the rule.

### T7 fielding semantics

play_code 0 (PO) = one out: credited to the current pitcher of the fielding team (the record's
half), in order 0..27 per staff (all 23 games exact). play_code 3 (DP) = a double play (the
out already counted by its two PO records); play_code 1 (A) = an assist, 2 (E) = an error,
4 (PB) = a passed ball.

### Box-score replay (`_batters` / `_pitchers`)

From the decoded events only:
- `_batters` rows `{pid, ab, h, hr, rbi, bb, so, r, sb}`: ab = count of T6 code-0 records;
  h = codes 1/2/3/4; hr = code 4; rbi = code 5; bb = code 6; so = code 7; r = code 12;
  sb = code 13. Rows materialize only when a counted stat lands (the box files omit all-zero
  rows; the H decoder excludes them too).
- `_pitchers` rows `{pid, outs, bf, h, hr, bb, so, r}`: outs = T7 code-0 records credited to
  the current pitcher of the fielding side; bf = count of T5 code-15 pitches; h/hr/bb/so =
  the opposing batters' T6 marks (1/2/3/4, 4, 6, 7); r = the T6 code-12 records charged to
  the fielding side's current pitcher.
- Verified row-for-row (multisets) against every box score of both visible days (9 + 14).

## Codec state (round 3)

- `decode`/`encode` round trip byte-for-byte for both files on both days (23 games).
- The walk uses the simulator's own fixed size table — no heuristics, no drift.
- GDI: every span named; the raw byte spans travel as control-prefixed hex strings
  (unprintable → never picked as edit strings; cheap in the opaque budget).
- GDO: 9 typed records + a tolerant fallback (`log_word`) for unseen words; kind strings are
  `_`-derived from the codes.
- The real referee still cannot run in this sandbox (the jail needs a systemd user manager;
  PID 1 is bwrap). `analysis/localref.py` mirrors its check_day + edit_test verbatim:
  PASS on both days, plus 16+12 varied edit seeds all PASS.
- Holdout hardening in round 3: the block-order fix (away=block 0), raw spans as strings,
  the `_`-derived kind strings, the tolerant GDO walk, and the verified record-level replay.
