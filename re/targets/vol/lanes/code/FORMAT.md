# FPS Baseball Pro '98 `.VOL` ("VOLM") container format

Reverse-engineered 2026-10-07, lane `code`. Sources: the four archives below, plus the
game's reader decompiled at `/mnt/nvme/bbpro98/index/EZShell/_all.c` (EZShell
`Utility\Volume.cpp`, functions `6a035f7a` mount, `6a036158` hash lookup, `6a036235`
table access, `6a0362b5` name hash; `Utility\Volfile.cpp` wrapper `6a035bb8/6a035c74/
6a035d1e`).

Files used as evidence:

| file | size | count | dirs |
|---|---|---|---|
| `BBPRO98_package/game/SHELL.VOL` (pristine) | 1477536 | 30 | `ShelPcx8\` |
| `work_install/SHELL.VOL` (modded rebuild) | 1477772 | 30 | `ShelPcx8\` |
| `work_install/SHELL1.VOL` | 11312660 | 41 | `ShelPcx8\` |
| `work_install/SHELL2.VOL` | 2047199 | 12 | `Misc\`, `ShelPcx8\` |

## 1. Header

```
off  size  field                         SHELL.VOL   SHELL1.VOL   SHELL2.VOL
0    4     magic "VOLM"                  VOLM        VOLM         VOLM
4    u32   version                       1           1            1
8    u8    0                             0           0            0
9    u8    ndir                          1           1            2
10   u16   dirnames_len                  10          10           16
12   ...   dirnames (see 2)
```

`dirnames_len` = total bytes of the directory-name strings including each NUL
("ShelPcx8\" = 9+1 = 10; "Misc\" + "ShelPcx8\" = 6+10 = 16). Evidence: it matches the
parsed strings exactly in all four files, and the entry count lands right after
`12 + dirnames_len` in all four.

## 2. Directory names (subdirectory records)

`ndir` NUL-terminated strings, each ending in a backslash, concatenated:
`"Misc\0" "ShelPcx8\0"`. These name the subdirectories the archive is organized into;
there is no tree, just a flat list. The mount code in `6a035f7a` never touches them;
they are metadata for the mod/volume tools.

## 3. Entry directory

```
u16   count       entry count (30 / 41 / 12)
u32   dirbytes    bytes of the record block = count * 18 (540 / 738 / 216)
count * 18-byte records
```

Each record (fixed 18 bytes):

```
[0..11]  u8[12]  file name, ASCIIZ. A name of up to 11 chars is NUL-padded; a
                 12-char name (e.g. PGENFRST.DAT, UNICOLOR.PCX) fills the field
                 completely and its NUL overwrites the LOW BYTE of the u16 below,
                 which then reads 0xff00 / 0x0000 etc.
[12..13] u16     dir<<8 | type: high byte = index into the directory-name list
                 (0xff = archive root), low byte = resource type
[14..17] u32     absolute offset of the entry blob in the file
```

Type bytes observed: `0xad` SHELLxx.PCX, `0xa7` GLENW.PCX, `0xa6` *.WAV,
`0xa0-0xa4` / `0x00` SHELL.VOL DAT/PCX/REQ files. The dir-index reading is
corroborated three ways: SHELL1.VOL (one dir) is all `0x00ad`; SHELL2.VOL splits
exactly `0x00a6/0x00a7` (Misc) vs `0x01ad` (ShelPcx8), and SHELL42-48.PCX continuing
SHELL01-41.PCX belong to ShelPcx8 just like SHELL1.VOL's contents; the root/`0xff`
entries in SHELL.VOL are precisely the game's own DAT/PCX/REQ files while the added
`SHELL00.PCX` is `0x00ad` (ShelPcx8).

Bytes between a name's NUL and offset 12 are writer residue, not padding: they are
non-zero for several entries (`MENU.DAT`, `MENU.REQ`, `DIAL.REQ`, `TRIM.PCX` store
`c3 00 00`; `HAT.PCX` stores `9f c3 00 00`) yet zero for same-length neighbours
(`PGEND.DAT`, `WBREQ.PCX`), and identical `c3 00 00` recurs across two different
archives (SHELL.VOL and SHELL2.VOL EYE*.WAV). Not derivable from the name; the codec
preserves the record's static 16 bytes verbatim and recomputes only the offset.

The offsets are strictly increasing and the first one equals
`12 + dirnames_len + 6 + 18*count` in all four files (no alignment padding). The last
entry ends exactly at EOF.

### What the game does with this (decompile cross-check)

`6a035f7a` (mount) opens the volume and builds an in-memory sorted table of
`count+1` 8-byte records `{u32 key, u32 value}` (`count*8+8` bytes read, assertion at
Volume.cpp:63 when the size would change). `6a0362b5` computes `key` from the entry
name: uppercase (`& 0x5f`) up to 13 bytes, `sum += (signed char)c`, `xor ^= c`, then
`key = sum_over_i(seed[i] -> selected name byte)` assembled big-endian
`key = key*0x100 + byte`, finally `+ (short)(xor*sum)`. `6a036235` returns
`table[i].value`; `6a035bb8` (open entry) sets start = `value[i]`, end =
`value[i+1]`, and the sentinel `table[count].value` is compared against the file size
in `6a035f7a` - i.e. entries are contiguous `[off[i], off[i+1])`. The table is built
from the directory, not stored (no `{seed, count, table}` structure with
`table[count].value == filesize` exists anywhere in the files; scanned). The files'
record `u16` is not that hash either (`AGEPLYR.DAT` would hash to 0x6cb1/0xc34a
depending on seed use, stored is 0xffa4).

## 4. Entry blob

```
off+0  u8    method: 2 in every entry of every file (stored / no compression)
off+1  u32   size: len(payload)-1 in all pristine entries
off+5  u32   stamp: DOS date (high u16) + DOS time (low u16). E.g. 0x544d2271 =
             2022-02-13 04:19:34; 0x4ab8232c = 2017-05-24 04:25:44. All observed
             values decode to valid even-second DOS times, minutes 10-25.
off+9  ...   payload: the entry's bytes, verbatim (PCX starts 0a 05 01 08,
             WAV starts "RIFF", DAT files start with their own magics like
             "IDX:" / 0x12345678)
```

`size = len(payload)-1` holds for every entry of the three pristine archives. It is
NOT a compression size: payloads are stored raw (the PCX/WAV magics are at off+9, and
a 640x480 PCX occupies ~250-300 KB, matching its RLE size).

The modded `SHELL.VOL` proves the offsets - not `size` - are authoritative:
`MENU.REQ` grew from 66084 to 66320 bytes (a 236-byte insert) but its `size` and
`stamp` were left untouched (`size=66074`, while the payload is 66311 bytes), and
every later offset shifted by exactly 236. So `size` means "logical size the game
should read", and tools may append bytes the game ignores. Consequence for a codec:
slice payloads by next-offset (EOF for the last entry) and preserve `method`, `size`,
`stamp` verbatim; recomputing `size` would corrupt a round-trip of the modded file.

## 5. Codec behaviour (`codec.py`)

- unpack: parses header/dirs/records, writes one `eNNNN.bin` per entry and a
  `manifest.json` with, per entry: `name` (dirname + base name, `ShelPcx8\SHELL01.PCX`
  style, root entries have no prefix), `file`, `flags` (the record u16), `rec`
  (hex of the record's static 16 bytes: name + filler + dir/type word) and `hdr`
  (`method`, `size`, `stamp`).
- pack: recomputes `ndir` from the (preserved) directory list, `dirnames_len`,
  `count`, `dirbytes = 18*count` and every blob offset from the actual payload
  lengths; writes each preserved record with the new offset and each blob header
  verbatim. Works for any entry sizes and for removed entries.
- Round-trip: byte-identical for all four archives, including the modded
  `SHELL.VOL`; the referee's grow-largest/drop-smallest edit also round-trips.

## 6. Open questions

- The record u16's low byte (resource type) and the filler bytes: semantics unknown,
  preserved verbatim.
- `size = len(payload)-1`: why the writer emits one less than the payload length
  (writer quirk or a consumed sentinel byte), unknown; irrelevant to lossless packing.
- `method` byte 2: only value observed; if other archives use compressed methods,
  the payload here would need a decompressor (none seen in the four files).
