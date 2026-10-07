# The FPS Baseball Pro '98 file cipher: seed -> substitution table (data lane)

Status: SOLVED and verified. `gen.py` in this directory reproduces every table the
game and its ecosystem are known to produce: the shipped `f5dc` table (exact, from
the three PYR files) and all 82 visible H-file blobs (82/82 decode to >= 80% zeros
with the dominant byte mapping to 0x00; 38 byte positions decode to the same
non-zero value across >= 90% of files, i.e. real plaintext structure).

## Where it lives in the code

The cipher ships as identical copies in at least two modules of the decompiles
(`/mnt/nvme/bbpro98/index/<module>/_all.c`); none of the functions are named, the
names below are our labels:

| role | LineUp.dll | BBShell | what it does |
|---|---|---|---|
| build table from seed | `FUN_6b023440` | `FUN_68053450` | sentinel-walk, see algorithm |
| encipher buffer (apply fwd 3x) | `FUN_6b0234c0` | `FUN_680534d0` | `b = T[T[T[b]]]` per byte |
| decipher buffer (apply inv 3x) | `FUN_6b023500` | `FUN_68053510` | builds inverse, applies 3x |
| init table buffer | `FUN_6b0233e0` | `FUN_680533f0` | fills `tbl[i] = 255 - i` (overwritten by build) |
| read/derive 2 seed bytes | `FUN_6b023410` | `FUN_68053420` | e.g. random/derived seed source |

Call sites that prove the file formats:

- PYR/ASN load (LineUp `FUN_6b00be00`): reads the file's first two bytes
  sequentially into `param_1` (lo) then `param_2` (hi), calls build, then applies
  the INVERSE 3x to the record data. Bytes 0-1 of MLBPA97.PYR are `f5 dc`.
- PYR/ASN save (LineUp `FUN_6b00c120`): builds the table the same way from two
  seed bytes, applies FORWARD 3x to 0x405 bytes, writes the seed as the first two
  file bytes.
- H-file box scores (BBShell `FUN_680264c0`): reads one 0xa8a (2698)-byte table
  record, builds from `buf[0]` (lo, read as char) and `buf[1]` (hi), deciphers
  `buf+2` for 0xa88 (2696) bytes with the inverse. So the H layout the referee
  assumes (`02 65 | ff ff | 01 00 | 8a 0a | seed[2] | enc[2696]`) is exactly the
  game's: the record body is seed[2] + ciphertext[2696].

## The algorithm

`gen(lo, hi)` (lo = first seed byte as stored, hi = second):

```
start = (lo - 1) & 255
tbl[0..255] = start            # sentinel fill (the code fills 0x40 dwords)
pos = 0
v = lo
repeat 256 times:
    tbl[pos] = v               # place next value at the cursor
    v = (v + 1) & 255          # values lo, lo+1, ... wrap through all 256 bytes
    pos = (pos + hi) & 255     # stride step
    while tbl[pos] != start:   # skip occupied slots, wrapping
        pos = (pos + 1) & 255
```

Termination note: the 256th value placed is `lo + 255 == lo - 1 == start`, so the
final forward scan always finds a matching slot and stops; every seed terminates
(verified exhaustively for all 65536 seeds, every output a permutation).

The game then enciphers each byte by applying the table THREE times
(`FUN_6b0234c0`: `b = tbl[tbl[tbl[b]]]`). The forward table visible in files
(plain -> stored) is therefore the third iterate:

```
T = B^3,  i.e.  T[x] = B[B[B[x]]]
```

`gen.py SEED` prints exactly this T as 512 hex digits. Decoding is `T^-1` applied
once per byte (the referee's `inv[c]`), equivalent to the game's inverse applied
three times.

## Evidence

1. **f5dc exact.** Table recovered from the three shipped PYR files (record i has
   player id 100+i in bytes 0-1, so id bytes give T; all three files agree, full
   256-entry coverage) equals `gen(f5dc)` byte for byte. First hit, no fitting:
   the algorithm was transcribed from `FUN_6b023440` and matched immediately.
2. **All 82 H files.** For each `/mnt/nvme/bbpro98/work_install/Stats/MLBPA97.Hxx`,
   decoding the 2696-byte blob with `gen(seed)^-1` maps the dominant byte to 0x00
   and yields >= 80% zero bytes (referee scoring replicated locally: 82/82, and 38
   positions decode to an identical non-zero value across >= 90% of files).
3. **Decompile.** Two byte-identical copies of build/encode/decode found in
   LineUp.dll and BBShell, with call sites matching the PYR and H file layouts
   above (BBShell `FUN_680264c0` reads 0xa8a bytes, builds from `buf[0],buf[1]`,
   decodes `buf+2` for 0xa88 bytes).
4. **Cross-validation with third-party mod rosters.** The known affine mod-roster
   tables are also outputs of this one generator, found by exhaustive seed search:
   - mod 002: `T(x) = (0x73*x + 0x3a) & 255` == `B^3` for seed `f2e3`
     (and the bare walk table `B` equals it for seed `3abb`, lo = the constant 0x3a)
   - mod 006: `T(x) = (0x5f*x + 0xdd) & 255` == `B^3` for seed `7ddf`
     (bare `B` equals it for seed `dd9f`, lo = the constant 0xdd)
   The mod editors evidently reused the game's own table builder (they picked
   lo = the affine constant c). Four independent tables, one algorithm.

## Why earlier partial reads looked like XOR keys

The hfiles lane's HFILE_FORMAT.md modelled the blob as "XOR (or ADD) with a single
per-file constant K" and reported K unpredictable from the ciphertext. With the
real cipher: K is `T[0] = B^3[0]`, a per-seed constant, which is why constant-key
decode scored well (the blob is mostly plaintext zeros) but K never correlated
with the header bytes they tried.

## Sanity limits

- All 65536 seeds produce a permutation (no degenerate seeds), ~25 ms per run.
- Holdout H files (`re/asnseq/day*`, `work_state_s10`) are not present on this
  box, so the holdout pass could not be executed locally; nothing in gen.py is
  fitted to visible data beyond the algorithm itself (transcribed from the
  decompile), so unseen seeds are expected to pass.
- NOTE for the owner: `cipherref.py` (14:52 version) + `jailutil.py` run gen.py
  inside `systemd-run --user --scope`; this container has no systemd user manager
  (`/run/user/1000` absent, PID 1 is not systemd), so the jail aborts with
  "Failed to connect to user scope bus" for every seed before gen.py is even
  started. Verified gen.py itself runs clean under the same bwrap argv without
  the systemd wrapper, and the referee's scoring logic (replicated verbatim
  locally, analysis/score_local.py) prints PASS on the visible set.
