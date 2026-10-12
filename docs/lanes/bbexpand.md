# Lane bbexpand: add teams and leagues to a career association

Status: built and run in game. `work/lahman/expand.py` writes a new association from a preseason one;
`work/lahman/tests/test_expand.py` runs it on a copy of 16L1927 and decodes every file it writes. An 18-team 18X1927
(16L1927 plus PHO and DEN in the NL) loaded and played a full season in the scratch game on 2026-10-12 (section 8,
Results). Not run: a season rollover and a 30-team association.

## Verdict

- The game can hold a shape change for a career association. Each shape's schedule and division layout come from a
  template the game minted (`structure.SHAPES`, `/mnt/nvme/bbpro98/lahman/templates`). The expansion carries the source's
  players, stats, transactions and team records into that template, so the schedule is the game's own.
- Reachable by adding teams without re-cutting divisions (stock templates): T8→T10, T12→T14_77, T16_2L→T18, T16_2L→T20,
  T18→T20, T24_2x12→T26_12_14, T24_2x12→T28_77, T24_3x8→T26_8_8_10, T26_12_14→T28_77. A new league: T8→T16_2L,
  T16_2L→T24_3x8, T16_2L→T26_8_8_10, T22→T34, T14_554→T30, and others (computed from `structure.SHAPES`).
- **MLBPA97 (T28_554, two leagues of 5/5/4) has no stock growth target.** Its only 30-team template, T30, is
  `[5,5,4],[8,8]`: the AL would have to be re-cut. The expansion keeps each team's league and division, so MLBPA97 needs a
  template of its exact target shape (e.g. NL 5/5/5 and AL 5/5/5) minted in the game first. Whether the game mints that
  shape is unverified.
- **Depth limits the count.** Expansion draws on the existing rosters and the free-agent pool. 16L1927 has 0 free agents
  and thin rosters: two new teams seat (T18), four are refused (T20, "not enough free agents"). A 28-team league with a
  494-player pool (MLBPA97's) is larger, but its shape is the blocker, not the pool.

## 1. Inventory: every file an association owns

Paths are `Assn/<stem>.*` and `Stats/<stem>.DAT` in an install. Evidence: the decoded copies in
`/mnt/nvme/bbpro98/lanes/bbexpand/probe` (MLBPA97, a 28-team career association with 169 games played; 16L1927, a
preseason 16-team build) and the templates in `/mnt/nvme/bbpro98/lahman/templates`. ASN members are found by name
(`ctree.parse`).

| File / member | Contents | Team ids | Player ids | Expansion |
|---|---|---|---|---|
| ASN `a` (1 rec, 256 B) | association name, trophy, season dates (u32 at 0x0a, 0x0e) | none | none | source record copied; key byte from the template |
| ASN `l` (2 rec, 46 B) | league name 0x04, abbrev 0x25, layered flag byte 2, DH flag byte 3, division keys 0x2a..0x2c | none | none | source names, template division keys |
| ASN `d` (2 or 6 rec) | league idx byte 1, division idx byte 2, name 0x03, team keys 0x14..0x1d (10 slots) | **value** (list of team keys) | none | rewritten with the new slot keys |
| ASN `t` (N rec) | team: record key = team id (index key); name 0x12, manager 0x34, abbrev 0x45, stadium 0x53, city8 0x74, ownership byte 0x0c (1 human, 0 computer), weather code byte 4 | **key** | none | moves to its slot (key byte rewritten) |
| ASN `r` (N rec, 294 B) | roster window: record key = team id; ids 0..24 active, 25..54 reserve (id, level) pairs, 77..112 two batting orders and two alignments, 113..125 rotation and bullpen; u16 words at payload 42 (build.py `r_record`) | **key** (+ none in window) | window values = 100 + PYR index | unchanged teams keep their window; changed or new teams rebuilt (section 2e) |
| ASN `xs` (N rec) | team W, L (bytes 1, 2); record key = team id | **key** | none | zeroed by the template; refused unless every team is 0-0 |
| ASN `s` (games per team × N / 2 regular records, plus specials) | schedule: away p[6], home p[10] (team ids), played flag p[14] == 0 means played, special p[15] | **value** | none | the template's schedule, unchanged |
| ASN `tr` (plain, 21 B) | transactions: pid at p[6] and p[13], team fields p[12] and p[19] (255 = none), kind p[20] | **value** at p[12], p[19] | pid values | template's rows deleted, source rows added with team fields remapped |
| ASN `df` (1 rec, 100 B) | draft board: 50 u16 (values include ids ≥ 100) | possibly | yes | **dropped**: no `df` member in any template |
| ASN `po` (1 rec, 283 B) | playoff record, plain | not decoded | not decoded | **dropped**: no `po` member in any template |
| ASN `sp` | empty in MLBPA97 (1398 tombstones, 0 live) | n/a | n/a | nothing |
| Stats `<stem>.DAT` (49 members: bt, pt, ft, bs*, ps*) | stat rows: word0 scope (0, 1, 2, 3, 16, 17), word1 = 2, word2 = **player id (≥ 100) or team id (< 100)** (stats.py) | **value** (word2 < 100) | word2 ≥ 100 | player rows byte-identical; team rows word2 remapped |
| Assn `<stem>.PYR` | 192-byte header + 192-byte records, enciphered with the seed in header bytes 0..1; record i is player id 100 + i | none (no team field) | record index | copied byte for byte (no players are created) |
| Assn `<stem>.PYF` | `PPD:`, u32 length (2 + 2n), s16 n, n u16 free-agent ids, then a stale tail (MLBPA97: 74 bytes after 494 ids) | none | free agents | ids removed as they are signed; tail kept |
| Assn `<stem>.apc` | champions history: `PC0:` chunks, year and team-name strings (524 B, misc8 spec) | by name only | none | copied |
| Assn `<stem>.eos` | c-tree superfile: psaMvp, psaCy, psaRook, hof, psaTC (20/20/20/86/4 records, 64 B) | **not identified** | names and numbers; ids not identified | copied byte for byte (unverified, section 7) |
| Assn `<stem>.pyc` | `PPD:` header with count 0 and a stale list in the tail (MLBPA97) | stale | stale | copied |
| Stats `<stem>.H<day><game>` | one box score per game; watch.py keeps the last seven days (`news/watch.py`, `work/hdecode.py`) | yes | yes | not carried (a new stem starts with none) |
| hilights `<stem>.NQ0` | 306 KB in MLBPA97; format not decoded | unknown | unknown | not carried |
| Mods `focus.txt` | `pid birth kind assn` lines, keyed by stem (CLAUDE.md) | no | yes | not carried |
| news data folders | per stem, outside the game dir (watch.py) | per stem | per stem | not carried |

Team id is a **key** in `t`, `r`, `xs` (the index is built on it, so the slot a team occupies is its id) and a
**value** in `d`, `s`, `tr`, the stats rows, and possibly `po`/`eos`. A team that changes slot must move in every key
and value; `ctree.do_apply` rebuilds the B-trees over every touched member, and `_index_ok` in the test checks the
rebuilt trees (sorted keys, pointers equal the live records, counts equal).

Team-row evidence: in MLBPA97's DAT every stats table has team rows with word2 = 1..28 in scopes 0, 1, 16 and 17 (the
team totals and pre-game snapshots); one exception, `bsl` scopes 16/17, has 27 of them.

## 2. Design

a. **Refuse a season in progress**: any regular game (both teams in 1..N, special 0) with played flag 0, or any team with
   W or L nonzero in `xs`.

b. **Target shape**: the source's league and division sizes plus the adds. A new league (`--new-league`) comes last;
   its divisions are the names the adds give, in order of appearance. The shape must equal an entry in
   `structure.SHAPES` with a minted template in `--templates`. Divisions are never re-cut: an existing team keeps its
   league and division, and every division's size is the source's plus its adds.

c. **Slots**: the template's slot keys for each (league, division) come in plan order (`template_slots`). Existing
   teams keep their order in the division and take its first slots; each new team takes the next slot, in add order
   (`assign_slots`). T18 keeps every old key (new teams 17 and 18). T20 moves the NL from 9..16 to 11..18 (new AL 9, 10;
   new NL 19, 20), covered by `test_slots_of_the_two_league_shape_move_the_old_teams`.

d. **Container**: the template's ASN (its member set, index and schedule), with every slot's `a`, `l`, `d`, `t`, `r`
   rewritten in place (same record length, checked), `xs` left at the template's zeros, `tr` replaced by the source's
   transactions (team fields remapped), and no `df`/`po`/`sp` (the templates have none).

e. **Players**: each existing team protects its 15 best by value (pitcher: control + endurance + strikeout attribute +
   mean pitch rating; hitter: contact + power + speed + fielding at his position; `value_of_fn`). Then the expansion draft
   (`expansion_draft`): new teams pick in turns, 30 each. A pick must leave its team with at least 25 players, 10
   pitchers and 9 fielders (`can_go`). A new team picks only pitchers while it needs them to reach 10 from the picks
   left, and only hitters while it needs them to reach 15 hitters. Then `seat()` tops each new team and each team that
   lost players up from the free-agent pool (best by value) until it has 25 active with 10 pitchers and 9 fielders.
   If the pool cannot do that, the run is refused before any file is written.

f. **Rosters and lineups**: a team that lost no one keeps its window bytes (only the key byte changes). A team that lost
   players or is new gets `B.choose_roster`'s split and build.py's `lineup`, `staff` and `r_record`, all driven by the
   ratings (`FillerSeason`), not by stats. A reserve list may be empty, as in the stock builds (16L1927 has teams with
   0 reserves).

g. **Stats**: player rows are untouched. Team rows (word2 < 100) take the team's new slot (`remap_stat_teams`, via
   `stats.stat_records` and `ctree.do_apply`). New teams have no rows, which is how a fresh build starts.

h. **Files**: `.ASN` from the template, `.PYR` copied, `.PYF` rewritten with the signed free agents removed, `.DAT`
   remapped, `.apc`/`.eos`/`.pyc` copied when present. The output stem must not exist and must be 8 characters or fewer.

## 3. Code

`work/lahman/expand.py` (stdlib plus the repo's `ctree`, `stats`, `lahman.build`, `lahman.ratings`, `lahman.asnfile`,
`lahman.structure`). `work/lahman/build.py` gets one change: `load_template(key, templates=None)`, so the expansion can
read a templates directory other than the default.

```
python3 work/lahman/expand.py --install DIR --assn STEM --templates DIR \
    --add "LEAGUE:DIVISION:City:Name:ABR" [--add ...] [--new-league NAME] [--name NAME] --out-stem NEWSTEM
```

- The new association's name (the label in the load list) is `--name`, else `NEWSTEM <source name>` cut to 32
  characters (18X1927 reads "18X1927 1927 Major League Baseball"). The list sorts by label and clips it past about 19
  characters, so a copied name gave two identical rows (found in the in-game check, section 8).

- LEAGUE is a league's name or abbreviation (or the `--new-league` name). DIVISION is a division's name or a 1-based
  index (16L1927's single divisions have blank names; use `1`). The team name is `City Name` (16 characters at most: the game saves 16, section 8);
  the abbreviation is up to 3 letters or digits.
- Refusals (`ExpandError`, exit 2, nothing written): a game played or a team record this season; out stem already
  present; a duplicate team name or abbreviation (against the source and within the adds); an unknown league; a shape
  with no entry in `structure.SHAPES`; a shape whose template is absent or has no schedule (`load_template`, which
  covers the 14-team-league landmine); a pool that cannot seat the new teams.
- Output summary: one line per team (key, abbrev, league, division, active, pitchers, reserve, NEW, players out), then
  players drafted, free agents signed, transactions carried, side files copied, and the dropped members.

Example run (16L1927 → 18X1927, the test case):

```
16L1927 -> 18X1927: template T18, shape [[8], [10]], 16 teams -> 18
   1 BOS  American League        act 25 (P 10) res  9 out 1
   ...
   9 BRO  National League        act 25 (P 10) res  4 out 1
  ...
  17 PHO  National League        act 25 (P 10) res  5 NEW
  18 DEN  National League        act 25 (P 10) res  5 NEW
players drafted 60, free agents signed 0, transactions carried 0, side files [], dropped none
```

## 4. Tests

`work/lahman/tests/test_expand.py`: 22 tests. They copy 16L1927 (and MLBPA97 for the refusal and the DAT and
transaction remaps) into a directory under `$SCRATCH`, run `expand`, and decode every output file with the repo codecs:
ASN via `AsnFile` and `ctree` (every enciphered record decodes and re-encodes to its own bytes; every index tree is
consistent), PYR (`_pyr_recs` and `RT.write_pyr` round trip), PYF (`read_pool`/`write_pool` round trip, MLBPA97's stale
tail included), DAT (`stats.stat_records`, player rows equal to the source, index consistent).

Checked for T18 (the one case 16L1927 can reach; T20 is refused for depth, tested):
team count and leagues; new teams named, Computer, no manager; original teams keep name, manager, park, ownership;
PYR byte-identical; every window id a real player, no player on two teams, every roster 25 active with ≥ 10 pitchers
and ≥ 9 fielders; original teams lose only drafted players and gain only free agents; schedule equal to the template's;
season dates and trophy unchanged, association name led by the out stem; stats player rows unchanged; lineup, rotation and bullpen ids on
the roster; log names every new team.

Refusals: a played season (MLBPA97: 169 games), no shape (16 + 1 = `[8],[9]`), duplicate team name and abbreviation,
unknown league, a 24-team league with eight new teams and no free agents, four new teams (T20) with no free agents, the
PYF codec, and `parse_add` spec errors.

Other: `test_stat_team_rows_follow_the_team_slots` (MLBPA97's team rows, reversed slot keys: rows move, player rows and
the other fields do not, index consistent) and `test_transactions_follow_the_team_slots` (MLBPA97's live transactions).

Results: `SCRATCH=/mnt/nvme/bbpro98/lanes/bbexpand python3 -m pytest work/lahman/tests/test_expand.py -q` → 22 passed,
0 skipped. The whole `work/lahman/tests` → 189 passed, 7 skipped; the skips are pre-existing (test_build.py needs the
`$SCRATCH` directory `/mnt/nvme/bbpro98/tmp`, which this host lacks; test_lahdb.py's database check). `capped` is not
installed on this host, so pytest ran directly. pyflakes is clean on both new files.

## 5. What is carried and what is lost

Carried: every player record (ids, ratings, names), every player's stat rows (both scopes 2 and 3 and the scope 0/1/16/17
player rows), every original team's name, manager, abbreviation, stadium, city8, ownership, roster ids (except the
drafted players), transactions (team fields remapped), the season dates, the association name and trophy, the schedule
shape of the template, the free-agent list, the champions history (`.apc`), the awards and Hall of Fame file (`.eos`,
bytes only), the `.pyc` list.

Lost or reset:
- `df` (draft board) and `po` (playoff bracket): no member in the template, so dropped. The game creates them itself on
  a fresh association (16L1927 has neither), but whether it does so mid-career is unverified (section 8).
- Box scores (`Stats/<stem>.H*`) and highlights (`hilights/<stem>.NQ0`): not carried.
- News data folders and Mods `focus.txt`: keyed by the old stem; the new association starts without them.
- The stat-based batting order and rotation of every team that lost players: rebuilt from ratings.
- Team art and park: the new teams take the template slot's stadium, city8 and weather code (stock values for that slot).
  Their manager is blank and their name and abbreviation are the adds'.
- The schedule: the template's, so every team plays its template count. T18: slots 1–8 (AL) 154 games, slots 9–18
  (NL, the original NL teams included) 162. 16L1927 was 154 for everyone, so the original NL teams play 8 more games.

## 6. Limits the code does not solve

- `work/league.py` caps team ids at 28 in `parse_container`, `build_json`, `_game_json` and `encode`'s division writer
  (lines 149, 158, 159, 177, 209, 224, 411). An association with more than 28 teams decodes with the new teams missing
  from `league.py`'s JSON. `news/gamedata.py` uses `MAX_TEAM = 34` and reads them. Not changed here.
- Adding a team inside an existing division (or a whole division) to a shape with no stock template is refused until
  the template is minted. The tool does not re-cut divisions.
- The depth check is by pool and roster floors, not by ratings; a thin league is refused, not padded with generated
  players (build.py's pads are not available at expansion time).

## 7. Not verified

- The `.eos` file's team references: its 64-byte records carry names and small numbers, and no team field has been
  identified. It is copied byte for byte. If a record holds a team slot, the Hall of Fame or award screen will show the
  wrong team after a slot move; the in-game check should look at it.
- `po` and `df` contents (not decoded; only their absence from the templates is known).
- `hilights/*.NQ0` format.
- The game's behaviour with a 30-team association. The T30 template's own schedule gives 16 teams 160 games and 14
  teams 162. Not run.
- Whether the game looks up art (logos, uniforms, the park) by abbreviation or city8, which the new teams do not have
  stock files for. Unverified; the in-game check below looks at the new teams' screens.

## 8. In-game checks (orchestrator)

Build the case in a scratch install only, never the live prefix or MLBPA97:

```
mkdir -p $SCRATCH/game/Assn $SCRATCH/game/Stats
cp <work_install>/Assn/16L1927.{ASN,PYR,PYF} $SCRATCH/game/Assn/
cp <work_install>/Stats/16L1927.DAT $SCRATCH/game/Stats/
python3 work/lahman/expand.py --install $SCRATCH/game --assn 16L1927 --templates /mnt/nvme/bbpro98/lahman/templates \
    --add "NL:1:Phoenix:Dogs:PHO" --add "NL:1:Denver:Mile High:DEN" --out-stem 18X1927
```

Then, in the scratch game (harness lane, its own Wine prefix; `news/watch.py --game G --data D --once --no-llm` first if
the association pages must open):

1. Association list. 18X1927 reads "18X1927 1927 Major..." (the stem leads the copied name; before that change the
   list showed two rows with one label). The `seasonloop.season` wrong_association guard still catches a wrong row.
   Association Data: AL 8 teams, NL 10 teams, division fields blank; check the screen does not ask to save on exit.
2. Preseason, team keys 17 (PHO) and 18 (DEN): the roster for each shows 25 active and at least 10 pitchers; the
   batting order has no blank slot (LINEUP.DLL crashes on a 0 in the order; build.py landmine).
3. Standings: 18 teams, AL 8, NL 10.
4. Sim one full season (`seasonloop.season`). Judge by games played, not by the screen: count the regular games with
   played flag 0 (`p[14] == 0`) per team from the ASN `s` records after the sim. Expected: keys 1–8 = 154 games each,
   keys 9–18 = 162 each (the template's count per slot, section 5). Any team with a different count fails the check.
5. Roster counts per team after the season: every active roster has at least 5 pitchers (the build.py landmine) and 25
   active; check the new teams' and the drafted-from teams' rosters.
6. Season rollover (`seasonloop` "seasons" demographics): no crash, the new season's file still decodes, and the
   association list still shows 18X1927 with 18 teams.
7. Player records: the PYR is byte-identical to 16L1927's (the test asserts this on disk; check it again after the sim
   and the rollover, since the game writes the PYR at rollover).

### Results, 2026-10-12 (harness lane 2, `plan_season.json`, gate files in /mnt/nvme/bbpro98/lanes/bbexpand/gate)

- 1. Load list shows "18X1927 1927 Major...", one row; Association Data shows AL and NL, division fields blank, Career.
- 4. Season: 1426 of 1426 regular games played, one mid-season amateur draft (seasonloop ran it). Per team, scheduled
  and played both equal the template: keys 1 to 8 154 each, keys 9 to 18 162 each. No team off by one.
- 5. Rosters after the season (r records, active plus reserves including the draftees): 35 to 43 players, 17 to 21
  pitchers per team. PHO 40/19, DEN 39/19.
- 7. The PYR is not byte-identical after a season, and should not be expected to be: the draft added 478 players (512
  to 990), none removed, and the game rewrote in-season fields of all 512 original records (bytes 2 to 63, ratings and
  condition). Names and birth dates of all 512 are unchanged. The byte-identical check holds for expand.py's output
  before the game runs (the test asserts it).
- Found and fixed: the game saves 16 characters of a team name and a NUL at byte 16, though the record holds 32. The
  season cut "Phoenix Desert Dogs" to "Phoenix Desert D". Stock names abbreviate to fit ("Phila. Athletics").
  `NAME_FIELD` is now 16 and `parse_add` refuses a longer name (test, and a positive control at 31 fails it).
- Open: a new team's manager. expand.py blanks the manager field's first byte and the template's tail stays ("\0erry
  Collins"); after the season the field reads "\0ob O'Farrell", so the manager screen shows no name for PHO and DEN.
  Not checked on screen. Item 6 (rollover) not run.

MLBPA97 is not an input: the tool refuses it (games played), and no template of its target shape exists yet.

## 9. Open questions for Will

- A template of the target shape for MLBPA97 (e.g. 30 teams, NL and AL 5/5/5) has to be minted in the game. Is that the
  intended first case, and which teams and divisions should the two new teams join?
- Team names: the `City Name` form in the add ("Phoenix Dogs", 16 characters at most) is my choice; the stock names are one-word
  cities in MLBPA97 (`Atlanta`, `Florida`). Say if the name field should take the city alone.
