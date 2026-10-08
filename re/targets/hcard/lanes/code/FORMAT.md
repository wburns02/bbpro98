# H-file lineup card format (FPS Baseball Pro '98) — code lane

> **Superseded 2026-10-07 by work/spec/HCARD_FORMAT.md + work/hcard.py.** Body is 0xa88 bytes (not 2698-10), 0xa70 is time of game, 0xa76 total outs, bat spots start at 0x3cb, bit 11 = pinch runner, slot +7..+20 are seven u16 counters, the date is not fixed to April. Container, cipher use and positions mask are right. Kept as the lane record.

Status: PORTED, verified and leak-guard CLEAN. `hcard.py` round-trips all 104
distinct H files of day01–day10 byte for byte and PASSES every visible referee
check (`hcardref.py`: schema, team ids, abbrev/name vs league, month/day vs
schedule, players/slots/roster, pitchers, positions vs masks and fielding
changes, `encode(decode(x)) == x`, edit tests on day05/day09). Referee tail:
PASS (round 1 and round 2 after the rewrite).

## File layout

An H file is a row of records of varying length. The FIRST record (2698 bytes)
is the enciphered lineup card; the plaintext box tables follow
(`rec 40` batting, `rec 70` pitching, `rec 22/36/150` others — see
`re/hfiles/lanes/data/hdecode.py`).

```
card record: 02 65 | ff ff | 01 00 | 8a 0a | seed[2] | ciphertext[2696]
```

The two seed bytes build the game's substitution table (BBShell
`FUN_68053450`, the sentinel walk documented in
`re/targets/cipher/lanes/data/CIPHER.md`), and the stored bytes are `plain`
pushed through the table THREE times (`FUN_68053510` / `FUN_680264c0` chain:
read 0xa8a bytes, build the table from `this[0]`/`this[1]`, decipher 0xa88
bytes into `this+2`). Decoding is the inverse applied once per byte.
BBShell `FUN_680117a0` copies the deciphered table into the working struct and
`FUN_680265d0` / `FUN_68026600` hand out per-side copies and the game tail.

## Deciphered card body (2688 bytes = 0xa80)

Two side structs of 0x533 bytes: **side 0 = AWAY at 0x000**, **side 1 = HOME
at 0x533**, followed by the game tail at **0xa66** (26 bytes).

### Side struct (offsets side-local)

| offset | size | name | meaning + evidence |
|---|---|---|---|
| +0x00 | u16 | `team_id` | box-score tid (1..28) **in BOTH bytes** — the tid is duplicated low and high in all 986 side blocks (verified; round 1's "bit 8 = played flag" reading was wrong). |
| +0x02 | 9 | `assoc` | association name, NUL-padded ("MLBPA97") |
| +0x0b | 34 | `name` | team name, NUL-padded ("Florida") — == league `name` |
| +0x2d | 5 | `abbrev` | team abbrev ("FLA") — == league `abbrev` (referee checks both) |
| +0x32 | 40 x 21 | player slots | 40 slots, see below |
| +0x37a | 1 | `lineup_entries` | count n (9..18): the number of batting-order entries = the 9 starters first, then every sub who batted in entry order. **Not** 9 + a separate list. |
| +0x37b | n x u16 | `batting_order` | all order entries (LE u16 pids): starters first, then batted subs. Every entry nonzero, no duplicates (986/986 sides). |
| +0x37b+2n .. +0x3cc | | (zeros) | zero padding |
| +0x3cc | n | `bat_slot` | one byte per order entry: `i+1` for i = 0..7 ALWAYS (898/898 sides with n >= 9); entry 8 = 0 in 73 sides (the 9th slot: NL pitcher) and 7/8 in the rest; sub entries = usually 8, the last entry = 0 on all 986 sides. Reads like the scorebook slot/sequence number of the entry; exact semantics not fully confirmed (not the fielding position code — entry 0 has value 1 for non-pitcher leadoff batters). |
| +0x3f0 | 3 | (zeros) | padding |
| +0x3f3 | 1 | `pitchers_count` | |
| +0x3f4 | m x u16 | `pitchers` | pids in mound order, STARTER FIRST. Set-equal to the box pitching table's pids (rec 70) for all 986 side blocks; m == the number of used pitchers. |

Player slot (21 bytes, at `0x32 + 21*i`):

| offset | size | name | meaning |
|---|---|---|---|
| +0 | u16 | `pid` | 0 = empty. |
| +2 | u16 | `positions_mask` | **positions played this game**: bit 0=P, 1=C, 2=1B, 3=2B, 4=3B, 5=SS, 6=LF, 7=CF, 8=RF. A player is a USED PITCHER iff **bit 0 is set** (== box pitchers rec 70, 1972/1972 side records); non-pitchers have positions in bits 1..8; bench players have 0. **Bit 9 = DH** (w6 role code 10; the DH is in the batting order with no fielding position, 102 slots), **bit 10 = pinch-hitter role** (code 11, 145 slots; on 12/493 blobs it rides along with a second fielding position, e.g. PH then 2B), **bit 11 = a third rare role** (code 12, 3 slots in 104 games). The codec preserves bits >= 9 verbatim. |
| +4 | u16 | `starting_role` | the position the player held AT FIRST PITCH (same bit numbering): starting position players have their fielding position, the starting PITCHER has bit 0 (0x001), RELIEVERS have 0 (353/353 reliever slots), DHs have 0x200, subs who entered later have 0. 4843/5200 slots match the derived rule exactly; the 3 remaining exceptions are multi-position starts (the slot echoes only the STARTING spot, e.g. CF though he ended in LF). |
| +6 | u16 | `role_code | pitch_count<<8` | low byte = the player's role code, ALWAYS the lowest set bit of `positions_mask` + 1 (5199/5200 slots): 1=P..9=RF, 10=DH, 11=pinch hitter, 12=the rare code, 0=bench/empty. High byte = nonzero only for pitchers (1..141, 109 distinct): matches no box pitching column (checked all 32); consistent with a PITCH COUNT (96 for a 6-inning CG start, 7/11/14/33 for short relief) but unconfirmed. |
| +8 | 13 | `spare` | all zeros in every observed file; preserved verbatim |

### Game tail (0xa66..0xa80, 26 bytes)

| offset | name | evidence |
|---|---|---|
| 0xa66 | u8 = 1 (always) | record marker |
| 0xa67 | 9 chars | **home city** — == the league's `city8` for the HOME team for all 104 files, NUL-padded ("CLEVELAN") |
| 0xa70 | u16 | **game id**: 97 distinct values for 97 distinct games (7849..14301). Failed every semantic hypothesis (attendance/…, roster sums/xors, box totals, schedule aux) — a per-game identifier of unknown derivation. |
| 0xa72 | **u32 day serial** | the game date as the sim's day serial. Verified: `serial - 733131` == the schedule day-of-month for 95/95 newly played games (April 1997; 733132 = April 1, season day 1). **The card stores NO month/year — the codec maps serial→(month=4, day) via this verified season calendar.** |
| 0xa76 | u8 | **temperature °F** (51..78 over 10 distinct values) |
| 0xa77 | u8 | sky/game-condition code?, unconfirmed |
| 0xa78 | u8 | game-time-ish, unconfirmed |
| 0xa79 | u8 | game-length-ish, unconfirmed |
| 0xa7a | u8 | 0..9 (schedule slot?), unconfirmed |
| 0xa7c | u8 | 1..7 (innings-ish?) |
| 0xa7d..0xa7f | u8 x3 | attendance-digit-like, unconfirmed |

### Stale vs current data

The card was pre-filled at the game's START and patched as the game went; some
regions keep both the starting state (slot `starting_role`) and the final
state (slot `positions_mask`). The `raw_after_*` regions (zeros + leftover
blocks) are preserved verbatim by the encoder.

## Verified evidence summary

- 104 distinct H files across day01–day10; all round-trip byte for byte.
- 95/95 newly played schedule games: `(month=4, day=serial-733131)` matches.
- 986 side blocks: tid duplicated in both bytes of side+0.
- pitchers list @0x3f4 == box pitchers (rec 70) for 986/986 side blocks.
- Home city == league city8 for 104/104 files (493/493 in round 1).
- positions: mask bits 0..8 == the fielding-line changes in the stats database
  for every player in exactly one game that day (referee check, PASS on all days).
- role_code == lowest set mask bit + 1 for 5199/5200 slot words.
- starting_role == held position at first pitch for 4843/5200 slots (rest are
  multi-position/relief edge cases, all consistent).
- bat_slot[i] == i+1 for i = 0..7 on 898/898 sides.
- BBShell `FUN_680264c0` (read 0xa8a, build table from `this[0]`/`this[1]` by
  `FUN_68053450`, decipher 0xa88 into `this+2`), `FUN_680117a0` / `FUN_680265d0`
  (copy per side, stride 0x533), `FUN_68026600` (copy the game tail).

## What the codec edits

`encode` applies from `edited.json`: `game.month/day` (via the season
calendar), `game.home_city`, `game.game_id`, `game.temperature_f` + every
other named tail byte, each side's `abbrev`/`name`/`assoc` and each player's
`positions` (+ optionally `bat_position`). Everything else (roster slots,
pitchers, batting order, masks' high bits, raw regions) is preserved verbatim
from the input file, then the body is re-enciphered with the input file's
seed.
