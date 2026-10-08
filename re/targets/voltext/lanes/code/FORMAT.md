# SHELL.VOL string-table DATs — layout (all nine names share one format)

> **Superseded 2026-10-07 by work/spec/STRTABLE_FORMAT.md + work/strtable.py.** The header is a two-level index (W[s] = word index of section s; W[0] doubles as the count), labels[0] is string 0 of section 0, the "AJA" fold is a coverage-check workaround, and each section ends with an empty end-marker string. Kept as the lane record.

FPS Baseball Pro '98 shell string tables, extracted from SHELL.VOL
(`work/volcodec.py`). Session-localized DOS text: each byte is an 8-bit
char, NUL terminates a string. Multi-line texts (ASSERTXT, print
reports) use `\n` (0x0A); report headers carry a literal trailing `\`
character; box-score/news row templates use printf codes.

## Header

```
offset 0: u16 total        file length - 3
offset 2: u16 sectionCount number of section pointers (1..8)
offset 4: u16 sectionPointers[sectionCount]
                           byte offsets relative to file byte 2; the LAST one
                           points at the label pool (value = poolPos - 2); the
                           earlier ones mark where each print report's block
                           starts inside the string-offset table
```

Then `sectionCount`-1 u16 "section-pointer" values that repeat
`sectionPointers[1..]` (a quirk of the original writer: ASNEWS byte 8 =
0x0267 = second pointer again), then the string-offset table:

```
u16 stringOffsets[nOffsets]  pool offsets relative to file byte 2; entry
                             entryValue points at label entryValue + 2
```

`nOffsets = (lastPointer+2 - 6) / 2` (single-section files), or
`(lastPointer+2 - 4 - 2*sectionCount) / 2` (multi-section files, the
offset table starts after the section-pointer block).

Verified: for every entry `entryValue + 2` is a label start and the
previous labeled string's NUL + 1 == next label start (the tables are
one contiguous consecutive run pointing at the pool).

## Label pool

NUL-terminated strings starting at `lastPointer + 2`:

- `labels[0]` — the pool's first string, never referenced by the offset
  table (empty in ASNEWS..PREFSCRN; 'Historical data' in ROSTEXT).
- `labels[1..nOffsets]` — pointed at by entries `0..nOffsets-1`.
- Two trailing blank labels on most files; every file ends with 3 NUL
  bytes (`len == total + 3`), ASSERTXT with 2 (the pool there ends
  with the last real string's NUL, one blank, one filler NUL).
- ROSTEXT boundary quirk: the pool offsets are around 0x4100-0x4200, so
  the last entries' big-endian-displayed high bytes are printable
  ASCII — the three bytes before the pool read `'AJA'` and merge with
  `labels[0]` into one printable run across the offset-table/pool
  boundary. The decoder folds those bytes into `labels[0]`
  (`_boundaryPrefixLen` = merged prefix length, recomputed at encode);
  the encoder rebuilds labels in pool order when the merged view
  reproduces, otherwise it pins the last two entry-referenced labels to
  their original byte positions (keeping the boundary bytes identical)
  and moves remaining labels into NUL gaps after the tail.

## Per-name content

- **ASNEW/ASNEWS** (association news): month abbreviations/names,
  roster level names (active roster, AAA, DL, Low Minors), 24
  transaction templates (`~4%s ~5%s~6 sent to AAA.`), trade lines,
  ~45 free-agent/draft/release templates, 6 injury summary lines
  (`went on the DL ~4%s %d~6 ...`), ~205 injury descriptions.
- **TMNEWS** (team news): the ASNEWS tables plus 4 trade/free-agent
  dialog prompts, 2 date prefixes.
- **PONEWS** (playoff news): 9 templates — League/World championship,
  `Best of %d - %s (%d) vs. %s (%d)`, `Game #%d: %s (%d) at %s (%d)`,
  Round One/Two, standings header.
- **ASSERTXT** (startup/error text): 9 multi-line messages (startup
  error chain, c-tree(TM) notice, copy-protection error, disk space…).
- **BOXTEXT** (box score): title, day-of-week names, month names, 's'
  plural, ordinal suffixes 1st-30th (`21th` etc. as stored), position
  abbreviations (P C 1B 2B 3B SS LF CF RF DH PH PR), TOTALS:, 25
  batting/fielding/pitching stat labels, 12 row templates with `|1..|9`
  column markers and `~5`/`~4`/`~6` colour codes, 8 game-data lines
  (time/temp/wind, rain delay), 8 wind-direction labels.
- **PREFSCRN** (menu captions): 20 screen names (Exhibition Play,
  Association Data, Team Roster/..., Association News, ...).
- **PRINTTBL** (print column formats): printf width/precision specs
  per printed report (`%-16.16s`, `%3.3s`, `%5.5s`, ...), section
  header rows (`Team Statistics: %s\n`), 7 section pointers.
- **PRINTTXT** (print report text): 40+ report templates —
  association/team data pages, ground rules, standings, schedules,
  rosters, leaderboard headings, uniform-color lines, 8 section
  pointers.
- **ROSTEXT** (roster screen): 985 labels — 'Historical data' +
  data-view names, handedness letters, roster status (OK P CEI Act AAA
  DL Low), 60+ stat abbreviations (AB R H 1B 2B 3B HR RBI SH SF HBP BB
  IBB SO SB CS GDP Avg OBP SLG PA Iso K/BB RC TB SA Pro TA Inn PO A E
  DP PB Pct. Rng), per-split abbreviations (Sc: Hm: Rd: CL: Ap: My:
  Jn: Jl: Au: SO: + 12 more months), 120+ full descriptions for the
  same stats, wind/hold/enter endurance pitch ratings, and `Xx:STAT`
  column heading pairs for each roster split.

## Substitution codes (named)

- `%s %d %2d %02d %-4s %-41s ...` — printf conversions; count and
  order per template from the template text.
- `~N` colour codes in ASNEWS/TMNEWS/BOXTEXT news lines: `~4` field
  name, `~5` team name, `~6` plain text.
- `|N` column markers in BOXTEXT/PRINTTXT rows: `|1` visiting team
  name, `|2` at-bats, `|3` runs, `|4` hits, `|5` RBI, `|6` walks, `|7`
  strikeouts, `|8` mid-sentence insertion (innings/notes), `|9` innings
  pitched (pitching rows).

Evidence: the string tables are consumed by text-window and print
routines in BBShell; the row/wind/en|dec decompile at
`/mnt/nvme/bbpro98/index/BBShell/_all.c` (FUN_68009a60 wraps |N/colour
run splitting, FUN_680510c0 + FUN_68063ec0/FUN_68063a80 read the
named DATs with 0x94/0x28-byte records).
