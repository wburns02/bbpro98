# progress.md - data lane (cipher seed -> table generator)

## Round 1 (2026-10-07): SOLVED - generator found, verified, gen.py delivered

**Result: `gen.py` reproduces the game's cipher exactly. f5dc exact on first port;
82/82 visible H files decode (>= 80% zeros, dominant byte -> 0x00); 38
structure-agree positions. Local replica of the referee prints PASS. The shipped
referee cannot run in this container (no systemd user bus, see blocker below);
both lanes hit this.**

### Route taken

1. Recovered the f5dc forward table from the three PYR files exactly as the
   referee does (record i -> id 100+i bytes); all three files agree, full
   permutation. Saved `analysis/f5dc.bin`.
2. Brute-forced the algebraic families first (affine mod 256, XOR-affine,
   affine composed with output/input bit permutations and rotations, ~2M forms):
   ZERO hits. The table is not algebra - it is algorithmic (a walk).
3. Went to the decompiles and found the cipher cluster by looking for 256-byte
   stack arrays, then confirmed by call sites. My find: LineUp.dll
   `FUN_6b023440` (build), `FUN_6b0234c0` (apply fwd 3x), `FUN_6b023500`
   (inverse 3x), and the BBShell byte-identical copies (`FUN_68053450`,
   `FUN_680534d0`, `FUN_68053510`), plus BBShell's H-file reader
   `FUN_680264c0` (reads 0xa8a bytes, builds from buf[0],buf[1], decodes
   buf+2 for 0xa88 bytes) - which pins the H-file layout the referee assumes.
4. Transcribed `FUN_6b023440` verbatim into Python; `gen(0xf5,0xdc)` composed 3x
   (the game applies the table three times per byte) matched the recovered f5dc
   table EXACTLY on the first attempt. No free parameters.
5. Wrote gen.py; replicated the referee's scoring locally
   (`analysis/score_local.py`, line-for-line same pyr_table/blobs/score):
   `{"mode": "hfiles", "files": 82, "f5dc_exact": true, "h_zero_ok": 82,
   "nonzero_agree_positions": 38}` -> PASS.

### New facts beyond the code lane's notes

- **The mod-roster affine tables are outputs of this same generator.** Exhaustive
  seed search: mod002 affine (m=0x73,c=0x3a) == B^3 of seed `f2e3`; mod006
  (m=0x5f,c=0xdd) == B^3 of seed `7ddf`; the bare walk table B equals them for
  seeds `3abb` / `dd9f` (whose lo byte = the affine constant c - the mod editors
  reused the game's builder and picked lo = c). So four independent tables from
  three different producers all reduce to one algorithm. (The code lane's
  CIPHER.md says the mod tables come from "the editors' own simpler scheme";
  the seed evidence says otherwise. Doesn't affect gen.py.)
- **The hfiles lane's "constant XOR/ADD key" model of the blob is explained**:
  their K is `T[0] = B^3[0]`, constant per seed, unpredictable from the header
  bytes they tried - exactly as observed there.
- From the code lane (adopted, verified plausible): Upstats picks seeds as
  `random_range(0,255)` for byte 0 and `random_range(1,255)` for byte 1, so
  game-written H seeds never have hi (step) = 0. gen.py handles hi=0 anyway.

### Minor discrepancy with the code lane

They label BBShell `FUN_68053510` as the encipher; the H-file READER
(`FUN_680264c0`) calls it on a freshly-read blob, so it is the decipher (it
builds the inverse table first - `FUN_680534d0` is the direct 3x apply, i.e. the
encoder). Direction of T is pinned by data regardless: forward plain->stored =
B^3 is what the PYR id-byte recovery and all 82 blob decodes confirm.

### Verification performed

- gen(f5dc) == PYR table, byte-exact; all three PYRs internally consistent.
- 82/82 H files: dominant byte -> 0x00, 83-88% zeros; 38 positions agree
  non-zero across >= 90% of files.
- All 65536 seeds: base table and B^3 both permutations, no hangs (3.5 s total);
  single run ~25 ms (referee budget 60 s).
- Runs clean under the referee's exact bwrap argv (without the systemd wrapper)
  for f5dc and 080a.
- gen.py: stdlib only (sys), 1.5 KB, reads no files, one line of hex out.

### BLOCKER (environment, not solvable from the lane)

`cipherref.py` (14:52 version) jails gen.py via `systemd-run --user --scope`
(jailutil.py). This container has no systemd: PID 1 is not systemd, there is no
`/run/user/1000`, and `systemd-run --user` fails with "Failed to connect to user
scope bus via local transport: No such file or directory" for every seed before
python is ever started. Reproduced the failure, then reproduced the jail without
the systemd wrapper (works). I did not and will not modify cipherref.py or
jailutil.py, and I did not fake a systemd-run shim to force a PASS. The
orchestrator should run the real referee from a context with a systemd user
session; expected output is the PASS line above (holdout files
`re/asnseq/day*`, `work_state_s10` are also absent from this box, so the 36
unseen-seed check can only run on the grading host).

### State

- `gen.py` - final, runnable, verified. `python3 gen.py f5dc` ->
  `1d0125f982a68aae7044684cd5e9cdf1...` (512 hex).
- `CIPHER.md` - full documentation: decompile addresses, algorithm, evidence,
  cross-validation.
- `analysis/` - recovery/scoring/verification scripts (recover.py, algebra.py,
  verify_gen.py, score_local.py, exhaustive.py, mod_check.py, f5dc.bin,
  hfiles.json).
- No referee PASS line from the real binary in this container (blocked as
  above); local replica PASS on the full visible set.

## Round 2 (2026-10-07): guard fix - gen.py scrubbed of path references; algorithm untouched

**Orchestrator's real referee run now works and printed PASS for this lane
(`f5dc_exact: true`, 82/82 h_zero_ok, 38 agree positions); the only failure was
the leak guard: "gen.py references forbidden paths".**

- Cause: the gen.py docstring cited the decompile source by path
  (the LineUp `_all.c` file under the index tree) and the file had a
  `#! /usr/bin/env` shebang, both path-shaped. The cipher itself was never wrong.
- Fix: rewrote the docstring to describe provenance without any path
  ("recovered from the game binary decompile") and dropped the shebang. gen.py
  now contains zero `/` characters (verified by grep), no `open`, no `os`, no
  `pathlib`; imports only `sys` and touches only `sys.argv[1]`. It reads
  nothing but its command line.
- Verified unchanged behavior:
  - `python3 gen.py f5dc` byte-identical to the round-1 output
    (diff clean; `1d0125f982a68aae...`).
  - Spot seeds f5dc 6304 080a f2e3 7ddf 3abb dd9f 0000 0100 all as in round 1.
    f2e3 still reproduces the mod002 affine table (3a ad 20 ...) as B^3.
  - Local replica of the referee (`analysis/score_local.py`, same pyr_table /
    blobs / score logic, direct `python3 -I gen.py` instead of the jailed run):
    `{"f5dc_exact": true, "h_files": 82, "h_zero_ok": 82,
    "nonzero_agree_positions": 38}` -> PASS. Holdout mode reports FAIL here only
    because the 36 holdout files are not on this box (round-1 blocker); gen.py
    is the game's exact algorithm with no fitted parameters, so holdout risk is
    unchanged (nil).
  - Real `cipherref.py` still cannot run inside this container (systemd user
    bus absent, same round-1 environment blocker) - needs the orchestrator's
    context, where it already produced the PASS above.
- Nothing else changed: CIPHER.md, analysis/ and the algorithm are exactly as
  delivered in round 1.
