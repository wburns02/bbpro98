# FUN_6805ecfd (short __thiscall FUN_6805ecfd(void *this,uint param_1,int *param_2))

DRAFT (GLM-Flash, unaudited)

# FUN_6805ecfd — FastSim_FTHROW

## 1) PURPOSE
For one fielder (`this`) and one runner index, choose and score the best out-attempt option (step on bag / tag / chase / throw), decide whether the attempt is worth committing to, and return a composite action/confidence code while filling a play-output struct.

## 2) INPUTS
- `this` (fielder object). Fields used: `+0x08` (position, passed to distance fn), `+100` (int state; `==5` is special-cased), `+0x2ad` (uint, compared to runner index — guess: this fielder's coverage assignment).
- `param_1` (uint): runner/base index (0–3 inferred; 0 gets special handling — guess: batter-runner/lead runner).
- `param_2` (int*): output struct, initialized by `FUN_6805d8d5`:
  - `+0`: chosen play id (0=step on bag, 1=tag, 2=chase, 3=throw — ids inferred from PB names)
  - `+4`: flags field, written via `FUN_68002c40` (values 2 and 4)
  - `+6`: `param_1` (stored)
  - `+0xa`: target object (from table `DAT_68143e28` via `FUN_6804ec35`/`FUN_6804f19e`/`FUN_6804f214`); zeroed if no play
  - `+0xe`: throw-target object (from table `0x680d26b0` via `FUN_6805f79b`)
- Runner position/data: `local_8 = FUN_6800a3a6(param_1)` (short*).
- Globals read: byte at `0x68143ee0` (read twice; guess: out count), `FUN_68039356(0x681147a0)` (bool, unknown meaning).

## 3) RULES
**Setup**
1. Init `param_2`; store `param_1` at `+6`; `target = FUN_6804ec35(DAT_68143e28, param_1)` → `param_2+0xa`; result code `local_c = 0`.

**Branch A — `target == 0` (no target object)**
2. Only if `this+0x2ad == param_1`: set play id = 2, set flag 4 (`FUN_68002c40(param_2+1, 4)`).
3. If `param_1 > 0`: `param_2+0xa = FUN_6804f19e(DAT_68143e28, param_1-1)`. If nonzero, `FUN_6804aee0(obj)&0xff`, helper-pair test `F(obj) < F(obj)` (see UNCERTAIN), and `FUN_68002bb0(runnerPos, obj+0xc) < 0x708` (1800): return **99**.
4. Else if no 99 yet and `param_1 < 3`: repeat with `FUN_6804f214(DAT_68143e28, param_1)` (next base) and same tests → return **99**.
5. Otherwise return `local_c` (0). Note `param_2+0xa` may be left pointing at the adjacent object even when returning 99.

**Branch B — `target != 0`**
6. `throwTarget = FUN_6805f79b(0x680d26b0, param_1)` → `param_2+0xe`; `d = FUN_68003988(target+8, runnerPos)`; set costs `cost[0..3] = 9999`.
7. Option 0 (step on bag): if `FUN_6804b1b5(target, param_1)` (guess: runner is forced): `cost[0] = (short)FUN_68003988(this+8, runnerPos) + PB[stepOnBagSlop]`.
8. Option 1 (tag): otherwise: `cost[1] = (short)FUN_68003988(this+8, runnerPos) + PB[tagAtBagSlop]`. (Exactly one of 0/1 is set.)
9. Option 2 (chase): if `FUN_68016fd0(target, 0)`: `cost[2] = (short)FUN_6805c56e(this, target)`.
10. Option 3 (throw): if `throwTarget != this`: `cost[3] = FUN_68005b50(FUN_6805dab6(this, runnerPos), (short)FUN_68003988(throwTarget+8, runnerPos) + PB[throwToBagSlop])`. Then if `param_1 == 0` AND `property(this) == 0` (Ghidra: `CControlBar::GetBarStyle`; see UNCERTAIN) AND `FUN_68002ef0(throwTarget)`: `cost[3] += PB[firstToPitcherSlop]`.
11. Selection: for `i = 3` down to `0`: `score = (short)d - cost[i]`; if `score >= best` (best starts at 0), set play id = `i`, `margin = score`. Scanning downward with `<=`, so **ties favor the lowest index**; options scoring < 0 are never chosen (play id keeps its initialized value; margin stays 0).
12. Commit gate — commit iff `[ this+100 == 5 AND (play==1 OR play==2) ]` OR `margin >= PB[possibleOutFrames]`. If not committed: `param_2+0xa = 0`; return 0.
13. If committed:
    - `local_c += 1`.
    - If `FUN_6804b1b5(target, param_1)` (forced): set flag 2 (`FUN_68002c40(param_2+1, 2)`); `local_c += 2`. Let `s = byte[0x68143ee0]`. If `s == 2`, or (`s == 1` AND `FUN_68039356(0x681147a0) == 0`): `likely = (margin >= PB[likelyOutFrames])`; if play==0: `local_c += likely ? 4 : 2`; if play==3: `local_c += likely ? 3 : 1`; if `param_1 == 0` AND likely: `local_c += 1`.
    - Re-read `s = byte[0x68143ee0]`; if `s < 2`: if `FUN_6804b130(target)` and `FUN_68017010(target) == 3`: `local_c += 1`; if `FUN_6804b0fc(target)`: `local_c += 1`.
    - Global `DAT_681785f8` (16-bit) `= FUN_680190e0(margin - 500, 1000)`.

## 4) OUTPUT / SIDE EFFECTS
- Returns short: **0** = no play; **99** = stand down (adjacent fielder within 1800 of runner, branch A only); otherwise the sum of increments above (committed=+1, forced=+2, play-0 confidence +4/+2, play-3 confidence +3/+1, +1 if `param_1==0` & likely, +1/+1 from the two `s<2` target checks).
- `param_2` written: play id (`+0`), flags 2 and/or 4 (`+4`), runner index (`+6`), target object or 0 (`+0xa`), throw target (`+0xe`).
- Global `DAT_681785f8` written only on the commit path.
- All cost/margin arithmetic is 16-bit (shorts).

## 5) UNCERTAIN
- Several helpers are Ghidra-mislabeled as MFC (`CSplitterWnd::IsTracking`, `CControlBar::GetBarStyle`); real semantics unknown. In rule 3 the **same-named** helper is called twice and compared `second < first` — either a stateful function or two distinct functions collapsed by Ghidra; not resolvable from this listing.
- `FUN_68003988` (distance vs. time-in-frames), `FUN_68005b50` (how throw value and runner cost combine — max/difference/other), `FUN_6805dab6`, `FUN_6805c56e`, `FUN_680190e0` (clamp? scale? args `margin-500`, `1000`).
- Play-id names (0/1/2/3), flag-bit meanings (2, 4), and the meaning of each return-code increment are inferred from PB names and structure, not confirmed.
- `byte[0x68143ee0]` guessed to be the out count (only values 0–2 are distinguished); `FUN_68039356(0x681147a0)` unknown.
- Whether `param_1` is a runner index or base index; meaning of `this+0x2ad`, `this+100 == 5`, and `target+8` vs `obj+0xc` position fields.
- Predicates `FUN_6804b1b5` (forced?), `FUN_6804b130`, `FUN_68017010==3`, `FUN_6804b0fc`, `FUN_68002ef0`, `FUN_6804aee0` — inferred from call shape only.
- Downstream use of `DAT_681785f8` and of the returned code.
- Behavior on short overflow for large distances is not modeled.
