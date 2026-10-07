# FUN_6803a5ff (int FUN_6803a5ff(void))

DRAFT (GLM-Flash, unaudited)

## 6803a5ff — Environmental ball modifier (altitude + temperature), memoized

**1) PURPOSE**
Returns a cached scalar (base 130) that rises with stadium altitude and temperature, derived from the park/weather object, for use by ball-flight callers (6803a6f0, 6803aa6b).

**2) INPUTS**
- Global object `DAT_68114948` (Ghidra typed it `CFileDialog`; almost certainly the weather/park context):
  - `GetStartPosition(&DAT_68114948)` → current stadium altitude, integer [inferred — MFC typing is spurious]
  - `FUN_6803bdb0(&DAT_68114948)` → current temperature, low byte (°F assumed) [inferred]
- `PB[ballAltitudePct]` (100) — percent scale on stadium altitude
- `PB[ballBaseAltitude]` (0) — flat altitude offset
- `PB[ballTempPct]` (40) — percent scale on (temp − 69)
- Cache globals: `DAT_68096a54` (altitude term), `DAT_68096a58` (temp term), `DAT_68096a50` (result)

**3) RULES**
1. **Cache check first:** fetch current altitude A and temperature T. If `A == DAT_68096a54` AND `(short)T == DAT_68096a58`, return `DAT_68096a50` unchanged. (Note: it fetches altitude via `GetStartPosition` twice — once for the check, once for the recompute.)
2. **Altitude term:** `DAT_68096a54 = FUN_68005b80(A, PB[ballAltitudePct]) + PB[ballBaseAltitude]` — i.e. `A * ballAltitudePct/100 + ballBaseAltitude` [FUN_68005b80 assumed = v*p/100].
3. **Temperature term:** `DAT_68096a58 = FUN_68005b80(T - 0x45, PB[ballTempPct])` — i.e. `(T - 69) * ballTempPct/100`. 69 (0x45) is the neutral temperature.
4. **Result:** `DAT_68096a50 = FUN_68005b80(0x82, (int)DAT_68096a54/0x113 + 100 + DAT_68096a58/5)` — i.e. `130 * (100 + altTerm/275 + tempTerm/5) / 100`.
5. All divisions are integer (truncating): `altTerm/275` and `tempTerm/5` are truncated independently before summing.
6. Return `DAT_68096a50`.

Net effect at defaults: 130 at sea level / 69°F; each +275 ft of effective altitude adds ~1.3 (+1%); each +12.5°F above 69 adds ~1.3 (tempTerm/5 = 0.08·(T−69) at ballTempPct=40).

**4) OUTPUT / SIDE EFFECTS**
- Returns `DAT_68096a50` (int).
- On recompute, writes all three cache globals (`DAT_68096a54`, `DAT_68096a58`, `DAT_68096a50`). No other side effects visible.

**5) UNCERTAIN**
- Identity of `DAT_68114948` and both accessor calls; "stadium altitude" / "temperature" are inferences from the PB names and usage. The `CFileDialog`/`__POSITION` types are Ghidra noise.
- `FUN_68005b80(v,p)` semantics: assumed `v*p/100`; rounding method unknown. (Argument order is irrelevant only if it's a symmetric multiply-scale.)
- **Cache check looks wrong as decompiled:** it compares *raw* inputs against cached *processed* values. The temp comparison `T == (T−69)·ballTempPct/100` is essentially never true at the default 40%, and the altitude comparison holds only when `ballBaseAltitude=0` and `ballAltitudePct=100`. Either the decompile misrepresents the comparison, or the cache effectively never hits for temperature (latent bug). Not resolvable from this function alone.
- Units (feet, °F) and the physical meaning of the returned scalar (carry/liveliness) — callers not analyzed.
- Whether `FUN_6803bdb0` returns a full byte and how sign-extension behaves; only the low 16 bits are compared.
- Behavior for negative `altTerm`/`tempTerm` (truncation direction for negatives assumed C semantics).
