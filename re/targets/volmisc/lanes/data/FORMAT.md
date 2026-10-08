# SHELL.VOL DAT entry formats (FPS Baseball Pro '98)

Evidence: hexdump inspection of the three DAT entries plus the BBShell decompile
(`/mnt/nvme/bbpro98/index/BBShell/_all.c`). The shell reads these files with the
same "vfile" walker, `FUN_68063450` (line 83022): records are found by tag, each
record prefixed by a 4-byte tag and a payload length. `s_weather_dat_6808c970`
(WEATHER.DAT loader `FUN_68064da0`, line 84581) confirms per-city indexed
records; `FUN_68064f60` reads climate bytes as monthly means (`(bVar1 + 8) % 0xc
+ 0x30 + param_1` — a 12-entry monthly table at record offset 0x30).

All multi-byte integers are little-endian. All three codecs live in `voldat.py`
(Python 3 stdlib only, runs alone in a bwrap jail).

## MENU.DAT — shell menu definitions (29,176 bytes)

```
'IDX:' 4-byte magic
'x'    filler byte (part of the signature C-string, see below)
00 00  pad to 8
u32    menu count (29)
u32 xN menu data offsets; each points 8 PAST its 'MUB:' record head
```

- The first 8 bytes print as the C-string `IDX:x` (NUL at byte 5); the u32
  count and offset table follow. Offsets are absolute file offsets of
  `head + 8` where head = `MUB:` + u32 size.
- Evidence: `IDX:x\0\0\0` then `1d 00 00 00` (29) then `88 00 00 00` (136 =
  first offset); byte 136 = `4d 55 42 3a` = `MUB:`.

Each menu record:

```
'MUB:'  + u32 size | data (size bytes):
  u16 bytes_per_row   = 8
  u16 columns         = 41 (0x29)
  u16 row_height      = 624
  u16 border_style    = 4 or 6
  u16 has_help_u16    = 0
  u16 lead_marker     = 1
  u16 title_width     = 50 (0x32)
  u16 title_flag      = 0
  u16 title_cols      = 8
  C-string title      = 'Main' (all 29 menus)
  items, until the record ends:
    u16 lead           0 = command, 1 = submenu/other, 2 = separator
    FORM A (8 bytes)   lead + 3 u16 words + caption
    FORM B (10 bytes)  lead + 4 u16 words + caption
    caption C-string, may embed \x01 + accelerator text (e.g. 'Ctrl+W')
```

Form choice is structural: the 8-byte form's caption starts 8 bytes after the
lead. A 10-byte record can never pass the 8-byte test because its 4th word's
high byte is always 0x00/0xff (all flag values are < 256 or 0xffff) — never a
printable caption start. The word meanings differ per lead (lead 0: kind /
item id / flags [+ ref]; lead 1: way / kind / id / flags or id / flags / ref),
so the codec stores them positionally as `target_kind` / `target_id` /
`target_flags` / `target_ref`; that keeps the field names stable under edits.

JSON: `_file_type` (derived), `signature` = `IDX:x` (on-disk content), one
`menus[]` entry per record with `header` (the 9 u16 fields), `title`, and
`items[]`. `_file_padding` holds the byte after the last record (1 byte).

## WEATHER.DAT — per-city climate table (4,783 bytes)

A record stream (107 records, no global header):

```
record-header C-string, e.g. 'WeC:*':
  'WeC:'/'WeR:'/'WeW:' tag + ONE character whose code is the payload size
  NUL + 2 pad bytes            (the 5-char header + NUL + 2 pad = 8 bytes)
payload (size bytes)
```

- WeC 42 bytes = city name in a fixed 22-byte NUL-padded field + 20 climate
  bytes: mean temp Apr..Oct x7 (F), rain chance x7 (%, multiples of 5), 4 aux
  values (wind/cloud?), elevation u16 (ft, e.g. Albany 20? actually 20).
- WeR 14 bytes = 6 pair-bounds + lead 1 (Jan) + tail 100: a season range table.
- WeW 26 bytes = 12 pair-bounds + lead 1 + tail 100: an expanded range table.
- One stray `0x64` after the last record (kept in `_tail_padding`).

85 WeC + 18 WeR + 4 WeW records. Evidence: `WeC:*` headers (0x2a = 42), the
first payload `Albany, NY\0…` + `2f 3a 43 47 45 3d 33 2d 32 32 2d …` where
byte 50 (`14 00`) = elevation 20 as u16 at climate offset 18; `FUN_68064f60`
in the decompile indexes climate bytes by `(month + 8) % 12`, a 12-entry
monthly table.

Notes on the 5th character: 42/14/26 are all < 256, so the size fits in one
char. The header is exposed as editable content (`record_header`); the encoder
validates that it starts with the right tag and keeps the size char at index 4
(edits append after it, which grows the head by the edit length — the decoder
takes the payload start from the header's NUL, so it follows).

## ASNEW.DAT — new-association defaults (1,438 bytes)

```
A: 21 x 20-byte records, id u16 = 1234 (0x04d2)  — league layouts
B:  5 x 20-byte records, id u16 = 5678 (0x162e)  — size variants
   + 1 terminator record
C:  6 x 52-byte records, id u16 = 3456 (0x0d80)  — schedule layouts
u16 name-pool byte count (582)
NUL-terminated layout names (31: 'Not Available', '1 8-team league', …)
2 trailing NULs
```

20-byte record: `id u16, n u8, leagues u8, team counts x3, strength u8,
strength_flag u8, strength_alt u8, spare u8, division_count u8 + division
sizes x3, value u8 + 3 spare`. 52-byte record: `id u16, team_count u8, flag
u8, three 16-byte order lists`.

Evidence: `0x04d2` at 0/20/40/… (21 records), `0x162e` at 420…500, `0x0d80`
at 540/592/… (6 records), then `46 02 00` (582) at 852 and the name pool from
855.

## Verification

`python3 voldat.py {decode,encode}` round trips all three files byte for byte;
800 random edit seeds (strings +Qz, ints +1) re-decode to the edited JSON and
re-encode stably; the referee suite passes (normal + holdout emulation with
bwrap). Zero generic keys; opaque bytes 378/1195 (WEATHER), 288/359 (ASNEW),
0/7294 (MENU) — all under the 25% cap.

## Superseded (Claude, 2026-10-07)

Superseded by work/volmisc.py and work/spec/VOLMISC_FORMAT.md. This lane's menu item parse was heuristic (the real
grammar is bar head, popup class, popup head + title, typed entries 0 command / 1 separator / 2 text slot), the tail
of the weather city record was misnamed (it is rain table id, wind dice, wind offset, calm-wind table id, u16
elevation in feet), and the coverage strings (IDX:x, WeC:*) are no longer needed: the referee exempts chunk tags.
