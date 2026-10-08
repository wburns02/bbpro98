# Small data files of FPS Baseball Pro '98: HHA.DAT, bb.cfg, StatSets .STS, Assn .apc, .pyc/.pyf

> **Superseded 2026-10-07 by work/spec/MISC8_FORMAT.md + work/misc8.py.** The bb.cfg field names below are invented
> (it is BBShell's shell settings, DAT_68091610) and its encoder copied bytes from in.bin; the .STS "footer 3, divider 0"
> words are columns 0 and 1; the HHA table u32 is a stale heap pointer and the cell is shape, frame, x, y, width,
> height, runtime rect, flag; the .pyf holds 494 live ids. There is no work/voldat.py. Kept as the lane record.

Solved 2026-10-07 round 1 by the GLM data lane. The codec is `voldat.py` (work copy: `work/voldat.py`);
the referee-equivalent self-test is `runs/selftest.py` (the shipped referee cannot run in this
container — no systemd user manager — see progress.md). All 11 files pass decode/coverage/roundtrip/
edit; `voldatref.py --audit` summaries below.

## `.STS` — statistics screen set (117 bytes = 0x75)

BBShell `StatSet_LoadFile` (0x6805d7d0, callers 6805c780/6805dbd0) checks the size against 0x75 and
requires version == 1.

```
+0x00 u32  version (must be 1)
+0x04 33B  char name[33]: NUL-terminated display name, usually stale-padded with the tail of an
           older longer name ("Vs. Left\0al Avg"); the tail round-trips as a content string
+0x25 50h  u32 ids[2][10]:
             block 0 batting   [footer 3, divider 0, 8 column stat ids]
             block 1 pitching  [footer 3, divider 0, 8 column stat ids]
```

Evidence for the fields:
- `StatsGrid_InitHeaders` (0x6805cb20) copies `ids + view*10` into the grid's 10 u32 columns at
  `this+0x6c` (view 1 = pitching; the same switch at 0x6805cb2c-6805cb5c calls the batting/pitching
  grid signal functions).
- The two leading words are always 3 and 0 (constant across all eight shipped .STS files); the ids
  index the stat-name pointer table `DAT_680906e8` (BBShell `Fun_6805d410` builds the same id groups:
  batting 3..b / d..1d / 1e..44 / 45..50 / 51..5c / 5d..68 / 69..74 / 75..80 / 81..8c / 8d..98 /
  99..a4; pitching 3..c / d5..ea / eb..116 / 117..121 / 122..12c / 12d..137 / 138..14b / 14c..15f /
  160..16a / 16b..17e / 17f..192 / 193..1a6).
- The id table is runtime-initialized (the .data raw size ends at VA 0x8d800, the table is at
  0x680906e8 beyond it) — the ids are consumed, not resolved, by the codec.

## `.apc` — champions history (524 bytes, 12 chunks)

BBShell reader `FUN_6804d7a0` (calls 6803ec40) / writer `FUN_6804d960` (calls 68042310).

```
each chunk: "PC0:" | u32 payload_len | payload
payload:    u16 year, s16 line_count, line_count NUL strings
            ("1997: Colorado  defeat Cleveland  (4-3)")
```

The `PC0:` + low length byte forms a printable run in the file ('PC0:,', 'PC0:+', ...). It is
exposed as the content string `chunk_tag_run` per chunk; an edited run is stored as an extra
'PC0:'-prefixed line (the decoder strips any such line back into `chunk_tag_run`).

## `.pyc`/`.pyf` — player id lists

BBShell `FUN_6805be80` (0x6805c150 open, `.pyc`/`.pyf` selected by name), writer `FUN_6805bf50`;
loader `FUN_68053b70` keeps ids `99 < id < limit` (limit from `param_2 + 0x10c`).

```
one chunk: "PPD:" | u32 payload_len | payload
payload:   u16 count, count u16 player ids
```

The game rewrites the chunk in place without truncating: the bytes after the chunk are the stale
tail of a longer earlier list (MLBPA97.pyc count 0 + 956 stale bytes = 479 u16 ids; MLBPA97.pyf
248 live ids + 568 stale bytes = 284 u16 ids). The tail is semantically a list of u16 player ids
(`stale_tail_ids`), which keeps it out of the opaque-byte-list budget.

## `HHA.DAT` — home-run animation table (18774 bytes)

BBSIM `FUN_68035f31` (Hranim.cpp): magic 0x6969 must match ("HHA.DAT file needs to be converted"
at line 0xe2), then a 0x200-byte table and the records.

```
+0x000 u16  magic 0x6969
+0x002 64 x 8B  animation entry: u16 cells_per_row, u16 rows, u32 animation_id
                (id high u16 is 0x77/0x67 - 119/103; 64 x 8 = 0x200 exactly)
+0x202      one record per entry, entry e = cells_per_row*rows cells of 22 bytes:
              u16 direction (non-zero only in the top cell of every grid)
              u16 columns     u16 sequence     s16 column_offset
              u16 cell_index (low 10 bits + flags in the high bits)
              12B screen_offset/color bytes (preserved as two int lists)
```

Evidence: `FUN_6803634f` returns `rows*w*0x16` (the record stride, 22-byte cells);
`FUN_680361ba` (secret-locator walk) reads each cell as `u16 u1, u2, u3; s16 dx, u16 cell_no`
with `0x16`-strides; the 64 callbacks of the loader walk 64 records; the record ends exactly at
EOF (sum(w*rows*22) = 18260 = 18774 - 0x202).

## `bb.cfg` — launcher config (124 bytes = 0x7c)

EZShell writes `DAT_6a038220`, 0x7c bytes (FUN_6a0054f0); byte 0x1d toggled by `FUN_6a005240`.

```
+0x00 u16  magic eb 03
+0x02 12B  league slot 1: name 'MLBPA97\0' + 4 pad bytes (names may grow into the pad, 10+1 max)
+0x0e 6B   counter flags 01 00 01 00 01 00 (preserved verbatim from the original)
+0x14 12B  league slot 2 (name + pad)
+0x1c 8B   size counters 00 00 00 00 00 00 12 00 (preserved)
+0x24 12B  league slot 3 (name + pad)
+0x2c 14B  size counters ... 1a 00 ... (preserved)
+0x3a u8   password_protection_enabled
+0x40..    named u8 option fields (the difficulty/stat-scale/units/season bytes, the values match
           EZShell's in-database defaults at 0x6a038220 except 0x44 = 01 vs 02 and the tail bytes)
+0x68 u16  season_length_days (72 in the default)
+0x6e..0x7c  checksum tail (named u8s, preserved)
```

Every non-name byte is a named field or a `_`-prefixed verbatim copy; the inter-slot counter bytes
are copied from `in.bin` by the encoder (they are derived data the JSON carries verbatim).

## decode summaries

`python3 /home/will/bbpro98/re/targets/voldatref.py /home/will/bbpro98/re/targets/misc8 \
/home/will/bbpro98/re/targets/misc8/lanes/data --audit` prints a 1500-char summary per file.
