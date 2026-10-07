# FUN_6800e5db (void __fastcall FUN_6800e5db(int param_1))

DRAFT (GLM-Flash, unaudited)

## 6800e5db — Compute "adjust units" value

**PURPOSE**
Computes a swing-type-adjusted value from a rating field and stores it at struct offset 0x129, then reduces it by the shortfall between two externally-sourced values and clamps at zero.

**INPUTS**
- `param_1`: pointer to a batter/at-bat struct (guess).
- `param_1+0x95`: rating scaled in step 1; likely contact-hitting (CH) rating (guess, from `adjustUnitsCHPct` name).
- `param_1+0xbd`: swing/attempt type selector: 0=power, 1=normal, 2=contact, 3=bunt (mapping inferred from PB names; guess).
- `param_1+0x70`: pointer to another object (guess: player or context struct).
- field at `(*(param_1+0x70))+0x29e`: read via `FUN_6803e0d5`; meaning unknown.
- global `DAT_680a224c`: argument to the call Ghidra labels `CSplitterWnd::IsTracking` (likely a mislabel; see UNCERTAIN).

**RULES**
1. `result = FUN_68005b80(*(param_1+0x95), PB[adjustUnitsCHPct])` (default 40); store at `param_1+0x129`. `FUN_68005b80` is presumably a percent helper (`value * pct / 100`) — inferred, not verified.
2. Scale `result` again by the type percentage, selected by `*(param_1+0xbd)`:
   - 0 → `PB[adjustUnitsPowerPct]` (20)
   - 1 → `PB[adjustUnitsNormalPct]` (100)
   - 2 → `PB[adjustUnitsContactPct]` (70)
   - 3 → `PB[adjustUnitsBuntPct]` (500)
3. Add the flat type adjustment, same selector:
   - 0 → `PB[adjustUnitsPowerAdjust]` (0)
   - 1 → `PB[adjustUnitsNormalAdjust]` (0)
   - 2 → `PB[adjustUnitsContactAdjust]` (0)
   - 3 → `PB[adjustUnitsBuntAdjust]` (999)
Let `A` = return value of the `IsTracking`-labeled call on `DAT_680a224c`; let `B` = `FUN_6803e0d5((*(param_1+0x70)) + 0x29e)` (decompile: `FUN_6803e0d5(*(int *)(param_1 + 0x70) + 0x29e)` — the pointer at `param_1+0x70` is dereferenced, then `0x29e` is added; no `&`). If `B < A`: `result -= (A - B)`. This subtraction applies regardless of swing type.
5. If `result < 0`, set `result = 0`. There is no upper clamp.
6. If `*(param_1+0xbd)` is not 0–3, steps 2–3 are skipped entirely (only the CH scaling in step 1 applies).

**OUTPUT / SIDE EFFECTS**
Writes `param_1+0x129`. No other fields modified; no return value.

**UNCERTAIN**
- Behavior of `FUN_68005b80` (assumed percentage multiply; could include rounding or clamping).
- Meaning of fields `+0x95`, `+0xbd`, `+0x70`, and `+0x29e`; the 0–3 type mapping is inferred from parameter names only.
- The call Ghidra resolved as `CSplitterWnd::IsTracking(DAT_680a224c)` is suspicious in a fast-sim module; its true target and the meaning of its return value (used as a benchmark/cap in rule 4) are unknown.
- Whether `FUN_6803e0d5` is a pure getter or has side effects.
- Caller context (`6800b36e`) not examined; purpose of the stored value at `+0x129` unknown.


CORRECTIONS (audit pass 2, GLM-Flash vs decompile; findings verified shaped, apply when editing):
- Rule 4 (argument to FUN_6803e0d5): draft writes `FUN_6803e0d5(&(*(param_1+0x70))+0x29e)`, i.e. address of the pointer field plus 0x29e, but the decompile passes the dereferenced pointer plus the offset: `iVar2 = FUN_6803e0d5(*(int *)(param_1 + 0x70) + 0x29e);` — the argument is `(*(param_1+0x70)) + 0x29e`, not `(param_1+0x70) + 0x29e`. (The draft's INPUTS section states the correct form; the `&` in rule 4 is the error.)

CORRECTIONS HISTORY (audit pass 2 findings; rules above were rewritten accordingly):
- Rule 4 (argument to FUN_6803e0d5): draft writes `FUN_6803e0d5(&(*(param_1+0x70))+0x29e)`, i.e. address of the pointer field plus 0x29e, but the decompile passes the dereferenced pointer plus the offset: `iVar2 = FUN_6803e0d5(*(int *)(param_1 + 0x70) + 0x29e);` — the argument is `(*(param_1+0x70)) + 0x29e`, not `(param_1+0x70) + 0x29e`. (The draft's INPUTS section states the correct form; the `&` in rule 4 is the error.)
