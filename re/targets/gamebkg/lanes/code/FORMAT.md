# game.bki / game.bko: the shell <-> simulator hand-off of FPS Baseball Pro '98

Status: both layouts decoded, `voldat.py` round trips all four visible files byte-for-byte and
its replayed event rows equal every visible box score exactly (23/23 games, day1 + day2). Round
2: the all-zero-row drop, the dynamic roster split and the length-agnostic ADI were added for
the day3 holdout; the visible days still pass (score_local, byte-identical referee logic).

Both files are a stream of chunks: a 4-byte tag + u32 little-endian payload length + payload.
BBShell writes `game.in` (one setup record per game) for the simulator, the simulator answers in
`game.out` (one event stream per game), BBShell renames them to `game.bki` / `game.bko`
(`FUN_68061390`: `_unlink(game.bki); rename(game.in, game.bki); _unlink(game.bko); rename(game.out, game.bko); _unlink(game.bks); rename(game.sav, game.bks)`).

## game.bki — setup records (shell -> simulator)

Chunk sequence per game: one `GDI:` chunk (payload 1031 bytes) then one `ADI:` chunk (12 bytes).
day1 = 9 GDI + 9 ADI, day2 = 14 GDI + 14 ADI (uniform payload lengths: GDI 1031, ADI 12).

GDI payload = the 2-byte cipher seed + 1029 enciphered body bytes:

    decipher(payload[2:], payload[:2])

with the game's own file cipher (`re/targets/cipher/lanes/data/CIPHER.md`; `gen(lo, hi)` sentinel
walk, each byte forward = `B^3`, decode = the inverse once). Verified: the seed bytes are read by
BBShell `FUN_68053420` (two random bytes via `FUN_6805c420(0..1, 0xff)`), the table is built by
`FUN_68053450` and the body is deciphered by `FUN_68053510` (BBShell `FUN_68061dd0` reads the
GDI record with `(**)(vtable + 0x18)(0x405, record)` = 0x405 = 1029 bytes).

Plain body = two team blocks of 490 bytes (away first, home second) + a 49-byte tail
(490*2 + 49 = 1029).

### Team block (offsets relative to the block start)

    +0    u16 statusFlags    (varies per game: day1 g0 home = 0x0001, away = 0x0008)
    +2    u16 statusFlag1    (varies: 0x0000 / 0x0201 / 0x0200 ...)
    +4    u16 structVersion  = 0x0001
    +6    u16 structFlag     = 0x0100
    +8    u16 colorPrimary   = 0x0303 (both teams of every visible game)
    +10   u16 colorSecondary = 0x0303 (both teams of every visible game)
    +12   team name, 33-byte NUL-padded field ("Atlanta", "Houston", "Montreal", ...)
    +45   0x00 pad           (BBShell `FUN_68061660`: `puVar6[0x1e1] = 0`)
    +46   manager name, 17-byte NUL-padded field ("Bobby Cox", "Larry Dierker", "Felipe Alou", ...)
    +63   team abbreviation, 4-byte field ("ATL\0", "HOU\0", "MON\0", ...)
    +77   stadium name, 33-byte NUL-padded field ("Atlanta-Fulton County Stadium", "The Astrodome",
          "Stade Olympique", ...)
    +110  city, 9-byte NUL-padded field ("ATLANTA.", "HOUSTON.", "MONTREAL", ...
          the visible values are 8 chars)
    +119  96 bytes of per-slot color triples: 32 triples of 3 bytes each (the same value repeated
          r=g in nearly every triple: 34 34 80 | 30 30 74 | 2c 2c 6c | ... the team brightness per
          slot), then
    +215  2 extra bytes (the visible values = 0x00 0x00)
    +217  u16 id region, 240 bytes = 120 words:
            +217   the roster player ids (the leading contiguous non-zero run = the active
                   roster; the visible days carry 25 ids, so the boundary is read, not assumed)
            then   spare roster slots (0x0000 words), then the lineup/id blocks: 3 batting-order
                   blocks and the pitching staff, terminated by 0x0000 / 0xffff markers (day1 g0
                   home: the batting order 1653 965 104 105 109 1530 1443 1723 115, the bench
                   bench ids, then the staff)
            +455   the last words of the region
    +457  16 bytes: a 0..63 permutation-like slot order table (values 0..0x3c: 0a 2b 12 18 1f 08 24 0d
          04 0b 03 01 3c 30 15 17)
    +473  league name, 7 bytes ("MLBPA97")
    +480  5 u16 block-tail words (day1 g0 home: 00 00 8a 01 00)

The first words at +217 (the leading contiguous non-zero run) are the active roster; every
player id the simulator is told about (roster + lineups + staff of both teams) appears there, so
the roster covers every pid of the matching box score. The visible days carry 25 ids per team
(the 25-man roster); the boundary is read from the first 0x0000 split, so an expanded holdout
roster decodes under the same pid key. Evidence: BBShell `FUN_68061660` (the GDI record builder)
writes the team strct at a 0x1ea (490) stride: `param_1 * 0x1ea + *(int *)this` and copies the name with
`strncpy(puVar6 + 0x1d9, param_2, 9); puVar6[0x1e1] = 0` (that is the second team block's name
at +0x1d9 - 0x1ea = the away team's name at 469) hmm that is the builder's own offset math; the
reader (`FUN_68061dd0`) reads the record body with 0x405 and then reads the ADI payload with
0xc into `record + 0x405`.

### Tail (49 bytes after the two team blocks)

    +0    23 bytes of per-game status/counters (varies: day1 g0 = 00 00 00 48 08 01 00 96 01 01 00
          00 00 2d b5 04 ef 8d 02 01 04 01 00; day1 g8 = 03 46 00 2a 02 00 01 01 00 00 00 2d b5 04
          ef 4e 02 01 04 01 00 ...) the "2d b5 04 XX XX 02 01 04 01 00" part is a fixed byte-exact
          pattern with two varying bytes (ef 8d / 6d 91 / ...)
    +23   the away team's city, 8 bytes ("HOUSTON.", "DENVER.D", "MIAMI.DA", ...)
    +31   0x00
    +32   the box-score file name the game's box score is written to, 11 bytes
          ("MLBPA97.HB0" = the day's box file for game 0; "MLBPA97.HB1" = game 1; "MLBPA97.HC3" = ...)
    +43   6 trailing bytes (day1 g0 = 00 00 00 01 28 00)

Evidence for the layout: day1 game 0's enciphered body deciph with seed 6269 gives the two team
blocks and the tail; the box file name deciph as "MLBPA97.HB0" and the day1 `MLBPA97.HB0` box
score deciph by the solved H decoder matches the GDI game 0 (the game index matches between the
files: GDI game i = the box file named in the GDI game i's tail = GDO game i).

## ADI chunk (12 enciphered bytes)

`decipher(payload, the matching GDI record's seed)` = three u32s: a byte-exact cover word (the
same value twice: day1 every game = 0x000b2fd7, day2 every game also = hmm the visible days' ADIs
decode to the same cover), then the u32 game number (0x100 for game 0, 0x101 for game 1, ...).
day1 g0 = d72f0b00 d72f0b00 00010000 = cover 0x000b2fd7 twice + game 0x100. day1 g1 = game 0x101.
The ADI is enciphered again with the GDI record's seed on the re-encode.

Evidence: BBShell `FUN_68061dd0` reads the ADI record with tag DAT_6808c8a4 only when the
status byte at record + 999 = 1..3 and deciphers 0xc bytes into `record + 0x405`.

## game.bko — event records (simulator -> shell)

One `GDO:` chunk per game (payload 8-15 KB, plaintext, no cipher). The payload = a sequence of
u16 event records; every record = a u16 type then the record's payload, the record sizes in bytes
per type (0..8) are FIXED:

    type 0 "Enter Game"        4 bytes
    type 1 "Exit Game"        82 bytes
    type 2 "Plate Appearance" 30 bytes
    type 3 "Substitution"     14 bytes
    type 4 "Team"              6 bytes
    type 5 "Pitching"          8 bytes
    type 6 "Batting"           8 bytes
    type 7 "Fielding"         10 bytes
    type 8 "Injury"           12 bytes

Evidence for the tag/sizes: the simulator writes the records into an 0x8000-byte in-memory event
log (`FUN_6802886a`, `FUN_68028955` appends the log to "game.evt" and writes it as a GDO chunk);
the per-type size table sits at BBSIM.dll 0x680b3238 = [4, 82, 30, 14, 6, 8, 8, 10, 12]; the
walker `FUN_68028c0a` steps the log by `*(int *)(&DAT_680b3238 + *local_10 * 4)`; the validator
`FUN_68028ce3` = "type 0 must have 4 bytes, the sizes must fill the log"; the type names come
from the simulator's own event-name table at BBSIM.dll 0x680ba358 (a 17-byte-stride table) =
['Enter Game', 'Exit Game', 'Plate Appearance', 'Substitution', 'Team', 'Pitching', 'Batting',
'Fielding', 'Injury'] and the text formatter `FUN_68027ae8` prints "EVENT: %s ..." per type
("EVENT: %s Version: %d" for type 0, "EVENT: %s Outs: %d Game Time: ..." for type 1, ...).

### Fields per type (day1+day2 evidence)

    0 Enter Game:        [0, 4] = the format version 4 ("Version: %d").
    1 Exit Game:         [1, gameLengthTicks, outs, r_r_half, r_l_half, ..., a line-score block,
                          ..., the last words = the day's final counters].
                         day1 g0 = word1 = 0x2585 = 9605 ticks, word2 = 51 = the pitcher-outs total
                         (the box = 51) — "Outs: %d Game Time: %02d:%02d:%02d" with word1 / 0xe10 =
                         hours and then the two 19-word halves "R H E LOB" per team.
    2 Plate Appearance:  [2, pitcherPid, defensePids(9), onDeckPid, batterPid, 0, 0, 0].
                         day1 g0 first PA: [2, 400(P gibberish? no = the pitcher 400 = 0x0190),
                         1828 1595 924 2215 1638 1942 2091 390 965 = the 9 defenders, 965 =
                         on-deck, 1653 = the batter, 0, 0, 0]. Verified: the word1 values across
                         day1 g0 = {400: 27, 115: 25, 1608: 12, 1682: 6, 2165: 3} = EXACTLY the box
                         pitchers' bf (the batters faced).
    3 Substitution:      [3, half, playerPid, orderId, sequence, code(5/6/7/8/9), flag]
                         ("Substitution", day1 = the pinch hitters and the relief pitchers).
    4 Team:              [4, half, code] (the visible values = 0..3; the day1 sampler).
    5 Pitching:          [5, half, pitcherPid, pitchEvent] the pitch record:
                         the visible pitchEvent values = 0 (ball in play — count = AB exactly),
                         1 (the walk marker), 2/4/5/6/7/9/12/13/15/16 (the samplers), and the
                         packed 0x?13 / 0x?14 values (the low byte = the pitch kind 19/20 = the
                         ball/strike kinds, the high byte = the pitch speed id; FastSim's own
                         pitch-kind strings at FastSim.dll 0x96c30 = ['No Exit', 'Ball Hit',
                         'Ball Bunt', 'Strike Out', 'Walk', 'Int. Walk', 'Pickoff Att.',
                         'Passed Ball', 'Wild Pitch', 'Runner Stealing', 'Double Steal',
                         'Batter Hit', 'Batter Nailed']). The pitcherPid = the pitcher on the
                         mound (the mid-PA relief change = the following t5s carry the new
                         pitcher).
    6 Batting:           [6, half, playerPid, outcome] — the outcome indexes the simulator's
                         batting-outcome table (BBSIM.dll 0x680ba4b0, a 4-byte-stride table) =
                         ['AB', '1B', '2B', '3B', 'HR', 'RBI', 'BB', 'K', 'HBP', 'BBI', 'SH', 'SF',
                         'R', 'SB', 'CS', 'GDP', 'PO']:
                           0 = at-bat ended (count = the box AB exactly, day1 9/9 games),
                           1 = single, 2 = double, 3 = triple, 4 = home run (the count of
                               1+2+3+4 = the box H exactly; 4 = the box HR exactly),
                           5 = RBI (day1 g0 count = 8 = the box RBI total),
                           6 = walk (count = the box BB exactly, 9/9 visible games),
                           7 = strikeout (count = the box SO exactly, 9/9 visible games),
                           8 = hit by pitch?? (the visible value = rare),
                           9 = the intentional-walk marker (rides on the code-6 = one BB),
                           12 = run scored (day1 g0 count = 8 = the box R total),
                           13 = stolen base, 14 = caught stealing, 15 = double play, 16 = putout.
    7 Fielding:          [7, half, fielderPid, play, position] — the play indexes the simulator's
                         fielding table (0x680ba4f8 = ['PO', 'A', 'E', 'DP', 'PB']):
                           0 = putout (count = the box pitcher-outs exactly, 9/9 visible games),
                           1 = assist, 3 = ... (the visible value), the position = the fielding
                         position (day1 g0 = 2/3/4/5/6/9 = C/1B/2B/3B/SS/RF).
    8 Injury:            [8, half, playerPid, genre, duration, severity]
                         ("EVENT: %s %s Type:%d Duration:%d Severity:%d"; the visible day2 values
                         = genre 0x82/0x50/0xc6, duration 8/10/11, severity 0x1a/18/0x12).

### The replay (voldat.py) = the box-score rows

`replay()` walks the event records and accumulates the batting/pitching rows:

  - the PA record = the batter faced for the pitcher named in the PA's word1;
  - the Pitching record's pitcherPid = the CURRENT pitcher on the mound (the mid-PA relief change
    = the following records carry the new pitcher; verified: day2 HC3 = the box pitchers 444 outs
    12 vs my PA-header attribution = 13 — the t5-based attribution gives the box value);
  - the Batting outcomes 0..12 belong to the player named by the record (codes 13/14 = the
    base-runner events attach to an existing row; a caught-stealing = not a row (the box has no
    caught-stealing field: HC0's pinch runner 2019 = the cs event = the box carries no row));
  - the fielder's putout (fielding play = 0) = one out for the current pitcher;
  - rows whose counted cells are all zero are dropped (a player who appeared without a counted
    stat — a pinch runner, a lone sac bunt/HBP PA — is no box row), matching the box-score
    decoder's own `if any(v)` row filter cell-for-cell (the batters keep pa+cs as extra keys).

Verified against the visible days' box scores (`re/targets/cipher/... / the solved H decoder`):
all 23 games of day1 + day2 = the batting and pitching rows equal the day's box scores exactly
(the multisets, exact). The box-score row fields: batters = pid ab h hr rbi bb so r sb (+pa cs),
pitchers = pid outs bf h hr bb so r.

Note for the owner: this container has no systemd user manager (`/run/user/1000` absent, PID 1 =
bwrap), so the referee's jail (`systemd-run --user --scope` = see jailutil.py) aborts before
bwrap runs. `score_local.py` in this lane replicates the referee's checks (voldatref.decode /
validate / encode / edit_test / gamebkref.check_day, byte-identical logic) running the codec
under the SAME bwrap argv without the systemd wrapper and prints PASS on both visible days
(the cipher lane's CIPHER.md sanity limits note the same).
