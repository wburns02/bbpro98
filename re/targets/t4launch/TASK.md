# Task: exact replay model of FastSim FUN_6803b82c (ball launch velocity)

Work only in `/home/will/bbpro98/re/targets/t4launch/lanes/code/`. Edit `launch.py` there (it already holds the
DLL table `TAB`; do not change TAB). Python 3 stdlib + `t3lib` only, no file or network access at run time (the referee
runs the module in a jail holding only launch.py and t3lib.py).

## Contract
`def replay(o, r)` re-executes FUN_6803b82c for one recorded call and RETURNS the function's int return value
(`local_c` below, a signed 32-bit int; the referee compares the low 32 bits with the recorded eax).

- `r` is a dict: `r['obj']` = bytes, the first 0x100 bytes of `*param_1` (the ball object) BEFORE the call;
  `r['self']` = the param_1 pointer (int). Other keys (game, mflags, xf, rm0, ri0, i, fn, depth, over, arg) are
  irrelevant here.
- `o` is the oracle. `o.x(va, arg1=None)` must be called for every probed getter, in call order, and returns its
  recorded return value (unsigned 32-bit). When you pass `arg1`, the referee checks it equals the recorded first stack
  argument (compare as unsigned 32-bit: pass `v & 0xffffffff`). A wrong getter, order or arg1 fails the record.
  The record passes when replay consumed all of the record's events AND returned the right value.
- Helpers in t3lib: `t3lib.s16(b, off)`, `t3lib.i32(b, off)`, `t3lib.u32(b, off)`, `t3lib.s16v(v)` (wrap to signed 16),
  `t3lib.cdiv(a, b)` (C division, truncates toward zero), `t3lib.s8(v)`.

Every record has exactly these five probed calls, in this order (the probes of FUN_68005ec0, FUN_6803a5cd,
FUN_68014b50, FUN_6807c661, FUN_68014b50; other callees are not probed, so they produce no events and you compute
them yourself):
```
X[68005ec0](ecx=P+0xc, arg1=48)          FUN_68005ec0(param_1 + 6, 0x30)
X[6803a5cd](ecx=P)                       FUN_6803a5cd(param_1)
X[68014b50](ecx=P+0x10, arg1=P+0x1c)     FUN_68014b50(param_1 + 8, param_1 + 0xe)
X[6807c661](ecx=P+0x28, arg1=local_c, arg2=heading)   FUN_6807c661(param_1 + 0x14, local_c, param_1[5])
X[68014b50](ecx=P+0x34, arg1=<stack address>)         FUN_68014b50(param_1 + 0x1a, puVar2)
```
So call: `o.x(0x68005ec0, 0x30)`, `o.x(0x6803a5cd)`, `o.x(0x68014b50, (r['self'] + 0x1c) & 0xffffffff)`,
`o.x(0x6807c661, local_c & 0xffffffff)`, `o.x(0x68014b50)` (no arg1 for the last: it is a stack address).
Sample record (record 858): obj starts `ffff1e006a00a45e48cab049...`, events: 68005ec0 arg1=48; 6803a5cd;
68014b50 arg1=1745483057 (= self 1745483029 + 0x1c); 6807c661 arg1=6336 arg2=51632; 68014b50 arg1=5700572.
Recorded return 6336.

## The function (Ghidra decompile; param_1 is `short *`, so param_1[k] is the s16 at byte offset 2k)
```c
int __fastcall FUN_6803b82c(short *param_1)
{
  FUN_68005ec0(param_1 + 6,0x30);
  FUN_6803a5cd(param_1);
  FUN_68014b50(param_1 + 8,(undefined4 *)(param_1 + 0xe));
  param_1[0x28] = 0;
  uVar1 = FUN_6807cb88(param_1[3]);
  local_c = FUN_6803bd80((int)param_1[0x2b],(short)uVar1);
  uVar1 = FUN_6807cbbe(param_1[3]);
  local_8 = FUN_6803bd80((int)param_1[0x2b],(short)uVar1);
  if (local_c < 0) {
    local_c = -local_c;
    param_1[5] = param_1[5] + -0x8000;
  }
  FUN_6807c661(param_1 + 0x14,local_c,param_1[5]);
  *(undefined4 *)(param_1 + 0x18) = local_8;
  puVar2 = FUN_68011090(local_18,0,0,0xffffffbb);
  FUN_68014b50(param_1 + 0x1a,puVar2);
  ...  (writes param_1[0x29], param_1[0x2a]; no more probed calls)
  return local_c;
}
```
None of the calls before the cb88 line change param_1[3] (byte offset 6) or param_1[0x2b] (byte offset 0x56), so read
both from r['obj']. The value passed to FUN_6807c661 as arg2 is param_1[5] after the possible -0x8000 (not checked by
the oracle, only arg1 is).

Callees you compute (not probed):
```c
void FUN_6803bd80(int param_1,short param_2) { FUN_6807d2f6(param_1,(int)param_2,0x4000); }   // returns that value

uint FUN_6807d2f6(int param_1,int param_2,int param_3) {
  ulonglong uVar1 = (longlong)param_1 * (longlong)param_2;
  if (param_3 == 0) { ... }                       // never 0 here
  else uVar2 = (uint)((longlong)uVar1 / (longlong)param_3);   // signed 64-bit C division (truncates toward zero), low 32 bits
  return uVar2;
}

uint FUN_6807cb88(short param_1) {           // cosine of a 16-bit angle, table scaled to 16384
  uVar1 = ((int)param_1 >> 4) + (uint)(((int)param_1 >> 3 & 1U) != 0);
  uVar3 = (int)uVar1 >> 0x1f;
  iVar2 = (uVar1 ^ uVar3) - uVar3;                    // abs
  if (iVar2 < 0x400) uVar1 = (uint)*(ushort *)(&DAT_6809de80 + iVar2 * 2);        // TAB[iVar2]
  else               uVar1 = -(uint)*(ushort *)(&DAT_6809de80 + (0x800 - iVar2) * 2);  // -TAB[0x800 - iVar2]
  return uVar1;
}

uint FUN_6807cbbe(short param_1) {           // the same with (short)(param_1 - 0x4000) in place of param_1
  ...
}
```
Note `(short)uVar1` in the caller: the cosine result is truncated to signed 16 bits before FUN_6803bd80. Python's `>>`
on negative ints is arithmetic like C's, good. Mind every C cast (short / int / uint) exactly.

## Referee
`python3 /home/will/bbpro98/re/targets/t3ref.py /home/will/bbpro98/re/targets/t4launch /home/will/bbpro98/re/targets/t4launch/lanes/code -v`
prints `records 3969 ok N` and the first failing records with the reason, then PASS or FAIL. Dev records (to inspect,
read-only): `/mnt/nvme/bbpro98/targets_data/t4launch/records.jsonl` (JSON lines; obj/game/... hex; ev = list of
[type, gen, idx, a, b, r, va]; 'ret' = recorded eax). Do NOT use --holdout and do not read any other targets_* path.
Iterate until PASS. Do not edit t3ref.py, t3run.py, t3lib.py or anything outside the lane dir.

## Done
Report: the final referee line, and a 3-line summary of anything surprising (e.g. a cast that mattered).
