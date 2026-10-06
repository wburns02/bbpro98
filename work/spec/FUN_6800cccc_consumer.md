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
4. `row = FUN_6800f1c0()`, `col = FUN_6800f1e0()`; then:
   - `A[iVar4] += PBG[lookBestType00CountAdjust]` at byte offset `col*4 + row*0xc` (3×3 int table: row stride 12, col stride 4 — inferred from strides).
   - `A[local_58] += PBG[lookPrimaryType00CountAdjust]` at the same offset (same row/col).
5. `sumA = ΣA[0..7]`, `sumB = ΣB[0..7]`.
6. Build weights W = `aiStack_24`:
   - `sumA == 0 && sumB == 0`: `W[cur] = 1`, rest 0.
   - `sumA == 0`: `W[i] = B[i]` for all i.
   - `sumB == 0`: `W[i] = A[i]` for all i.
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
