# game.bki / game.bko: layouts, event grammar, evidence (lane "code", rounds 1-2)

Sources read: BBSIM.dll and BBShell.dll decompiles (`/mnt/nvme/bbpro98/index/{BBSIM,BBShell}/_all.c`), the
BBSIM.dll image itself for string/table bytes (`BBPRO98_package/game/BBSIM.dll`, PE base 0x68000000, read with
Python only), and the visible files. Everything below was checked against the 23 visible games (day1 9, day2 14).

## 0. Container (both files)

Both files are a stream of chunks: 4-byte tag, u32 little-endian payload length, payload.
- game.bki: one game = `GDI:` (1031 bytes), then its `ADI:` (12 bytes), then an OPTIONAL `DIF:` (72 bytes), up to the
  next `GDI:`. Any other chunk in that span is kept verbatim (`_other_chunks`). The codec records the order of a game's
  chunks in its derived `_layout` (items: `ADI:`, `DIF:`, `other`), so the rebuild is byte exact.
- game.bko: `GDO:` (variable length), once per game. Any non-GDO chunk is kept verbatim in the top-level
  `_other_chunks` with `before_game` (how many games precede it).

## 1. game.bki (BBShell writes it, the simulator reads it)

### 1.1 GDI payload: 2 seed bytes + 1029 enciphered bytes
- `payload[0:2]` = cipher seed `(lo, hi)`. The record is `decipher(payload[2:1031], seed)` with the solved file
  cipher (`ref/fpscipher.py`; copied into voldat.py). The codec stores the seed as `cipher_seed = lo | hi << 8`.
- Evidence: BBSIM FUN_680324d9 reads the seed bytes, then 0x405 bytes, then deciphers (FUN_680b0ef6 / FUN_680b10c5).
  BBShell FUN_68061dd0 does the same (`FUN_68053450(local_188, seed)`, `FUN_68053510(..., 0x405)`).

### 1.1a Why the optional blocks are handled
BBSIM FUN_680324d9 (the game.in reader, decompile BBSim `_all.c` ~l.29170-29265) walks the chunks: it counts `GDI:`
tags, and for the selected game reads 0x405 bytes after the seed, then scans up to the next `GDI:` for `ADI:` (reads
10 bytes into its parameter block) and `DIF:` (reads 0x48 bytes), deciphering both with the game's seed. Each block is
optional. Round 1 raised on a missing or extra chunk; that is one plausible cause of the day3 holdout failure (unconfirmed).

### 1.2 ADI payload: 12 bytes enciphered with the same seed
Deciphered, all 23 games: `d7 2f 0b 00 | d7 2f 0b 00 | game_no u16 | flag u16`.
- `day_key` (u32) and `day_key_copy` (u32) are equal in every game of a day (same value in day1 and day2 files as
  seen; treated as content, see "unverified" below).
- `game_no` = 0..n-1 in file order (0,1,2,3 ... seen). `adi_flag` = 1 in every visible game.
- Evidence: BBShell FUN_68061dd0 reads `0xc` more bytes into `this+0x405` and deciphers them with the GDI table.
  BBSIM FUN_680324d9 reads 10 bytes into a parameter block and a `DIF:` chunk (72 bytes) if present (none visible).

### 1.3 Record (1029 bytes after decipher)

| offset | size | field (codec key) | evidence / note |
|---|---|---|---|
| 0 | 490 | away team block (`away_team`) | BBSIM copies record+12 (name) into the team-name slot, so block 0 starts at 0 |
| 490 | 490 | home team block (`home_team`) | BBSIM copies record+502 (home name); same block layout |
| 980 | 4 | `record_tail.game_code` | varies per game (day-specific), unverified |
| 984 | 12 | `record_tail.schedule_params` | `08 01 00 96 01 01 00 00 00 2d b5 04` in most games; bytes 984..988 vary, unverified |
| 996 | 2 | `record_tail.game_seed` (u16) | varies per game, unverified (likely the sim's per-game seed) |
| 998 | 1 | `record_tail.shell_status` | = 2 in all games. BBShell FUN_68060f90 writes its status argument (1 or 2) at payload+1000, which is record[998] |
| 999 | 1 | `record_tail.ready_flag` | = 1 in all games. BBShell FUN_68061dd0 accepts the record only if this byte is 1, 2 or 3 |
| 1000 | 3 | `record_tail.tail_flags` | `04 01 00` in all games |
| 1003 | 9 | `record_tail.home_city_echo` | equals the home team's city in 23/23 games |
| 1012 | 12 | `record_tail.box_score_file` | e.g. `MLBPA97.HB0`, `MLBPA97.HC7`. Equals the box file whose rows the game's replay reproduces, in 23/23 games |
| (any) | | `_junk_after_nul` (derived) | field tails after a NUL, kept only when non-zero (round 2: buffer leftovers are not an error) |
| 1024 | 5 | `record_tail.tail_words` | `00 00 01 28 00`, `00 00 00 a0 14` (vary), unverified |

### 1.4 Team block (490 bytes, same layout for both teams; base b = 0 or 490)

| rel. offset | size | key | content / evidence |
|---|---|---|---|
| 0 | 4 | `team_code` | varies per team (`01 00 00 00`, `08 00 01 02`, ...), unverified |
| 4 | 8 | `header_tail` | `01 00 00 01 03 03 03 03` in all 46 team blocks |
| (any) | | `_junk_after_nul` (derived) | per string field, the bytes after its NUL when non-zero (round 2) |
| 12 | 34 | `team_name` | NUL-terminated, fixed 34-byte field ("Atlanta", "Houston"); BBSIM strcpy's it into 0x22-byte slots |
| 46 | 17 | `manager` | "Bobby Cox", "Larry Dierker" |
| 63 | 14 | `abbreviation` | "ATL", "HOU" |
| 77 | 33 | `stadium` | "Atlanta-Fulton County Stadium" |
| 110 | 9 | `city` | "ATLANTA." (also the home city echo in the record tail) |
| 119 | 98 | `tuning_rows` (32 rows of 3) + `tuning_tail` (2) | per-team byte table. Rows look like `(x, x, y)` or `(z, z, z)`, with the phase shifting in the last 6 rows. Semantics unknown |
| 217 | 80 | `roster_pids` (40 u16) | the 40-slot roster table. Upstats FUN_6c007350 copies 0x14 dwords from team offset 0xd9 (= 217), and FUN_6c002850 loads all 40 words into the side's player table (0x28 entries of 21 bytes). Visible: slots 0..24 hold the 25 players, slots 25..39 are 0 (empty). Round 3: 40 slots, not 25 + padding |
| 297 | 136 | `lineup_segments` (68 u16) | see 1.5 |
| 433 | 40 | `depth_table` | 40 bytes, values 1..73, distinct within a team in 45 of 46 teams (one team repeats one value). Semantics unknown |
| 473 | 8 | `league` | "MLBPA97" (NUL-terminated, 8-byte field) |
| 481 | 9 | `team_flags` | 9 bytes, one of two patterns (`0 0 1 1 0 1 1 1 0` or `0 0 1 1 1 1 1 1 0`) in all teams, unverified |

### 1.5 lineup_segments: u16 words split by separators
The 68 words are split on 0x0000 / 0xffff. Each segment keeps its end word (the last has `end: null`). Layout seen
in all 46 teams:
- seg 0: 17 ids. The first 9 look like a batting order whose 9th slot is the starting pitcher (115 / 400). The
  next 8 are a second order without the pitcher, with no separator between them (unverified reading).
- segs 1..4: 8-id batting orders (ends 0xffff, 0xffff, 0, 0).
- seg 5: starter 115 listed twice, plus 2422, 1887, 1792 (bench players; not in the box score as pitchers).
- segs 6, 7: empty. seg 8: 101, 135, 1608, 100, 112, 941 (the staff; 1608 is a box-score reliever).

The encoder rebuilds the words from the segments. Edits to ids keep the width.

Team-level roster coverage: all 23 box scores' players are within `roster_pids` plus `lineup_segments` of one game
(referee check passes; at most 64 distinct ids per game: about 50).

### 1.6 DIF payload (optional, 72 bytes, enciphered with the same seed)
Key `dif_block` (list of 72 ints, deciphered). BBSIM FUN_68031e2f zeroes a 0x48-byte block at game-state +0x409 and
FUN_680327b5 fills it from the `DIF:` chunk when present (its accessor returns `param_1 + 0x409`, BBSim `_all.c`
l.44634). Field meanings are NOT established: the 72 bytes are kept exactly and listed. No visible game has a DIF.

## 2. game.bko (the simulator writes it, BBShell reads it)

### 2.1 Stream
`GDO:` payload = u16 little-endian words. Each record starts with its type word. Record size per type comes from
BBSIM's size table at DAT_680b3238 (int per type; types 0..8 = 4, 82, 30, 14, 6, 8, 8, 10, 12 bytes; types 9+ = 0).
Every visible game parses exactly: one type 0 first, one type 1 last, no gaps (9 + 14 games).

### 2.2 Labels and event formatter
BBSIM FUN_68027ae8 is the event formatter. The label table at DAT_680ba358 (17-byte stride) gives the names used
below: `Enter Game, Exit Game, Plate Appearance, Substitution, Team, Pitching, Batting, Fielding, Injury`.
Stat code tables and flag strings are read from the BBSIM.dll image (tables at DAT_680ba3f8, 438, 458, 4b0, 4f8, 405,
448, 63c). The event queue and writer are BBSIM FUN_68028b7d / FUN_68028c0a / FUN_68028578 / FUN_68028650 / FUN_6802853f
/ FUN_680286ad.

| type | name (codec kind) | words | fields (codec keys) and evidence |
|---|---|---|---|
| 0 | `enter_game` | 2 | `version`: "EVENT: Enter Game / Version: %d" |
| 1 | `exit_game` | 41 | `game_seconds` (p1; "Game Time %d:%02d:%02d"), `total_outs` (p2; equals the sum of pitcher outs in all 23 games), `unnamed_words_3_17` (p3..p17, unknown), `teams[0]` = {runs p18, hits p19, errors p20, left_on_base p21, unnamed_words_22_36 p22..p36}, `teams[1]` = {runs p37, hits p38, errors p39, left_on_base p40}. Runs match the replayed batter `R` codes per team (team 0 = Away) |
| 2 | `plate_appearance` | 15 | state snapshot before a PA. `pitcher p1, catcher p2, first_base p3, second_base p4, third_base p5, shortstop p6, left_field p7, center_field p8, right_field p9` (formatter's fielder names by slot), `on_deck p10, batter p11` (formatter's "OD" and "AB" labels; `batter` is the at-bat batter, the leadoff 1653 in game 0 of day1), `runner_on_first p12, runner_on_second p13, runner_on_third p14` (formatter's "1B/2B/3B"). The inning/half/outs state is a BBSIM global and is not written |
| 3 | `substitution` | 7 | `team p1`, `player p2`, `sub_kind p3` (0 PH, 1 PR, 2 RP, 3 DS), `batting_order p4` ("BO:%d"), `position p5` (table at DAT_680ba405: P, C, 1B...), `br_field p6` ("BR:%d", meaning unknown) |
| 4 | `team_stat` | 3 | `team p1`, `stat_index p2` into RUN, ER, TP, DP, AB, B1, B2, B3 (DAT_680ba448). Team-level counter events |
| 5 | `pitching_stat` | 4 | `team p1` (the pitching team), `pitcher p2`, `stat_index` = low byte of p3 into AB, B1, B2, B3, HR, RBI, BB, K, HBP, BBI, SH, SF, R, SB, CS, BFP, ER, IR, IRS, PT, KT, WP (DAT_680ba458), `flags` = high byte of p3: 0x800 batter_lefty (BLH), 0x400 pitcher_lefty (PLH), 0x200 starter (SP), 0x100 closer (CL) |
| 6 | `batting_stat` | 4 | `team p1`, `batter p2`, `stat_index` = low byte of p3 into AB, B1, B2, B3, HR, RBI, BB, K, HBP, BBI, SH, SF, R, SB, CS, GDP (DAT_680ba4b0), `flags` = high byte of p3 (always 0 seen) |
| 7 | `fielding_stat` | 5 | `team p1` (fielding team), `fielder p2`, `stat_index` into PO, A, E, DP, PB (DAT_680ba4f8), `position_index p4` (DAT_680ba405) |
| 8 | `injury` | 6 | `team p1`, `player p2`, `injury_type p3`, `duration p4`, `severity p5` ("Type:%d Duration:%d Severity:%d") |

The codec stores numeric `stat_index` as content and writes the stat names as derived `_stat_name` keys, so
edits never touch names. Event kinds are the single key of each event object (the kind is not an editable leaf).

### 2.3 Box-score replay (derived, `_batters` / `_pitchers`)
Rules that reproduce all 23 visible box scores (the referee's exact multiset match). Round 3 changed the row rule
and the putout fallback (both reproduce 23/23; see the bullets):
- Pitcher outs (round 2 model, same 23/23 result). The sim charges each putout (`fielding_stat` PO, team = fielding
  side) to the pitcher in that side's defensive slot 1: BBSIM's Upstats card builder, `FUN_6c003550` (PO case), reads
  `this + (1 + 10*side)*2 + 0xb878` for the pitcher and calls the pitcher stat-0 counter. Slot 1 is the starter from the
  game set-up, and a relief substitution (sub_kind RP = 2) overwrites it: `FUN_6c001980` (applies queued subs)
  writes `this + 0xb87a + 0x14*side`. The replay therefore keeps `cur[team]`: set by an RP substitution (`player`) and
  by every pitching event (`pitcher`). Visible days contain no putout inside an RP window, so round 1's
  "last pitching event" rule and this one agree; the new rule is the one that holds when a putout falls after a
  pitching change but before the reliever's first event.
- Row membership (round 3). A row exists iff one of the row's own fields is non-zero: batter (ab, h, hr, rbi, bb,
  so, r, sb), pitcher (outs, bf, h, hr, bb, so, r). Evidence:
  - Upstats FUN_6c002850 (game start) and FUN_6c001980 (each substitution) call the appearance code `FUN_6c0020e0(..,
    0x20)` for every starter, starting pitcher and substitute, including defensive subs and pinch runners that never
    bat. So appearance is not what the box file keeps.
  - Visible: the only batter with no row is pid 2019 (day2 game 0), whose only batting event is CS (caught stealing;
    CS is not a row field). His appearances are a PR and a DS sub, the same kind of entry as the rowed pinch runners
    552 and 2336, so the exclusion comes from the counted fields, not from the sub kind.
  - Visible: all 456 batter rows and all 128 pitcher rows have a non-zero field; no all-zero row exists.
  - Not visible: a batter whose only events are HBP, SH, SF, BBI or GDP (not row fields). The round 2 rule (any batting
    event but CS) would write an all-zero row for him; the round 3 rule writes nothing. Unverified.
- Batter row `{pid, ab, h, hr, rbi, bb, so, r, sb}` from `batting_stat` events: AB -> ab; B1, B2, B3, HR -> h (HR also
  -> hr); RBI -> rbi; BB -> bb (BBI is not a walk); K -> so; R -> r; SB -> sb. GDP, SH, SF, HBP are not in the row.
- Pitcher row `{pid, outs, bf, h, hr, bb, so, r}` from `pitching_stat` events: BFP -> bf; B1, B2, B3, HR -> h; HR -> hr;
  BB -> bb; K -> so; R -> r.
- `outs`: each fielding `PO` event (type 7, stat 0) is one out (count of PO equals total_outs in all 23 games). It is
  charged to the pitcher in `cur[team]` (last pitching event of that team, or the reliever named by an RP sub). A PO
  before the team's first pitching event (none in the visible games) goes to the team's first pitcher in the stream,
  which is its starter. The starter flag bit (0x200) is not set on those first events, so it is not used.

### 2.4 Box-score files (evidence only, not read by the codec)
Read from the visible `MLBPA97.H??` files (evidence for 2.3; the codec does not open them):
- Header 8 bytes `02 65 ff ff 01 00 8a 0a`, then 2698 bytes: seed `(lo, hi)` + 2696 bytes enciphered with the file
  cipher (BBShell FUN_680264c0). Deciphered, it is the sim's per-side state: side 0 at offset 0, side 1 at 0x533.
  Player table: 40 entries of 21 bytes at side + 0x32 + 21k, pid u16 first. For day2 game 0, the 40 pids equal
  `roster_pids` of both teams in game.bki (40/40 each), which is why the roster is 40 slots (1.4).
  Entry bytes 2..6: a lineup-position bitmask (+2, +4; PH 0x0400, PR 0x0800, RP 0x0001 as in Upstats FUN_6c001980)
  and a batting slot (+6; 1..9 starters, 11 for PH entries).
- A plaintext batter table follows (file offset 2718, 40-byte records = pid + 17 u16 words): AB, B1, B2, B3, HR, RBI,
  BB, K, HBP, BBI, SH, SF, the appearance flag (Upstats 0x159c, always 1 for an appearance), R, SB, CS, GDP.
  In day2 game 0, AB, HR, RBI, BB, K, R and SB equal the box row fields for all 11 players of the table who have a
  row (fit over the 17 records of the first table; h = B1+B2+B3+HR as in 2.3). The table holds 9..16 players per file,
  not every appearance. A CS-only pinch runner (2019, day2 game 0) has a full record (CS = 1) and
  no row. Across the 23 visible files this is the only table record with zero row fields and a non-zero other counter;
  it is the basis of the rule in 2.3.
- The appearance flag does not decide membership: 2019 has it set and no row. Membership is decided by the counters.

## 3. Unverified / open
- Round 2 holdout (day3) failed without a visible reason (the referee hides the error in holdout mode). Round 2 removes
  the raises for the unseen layouts it could identify: optional DIF/ADI/other chunks, non-zero string tails, non-zero
  roster padding. The actual day3 cause is not confirmed. Batter rows and
  pitcher rows are still event-based (see 2.3). A CS-only batter is the one visible exclusion; a holdout could show
  another (e.g. a batter with only SF/SH/HBP events, whose row may depend on roster membership).
- Byte-valued content fields (tuning, depth, flags, DIF block) cannot take a +1 of 255: the referee's edit test would
  need 256 in a byte. No visible byte field is 255 (checked over 8000 byte leaves), so no visible test hits this.
- `tuning_rows`, `tuning_tail`, `depth_table`, `team_code`, `team_flags`, `header_tail`, `schedule_params`,
  `game_code`, `game_seed`, `tail_words`, `unnamed_words_*`, `br_field`, the `lineup_segments` roles beyond the
  listed ones: layout is exact (round trip), meaning is not established.
- `day_key` / `day_key_copy` / `game_no` / `adi_flag` meaning (it looks like a day key and game index).
- `flags` on batting events and the 4-character stat strings past index 15 in the batting table.
- Holdout days: the decoder is generic (sizes from the table, segments by separators, replay from events). Event
  types outside 0..8 raise an error. The sim cannot write them: BBSIM FUN_68028ce3 asserts 0 <= type <= 8 on every
  game.out event (and type 0 must carry version 4).
- Round 3 candidate causes for the day3 failure (none confirmable from this lane): (a) bench players in roster slots
  25..39 (the codec read them as padding, so they were missing from the coverage check and never labelled as players);
  now fixed by the 40-slot roster. (b) a batter with HBP/SH/SF-only events (row rule changed in 2.3). (c) an edit
  of a byte equal to 255 (the referee's +1 needs 256; no visible byte is 255). Unfixed: the byte cannot hold 256.

## 4. Round 2 change log (lane "code")
- bki: ADI/DIF optional per game; unknown chunks kept (`_other_chunks`, `_layout`, `_leading_chunks`).
- bki/bko strings and roster padding: non-zero tails kept as derived `_junk_after_nul` / `_roster_padding` instead of raising.
- bko: non-GDO chunks kept (`_other_chunks`).
- replay: relief substitutions set the outs pitcher (2.3).
- Verification: round trip byte exact on 4 visible files; referee PASS on day1 (9 box scores) and day2 (14);
  holdout-mode check (3 edit rounds, 8 edits, `gamebkref.check_day(..., hold=True)`) passes on both visible days for
  12 seeds each, and on a synthetic day with a DIF chunk, a junk byte after a team-name NUL, roster padding and an
  extra bko chunk (`scratch/synth.py`, `scratch/holdcheck.py`).

## 5. Round 3 change log (lane "code")
- bki: `roster_pids` is the 40-slot table (1.4); `_roster_padding` removed (the slots are content now).
- bko: box rows use the row-field rule (2.3); a putout before a team's first pitching event goes to that team's
  first pitcher in the stream.
- Verification: referee PASS on day1 (9) and day2 (14) via the local jail harness; round trip byte exact on the four
  visible files; holdout-mode sweep (24 runs) and edit stress (12 runs): 0 failures.
