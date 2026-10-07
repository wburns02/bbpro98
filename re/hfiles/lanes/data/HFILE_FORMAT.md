# Stats/MLBPA97.Hxx (per-game box score) - format, decoded 2026-10-07 (data lane)

All multi-byte ints are little-endian. Verified against per-day DAT deltas for
days 2..7 via check_hdecode.py: batting 1.0000, pitching 1.0000, 0 missing/extra.

## File structure

The file is a **chain of tables**, back to back, no padding, ending exactly at EOF:

```
table   := magic u16_unk u16_count u16_recsize body
magic   := 02 65                      (constant, every table)
body    := count * recsize bytes      (records, no per-record header)
```

Walk: `off += 8 + count*recsize` starting at 0. All 327 H files in
day01..day07 walk cleanly to EOF (0 bad magics, 0 overruns, 0 trailing bytes).

## Table inventory (per game file, H20 example)

| unk   | recsize | count | content                                                        |
|-------|---------|-------|----------------------------------------------------------------|
| 0xffff| 2698    | 1     | obfuscated blob (only encrypted table; NOT needed)             |
| 0     | 40      | 23-28 | **batting lines**, one row per player who batted, both teams   |
| 1..5  | 22      | 3-22  | small stat rows, unexplored (likely batting-related splits)    |
| 6..10 | 22      | 0     | empty                                                          |
| 0xb   | 70      | 3-8   | **pitching lines**, one row per pitcher, both teams            |
| 0xc..0x10 | 36  | 3-8   | 15-stat rows, unexplored (pitcher splits)                      |
| 0x11..0x15 | 36 | 0     | empty                                                          |
| 0x16  | 150     | 23-25 | big table, plaintext, unexplored                               |

Exactly one recsize=40 and one recsize=70 table per file (checked on all 327 files).

## Record layout (batting, recsize 40 = 20 u16; pitching, recsize 70 = 35 u16)

Identical to the mlbpa97.DAT scope-1 season lines minus the leading
[scope, 2] pair (work/NOTES_stats_format.md):

```
u16[0] = 0            (DAT: scope)
u16[1] = 0            (DAT: constant 2)
u16[2] = id           player id; team-total rows use team id 1..28;
                      rows of one of the two sides have 0x8000 ORed into id
u16[3..] = stat cols  c[i] = u16[3+i], same column order as .DAT lines
```

Batting columns (c = u16[3..], 17 cols): c0 AB, c1 1B, c2 2B, c3 3B, c4 HR,
c5 RBI, c6 BB, c7 SO, c8/c9 IBB/HBP, c10 SH?, c11 SF?, c12 G, c13 R, c14 SB,
c15 CS, c16 GIDP?. H = c1+c2+c3+c4 (derived, not stored).

Pitching columns share c0..c16 (opponent batting line against the pitcher;
c13 = R allowed, c14 = SB allowed); c18 outs, c19 BF, c20 W, c21 L, c22 SV,
c26 ER.

## Filters the decoder needs

- pid = id & 0x7fff. Real player pids are 100..2526 (MLBPA97.PYR, 2427 players);
  team-total rows mask to 1..28. Skip rows with masked id < 100.
- The file contains rows for players who appeared with no counted stat
  (e.g. pinch-runner: G=1, all stat cols 0). The truth (DAT deltas) has no row
  for them, so the decoder must skip rows whose scored cells are all zero.
- Pitcher rows appear in the batting table too (NL lineups) - they are just
  normal batting rows; emit when nonzero like anyone else.

## The obfuscated first table (unk=0xffff, 2698 bytes, not needed for stats)

- Plain is mostly zeros: ciphertext shows long runs of a single per-file byte
  (the "fill"), e.g. 0x8d in H20, 0xbc in H21, 0xa7 in H22 ... i.e. a **single
  constant per-file byte key**, XOR (or ADD) with per-file K.
- Constant-key decode beats a chained/rolling decode (fraction of bytes < 16:
  0.894 vs 0.845 on H20), and fill runs resume with the SAME byte across the
  whole table, which rules out `enc[i]=p[i]^enc[i-1]` chaining (the fill would
  drift after each data cluster).
- K is not a simple function of the ciphertext: T[0]^T[1], sum(T)&0xff,
  xor(T), T[0], T[-1] all fail to predict K across 13 day-2 files. K is likely
  derived from plaintext/game state (writer-side); the game's own reader must
  get it from somewhere else (header bytes or an external index).
- Decoded with K, the first ~19 bytes hold per-file data (bytes 2,3 are always
  equal in the raw ciphertext, so plain[2]==plain[3]); the rest is stat-shaped
  sparse data. Not decoded further - the plaintext tables carry everything the
  box score needs.

## Evidence

- check_hdecode.py (days 2..7, 77 game files): bat cell accuracy 1.0000
  (1544 players), pit 1.0000 (427 pitchers), 0 missing, 0 extra -> PASS.
- 13/13 day-2 batting rows and 7/7 pitching rows of H20 matched the day-2
  DAT delta exactly, including both team-total rows (excluded from output).

## Round 2 changes (2026-10-07)

- Removed the season-stat filename string from hdecode.py's docstring (the
  driver's mechanical leak guard greps decoder text for dataset paths; the code
  never touched those paths, only the comment named one).
- Decoder now sums rows per pid within a file instead of appending duplicates.
  Pure insurance for holdout days: a scan of all 327 day01..07 files found
  11,047 player rows with ZERO duplicate (table,pid) pairs, so aggregation
  never fires on observed data and referee output is unchanged (re-run: PASS,
  1.0000 both sides). Re-verified: 327/327 exact chain walks; all files decode
  rc 0; avg 19.9 batters / 5.4 pitchers per file; empty/garbage/truncated
  inputs give valid JSON.
