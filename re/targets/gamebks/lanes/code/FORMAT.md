# game.bki / game.bko: the BBShell <-> simulator hand-off (FPS Baseball Pro '98)

Codec: `voldat.py` (decode / encode, byte-exact round trip on day1 and day2).
Evidence tags: **[code]** = read in a decompile, **[data]** = checked against the visible files, **[guess]** = naming
not proven.

## Container (both files)

A stream of chunks `tag[4] | u32 LE payload length | payload`. [code] BBShell `FUN_68060f90` (writes the status byte),
Baseball.exe `FUN_00404720`, BBSIM `FUN_680324d9`, FastSim `FUN_68028f54` (GDI/ADI reader), FastSim `FUN_68029695`
(GDO reader) all walk the stream this way.

* game.bki (`game.in`, written by the shell): per game `GDI:` (1031 bytes) then `ADI:` (12 bytes).
* game.bko (`game.out`, written by the simulator): per game one `GDO:` (8-15 KB).
* Game i of game.bki is game i of game.bko, and game i's box score is `game_setup.box_score_file`. [data] 23/23.

## Cipher

GDI payload = 2 seed bytes + 1029 enciphered bytes; the ADI payload (12 bytes) is enciphered with the SAME table
(seed taken from the GDI before it). [code] FastSim `FUN_68028f54`: reads the two seed bytes, builds the table
(`FUN_680881c6`), deciphers the 0x405 = 1029 GDI bytes (`FUN_68088395`) and then the 10 ADI bytes with the same object.
Algorithm: see `ref/CIPHER.md`, copied into `voldat.py`. The seed is kept in the JSON as `_cipher_seed` so the rebuild
is byte-exact (the shell picks it at random per game).

## GDI plaintext (1029 bytes)

`away_team` (490) + `home_team` (490) + `game_setup` (49). Team index 0 = Away/Visitors, 1 = Home. [code] FastSim
event strings (`DAT_6808e5b0` = "Away","Home") and every `* 0x1ea` access (0x1ea = 490 = one team block). [data] bko
team 0 bats first and holds the batters of block 0.

### Team block (offsets inside the 490 bytes)

| off | size | key | notes / evidence |
|---|---|---|---|
| 0 | 1 | team_id | 1..28 [data] |
| 1 | 1 | league_id | 0 NL, 1 AL [data] |
| 2 | 1 | division_id | 0 East, 1 Central, 2 West [data] |
| 3 | 1 | division_slot | alphabetical slot in the division [data] |
| 4 | 1 | computer_manager | bit 0x01 of the team option mask (FastSim `FUN_68028a10`: byte 4 + other 7 flags are summed with weights 1,2,4,..0x80); checkbox beside the Managing combo [guess] |
| 5 | 1 | _spare_5 | constant 0 [data] |
| 6 | 1 | managing_level | combo "Managing": Basic/Standard/Advanced [code] FastSim `FUN_680649f7` strings, `FUN_68028a10` copies bytes 6, 8..11 into the control table |
| 7 | 1 | _spare_7 | constant 1 [data] |
| 8..11 | 4 | pitching_level, batting_level, fielding_level, running_level | combos Computer/Basic/Standard/Advanced (3 = Advanced in all files) [code] |
| 12 | 17 | city | NUL padded string; LineUp `FUN_6b00b870` copies the strings at 0xc, 0x1d, 0x2e, 0x3f, 0x44, 0x4d, 0x6e |
| 29 | 17 | nickname | empty in every file |
| 46 | 17 | manager | |
| 63 | 5 | abbreviation | |
| 68 | 9 | short_name | empty in every file |
| 77 | 33 | stadium | |
| 110 | 9 | park_code | 8-char file-name stem ("ATLANTA.", "DENVER.D") |
| 119 | 96 | park_geometry | 32 triples (left, center, right) in 5 bands of 6,8,8,6,4 rows [data]: bands 1 and 4 are equal, 2 and 3 are equal; the large value of a triple moves between columns from park to park. Meaning of the numbers unknown (fence profile?) [guess] |
| 215 | 1 | artificial_turf | 1 in Houston, Seattle, Toronto, Minnesota, Montreal, Philadelphia, Pittsburgh, Cincinnati [data]; equals the game block's turf flag of the home park |
| 216 | 1 | _spare_216 | constant 0 |
| 217 | 80 | roster | 40 u16 player ids (25 used, rest 0) [code] FastSim `FUN_68040a7e` reads `*(short*)(rec+i*2)`, i<0x28 |
| 297 | 18 | batting_order_pids | 9 ids, batting order; with no DH the 9th is the pitcher [code] `FUN_68040a7e` (rec+0x50) [data] |
| 315 | 18 | defense_pids | 9 ids C,1B,2B,3B,SS,LF,CF,RF,DH (0 = pitcher bats) [code] (rec+0x62) [data]: equals event-2 fielders 2..9 of the first PA |
| 333 | 72 | lineup_cards | 2 cards x (batting order 9 + defense 9) = saved lineups; card 1 usually equals the active lineup, card 0 is the alternate; batting order ends with 0xffff when the pitcher bats [data] |
| 405 | 2 | starting_pitcher_pid | [code] rec+0xbc |
| 407 | 10 | rotation_pids | 5 starters [code] role 0 in `FUN_68040a7e` (rec+0xbe) |
| 417 | 8 | closer_pids, setup_pids, middle_relief_pids, long_relief_pids | 4 pairs; roles 1,2/3,4,5 in `FUN_68040a7e`; names [guess]; in game 0 both teams used pitchers from the 3rd pair |
| 433 | 40 | roster[i].slot_rank | one byte per roster slot, distinct values 1..68; stored in the player object at +0x23e (`EnableStackedTabs` is a mislabel) [code]; meaning unknown [guess] |
| 473 | 9 | league_name | "MLBPA97" |
| 482 | 1 | controller | who steers the team: 0 computer; bit 0x01 keyboard R (-1); bit 0x04 keyboard L (-2); bit 0x02 joystick, device number = value >> 4 [code] BBSIM `FUN_68031e2f` game-setup loader (the loop reading `t*0x1ea + 0x1e6 + param_1`) |
| 483..489 | 7 | options.injuries, fatigue, dh_rule, use_ratings, fielding_errors, base_stealing, pitch_to_center | the seven team checkboxes of the "Team Options" dialog, masks 0x02,0x04,...,0x80 [code] FastSim `FUN_6806938c` + dialog strings in FastSim.dll; `dh_rule` is 1 for AL teams [data] |

### Game block (offsets from 980)

| off | size | key | notes |
|---|---|---|---|
| 0 | 1 | weather.wind_direction | 0..7 In From Center, In From Left, Left To Right, Out To Right, Out To Center, Out To Left, Right To Left, In From Right (dialog strings, order assumed) |
| 1 | 1 | weather.wind_speed | |
| 2 | 1 | weather.sky_condition | 0 Clear, 1 Partly Cloudy, 2 Cloudy, 3 Rain Possible, 4 Rainout Possible; 3 and 4 occur only in the rain games [data] |
| 3 | 1 | weather.temperature_f | 72 in the domes [data] |
| 4 | 1 | weather.rain_kind | 8 = none; FastSim `FUN_6803cc8d` zeroes the next two when it is 8 |
| 5, 6 | 1+1 | weather.rain_start, rain_length | window in outs (`FUN_6803cce3`) |
| 7 | 1 | weather.wind_shift_count | (`FUN_6803cd80` loops over this many entries) |
| 8 | 4 | weather.wind_shift_times | |
| 12 | 4 | weather.wind_shift_values | |
| 16 | 2 | random_seed | varies per game |
| 18 | 1 | sim_status | BBShell writes 1 or 2 here after running the game (`FUN_68060f90`); 2 in all files |
| 19 | 1 | game_class | |
| 20..22 | 3 | _spare_1000.._spare_1002 | 4,1,0 in all files |
| 23 | 9 | home_park_code | = home team's park_code |
| 32 | 14 | box_score_file | "MLBPA97.HB0": day letter + hex game index |
| 46 | 1 | artificial_turf | |
| 47 | 2 | altitude_ft | 5280 in Denver [data] |

### ADI (12 bytes, deciphered)

`u32 game_date_serial, u32 game_date_serial_copy, u8 game_index_in_day, u8 _spare_9, u16 _spare_10`. Day 1 = 0x000b2fd7,
day 2 = +1; the index counts 0.. within the day [data].

## GDO: the event log (FastSim FEVENT module)

Sequence of u16 records, first word = type. Sizes in words: 0:2 1:41 2:15 3:7 4:3 5:4 6:4 7:5 8:6. The decoder walks the
payload with this table and ends exactly at the payload end for all 23 games. [code] FastSim `FUN_6801f748` (the debug
printer: event names `DAT_6808e510`, formats), constructors `FUN_680201d8` (2), `FUN_680202b0` (3), `FUN_6802019f`
(4), `FUN_6802030d` (5), `FUN_68020344` (6), `FUN_6802037b` (7), `FUN_680203c9` (8), `FUN_6802013a` (1),
`FUN_68020104` (0).

| type | name | words after the type |
|---|---|---|
| 0 | enter_game | version (4) |
| 1 | exit_game | game_seconds (printed as h:mm:ss), outs (total outs of the game), then per side (away, home) 19 words: 30 bytes of runs per inning, runs, hits, errors, left_on_base |
| 2 | plate_appearance | 9 defenders in the order pitcher,catcher,1B,2B,3B,SS,LF,CF,RF; 5 runner slots on_deck, at_bat, 1st, 2nd, 3rd (0 = empty) |
| 3 | substitution | team, player_pid, kind (0 pinch hitter, 1 pinch runner, 2 relief pitcher, 3 defensive sub), batting_order (0-based; 0xffff = none), position (1 P,2 C,3 1B,..,9 RF), base_runners (PR: base of the runner; RP: runners inherited; PH: count) |
| 4 | team_event | team, event (0 run, 1 earned run, 2 triple play, 3 double play) |
| 5 | pitching | team (fielding team), pitcher_pid, stat byte, flags byte |
| 6 | batting | team (batting team), batter_pid, stat byte, flags byte |
| 7 | fielding | team (fielding team), fielder_pid, play (0 PO, 1 A, 2 E, 3 DP, 4 PB), position 1..9 |
| 8 | injury | team, player_pid, kind, duration, severity |

Stat codes (pitching table `DAT_6808e610`, batting table `DAT_6808e668`): 0 AB, 1 B1, 2 B2, 3 B3, 4 HR, 5 RBI, 6 BB,
7 K, 8 HBP, 9 BBI (intentional, always sent together with BB), 10 SH, 11 SF, 12 R, 13 SB, 14 CS, batting 15 GDP;
pitching 15 BFP (first event of every plate appearance), 16 ER, 17 IR, 18 IRS, 19 PT (pitch thrown), 20 KT
(strike thrown), 21 WP. The flags byte is printed as the tags CL(1) SP(2) PLH(4) BLH(8); only seen on stat 19 (0..15).
In a plate appearance the order is: 2, BFP, the pitches (19, 20 each), then outcome events (fielding PO/A/E, team
events, pitching and batting stats). The `exit_game` record is last; FastSim `FUN_68029695` reads the final scores
from it (outs at 4 bytes into the record, runs of both sides at +0x24 and +0x4a). [data] runs_by_inning sums to
`runs`.

### Box score replay (the `_batters` / `_pitchers` keys)

Computed from the decoded events only, verified against all 23 box scores of both days:

* batter: ab = stat 0 events, h = stats 1..4, hr = 4, rbi = 5, bb = 6, so = 7, r = 12, sb = 13, keyed by `batter_pid`.
* pitcher (event `pitching`, keyed by `pitcher_pid`): bf = stat 15, h = 1..4, hr = 4, bb = 6, so = 7, r = 12.
* pitcher outs: each `fielding` event with play 0 (putout) is one out charged to the pitcher currently on the mound
  of the fielding team; that is the pitcher of the latest `pitching` event of that team, replaced by a
  `substitution` of kind relief pitcher (or defensive sub at position 1).
* rows whose counted columns are all zero are not part of a box score (pinch runners, ...); they are dropped.

## Known gaps

* park_geometry numbers, slot_rank, the exact roles of the four bullpen pairs, game_class, rain/wind-shift bytes and
  the spare bytes are labelled from structure only.
* The referee's jail needs systemd/bwrap, which this box lacks; `/tmp/w/localref.py` ran the real referee code with the
  jail swapped for a plain subprocess (PASS on both days, 12 random edit seeds per file).
