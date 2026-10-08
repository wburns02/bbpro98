# Lane "code": progress (game.bki / game.bko codec)

## Round 1 status (2026-10-08)
- `voldat.py` written (stdlib only, ~17 KB). Round trip is byte-exact on all 4 visible files (day1/day2 x bki/bko).
- Referee (unmodified `gamebkref.py` logic): **PASS** on both visible days (9 and 14 box scores).
  - The official jail (`jailutil.jail`) calls `systemd-run --user`, which fails in this container
    ("Failed to connect to user scope bus"), so the official command fails for every lane here.
    I did NOT edit jailutil or the referee. I ran the same referee code through a local harness that keeps the bwrap
    argv and drops only the systemd scope: `scratch/run_ref.py` (with `scratch/localjail.py`).
    Command: `cd /home/will/bbpro98/re/targets && python3 -I gamebkh/lanes/code/scratch/run_ref.py <targets> <lane> -v`
  - Output: `{"day": "day1", "ok": true, "box_scores": 9}`, `{"day": "day2", "ok": true, "box_scores": 14}`, `PASS`.
- Edit-test stress (own script `scratch/stress.py`, same checks as the referee): 60 seeds x 4 files, 0 failures.
- Holdout days are not readable here, so the holdout pass was not run.

## What was learned (details in FORMAT.md)
- GDI payload = seed(2) + 1029 enciphered bytes; ADI = 12 bytes enciphered with the same seed.
  Record = away block (0..489) + home block (490..979) + 49-byte tail. Team block fields have fixed offsets.
- GDO = u16 event stream. Sizes come from BBSIM's table at DAT_680b3238 (types 0..8: 4,82,30,14,6,8,8,10,12 bytes).
  Names come from BBSIM's formatter FUN_68027ae8 and its label tables read out of BBSIM.dll
  (DAT_680ba358 .. DAT_680ba4f8; the PE image was read with a small stdlib script, `scratch/pe.py`).
- Box scores reproduce exactly from the events:
  - batter rows: AB, B1..B3, HR, RBI, BB (not BBI), K, R, SB; h = B1+B2+B3+HR; batters with only CS are excluded.
  - pitcher rows: BFP, B1..B3, HR, BB, K, R; outs = PO putouts charged to the last pitcher seen for the fielding team.
  - the exit-game record's total_outs equals the sum of pitcher outs (and the PO count) in all 23 games.
- Correction to the task's note: in day1 game 0 the first PA's batter is 1653 (lead-off); 965 is the on-deck slot.

## Open
- Meaning of: tuning_rows (98-byte per-team table), depth_table (40 bytes), team_code, team_flags, header_tail,
  schedule_params, game_seed, tail_words, unnamed_words_* (exit game), br_field (substitution), ADI day_key/game_no.
  All are kept exactly, named descriptively, and marked unverified in FORMAT.md.
- Event types 9+ are not in the size table, so the decoder raises on them. Holdout days might differ; unknown.
- Pitcher outs are charged by the team's most recent pitching event. This matches 23/23; untested on relief changes
  within a PA (none seen).

## Next round ideas
- Trace BBShell's game.bki writer (FUN_68061430 / FUN_68061dd0 callers) to name the team tuning bytes and team_code.
- Trace the sim's team-setup reader for depth_table, team_flags and the lineup segment roles (BBSIM FUN_68033019 area).
- Check the other lanes' FORMAT.md for the meaning of ADI day_key and game_seed (not read yet: no files existed).

## Scratch files (not part of the codec)
- `scratch/chunks.py`, `gdi.py`, `gdi2.py` (GDI decipher survey), `gdo_parse.py`, `replay1.py`, `replay2.py`
  (replay rules, 23/23), `outs1.py`, `pe.py` (PE reader for string tables), `fn.sh` (print a decompile function),
  `rt.sh` (round trip), `localjail.py` + `run_ref.py` (local referee harness), `stress.py` (edit stress).

## Round 2 (2026-10-08)
Input: referee PASS on the visible days; holdout day3 FAILED (error hidden in holdout mode), day4 ok.

### What I checked
- The referee's holdout path (`gamebkref.check_day(hold=True)`): 3 edit rounds, 8 edits, bki grows at most 32 bytes.
  I cannot read day3, so its cause is not confirmed. Candidates I could test:
  1. Decoder raises on layouts the visible days lack. Confirmed in code: an extra or missing ADI, any other chunk,
     non-zero bytes after a string NUL, non-zero roster padding all raised. BBSIM's game.in reader (BBSim decompile
     ~l.29170-29265, FUN_68031e2f) also reads an OPTIONAL `DIF:` (72 bytes) per game, which round 1 rejected.
  2. Byte fields holding 255 cannot take the referee's +1 edit. None of the ~8000 visible byte leaves is 255, so
     not testable here; it is documented.
  3. Pitcher outs in a relief window (see 2.3 of FORMAT.md). Upstats FUN_6c003550 charges a putout to defensive
     slot 1, which a relief substitution (sub_kind 2) sets (FUN_6c001980). Round 1 used "last pitching event".
     Visible data has 0 putouts in a relief window, so the two rules agree on it.
  4. Box-row membership (batters/pitchers): Upstats writes a box row for each roster entry the batting stat code
     touches (FUN_6c0020e0 via FUN_6c003a00). Not testable with the bko stream alone; still the main open risk.

### What changed (voldat.py, round 1 backup in scratch/round1/)
- bki: ADI and DIF optional per game; other chunks kept (`_other_chunks`, order in `_layout`); leading chunks kept.
- strings: any non-zero tail after a NUL kept as derived `_junk_after_nul` (team fields and record tail).
- roster padding: kept as derived `_roster_padding` when non-zero.
- bko: non-GDO chunks kept (`_other_chunks`, `before_game`).
- replay: an RP substitution sets the outs pitcher (`cur[team]`).
- DIF block: `dif_block` = 72 deciphered ints, content (meaning unverified; BBSIM FUN_68031e2f at game state +0x409).

### Verification (all run after the last code edit)
- Round trip, byte exact: day1/day2 x game.bki/game.bko (`cmp` on decode->encode).
- Referee on visible days, through the local jail harness (`scratch/run_ref.py`, same argv as the official run):
    {"day": "day1", "ok": true, "box_scores": 9}
    {"day": "day2", "ok": true, "box_scores": 14}
    PASS
- Holdout-mode `check_day` (3 edit rounds, 8 edits) on day1 and day2, seeds 20..31: 24/24 ok (`scratch/seedsweep.py`).
  Earlier holdout-mode runs at seeds 101/977/4242 on day2: ok.
- Synthetic variants built from raw bytes (`scratch/synth.py`): game 0 with a DIF after ADI + junk after a team name
  NUL + roster padding; game 1 with a DIF; an extra `ZZZ:` chunk in game.bko. All round-trip, and the DIF bytes
  decode to range(72). `scratch/holdcheck.py` runs holdout-mode check_day on the DIF variant: ok, 3 seeds.

### Not done / next round
- Batter/pitcher row membership is still event-based. To test it, find how FUN_6c001800 (the appearance list) and
  FUN_6c003a00 (roster lookup) fill the side's 40 roster entries at game start (FUN_6c002850), and whether a pinch
  runner that never gets a roster entry should have no row.
- The DIF block's fields: follow the users of the 0x409 accessor (BBSim `_all.c` l.44634) to name them.
- Nothing in this round can be checked against day3 itself; it is not readable from this lane.

## Round 3 (2026-10-08)
Input: day1/day2 PASS; holdout day3 FAILED (hidden), day4 ok. Holdout error text is hidden, so no direct evidence.

### What changed (voldat.py; round 2 backup in scratch/round2/)
- Roster: `roster_pids` is the 40-slot roster table (bytes 217..297), not 25 + padding. The sim copies all 40 words
  (Upstats FUN_6c007350 at 0xd9, FUN_6c002850 loads 40 entries). The H body confirms it: its 40 player-table pids
  equal the roster of both teams (day2 game 0). Before, a box player who sat in slots 25..39 was not in any
  pid-keyed list, so the coverage check could fail on a day with such a player. `_roster_padding` is gone.
- Box rows (2.3 in FORMAT.md): a row exists iff one of its own fields is non-zero (batter ab/h/hr/rbi/bb/so/r/sb;
  pitcher outs/bf/h/hr/bb/so/r). Visible: identical output (CS-only pid 2019 excluded, no zero rows). Round 2's
  "any batting event except CS" would write a zero row for a batter whose only events are HBP/SH/SF/BBI/GDP.
  Evidence in 2.4: the H file's batter table has a CS-only record with no row and no counter outside CS.
- Putouts before a team's first pitching event go to that team's first pitcher in the stream (none in visible games).

### Verification (after the last code edit)
- Referee on visible days through the local jail harness (`scratch/run_ref.py`):
    {"day": "day1", "ok": true, "box_scores": 9}
    {"day": "day2", "ok": true, "box_scores": 14}
    PASS
- Round trip byte exact: day1/day2 x game.bki/game.bko.
- Holdout-mode sweep `scratch/seedsweep.py` (3 edit rounds, 8 edits, seeds 20..31, day1 and day2): 0 failures.
- Edit stress `scratch/stress.py 6`: 0 failures.

### Checked and ruled out (for the day3 failure)
- Unknown event types: BBSIM FUN_68028ce3 asserts 0 <= type <= 8 on every game.out event, and type 0 must carry
  version 4. So the decoder's raise cannot be reached by a sim file.
- Cipher seeds: all 65536 (lo, hi) pairs give a permutation, so no edit of a seed breaks the round trip.
- Pitcher outs: a putout inside a relief window never occurs in the visible games; the RP rule and the
  last-pitcher rule agree there.
- Coverage cap (64 pids): visible games have 51 distinct ids (50 players + 0).

### Still open
- Holdout day3 cause is not confirmed. Remaining candidates: (a) a batter with only HBP/SH/SF/BBI/GDP events
  (membership rule above, unverified); (b) a byte field equal to 255, where the referee's +1 needs 256 (not
  representable; no visible byte is 255; FORMAT.md 3); (c) bench players in roster slots 25..39 (fixed, untested
  on a real file).
- The H file's second table (40-byte records, file offset 2718) is only partly parsed: 9..16 batters per file.
  The rest of the H file (pitcher and fielding tables, 2nd team records) is not decoded here.
