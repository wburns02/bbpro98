# Task: the seed -> substitution-table generator of the game's file cipher (FPS Baseball Pro '98)

You are the builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
The game enciphers record bytes with a 256-byte substitution table derived from a 2-byte seed stored in the file.
All shipped PYR (player) and ASN (league) files use seed `f5dc`, whose table is known (recoverable from data). Every
per-game box-score file `Stats/MLBPA97.Hxx` starts with a 2698-byte table enciphered with its OWN seed. Without the
generator those blobs stay unreadable and new files cannot be written with fresh seeds.

## Goal
Write `$LANE/gen.py` (Python 3 stdlib only, under 30 KB, reads no files): `python3 gen.py SEED` where SEED is the two
seed bytes as stored, as 4 hex digits (e.g. `f5dc`, `6304`), prints the forward table plain -> stored as 512 hex
digits on one line (byte i of the output = stored value of plain byte i).

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/cipherref.py /home/will/bbpro98/re/targets/cipher $LANE [-v]`
It runs gen.py in a jail and checks: every table is a permutation; `gen(f5dc)` equals the table recovered from the
three PYR files exactly; for each of the 82 H files in `/mnt/nvme/bbpro98/work_install/Stats/`, decoding its blob with
`gen(seed)` maps the blob's most common byte to 0x00 and leaves >= 80% zero bytes. It also reports how many non-zero
positions decode identically across files (only a fully right table makes structure appear). PASS needs f5dc exact
and >= 97% of H files. Then a model audits your code, and the same checks run on 36 seeds you never see.

## Data (read only)
- PYR: `/mnt/nvme/bbpro98/work_install/Assn/{MLBPA97,_DEFAULT,MLBPA96E}.PYR`: bytes 0-1 = seed `f5 dc`, bytes 2-3 =
  version `01 00`, 192-byte header, then 192-byte records; record i holds player id 100+i (u16 LE) in bytes 0-1, so the
  stored bytes of ids give the table (see `/home/will/bbpro98/BBPRO98_package/research/dump_pyr.py`; ~2400 records
  cover all 256 low bytes).
- H files: `/mnt/nvme/bbpro98/work_install/Stats/MLBPA97.H*`: `02 65 | ff ff | 01 00 | 8a 0a` (one record of 2698
  bytes), then the 2-byte seed, then 2696 enciphered bytes, then plaintext `02 65` tables (decoded format:
  `/home/will/bbpro98/re/hfiles/lanes/data/HFILE_FORMAT.md`). The blob is mostly zero padding.
- Mod rosters made by third-party editors used affine tables T(x) = (m*x + c) & 255 (mod 002: m=0x73, c=0x3a;
  mod 006: m=0x5f, c=0xdd); the shipped f5dc table is NOT affine mod 256, but shows XOR-linear structure in places
  (forward table entries 4..7 = 82 a6 8a ae: XOR differences 0x24, 0x08, 0x2c). Verify, do not trust.
- Decompiles: `/mnt/nvme/bbpro98/index/<module>/_all.c` (+ `_functions.tsv`) for Upstats, BBShell, LineUp, BBSIM,
  FastSim, FPS_DCL, FPS_CT, EZShell.

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the algorithm in `$LANE/CIPHER.md` (where it lives in the code, the algorithm, the evidence).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `gen.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/cipher/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `CIPHER.md` (read-only to you) and reuse anything verified.
