# Task: decode the ASN tail log (last 32KB of MLBPA97.ASN)

Reverse-engineering task for Front Page Sports Baseball Pro '98 (Win98 game, data files only, no game running).

## Deliverable
One file: /mnt/nvme/bbpro98/re/tail_log_decode.md containing:
1. A byte-level field map of the 25-byte log entry (every byte offset: what it is, evidence).
2. An event-type table (each observed value of the type byte(s) -> what event, evidence).
3. A mapping of EVERY day10 entry to a real April 11 league event where possible, or "unresolved" with your best hypothesis.
4. What the second id-like group in each entry is (team? money? game ref?) with evidence.

## Constraints
- Work ONLY under /mnt/nvme/bbpro98/re/ (create a scratch dir re/tail_log_work/ for your scripts; scripts run with python3 -I).
- Do NOT modify or delete any existing file except creating tail_log_decode.md and your scratch dir. Do NOT touch /mnt/nvme/bbpro98/work_install (read-only reference). NO wine, NO X display, NO network.
- Be terse in the output file. Evidence over prose. Quote bytes as hex.

## Files
- ASN snapshots: /mnt/nvme/bbpro98/re/asnseq/day01..day10/Assn/MLBPA97.ASN (each after one more sim day; day10 = April 11, day09 = April 10).
- Player database: /mnt/nvme/bbpro98/work_install/Assn/MLBPA97.PYR. Reader: /home/will/bbpro98/BBPRO98_package/research/dump_pyr.py (usage: dump_pyr.py FILE.PYR --rec N; player id = 100 + record index; pos code 1=P 2=C 3=1B 4=2B 5=3B 6=SS 7=LF 8=CF 9=RF; names are per-record substitution-decoded).
- 2427 player records, ids 100..2526.

## Verified facts (do not re-derive, build on these)
- Day10 (April 11) new bytes in the tail: range 0x299e1a-0x29a7ff (1238 bytes changed vs day09). Sector-start offsets that changed: 0x299e1a, 0x29a21a, 0x29a41a, 0x29a51a, 0x29a61a, 0x29a71a (record starts end in 0x1a).
- Entries are 25 bytes, stride-25 within a sector run. Each entry's bytes 21-22 = u16 LE date stamp; day10 entries carry 0x2FD6 (12246 = (era 47 << 8) | day 214); bytes 23-24 = u16 LE 0x000B (11) in every day10 entry observed.
- Bytes 0-1 u16 LE = a PYR PLAYER ID. Proven joins (via dump_pyr):
  1973 = Bob Wagner (2B), 2276 = John Aragon (SS), 881 = Darren Lewis (CF),
  534 = Ray Eibel (2B), 833 = Jorge Posada (C), 371 = Curtis Goodwin (CF), 1660 = Dave Maas (LF).
  Values > 2526 (e.g. 4608, 10214, 10658) are NOT player ids; one of them may be a team or game id.
- Day10 entry dump (index: offset: hex | u16 LE view) is reproduced below. Entries 0-12 are byte-identical; note repeated pairs: entries 19/20 differ only in the 4-byte group at offset 14-17; entries 22-26 are identical.
- Alignment caveat: entries pack at stride 25 inside sectors, but sector starts (offsets ending 0x1a) are true record anchors; an entry that would cross a sector start actually restarts there (entry at 0x29a21a reads [A=0x27e6=10214][... type 01][group e5 68 04][date][11]).

## Day10 entry dump
0 0x299e2e b5 07 01 00 00 00 08 b5 07 01 00 00 00 08 06 d4 bd 06 00 00 00 d6 2f 0b 00
1..12 identical to 0 (offsets 0x299e47 +25k through 0x299f5a)
13 0x299f73 b5 07 01 00 00 00 08 b5 07 01 00 00 00 08 06 07 79 06 00 00 00 d6 2f 0b 00
14 0x299f8c e4 08 00 00 00 00 ff 80 08 00 00 00 00 10 02 07 79 06 00 00 00 d6 2f 0b 00
15 0x299fa5 e4 08 00 00 00 00 ff 80 08 00 00 00 00 10 02 07 79 06 00 00 00 d6 2f 0b 00
   (gap of unchanged filler 0x299fbe..0x29a0c3)
16 0x29a0c4 71 03 00 00 00 00 ff 00 00 00 00 00 00 14 00 12 e6 27 00 00 00 d6 2f 0b 00
17 0x29a0dd 16 02 00 00 00 00 ff 00 00 00 00 00 00 15 00 12 a2 29 00 00 00 d6 2f 0b 00
   (gap 0x29a0f6..0x29a214)
18 0x29a215 00 12 e6 27 00 00 00 00 00 00 00 00 00 00 01 e5 68 04 00 00 00 d6 2f 0b 00   <- parser slipped; true entry starts at sector start 0x29a21a: e6 27 00 00 00 00 00 00 00 00 00 00 00 01 e5 68 04 00 00 00 d6 2f 0b 00 plus 5 preceding bytes 00 12 belong to the gap
19 0x29a22e 41 03 00 00 00 00 ff 00 00 00 00 00 00 06 00 e5 68 04 00 00 00 d6 2f 0b 00
20 0x29a247 41 03 00 00 00 00 ff 00 00 00 00 00 00 06 00 86 8f 06 00 00 00 d6 2f 0b 00
21 0x29a260 73 01 00 00 00 00 ff 00 00 00 00 00 00 13 00 be 90 06 00 00 00 d6 2f 0b 00
22 0x29a279 7c 06 00 00 00 00 ff ac 05 00 00 00 00 19 02 be 90 06 00 00 00 d6 2f 0b 00
23..26 identical to 22 (offsets 0x29a292, 0x29a2ab, 0x29a2c4, 0x29a2dd)
   (gap 0x29a2f6..0x29a3d6)
27 0x29a3d7 00 00 04 05 05 62 b1 00 00 00 04 05 06 85 b1 00 00 00 04 00 00 d6 2f 0b 00   <- different shape; two groups (04 05 05 62 b1 / 04 05 06 85 b1), may be two packed sub-records or a mis-sliced pair; investigate
Further entries exist up to 0x29a7ff; dump them yourself with the same anchor rule (bytes 21-22 == day stamp).

## Day09 anchor
Day09 (April 10) entries carry date stamp 0x2FD5. Use day09 vs day10 diffs the same way to confirm the structure generalizes (day09's changed range and sector starts you must compute; day09 scan with my stride-25 anchor from file start found 0 entries, so its records may sit at different sector offsets: find them by locating 0x2FD5 stamps in the tail).

## Ground truth: April 11 league events (from the game UI; some read by eye from a screenshot, treat wordy parts as approximate, numbers as exact)
- 6 National League games (schedule screen):
  FLA 4, MIL 0 (W: Fernandez, L: Melton)
  PIT 5, MON 0 (W: Lindsey, L: Hermanson)
  NY? 1-6?, CIN 1 (W: G?..., L: Paschall)   [uncertain score]
  CHN 5, HOU 0 (W: Gill, L: Garcia)
  PHI 5, STL 0 (W: Loaiza, L: Powell)
  LA?/COL 5-? in 10 innings (W: Cantwell, L: Geisel)  [uncertain]
- American League played the same day (count unknown; find it in the data).
- Full box score was pulled for one game, ATL at FLA, final 0-4 (FLA home):
  Line: ATL 000 000 000 - 0; FLA 003 100 00x - 4 (FLA scored 3 in the 3rd, 1 in the 4th).
  ATL totals: AB 30 R 0 H 4 RBI 0 BB 3 SO 7. FLA totals: AB 29 R 4 H 8 RBI 3 BB 6 SO 4.
  FLA batters (pos AB R H RBI BB SO): CF Lindsey 3-1-1-0-1-0; 2B Castillo 3-1-2-0-1-0; RF Sheffield 3-1-0-0-1-0; LF Floyd 2-0-0-1-1-0 (SF); C Johnson 3-0-2-1-1-0 (2B); 3B Rust 4-0-0-0-0-0; SS Crespo 4-1-2-0-0-1; 1B Bi?holder 4-0-1-1-0-2; P Fernandez 1-1-1-0-2-0; PH Lynch 1-0-0-0-0-0; P ?echrist 0-0-0-0-0-0; P Silva 0-0-0-0-0-0.
  ATL batters: CF Hosken 2-0-1-0-0-1; RF Tucker 4-0-0-0-0-1; 3B Jones 4-0-0-0-0-0; LF Klesko 3-0-0-0-1-0; C Lopez 3-0-1-0-1-1; 1B Sudhoff 3-0-0-0-1-1 (GDP); 2B Graffanino 3-0-0-0-1-1; SS Price 3-0-1-0-0-0 (2B); P Melton 1-0-0-0-0-1 (L, pitcher); PH Lake 1-0-0-0-0-1; P Hutchinson 0-0-0-0-0-0; P Mosser 0-0-0-0-0-0.
  Note: box-score names may differ slightly from PYR names (generate-a-player vs real); join via positions+stats, not strings. 2B: Price (ATL), Johnson (FLA). 3B: Brancato J. (FLA). GDP: Sudhoff (ATL), Sheffield (FLA).
- Transaction/news shapes (Association News screen, April 12 shown; April 11 not scrollable in UI but same shapes): "Apr 12: <TEAM> submitted claim for free agent <pos> <Name>." repeated for MANY teams on the SAME player (e.g. 2B Angel Scanlan claimed by ATL, BAL, BOS, CHA?, CHN, CLE, COL ...), interleaved with "<TEAM> awarded free agent <pos> <Name>." lines. The day10 log has 13 byte-identical entries for 2B Bob Wagner and then entries for 6 other players: a claim pile-on shape.
- The News screen teams are 3-letter abbreviations (ANN, BAL, BOS, CHA, CHN, CIN, CLE, COL, DET, KC...). Team ids live somewhere in the ASN (a prior probe noted team record 0 payload starts 01 1d 1d 1d a6 01) or another file; if you can map team abbreviations to numeric ids, test whether any entry field holds them.

## Method suggestions (you decide)
- Extract each day's changed tail bytes vs the previous day into scratch files first.
- Test simple hypotheses per field: u8 small ints (type codes), u16 LE ids, u24/u32 money-like values, packed pairs.
- The 0xff bytes at offset 6 in entries 14-22 (absent in 0-13) probably matter for the type split.
- Entry 27's shape differs; check whether the tail log interleaves two record classes (e.g. transactions vs game lines) or your stride slipped.
