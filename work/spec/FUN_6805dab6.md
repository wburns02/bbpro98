# FUN_6805dab6 (short __thiscall FUN_6805dab6(void *this,short *param_1))

DRAFT (GLM-Flash, unaudited)

## FUN_6805dab6 — throw-time estimate

**1) PURPOSE**
Computes a short integer time value equal to a quantity divided by a rate, plus the `throwTimeSlop` fudge factor (likely an estimated throw/arrival time).

**2) INPUTS**
- `this` — object instance; field at `this+0xc` is passed to `FUN_68002bb0` (contents unknown; guess: a position/point or entity holding one).
- `param_1` — `short*`, passed to `FUN_68002bb0` (guess: target position or destination).
- `PB[throwTimeSlop]` — default 6.

**3) RULES**
1. `iVar2 = FUN_68002bb0(this+0xc, param_1)` — semantics unknown; guess: a distance/length in game units between the point at `this+0xc` and `param_1`.
2. `sVar1 = FUN_6805d960(this, iVar2)` (returned as `short`) — semantics unknown; guess: a rate/speed, possibly distance-dependent since it receives `iVar2`.
3. Result = `(short)(iVar2 / (int)sVar1) + (short)PB[throwTimeSlop]`.
   - Integer (truncating) division; no zero-check on `sVar1` — a zero rate would divide by zero.
   - The slop is added after the division, as a flat constant (default 6 ticks/frames — unit inferred from the parameter name only).
4. Return the sum as `short`.

**4) OUTPUT / SIDE EFFECTS**
- Returns the computed `short`.
- No side effects visible in this function; any side effects live inside `FUN_68002bb0` / `FUN_6805d960` (unknown).
- Called from 5 sites (`68023268`, `6805cc60`, `6805e262`, `6805e93b`, `6805ecfd`), consistent with a shared throw-time helper.

**5) UNCERTAIN**
- What `FUN_68002bb0` computes (distance is a guess from the divide pattern and the slop parameter's name).
- What `FUN_6805d960` returns (rate/speed is a guess; it could be any divisor, e.g., a per-unit time already scaled).
- Whether `param_1` is a point (x,y pair of shorts) or something else.
- Units of the return value (frames vs. ticks vs. internal time units).
- Whether the subfunctions have side effects or read other PB parameters.
- Behavior on `sVar1 == 0` (no guard present; would fault or produce platform-defined result).
