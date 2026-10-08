# game.bki / game.bko (shell <-> simulator game hand-off)

Codec: `work/gamebk.py` (Claude, 2026-10-08). Built on the #8b winning lane (re/targets/gamebk/lanes/code, round 3,
`voldat.py` + FORMAT.md) after reading it against BBShell and BBSIM. Changes from the lane: team strings split at the
real 17-byte boundaries, "pitch-frame table" is the uniform palette, team header bytes named, record tail named,
score-line innings decoded, substitution and injury fields named from the debug printer, the DIF chunk kept instead of
dropped, a strict walk only (unknown event types or chunks fail), and sides as content (`side`) instead of
`_`-prefixed keys that the lane's encoder read anyway.

The shell writes game.in, the sim reads it and writes game.out; BBShell renames them game.bki / game.bko
(FUN_68061390). Both are chunk streams: `tag[4] + u32le length + payload`, chunk helpers BBShell FUN_680633b0,
FUN_68063450 (read with tag compare), FUN_68063840 (tag + length placeholder), FUN_68063910 (backpatch).

## game.bki

Per game: `GDI:` (2-byte cipher seed + 0x405-byte record), then `DIF:` (72 bytes, only written when not all 0xff),
then `ADI:` (12 bytes). DIF and ADI are enciphered with the GDI seed (work/fpscipher.py). Shell write order:
FUN_680620a0 (GDI), FUN_680621c0 (DIF), FUN_68062160 (ADI, only for game types 1..3). The sample days have no DIF
chunk; its handling follows the code and is untested on data. JSON `order` keeps the chunk order per game.

GDI record. Fill: BBShell FUN_68016ce0, FUN_68016ec0 (weather), FUN_68017000 (each side) with setters
FUN_68061660 / 68061a20 / 68061a50 / 68061a80 / 68061b20..68061c50. Read by BBSIM FUN_68031e2f.

### Team block (0x1ea bytes: away at 0, home at 0x1ea)

| Off | Size | JSON | Source / evidence |
|---|---|---|---|
| 0x00 | 1 | team_id | t.dat byte 0; 1..28 in league order |
| 0x01 | 1 | league_idx | t.dat byte 1; 0 NL, 1 AL for all 28 teams |
| 0x02 | 1 | div_idx | t.dat byte 2; East 0, Central 1, West 2 |
| 0x03 | 1 | div_slot | t.dat byte 3; order inside the division |
| 0x04 | 8 | tdat_bytes | t.dat bytes 5, 0xc, 0xd, 6, 0xe, 0xf, 0x10, 0x11 (FUN_68061660); constant 01 00 00 01 03 03 03 03 |
| 0x0c | 17 | name | t.dat +0x12 |
| 0x1d | 17 | alt_name | t.dat +0x23, empty in the data |
| 0x2e | 17 | manager | t.dat +0x34 |
| 0x3f | 5 | abbrev | t.dat +0x45 |
| 0x44 | 9 | at_0x44 | t.dat +0x4a, a 9-byte string (team object +0x80 in the shell's team editor, FUN_6804bb30); empty in the data |
| 0x4d | 33 | stadium | |
| 0x6e | 9 | city8 | the 8-char DOS stem of the stadium file |
| 0x77 | 96 | uniform_palette | 32 RGB triples (FUN_68061a20; TAP_FORMAT team record +0x6d) |
| 0xd7 | 1 | turf | t.dat byte 0xaa = the home stadium's .DT turf byte (FUN_6801b1b0 reads STADIA\<file> info, byte 0x41); 1 for HOUSTON, MINNESOT, PITTSBUR, SEATTLE ... |
| 0xd8 | 1 | at_0xd8 | t.dat byte 0xab (team object +0x18 in the team editor); 0 in the data |
| 0xd9 | 50 | roster | 25 x u16 pid; covers every box-score pid |
| 0x10b | 204 | order_words | 102 x u16: 15 zero words, batting orders split by 0 / 0xffff, staff, then stale words. Kept verbatim |
| 0x1d7 | 2 | at_0x1d7 | the last 2 bytes of the 40-byte copy at 0x1b1 (see below) |
| 0x1d9 | 9 | league | "MLBPA97" |
| 0x1e2 | 1 | control | game setup per side +0x44 (FUN_68061a50) |
| 0x1e3 | 7 | options | game setup per side +0x4c..+0x52 (FUN_68061a80); options[2] = 1 for every AL team, 0 for NL (DH) |

0x10b..0x1d8 come from the side's lineup objects (FUN_68061660; lineup = team object +0x12c, `L`, and a 0x110-byte
lineup buffer filled by FUN_6804b470, `B`): 0x10b up to 15 words from L+0x5c (the word of each pair whose flag word is 0
or 3), 0x129 B+0xc4..0xd5 (18 bytes), 0x13b B+0xe8..0xf9, 0x14d L+0xc4 (72 bytes), 0x195 u16 B+0x10c, 0x197 L+0x10c
(26 bytes), 0x1b1 L+2 (40 bytes, ending in at_0x1d7). The codec keeps 0x10b..0x1d6 as `order_words`.

Strings keep bytes left after their NUL as `<key>_tail: [offset, text]`.

### Record tail

| Off | Size | JSON | Source |
|---|---|---|---|
| 0x3d4 | 4 | weather.wind_direction, wind_mph, sky, temperature_f | FUN_68061b90 / ba0 / b70 / b80; temperature kept 35..105, wind under 41 |
| 0x3d8 | 12 | weather.rain {kind, start_out, span_outs, delay_count, delay_outs[4], delay_minutes[4]} | FUN_68061bb0; kinds 6 and 8 = no rain, rest of the block stale (HCARD_FORMAT) |
| 0x3e4 | 2 | sim_seed | DAT_68091608 or FUN_6805c3b0 at write time; the sim's RNG seed (`-ns<N>`) |
| 0x3e6 | 1 | mode | FUN_68061b20; 0xff = empty slot (set after the write) |
| 0x3e7 | 1 | game_type | FUN_68061b30; 1..3 = ADI written, 4 forces sim mode 5 |
| 0x3e8 | 1 | month | FUN_68061b40: the game month from the date (FUN_68049250), 4..10; picks the weather table row |
| 0x3e9 | 1 | preset_lineups | FUN_68061b50 = setup +0x6a, Exhibition Play "Use Preset Lineups" (MENU.REQ 3 gadget 71; default 1, FUN_680172d0) |
| 0x3ea | 1 | one_pitch | FUN_68061b60 = setup +0x6d, Exhibition Play "One Pitch Mode" (gadget 74; default 0) |
| 0x3eb | 9 | stadium_file | FUN_68061c10; city8 stem, the sim maps "." to ".dat" |
| 0x3f4 | 12 | box_file | "MLBPA97.HB0": the game's box-score file |
| 0x400 | 2 | at_0x400 | no shell setter writes it (FUN_68061b20..68061c40 cover the rest of the tail); 0 in all data |
| 0x402 | 1 | stadium_flag | FUN_68061c40; stadium record +0x43 |
| 0x403 | 2 | elevation_ft | FUN_68061bf0 from the weather roll (FUN_68065410 out +2 = weather object +2, read from the home city's WEATHER.DAT record +40); Miami 10, Houston 40 in the data |

### ADI (12 bytes)

u32 day serial (`year`/`month`/`day`; serial = ordinal + 365 as in hcard.py), u32 copy (`copy_serial`, null when equal),
u8 `game_index` (0.. per day), u8 `at_9` (1), u16 `at_10` (0). The sim reads 10 bytes.

## game.bko

One `GDO:` chunk per game, same order as game.bki. Plain u16 event records with fixed sizes per type (BBSIM
DAT_680b3238, bytes incl. the type word): 0:4, 1:82, 2:30, 3:14, 4:6, 5:8, 6:8, 7:10, 8:12. Labels are the debug
printer FUN_68027ae8's own tables. Side 0 = away (block 0), 1 = home.

| Type | JSON t | Fields |
|---|---|---|
| 0 | start | version (4) |
| 1 | score | game_seconds, outs, away / home {innings: 30 x u8 runs per inning, runs, hits, errors, left_on_base} |
| 2 | pa | fielders[9] (P C 1B 2B 3B SS LF CF RF), on_deck, batter, runners[3] |
| 3 | sub | side, pid, kind (PH PR RP DS), bo (batting order), position (1-based code), br |
| 4 | team | side, event (RUN ER TP DP AB) |
| 5 | pitch | side (fielding), pid, result (AB B1 B2 B3 HR RBI BB K HBP BBI SH SF R SB CS BFP ER IR IRS PT KT WP), flags (CL 0x100 close/late, SP 0x200 scoring position, PLH 0x400 pitcher left, BLH 0x800 batter left), flags_high (bits 12-15) |
| 6 | bat | side (batting), pid, result (AB B1 B2 B3 HR RBI BB K HBP BBI SH SF R SB CS GDP PO) |
| 7 | field | side (fielding), pid, play (PO A E DP PB), position (DAT_680b3228 order) |
| 8 | injury | side, pid, type, duration, severity |

Codes past a label table decode as integers and encode back as given.

Box-score replay (`_batters`, `_pitchers`, derived): ab = bat AB; h = B1..B3, HR; hr = HR; rbi, bb, so (K), r (R), sb;
pitcher outs = field PO for the fielding side's current pitcher (the last pitch record's pid); bf = pitch BFP; the
pitcher is charged h, hr, bb, so, r of the opposing batters. All-zero rows are dropped, as in the box files.

## Verification (2026-10-08)

- `gamebk.py verify`: byte-exact round trip of game.bki and game.bko on day1, day2 and the holdout day3, day4 (51 games).
- Replay equals the box-score files row for row on day1/day2 (23 games) and equals the lane's referee-passing replay
  on all 51 games. Every score line's innings sum to its runs.
- Edit test: team name, manager, palette entry, temperature, ADI date, roster pid, an inserted injury event, a deleted
  event, B1 -> HR, pitch flags: encode, decode, content equal, re-encode stable on all 8 files. Bad labels fail.
- The #8b referee's random edit test appends "Qz" to every string leaf, which a codec with named codes rejects by
  design; the lane codec (integer codes, `_` labels) remains the referee-passing one.
