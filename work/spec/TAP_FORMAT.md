# Instant-replay tapes (hilights/*.tap) and the tape queue (MLBPA97.NQ0)

Codec: `work/tapcodec.py` (decode/encode JSON). Every byte is a named field. It round-trips all 7 sample files
(4 tapes, 1 queue holding 5 tapes, 2 more tapes) byte for byte and passes `re/targets/voldatref.py` visible and
`--holdout`. Coverage is off for this target (`re/targets/tap/files.json`): the printable runs left in a tape are int
words in the frame records and stale string padding, which the codec keeps byte-exact.

The tap data lane (`re/targets/tap/lanes/data`) won with a tokenizer: printable runs became text and everything else
became u32 "playback words". Its NQ0 container was right. Its FORMAT.md calls FUN_6807ac99 the writer; that is the
snapshot restore. Claude mapped the rest from BBSIM (the Vcr object):
- file: FUN_680737fc save, FUN_680736c4 load, FUN_68079e75 checksum check, FUN_680ac5f3 checksum
- snapshot: FUN_6807adde write (size checked as 0x41b by FUN_6807ac99 restore)
- frames: FUN_68079aee write, FUN_680ac376 raw record, FUN_680ac3f7 delta record

## File

| Off | Size | Field |
|---|---|---|
| 0x00 | 2 | u16 version 0x2b |
| 0x02 | 80 | caption, NUL-padded (Vcr +0x367). The replay menu shows it. Stale bytes after the NUL are kept. |
| 0x52 | 2 | u16 frame count (Vcr +0x359) |
| 0x54 | 4 | u32 tape length (Vcr +0x1b) = file size - 0x5c |
| 0x58 | 4 | u32 checksum of the tape (Vcr +0x1f) |
| 0x5c | len | tape: snapshot (0x41b bytes), then frames |

Checksum (FUN_680ac5f3): for each tape byte, MSB first, `hi = c & 0x8000; c = (c << 1) & 0xffffffff; c |= bit;
if hi: c ^= 0x1021`. It is CRC-16/XMODEM shifted through a 32-bit register that is never masked, so the stored value
is 32 bits. The loader rejects a tape whose checksum does not match. Encode recomputes length, count and checksum.

## Queue (MLBPA97.NQ0)

u16 version (5), then per entry u16 tag (0x4000 | id), u32 length, and a whole tape file. The sample holds ids 1..5.
JSON: `{"version", "tapes": [{"id", "tape": <tape JSON>}]}`.

## Snapshot (0x41b bytes, FUN_6807adde)

The snapshot is the game state when the tape was saved, after the play. The caption describes the situation before
it (highlight004: caption "TOR 1, PIT 0 T-3rd O-0 Loaded", snapshot PIT 1 run and 1 out).

| Off | Size | Field | Writer |
|---|---|---|---|
| 0 | 2 | batting side, 0 away, 1 home (FUN_680027c0) | FUN_6806a8d4 |
| 2 | 2 | inning-state +0x00 (0xc020 or 0xc021 in the data) | |
| 4 | 2 × 0x22 | team state (away, home), layout below | |
| 72 | 4 | u8 balls, strikes, outs, inning (init 0, 0, 0, 1) | |
| 76 | 2 | u16 clock: +150 per half inning (FUN_6806acc0), read by FUN_6806a578 | |
| 78 | 2 × 0xcd | team records (away, home), layout below | FUN_68032f7b, object +0x45d |
| 488 | 41 | game setup, layout below | |
| 529 | 14 | stadium data file ("TORONTO.DAT") | FUN_6806fa61 |
| 543 | 14 × 36 | persons: 9 fielders, then 5 offense (batter, runners, on-deck) | FUN_6802e385, FUN_68061b28 |
| 1047 | 4 | u32 object +0x7e (or +0x82 when +0x7e is 0); 1 in the data | FUN_6804d42d |

Team state (0x22 bytes, accessors FUN_6806a0e5 / FUN_6806a1d4 / FUN_6806a25a / FUN_6806a2e0):
u8 runs, 30 × u8 runs per inning, u8 hits (+0x1f, FUN_68027840 counts a hit and clears the count), u8 errors (+0x20,
FUN_680268f0 charges the fielding side), u8 left on base (+0x21, FUN_68027880 adds to it). The box line prints R, H, E
from these. JSON trims scoreless innings past the 9th.

Team record (0xcd bytes), copied by the game-set init FUN_68031e2f from the GDI team block:
byte 0 = GDI team byte (team id), byte 1 = GDI team +5, then GDI team +0x0c..+0xd6:

| Off | Size | Field |
|---|---|---|
| 0x02 | 17 | name (team +0x0c) |
| 0x13 | 17 | alt name (team +0x1d), empty in the data |
| 0x24 | 17 | manager (team +0x2e) |
| 0x35 | 5 | abbrev (team +0x3f) |
| 0x3a | 9 | team +0x44..+0x4c, zero in the data |
| 0x43 | 33 | stadium (team +0x4d) |
| 0x64 | 9 | city8: the 8-character DOS stem of the stadium file ("PITTSBUR", "TORONTO.") |
| 0x6d | 96 | uniform palette, 32 RGB triples (two 16-shade ramps) |

Game setup (41 bytes at object +0x5f7):

| Off | Field |
|---|---|
| 0 | u8 game mode: GDI 0x3e6, or 5 when GDI 0x3e7 is 4. Tested for 0..5 across BBSIM. |
| 1 | u8 GDI 0x3e7 (0 when the mode was forced to 5) |
| 2 | u8 GDI 0x3e8 |
| 3 | 14-byte stadium file: home city (GDI 0x3eb) with its "." replaced by ".dat", or ".dat" appended (FUN_68031e2f) |
| 17 | 14-byte association file ("MLBPA97.NQ0") from GDI 0x3f4 |
| 31 | u32 day serial (proleptic Gregorian ordinal + 365, as in the H card), u8 month 0..11, u8 day 0..30, u16 year. Set together by FUN_680327ed(serial), called from FUN_68031e2f; the screen prints "%s, %s %d, %d" from them. |
| 39 | 2 × u8 per side: 1 when team bytes +0x1b × 3 + +0x1c × 4 + +0x1d × 2 < 0x480 (`low_rating`) |

JSON keeps year, month (1-based), day (1-based); encode rebuilds the serial. A date that does not match its serial
would be kept raw as `_raw_date`.

Person (36 bytes): first name 17, last name 17, u16 uniform number (actor +0x70, +0x81, +0x6e). Unused slots are
empty; the data repeats a runner in several offense slots.

## Frame (FUN_68079aee)

1. Camera, 28 bytes (FUN_680157e8 on the global camera at 0x680d5460): u16 +0x58, u16 +0x5b, u16 angle +0x11,
   u16 angle +0x15, 3 × i32 position +0x05/+0x09/+0x0d (the debug overlay prints "(%d, %d, %d) [%04hx, %04hx, %04hx]"
   from +0x05..+0x15), 3 × u16 +0x61, u16 +0x67.
2. Ball flight (FUN_680490ca on the ball): u8 flag (+0xe8c, cleared after writing), u32 +0xe70. When the flag is 1:
   u32 n (+0xe74), u32 +0xe78, +0xe7c, +0xe80, +0xe84, +0xe88, then n + 1 points of 3 × i32 (+0x60). JSON keeps the
   path only when present; n comes from the point count.
3. State record, 408 bytes. Frame 0 stores it whole (FUN_680ac376). Every later frame stores u32 k, then k pairs
   of (u32 word index 0..101, u32 new value) for the words that changed, in ascending order (FUN_680ac3f7). Every
   stored word changes; encode re-deltas by comparison and reproduces the files exactly.

State record:

| Off | Size | Field |
|---|---|---|
| 0 | 30 | ball (FUN_68048e56): u16 state +0x0c, u16 +0x50, u16 +0x52, 3 × s16 position +0x00, 3 × s16 velocity +0x06, u32 +0x44, +0x40, +0x4c |
| 30 | 8 | u16 sim +0xe92, u32 sim +0xea8, u16 global 0x680b80b4 (FUN_6800972a) |
| 38 | 4 | u32 fielding object +0x2f |
| 42 | 9 × 18 | fielders: actor (10) + u32 +0x2a5 + u32 +0x2a9 (FUN_6802d8a3). Order 1B, 2B, 3B, SS, P, C, RF, CF, LF in the data. |
| 204 | 5 × 26 | offense: actor + u32 +0x2b9, +0x2a9, +0x2ad, +0x2b1 (FUN_6805de6a) |
| 334 | 6 × 10 | umpires: actor only. 1B, 2B, 3B, home (0, -225), two line umpires at (±4879, 4879). |
| 394 | 2 | u16 +0x1d (FUN_68078374) |
| 396 | 6 | u32 +0x3390, u16 +0x3394 (FUN_68047f66) |
| 402 | 4 | u8 global 0x681ec180, 3 bytes global 0x681ec194 (FUN_6806eed4) |
| 406 | 2 | u16 written from an uninitialized local (FUN_68079de6), stack garbage |

Actor (10 bytes, FUN_68005985): s16 x (+4), s16 y (+6), u16 z (+0x10, about 144 standing), s16 heading (+0x0e,
-32768 faces home), u8 animation (+0x1e), u8 +0x2e. Units are 1/30 ft with home plate at (0, 0) and +x toward
first base: 1B bag (1909, 1909), 2B (0, 3818), pitcher y = 1815 (60.5 ft), batter (±60, 0).

Fields named `at_0x..` / `global_..` are stored and editable but their meaning is not labelled yet (ROADMAP #10).

## JSON keys

```
{caption, snapshot: {state: {batting_side, at_0x00, teams: [{runs, linescore, hits, errors, left_on_base}] x2,
                             balls, strikes, outs, inning, clock},
                     team_records: [{team_id, setup_5, name, alt_name, manager, abbrev, unused_0x44, stadium, city8,
                                     uniform_palette: [[r, g, b]] x32}] x2,
                     game: {game_mode, setup_mode, setup_0x3e8, stadium_file, association_file,
                            date: {year, month, day}, low_rating: [a, b], _day_serial},
                     stadium_dat, fielders: [{first_name, last_name, number}] x9, offense: [...] x5, at_0x7e},
 frames: [{camera: {...}, ball_flight: {at_0xe70, path?: {at_0xe78.., points: [[x, y, z]]}}, record: {...}}],
 _frame_count, _tape_length, _checksum, _stale_strings?}
```

`_` keys are derived and ignored on encode, except `_stale_strings` (path -> original field hex), which puts the
bytes after a string's NUL back when that string is unchanged.
