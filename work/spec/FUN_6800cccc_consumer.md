# FUN_6800cccc consumer of init-loaded PB globals

DRAFT (GLM-Flash, unaudited)

## FUN_6800cccc — Spec

### 1) PURPOSE
Picks one of 8 "type" indices by weighted random draw from a blend of two count distributions read from a team/stat block, with hardcoded bonuses/penalties and two tunable adjustments, and stores the winner into the caller's struct (likely a pitch/"look" type choice — guess).

### 2) INPUTS
- `param_1` — caller struct; result index written to `*(int*)(param_1 + 0xe5)`.
- Global object `0x68143ee0`:
  - `FUN_680076c0(obj)` → bool selecting one of two 0x173be-byte data blocks via `FUN_68041d83(&DAT_68114ba8 + bool*0x173be)` (guess: home/away or league/team).
  - `FUN_6800f1c0(obj)` → byte → row index into PB tables (guess: small count 0–2).
  - `FUN_6800f1e0(obj)` → byte → column index into PB tables (guess: small count 0–2).
- `DAT_680a224c` object: three calls to the function Ghidra typed as `CSplitterWnd::IsTracking` (signature reuse; real semantics unknown). Return used as loop bound (`local_28`) and as index (`local_58`, `iVar4` — same call, presumably same value).
- Selected data block `puVar3`:
  - table at `+0x6b0`: `FUN_6803e2b9(tbl, idx)` returns int* → base count (array A).
  - table at `+0x29e`: `FUN_6803e004(tbl, idx)` returns int (array B); `FUN_6803e04e(tbl, idx)` returns a second int (meaning unknown).
- RNG: `FUN_68082999(&DAT_680a2128, n)` — assumed uniform in [0, n).

### 3) RULES
1. Zero-init two 8-int arrays: A = `local_48`, B = `local_78`.
2. For i = 0 .. N−1 (N = first getter call's return): `idx = FUN_6800f6c0(obj, i)`;
   - `A[idx] = *(int*)FUN_6803e2b9(puVar3+0x6b0, idx)`
   - `B[idx] = FUN_6803e004(puVar3+0x29e, idx)`
   - if `B[idx] == 0`: `A[idx] -= 25` (0x19); and if `FUN_6803e04e(puVar3+0x29e, idx) > 0`: `A[idx] -= 25` again (total −50).
3. `A[cur] += 50` (0x32), where `cur` = second getter call's return.
`row = FUN_6800f1c0()`, `col = FUN_6800f1e0()`; then two direct reads of two distinct globals (no `FUN_68003170` call exists in FUN_6800cccc; the INPUTS "row/col index into PB tables" framing is withdrawn):
   - `A[iVar4] += *(int *)(&DAT_6808cf28 + col*4 + row*0xc)`
   - `A[local_58] += *(int *)(&DAT_6808cef8 + col*4 + row*0xc)`
   Bases `DAT_6808cf28` and `DAT_6808cef8` are 0xd0 apart and neither is the PlayBalance base `DAT_6808fde0`; the added value varies with `row`/`col` (table lookup, not a fixed PB scalar), so no lookBestType00CountAdjust (547) / lookPrimaryType00CountAdjust (535) attribution and no shared "PBG" source.
Build weights W = `aiStack_24` (never memset/zero-initialized in the function; only written entries are defined):
   - `sumA == 0 && sumB == 0`: only `aiStack_24[local_58] = 1` is assigned (`W[cur] = 1`); the other 7 entries are uninitialized stack, not 0 — this garbage flows into `total` (rule 7) and the RNG walk (rule 9).
   - `sumA == 0`: `W[i] = B[i]` for all i.
   - `sumB == 0`: `W[i] = A[i]` for all i.
   - otherwise: `W[i] = (A[i]*sumB + B[i]*sumA) * 100 / (sumB * sumA)` (integer division). Mathematically `100*(A[i]/sumA + B[i]/sumB)`; total ≈ 200 when both nonzero.
   - otherwise: `W[i] = (A[i]*sumB + B[i]*sumA) * 100 / (sumB * sumA)` (integer division). Mathematically `100*(A[i]/sumA + B[i]/sumB)`; total ≈ 200 when both nonzero.
7. `total = ΣW[0..7]`.
8. If `total == 0`: result = `cur`.
9. Else: `r = FUN_68082999(&DAT_680a2128, total)`; walk i = 0..7 subtracting `W[i]` from r; first i where `r − W[i] < 0` wins.
10. Store winner at `*(int*)(param_1 + 0xe5)`.

### 4) OUTPUT / SIDE EFFECTS
- Writes selected index (0–7) to `*(int*)(param_1 + 0xe5)`.
- Consumes one RNG draw (unless total == 0).
- No other writes visible.

### 5) UNCERTAIN
- Real identity/semantics of the three "IsTracking" calls (Ghidra MFC signature reuse); whether all three return the same value; whether it's a count or current index (used as both loop bound and array index).
- What the 8 categories represent (pitch types / look types — guess only).
- Meaning of the `+0x6b0` vs `+0x29e` tables and the `FUN_6803e2b9` / `FUN_6803e004` / `FUN_6803e04e` accessor distinction.
- What the bool from `FUN_680076c0` selects (two 0x173be-byte blocks).
- What `FUN_6800f1c0` / `FUN_6800f1e0` return (assumed 0–2 counts).
- PB table dimensions (3×3 inferred from strides 4 and 0xc only).
- No clamping: penalties (rule 2) can drive A negative; behavior with negative `sumA`/`sumB` (negative divisor in rule 6) not guarded.
- RNG range of `FUN_68082999` (assumed [0, total)); if it can return `total`, the walk can finish with no write.
- Whether the two PB adjustments target the same index (they use `iVar4` vs `local_58`, separate calls to the same getter).


CORRECTIONS (audit pass 2, GLM-Flash vs decompile; findings verified shaped, apply when editing):
- 6800cccc: rule 4 (and the INPUTS framing "row/col index into PB tables") — PB attribution unsupported. FUN_6800cccc contains no call to FUN_68003170 anywhere; the two "tunable adjustments" are direct reads of two distinct globals: `local_48[iVar4] = local_48[iVar4] + *(int *)(&DAT_6808cf28 + local_50 * 4 + local_54 * 0xc);` and `local_48[local_58] = local_48[local_58] + *(int *)(&DAT_6808cef8 + local_50 * 4 + local_54 * 0xc);`. The bases DAT_6808cf28 and DAT_6808cef8 are 0xd0 apart and neither is the PlayBalance base DAT_6808fde0, so citing lookBestType00CountAdjust (547) / lookPrimaryType00CountAdjust (535) — and a single shared "PBG" source for both — is not supported by this decompile; the added value also varies with local_54/local_50, unlike a fixed PB scalar.
- 6800cccc: rule 6 first branch — "W[cur] = 1, rest 0" is contradicted. The decompile performs only `aiStack_24[local_58] = 1;` under `if ((local_84 == 0) && (local_4c == 0))`, and `aiStack_24` is never memset/zero-initialized in the function, so the remaining 7 weights are uninitialized stack, not 0 (affecting the `local_90` total and the RNG walk).

CORRECTIONS HISTORY (audit pass 2 findings; rules above were rewritten accordingly):
- 6800cccc: rule 4 (and the INPUTS framing "row/col index into PB tables") — PB attribution unsupported. FUN_6800cccc contains no call to FUN_68003170 anywhere; the two "tunable adjustments" are direct reads of two distinct globals: `local_48[iVar4] = local_48[iVar4] + *(int *)(&DAT_6808cf28 + local_50 * 4 + local_54 * 0xc);` and `local_48[local_58] = local_48[local_58] + *(int *)(&DAT_6808cef8 + local_50 * 4 + local_54 * 0xc);`. The bases DAT_6808cf28 and DAT_6808cef8 are 0xd0 apart and neither is the PlayBalance base DAT_6808fde0, so citing lookBestType00CountAdjust (547) / lookPrimaryType00CountAdjust (535) — and a single shared "PBG" source for both — is not supported by this decompile; the added value also varies with local_54/local_50, unlike a fixed PB scalar.
