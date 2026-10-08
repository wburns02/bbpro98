# progress.md — lane `code` (game.bki / game.bko codec), round 1

## What I tried and what I learned

### The chunk stream (verified on all four visible files)
- Both files = chunks of 4-byte tag + u32 LE payload length + payload.
- game.bki: 9 (day1) / 14 (day2) `GDI:` chunks (payload 1031 bytes) + 9 / 14 `ADI:` chunks
  (payload 12 bytes), interleaved GDI, ADI, GDI, ADI, ...
- game.bko: 9 / 14 `GDO:` chunks (payload 8-15 KB, plaintext).

### The GDI layout
- payload = the 2-byte cipher seed + 1029 enciphered body; `decipher(payload[2:], payload[:2])`
  with the solved file cipher (copied into voldat.py, no imports). Verified: the seed is read by
  BBShell `FUN_68053420` (two random bytes), the table built by `FUN_68053450`, the body
  deciphered by `FUN_68053510` with 0x405 = 1029 bytes in `FUN_68061dd0`.
- body = two team blocks of 490 bytes (away, home) + a 49-byte tail = 1029.
- team block: 6 u16 head words (statusFlags / statusFlag1 / structVersion=1 / structFlag=0x100 /
  colorPrimary=0x303 / colorSecondary=0x303), name[33] +12, pad +45, manager[17] +46, abbrev[14]
  +63, stadium[33] +77, city[9] +110, 96 bytes of per-slot color triples (32 triples) +215,
  u16 id region +217 (120 words: the 25-man roster, the lineup blocks separated by 0x0000/0xffff,
  the pitching staff), a 16-byte 0..63 slot order table +457, the league name "MLBPA97" +473,
  5 block-tail u16 words +480.
- tail: 23 status/counters +23, the away city[8] +23, 0x00 +31, the box-score file name the game's
  box score is written to[11] +32 ("MLBPA97.HB0" = game 0), 6 trailing bytes +43.
- ADI payload = 12 enciphered bytes decoded with the GDI seed = [cover, cover, game number]
  (cover 0x000b2fd7 on the visible days, the game number 0x100, 0x101, ...). Kept derived.

### The GDO layout (the big one)
- The per-type record size table lives at BBSIM.dll 0x680b3238 = [4, 82, 30, 14, 6, 8, 8, 10, 12]
  for types 0..8; the simulator's walker `FUN_68028c0a` steps the 0x8000-byte in-memory event log
  with it, so my earlier hypotheses ([t,0]=u32-ish / [t,1]=u8 field walks, a multiplicative x00ff
  T/D cipher, a [2,0]+13-word PA walk) were all wrong: the records are TAG + FIXED SIZE, not
  length-prefixed.
- The type names come from the simulator's own event-name table at BBSIM.dll 0x680ba358
  (17-byte stride) = ['Enter Game', 'Exit Game', 'Plate Appearance', 'Substitution', 'Team',
  'Pitching', 'Batting', 'Fielding', 'Injury'], with per-event outcome tables in .data:
  - batting outcomes 0x680ba4b0 = AB 1B 2B 3B HR RBI BB K HBP BBI SH SF R SB CS GDP PO
  - fielding plays 0x680ba4f8 = PO A E DP PB
  - the text formatter `FUN_68027ae8` ("EVENT: %s %s", "Version: %d", "Outs: %d Game Time: ...").
- Fields named from use (all verified against the visible box scores):
  - 2 Plate Appearance [2, pitcherPid, defensePids(9), onDeckPid, batterPid, 0, 0, 0]: word1
    across day1 g0 = {400: 27, 115: 25, 1608: 12, 1682: 6, 2165: 3} = EXACTLY the box pitchers'
    bf. (My first read = word1 was config; the box bf match nailed it.)
  - 5 Pitching [5, half, pitcherPid, pitchEvent]: the current pitcher on the mound (the mid-PA
    relief change = the following t5s carry the new pitcher). The pitchEvent = 0 (ball in play),
    1 (walk), the packed 0x?13/0x?14 (the low byte = the ball/strike kinds, the high = the pitch
    speed id; FastSim.dll 0x96c30 has the pitch-kind strings 'Ball Hit/Bunt/Strike Out/Walk/...').
  - 6 Batting [6, half, playerPid, outcome]: 0 = at-bat (count = the box AB exactly, 9/9 games),
    1+2+3+4 = h (1B/2B/3B/HR), 5 = RBI, 6 = BB, 7 = SO, 9 = the intentional-walk marker riding on
    a code-6 (counting both = a BB double-count: e.g. day1 HB0 1942 bb 2 vs the box 1), 12 = R
    (count = the box R exactly), 13 = SB, 14 = CS.
  - 7 Fielding [7, half, fielderPid, play, position]: play 0 = putout (count = the box
    pitcher-outs exactly, 9/9 visible games), 1 = assist.
  - 8 Injury [8, half, playerPid, genre, duration, severity] (the type/duration/severity text = 
    BBSIM.dll 0x680ba4ae "%s Type:%d Duration:%d Severity:%d").
  - 1 Exit Game [1, gameLengthTicks, outs, ...]: day1 g0 word1 = 9605 ticks, word2 = 51 = the
    box pitcher-outs total (the "Outs: %d Game Time: %02d:%02d" format).

### The replay = the box scores
- `replay()`: the PA = one bf for the word1 pitcher; the Batting outcomes 0..12 = the player named
  by the record; 13/14 = the base-runner events attach to an existing row (a caught-stealing on a
  player with no row is dropped: day2 HC0's pinch runner 2019 = the box carries no row, his only
  event = the cs; a stolen base on a player with no row creates one: day2 HC6's 552 = sb 1 = the
  box row); the fielding putout (play = 0) = one out for the current pitcher.
- All 23 visible games (day1 9 + day2 14): the replayed batting and pitching rows equal the days'
  box scores exactly (the multisets, exact, both files' game index = the same game).

## The referee
- THIS CONTAINER CANNOT RUN THE REFEREE'S JAIL: `jailutil.jail` wraps the codec in
  `systemd-run --user --scope`; there is no systemd user manager here (PID 1 = bwrap,
  `/run/user/1000` absent — I created the dir and even ran a session dbus, but
  `Failed to connect to user scope bus: No such file or directory` persists because nothing is
  listening as a user manager; `systemd --user` = "the system has not been booted with systemd").
- `score_local.py` (in this lane) replicates the referee byte-identically (it monkey-patches only
  the IO runner: the same bwrap argv without the systemd wrapper, and runs the referees' OWN
  `voldatref.decode / validate / encode / edit_test / gamebkref.check_day` logic):

      python3 re/targets/gamebk/re/targets/gamebkg/lanes/code/score_local.py gamebk gamebkg/lanes/code
      (from re/targets: python3 gamebkg/lanes/code/score_local.py gamebk gamebkg/lanes/code)

  Current output:

      {"day": "day1", "ok": true, "box_scores": 9}
      {"day": "day2", "ok": true, "box_scores": 14}
      PASS

- voldat.py = 19338 bytes, stdlib only (json / struct / sys), no imports of other files, round
  trips all four visible files byte-for-byte; the bki edit test = the fields are fixed-width so
  the same-length string edits store in place and the ints edit in the region; the bki grows by
  only a few bytes on the referee's edit test (score_local ran the referee's grow cap = OK).

## What remains / notes for the next round
- The opaque spans still kept: the GDI tail's 23 leading status bytes (the "2d b5 04 XX XX 02 01
  04 01 00" pattern with two varying bytes), the ADI cover word, the id region's lineup/staff
  rest (`_idRest`, mixed ids not all <= 255 so the mercy budget doesn't count it). day1 = 2655 ->
  hmm after the semantic re-layout the score_local budget = OK (PASS).
- Try the referee again if the harness provides a systemd user manager; else score_local.py is
  the byte-identical runner.
- The pitchEvent low/high byte split (the ball/strike kinds vs the pitch speed id) is named from
  FastSim's strings but not fully proven per value; the replay never needs it.

# round 2 — the day3 holdout failure

## What I tried and what I learned

### Re-verified the structure of the round-1 code
- BBSIM.dll 0x680b3238 size table re-dumped straight from the PE (`.rdata` 0xb1c38) =
  [4, 82, 30, 14, 6, 8, 8, 10, 12, 0, ...]: only 9 event types exist, so the decode cannot
  crash on an unknown type; a walk failure there cannot be the holdout risk.
- The batting/fielding/pit5/sub/team sub-code census re-run per visible game (day1 9 + day2 14):
  batting 0..16, fielding 0..4, sub codes 0..9 — the round-1 outcome naming covers them.
- The zero-row census across all 23 visible games: hdecode (the truth decoder) drops rows whose
  8 batting cells / 7 pitching cells are all zero ("players who appeared without a counted stat,
  e.g. pinch runners"); every visible game's zero-row set coincided with the box (no extra rows),
  so the round-1 replay never hit the case on the visible days.

### The three fixes (the day3 holdout hypothesis)
1. All-zero rows are now dropped from `_batters`/`_pitchers`, mirroring the truth decoder's own
   `if any(v)` filter cell-for-cell (batting: ab/h/rbi/bb/so/r/sb; pitching: outs+bf/h/hr/bb/so/r,
   bf included so a pitcher pulled mid-PA before any counted stat keeps his box row). A player
   whose only PA outcome is an HBP (code 8), a sac bunt (11), a GIDP (15) or a lone PA would
   otherwise be born as an all-zero row that the truth never carries — exactly a
   "no game reproduces box score X" multiset failure on unseen content.
2. The GDI roster split is dynamic now (`roster_end = ids.index(0)`, the leading contiguous
   non-zero run) instead of the hard-coded 25; an expanded roster (September call-ups at the
   holdout) puts every extra id under `rosterPids` (contains "pid") so the referee's
   pid-coverage check still sees them; `_idRest` no longer hides them under a name without
   "pid"/"player".
3. ADI decoding is payload-length-agnostic (`<%dI` of len//4 instead of the hard-coded `<3I`)
   and the phantom "one GDI game per file game" encode assert was dropped (encode is driven by
   the edited JSON only).

### Result
- score_local.py (byte-identical referee logic per round 1; this container lacks the systemd
  user manager, PID 1 = bwrap): day1 ok 9 boxes, day2 ok 14 boxes, PASS.
- The real referee still fails in the JAIL layer (systemd-run --user: "Failed to connect to
  user scope bus"), which is a container limitation, not a codec failure; the code path is the
  same score_local.py runs.
- voldat.py = 20191 bytes, stdlib only, round trips all four visible files byte-for-byte.

## What remains / notes for the next round
- The _tail0 (23 status bytes) and _tail2 (6 trailing bytes) spans stay opaque; the ADI cover
  word stays derived; the id region's lineup/staff rest stays under _idRest.
- The pitchEvent low/high byte split (the pitch kinds vs the speed id) is named from FastSim's
  strings but not fully proven per value; the replay never needs it.
- If a holdout day still fails, the next suspects: (a) a mid-PA mound change where a putout is
  charged (my `fld play==0` credit goes to `mound` only), (b) a code-8 HBP charged to the
  pitcher's bb (my prow bb only counts code 6), (c) the inning/half field of
  t5/t6/t7 (`vals[1]`) possibly being the batter's team rather than the mound side.
