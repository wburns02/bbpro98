# Task: name the unlabelled fields of the BBPro 98 highlight tape (.tap)

Work only in `$LANE`. Write `$LANE/NAMES.json`. Nothing you write is executed; the referee checks the JSON.

## Background
`/home/will/bbpro98/work/tapcodec.py` decodes and re-encodes the game's highlight tapes losslessly, and
`/home/will/bbpro98/work/spec/TAP_FORMAT.md` documents the layout. 29 stored fields are still called `at_0x..` after
the object offset they are copied from. Your job is to find what each one means in the game code and name it.
Read TAP_FORMAT.md first: it says which object each field comes from and which routine copies it (for example the
ball record is copied by FUN_68048e56 from the ball object, the camera by FUN_680157e8 from the global camera at
0x680d5460, fielders by FUN_6802d8a3, offense by FUN_6805de6a, actors by FUN_68005985).

Sources (all read-only):
- `/mnt/nvme/bbpro98/index/BBSIM/_all.c`: the Ghidra decompile of BBSIM.DLL, each function after a line
  `// ==== <va> FUN_<va> callers=[...]`. `_functions_labeled.tsv` beside it has a short name and comment per function.
- The tapes `/mnt/nvme/bbpro98/targets_data/tap/highlight002.tap` and `highlight005.tap`. Decode one with
  `python3 /home/will/bbpro98/work/tapcodec.py decode highlight002.tap /mnt/nvme/bbpro98/targets_data/tap/highlight002.tap $LANE/h002.json`
  and look at how each field changes over the frames (constant, a counter, a coordinate, a small enum, an angle, a
  pointer-like value...). Values and the code must agree.

Offsets are bytes into the source object. The decompile writes them many ways: `*(short *)(param_1 + 0x50)` on a
byte pointer, `param_1[0x28]` on a `short *` (byte 0x50), `*(int *)(iVar1 + 0x44)`, `param_1 + 0x11` on an `int *`
(byte 0x44). Work out each function's pointer type before you trust an offset.

## The 29 fields (key in NAMES.json: struct.old_key)
```
actor.at_0x2e                     u8, every actor (fielders, offense, umpires); actor +0x2e
camera.at_0x58 .at_0x5b .at_0x61 (3 x u16) .at_0x67     global camera object
ball.at_0x50 .at_0x52 (u16)  .at_0x44 .at_0x40 .at_0x4c (u32)   ball object
sim.at_0xe92 (u16) .at_0xea8 (u32)    the sim object
fielders.at_0x2a5 .at_0x2a9       u32, fielder object
offense.at_0x2b9 .at_0x2a9 .at_0x2ad .at_0x2b1   u32, batter/runner object
record.at_0x1d                    u16 (FUN_68078374)
pitch.at_0x3390 (u32) .at_0x3394 (u16)   (FUN_68047f66)
state.at_0x00                     u16 inning-state +0x00 (0xc020 or 0xc021 in the data)
snapshot.at_0x7e                  u32 object +0x7e (or +0x82 when +0x7e is 0) (FUN_6804d42d)
ball_flight.at_0xe70              u32 ball +0xe70
path.at_0xe78 .at_0xe7c .at_0xe80 .at_0xe84 .at_0xe88   u32 ball +0xe78.. (written with the flight path points)
```

## Output contract
```json
{"ball.at_0x44": {"name": "snake_case_name", "meaning": "one or two sentences: what it holds, its units/values",
                  "confidence": "high|medium|low",
                  "evidence": [{"function": "FUN_6804xxxx", "quote": "a line or expression copied from that function"}]},
 ...}
```
Rules the referee enforces:
- exactly the 29 keys above; `name` is snake_case, 3..40 characters, not a placeholder (no `at_`, `unk`, `unknown`,
  `field`, `var`, `tmp`, hex offsets or `0x`), and not equal to another key already in that struct (TAP_FORMAT.md's
  JSON keys) or to another new name in the same struct (an actor field counts in the fielder and offense structs);
- `meaning` at least 20 characters; `confidence` one of high, medium, low;
- 1..6 evidence items; each `quote` at least 15 characters and found verbatim (whitespace collapsed) in the body of
  the named BBSIM function; at least one quote per field must come from a function that USES the field (sets,
  tests or computes with it), not from the tape save/load routines (the writers listed in TAP_FORMAT.md and their
  membuf_read counterparts such as FUN_6802d82d, FUN_6805ddac, FUN_680156ca). Some offsets appear only in that
  save/load pair. For such a field, do not cite an unrelated line that touches a different offset: set
  `"code_use": "none"`, `"confidence": "low"`, quote the save/load lines, and base the meaning on the tape values
  (the meaning must say so, mentioning the tapes).

Honesty beats coverage: if the code only shows that a field is, say, a counter compared against 30, name it for that
(`frame_countdown`) and mark it low or medium. A separate reviewer reads every meaning against its quotes; names
that the quotes do not support fail the round.

## Referee
`python3 /home/will/bbpro98/re/targets/tapnameref.py /home/will/bbpro98/re/targets/tapnames $LANE`
prints `fields 29 ok N`, the problems, then PASS or FAIL. Add `--audit x` to see the table the reviewer reads.
Iterate until PASS. Keep scratch files in your lane; do not edit anything outside it.
