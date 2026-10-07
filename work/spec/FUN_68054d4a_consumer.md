# FUN_68054d4a consumer of init-loaded PB globals

DRAFT (GLM-Flash, unaudited)

## FUN_68054d4a — Spec (part 1/2)

### PURPOSE
Computes a hit-angle-derived adjustment value and begins loading two player records (with scaled stat values) into local structures for a comparison/display operation.

### INPUTS
- `this` — object; contains a splitter window pointer at offset `+0x6b`
- `param_1` — 4-byte record identifier (first entity) [guess: player/team ID]
- `param_2` — 2-byte record identifier (first entity) [guess: sub-ID or year]
- `param_3` — int; multiplied by 1000 [guess: a rating or count for first entity]
- `param_4` — pointer to 6-byte record (4+2 bytes) for second entity [guess: matching ID pair]
- `param_5` — pointer to int; dereferenced and multiplied by 1000 [guess: rating/count for second entity]
- `param_6` — uint pointer; **not referenced in this portion**

### RULES
1. Read splitter tracking state (`local_9c`, 0 or 1) from `this+0x6b`. Use it to index into three PBG arrays: `hitAngleCountPower`, `hitAngleFacesPower`, `hitAngleBasePower` (each indexed `local_9c * 4`).
2. Call `FUN_68082a7c(countPower, facesPower, basePower)` → produces an angle value (`local_104`).
3. Clamp/map that value to range [0, 0x39] (0–57) via `FUN_6800f0e0` → `local_e4`.
4. Use `local_e4` as index into lookup table at `DAT_68097660`: read two shorts (`local_44` at `index*2`, `local_98` at `index*2+2`).
Call `FUN_680829dc(&DAT_68185a60,(int)local_44,(int)local_98)` → base angle value (`local_58 = (short)iVar2`, truncated to short). The lookup base is `&DAT_68185a60`, **not** the rule-4 table `DAT_68097660`; `DAT_68097660` only supplies `local_44`/`local_98` (rule 4).
6. Re-read tracking state (`local_c8`).
7. Select one of two data blocks (offset `0x173be` apart) based on `FUN_680076c0(0x68143ee0)` result. From the selected block, read an int at offset `+0x6b0`, element index `0x23` (35).
8. Compute `local_bc = (read_value + tracking_state) / 2`.
`local_40 = 0;` If `local_bc < 0x32` (50): `iVar2 = FUN_68005b80(0x4000 - local_58,0x32 - local_bc); local_40 = (short)iVar2;` Else: `iVar2 = FUN_68005b80(local_58 + 0x4000,0x32 - local_bc); local_40 = (short)iVar2;` — the adjustment is stored to `local_40` (short), not discarded.
10. `local_58 = adjustment + local_58` (final adjusted angle).
Immediately after the branch: `local_58 = local_40 + local_58;` — the rule-9 adjustment `local_40` is added to `local_58` (16-bit), giving the final adjusted angle. This `local_58` is the value consumed in part 2 as the `local_110 + local_58` addend in `_local_110 = CONCAT22((short)((uint)local_c4 >> 0x10),local_110 + local_58);`.
12. Call `FUN_6807d31c` on the `param_4`-derived data → `local_7c` (processed record 2).
13. Set `local_90 = *param_5 * 1000`.
14. Call `FUN_6807d31c` on the `param_1`/`param_2`-derived data → `local_34` (processed record 1).
15. Set `local_50 = param_3 * 1000`.
16. Copy `local_c0` to `local_10c`.

### OUTPUT / SIDE EFFECTS
- `local_58` — adjusted angle value (carries to part 2)
- `local_7c`, `local_34` — processed record data for two entities
- `local_90`, `local_50` — stat values scaled ×1000
- Multiple zero-initialized locals (`local_94`, `local_54`, `local_100`, `local_f4`, `local_b8`, `local_68`, `local_ac`, `local_110`) prepared for part 2
- `CString local_88` constructed (used in intermediate calls)

### UNCERTAIN
- Exact semantic meaning of the `DAT_68097660` lookup table entries
- What `FUN_68005b80` computes (interpolation, scaling, or angular wrap?)
- What `FUN_6807d31c` / `FUN_6807d14c` do internally (likely stat extraction and formatting)
- Why index `0x23` is used into the data block at `+0x6b0`
- Purpose of `param_6` (unused in this portion)
- Whether the two records represent batter vs. pitcher, or two players being compared
- The meaning of the ×1000 scaling on `param_3` and `*param_5`

=====

**PURPOSE**
Builds a 3D point (base vector + direction vector scaled by clamped factors derived from `local_b4`) and derives from it three component-ratio shorts, one heading angle scaled ×44/10, and a horizontal (y=0) direction vector, writing all three to caller output pointers.

**INPUTS**
- Carried over from part 1 (origins unknown, all guesses): `local_b4` (scalar driving both clamps; likely angle/power), `local_b0`, `local_b8` (pair used for magnitude and ratio), `local_c4` (32-bit, split into two 16-bit halves), `local_58` (16-bit addend), base vector `local_100/local_fc/local_f8`, direction vector `local_f4/local_f0/local_ec` (guess: contiguous struct at `&local_100`), transform objects `local_20`/`local_e0`, object handle `local_88`.
- Args: `param_4` (ptr, ≥3 shorts out), `param_5` (ptr to int out), `param_6` (ptr, ≥3 ints out). `param_1`–`param_3` unused in this half.

**RULES**
1. Low 16 bits of `local_c4` get `local_58` added (16-bit wrap; high 16 bits pass through, no carry) → `_local_110`; converted via `FUN_6807d31c` into `local_20` (then passed through `FUN_6807d2c8`) and into `local_e0`.
2. `FUN_6807d14c` produces `local_94` (from `local_20`, `&local_100`) and `local_54` (from `local_20`, `&local_f4`); neither is read again here.
3. `local_b8` initialized from `&local_f4` (`FUN_68014b50`), combined with `&local_100` (`FUN_6803bab0`, guess: subtract), scaled by `FUN_6803bd30(...,1000)` (guess: normalize to 1000); `local_c = FUN_6807c959(&local_b8) * 0x14` (×20). `FUN_6807c959` guess: atan2-style angle.
4. `local_cc = FUN_6807cb34(local_b0*local_b0 + local_b8*local_b8)` — square root (magnitude of b0,b8).
5. `_local_e8` (low short) = `2 * FUN_6807c09c(local_cc, local_b4)`; `_local_8` (low short) = `FUN_6807c09c(local_b8, local_b0)`. `FUN_6807c09c` guess: fixed-point divide or angle-ratio.
6. `local_a0 = FUN_68009440((short)local_c, (short)_local_e8)` (guess: 16-bit multiply).
7. `local_ac = -FUN_68009440((short)local_a0, (short)_local_8)`.
8. `local_a8 = 0` (hardcoded).
9. `local_a4 = FUN_68009470((short)local_a0, (short)_local_8)` (companion op to 68009440; guess: add or cos-multiply). Pattern (−f(a0,_8), 0, g(a0,_8)) resembles polar→Cartesian (−sin, 0, cos) — guess.
10. Clamp factors (integer division): `local_5c = clamp(0x37 − (local_b4 − 0x3c)/3, 0x2d, 0x37)` = clamp(55 − (b4−60)/3, 45, 55); `local_108 = clamp(local_b4/2, 0, 0x45)` = clamp(b4/2, 0, 69).
11. Offset point (`FUN_68005b80` guess: fixed-point multiply):
    - `local_68 = local_100 + FUN_68005b80(local_f4, local_108)`
    - `local_64 = local_f0 − FUN_68005b80(local_fc, local_5c)`
    - `local_60 = local_f8 + FUN_68005b80(local_ec, local_108)`
    i.e. V1 + V2·scale; x/z use clamp(b4/2,0,69), y uses clamp(55−(b4−60)/3,45,55) and is subtracted.
12. `local_68`-vector and `local_ac`-vector fed through `FUN_68014b50`/`FUN_6807d14c` with `local_e0` into object `local_88`; no named result kept in this half.
13. `param_4` outputs (computed before step 14's rescale of `local_68`): `[+0] = FUN_6807c09c(local_64, local_60)`; `[+2] = FUN_6807c09c(local_60, local_68)`; `[+4] = FUN_6807c09c(local_64, -local_68)`.
14. `FUN_6803bd30(&local_68, 1000)` (modifies `local_68` in place); `*param_5 = FUN_6807c959(&local_68)`; then `*param_5 = (*param_5 * 0x2c) / 10` (×44/10, integer).
15. `param_6[0] = local_ac; param_6[1] = local_a8 (0); param_6[2] = local_a4`.

**OUTPUT/SIDE EFFECTS**
- `*param_4`: 3 shorts (step 13). `*param_5`: int, angle ×44/10. `*param_6`: 3 ints, middle always 0 → horizontal direction vector.
- In-place modification of `local_68`; unknown side effects via `FUN_6807d2c8(local_20)` and the `local_88` object calls.
- **No PB/PBG parameter is referenced in this half.** All constants (55, 45, 69, 60, ÷3, ÷2, ×2, ×20, ×44/10, 1000) are hardcoded; any tunables must have been loaded into carried-over locals in part 1.

**UNCERTAIN**
- Semantics of all helper FUN_ functions; only `FUN_6807cb34` ≈ sqrt is high-confidence (a²+b² input). `FUN_6807c959` ≈ atan2, `FUN_6803bd30` ≈ scale/normalize-to-1000, `FUN_6807c09c` ≈ divide vs. angle-ratio, `FUN_68005b80` ≈ multiply, `FUN_68009440`/`70` ≈ multiply/add or sin/cos pair — all inferences from usage.
- Origin/meaning of every carried-over local and which (if any) hold PB values from part 1.
- Aliasing risk: if `FUN_68014b50(&local_b8, &local_f4)` copies >4 bytes, it overwrites `local_b4` before it is read at steps 5/10 — order dependency unresolvable without part 1.
- Whether `local_94`/`local_54` (step 2) and the `local_88` transforms (step 12) are dead stores or carry needed side effects.
- Physical meaning (batted ball, throw, fielder positioning) and units of `local_b4`; exact widths of locals beyond what Ghidra casts show.

STATUS: audited (chunked pass 3). Rules 5,9,10 rewritten from the audit corrections (v2 merged 2026-10-07); pass-3 verdict RESOLVED.

CORRECTIONS HISTORY (chunked audit pass 3; rules above were rewritten accordingly):
- 68054d4a rule 5: draft's `FUN_680829dc(table, …)` implies the rule-4 table `DAT_68097660`; decompile passes a different base: `FUN_680829dc(&DAT_68185a60,(int)local_44,(int)local_98)` (0x68185a60 ≠ 0x68097660; DAT_68097660 only supplies `local_44`/`local_98`).
- 68054d4a rule 9: adjustment is stored to a local the draft never mentions — `local_40 = (short)iVar2` after `FUN_68005b80(0x4000 - local_58,0x32 - local_bc)`; `local_58` is not written anywhere in this half, so rule 10's `local_58 = adjustment + local_58` is not evidenced here (slice cuts off mid-branch).
