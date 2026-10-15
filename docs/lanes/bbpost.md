# Where the ASN keeps the postseason

## Question
Where does an association file keep its postseason games, the series scores and the champion, and can the news site
read them back without the game's screens?

Short answer: one member, `po` (1 record, 283 bytes), holds the whole bracket: each series' teams, wins, winner and
every game's score. The champion is its World Series winner. The `s` schedule records with p[15] = 1 hold the same
games with dates, but their record slots are reused between rounds, so `po` is the source to parse.

## Snapshots
One 30-team association, 30L2025, two leagues of 15 (read only, under /mnt/nvme/bbpro98/tmp/s30):
- A `mid/Assn/30L2025.ASN`: saved October 6 2025, postseason scheduled, no postseason game played.
- B `out3/complete_0/Assn/30L2025.ASN`: right after the World Series (champion screen: Seattle Mariners over the
  Phila. Phillies). The folder also has `.eos` (32768 bytes) and `.apc` (66 bytes) that A lacks.
- C `out3/roll_0/Assn/30L2025.ASN`: after the offseason rollover to 2026 (557056 bytes, A and B are 393216).

Evidence below is `python3 work/postdiff.py A B C` (diff lines) and `--member s --flag15` (decoded games). Offsets are
into a member's plain payload as `gamedata._members` returns it. Team ids are t record numbers (2 Boston, 3 New
York Yankees, 9 K.C. Royals, 13 Seattle, 18 Phila. Phillies, 20 Chicago Cubs, 25 Diamondbacks, 29 San Diego).

## Members
| member | A n | A len | B n | B len | C n | C len |
|--------|-----|-------|-----|-------|-----|-------|
| a      | 1   | 256   | 1   | 256   | 1   | 256   |
| s      | 2435| 17    | 2448| 17    | 2415| 17    |
| tr     | 4   | 21    | 0   | -     | 841 | 21    |
| l      | 2   | 46    | 2   | 46    | 2   | 46    |
| d      | 5   | 30    | 5   | 30    | 5   | 30    |
| xs     | 30  | 16    | 30  | 16    | 30  | 16    |
| t      | 30  | 256   | 30  | 256   | 30  | 256   |
| r      | 30  | 294   | 30  | 294   | 30  | 294   |
| df     | 1   | 100   | 1   | 100   | 1   | 100   |
| po     | 1   | 283   | 1   | 283   | 1   | 283   |
| sp     | -   | -     | -   | -     | 0   | -     |

A to B changes: a (1 record), s (20 changed, 13 added), tr (4 removed), t (8), r (14), po (1). l, d, xs, df unchanged.

## Postseason games
**Schedule records.** An `s` record with p[15] = 1 is a postseason game; p[15] = 2 is the All-Star game (July 14,
away 0 and home 0, `A s 0#619: ... p15=2 ... month=7 day=14`). `--flag15` counts:
- A: `A: 21 of 2435 s records have p[15] != 0` (20 postseason, all `played=False`, plus the All-Star game).
- B: `B: 34 of 2448 s records have p[15] != 0` (33 postseason, all `played=True innings=9`).
- C: `C: 1 of 2415 s records have p[15] != 0` (only next year's All-Star game, unplayed).

In A the game pre-schedules every first-round series at full length: five records per series, Oct 6, 7, 9, 10 and 11,
slots 0 (NYY v BOS), 1 (SEA v KC), 3 (CHC v SD), 4 (ARI v PHI), records 2415 to 2434. When a series ends early its
unused records are rewritten for the next round, not removed: record 2423 is `K.C. Royals at Seattle, Oct 10, slot 1`
in A and `Boston at Seattle, Oct 18, slot 2` in B (`s 0#2423 16: u8 0 -> 9` is its innings byte). Records 2435 to 2447
are appended. So a record number says nothing about the series, and the slot is not a stable series id either (the
ALCS uses slot 2, the NLCS slot 5, the World Series slot 0). Guess: the slot is the bracket position for rounds 1 and 2
and the World Series reuses 0.

No byte of the `s` record names the round. The round is only recoverable by grouping games by team pair and ordering
by date, which is fragile. That is why the parser reads `po`.

**The bracket member `po`.** A to B, only bytes in `po` change from 0 to the series data (`po 1#0 23: u8 0,0,0,0,0,0,0
-> 2,3,4,1,133,131,131`, `po 1#0 222: u8 25,... -> 13,7,13,13,18,4,3,...`); B to C it does not change at all (`== po
B->C: 0 changed`). Layout, checked against every one of the 33 played games in B:

| offset | bytes | meaning | A | B |
|--------|-------|---------|---|---|
| 1      | 1     | state (guess: 0 not started, 2 complete) | 0 | 2 |
| 2..4   | 3     | games per round (best of) | 5, 7, 7 | 5, 7, 7 |
| 11, 79 | 8 each | league header: 3 bytes (guess: counts), the 4 first-round teams at +3..+6, pennant winner at +7 | | |
| 19, 39 | 20 each | league 1 first-round series | | |
| 59     | 20    | league 1 championship series | | |
| 87, 107 | 20 each | league 2 first-round series | | |
| 127    | 20    | league 2 championship series | | |
| 147..214 | 68  | all zero (guess: a third league's block) | | |
| 215..222 | 8   | World Series header: +3 and +4 the two pennant winners, +7 the champion | | 13, 18; 13 |
| 223    | 20    | World Series | | |

One series block (20 bytes):
- +0 best of (5 or 7)
- +1 winner's team id, 0 while undecided
- +2 team 1, +3 team 2
- +4 team 1 wins, +5 team 2 wins
- +6..+12 the away team's runs in games 1 to 7
- +13..+19 the home team's runs in games 1 to 7

Bit 0x80 on a run byte means that score is team 2's, so each game's away and home teams come from the flags and the
runs are the low 7 bits. A game count is wins 1 + wins 2.

Example, the NL first round CHC v SD at 87: `5, 20, 20, 29, 3, 1`, away runs `7, 10, 3|0x80, 1|0x80`, home runs
`6|0x80, 2|0x80, 2, 6`. That is CHC 7 at SD 6, CHC 10 at SD 2, SD 3 at CHC 2, SD 1 at CHC 6, the same as B's
`s 0#2425` to `0#2428` (`away=20 ar=7 home=29 hr=6`, `ar=10 ... hr=2`, `away=29 ar=3 home=20 hr=2`,
`away=29 ar=1 home=20 hr=6`).

Team 1 is not always the home team in game 1: in the four first-round series team 2 hosts game 1, in the ALCS team 1
(Boston) hosts it (`B s 0#2434: month=10 day=14 slot=2 away=13 ar=7 home=2 hr=1`). Read home and away per game from
the flags, never from the team order.

All seven B series decoded this way (wins as team 1 to team 2, games as `s` records confirm):
- AL round 1: NYY 2 to BOS 3 (best of 5); SEA 3 to KC 0.
- NL round 1: CHC 3 to SD 1; ARI 1 to PHI 3.
- ALCS: BOS 2 to SEA 4. NLCS: CHC 0 to PHI 4.
- World Series: SEA 4 to PHI 3, seven games, Oct 25 to Nov 2 (`B s 0#2437`, `0#2442` to `0#2447`).

## Champion
The champion is the World Series block's winner (po 224 = 13, Seattle), repeated at po 222 = 13. The series score is
po 227 and 228: 4 and 3.

**The game's own champion screen disagrees with its file.** It read "capture the World Series by beating the Phila.
Phillies by a score of 4 games to 2". The file and the seven `s` records agree on 4 to 3: Philadelphia won games 1, 2
and 5, and Seattle won 3, 4, 6 and 7 (`B s 0#2446: month=11 day=1 ... away=18 ar=3 home=13 hr=4`, `0#2447: month=11
day=2 ... ar=3 ... hr=5`). Guess: the screen's loser-wins argument is computed as games minus 5, or it is read before
game 7 is counted. In either case a story should take the score from `po`, not from the screen text.

The pennant and champion bytes must not be trusted before the series ends. In A, before any postseason game, po 86
(league 2 pennant) and po 222 (champion) both already hold 25 (Diamondbacks), and po 18 holds 13. B overwrote 86 with
18 and 222 with 13. Use a series block's +1 winner (0 while undecided) and po 1 = 2, not the header bytes.

The `t` records that change A to B are exactly the eight postseason teams (2, 3, 9, 13, 18, 20, 25, 29). The changed
bytes look like a runtime buffer written over the record's slack: offsets 40..43 get the same 4 bytes in all eight
(`t 2#0 40: u8 200,100,43,2 -> 40,219,148,1`, same line for 3, 9, 13, 18, 20, 25, 29), and text bytes in 62..111 turn
into pointer-like words (`t 2#0 95: u8 97,116,32,67,... -> 0,40,250,86,...`). Only the u16 at 112 differs per team
(Seattle and Philadelphia 36392, Boston 59104, the other five 58392 or 58424). Guess: 112 marks how far a team went,
but four values for four outcomes was not proven. Not decoded: the `r` diffs (14 rosters). Not checked:
Stats/30L2025.DAT, the box score files, and the `.eos`/`.apc` pair.

## Rollover
B to C:
- `s`: all 2415 regular-season records rewritten for 2026, and the 33 postseason records removed (`== s B->C: 2415
  changed, 0 added, 33 removed`). Only next year's All-Star record keeps p[15] = 2.
- `po`: unchanged. After the rollover it still holds the 2025 bracket with state 2, until the next postseason
  overwrites it.
- `xs`: all 30 team records zeroed (`xs 1#0 1: u8 79,83,42,39,... -> 0,0,0,0,...`).
- `tr`: 841 transactions added. `r`: all 30 rosters changed. `df`: changed (`df 0#0 8: u8 3 -> 26`).
- `a`: the season date at payload 14 moves on (`a 1#0 14: u8 83 -> 237 | u16@14 19027 -> 19181`).

So a reader of a rolled-over file finds last season's bracket in `po`. Whether it belongs to this season is told by
the schedule: no `s` record with p[15] = 1 means the bracket is the previous season's.

## Proposed parser
```python
def postseason(asn_path):
    """The bracket in the ASN's po member: {'rounds': [{'round': int, 'series': [...]}], 'champion': tid or None,
    'complete': bool}. Rounds 1 and 2 hold both leagues' series (league 1 first), round 3 the World Series."""
```
- `rounds[0].series`: blocks at 19, 39, 87, 107. `rounds[1].series`: blocks at 59, 127. `rounds[2].series`: block at
  223.
- Each series: `{'teams': [p[+2], p[+3]], 'wins': [p[+4], p[+5]], 'best_of': p[+0], 'winner': p[+1] or None,
  'games': [{'away': tid, 'home': tid, 'away_runs': int, 'home_runs': int}]}` for the first wins 1 + wins 2 games. For
  the spec's `home`/`away`/`wins: [h, a]` keys, `home` is the team that hosted game 1 (from the flags) and the wins are
  reordered to match.
- `champion`: the World Series block's winner when p[1] == 2, else None.
- `complete`: p[1] == 2.
- Skip a block whose best-of byte is 0 (an unused slot, as at 147..214).
- Add a `current` flag: True when any `s` record has p[15] == 1 (the bracket is this season's), False after the
  rollover. The archiver writes the past season's bracket at the rollover from that False case.

The parser can be built now for this shape: two leagues, four teams each, rounds of 5, 7, 7.

## Open questions
- Other bracket shapes: a 28-team MLBPA97 association, one league, or more playoff teams. Only one snapshot shape was
  read, so the league header's first 3 bytes and the 147..214 block are guesses. Check one MLBPA97 ASN before the
  parser trusts the fixed offsets: refuse a shape whose header bytes differ from 2, 3, 4 instead of guessing.
- Why the champion screen says 4 to 2 for a 4 to 3 series. Check whether the stock string's arguments come from po
  227/228 (BBShell's champion handler, near champtext's patch site).
- What po 6 (63 in A, 85 in B) and po 7..9 hold. Guess: a day counter.
- Whether the box score files (Stats/30L2025.H*) and the DAT carry postseason lines.
