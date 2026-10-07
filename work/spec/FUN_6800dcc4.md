# FUN_6800dcc4 (void __fastcall FUN_6800dcc4(int param_1))

DRAFT (GLM-Flash, unaudited)

# FUN_6800dcc4 — Batter Discipline Rating

## 1) PURPOSE
Computes the batter's plate-discipline rating for the current pitch and stores it at `*(param_1 + 0x11a)`, as a base from batter ratings plus situational adjustments.

## 2) INPUTS
- `param_1`: at-bat/batter context struct.
  - `+0x70`: pointer to a record; `FUN_6803da2b(ptr+4, 4)` yields an int (guess: experience/plate-appearance-derived value).
  - `+0x95`: int batter rating (guess: "CH" contact/chase rating, per `disciplineRatingCHPct`).
  - `+0x8d`: int, passed to zone classifier (guess: batter/stance zone input).
  - `+0xe9`: short (guess: batter's "look" location component).
  - `+0xfa`: int (guess: pitch type; 0 = fastball, per `FBDownMiddle` rule).
  - `+0x107`, `+0x109`: pitch location as two shorts (x/y).
  - `+0x11a`: int output field (discipline rating).
- Globals: game-state object `0x68143ee0` (count values via `FUN_6800f1c0`/`FUN_6800f1e0`, an index via `FUN_680076c0`, outs via `FUN_68002c80`); runner-state object `0x680a57b7` (`FUN_6800f600`, `FUN_6800f640`); `DAT_680a224c` (arg to `FUN_6800f680`); table `DAT_6808cf58`; pitcher-record array `DAT_68114ba8` (stride 0x173be).
- `FUN_68005b80(value, pct)` is assumed to be a percent-scale (`value*pct/100`), inferred from the `*Pct` parameter names.

## 3) RULES
1. Start: `rating = scale(+0x95, PB[disciplineRatingCHPct]) + scale(expValue, PB[disciplineRatingExpPct]) + PB[disciplineRatingBase]`.
2. Add `DAT_6808cf58[v1*0xC + v2*4]` — a 3×3 int table indexed by two game-state values `v1 = FUN_6800f1c0(...)`, `v2 = FUN_6800f1e0(...)` (guess: balls/strikes count).
3. If the pitcher record (selected by `FUN_680076c0(...)` into `DAT_68114ba8`, stride 0x173be) has zero at int-array element index 0xB of the array at offset 0x29E, add `PB[disciplineRatingNoPitchesAdjust]`.
4. If `FUN_6800f600(...)` OR `FUN_6800f640(...)` (runner state, guess: runner on 2nd/3rd = scoring position) is nonzero, add `PB[disciplineRatingScoringPosAdjust]`.
5. If `FUN_6800f640(...)` is nonzero (guess: runner on 3rd) AND outs (`FUN_68002c80(...)`) < 2, add `PB[disciplineRatingOnThird01OutsAdjust]`.
6. `zone = FUN_6802ef2a(+0xfa, +0x107, FUN_6800f680(DAT_680a224c), +0x8d)`; if `zone == 2` add `PB[disciplineRatingPlusZoneAdjust]`; if `zone == 0` add `PB[disciplineRatingMinusZoneAdjust]`; otherwise no change.
7. Compute `FUN_68005cc0(FUN_68005c40(pitchLoc(+0x107), lookLoc(+0xe9)), 5)`; if both 16-bit halves of the result are zero, add `PB[disciplineRatingLocNextToLookAdjust]` (guess: pitch located adjacent to batter's look).
8. If `+0xfa == 0` (guess: fastball) AND `FUN_68009560(short@+0x107) < 2` AND `FUN_68009560(short@+0x109) < 2`, add `PB[disciplineRatingFBDownMiddleAdjust]`.
9. Final: `rating = scale(rating, PB[disciplineRatingPct])`.

## 4) OUTPUT / SIDE EFFECTS
Writes the final rating to `*(param_1 + 0x11a)`. No other writes to `param_1`; no return value.

## 5) UNCERTAIN
- Semantics of `FUN_68005b80` (assumed percent-scale), `FUN_68005c40`, `FUN_68005cc0(…,5)`, `FUN_68009560`, `FUN_6802ef2a`, `FUN_6800f680`.
- Which count values `FUN_6800f1c0`/`FUN_6800f1e0` return and the contents/meaning of the `DAT_6808cf58` table.
- Meaning of the `FUN_680076c0` index (team/pitcher selection) and of the pitch-array element at +0x29E[0xB].
- Which runner state each of `FUN_6800f600`/`FUN_6800f640` represents (order inferred from the "OnThird" rule name).
- Whether higher stored rating means more or less batter discipline.
