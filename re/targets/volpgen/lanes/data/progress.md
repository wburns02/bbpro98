# progress.md — lane `data` (volpgen)

## Round 6 verification (2026-10-07)

This round was a verification round: the round-5 state (all six files PASS on
localref normal + holdout) was reproduced unchanged. No edits to `voldat.py`
were needed.

- `python3 localref.py` → PASS (all six ok), `python3 localref.py --holdout`
  → PASS (all six ok, 3 edit rounds per file at seed 9000). Output archived
  to `localref_latest.log` in this lane (the `runs/` dir is bind-mounted
  read-only here, so new logs go to the lane root).
- The true referee command was retried and fails identically to round 5:
  "Failed to connect to user scope bus via local transport". Root cause now
  confirmed — this session itself runs inside a bwrap container whose PID 1
  is bwrap, and `/sys/fs/cgroup` is masked from view, so `systemd-run
  --user` (used by the referee's `jail()` in jailutil.py) cannot start a
  user manager. This is infrastructure-only; the codec runs fine under
  `python3 -I`.
- Cross-lane check: the `code` lane (`../code/`), whose `voldat.py` was
  built independently, also yields PASS on its own `local_ref.py` run —
  both lanes agree on a passing layout family for all six files.
- `voldat.py` is 20,305 bytes, stdlib-only (`json`, `struct`, `sys`).

## Round 5 (2026-10-07)

Starting state: `voldat.py` existed from earlier rounds (rounds 1–2 crashed
before writing; round 3 produced a codec that passed 5/6 files, failing only
PGEND.DAT with one uncovered string `12E2d`). Round 4's log was empty (model
unrecognized), so this round continued from round 3's state.

Note: the real referee `voldatref.py` cannot run in this sandbox — its bwrap
jail needs a systemd user-scope bus that does not exist here
("Failed to connect to user scope bus via local transport"). `localref.py`
(present from an earlier round) runs the referee's own checks with only the
jail swapped for a plain `python3 -I` subprocess; every check (coverage,
opaque budget, generic keys, round trip, edit tests, holdout seeds) is the
referee's unmodified code.

### Fixes applied to voldat.py

1. **PGEND `ageParamBlock` was parsed as 8 bytes; it is 7.** The
   NUL-terminated label `12E2d` starts at file offset 0x17C (380). With the
   extra byte consumed, `ageLabel` began at `2E2d` and the referee's coverage
   check failed on the leading `1`. Fixed the field width
   (`("bytes", 7, "ageParamBlock", True)`).

2. **`encode_pgend_doc` flattened `agingCurveRows` to 256 ints** while
   `wr_field`'s rows handler expects rows-of-8 and calls `unchunk` on them
   (`'int' object is not iterable`). This was latent — it only surfaced after
   fix 1 let the encode path run. Fixed `encode_pgend_doc` to keep the rows
   nested and made `wr_field`'s rows handler accept either shape.

3. **`encode_pgend` required the record to stay exactly 938 bytes**, but the
   referee's edit test appends "Qz" to content strings (here the profile
   `asciiTail`s), growing the record. `recordSize` is a `_` (derived) value,
   so the encoder now assembles the body first, computes its length and
   writes `PGD:` + recomputed size.

4. **`_trailingUnreadByte` was read at the fixed offset 946**, inside the
   data for any edited (grown) file, which made `encode(decode(x)) != x` on
   edited files. Now read relative to EOF (`blob[-1]`) and appended.

Referee output (localref.py, that round) is archived in
`localref_latest.log`.

### Round-5 referee output

```
  {"file": "PGENFRST.DAT", "ok": true}
  {"file": "PGENLAST.DAT", "ok": true}
  {"file": "PGENTABL.DAT", "ok": true}
  {"file": "PGEND.DAT",    "ok": true}
  {"file": "AGEPLYR.DAT",  "ok": true}
  {"file": "SPRPLYR.DAT",  "ok": true}
PASS
```

`--holdout` mode (3 edit rounds per file, seed 9000): PASS on all six.

Extra fuzz beyond the referee: 40 random SystemRandom seeds x 6 files x 6
edits per file through the referee's own `edit_test` — 0 failures.

Budgets: opaque bytes 0% (name pools, AGEPLYR, SPRPLYR), 2.7% (PGENTABL),
5.7% (PGEND) against the 25% cap; 0 generic keys in every file.

### What was learned

- Coincidental ASCII is the main trap in these binary tables: rating
  percentage bytes (0x20–0x7e) followed by a NUL look like strings to any
  scanner, so spans like `Z(Z<`, `dKdE` and `12E2d` must be decoded *as
  string fields* at those exact offsets — the coverage check finds the run,
  not a substring.
- Fixed offsets in the JSON for values that sit after variable-length
  content (trailing bytes) break as soon as an edit grows a string; derive
  them from EOF instead.
- The referee validates before it encodes, so shape bugs in the encode path
  (latent `unchunk` on an int list) only surface after the coverage check
  passes — worth smoke-testing encode directly with `python3 -I`, not just
  through the referee.

### Reuse notes for other lanes

- Both name pools: 16-byte header `0x12345678/dataSize/count/recSize`
  (14808x12 first, 14900x14 last), NUL-padded records, one unread trailing
  0x00 byte; duplicates are selection weights.
- PGEND: label field at rec+0x14C is `12E2d` with the 7-byte age param block
  in front of it; record base is file+8; 40 leading bytes are always-zero
  runtime counters.
- AGEPLYR is byte-identical to the 32x8 curve at PGenD rec+0x1FA; SPRPLYR's
  loader stops at 0x6B but the rest of the file decodes the same way.
- `FORMAT.md` in this lane documents every layout with evidence.

### Current referee output

Local referee (jail swapped for a subprocess, referee code otherwise
unmodified): PASS on all six files and on `--holdout`. The true referee
command could not run in this sandbox for infrastructure reasons (no systemd
user-scope bus), not for codec reasons.

### Round-6 sanity checks beyond localref

- Isolated-dir smoke test: copied `voldat.py` plus PGENFRST.DAT and
  SPRPLYR.DAT to /tmp and ran `python3 -I voldat.py decode/encode` there —
  decode JSON has only named keys plus `_`-prefixed deriveds (selector drew
  14,808 first names; SPRPLYR shows the base groups, four named ramps and
  their negative heads), and re-encoded bytes are `cmp`-identical to the
  originals.

## Round 8 (this round, 2026-10-07) — leak-guard fix

The driver's leak guard (`/home/will/bbpro98/re/targets/drive.sh`, with this
target's `LEAK_RE = 'targets_data|/mnt/nvme|/home/will|\.\./'`) greps the
decoder source after PASS; round 2's run failed there because the
`voldat.py` module docstring cited the decompile index path
(`/mnt/nvme/bbpro98/index/BBShell`). The codec itself was already correct.

### Fix

- Removed the absolute index path from the `voldat.py` docstring (kept
  "mapped against the BBShell decompile"); no other matches for
  `targets_data|/mnt/nvme|/home/will|../` remain in the source.
- Same for `FORMAT.md` (this lane's documentation file, also grepped by no
  one, but kept consistent).

### Verification

- `grep -E 'targets_data|/mnt/nvme|/home/will|\.\./' voldat.py` → no match.

- `python3 localref.py` → PASS on all six files;
  `python3 localref.py --holdout` → PASS (seed 9000, 3 edit rounds/file).
  Both runs archived to `localref_latest.log`.

- `voldat.py` is 20,271 bytes, stdlib-only (`json`, `struct`, `sys`); shebang
  `#!/usr/bin/env python3` is unrelated to the leak pattern and fine.

### Note for the next round

- Only remaining known issue was the leak guard; that is fixed. If the
  referee / audit round fails in a new way, capture its exact output here.
- The `runs/` directory is bind-mounted read-only in this lane; write new
  logs to the lane root (see `localref_latest.log`).
