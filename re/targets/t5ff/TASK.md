# Task: exact replay model of FastSim FUN_68022ea4 (which fielder goes for the ball)

Work only in `/home/will/bbpro98/re/targets/t5ff/lanes/code/`. Edit `find_fielder.py` there. Python 3 stdlib + `t3lib`
only, no file or network access at run time (the referee runs the module in a jail holding only find_fielder.py and
t3lib.py).

## Contract
`def replay(o, r)` re-executes FUN_68022ea4 for one recorded call and RETURNS its int return value (a fielder object
pointer, compared as the low 32 bits of the recorded eax).

- `r` is a dict: `r['obj']` = bytes, the first 0x100 bytes of `*param_1` before the call. The 9 fielder pointers are
  `t3lib.u32(r['obj'], 0xb + 4 * k)` for k = 0..8. Other keys are not needed.
- `o` is the oracle; every probed call must be made through it, in the function's call order:
  - `o.x(va)` for a probed getter: returns its recorded return value (unsigned 32-bit). Do not pass arg1 (the recorded
    arguments are stack addresses you cannot know).
  - `o.x2(0x6803997d)` for the flight-path step FUN_6803997d: returns `(value, z)` where z is the s16 at offset 4 of
    the iterator AFTER the step (Ghidra's `local_e94`), logged by the trace in the event's idx field.
  A record passes when replay made exactly the recorded calls (a wrong getter, order or a missing / extra call raises
  t3lib.Mismatch) AND returned the right pointer.
- Helpers in t3lib: `t3lib.u32(b, off)`, `t3lib.i32(b, off)`, `t3lib.s16v(v)` (wrap to signed 16), `t3lib.s8(v)`.

## Probed calls (each one is an `o.x` / `o.x2` call; nothing else in the function produces events)
FUN_68039645 (iterator init), FUN_6803997d (step, use o.x2), FUN_68002e30 (path ended?), FUN_68023be0 (point not
reachable?), FUN_68003988 (fielder's time to the point), FUN_68021fca (fielder's reaction delay), FUN_6802644a (the
fallback: nearest fielder when the path runs out; its return is the function's return).

Truncations: `bool` and `(uVar3 & 0xff)` mean the low BYTE of the returned value (`v & 0xff`, nonzero = true).
`(short)uVar3 + sVar2` with sVar2 = `(short)` of FUN_68021fca's value: compute `t3lib.s16v(t3lib.s16v(d) + t3lib.s16v(s))`.
`local_8` and `local_ea4` are shorts; `local_e94` (z) is a short, so `0xe0 < local_e94` is a signed compare.
C `||` short-circuits: FUN_68002e30 is called only when the step returned true.

## The function (Ghidra decompile)
```c
int __fastcall FUN_68022ea4(void *param_1)
{
  local_e9c = 0;
  FUN_68039645(local_e98,&DAT_6809f515);
  local_8 = 0;
  do {
    do {
      bVar1 = FUN_6803997d(local_e98);
      if ((!bVar1) || (uVar3 = FUN_68002e30((int)local_e98), (uVar3 & 0xff) != 0)) {
        iVar4 = FUN_6802644a(param_1,local_e98,0);
        return iVar4;
      }
      local_8 = local_8 + 1;
      bVar1 = FUN_68023be0((int)local_e98);
    } while ((bVar1) || (0xe0 < local_e94));
    local_ea4 = 0;
    for (local_ea0 = 0; local_ea0 < 9; local_ea0 = local_ea0 + 1) {
      iVar4 = *(int *)((int)param_1 + local_ea0 * 4 + 0xb);
      uVar3 = FUN_68003988((void *)(iVar4 + 8),local_e98);
      sVar2 = FUN_68021fca(iVar4);
      sVar2 = (short)uVar3 + sVar2;
      if ((sVar2 < local_8) && ((local_e9c == 0 || (sVar2 < local_ea4)))) {
        local_ea4 = sVar2;
        local_e9c = iVar4;
      }
    }
  } while (local_e9c == 0);
  return local_e9c;
}
```

## Sample (start of one record's events)
```
X[68039645]=2030896  X[6803997d]=1 z=254  X[68002e30]=5696512  X[68023be0]=5696513
X[6803997d]=1 z=218  X[68002e30]=5696512  X[68023be0]=5696513   ... (68023be0 low byte 1: keep stepping)
... X[6803997d]=1 z=28  X[68002e30]=5696512  X[68023be0]=5696512 (low byte 0, z <= 0xe0: score the 9 fielders)
X[68003988]=.. X[68021fca]=9  (x9, fielders in obj order) ...
```

## Referee
`python3 /home/will/bbpro98/re/targets/t3ref.py /home/will/bbpro98/re/targets/t5ff /home/will/bbpro98/re/targets/t5ff/lanes/code -v`
prints `records 254 ok N`, the first failing records with the reason, then PASS or FAIL. Dev records (read-only, to
inspect): `/mnt/nvme/bbpro98/targets_data/t5ff/records.jsonl` (JSON lines; obj hex; ev = list of
[type, gen, idx, a, b, r, va]; 'ret' = recorded eax). Use `t3lib.top_level(rec)` to see the events the oracle serves.
Do NOT use --holdout and do not read any other targets_* path. Iterate until PASS. Do not edit t3ref.py, t3run.py,
t3lib.py or anything outside the lane dir.

## Done
Report: the final referee line, and a 3-line summary of anything surprising.
