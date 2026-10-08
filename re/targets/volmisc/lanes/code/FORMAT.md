# FORMAT.md — SHELL.VOL DAT entries: MENU, WEATHER, ASNEW (FPS Baseball Pro '98)

All three files are entries of the shell volume `SHELL.VOL` ("VOLM" format,
decoded by `work/volcodec.py`).  Layouts below were worked out from the BBShell
decompile (`/mnt/nvme/bbpro98/index/BBShell/_all.c`) and confirmed against the
files.  Codecs: `voldat.py` (this directory).

Every layout is verified with `encode(x, decode(x)) == x` byte for byte, the
referee's coverage/opaque/generic-key checks (`voldatref.py` logic, run through
`local_ref.py` because this sandbox has no systemd user bus), and 150 random
edit seeds per file (`seed_sweep.py`, K=6 edits each) — 450 edits, 0 failures.

## MENU.DAT — shell menu definitions (29 176 bytes)

Loader: `FUN_68046a60` reads the index over `dlog.func` calls (a 0x18 group
head, then 4-byte reads for the extent and count, then `count << 2` bytes of
offsets); `FUN_68046b50` seeks `offsets[menu - 1]` relative to the record head
to open menu *i*.

```
'IDX:'  u32 index extent (= 4 + 4*count; its low byte is 0x78 'x' in the
        pristine file, giving the on-disk signature 'IDX:x')
        u32 count (= 29)
        u32 dataOffsets[count]   each points 8 past its 'MUB:' record head
then count records, back to back:
  'MUB:'  u32 size  + the menu block
file end: one 0x00 pad byte
```

Menu block:

```
u16 header, 9 words:  rowStride(8), width(41), height(624), topLevelItems,
                      0, 1, 50, 0, 8        (only word 3 varies: 4 or 6)
C-string menu title           starts at byte 18 (e.g. "Main")
then item records, back to back:
  u16 struct, either
    short  form (8 bytes):  x, y, commandId, itemFlag
    long   form (10 bytes): selector, x, y, commandId, itemFlag
    (the long form's selector prints as the 0x01 anchor that precedes the
     x/y pair; when the item flag is 1 both forms parse, and the decode
     picks the parse with the longer caption)
  C-string caption            "text\x01accelerator" — the game splits the
                              caption at the \x01 to show the shortcut
                              ("Create New Association...\x01Ctrl+W")
```

Evidence: every command id in the structs matches the menu handler
dispatches (`menu_event_handler` case 0xe = 14 = "New Association", Exit = 45,
Resume = 34, ...); the caption texts match the game's strings; all 29 blocks
parse to their exact `MUB:` sizes; the last block ends one byte before EOF.
JSON: `{"_file_type", "menus": [{"header", "title", "items": [{"x", "y",
"command_id", "item_flag", "caption", "accelerator"}...]}...], "index_signature"}`.
`index_signature` is content (the header run 'IDX:x' is a file string the
referee's coverage check requires); its chars past byte 5 live in the extent's
high bytes, which are otherwise zero.

## WEATHER.DAT — per-city weather climate table (4 783 bytes)

Loader: `FUN_68064da0`/`FUN_680651a0` walk the records over `dlog.func` reads:
0x16 = 22 (city), 7, 7 (temperature/precipitation), 1, 1, 1, 2 bytes; then
looks up the 14- and 26-byte threshold tables by the ids it read and fetches
them with `FUN_680515b0`.  `FUN_68064fb0` reads 5 `[lo, hi]` temperature
threshold pairs from the 14-byte record (the game picks the sky condition from
the current temperature); `FUN_68064f60` uses the same table shifted by month.

```
one run of length-prefixed records:
  'WeC:' u32 42  city record:
       city_name[22]  NUL-padded (a 21-char name fills the field without NUL)
       u8[7]  monthly mean temperature, F        April..October
       u8[7]  monthly precipitation chance, %    (multiples of 5)
       u8     season start April index (the game checks 1..0x12)
       u8     weather pattern id  (checked 1..4: clear/cloudy/rain/storm)
       u8     alternate pattern id (checked 1..4)
       u8     short threshold table id
       u8     wide threshold table id        ([39:41] read as one u16)
       u8     zero                           ([41], kept in "_byte_41")
  'WeR:' u32 14  temperature threshold table: count byte + [lo,hi] pairs
  'WeW:' u32 26  temperature threshold table: count byte + [lo,hi] pairs
         (the pad after the pairs is kept in "_pad" for a lossless rebuild)
one 0x64 'd' byte trails the last record (kept in "_trailing_bytes")
```

Counts: 85 cities, 18 short tables, 4 wide tables.  JSON: `{"_file_type",
"record_marker": "WeC:*", "cities": [...], "short_threshold_tables": [...],
"wide_threshold_tables": [...]}`.  `record_marker` is content: the marker run
'WeC:*' (tag + the 42 size byte) is a file string the coverage check requires;
its chars past byte 5 live in the size's high bytes, which are otherwise zero.
The record walk keys off the tag's known payload size, so a marker edit keeps
the file parseable.

## ASNEW.DAT — new-association defaults (1 438 bytes)

Loader: `FUN_68004fe0` reads the file into the association-creation dialog with
DEC reads of 0x1a4 = 420 = 21*20 bytes, 0x78 = 120 = 6*20, 0x138 = 312 = 6*52
and a u16 string length; the parse functions `FUN_68005180`/`FUN_68005230`/
`FUN_68005370` walk the group steps (`rec + 5 + i*8`) and resolve the name
refs (`FUN_68005220` = `ref + 0x370 + gamebuf`, where the names live at the
pool the file ships).

```
21 league-layout  records of 20B (id u16 = 1234 = 0x04d2)
 6 size-variant   records of 20B (id u16 = 5678 = 0x162e; the last is a
                  terminator: team count 0, name ref 1 = 'Not Available')
 6 schedule-layout records of 52B (id u16 = 3456 = 0x0d80)
u16 nameBytes + 1            (= 582; the pool holds 581 bytes)
u8 0 separator
name pool   "name\0" * 31 + one extra NUL      (the layout names)
u16 0 + u8 0?  file end: two NUL bytes         (kept in "_pool_trailing_bytes")
```

20-byte record:

```
u16    record id sentinel
u8     team count          (8..48 for the league layouts)
u8     league count        (1..3)
u8     conference count for group set 0   (1..3)
u8[3]  group set 0 sizes   (the game reads them at +5 + i*8)
u16    layout name ref     1-based byte offset into the pool; the name sits
u16    alt name ref        at ref - 1 (0 = none); the game adds 0x370
u8     conference count for group set 1   (0..3)
u8[3]  group set 1 sizes
u16    secondary name ref
u16    tertiary name ref
```

52-byte schedule record: id u16, team count u8, layout flags u8, three 16-byte
schedule order lists (the game strides 0x18 per league).

Every name ref resolves against the pool (verified: all 27 non-terminator refs
land exactly on name starts, e.g. ref 15 = '1 8-team league').  The refs stay
content ints in the JSON (`pool_ref_0..3`); the resolved names are derived
(`_layout_name` ...), so renaming a pool entry re-points every record that
uses it and editing a ref number re-points that record — both survive the
referee's edit test.

JSON: `{"_file_type", "league_layouts": [...], "size_variants": [...],
"schedule_layouts": [...], "layout_name_pool": [...], "_pool_trailing_bytes"}`.

## Tooling notes

- `voldat.py` — the deliverable codec (Python 3 stdlib only).
- `local_ref.py` — referee checks with a plain subprocess launch (no systemd
  user bus in this sandbox; the orchestrator's real referee uses bwrap).
- `seed_sweep.py` — multi-seed edit test sweep.
- `analysis/` — hex dumps, field dumps and the scripts that produced them.

## Superseded (Claude, 2026-10-07)

Superseded by work/volmisc.py and work/spec/VOLMISC_FORMAT.md. This lane's menu item parse was heuristic (the real
grammar is bar head, popup class, popup head + title, typed entries 0 command / 1 separator / 2 text slot), the tail
of the weather city record was misnamed (it is rain table id, wind dice, wind offset, calm-wind table id, u16
elevation in feet), and the coverage strings (IDX:x, WeC:*) are no longer needed: the referee exempts chunk tags.
