# FUN_6803aa6b (void FUN_6803aa6b(undefined4 *param_1))

DRAFT (GLM-Flash, unaudited)

## 6803aa6b

**PURPOSE**
Copies a ball-flight/physics object into a static temp, updates its air-resistance-related values (one from a helper call, one from `PB[ballAirResistancePct]`, one hardcoded 100), and writes the temp back to the original object.

**INPUTS**
- `param_1` — pointer to the object being updated (`undefined4 *`). Layout unknown; treated as an opaque blob passed whole to the copy-in/copy-out helpers. *(Guess: ball trajectory/drag state struct.)*
- `PB[ballAirResistancePct]` — global balance parameter, default **95**. Read directly by this function.
- No other arguments. `FUN_6803a5ff()` takes nothing from this function; its value source is external (globals or side effects).

**RULES**
1. Initialize/copy the static work object at `DAT_68114908` from `*param_1` (`FUN_68014b50`).
2. Call `FUN_6803a5ff()` (no arguments) and pass its return value to `FUN_6803bd30(&DAT_68114908, value)` — stores value V1 into the work object.
3. Pass `PB[ballAirResistancePct]` (default 95) to `FUN_6803bce0(&DAT_68114908, 95)` — a *different* setter than step 2's, so presumably a different field.
4. Pass the literal `100` to `FUN_6803bd30(&DAT_68114908, 100)` — same setter as step 2. Either overwrites V1 (making step 2's store dead) or the setter targets another field internally; not determinable here.
5. Commit the work object back into `*param_1` via `FUN_6803bab0(param_1, &DAT_68114908)`.

**OUTPUT / SIDE EFFECTS**
- `*param_1` is modified (per rules 2–4, via the temp copy).
- Static temp `DAT_68114908` is left populated (never freed; it is a fixed global work object).
- Returns void.
- Sole caller: `FUN_6803aad7` (adjacent function).

**UNCERTAIN**
- What `FUN_6803a5ff()` computes (random value, global state, derived physics quantity — no visible inputs).
- Whether `FUN_6803bd30` is a field setter or a scale/apply-percentage operation; consequently whether the two calls (V1, then 100) touch the same field or different ones, and whether V1 survives.
- Which fields of `param_1` correspond to "air resistance"; the struct layout is opaque.
- Whether the `95` / `100` pair is a percentage fraction (95/100) as the PB name suggests — plausible but not provable from this function alone.
- Whether `FUN_6803bab0` performs a full copy back or a partial merge.
