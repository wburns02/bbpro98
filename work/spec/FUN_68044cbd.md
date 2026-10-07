# FUN_68044cbd (void __thiscall FUN_68044cbd(void *this,int param_1,int param_2)) relief/pinch-hit decision (chunked)

DRAFT (GLM-Flash, unaudited, 4 parts)

FAILED PART

=====

## 1) PURPOSE
Continues accumulating the pinch-hit-for-pitcher desire score with inning/lead/fatigue/bench/injury adjustments and forced-PH overrides, then starts the pinch-hit-for-batter score (base, inning, home/away, lead, per-out terms).

## 2) INPUTS
- `param_1` — decision mode: nonzero (part 1's branch, presumably 1) = PH-for-pitcher; `0` = PH-for-batter (guess on encoding).
- `local_18` — accumulator from part 1 (pitcher base + early/middle-inning term already applied).
- `local_1c` — inning number (guess; tested `<7/<9/<10`).
- `local_44` — outs in current half-inning (guess; PerOut multiplier).
- `local_4c, local_78, local_34, local_24, local_3c, local_40` — boolean situation flags computed in part 1; mapped to big-lead / lead / win-run-in-scoring-pos / win-run-on-first / win-run-at-bat / win-run-on-deck per PB names (mapping inferred, guess).
- `local_38` — current pitcher record; `+0x29e` = fatigue/status field, `+4` = player id (guesses).
- `local_14` — team index (guess) compared to `this+0x172f0` (team-at-bat or defensive team, guess).
- `this+0x1733e`, `this+0x17342` — bench-strength measures (guess); `this+0x17328`, `this+0x1732c` — two slots, `-1` = empty (guess: pending substitution slots).
- `DAT_68143ee0` — global game state passed to helpers.

## 3) RULES
Pitcher path (continued from part 1):
1. Inning bucket (chain begun in part 1; LateInn branch condition cut off at part boundary, likely inning `<9` by analogy with hit path): inning `<10` → `+PB[phForPitcherInn9Adjust]`; else (≥10) → `+PB[phForPitcherExtraInnAdjust]`.
2. First-true situation chain (exactly one applies): bigLead → `+PB[phForPitcherBigLeadAdjust]`; else lead → `+PB[phForPitcherLeadAdjust]`; else winRunInScoringPos → `+PB[phForPitcherWinRunInScoringPosAdjust]`; else winRunOnFirst → `+PB[phForPitcherWinRunOnFirstAdjust]`; else winRunAtBat → `+PB[phForPitcherWinRunAtBatAdjust]`; else winRunOnDeck → `+PB[phForPitcherWinRunOnDeckAdjust]`; else `+PB[phForPitcherWinRunInDugoutAdjust]`.
3. `local_18 += PB[phForPitcherPerOutAdjust] * local_44`.
4. Fatigue via `FUN_6803df0d(local_38+0x29e)` (called twice, same value): `==4` → `+PB[phForPitcherExhaustedAdjust]`; `==3` → `+PB[phForPitcherTiredAdjust]`; otherwise → `+PB[phForPitcherRestedAdjust]`.
5. Only if `this[0x172f0] == local_14`: if `FUN_68056985(state,4,0) == 0` → `+PB[phForPitcherShutoutAdjust]`; independently, if `FUN_68056a74(state,4) == 0` → `+PB[phForPitcherNoHitterAdjust]` (two separate ifs; both can apply).
6. `local_18 += FUN_6800f0e0(this[0x17342],0,5) * PB[phForPitcherPerBPPitcherAdjust]`.
7. `local_18 += FUN_6800f0e0(this[0x1733e],0,5) * PB[phForPitcherPerBenchPlayerAdjust]`.
8. If `FUN_6803dec5(local_38+0x29e, 4)` nonzero: `local_18 += FUN_6804916c(this, *FUN_6803da2b(local_38+4,0)) * PB[phForPitcherPerInjuryPointAdjust]`.
9. Forced value (assignment, not addition): if `FUN_68049663(this)` AND `FUN_6804a357(this)` → `local_18 = 100`; else if `FUN_6804a64d(this)` → `local_18 = 100`.
10. Forced value: for `i = 0..1`, if `this[0x17328 + 4*i] != -1` → `local_18 = 100`.

Hit path (`param_1 == 0`):
11. `local_18 = PB[phForHitBase]`.
12. If inning `<7`: call `FUN_680460bb()` and return from the function (no further terms).
13. Inning: `<9` → `+PB[phForHitLateInnAdjust]`; `<10` → `+PB[phForHitInn9Adjust]`; else → `+PB[phForHitExtraInnAdjust]`.
14. If `FUN_68009610(state) == 0` → `+PB[phForHitAwayAdjust]`; else → `+PB[phForHitHomeAdjust]`.
15. Same first-true situation chain as rule 2, using `phForHitBigLeadAdjust`, `phForHitLeadAdjust`, `phForHitWinRunInScoringPosAdjust`, `phForHitWinRunOnFirstAdjust`, `phForHitWinRunAtBatAdjust`, `phForHitWinRunOnDeckAdjust`, `phForHitWinRunInDugoutAdjust`.
16. `local_18 += PB[phForHitPerOutAdjust] * local_44`.

## 4) OUTPUT / SIDE EFFECTS
- `local_18` (desire score) updated; carried into part 3.
- Early-inning hit path (`param_1==0`, inning `<7`): calls `FUN_680460bb()` and returns from the entire function; its effects unknown.
- No PB writes.

## 5) UNCERTAIN
- Semantics of all helpers: `FUN_6803df0d` (fatigue value?), `FUN_6803dec5` (injury flag test? arg `4` meaning), `FUN_6803da2b` (player id lookup?), `FUN_6804916c` (injury points?), `FUN_6800f0e0` (count, args `0`/`5` meaning), `FUN_68056985`/`FUN_68056a74` (runs scored / hits allowed? arg `4` meaning), `FUN_68009610` (home-team test?), `FUN_68049663`/`FUN_6804a357`/`FUN_6804a64d` (forced-PH conditions, e.g. DH rule / pitcher must hit / bench availability — unknown).
- Meaning of `this+0x172f0`, `+0x1733e`, `+0x17342`, `+0x17328/+0x1732c`; identity of `local_14`, `local_44`, `local_1c`, `local_38` (inferred from usage only).
- Whether `local_18 = 100` means "definitely pinch hit" (threshold semantics live in part 3/4).
- Whether `FUN_680460bb()` consumes `local_18` (Ghidra shows no arguments).
- Part 1 content (early/middle pitcher inning buckets, flag computation) inferred, not shown.

=====

## 1) PURPOSE
Continues the pinch-hit-for-hitter score (bench depth, batter injury, batter/on-deck/pinch-hitter rating tiers, platoon advantage) and, on the alternate branch, begins the pinch-runner score with an early exit before the 7th inning.

## 2) INPUTS
- `local_18` — score accumulator carried in from part 2 (hit branch adds to it; run branch re-initializes it).
- `this+0x1733e` (int) — guess: available bench-player count; passed to `FUN_6800f0e0(x,0,5)` (guess: clamp to [0,5]).
- `local_38` — pointer to a player struct (guess: current batter due up). Fields used: `+0x29e` status byte tested with arg `4` (guess: injured flag/bit); `+0x4` sub-object queried at index 0 (guess: player id); `+0x6b0` ratings table, index `0x18` → `local_58` (guess: bat rating).
- `local_54` — pointer to a second player struct (guess: on-deck batter); `+0x6b0` index `0x18` → `local_60` (the "OD" rating).
- `local_50` — set in part 2; guess: pinch-hitter candidate's bat rating (used in the diff).
- `local_14`, `local_74` — player pointers for platoon checks (guess: current batter and PH candidate).
- `local_1c` — inning number (guess: 1-based).
- `FUN_68009610(0x68143ee0)` — global flag; guess: batting team is home.
- `local_4c`, `local_78`, `local_34`, `local_24` — char flags set in part 2; identities inferred from the PB names they select: big lead, (non-big) lead, winning run in scoring position, winning run on first.

## 3) RULES
Hit branch (tail of `phForHit*` score; branch entered before this fragment):
1. `local_18 += FUN_6800f0e0(this+0x1733e, 0, 5) * PB[phForHitPerBenchPlayerAdjust]` (default 10).
2. If `FUN_6803dec5(local_38+0x29e, 4)` ≠ 0 (guess: batter is injured): `local_18 += FUN_6804916c(this, *FUN_6803da2b(local_38+4, 0)) * PB[phForHitPerInjuryPointAdjust]` (default 5).
3. Bat-rating tier on `local_58` (boundaries are the PB thresholds, so tunable):
   - `local_58 ≥ PB[phForHitVeryHighBatRatThresh]` (60) → `+= PB[phForHitVeryHighBatRatAdjust]` (−100)
   - `≥ PB[phForHitHighBatRatThresh]` (38) → −50 (`phForHitHighBatRatAdjust`)
   - `≥ PB[phForHitMedBatRatThresh]` (28) → 0 (`phForHitMedBatRatAdjust`)
   - `≥ PB[phForHitLowBatRatThresh]` (14) → +20 (`phForHitLowBatRatAdjust`)
   - else → `+= PB[phForHitVeryLowBatRatAdjust]` (+50)
4. OD-rating tier on `local_60`, same nesting with `phForHit{VeryHigh,High,Med,Low}ODRatThresh` (60/38/28/14) and adjusts −10/−5/0/+5/+10 (`phForHit{VeryHigh,High,Med,Low,VeryLow}ODRatAdjust`).
5. Diff `d = local_50 − local_58`: `d ≥ PB[phForHitVeryHighPHBatDiffRatThresh]` (15) → +50; `≥ High` (5) → +25; `≥ Med` (−5) → 0; `≥ Low` (−15) → −50; else `+= PB[phForHitVeryLowPHBatDiffRatAdjust]` (−100).
6. If `FUN_6804aa0f(this, local_14)` true: `+= PB[phForHitBatPlatAdvAdjust]` (−10).
7. If `FUN_6804aa0f(this, local_74)` true: `+= PB[phForHitPHPlatAdvAdjust]` (+30).

Run branch (`else`; `phForRun*` score):
8. `local_18 = PB[phForRunBase]` (−50) — fresh assignment, not additive.
9. If `inning < 7`: call `FUN_680460bb()` and return (pinch runner not considered; no score finalized).
10. Inning 7–8: `+= PB[phForRunLateInnAdjust]` (−15); inning 9: `+= PB[phForRunInn9Adjust]` (−10); inning ≥ 10: `+= PB[phForRunExtraInnAdjust]` (−5).
11. If `FUN_68009610(0x68143ee0)` false: `+= PB[phForRunAwayAdjust]` (−20); else `+= PB[phForRunHomeAdjust]` (−15).
12. First true flag only (if/else-if chain): `local_4c==1` → `+= PB[phForRunBigLeadAdjust]` (−50); elif `local_78==1` → `+= PB[phForRunLeadAdjust]` (−10); elif `local_34==1` → `+= PB[phForRunWinRunInScoringPosAdjust]` (+10); elif `local_24==1` → `+= PB[phForRunWinRunOnFirstAdjust]` (+5). Fragment ends here; chain continues in part 4.

## 4) OUTPUT / SIDE EFFECTS
- `local_18` holds the running score for whichever branch executed (hit branch falls through to part 4; run branch continues in part 4).
- Early-return path (inning < 7, run branch): calls `FUN_680460bb()` then returns from the function.
- No memory writes visible in this part other than locals; all called functions assumed read-only getters (guess).

## 5) UNCERTAIN
- Semantics of all helper calls: `FUN_6800f0e0` (assumed clamp to [0,5]), `FUN_6803dec5` (assumed flag test; meaning of arg 4), `FUN_6803da2b`, `FUN_6804916c` (assumed injury-points lookup), `FUN_6803e2e1` (assumed rating accessor; index 0x18 assumed bat-rating slot), `FUN_6804aa0f` (assumed platoon-advantage test), `FUN_68009610` (assumed home-team check of global 0x68143ee0), `FUN_680460bb` (no args; effect unknown).
- Identity of `local_54` (guess: on-deck batter) and what "OD" rating means; `local_50` assumed PH bat rating from part 2.
- Which player `local_38` points to (guess: current batter due up).
- Sign convention of `local_18` (assumed higher = more likely to act; final comparison is in part 4).
- Whether `local_1c` is 1-based; exact encodings of flags `local_4c/local_78/local_34/local_24` (inferred from PB names only).
- Hit-branch inning/home/lead adjustments are not in this fragment (presumably part 2).

=====

## 1) PURPOSE
Computes the "run"-variant pinch-hit desirability score (the `phForRun*` parameter family) for replacing the current batter with a bench player, then executes the substitution if the score beats a random roll.

## 2) INPUTS
- `local_18` — accumulated score from earlier parts (base + inning/lead terms already added there).
- `local_3c` (byte) — flag: winning run at bat when ==1 (==2 case, in-scoring-pos, is the preceding branch in part 3 — inferred).
- `local_40` (byte) — flag: winning run on deck when ==1.
- `local_44` — out count (guess).
- `this+0x1733e` — count of available bench players (guess), passed to FUN_6800f0e0 with bounds 0,5.
- `local_38` — pointer to current batter's struct (guess): flags word at +0x29e (bit 4 tested), player ref at +4, rating at +0x6b0 element 0x18.
- `local_54` — pointer to a second struct of same layout; source of the "OD" rating (identity unknown).
- `local_50` — pinch hitter's bat rating, set in an earlier part (guess).
- `local_14` — current batter index; `local_74` — pinch hitter index (both guess).
- `local_d0` — log context; `DAT_68114ba4` — global logging-enabled flag; `DAT_68185a60` — RNG state.

## 3) RULES
1. Winning-run location (mutually exclusive): if winning run is at bat (`local_3c==1`) add PB[phForRunWinRunAtBatAdjust] (5); else if on deck (`local_40==1`) add PB[phForRunWinRunOnDeckAdjust] (−5); otherwise add PB[phForRunWinRunInDugoutAdjust] (−10).
2. Add PB[phForRunPerOutAdjust] (−5... value 5) × `local_44` (outs): `5 * outs`.
3. Add bench count (FUN_6800f0e0 value, bounded 0..5) × PB[phForRunPerBenchPlayerAdjust] (10).
4. If bit 4 of the word at `local_38+0x29e` is set (injury flag, guess): add FUN_6804916c(this, player from `local_38+4`) × PB[phForRunPerInjuryPointAdjust] (5).
5. Read `local_58` = rating from `local_38+0x6b0`[0x18] (current batter's bat rating, guess) and `local_60` = rating from `local_54+0x6b0`[0x18] ("OD" rating).
6. Bat-rating tier for `local_58` (first threshold met, using `<` tests so tier is value ≥ threshold): ≥ PB[phForRunVeryHighBatRatThresh] (60) → add PB[phForRunVeryHighBatRatAdjust] (−100); ≥ High (38) → −50; ≥ Med (28) → 0; ≥ Low (14) → +20; else (<14) → PB[phForRunVeryLowBatRatAdjust] (+50).
7. OD-rating tier for `local_60`, same threshold pattern (60/38/28/14): adjusts −10 / −5 / 0 / +5 / +10 (VeryLow +10).
8. PH-vs-batter diff = `local_50 − local_58`; tiers: ≥ PB[phForRunVeryHighPHBatDiffRatThresh] (15) → +50; ≥ 5 → +25; ≥ −5 → 0; ≥ −15 → −50; else (<−15) → −100.
9. If FUN_6804aa0f(this, `local_14`) true (current batter has platoon advantage, guess): add PB[phForRunBatPlatAdvAdjust] (−10).
10. If FUN_6804aa0f(this, `local_74`) true (PH has platoon advantage, guess): add PB[phForRunPHPlatAdvAdjust] (+30).
11. Logging: if global `DAT_68114ba4` != 0 AND score > 0, and the "sub_log" category is enabled (FUN_680825ac / FUN_68082567): emit "=== Check For Sub ===", both player names (FUN_6803d745 on `this + idx*0x93c + 0x144`), "Pinch Hit: %s in for %s", "Chance: %d".
12. Decision: roll = FUN_68082999(&DAT_68185a60, 100) (random 0–99, guess); if roll < score → execute substitution FUN_68041d33(this, `local_74`); otherwise nothing. Score ≤ 0 can never trigger.

## 4) OUTPUT / SIDE EFFECTS
- May swap the pinch hitter (`local_74`) into the game via FUN_68041d33.
- May write decision-log lines (header, player names, "Pinch Hit: %s in for %s", "Chance: %d").
- No return value; FUN_680460bb() is the common exit/cleanup path.

## 5) UNCERTAIN
- Meaning of "OD" rating and what `local_54` points to (on-deck batter, pinch hitter, or opponent) — not determinable from this part.
- Whether `local_38` is the batter's struct vs. team struct; whether bit 4 at +0x29e is an injury flag and FUN_6804916c returns injury points.
- Whether `local_44` is current-inning outs or outs remaining.
- Whether FUN_6800f0e0 is a clamp and what `this+0x1733e` counts (assumed bench players).
- Semantics of FUN_6804aa0f (assumed platoon-advantage test) and FUN_68082999's range (assumed 0–99 from the 100 argument).
- The `%d` argument to "Chance:" is not visible in the decompile (presumably `local_18`; varargs elided).
- Roles of FUN_680573db, FUN_680460a5, FUN_680460bb, and the `local_8 = 0 / 0xffffffff` pattern (assumed logging/cleanup or exception-scope scaffolding).
- Player struct stride 0x93c and name offset 0x144 are inferred from the logging calls only.
- That the `local_3c==2` (scoring position) branch and the score base/innings/lead terms live in parts 1–3 is inferred from the else-if chain and the unused parameter list.


CORRECTIONS (audit pass 2, GLM-Flash vs decompile; findings verified shaped, apply when editing):
- 68044cbd: dispatch encoding — draft says pitcher path runs for "nonzero (presumably 1)" `param_1`; decompile branches `if (param_1 == 2)` → pitcher (0xbe chain), `else if (param_1 == 0)` → hit (0xd4), `else` → run (0x101). `param_1==1` executes the phForRun branch, not the pitcher branch.
- 68044cbd: forced-PH nesting — decompile calls `FUN_6804a64d(this)` only in the `else` of `if (FUN_68049663(this))`, i.e. only when FUN_68049663 is false; draft's "if A AND B → 100; else if C → 100" would also test FUN_6804a64d when FUN_68049663 true but FUN_6804a357 false.
- 68044cbd: draft part 4 rule 2 computes "`5 * outs`"; decompile adds `FUN_68003170(0x10e) * local_44` with 0x10e=270 → phForRunPerOutAdjust default −5 (which the draft itself cites), so the multiplier is −5, not +5.
