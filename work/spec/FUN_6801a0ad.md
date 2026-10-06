# FUN_6801a0ad () params=6

DRAFT (GLM-Flash, unaudited)

**1) PURPOSE**
Recomputes fielding positions for either the four infielders (indices 0–3) or the three outfielders (indices 6–8), selected by a mode flag, by applying depth and lateral offsets to base template coordinates and storing the results.

**2) INPUTS**
`param_1` — settings block; fields read as 32-bit ints at byte offsets:
- `+0x05`: destination set index in the output position array *(guess: which team/side slot to write)*
- `+0x09`: mode: 0 = position infielders, 1 = position outfielders
- `+0x0d`: template-set index for infield base coordinates *(guess: stadium or saved alignment set)*
- `+0x11`: template-set index for outfield base coordinates *(same guess)*
- `+0x15`: infield depth setting; used as (value − 2), so 2 = neutral *(guess: 0–4)*
- `+0x19`: outfield depth index 0–4 (very shallow … very deep)
- `+0x1d`: infield lateral parameter; used as multiplier (2 − value) *(guess: handedness/shift)*
- `+0x21`: outfield lateral parameter; same use

Globals/tables:
- `DAT_6808d71c` (byte): when 1, PB outfield percentages replace built-in defaults
- Base coordinates at `DAT_680c8fc8` (first short, depth axis) / `DAT_680c8fca` (second short, lateral axis); layout: set stride 0x24 (36) bytes = 9 positions × 4-byte (short,short) pair
- PB: `infieldPosFeetPerDepth` (10); `outfieldPosPctVeryShallow` (60), `outfieldPosPctShallow` (65), `outfieldPosPctNormal` (70), `outfieldPosPctDeep` (75), `outfieldPosPctVeryDeep` (80)

**3) RULES**
Infield (runs only while `+0x09 == 0`), i = 0…3:
1. depthOff = (short)( (infieldDepth(+0x15) − 2) × (short)PB[infieldPosFeetPerDepth] × 0x1E ). Default 10 → ±300 units per step (0x1E = 30; if coordinates are 1/30 ft, this is 10 ft/step — inference).
2. v = FUN_68009650( base_lateral[i][set(+0x0d)] ) — transform of the base lateral coordinate (unknown function).
3. t = (short)( (0x2000 − v) >> 2 ), i.e. (8192 − v)/4.
4. a = FUN_68014c70( t, 0, 0x444 ) — second/third args are 0 and 1092 (exact semantics unknown).
5. latOff = (short)( a × (2 − (short)lateralParam(+0x1d)) ).
6. out.depth[i] = base_depth[i][set(+0x0d)] + depthOff.
7. out.lateral[i] = base_lateral[i][set(+0x0d)] + latOff.

Outfield (runs only while `+0x09 == 1`), i = 6…8:
8. pct[] = {0x28, 0x3C, 0x45, 0x50, 0x5F} = {40, 60, 69, 80, 95} (built-in defaults).
9. If `DAT_6808d71c == 1`: pct[] = { PB[outfieldPosPctVeryShallow], PB[outfieldPosPctShallow], PB[outfieldPosPctNormal], PB[outfieldPosPctDeep], PB[outfieldPosPctVeryDeep] } (= {60,65,70,75,80} default).
10. latOff computed exactly as rules 2–5, but using set(+0x11) and lateralParam(+0x21).
11. out.depth[i] = pct[outfieldDepthIdx(+0x19)] — set directly; the outfield base depth coordinate is never read.
12. out.lateral[i] = base_lateral[i][set(+0x11)] + latOff.

Both loops:
13. FUN_6801abdc(&out[i], i) is called per positioned player, before the copy (post-processing, unknown).
14. The 4-byte (depth, lateral) pair at `DAT_680c8ec0 + i×4` (set 0, used as scratch) is copied to `DAT_680c8ec0 + i×4 + destSet(+0x05)×0x24`.
15. Positions 4 and 5 are never touched by this function.
16. FUN_6801a392() is called once before return.
17. Loop conditions re-test the mode flag each iteration, but nothing in the loops writes it, so each loop is effectively an if-guarded for.

**4) OUTPUT / SIDE EFFECTS**
- Writes (depth, lateral) short pairs into the position array at `DAT_680c8ec0`: working copy at set 0 plus duplicate at set +0x05, for positions 0–3 (infield mode) or 6–8 (outfield mode).
- Calls FUN_6801abdc per player and FUN_6801a392 once (effects unknown).
- A local CString is constructed and never used (dead code, likely debug leftover).

**5) UNCERTAIN**
- Behavior of FUN_68009650, FUN_68014c70 (clamp? scale? random?), FUN_6801abdc, FUN_6801a392.
- Physical meaning of the two coordinate components (which field axis, units, whether 0x1E=30 is a units-per-foot scale, and why outfield depth is an absolute 40–95 value while infield depth is an offset from a base).
- Meaning of the (2 − value) lateral multiplier: handedness vs shift direction vs magnitude; legal values.
- What the set indices (+0x05, +0x0d, +0x11) select (team? stadium? handedness-specific template?).
- Meaning of the `DAT_6808d71c` flag.
- Why built-in outfield percentages (40/60/69/80/95) differ from the PB defaults (60/65/70/75/80).
- Identity of positions 0–3 and 6–8 *(guess: 0–3 = infield, 6–8 = LF/CF/RF; 4–5 = pitcher/catcher handled elsewhere)*.
- Full struct layout/types; only the eight 4-byte fields read here are known.
