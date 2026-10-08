# progress (lane code, runner_ai FUN_6804faa1)

## Round 1
- Wrote runner_ai.py from the decompile. Referee (advisory): `records 2500 ok 2500 | deep 173 ok 173` PASS.
- Key facts learned:
  - Truthiness of every flag getter is the LOW BYTE only (`uVar & 0xff`): 680030c0 returns 0x100 for flag 0x100 -> falsy.
  - Ghidra's "CMiniDockFrameWnd::OnClose(&DAT_680a2158)" = 6800f8f0 (probed, makes calls -> span); the 2nd OnClose(local_10)
    = 68050b00 = 680030c0(arg 4). IsTracking(local_10) = unprobed 68050ae0 (+0x93), 68050b30 (+0xdb) or probed 6800f780.
  - FUN_6802a8b7 (anim advance) runs right after the state read (events 680030c0(0x100), 680030c0(4)...), FUN_6802a6b1
    (anim start) = X(68002c40, flags) then X(680030c0, 1) after the X(68002ce0, 0) for its point argument.
  - Dev data never reaches flags!=0 on the AI word, [0x7e]==3, or an animation in progress: those paths are modeled from the
    decompile only (untested by dev).
- Assumptions in untested paths (holdout risk):
  1. Which IsTracking is probed: guessed `6800f780` is the divisor z of `400/z` and the `==0` guard (S2/S3), 68050ae0 = the
     `>>4` term, 68050b30 = the term compared to byte +0x86 / subtracted. 68050b30's value is not observable, so `T != [0x86]`
     is assumed true.
  2. Anim table frame count (first word of table entry at 0x680d3f28+id*8) is loaded at run time (not in record): forward play
     is assumed never on its last frame (`frame < count-1` true).
  3. Dedupe of identical consecutive X events is handled by the oracle.
