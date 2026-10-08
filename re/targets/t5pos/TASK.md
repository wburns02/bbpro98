# Task: exact replay model of FastSim FUN_6803853e (fielder positioning / defensive alignment)

Work only in `/home/will/bbpro98/re/targets/t5pos/lanes/code/`. Edit `positioning.py` there. Python 3 stdlib + `t3lib`
only, no file or network access at run time (the referee runs the module in a jail holding only positioning.py and
t3lib.py).

## Contract
`def replay(o, r)` re-executes FUN_6803853e for one recorded call and RETURNS a list of 7 ints: the u32 values the call
leaves in the global alignment object A (= 0x680c8f98) at A+0x09 (mode), A+0x0d (a slot of mode 0), A+0x11 (a slot of
mode 1), A+0x15 (b, mode 0), A+0x19 (b, mode 1), A+0x1d (c, mode 0), A+0x21 (c, mode 1). The referee compares them with
the recorded after-call bytes.

- `r` is a dict: `r['xf']` = bytes; `t3lib.i32(r['xf'], 0)` is `*(int *)(param_1 + 0x348e)` before the call (0 or 1).
  Other keys (obj, game, mflags, self, ...) are not needed.
- `o` is the oracle; every probed call must be made through it, in the function's call order:
  - `o.x(va, arg1=None)` for a probed getter: returns its recorded return value (unsigned 32-bit). Pass `arg1` for
    FUN_68056985 (3 or 4) and FUN_68019fba (0 or 1); the referee checks it against the recorded first argument.
  - `o.pb(i)` for every `FUN_68003170(i)` (a PlayBalance table read): returns the value. `o.pb(0x30)` etc.
  - `o.align(a, b, c)` for every `FUN_6801a4b1(&A, a, b, c)`: checks the arguments, returns None.
  - The four slot-shift calls FUN_6801a716 / FUN_6801a7e8 / FUN_6801a50e / FUN_6801a612 are probed getters too: call
    `o.x(0x6801a716)` etc. (ignore the value) AND apply their effect to your own copy of the slots.
  A record passes when replay made exactly the recorded calls (a wrong getter, order, argument or a missing call raises
  t3lib.Mismatch) AND returned the right 7 values.
- Helpers in t3lib: `t3lib.i32(b, off)`, `t3lib.u32(b, off)`, `t3lib.s16(b, off)`, `t3lib.s16v(v)`, `t3lib.s8(v)`.

## Which getter each call is (from the trace, Ghidra's names are wrong)
Ghidra shows `CSplitterWnd::IsTracking(this)` for three different probed getters. In call order:
- the one stored in `iVar10` (before the first FUN_68019fba) is **FUN_6802fd50**: `o.x(0x6802fd50)`;
- every `IsTracking(this)` compared with `FUN_68003170(0x30 / 0x31 / 0x32 / 0x33)` is **FUN_68038e90**;
- every `IsTracking(this)` compared with `FUN_68003170(0x34 / 0x35)` is **FUN_68038e70**.
Each comparison block calls the getter again before each PB read (the getter, then the PB, then the getter, then the
next PB). Calls the decompile shows that are not probed (none of the others below) produce no events.

Truncations: `bVar2..bVar5` are the low BYTE of the getter's return (`v & 0xff`, unsigned); `cVar6` is the low byte of
FUN_68039356's return (only compared with 0); `uVar7 & 0xff` for FUN_68038ed0; `sVar14 = (short)(bVar3 - bVar4)` with
bVar3/bVar4 the low bytes of FUN_68056985(3) and (4) (signed 16-bit result, can be negative). `iVar8` (FUN_68032ff0),
`iVar9` (FUN_6800f600) and `iVar10` (FUN_6802fd50) are full 32-bit values (signed: values >= 2**31 are
negative; only `== 0`, `!= 0`, `== 1` and the PB comparisons matter). The PB comparisons are signed int comparisons of
the getter value against the PB value. `bVar15 = (FUN_6800f640 != 0)`.
`-1 - (uint)bVar15 != (int)sVar14` compares as 32-bit ints: (-1 - bVar15) vs sVar14 (both small signed ints).
`(int)(short)(ushort)bVar4 + 1U < (uint)(int)(short)(ushort)bVar5` is `bVar4 + 1 < bVar5` (bytes, no sign issues).
Evaluation order: C `||` / `&&` short-circuit, so FUN_68038ed0 is called only when `cVar6 != 0` in that condition.

## The function (Ghidra decompile)
```c
void __fastcall FUN_6803853e(int param_1)
{
  bVar2 = FUN_6800f200(0x68143ee0);
  bVar3 = FUN_68056985(&DAT_68143ee0,3,(void *)0x0);
  bVar4 = FUN_68056985(&DAT_68143ee0,4,(void *)0x0);
  sVar14 = (ushort)bVar3 - (ushort)bVar4;
  bVar3 = FUN_68002c80(0x68143ee0);
  bVar4 = FUN_6800f1e0(0x68143ee0);
  bVar5 = FUN_6800f1c0(0x68143ee0);
  uVar7 = FUN_68039356(0x681147a0);
  cVar6 = (char)uVar7;
  iVar8 = FUN_68032ff0(0x680a57b7);
  iVar9 = FUN_6800f600(0x680a57b7);
  iVar10 = FUN_6800f640(0x680a57b7);
  this = DAT_680a5822;
  bVar15 = iVar10 != 0;
  iVar10 = CSplitterWnd::IsTracking(DAT_680a5822);          // FUN_6802fd50
  FUN_68019fba(&DAT_680c8f98,0);
  if ((((cVar6 == '\0') || (!bVar15)) || (sVar14 < -1)) || (1 < bVar3)) {
    if ((cVar6 == '\0') || (uVar7 = FUN_68038ed0(0x680a57b7), (uVar7 & 0xff) != 0)) {
      if ((iVar8 == 0) || (1 < bVar3)) FUN_6801a4b1(&DAT_680c8f98,0,2,2);
      else                             FUN_6801a4b1(&DAT_680c8f98,3,2,2);
    }
    else FUN_6801a4b1(&DAT_680c8f98,1,2,2);
  }
  else FUN_6801a4b1(&DAT_680c8f98,2,2,2);
  iVar11 = CSplitterWnd::IsTracking(this);                   // FUN_68038e90
  iVar12 = FUN_68003170(0x30);
  if (iVar11 < iVar12) {
    iVar11 = CSplitterWnd::IsTracking(this);                 // FUN_68038e90
    iVar12 = FUN_68003170(0x31);
    if (iVar11 <= iVar12) {
      if (iVar10 == 1) FUN_6801a716(0x680c8f98);
      else             FUN_6801a7e8(0x680c8f98);
    }
  }
  else if (iVar10 == 1) FUN_6801a7e8(0x680c8f98);
  else                  FUN_6801a716(0x680c8f98);
  bVar1 = false;
  FUN_68019fba(&DAT_680c8f98,1);
  if (((*(int *)(param_1 + 0x348e) == 0) && (8 < bVar2)) &&
     ((bVar15 && ((sVar14 == 0 && (bVar3 < 2)))))) {
    FUN_6801a4b1(&DAT_680c8f98,0,0,2);
  }
  else if ((cVar6 == '\0') || ((iVar9 == 0 || (-1 - (uint)bVar15 != (int)sVar14)))) {
    if ((cVar6 == '\0') ||
       ((iVar8 == 0 || ((-1 - (uint)bVar15) - (uint)(iVar9 != 0) != (int)sVar14)))) {
      FUN_6801a4b1(&DAT_680c8f98,0,2,2);
      iVar8 = CSplitterWnd::IsTracking(this);                // FUN_68038e70
      iVar9 = FUN_68003170(0x35);
      if (iVar9 < iVar8) {
        iVar8 = CSplitterWnd::IsTracking(this);              // FUN_68038e70
        iVar9 = FUN_68003170(0x34);
        if (iVar9 <= iVar8) FUN_6801a50e(0x680c8f98);
      }
      else FUN_6801a612(0x680c8f98);
      bVar1 = true;
    }
    else {
      FUN_6801a4b1(&DAT_680c8f98,0,3,2);
      iVar8 = CSplitterWnd::IsTracking(this);                // FUN_68038e70
      iVar9 = FUN_68003170(0x35);
      if (iVar8 <= iVar9) FUN_6801a612(0x680c8f98);
      bVar1 = true;
    }
  }
  else FUN_6801a4b1(&DAT_680c8f98,0,1,2);
  iVar8 = CSplitterWnd::IsTracking(this);                    // FUN_68038e90
  iVar9 = FUN_68003170(0x30);
  if (iVar8 < iVar9) {
    iVar8 = CSplitterWnd::IsTracking(this);                  // FUN_68038e90
    iVar9 = FUN_68003170(0x31);
    if (iVar8 <= iVar9) {
      if (iVar10 == 1) FUN_6801a716(0x680c8f98);
      else             FUN_6801a7e8(0x680c8f98);
    }
  }
  else if (iVar10 == 1) FUN_6801a7e8(0x680c8f98);
  else                  FUN_6801a716(0x680c8f98);
  if (bVar1) {
    iVar8 = CSplitterWnd::IsTracking(this);                  // FUN_68038e90
    iVar9 = FUN_68003170(0x32);
    if (iVar8 < iVar9) {
      iVar8 = CSplitterWnd::IsTracking(this);                // FUN_68038e90
      iVar9 = FUN_68003170(0x33);
      if (iVar8 <= iVar9) {
        if (iVar10 == 1) FUN_6801a716(0x680c8f98);
        else             FUN_6801a7e8(0x680c8f98);
      }
    }
    else if (iVar10 == 1) FUN_6801a7e8(0x680c8f98);
    else                  FUN_6801a716(0x680c8f98);
    if ((int)(short)(ushort)bVar4 + 1U < (uint)(int)(short)(ushort)bVar5) FUN_6801a50e(0x680c8f98);
    else if ((int)(short)(ushort)bVar5 + 1U < (uint)(int)(short)(ushort)bVar4) FUN_6801a612(0x680c8f98);
  }
  uVar13 = FUN_68038dd0((int)this);                          // probed: o.x(0x68038dd0), last event
  *(undefined4 *)(param_1 + 0x355c) = uVar13;
}
```

## The alignment object A (what the 7 return values are)
`mode` = int at A+9. Slots: a[g] at A+0x0d+4g, b[g] at A+0x15+4g, c[g] at A+0x1d+4g (g = mode, only 0 and 1 here).
- `FUN_68019fba(&A, m)`: mode = m (and A+0x25 = 0xffff).
- `FUN_6801a4b1(&A, a, b, c)`: a[mode] = a, b[mode] = b, c[mode] = c.
- `FUN_6801a716`: if c[mode] > 0: c[mode] -= 1.      `FUN_6801a7e8`: if c[mode] < 4: c[mode] += 1.
- `FUN_6801a50e`: if b[mode] < 3: b[mode] += 1.      `FUN_6801a612`: if b[mode] > 0: b[mode] -= 1.
(Their mode-3 branches never run here.) Every path sets all of mode 0's and mode 1's slots before shifting them, so
the starting contents of A do not matter. Return `[mode, a[0], a[1], b[0], b[1], c[0], c[1]]` (mode is 1 at the end).

## Sample record (top-level events, in order)
```
X[6800f200]=1746157063  X[68056985](arg1=3)=1746157313  X[68056985](arg1=4)=1746157059  X[68002c80]=1746157057
X[6800f1e0]=1746157058  X[6800f1c0]=1746157056  X[68039356]=-255  X[68032ff0]=2028952  X[6800f600]=0  X[6800f640]=0
X[6802fd50]=1  X[68019fba](arg1=0)  X[68038ed0]=1  align(3,2,2)  X[68038e90]=55 PB[48]=80  X[68038e90]=55 PB[49]=19
X[68019fba](arg1=1)  align(0,2,2)  X[68038e70]=55 PB[53]=20  X[68038e70]=55 PB[52]=85  X[68038e90]=55 PB[48]=80
X[68038e90]=55 PB[49]=19  X[68038e90]=55 PB[50]=60  X[68038e90]=55 PB[51]=39  X[6801a612]  X[68038dd0]=1508
after: mode 1, a = [3, 0], b = [2, 1], c = [2, 2]
```
(bVar15 = 0 here because FUN_6800f640 returned 0, so the first test takes the outer branch and FUN_68038ed0 is called.)

## Referee
`python3 /home/will/bbpro98/re/targets/t3ref.py /home/will/bbpro98/re/targets/t5pos /home/will/bbpro98/re/targets/t5pos/lanes/code -v`
prints `records 6619 ok N`, the first failing records with the reason, then PASS or FAIL. Dev records (read-only, to
inspect): `/mnt/nvme/bbpro98/targets_data/t5pos/records.jsonl` (JSON lines; xf/post hex; ev = list of
[type, gen, idx, a, b, r, va]; an 'L' event is align with a = a, b = b, idx = c). Use `t3lib.top_level(rec)` to see the
events the oracle serves. Do NOT use --holdout and do not read any other targets_* path. Iterate until PASS. Do not edit
t3ref.py, t3run.py, t3lib.py or anything outside the lane dir.

## Done
Report: the final referee line, and a 3-line summary of anything surprising.
