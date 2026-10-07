# MLBPA97.ASN tail log decode (news-pool sectors 0x27e000-0x29a800)

All analysis in `re/tail_log_work/`. Scripts run `python3 -I`. Files touched: only this doc + scratch dir.
All offsets are file offsets in day10 unless noted. Hex notation `xx` = single byte.

## 0. Context: what the "tail log" actually is

The tail of the ASN (0x27e000..0x29a800) is a chain of 512-byte **news blocks** (the Association News pool).
Each block:

- bytes `+0x00..+0x14` (29 bytes): block header (mostly pointer/slot machinery, not decoded further).
- bytes `+0x15 + 25k`: **news records, 25 bytes each, k = 0..17** (18 max per block; `0x15+18*25 = 0x1D7`).
- bytes `+0x1E5..+0x1FA`: slot-array tail (`b1 00 00 00 04` x2; *not* news records - it is the "SMA slot array"
  that the earlier stride-25 scan kept tripping over). A stamp found here is a parse artifact, not an entry.
- byte `+0x1FA..`: start of the next phase; block-boundary strings like `00 12 <ptr>` are the *next* block's head record.

**Every 25-byte record is one Association-News item.** Evidence for the 25-byte stride: every date stamp
(day-stamp field, below) sits at `block + 0x2A + 25k` (k=0..18) in *every* news block on all 10 days - ~800 stamps
checked (step27_enum.py). The task dump's mis-alignments (reported "entry crossing a sector start") came from
scanning from a single anchor instead of per-block.

### Block head record (k=0)

Distinct shape; byte 0 = `00` (head flag), byte 1 = `12` (18 = record capacity), bytes 2-3 = **u16 LE chain pointer**
= address of another news block's ID >> 8:

| block | bytes 2-3 | points to |
|---|---|---|
| 0x299E00 | `a2 29` (0x29A2) | 0x29A200 |
| 0x29A200 | `e6 27` (0x27E6) | 0x27E600 |
| 0x27E600 | `e4 27` (0x27E4) | 0x27E400 |
| 0x29A400 | `a6 29` (0x29A6) | 0x29A600 |
| 0x29A600 | `ec 27` (0x27EC) | 0x27EC00 |
| 0x299C00 | `e2 27` (0x27E2) | 0x27E200 |

Chains link each day's blocks to earlier days' blocks (0x27E400/0x27E000 are era-46 = 1997-season blocks, still
live). Pool-B pointers (below) also live at head bytes 14-17.

### Second parallel structure (Pool-B)

There is a second, older-format news store in 0x30000..0x6D500: **39-byte records, stride 39** (e.g. 0x6BD11,
0x6BD38, ... 912-byte block gaps at 0x6C200). Each starts `fa fa 27`, carries `00 00 00 15 00 00 00 10`, a
**3-byte back-pointer** to the previous record (e.g. rec at 0x6BDD4 has backptr `ad bd 06` = 0x6BDAD =
0x6BDD4-39; rec at 0x6BD11 has `ea bc 06` = 0x6BCEA = 0x6BD11-39 - verified, step-final), a date stamp and a
25-byte news entry embedded in its tail. ~749 `fa fa 27` records on day10. The `ref` field in the 25-byte tail
records points into this store (below). This second pool is the *detailed* news store; only its pointer semantics
were decoded, not its full text.

## 1. Byte-level field map of the 25-byte log entry

For a record at offset `S` (S = block + 0x15 + 25k; date stamp at S+21):

| offset | size | meaning | evidence |
|---|---|---|---|
| 0-1 | 2 | **player id (u16 LE)**, PYR id (100+rec). Claims repeat it at 7-8. Head records instead hold `00 12` (head flag + capacity 18). | `b5 07` = 0x07B5 = 1973 = Bob Wagner 2B (dump_pyr); `e4 08` = 2276 John Aragon SS; `41 03` = 833 Jorge Posada C; `41 03` = 833 in Apr-12 block - see id table below |
| 2-3 | 2 | 0 in normal records (`00 00`). Head records: chain ptr. | every claim row |
| 4-5 | 2 | `01 00` in claim rows, `00 00` otherwise. | step-final byte 4-5 table |
| 6 | 1 | **status flag**: `08` = active claim/hot item; `ff` = idle/back-reference; `00` = head. | claims all `08`; 0x29A22E `ff`; heads `00` |
| 7-8 | 2 | **second id (u16 LE)** = related player id; equal to bytes 0-1 in claim rows, 0 in idle rows, or a *different* player (see sec. 4). | `80 08` = 2176 Sam Wagner inside 2276-Aragon rows |
| 9-12 | 4 | zeros in normal records | claim rows |
| 13 | 1 | **event code** (u8), stable across days for the same event (sec. 2) | 1973 always 08; 2276 codes 09/10/11; 833 codes 03/06 - cross-tab over days 8-10 |
| 14 | 1 | sub-index into the Pool-B record pointed to by 15-17 (head rows use 01; claim rows 06; idle 02) | head of 0x299E00 idx `01`, claims idx `06`, 0x299F8C idx `02` |
| 15-17 | 3 | **Pool-B pointer (u24 LE)** = address of the 39-byte Pool-B record with the item's details | claims point at 0x6BDD4/0x67907; head of Apr-11 block 0x27E600 at `01 70 30 04` = 0x43070 |
| 18-20 | 3 | zeros | all rows |
| 21-22 | 2 | **date stamp u16 LE = (era << 8) \| day-of-season** (see sec. 3) | `d6 2f` = (47<<8)\|214 |
| 23 | 1 | `0b` = 11 - constant in every day10 entry | task-verified, holds for all scans |
| 24 | 1 | `00` terminator | " |

Evidence anchors: `00 12 a2 29 ... 01 d4 bd 06 00 00 00 d6 2f 0b 00` (head of 0x299E00) and
`b5 07 01 00 00 00 08 b5 07 01 00 00 00 08 06 d4 bd 06 00 00 00 d6 2f 0b 00` (Wagner claim).

## 2. Event-type table (byte 13 vs observed events)

Byte 13 = event id per (player, event) pair, stable across saves; byte 6 = the claim-active flag.
Only the two observed event classes on day10 are ground-truthed:

| byte 6 | byte 13 | observed players (ids) | event (ground truth) |
|---|---|---|---|
| `08` | `08` | 1973 Wagner x15 (0x2FD6 x14 + 0x2FD7 x1), 924 Vizcaino x2 | **"team submitted claim for free agent 2B Bob Wagner"** repeated 13x (April 11 transactions) - Feb 27 identical copies |
| `ff` | anything | all other rows | idle/parked news item (day's earlier items, kept until purged) |
| `00` | `00` | head records | block header, not a news item |
| `b1`/`85` | - | - | SMA slot-array artifact (not a record; sec. 0) |

The `ff` rows' codes (01..1c) are per-event ids of *earlier* days' news items (the pool keeps ~a season's worth;
era-46 = 1997 events still parked in 0x27E000-0x27E5FF). Codes for the *same* player-event pair persist across
saves (1973=08 on days 8/9/10, 2276=10 on days 8/9/10). Full type-angle alphabet beyond 08/ff not decodable from
this one save pair alone.

## 3. Date stamp = (era << 8) | day-of-season

- `d6 2f` = (47 << 8) | 214 = April 11 display date. 214-203 = 11; base 203 = March 31 (1998 season opener).
- Verification of the delta: day1 file = (47<<8)|206 (Apr 3), day3 = (47<<8)|208 (Apr 5), day10 = |214 (Apr 11),
  day10 also has |215 (Apr 12) items = 22 of them - the news is written one day ahead of the save's sim date.
- The pool retains old eras: 0x2ED5/0x2ED8 = (46<<8)|event-of-season-1997 blocks live in 0x27E000-0x27E5FF.
- Day09 anchors (0x2FD5, Apr 10 news): 17 entries at 0x299C15-0x299DBD, plus 0x2FD4 (31), 0x2FD3 (33) blocks -
  all *unchanged* day9->day10 (they are history). Day10's new writes touched only the 0x2FD6/0x2FD7 blocks.

## 4. The second id-like group (bytes 7-8) = related player id, not team/money

| bytes 0-1 (player) | bytes 7-8 (2nd id) | interpretation |
|---|---|---|
| 1973 Wagner | 1973 (same) | the claim row references itself (the claimed free agent) |
| 2276 Aragon (SS) | 2176 Sam Wagner (SS) | a *different* player, same position (SS) - best hypothesis: the rival free agent in the same claim pool |
| 1660 Maas (LF) | 1452 Paul Wagner (P) | another cross-player pair (Apr-12 idle row) |
| 534 Eibel | 1967 Lawless | byte 7-8 = a different player again |

Key conclusion: bytes 7-8 = a **player id** (u16 LE, PYR range), *not* a team id, not money. The task's earlier
reads `0x4608/0x1200`, `0x27E6` (10214), `0x29A2` (10658) were **parse artifacts**: 0x1200 = the head record's
`00 12`, and 0x27E6 / 0x29A2 are the **block chain pointers** of the head records (sec. 0).

Team ids: not present anywhere in these 25-byte entries. They live elsewhere (the game renders claims from text
in the Pool-B/0x6D-detailed store, which was only pointer-decoded here).

## 5. Every day10 (April 11, stamp 0x2FD6) entry -> April 11 event

48 April-11 entries total (blocks 0x27E600, 0x299E00, 0x29A200). Changed-vs-day09 = `CHG` (the day10 sim's writes).
Player names from `dump_pyr.py` on the player DB; positions + roles from the ground-truth text.

| offset | k | player | byte6 | byte13 | 2nd id | event interpretation | changed |
|---|---|---|---|---|---|---|---|
| 0x27E615 | 0 | head (ptr 0x27E4) | 00 | 00 | 0 | block header -> 0x27E400 (prev day chain) | CHG |
| 0x27E62E | 1 | 275 = Al Pechous 1B | ff | 1c | - | idle item (Pechous news) | CHG |
| 0x27E647..0x27E6F6 | 2-9 | 534 = Ray Eibel 2B (8 rows) | ff | 15 | - | idle item (Eibel, code 15) | CHG |
| 0x27E70F | 10 | 534 Eibel | ff | 15 | - | idle item (same event, older pool-B ref 0x47711) | |
| 0x27E728 | 11 | 534 | ff | 17 | - | idle item | |
| 0x27E741 | 12 | 534 | ff | 1a | - | idle item | |
| 0x27E75A | 13 | 534 | ff | 1b | - | idle item | |
| 0x27E773 | 14 | 1341 = Angel Scanlan 2B | ff | 11 | 1967 Lawless 2B | idle item | |
| 0x27E78C | 15 | 833 = Jorge Posada C | ff | 03 | - | idle item | |
| 0x27E7A5 | 16 | 833 Posada | ff | 06 | - | idle item | |
| 0x27E7BE | 17 | 333 = Brant Brown 1B | ff | 1c | 1045 | idle item | |
| 0x27E7D7 | 18 | 371 = Curtis Goodwin CF | ff | 13 | - | idle item | |
| 0x299E15 | 0 | head (ptr 0x29A2) | 00 | 00 | 0 | block header -> 0x29A200 | CHG |
| 0x299E2E-0x299F5A | 1-13 | 1973 = Bob Wagner 2B | `08` | 08 | 1973 | **April 11: "TEAM submitted claim for free agent 2B Bob Wagner"** x13 identical (claim pile-on; matches ground truth) | CHG |
| 0x299F73 | 14 | 1973 Wagner | `08` | 08 | 1973 | same claim event, different pool-B ref (0x67907) = a second claim copy | CHG |
| 0x299F8C | 15 | 2276 = John Aragon SS | ff | 10 | 2176 Sam Wagner SS | idle item (Aragon, 2nd id Sam Wagner) | CHG |
| 0x299FA5 | 16 | 2276 Aragon | ff | 10 | 2176 | same as above (duplicate row) | CHG |
| 0x29A0C4 | 7 | 881 = Darren Lewis CF | ff | 14 | - | **unresolved (old row)**: sits in block 0x29A000, unchanged on day10 (belongs to an earlier day's news, kept in pool) | |
| 0x29A0DD | 8 | 534 Eibel | ff | 15 | - | same as above (old row in 0x29A000 block) | |
| 0x29A215 | 0 | head (ptr 0x27E6) | 00 | 00 | 0 | block header -> 0x27E600 (the chain: 0x29A200 -> 0x27E600 -> 0x27E400) | CHG |
| 0x29A22E | 1 | 833 Posada | ff | 06 | - | idle item (Posada, code 06) | CHG |
| 0x29A247 | 2 | 833 Posada | ff | 06 | - | same event, different pool-B ref | CHG |
| 0x29A260 | 3 | 371 Goodwin | ff | 13 | - | idle item | CHG |
| 0x29A279-0x29A2DD | 4-8 | 1660 = Dave Maas LF | ff | 19 | 1452 | idle item x5 duplicate rows | CHG |
| 0x29A3D7 | 18 | - | b1 | 85 | - | **not a news entry**: SMA slot-array artifact (`00 04 05 05 62 b1 ... 04 05 06 85 b1`) | |

### Notes on the ground truth

- "Apr 11: <TEAM> submitted claim for free agent 2B Bob Wagner" xN teams -> the 13 identical 1973 Wagner rows
  (0x299E2E-0x299F5A) + the 14th row 0x299F73 (14 claim rows all `06 d4 bd 06`-ref except the last = `06077906`).
- "awarded free agent" lines = not visible in the day10 0x2FD6 rows; they'd be a different byte-13 code on the
  *winning team's* copy of the claim. Best hypothesis: byte 13 = the same event id (08) with byte 6 = 0xff and the
  pool-B ref advanced; not determinable from this save pair.
- The 6 NL games / AL games and the ATL-FLA box score are **not** in the news pool. Game data lives in the
  `fa fa 22` 34-byte lineup-record region 0x30000-0x6D500 and elsewhere (0x31613-0x31A00 changed on day10 =
  ~4 blocks of Apr-11 game lineups). Decoding those 34-byte records is outside the tail-log scope.
- The April 12 claims pile (`0x2FD7`, the 29A400/29A600 blocks) is in the day10 file too: 924 Vizcaino 2B claims
  x2 (0x29A4C4/0x29A4DD) + 1973 Wagner x1 (0x29A528), and idle rows for 645 Mueller 3B, 1161 Cora 2B, 658 Jensen C,
  2221 Bross LF, 1967 Lawless 2B, 903 Snopek 3B, 371 Goodwin, 833 Posada.

## 6. Unresolved / open questions

1. Exact meaning of the 0xff vs 0x08 vs 0x00 alphabet at byte 6 for events beyond "claim" (only 08/ff/00 observed
   on day10).
2. Head-record byte 5: 0x0C/0x09/0x0D = count-looking values in the 0x29A400/0x29A600/0x27EC00 blocks
   (12/9/13 = their stamped-record counts), but `00` in all news blocks - semantics unclear.
3. Head-record bytes 7-8 (0x2C 01 / 0xE1 00) = unexplained.
4. Pool-B (39-byte records, `fa fa 27`) internal layout: back-pointer verified, date + embedded 25-byte entry
   verified; full text/item layout not decoded.
5. The `fa fa 22` 34-byte lineup/game-result records (28 in 0x30000-0x6D500): not decoded (out of scope).
6. Byte 9-12 = zeros in all observed rows; using them as a length/other field is speculative.

## Scripts (scratch)

All in `re/tail_log_work/`: step1_diff.py .. step27_enum.py. Key one: step27_enum.py (per-block stamp
enumeration with the `+0x15 + 25k` model - reproduces every table cell above).
