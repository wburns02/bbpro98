# FUN_68043fcf () params=1

DRAFT (GLM-Flash, unaudited)

## 1) PURPOSE
Scans all 40 player slots and selects one (by role class and a two-key score) to be brought in as a pitcher, via escalating fallback passes; commits the choice or calls an emergency fallback.

## 2) INPUTS
- `param_1` — game-state object.
  - Player array: base `param_1`, stride `0x93c`, 40 entries (`0x28`).
    - `+0x144`: player record. `FUN_6803d44b(rec)` = validity/eligibility flag (guess: active/on roster). `FUN_6803da2b(rec,3)` = rating #3 (guess: pitching ability).
    - `+0x3de`: pitching-stats record (guess). `FUN_6803e1b2(s,3)` = stat 3, used as denominator (guess: appearances/innings). `FUN_6803e1b2(s,4)` = stat 4, numerator. `FUN_6803df4a(s)` = availability flag (guess: warmed up / can enter). `FUN_6803dded(s)` = role code, values 0/1/2 (guess: 0=starter, 1=reliever, 2=closer); called twice per check, assumed same result.
    - `+0x7f0`: counter block. `FUN_6803e2e1(blk,0x20)` = counter 0x20 (guess: pitches thrown today).
  - `+0x17330`: int, 0/1 selector (guess: team/side index).
- `PB[posPlayerPitchingRuns]` (default 12).

## 3) RULES
Per-player scores (computed identically in every pass):
- R1. Primary `P = (stat4 * 100) / stat3` (integer division; player skipped entirely if `stat3 == 0`).
- R2. Secondary `S = (rating3 * 100) / (counter0x20 + 0x33)` (0x33 = 51).
- R3. Running best is `(bestP, bestS, bestIdx)`, initialized to `(-1, -1, -1)`. A candidate replaces it iff `P > bestP`, or (`bestP < 1` and `S > bestS`). Strict comparisons: on ties the lowest player index wins. `bestP/bestS` are only ever set together with `bestIdx`, so each pass starts effectively fresh.

Passes (each scans all 40 slots; later passes run only if `bestIdx == -1`):
- R4. Pass A: player must pass `FUN_6803d44b`, have `stat3 != 0`, have `FUN_6803df4a != 0`, and role ∈ {1, 2}.
- R5. Gate between A and B: compute `bVar2 = FUN_68056985(&DAT_68143ee0, (*(int *)(param_1+0x17330) == 0), 0)` and `bVar3 = FUN_68056985(&DAT_68143ee0, *(int *)(param_1+0x17330), 0)` (per-team byte values, guess: runs). Pass B runs iff `PB[posPlayerPitchingRuns] <= (int)(bVar2 - bVar3)` (bytes compared as signed int difference).
- R6. Pass B: role ∈ {0, 2}; no `FUN_6803df4a` check.
- R7. Pass C: role ∈ {1, 2}; no `FUN_6803df4a` check.
- R8. Pass D: role ∈ {0, 2}; no `FUN_6803df4a` check.
- R9. If `bestIdx == -1` after all passes → `FUN_68043571(param_1)`; else `FUN_68041d33(param_1, bestIdx)`.

## 4) OUTPUT / SIDE EFFECTS
- No direct writes in this function. Effect is entirely via the final call: `FUN_68041d33(param_1, index)` commits the selected player (presumably installs him as pitcher), or `FUN_68043571(param_1)` handles the no-candidate case.

## 5) UNCERTAIN
- Semantics of every accessor: validity flag (`FUN_6803d44b`), availability (`FUN_6803df4a`), role codes 0/1/2 (`FUN_6803dded`), meaning of stats 3/4, rating 3, counter 0x20.
- What `DAT_68143ee0` holds and what `FUN_68056985` returns; whether `+0x17330` is a team index; which team's runs `bVar2`/`bVar3` are, so the sign of the margin vs. `PB[posPlayerPitchingRuns]` (losing vs. winning by ≥12) is unknown.
- Behavior of `FUN_68043571` (fallback) and `FUN_68041d33` (commit).
- Whether the double `FUN_6803dded` calls could return different values (assumed no).
