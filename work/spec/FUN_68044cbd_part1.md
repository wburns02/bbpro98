# FUN_68044cbd params=112 relief/pinch-hit decision (chunked)

DRAFT (GLM-Flash, unaudited, first quarter in 2 parts; remaining quarters above)

**1) PURPOSE**
Part 1/8 of the FastSim pinch-hit/relief decision: resolves the batting team's current and on-deck batter from the lineup arrays, validates lineup state, and fetches initial game-state values used by later parts.

**2) INPUTS**
- `this` — sim/game state object.
- `param_1` — not referenced in this part (guess: selector consumed in later parts).
- `param_2` — added to a base order index before `% 9` (guess: offset selecting which upcoming batter to evaluate, or half-inning selector).
- `this+0x17336` (int) — base batting-order index (guess: current slot of the batting team).
- `this+0x172a0` — int[9]: batting-order player IDs (inferred: on-deck lookup uses same array).
- `this+0x172c4` — int[9], plus one int at `this+0x172e8` (10 entries total): array searched for the batter (guess: in-game player list, 10th slot = DH/extra slot).
- Global object `0x68143ee0`: two byte getters called on it (guess: game state such as inning/half/outs).
- **PB parameters: none read in this part.**

**3) RULES**
1. Slot: `local_2c = FUN_6800f0e0((*(int*)(this+0x17336) + param_2) % 9, 0, 9)` (FUN_6800f0e0 guess: clamp to [0,9]).
2. Batter ID: `local_14 = *(int*)(this + local_2c*4 + 0x172a0)`.
3. `local_38 = FUN_68041e9c(this, 0)`; `local_54 = FUN_68041e9c(this, 1)` — one value per team index 0/1 (guess: team scores or team handles; use not shown in this part).
4. If `local_14 == -1`: call `FUN_68082319("...FastSim_FROSTER.cpp...", 0xf50, <msg>)` — error at FROSTER.cpp line 3920. No return/branch visible, so flow appears to continue.
5. Find batter in the 10-entry array: linear scan of slots 0–8 at `this+0x172c4+slot*4` comparing to `local_14`; then if `*(int*)(this+0x172e8) == local_14`, set index = 9. Result in `local_20` (0–9).
6. If `local_20 > 9`: error via `FUN_68082319(..., 0xf63, <msg>)` — line 3939. As compiled, `local_20` can never exceed 9, so this check appears unreachable (likely decompile artifact of an original "not found" test).
7. `local_1c = FUN_6800f200(0x68143ee0)`; `local_44 = FUN_68002c80(0x68143ee0)` (both return bytes).
8. On-deck: `local_68 = (local_2c + 1) % 9`; `local_64 = *(int*)(this + local_68*4 + 0x172a0)`.

**4) OUTPUT / SIDE EFFECTS**
- Locals prepared for later parts: `local_2c` (slot), `local_14` (batter ID), `local_20` (index in 10-entry array), `local_38`/`local_54` (FUN_68041e9c results), `local_1c`/`local_44` (global-state bytes), `local_68` (on-deck slot), `local_64` (on-deck batter ID); `local_18 = 0` initialized (role in later parts).
- Side effects: two potential error-log calls (lines 3920, 3939); MSVC SEH frame installed (`local_8 = -1`, handler → `LAB_680460b1`, FS:[0] swapped) — boilerplate, not game logic.

**5) UNCERTAIN**
- Semantics of `param_1`, `param_2`, and field `0x17336`.
- Exact meaning of the arrays at `0x172a0` / `0x172c4` / `0x172e8` (inferred as batting order and a 10-slot in-game list, possibly with DH).
- Return values of `FUN_68041e9c`, `FUN_6800f200`, `FUN_68002c80`; whether `FUN_6800f0e0` is a clamp.
- Whether the validation failures abort or only log (no visible branch).
- Reachability of the line-3939 check.

=====

## 1) PURPOSE
Categorizes the current game situation (lead size / position of potential tying-or-winning run) and scans the 40-player roster for the best available bench candidate, then begins computing the substitution threshold (currently only the `param_1==2` pitcher branch is visible).

## 2) INPUTS
- `param_1` — decision type: 0 = pinch hit, 1 = pinch run, 2 = relief pitcher *(labels inferred from PB parameter name prefixes)*
- `this` — team/game object; player array at stride `0x93c`, up to 40 entries (`0x28`)
- `local_1c` — inning number (set in part 1)
- `DAT_68143ee0` — game state struct; `FUN_68056985(&DAT_68143ee0, 3, 0)` and index `4` return the two team scores *(which is home/away is unknown)*
- `DAT_681147df`, `DAT_681147e1`, `DAT_681147e3` — boolean game-state flags *(inferred: runner on 1st, 2nd, 3rd respectively)*

## 3) RULES

**Situation categorization**

Let `diff = score_A − score_B` (from indices 3 and 4; sign convention uncertain). Let `r1`, `r2`, `r3` be the three flags and `n = r1 + r2 + r3`.

1. If `diff ≥ 5` → set `local_4c` (big-lead case).
2. Else if `1 ≤ diff < 5` → set `local_78` (lead case).
3. Else (`diff ≤ 0`), check in order (first match wins):
   - **a.** `(diff == 0 AND (r3 OR r2)) OR (diff == −1 AND r3 AND r2)` → set `local_34` (win-run in scoring position).
   - **b.** `r1 AND (n + diff == 1)` → set `local_24` (win-run on first).
   - **c.** `n + diff == 0` → set `local_3c` (win-run at bat).
   - **d.** `n + diff == −1` → set `local_40` (win-run on deck).
   - **e.** None of the above → no flag set (implicitly "win-run in dugout").

**Bench player scan**

4. For each player `i` in `0..39`:
   - If `param_1 == 0`: rating = value at sub-index `0x18` via `FUN_6803e2e1`.
   - If `param_1 == 1`: rating = value at sub-index `0x19`.
   - If `param_1 == 2`: rating = `FUN_68002dd0(value_at_0x18, value_at_0x19)` (combination function).
   - Player is eligible only if `FUN_6803dded(this + i*0x93c + 0x3de) == 0`.
   - Track the maximum rating (`local_50`) and its index (`local_74`); ties go to the earliest index.

5. If no eligible player found (`local_74 == −1`), call `FUN_680460bb()` and return immediately.

**Threshold computation (param_1 == 2 only, partial in this excerpt)**

6. `threshold = PB[phForPitcherBase]` (default −30).
7. Inning adjustment (using `local_1c`):
   - `inning < 4`: `threshold += PB[phForPitcherEarlyInnAdjust]` (−50)
   - `4 ≤ inning < 7`: `threshold += PB[phForPitcherMiddleInnAdjust]` (−50)
   - `7 ≤ inning < 9`: *(cut off; presumably `PB[phForPitcherLateInnAdjust]`)*
   - `inning ≥ 9`: *(not shown in this part)*

## 4) OUTPUT / SIDE EFFECTS
- Situation flags `local_4c`, `local_78`, `local_34`, `local_24`, `local_3c`, `local_40` set for use in later parts.
- `local_50` = best available bench rating; `local_74` = index of that player (−1 if none).
- `local_18` = partially computed threshold (pitcher branch only).
- Early return via `FUN_680460bb()` if no bench player is available.

## 5) UNCERTAIN
- Which team's score is index 3 vs 4 (sign of `diff`).
- Meaning of the three `DAT_681147df/e1/e3` flags (base-runner occupancy is inferred from the arithmetic and PB parameter names, not confirmed).
- What ratings at sub-indices `0x18` and `0x19` represent (batting vs running vs other).
- What `FUN_68002dd0` does to combine the two ratings.
- What `FUN_6803dded` checks (availability, injury, already in game, etc.).
- What `FUN_680460bb()` does on the no-candidate path.
- Direction of the eventual threshold comparison (not shown in this part).
