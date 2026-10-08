# Task: a semantic read/write codec for the motion-path file DMP.DAT (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
`DMP.DAT` ("Could not open DMP file", "Invalid number of motion paths in DMP file", BBSIM dmp.cpp and FastSim
FDMP.cpp) holds the 66 motion paths the simulation uses. Editing it changes how plays move. The container is trivial;
what is missing is the meaning of every number and of every path.

## Format facts (verified by Claude)
- `u16 n (66) | u32 offsets[n + 1]` (absolute; the last one is the file length) `| n paths`.
- Path: `u16 frames | u16 h1 | u16 h2 | frames x 62 bytes` (31 signed 16-bit words per frame). Frame counts 0..23.
- The game copies each path into a 0xf86-byte object (6 + 64 x 62: at most 64 frames) and checks n against the count
  it expects. Many paths are exact duplicates of others (e.g. 4 = 5, 1 = 6).
- First frame of path 0: `-2 25 71 | 39 69 51 | 14 104 56 | ...`, which reads like (x, y, z) triples: 10 points plus one
  extra word somewhere. Verify which word is extra.

## Goal
Write `$LANE/dmp.py` (Python 3 stdlib only, under 200 KB; it runs alone in a jail, never import or open other files):
```
python3 dmp.py decode in.bin out.json
python3 dmp.py encode in.bin edited.json out.bin
```
`decode` writes at least `{"paths": [{"index": i, <named h1/h2 fields>, "frames": [{<named fields>}, ...]}, ...]}`.
- The integer leaves of a path (excluding "index" and "frames"), read in key order depth first, must equal h1, h2;
  the integer leaves of a frame, in key order depth first, must equal its 31 words. Strings/floats/bools/null are free
  (use them for descriptions: what each path is for, units, which player/object a point is).
- Name things for what they are (body parts or objects, axes, time/tick, flags). Numbered placeholders (j3_x, p7,
  w12, unk) for most keys fail the referee's generic-name check and the audit.
- `encode` REBUILDS the file from edited.json (paths may gain or lose frames, up to 64): `encode(x, decode(x)) == x`.

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/dmpref.py /home/will/bbpro98/re/targets/dmp $LANE [-v]`
on `/mnt/nvme/bbpro98/work_install/DMP.DAT` (read only): schema and leaf fidelity, generic-name cap, round trip, a
value edit, and a resize edit (one path gains a frame, another loses one) checked by a trusted parser. Then a model
audits your code and a decode summary, and the same checks run on held-out synthetic files built from the real paths
(shuffled, resized, perturbed, fewer paths). Decode generically: never hard-code path data, counts or offsets.

## Tools and budget
- Decompiles: `/mnt/nvme/bbpro98/index/{BBSIM,FastSim,...}/_all.c` (BBSIM FUN_68024001 is the loader).
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (every field and path, with the evidence: code addresses or data facts).

Stop when the referee prints PASS and your names are backed by evidence, or when you are out of ideas for this round.
Always leave `dmp.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/dmp/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
