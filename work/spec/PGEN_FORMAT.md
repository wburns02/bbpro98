# Player-generator DAT entries (SHELL.VOL)

Codec: `work/pgen.py` (decode/encode JSON, byte-exact round trip, every field offset asserted). Mapped by Claude from
the BBShell decompile, replacing the volpgen GLM lane's layouts for PGEND, PGENTABL and SPRPLYR. The lane had PGEND
misaligned by 2 bytes from +0x49 on, SPRPLYR split at the wrong boundaries, and coincidental ASCII bytes decoded as
strings. Its name-pool layout was right and is kept.

Player fields are named by their offset in the in-memory player record, which has the same layout as a PYR record:
`pyr46` = byte +0x46.

| Offset | Meaning |
|---|---|
| +0x1a | u32 birth day number |
| +0x1e, +0x2f | first and last name |
| +0x41 | bats (1 L, 2 R, 3 S) |
| +0x42 | throws (1 L, 2 R) |
| +0x44 | position, 1..9 = P C 1B 2B 3B SS LF CF RF |
| +0x46..+0x5c | 23 peak ratings. The current rating sits 0x17 bytes later (+0x5d..+0x73). Pitch slots are +0x4d..+0x53; fielding at P..RF is +0x54..+0x5c. |
| +0x74..+0x8c | single attributes |

Dice:
- PGEND and AGEPLYR store dice as (base, count, sides): base plus `count` rolls of 1..`sides` (FUN_6805c490).
- PGENTABL stores the same thing as (count, sides, base) (FUN_6806a850).

Chance (num, den) is true with probability num/den (FUN_6805c470). Percent rolls are 1..100 (FUN_6805c450).

## PGENFRST.DAT / PGENLAST.DAT: name pools (FUN_6806ac30)

The file is a u32 magic 0x12345678, then u32 dataSize = count*recordSize, u32 count and u32 recordSize. Then come
`count` NUL-padded records and 1 unread byte. The generator draws a record uniformly, so duplicate names act as weights.
On encode the record size grows to fit the longest name.

## PGEND.DAT: generator 1 (FUN_68068370, loader FUN_68068680)

The file is "PGD:", then u32 0x3aa, then a 0x3aa-byte record, then 1 unread byte. Offsets below are relative to the
record, which starts at file+8.

| Rec off | Field | Code |
|---|---|---|
| 0x000 | 9 u32 per-position draw counts + u32 total (runtime, zero in the file) | FUN_68068760 |
| 0x028 | talent dice for pools 0, 2, 1 | FUN_68068960 |
| 0x031 | talent floor; below it, reroll with the dice at 0x032 | FUN_68068960 |
| 0x035 | 9 position weights (sum 200, roll 1..200) | FUN_68068760 |
| 0x03e | pitcher: secondary chance, ratio, else-dice | FUN_680689d0 |
| 0x045 | fielder: secondary chance, ratio | FUN_680689d0 |
| 0x049 | per position, 5 s16 tier weights over pyr46, pyr47, pyr48, own-position fielding, pyr49 | FUN_68068aa0 / FUN_68069920 |
| 0x0a3 / 0x0ad | pitcher / fielder: 5 s16 weights over pyr4b, pyr4c, pyr4a, pyr77, pitcher pyr49 | FUN_68068aa0 |
| 0x0b7 | per position, 6 × (bats, throws, weight); weights sum to 100 | FUN_680687b0 |
| 0x159 | 2 × (value, weight) giving pyr45 | FUN_68068800 |
| 0x15d | 3 × (value, weight) giving pyr43 | FUN_68068850 |
| 0x163 | birth years-back dice for pools 0, 2, 1 | FUN_680688a0 |
| 0x16c | lefty shift: if throws L, pyr77 < a and pyr4c > b, then move `shift` from pyr4c to pyr77 | FUN_68068c70 |
| 0x16f | pitch count = points / pointsPerPitch, clamped to min..max | FUN_68068d80 |
| 0x172 | pitcher secondary bonus | FUN_680689d0 |
| 0x173 | pyr4b nudge: down range, up range, chance, dice | FUN_68068cc0 |
| 0x17c | 4 rows (row index = throws*2 + pyr45 - 2) × 7 s16 pitch weights | FUN_68068d80 |
| 0x1b4 | 6 dice for current-from-peak: pct A/B/C, minus A/B/C | FUN_68068f00 |
| 0x1c6 | attribute dice (pyr74..pyr8c) | FUN_68069140 |
| 0x1d8 | pyr79 by bats: L (dice, redo dice, redo if below), R (dice, redo dice, redo if above), S (dice) | FUN_68069140 |
| 0x1e9 | pyr83 by throws: L, R | FUN_68069140 |
| 0x1f7 | aging dice | FUN_68069550 |
| 0x1fa | aging curve, 32 × 8 (row i = age 18+i), the same as AGEPLYR | FUN_68069550 |
| 0x2fa | develop blend pct | FUN_680697b0 |
| 0x2fb | develop draws | FUN_680697b0 |
| 0x2fc | 9 × 9 u8 other-position fielding % of own (0 = leave) | FUN_68068b30 |
| 0x34d | 9 × (chance %, 9 u8 weights): position reroll | FUN_68068b90 |
| 0x3a7 | position reroll dice | FUN_68068b90 |

## PGENTABL.DAT: generator 2 (FUN_68069b00)

The loader at 0x6806a330 reads 0x6d2 bytes raw into DAT_6808caa0. One unread byte follows. Every `d1 07` u16 tag
separates sections and is never read.

| Off | Field | Code |
|---|---|---|
| 0x002 | 100 ages; a random slot sets the birth date (generator mode != 2) | FUN_6806ad00 |
| 0x068 | 100 ages (mode 2) | FUN_6806ad00 |
| 0x0ce | 12 month lengths (not read by the generator) | |
| 0x0dc | per position, 6 cumulative thresholds for bats/throws R/R, L/L, L/R, S/R, R/L, S/L | FUN_6806a540 |
| 0x114 | pyr45 = (roll > value) | FUN_68069b00 |
| 0x115 | pyr43 = 0xff if roll <= value | FUN_68069b00 |
| 0x118 | position roll max | FUN_6806a3e0 |
| 0x119 | 9 position weights | FUN_6806a3e0 |
| 0x122 | runtime: u32 total, 9 u32 per-position counts, u16 round-robin index | FUN_6806a3e0 |
| 0x14e..0x3d3 | 46 rating specs of 14 bytes (two groups split by a tag) | FUN_6806a5f0 |
| 0x3d6 | 9 pyr48 specs, one per position (this + pos*14 + 0x3c8) | FUN_6806a5f0 |
| 0x456 | 9 × 9 other-position fielding % (movsx: bytes > 127 count as negative) | FUN_68069b00 |
| 0x4a7 | other-position current % range | FUN_68069b00 |
| 0x4ac | min/max age for the next table | FUN_6806a5f0 mode 1 |
| 0x4ae | 12 (min, max) current-% ranges, entry i = age min+i | FUN_6806a5f0 mode 1 |
| 0x4c8 | 5 pitch brackets: u16 pointsFrom (unread), s16 pointsUpTo, then 100 pitch masks indexed by roll 1..100 | FUN_6806a880 |

Pitchers, FUN_6806a880:
- points = pyr4c + pyr77 + pyr76. The first bracket whose upper bound ≥ points is used.
- In the mask, bit i (0..6) grants pitch slot i, starting at 30 current / 40 peak.

The 14-byte rating spec:

| Byte | Meaning |
|---|---|
| +0 | tag 0x69 (unread) |
| +1 | rollPeak: 1 = peak starts at the base dice |
| +2 | base dice (count, sides, base) |
| +5 | adjustWhen: 0 never, 1 always, 2 if peak < limit, 3 if peak > limit |
| +6 | limit |
| +7 | adjustMode: 1 = reroll the dice in +8..+10; 2 = abs; 3 = abs + adj[0]; 4 = add adj[bats-1] |
| +8 | adj[3] |
| +11 | currentMode: 0 = current is peak; 1 = peak × age-table %; 2 = peak × roll(+12..+13)%; 3 = peak × (+13·age + +12)% |
| +12 | 2 current params |

Peak is clamped to [floor, 99]. Current is ≤ peak.

## AGEPLYR.DAT: in-season aging (FUN_68054990 reads 0x103, FUN_68056210)

- 32 × 8 s8 curve, row i = age 18+i.
- Aging dice at 0x100, added to each delta.
- 1 unread byte.

## SPRPLYR.DAT: spring training (FUN_68054a70 reads 0x6b, FUN_68056320)

- 23 row selectors, one per rating index.
- 4 rows × 21 s8, indexed by value // 5. Row 3 scales (peak - current); the other rows scale peak.
- 1 unread byte.
