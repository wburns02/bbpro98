# Box-score lineup card (first record of Stats/<assn>.Hxx)

Codec: `work/hcard.py` (decode/encode JSON). Every byte of the card is a named field. It round-trips all 118 distinct
H files from the 10-day sim byte for byte and passes `re/targets/hcardref.py` both visible and `--holdout`.

The hcard GLM lane (`re/targets/hcard/lanes/code`) cracked the container and the slot mask. Claude remapped the rest
from these sources:
- Upstats: FUN_6c002850 (team blocks and slots), FUN_6c001980 / FUN_6c001800 (substitutions), FUN_6c002b00 (game
  facts) and the event handlers FUN_6c002fa0 / FUN_6c003320 / FUN_6c003550 (the slot +7/+9/+11 counters are near
  `_all.c` lines 1581-1590 and 1675).
- BBShell, read side: FUN_680264c0 (decipher), FUN_680265d0 / FUN_68026600, FUN_680117a0 (copies side 0 to struct
  +0x149a, side 1 to +0x19cd and the tail to +0x1f00), and the box printers FUN_6800fe70, FUN_68010080, FUN_680104c0
  (near `_all.c` lines 12080-12270, 12530-12710 and 13087-13180).
- EZShell weather generator: FUN_6a01a9d0 / FUN_6a01a5e0 / FUN_6a01a360, with the GDI setters at 0x6a017f90..0x6a017fd0.

Differences from the lane's FORMAT.md:
- The record is 8 + 0xa8a bytes (seed + 0xa88 body). The lane used 2698 and left the 8 rain-delay bytes opaque.
- 0xa70 is the time of game in seconds, not a game id.
- 0xa76 is the total outs, not the temperature.
- The batting-spot array starts at 0x3cb (the lane was off by one).
- Mask bit 11 is pinch runner.
- Slot bytes +7..+20 are seven u16 counters. They are not padding.
- The team name is two 17-byte strings.

## File

| Off | Size | Field |
|---|---|---|
| 0x000 | 8 | record header `02 65 ff ff 01 00 8a 0a` (tag, count 1, size 0xa8a) |
| 0x008 | 2 | cipher seed |
| 0x00a | 0xa88 | card body, enciphered (`work/fpscipher.py`: base table composed three times) |
| 0xa92 | rest | plaintext box-score tables (batting/pitching lines, play text), not touched by this codec |

Body = side 0 (away) at 0x000 + side 1 (home) at 0x533, 0x533 bytes each, + game tail of 0x22 bytes at 0xa66. In
Upstats the card sits at `this+0xa8a`.

## Side (0x533 bytes)

| Off | Field |
|---|---|
| 0x000 | u8 team id (GDI team byte, FUN_6c007240) |
| 0x001 | u8 box-score team row: the team id, except 10 + side when the game type is 0 or 3 |
| 0x002 | association, 9-byte string |
| 0x00b | team name, 17-byte string (GDI team +0x0c; the box prints it as %16s) |
| 0x01c | second name string, 17 bytes (GDI team +0x1d). It is empty in every file and never read by the box screen. |
| 0x02d | abbrev, 5-byte string (GDI team +0x3f) |
| 0x032 | 40 player slots of 21 bytes (layout below), filled from the GDI roster at team +0xd9 |
| 0x37a | u8 lineup entry count n |
| 0x37b | 40 × u16 lineup pids, in order of appearance |
| 0x3cb | 40 × u8 lineup spot, 0-based. A sub carries the spot he replaced. |
| 0x3f3 | u8 pitcher count |
| 0x3f4 | 40 × u16 pitchers, in mound order (starter first) |
| 0x444 | u8 "pitched to" note count (max 25) |
| 0x445 | 25 × 8-byte notes: u16 pid, u16 game outs when he entered, u16 batters faced, u16 outs (0 in all data). Box string "%s pitched to %d batter%s in the %s." |
| 0x50d | u16 runs |
| 0x50f | 30 × u8 runs per inning |
| 0x52d | u16 team left on base (box string idx 87) |
| 0x52f | u16 double plays (idx 91; Upstats event 3) |
| 0x531 | u16 triple plays (idx 92; Upstats event 2) |

Bytes past each list's count are zero in every posted card. The codec keeps any that are not as `_unused_*` hex.

### Player slot (21 bytes)

| Off | Field |
|---|---|
| +0 | u16 pid (0 = empty slot, all 21 bytes zero) |
| +2 | u16 positions-played mask. Bits 0..8 are P C 1B 2B 3B SS LF CF RF; bit 9 DH; bit 10 pinch hitter (sub type 0); bit 11 pinch runner (sub type 1). Bits 12..15 are never set. |
| +4 | u16 starting-position mask, same bits |
| +6 | u8 role: 1..9 position, 10 DH, 11 PH, 12 PR, 0 bench |
| +7 | u16 pitches (event 0x13) |
| +9 | u16 strikes (event 0x14) |
| +11 | u16 pickoffs (event 0x10; box "PickOff:" via 0x312) |
| +13 | u16 season holds |
| +15 | u16 season saves |
| +17 | u16 season wins |
| +19 | u16 season losses. +13..+19 feed the W/L/HLD/SV decision lines. |

JSON: `positions` holds bits 0..8 and `roles` holds bits 9..11 (`dh`, `ph`, `pr`), `started_at` is the +4 mask and
`role` is the code name. Upstats events 0 and 1 (errors, passed balls) go to `this+0x1520/0x1524` and are not in the
card.

## Game tail (body 0xa66, 0x22 bytes)

| Off | Field | Source |
|---|---|---|
| 0xa66 | u8 game type: 1 league game (BBShell tests ==1), 0 exhibition (stats file removed), 3 special game with box rows 10/11 (all-star, inferred) | GDI 999 |
| 0xa67 | home city, 9-byte string (city8) | GDI 0x3eb |
| 0xa70 | u16 time of game in seconds (shown h:mm) | |
| 0xa72 | u32 day serial = proleptic Gregorian ordinal + 365 (FUN_68049250). 733132 = 2007-04-01, a Sunday. Weekday = (serial - 1) % 7, 0 = Sunday. | GDI 0x405 |
| 0xa76 | u16 total outs in the game (51 or 54 for 9 innings; innings = (outs + 5) // 6) | |
| 0xa78 | wind direction 0..7 | GDI 0x3d4 |
| 0xa79 | wind mph 0..40 | GDI 0x3d5 |
| 0xa7a | sky 0..4 | GDI 0x3d6 |
| 0xa7b | temperature °F, 35..105 | GDI 0x3d7 |
| 0xa7c | rain kind | GDI 0x3d8 |
| 0xa7d | rain start out | |
| 0xa7e | rain span in outs (start + span ≤ 51) | |
| 0xa7f | delay count; Upstats truncates it to delays before the game ended | |
| 0xa80 | 4 × u8 delay game-out marks | |
| 0xa84 | 4 × u8 delay minutes | |

Wind directions: 0 in from center, 1 in from left, 2 left to right, 3 out to right, 4 out to center, 5 out to left,
6 right to left, 7 in from right (box strings 125 + dir).

Weather generator:
- Sky 0..2 is dry.
- Sky 3 rolls rain kind 0..3; sky 4 rolls kind 2..5.
- A dome sets sky 0, 72°F, wind 0/0 and kind 8.
- Kinds 6 and 8 mean no rain. Rain bytes past the count, and the whole rain block when there is no rain, are stale
  leftovers. The codec keeps them as is.

Box strings: "Rain delay of %d minutes in the %s inning", with inning = outs // 6 + 1.

## JSON keys

```
{"game": {game_type, home_city, time_of_game_seconds, year, month, day, outs, wind_direction, wind_mph, sky,
          temperature_f, rain: {kind, start_out, span_outs, delay_count, delay_outs[4], delay_minutes[4]},
          _time_of_game, _day_serial, _weekday, _wind_direction},
 "sides": [{side, team_id, box_team_row, association, name, alt_name, abbrev,
            players: [{slot, pid, positions, roles, started_at, role, pitches, strikes, pickoffs,
                       season_holds, season_saves, season_wins, season_losses}],
            lineup: [{pid, spot (1-based)}], pitchers: [pid], pitched_to: [{pid, entered_at_out, batters, outs}],
            runs, linescore (trailing zero innings past the 9th trimmed), left_on_base, double_plays, triple_plays}]}
```

`_` keys are derived and ignored on encode. The date is rebuilt from year, month and day, and an out-of-range day rolls
into the next month. Encode rebuilds the whole body from JSON under the input file's seed and copies the header and box
tables verbatim.
