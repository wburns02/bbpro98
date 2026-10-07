# Task: a read/write codec for the game's c-tree Plus database files (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists, continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
The league file (`.ASN`), the stats database (`Stats/*.DAT`), `.eos` and `SCHEDTMP.DAT` are FairCom c-tree Plus
files (ISAM superfiles: data members with variable-length records plus B-tree index members). The game reads and
writes them only through `FPS_CT.dll` (exports INTISAM, OPNFIL, OPNIFIL, EQLREC, FRSSET, NXTSET, LSTSET, RWTREC,
ADDREC, DELREC, RBLIFIL, GETRES, ...). A codec that can list every record and rewrite, add and delete records while
keeping the indexes and free space consistent unlocks editing every league, schedule and stat in the game.

## Goal
Write `$LANE/codec.py` (Python 3 stdlib only, under 150 KB) with two commands that work on the ORIGINAL file:
```
python3 codec.py dump in.bin out.json
python3 codec.py apply in.bin edits.json out.bin
```
`dump` writes:
```
{"members": [{"name": str, "kind": "data" | "index" | "other", "data": <data member idx, index members only>, ...}],
 "records": [{"m": member idx, "off": file offset of the record PAYLOAD, "len": payload bytes, "del": bool}, ...],
 "index":   [{"m": index member idx, "koff": file offset where this entry's key bytes are stored, "klen": int,
              "rec": the "off" of the record it points to}, ...],      # each index member's entries in key order
 "meta": {... small: header fields, key definitions, anything useful ...}}
```
Report every record including deleted ones (`del: true`), with offsets of the payload bytes as stored in the file.
Report every index member's leaf entries in key order; `koff` must point at the key bytes inside the index node.
`apply` takes `edits = [{"op": "rewrite", "rec": off, "data": hex}, {"op": "add", "m": data member idx, "data": hex},
{"op": "delete", "rec": off}]` (offsets from `dump(in.bin)`, applied in order) and writes the edited file. `apply` with
`[]` must reproduce `in.bin` byte for byte. Edits must behave like the c-tree engine: a rewrite may change the length
(relocate the record when it no longer fits, free the old space); add allocates space (reuse free space or extend the
member) and inserts the record's key into every index of that data member; delete frees the space and removes the
keys; headers (record counts, free-space chains, member sizes, node links) stay consistent. Key values come from the
key segment definitions of each index (record bytes at given offsets, possibly transformed, with a record-position
suffix for duplicate-allowed indexes).

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/ctref.py /home/will/bbpro98/re/targets/ctree $LANE [--files MLBPA97.eos] [-v]`
It runs your codec in a jail (no network, no files except copies named `in.bin` / `edits.json`) and checks, per file:
- dump: record bytes are read at the reported offsets; records do not overlap; every `FA FA` record its own scanner
  finds is reported (the scanner is `work/parse_stats.py`: header `fa fa | u32 total | u32 payload_len | u32 | u32`,
  payload at +18, total == payload_len + 18); index key bytes are read at `koff`; every index points only at active
  records of its data member, at most once each, in nondecreasing key order (bytewise), and covers >= 98% of them.
- apply: `[]` is the identity; a same-length rewrite, a rewrite grown by 9 bytes, an add (a new record), a delete, and a
  combined list (grown rewrite + add + delete) each produce a file whose dump passes the same checks, has the same
  members, contains exactly the expected active records (compared by content, so records may move), and whose indexes
  over that data member gained or lost exactly the right number of entries.
PASS = every primary file passes. Then a model audits your code and a dump summary, and the same checks run on
held-out saves from other sim days that you never see (so parse structures generically; never special-case a file).

## Files (read only)
`/mnt/nvme/bbpro98/work_install/`: `Assn/MLBPA97.eos` (64 KB, start here), `Assn/_DEFAULT.ASN`, `Assn/MLBPA96E.ASN`
(224 KB each), `SCHEDTMP.DAT` (704 KB), `Stats/_DEFAULT.DAT`, `Stats/mlbpa96e.dat` (1.2 MB), `Assn/MLBPA97.ASN`
(2.6 MB), `Stats/mlbpa97.DAT` (5 MB). The 5 MB file gets 13 codec runs, so keep the codec reasonably fast.

## What is known (verify, do not trust)
- All eight share a header: bytes 0-1 `ff ff` or `ff 7f`, bytes 0x28-0x2f `81 00 00 02 00 00 00 80`.
  Bytes 2-5 look like the file size in 64 KB units-ish (`0x50` for the 5 MB file), bytes 8-11 like a physical
  end or high-water mark. 512-byte structure is visible (news blocks in the ASN tail are 512-byte aligned).
- Record lengths seen: Stats DAT payloads of 22/36/40/70/150 bytes (stat lines; `work/lib.py` decodes them: u16
  words, word0 in {0,1,2,3,16,17}, word1 == 2); ASN payloads of 17/21/25/494 bytes; many 494-byte payloads
  (= 512 - 18) everywhere, which may be how big structures or index nodes are stored.
- The game's wrapper (`\Fps_ct\Ctree\Ctree.cpp`, BBSIM decompile `/mnt/nvme/bbpro98/index/BBSIM/_all.c` lines
  16455-16760) opens the superfile host with `OPNFIL(filno, name, 0x200)` and members with `OPNIFIL(ifil)` where the
  member name is `host` + a separator string + `member` (FUN_6801d065). IFIL structures (file name pointer, data file
  number, record length, extension size, file mode, number of indexes at +12, ..., index definition pointers) are
  static data in BBShell.dll / BBSIM.dll / Upstats.dll; their decompiles are next to BBSIM's in
  `/mnt/nvme/bbpro98/index/`.
- c-tree Plus is publicly documented (FairCom c-tree Plus 6.x): superfiles keep a member directory; variable-length
  data files use a record header with a mark and lengths and a free-space index; index files are B-trees with
  key-compressed or plain leaf nodes. Check every assumption against the bytes.

## Tools and budget
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (file header, member directory, record header, free space, index nodes,
  key definitions per member, evidence for each).

Stop when the referee prints PASS, or when you are out of ideas for this round. Always leave `codec.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/ctree/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
