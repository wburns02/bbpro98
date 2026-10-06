# FUN_6805da5e () params=1

DRAFT (GLM-Flash, unaudited)

**PURPOSE**
Estimates the travel time of a throw as distance ÷ throw speed plus a fixed slop constant.

**INPUTS**
- `this` — object whose throw speed is queried (likely a fielder/thrower entity) *(guess)*
- `param_1` — `short*`, target position or entity *(guess)*
- `param_2` — origin position or entity *(guess)*
- `PB[throwTimeSlop]` (default 6) — flat time added to the result

**RULES**
1. Compute `D = FUN_68002bb0(param_2, param_1)` (integer; argument order is reversed relative to this function's parameters — presumably a distance between the two points/entities).
2. Compute `S = FUN_6805d960(this, D)` (short; throw speed, possibly a function of the distance `D`).
3. Return `(short)(D / S) + PB[throwTimeSlop]`.
   - Division is integer division (truncating).
   - The slop is added after the division, as a constant.
4. No other thresholds, clamps, or branches exist in this function.

**OUTPUT / SIDE EFFECTS**
- Returns a `short`: estimated throw time (units unknown — likely ticks/frames).
- No side effects visible in this function's own body (the two callees could have side effects; not determinable here).

**UNCERTAIN**
- Exact semantics of `FUN_68002bb0` (Euclidean distance vs. squared distance vs. path distance) and what its arguments are.
- What `FUN_6805d960` returns (throw velocity? per-tick movement?) and how it depends on `D` and `this`.
- Whether `S` can be 0 — the visible code has no guard, so a zero speed would cause a division-by-zero; unknown if callers/callees prevent it.
- Units of the return value and of `throwTimeSlop`.
- Identities of the two callers' contexts (68023268, 6805e93b) — not inspected here.
