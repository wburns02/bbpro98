# progress.md - lane `code` (VOL codec)

## Round 1 (2026-10-07)

Status: **codec.py complete, referee-equivalent checks print PASS on all 4 files.**
(format documented in `FORMAT.md`, evidence below.)

### What was done

1. Ported the reader path from the decompile (`EZShell Utility\Volume.cpp`):
   `6a035f7a` mount builds a `count+1`-record table of `{u32 key, u32 value}`;
   `6a0362b5` is the name hash (uppercase, sum+xor, seed-selected bytes,
   `+ (short)(xor*sum)`); `6a036235` = `table[i].value`; `6a035bb8` sets
   entry range `[value[i], value[i+1])` and mount verifies
   `table[count].value == filesize` (sentinel = EOF, entries contiguous).
   That last fact is what makes next-offset slicing correct.
2. Confirmed the on-disk layout by parsing all four archives
   (SHELL.VOL pristine + modded, SHELL1.VOL, SHELL2.VOL):
   - header `VOLM`, u32 version=1, u8 0, u8 ndir, u16 dirnames_len
   - ndir NUL-terminated dir names ending in `\` (flat list, e.g. `Misc\`)
   - u16 count, u32 dirbytes (= count*18), count x 18-byte records:
     name ASCIIZ (max 12 chars; a 12-char name overwrites the low byte of
     the following u16), u16 dir<<8|type (0xff dir = root), u32 blob offset
   - blobs: u8 method=2, u32 size (=len(payload)-1), u32 DOS date+time stamp,
     then the raw payload (PCX `0a 05 01 08`, WAV `RIFF`; DATs start `IDX:`
     / `0x12345678`). No compression anywhere.
3. Key discovery (from the modded SHELL.VOL): `MENU.REQ` was grown by 236
   bytes with its `size`/`stamp` left stale and all later offsets shifted.
   Offsets are authoritative, `size` is advisory. A codec that recomputes
   `size` cannot round-trip the modded file; ours preserves the blob header
   and the record's static 16 bytes (which include non-NUL writer filler,
   e.g. `c3 00 00`, that recurs across archives and is not name-derived).
4. `codec.py` (7.4 KB, stdlib only): unpack -> manifest + `eNNNN.bin`;
   pack recomputes ndir/dirnames_len/count/dirbytes/every offset and
   preserves record bytes + blob headers. Manifest ~3.5-5 KB (cap is
   64 KB + 1% of input).
5. Verified inside the referee's exact bwrap+prlimit jail (both commands),
   then with the referee's own `check_file` logic on all 4 files:

```
  SHELL.VOL   ok=true coverage 0.999 magic 10/10 roundtrip edit
  SHELL1.VOL  ok=true coverage 1.0   magic 41/41 roundtrip edit
  SHELL2.VOL  ok=true coverage 1.0   magic 12/12 roundtrip edit
  (secondary) SHELL.VOL (modded) ok=true roundtrip edit
PASS
```

### Environment note (not a codec issue)

The referee here (`arcref.py` -> `jailutil.py`) wraps the jail in
`systemd-run --user --scope`; this container has no systemd user manager
(no /run/user, PID 1 is not systemd), so the referee as shipped cannot
execute inside the lane sandbox. The PASS above comes from the referee's
own code run from a /tmp copy of `arcref.py`+`jailutil.py` with only the
`systemd-run ... --` prefix stripped (referee files untouched); the bwrap,
prlimit and all checks are the referee's own. On the host, drive.sh runs
the real referee, where a user session exists.

### Open items / next-round ideas

- Record u16 low byte ("type": 0xad PCX, 0xa6 WAV, 0xa7, 0xa0-a4, 0x00) and
  the post-NUL filler bytes are preserved verbatim; meaning unknown. If a
  future lane needs pack to synthesize records for NEW names, model them as
  filler=0 + type from extension; our round-trips never synthesize.
- `size = len(payload)-1` quirk: writer emits one less; unexplained but
  harmless (preserved).
- The in-memory hash table and seed (`00 01 0a 00` / `00 02 10 00`) are
  rebuilt by the game at mount time, not stored in the file; no action
  needed for lossless round-trip. seed[i] semantics (name-byte selector)
  documented in FORMAT.md section 3.

Referee tail: PASS (see above). codec.py left runnable at
`/home/will/bbpro98/re/targets/vol/lanes/code/codec.py`.
