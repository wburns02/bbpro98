# FUN_6800d6be (void __fastcall FUN_6800d6be(int param_1))

DRAFT (GLM-Flash, unaudited)

## 1) PURPOSE
Computes a 2D scatter/offset (two i16s at `param_1+0x107/+0x109`) for an entity by rolling 0–99 against a rating scaled by `PB[idRatingLocWeight]`, then applying a rating-dependent random spread, plus flags derived from the result.

## 2) INPUTS
Struct at `param_1`:
- `+0xf1` (u8): rating passed through the PB weight (guess: a fielding rating)
- `+0xf9` (u8): if nonzero, skips the table-derived offset block
- `+0xfa` (i32): key for lookups `FUN_6802ee96` / `FUN_6802ee74` / `FUN_6802ee52` (guess: player or position id)
- `+0xe9` (2×i16): pair combined into the final zero-test temp (guess: base/reference position)
- Outputs also read back: `+0x102`, `+0x106`, `+0x107` (sign test)

Globals: `DAT_680a224c` (context object for `FUN_6800f750/f7a0/f680`); `DAT_680a2128` (arg to `FUN_68082999`, guess: RNG); `DAT_68114948` + `FUN_680076c0(0x68143ee0)` (gate test, arg `0x80`); `DAT_68114ba8` (table, record stride `0x173be`, array at record+`0x6b0`, element index `0x22`).
PB: `idRatingLocWeight` (default 100), second arg to `FUN_68005b80`.

## 3) RULES
1. Gate: if `FUN_6800f270(&DAT_68114948, FUN_680076c0(0x68143ee0), 0x80) != 0` → fallback path: `+0x106=1`, `+0x102=0`, `+0x107 = *FUN_68002ce0(...,0,0)` (presumably (0,0)), `+0x110=1`; return.
2. `roll = FUN_68082999(&DAT_680a2128, 100)`.
3. `weighted = FUN_68005b80(*(u8*)(param_1+0xf1), PB[idRatingLocWeight])`.
4. `margin` (`+0x102`, stored u32, compared signed) `= roll − weighted`; `+0x106 = (margin < 0)`.
5. i16 pair at `+0x107` (x=`+0x107`, y=`+0x109`) `= *FUN_6800f750(ctx, …)`.
6. If `+0xf9 == 0`:
   - a. `FUN_68005c40(&+0x107, FUN_6800f7a0(ctx))` — copy/add pair (guess).
   - b. `v = *FUN_6803e2e1(FUN_68041d83(&DAT_68114ba8 + FUN_680076c0(0x68143ee0)*0x173be) + 0x6b0, 0x22)`.
   - c. `p = FUN_6802ee96(+0xfa)`; `FUN_6800f220(p, (i16)v)`; `FUN_68005cc0(p, 99)`; `FUN_6800a4a0(p, FUN_6802ee74(+0xfa))`.
   - d. If `FUN_6800f680(ctx) == 1`: `p.x = −p.x`.
   - e. `FUN_6800a4a0(&+0x107, p)`.
7. `(s1, s2) = FUN_6802ee52(+0xfa)` (i16 pair: spread radii).
8. If `+0x106 == 0` (i.e., margin ≥ 0): `s1 += (margin/10)*2`; `s2 += (margin/10)*2` (integer division).
9. `j1 = FUN_68082999(&DAT_680a2128, s1)`; if `x < 0`: `x += s1/2 − j1`; else `x += j1 − s1/2` (i.e., jitter of half-width `s1` away from/toward 0 by sign).
10. `j2 = FUN_68082999(&DAT_680a2128, s2)`; `y += s2/2 − j2` (no sign branch).
11. `temp = pair(+0x107)`; `FUN_68005c40(&temp, pair(+0xe9))`; `FUN_68005cc0(&temp, 2)`; `+0x110 = (temp == (0,0))`. `temp` is **not** written back to `+0x107`.

## 4) OUTPUT / SIDE EFFECTS
- `+0x102` (u32): margin = roll − weighted rating (0 in fallback).
- `+0x106` (u8): 1 if margin < 0 (or fallback), else 0.
- `+0x107`/`+0x109` (2×i16): final scattered offset.
- `+0x110` (u8): 1 if the temp pair (offset + `+0xe9` pair, after `FUN_68005cc0(…,2)`) is (0,0), or in fallback; else 0.

## 5) UNCERTAIN
- What the `FUN_6800f270(..., 0x80)` gate tests (fallback trigger condition).
- `FUN_68082999` assumed to be a random draw in [0, n); `FUN_68005b80` assumed rating×weight/100 scaling — formula not visible.
- Semantics of `FUN_68005c40` (copy vs. add), `FUN_6800a4a0` (add), `FUN_68005cc0` (clamp to max: 99 for ratings, but 2 for the final temp is odd — could be deadzone/bounds enum), `FUN_6800f220` (scale/apply).
- Meaning of table element `0x22` at record+`0x6b0`; meaning of `FUN_6800f680(ctx)==1` (mirror?); identity of `+0xf1`, `+0xfa`, `+0xe9` fields.
- Why the rule-11 temp is discarded except for the zero test (possible decompiler artifact or intentional flag-only use).
