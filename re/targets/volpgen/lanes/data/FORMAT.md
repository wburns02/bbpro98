# FORMAT — SHELL.VOL player-generator DAT entries (FPS Baseball Pro '98)

> **Superseded 2026-10-07 by work/spec/PGEN_FORMAT.md + work/pgen.py.** The PGEND, PGENTABL and SPRPLYR layouts below
> are wrong (PGEND misaligned from +0x49, coincidental ASCII decoded as strings, SPRPLYR mis-split). Name pools and
> AGEPLYR are right. Kept as the lane record.

All layouts below were mapped by hexdumping the extracted files from
`SHELL.VOL` and cross-checked against the game's BBShell decompile (grep the
file names in the index `_all.c` files to find the loaders). `voldat.py` in
this directory implements `decode`/`encode` for each.

## PGENFRST.DAT / PGENLAST.DAT — player name pools (177,713 / 208,617 bytes)

Loaded by FUN_6806ac30, which opens the file by name, reads the 16-byte
header, picks a record at random and seeks `count*recsize + 0x10`.

```
u32  magic    = 0x12345678
u32  dataSize = count * recordSize        (excludes the 16-byte header)
u32  count    = 14808 (first) / 14900 (last)
u32  recordSize = 12 (first) / 14 (last)
count x recordSize  NUL-padded ASCII name records
1 byte trailing 0x00                    (loader never reads it)
```

The generator draws a record uniformly at random, so **duplicate entries act
as selection weights** (e.g. "Chris" appearing 5 times is drawn 5x as often).
The JSON exposes them as an ordered `names` list; edits may grow or shrink
strings and the encoder picks the smallest record size that fits every name
(`max(len+1)`, floored at the original), then rewrites `dataSize`/`count`.

Verified: `16 + dataSize == 177712` (first) / `208616` (last), file length one
byte larger in both cases.

## PGEND.DAT — player generator database (947 bytes)

Loaded by FUN_68068680 (`("PGD:"`) with a `0x3AA` read handed to
`param_1`, then consumed field-by-field by the FUN_68068760..FUN_680697b0
accessor family (position weights at rec+0x35, per-position 6-entry weighted
pick tables at rec+0xB7 whose weights sum to 100 against a 1..200 roll,
rating-percentage profiles via FUN_68068b30, the aging triple + curve at
rec+0x1F7/0x1FA).

```
4s  magic "PGD:"
u32 recordSize = 0x3AA (938)     -- recomputed on encode when strings grow
--- record (base = file + 8) ---
+0x000 40 bytes runtime counters (always zero in the shipped file; kept as
       derived pad so the encoder rewrites them)
+0x028 3+3+3 signed  overall-range triples (primary/tertiary/secondary)
+0x031 u8            range floor threshold
+0x032 3 bytes       range floor boost
+0x035 9 bytes       position weights (sum 200; rolled against 1..200)
+0x03E 2+2+3 u16/u16/3  draft chance/scale/spread scalars
+0x045 2+3 signed    alt chance pair + alt scale fraction
+0x04A 1 pad
+0x04B 54 u16        rating scalars
+0x081 1 pad
+0x082 9 x 6 x 3     position pick tables: 9 positions, 6 weighted entries of
                     (value u8, low u8, high u8); weights sum to 100
+0x132 4+4 signed    handedness pair tables
+0x13A 2 bytes       hand extra pair
+0x13C 9 signed      hand adjust triples
+0x145 8 signed      age param block
+0x14C NUL-terminated label "12E2d"   (coincidental ASCII, see below)
+0x152 2 bytes       age param tail
+0x154 28 u16        handedness profiles (4 x 7)
+0x170 18 x 3 signed rating range triples / slot weight triples
+0x1C0 30 x 3 signed age scale triples + 1 tail byte
+0x1F7 3 signed      aging roll range (-4, 2, 3) -- identical triple in AGEPLYR
+0x1FA 256 signed    aging curve (32 rows x 8), byte-identical to AGEPLYR body
+0x2FA 2+1           pct scale pair + terminator
+0x2FD 8 profiles    rating percentage profiles: 8 entries, each `leadN`
                     signed rating bytes then a NUL-terminated ASCII tail
                     (lead lengths 5,9,9,9,9,5,4,3)
+0x35A 9 bytes       slot scale header
+0x363 84 x 4        draft slot multipliers
1 byte trailing (loader never reads it)
```

Coincidental ASCII: rating bytes land in 0x20..0x7e and are followed by NUL,
so binary spans show up as printable strings to any scanner
(`Z(Z<`, `dKdE`, `12E2d`, ...). The referee's coverage rule requires every such
span inside a decoded string, so those exact byte runs are decoded as string
fields (`ageLabel`, per-profile `asciiTail`). They name real bytes and stay
one-to-one; growing one shifts later sections, handled by strict sequential
parsing. `recordSize` — like every `_` key — is recomputed by the encoder.

## AGEPLYR.DAT — aging table (260 bytes)

Loaded raw by FUN_68054990 (reads 0x103 bytes). FUN_68056210 indexes
`DAT_6809061c + age*8 - 0x90` — i.e. row `i` is age `18+i`, 8 rating classes.

```
32 x 8 signed bytes    aging curve: per-year rating deltas (growth early,
                       decline late); byte-identical to PGenD rec+0x1FA
+0x100 3 signed        aging roll range (-4, 2, 3): (base, rolls, spread)
1 byte trailing        loader never reads it
```

## SPRPLYR.DAT — spring-training table (108 bytes)

Loaded raw by FUN_68054a70 (reads 0x6B bytes). FUN_68056320 reads
`*(sel)*21 + rating/5 + 0x17`. The file holds constant base groups followed by
four progression lookup ramps, each preceded by a geometric negative head:

```
+0x00 3 bytes       base group 2s
+0x03 4 bytes       pad
+0x07 7 bytes       base group 3s
+0x0E 1 byte        pad
+0x0F 8 bytes       base group 1s
+0x17 2 signed      linear ramp head (-20, -10)
+0x19 1 byte        separator 0
+0x1A 18 x 6        linear +5 ramp to 90
+0x62 2 signed      doubling ramp head (-5, 0)
+0x64 19 x 8        doubling 1,2,4..68 ramp   (ends at 0x6B = spring read span)
1 byte trailing     loader never reads it
+0x6C 4 signed      step-3 ramp head (-80, -40, -20, -10)
+0x70 1 byte        separator
+0x71 16 x 8        linear +3 ramp to 48
+0xF1 2 signed      saturating ramp head (-50, -25)
+0xF3 1 byte        separator
+0xF4 18 x 8        saturating ramp 35,40..90,92..100
```

Each ramp maps a development roll to a rating result; heads are geometric
negative offsets; ramps are linear (+5), doubling, linear (+3) and saturating
at 100. `SPRING_READ = 0x6B`: the loader stops there; the remaining fields sit
beyond it but are decoded so nothing is opaque.

## PGENTABL.DAT — generator tables (1,747 bytes)

Thirteen sections, each opening with the u16 marker `d1 07` (2001):

1. 100 x 5   roll-to-tier curve for ages 17–23
2. 100 x 5   roll-to-tier curve for ages 18–35
3. 12 bytes  calendar month days (31,28,31,30,...)
4. draft rating ladders: NUL-terminated ASCII ladder strings (+1 follow pair
   each), 12 x 6 mid pairs, 18 x 6 peak rows
5. 2 bytes   draft baseline pair
6. 10 bytes + 42 zero bytes: draft slot params
7. 20 + 26 + 9 fixed 14-byte `69 01` records — draft slot profiles
   (kind, slot, u16 ref, 8 signed params) for early/mid/late rounds
8. 74 x 7 + 1 rating product rows and tail, `ratingsLadderTop` string
9. 26 bytes  percentile-to-rating curve
10. five value brackets: each `u16 lo, u16 hi` then a 100-byte tier row
    (shown as 20 rows of 5); bracket keys name their salary ranges
    (120–159, 160–199, 200–209, 210–279, 280+)
11. 1 byte   final marker byte

## Codec contract

- Required commands: `python3 voldat.py decode NAME in.bin out.json` and
  `python3 voldat.py encode NAME in.bin edited.json out.bin`.
- `_`-prefixed keys are DERIVED (counts, sizes, unread trailing bytes,
  coincidental-ASCII note fields); everything else is editable content.
- Strings may grow or shrink; names, the PGenD record, profiles and ladder
  strings all re-flow and every `dataSize`/`recordSize`/length is recomputed.
- `encode(x, decode(x)) == x` byte for byte on all six files; random edits
  (content strings += "Qz", non-zero content ints +1) re-decode to exactly the
  edited JSON on every content leaf and re-encode stably.
- At most a 25% opaque budget is allowed; measured usage: 0% for the two name
  pools, AGEPLYR and SPRPLYR; 2.7% (PGENTABL) and 5.7% (PGEND) for binary
  non-string spans; 0 generic keys anywhere.
