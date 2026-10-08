# Small data files: bb.cfg, HHA.DAT, *.STS, *.apc, *.pyc / *.pyf

Codec: `work/misc8.py` (decode/encode JSON, picks the layout by file name, rebuilds every byte from the JSON). It
round-trips all 14 sample files (11 visible, 3 holdout) byte for byte and passes `re/targets/voldatref.py` visible and
`--holdout`. Coverage is on for bb.cfg, HHA.DAT and the player lists; off for .apc and .STS, whose leftover printable
runs are the `PC0:` tag plus the low length byte, and stale name padding (kept byte-exact as `_` data).

The misc8 data lane (`re/targets/misc8/lanes/data`) won round 1. Its .STS, .apc and player-list containers were right;
its bb.cfg names were invented and its encoder copied bytes from in.bin. Claude remapped bb.cfg from BBShell, the HHA
cell from BBSIM, and the .STS id blocks from StatsGrid_InitHeaders.

Fixed strings keep the bytes an older, longer value left after the NUL as `_stale` / `_name_tail`
(`[offset, text]`). Encode writes the new string and puts back the stale bytes that lie past its NUL, as an in-place
copy in the game would.

## bb.cfg (0x7c bytes)

BBShell holds it in DAT_68091610 (load/save FUN_68062620; LineUp and Upstats read it too). EZShell writes its own
default copy (DAT_6a038220, FUN_6a0054f0) and seeks to 0x6f for the music byte.

| Off | Type | Key | Evidence |
|---|---|---|---|
| 0x00 | u16 | version (0x03eb) | never read by name |
| 0x02 | char[14] | association (.asn stem) | FUN_68046580; FUN_68062790 / FUN_68062800 fall back to the first .asn |
| 0x10 | u16 | favorite_team | options dialog FUN_680228a0, FUN_6803ced0; FUN_680467e0 -> DAT_6808e134 |
| 0x12 + 0x10k | u16 | exhibition_sides[k].team | FUN_680158b0; the fallback sets 0x10 = 1, 0x12 = 1, 0x22 = 2 |
| 0x14 + 0x10k | char[14] | exhibition_sides[k].association | same |
| 0x32 | u16 | exhibition_selector | exhibition screen FUN_68019f20 / FUN_68065180, set from a list selector |
| 0x34 | u8 | use_custom_stadium | game start FUN_68016ce0: 1 = use 0x35 / 0x43, else the home team's park |
| 0x35 | char[14] | custom_stadium_file | loaded by FUN_68053930, cleared when missing; passed to FUN_68061c10 |
| 0x43 | u8 | custom_stadium_type | set from FUN_6801b1b0(name); passed to FUN_68061c40 |
| 0x44 + 0x10k | 16 | side_controls[k] | below |
| 0x64 | u8 | option_0x64 | gadget 0x25 + value |
| 0x65 | u8 | option_0x65 | controls 0x69..0x6f set 4..10 |
| 0x66 | u8 | option_0x66 | control 0x4c cycles 0..4, skipping 4 |
| 0x67 | u8 | option_0x67 | control 0x4e cycles 0..7 |
| 0x68 | u8 | option_0x68 | controls 0x4f/0x50/0x53, selector + 0x23 (0x23..0x69; 0x48 in the sample) |
| 0x69 | u8 | option_0x69 | controls 0x51/0x52/0x54, < 0x29 |
| 0x6a | u8 | game_option_3e9 | control 0x47 toggles; game start copies it to GDI 0x3e9 (FUN_68061b50) |
| 0x6b, 0x6c | u8 | at_0x6b, at_0x6c | no reader found yet |
| 0x6d | u8 | game_option_3ea | control 0x4a toggles; GDI 0x3ea (FUN_68061b60) |
| 0x6e | u8 | at_0x6e | no reader found yet (1 in the sample) |
| 0x6f | u8 | shell_music | DAT_6809167f; FUN_6804c570 plays, FUN_6804be20 stops, FUN_6804ca90 toggles |
| 0x70 | u32 | start_screen | index into PREFSCRN.DAT's 0x2b screens (options dialog this+0x74; FUN_6801fe40) |
| 0x74 | u32 | at_0x74 | no reader found yet |
| 0x78 | u32 | print_to_file | options control 0x3f -> DAT_680905e8 ("print out") |

Side control record (16 bytes; side 0 at 0x44, side 1 at 0x54). The setup dialog handles each byte with a pair of
controls (c for side 0, c + 1 for side 1, both addressing `cfg + c * 0x10 - k`); the game start reader
FUN_68017000(side) copies the record into the side's setup:

| Off | Key | Values | Game use |
|---|---|---|---|
| +0 | controller | low nibble type, next nibble index, 0xffff none; type 2 checked by FUN_68064a30 (joystick) | FUN_68061a50 |
| +2 | mode_0x2 | 0..2 (controls 0x2d/0x2e) | setup +0x39 |
| +3 | toggle_0x3 | 0/1 (0x37/0x38) | setup +0x31 |
| +4..+7 | level_0x4..level_0x7 | 0..3 each (0x2f..0x36) | setup +0x3a..+0x3d |
| +8..+0xe | toggles_0x8 (7 bytes) | 0/1 each (0x39..0x46) | FUN_68061a80 gets a pointer to +8; +0xa is also the FUN_6804b470 argument |
| +0xf | at_0xf | 0 | none found |

The four 0..3 levels and the toggles are the per-side gameplay settings of the exhibition setup screen; naming each
one needs its gadget caption (ROADMAP #10).

## HHA.DAT (home-run animations)

BBSIM FUN_68035f31 (Hranim.cpp): u16 magic 0x6969 (else "HHA.DAT file needs to be converted"), a 0x200-byte table of
64 entries `{u16 frames, u16 variants, u32 record pointer}`, then each animation's cells. The u32 is a heap pointer
the loader overwrites (FUN_6803634f); the file holds stale values, kept as `_record_ptr`.

Cell (22 bytes) for (frame f, variant v) is at `record + (frames * v + f) * 22` (FUN_680361ba). FUN_68036985 copies it
to the sprite at +0x16 and adds the sprite position to x, y; FUN_68036531 starts animation id (0..63) on a variant, and
FUN_68036737 steps the frame forward or back.

| Off | Key | Notes |
|---|---|---|
| 0 | shape | sprite sheet / sequence id (< 0x48 triggers the clip refresh) |
| 2 | frame | frame within the sheet |
| 4 | x | s16 offset from the sprite position |
| 6 | y | s16 |
| 8 | width | |
| 10 | height | |
| 12 | `_rect` | 4 x s16 the game fills at runtime (x, y, x + w - 1, y + h - 1); zero in the file, so JSON omits it |
| 20 | flag_0x14 | 0 or 1 (sprite +0x2a) |

JSON: `{"animations": [{"variants": [[cell, ...frames], ...], "_record_ptr"}] x 64}`. Frames and variants come from the
grid shape.

## .STS (statistics screen set, 0x75 bytes)

BBShell 0x6805d7d0 checks the size is 0x75 and the u32 version is 1, reads the name (33 bytes) and the 0x50-byte id
block; StatSet_SaveFile writes it. StatsGrid_InitHeaders copies `ids + view * 10` (view 0 batting, 1 pitching) into the
grid's 10 columns and labels each from the stat-name table DAT_680906e8 (built at runtime). A grid with the flag at
+0xf4 set starts at column 2.

| Off | Key |
|---|---|
| 0x00 | u32 version 1 (fixed) |
| 0x04 | name, char[33] (`_name_tail` = stale padding) |
| 0x25 | batting_columns, 10 x u32 stat id (the samples start 3, 0) |
| 0x4d | pitching_columns, 10 x u32 |

## .apc (champions history)

BBShell reader FUN_6804d7a0, writer FUN_6804d960 ("%d games ahead" and series lines). A run of chunks:
`"PC0:" u32 payload length, u16 year, s16 line count, line count NUL-terminated strings`. JSON
`{"seasons": [{"year", "lines"}]}`; lengths are rebuilt.

## .pyc / .pyf (player id lists)

BBShell FUN_6805be80 opens the file without truncating it (`_open(.., 0x8102)`), FUN_6805bf50 rewrites the 10-byte
header in place, FUN_6805bfa0 appends one id (length += 2, count += 1), and FUN_68053b70 loads the ids, keeping
99 < id < the association's limit. Layout: `"PPD:" u32 length (2 + 2 * count), s16 count, count u16 ids`. The bytes
past the list are an older, longer list the game ignores: `stale_player_ids` (editable, stored as is; an odd last
byte goes to `_stale_last_byte`).
