# SHELL.VOL data entries: MENU.DAT, WEATHER.DAT, ASNEW.DAT

Codec: `work/volmisc.py` (decode/encode JSON, picks the layout by entry name, rebuilds every byte from the JSON). It
round-trips the three entries of the pristine SHELL.VOL (e0006 MENU.DAT, e0018 WEATHER.DAT, e0001 ASNEW.DAT) byte for
byte and passes `re/targets/voldatref.py` visible and `--holdout` with full coverage.

The volmisc code lane (`re/targets/volmisc/lanes/code`) won round 2 with the right containers (IDX/MUB, the We*
chunks, the ASNEW record sizes) but parsed menu items by heuristic and misnamed the tail of the weather city record.
Claude re-derived the menu grammar from the BBShell object parsers, the weather fields from the daily weather roll,
and the ASNEW pool refs and team lists from the new-association dialog. The lanes' coverage strings (`IDX:x`, `WeC:*`)
are gone: the referee now exempts chunk tags.

## MENU.DAT (shell menu bars)

BBShell menu bar object DAT_6808db48 (ctor FUN_68046870, vtable 0x680817e0). FUN_68046a60 opens `menu_dat`;
FUN_68046b50(n) seeks IDX offset[n - 1] and calls vtable[0] = 0x68046e30. There are 29 bars, one per shell screen;
all have Main / Association / Team / Help, and bars 2..29 add Action and Show.

```
"IDX:" u32 extent (= 4 + 4 * count), u32 count, u32 offset[count]   offset = the MUB block's data (tag + 8)
count x { "MUB:" u32 size, bar }
one 0x00 byte (unread; "_trailer")
```

Bar (0x68046e30): u16 x, u16 y, u16 width (8, 41, 624 in every bar; the height is computed), u16 popup count, then per
popup u16 class and the popup. Class 0 builds 0x68082020 (FUN_68077050), class 1 builds 0x68081fe0 (FUN_68076d90);
both read the same layout (0x68077190 / 0x68076ed0). Only class 0 occurs.

Popup: s16 hotkey_mods, u16 hotkey_scancode, s16 mnemonic, u16 entry count, NUL-terminated title, then the entries
(0x680777a0): u16 type and

| Type | Class | Data |
|---|---|---|
| 0 | command 0x680821f0 (parse 0x6807d980) | s16 hotkey_mods, u16 hotkey_scancode, s16 mnemonic, NUL-terminated caption |
| 1 | separator 0x68082190 (parse 0x6807d6c0) | none |
| 2 | text slot 0x680821c0 (parse 0x6807d7b0) | as type 0; the caption is blanks the shell fills at runtime (its length is kept at +0x24) |

- hotkey (FUN_68076cb0): the item answers key `hotkey_scancode` (PC set-1 scan code: 0x32 M, 0x11 W, 0x2d X) when bit 0
  of `hotkey_mods` is set and the first modifier is down, or bit 1 and the second. The data uses 1 on popups (Alt+M
  for Main) and 2 on commands whose caption says Ctrl+; 0 = no hotkey.
- mnemonic (FUN_68076cf0): index of the underlined letter in the caption, -1 = none (only the low byte is read).
- caption: text, then optionally `\x01` and the right-aligned shortcut label. JSON splits it into `text` and
  `shortcut`.
- A selected command is identified by its position in the popup (FUN_68077640 walks the list by index): captions,
  hotkeys and mnemonics can change freely; adding, removing or reordering entries changes which command runs.

JSON: `{menus: [{bar_x, bar_y, bar_width, popups: [{popup_class, hotkey_mods, hotkey_scancode, mnemonic,
title: {text, shortcut?}, entries: [{separator: true} | {hotkey_mods, hotkey_scancode, mnemonic,
caption: {text, shortcut?}, text_slot?: true}]}]}], _trailer}`. IDX offsets, sizes and counts are rebuilt.

## WEATHER.DAT (city climates)

BBShell weather object, loaded by FUN_680651a0(city). FUN_68063450(stream, tag, n) seeks the n-th chunk with a tag
(1-based). Chunks are `tag u32 size data`; one 0x64 byte trails the file (unread, `_trailer`).

City, `WeC:` (42 bytes; 85 cities), read field by field:

| Off | Key | Use |
|---|---|---|
| 0 | name, char[22] NUL-padded (at most 21 characters) | city list (FUN_68064da0) |
| 22 | mean_temp_f, 7 x u8, April..October | FUN_68064f60: game temperature = mean + random(0..30) - 15, clamped to 35..105 |
| 29 | precip_pct, 7 x u8, April..October | FUN_68064fb0: a roll at or under it rains, else the sky is one of 0..2 |
| 36 | rain_table, u8 (1..18) | which WeR table; the loader rejects 0 or > 18 |
| 37 | wind_dice, u8 | FUN_68065070: wind = sum of 4 rolls of 1..wind_dice - wind_offset, capped at 40 |
| 38 | wind_offset, u8 | |
| 39 | calm_wind_table, u8 (1..4) | which WeW table; the loader rejects 0 or > 4 |
| 40 | elevation_ft, u16 | weather object +2 (Denver 5280, Albuquerque 4945, coastal cities 5..40) |

The month is rolled 4..10 (FUN_68064f30) and indexed as (month + 8) % 12, so index 0 is April.

Rain table, `WeR:` (14 bytes; 18 tables): 7 [lo, hi] percent bands. On a rain day FUN_68064fb0 rolls a percentage
and finds its band among the first 5: band 0..2 gives sky 3, band 3..4 sky 4.

Calm-wind table, `WeW:` (26 bytes; 4 tables): 13 [lo, hi] percent bands. When the wind roll comes out below zero,
FUN_68065070 rolls a percentage and the wind speed is the index (0..11) of its band.

Weather state the roll fills (object offsets): +0x1a month, +0x1b temperature (0x6a = not rolled yet), +0x1c sky
(6 = not rolled), +0x1d wind speed (0x29 = not rolled), +0x1e wind direction 0..7 (9 = not rolled; FUN_680650f0).

JSON: `{cities: [{name, mean_temp_f, precip_pct, rain_table, wind_dice, wind_offset, calm_wind_table,
elevation_ft}], rain_tables: [[[lo, hi]] x 7], calm_wind_tables: [[[lo, hi]] x 13], _trailer}`. Chunks are written
cities first, then rain, then calm-wind tables, as in the file (`_chunk_order` keeps any other order).

## ASNEW.DAT (new-association league layouts)

BBShell FUN_68004fe0 (new-association dialog) reads, into the dialog object:

| Bytes | Dialog | Content |
|---|---|---|
| 21 x 20 | +0x1c | league layouts for 8, 10, .. 48 teams (FUN_68005180 picks (teams - 8) / 2) |
| 6 x 20 | +0x1c0 | division layouts for a league of 8, 10, 12, 14, 16 teams, then an empty one (teams 0) |
| 6 x 52 | +0x238 | default team lists for leagues of 8, 10, 12, 14, 16 teams, then the 14-team option-1 list |
| u16 n, n bytes | +0x370 | name pool: starts with a NUL, then NUL-terminated names |

Two zero bytes follow the pool (unread, `_trailer`).

Layout record (20 bytes), the same for league and division layouts:

| Off | Key |
|---|---|
| 0 | record_tag u16 (1234 league, 5678 division; never checked) |
| 2 | teams |
| 3 | option_count: 2 enables the second radio button (FUN_68005230, gadget 0x17); a division layout with 0 disables the league's division picker (FUN_68005370) |
| 4 + 8k | options[k].count: leagues (league layout) or divisions (division layout) |
| 5 + 8k | options[k].sizes, 3 x u8 team counts; a league of 0 teams uses the empty division layout |
| 8 + 8k | options[k].label, u16 pool offset |
| 10 + 8k | options[k].label2, u16 pool offset (second line, 0 = none) |

Name refs are byte offsets into the pool (FUN_68005220 returns dlg + 0x370 + ref); ref 0 is the pool's leading NUL,
the empty string. JSON holds the names themselves. Encode writes the pool in `_pool_order` (the file's order),
drops names no record uses, appends new ones, and recomputes every ref.

Default team list (52 bytes): u16 record_tag (3456), u8 teams, u8 at_0x3 (1, or 2 on the last list; not read by the
build), then 3 x 16 team ids, one row per league. The association build (BBShell decompile line ~4069) fills league k
with ids from row k of list (teams - 8) / 2, or of list 5 when the league uses division option 1. JSON trims trailing
zero ids; encode pads each row to 16.
