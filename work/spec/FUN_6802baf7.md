# FUN_6802baf7 (FastSim_FINJURY) params=19

DRAFT (GLM-Flash, unaudited)

## 1) PURPOSE
Initializes the fast-sim injury module: loads `injury.dat` into static tables, then overwrites the 19-entry per-event injury-chance table with values from the PB balance-parameter table.

## 2) INPUTS
- No function arguments (void).
- `PB[]` global balance table — reads 19 `injuryChance*` entries (listed in Rules).
- File `"injury.dat"` (string ref `s_injury_dat_6808efe4`), accessed via helper calls `FUN_68082420` / `FUN_680825ac` / `FUN_68082753` / `FUN_6808268d` (assumed construct/open/read/close — guess based on usage pattern).
- Globals `DAT_68185a60` (passed to `FUN_6800f160`) — unknown meaning.

## 3) RULES
1. Open `injury.dat` via `FUN_680825ac`. If the open fails (low byte of return == 0), skip both reads.
2. If open succeeded, read 0x2C (44) bytes into table A at `DAT_68113b48`, then 0x26 (38) bytes into table B at `DAT_68113b88`.
3. If open or either read failed, call `FUN_68082319("__FastSim_FINJURY.cpp", 0x72, <ptr 0x6808eff0>)` — an error/assert reporter with source line 114. Execution then continues to the close call either way.
4. Close the file (`FUN_6808268d`).
5. Overwrite table B (19 × uint16 at `DAT_68113b88`–`DAT_68113bac`) with PB values, each truncated to 16 bits, in this order/offset:

| Off | PB param | Default |
|-----|----------|---------|
| +00 | injuryChanceRunThroughFirst | 7500 |
| +02 | injuryChanceThrowBall | 6500 |
| +04 | injuryChanceRunBases | 8500 |
| +06 | injuryChanceFieldFlyBall | 1800 |
| +08 | injuryChanceFieldGrounder | 2200 |
| +0A | injuryChanceHitByHighPitch | 28 |
| +0C | injuryChanceHitByMediumPitch | 28 |
| +0E | injuryChanceHitByLowPitch | 28 |
| +10 | injuryChanceBatterSwing | 6500 |
| +12 | injuryChanceBatterHit | 180 |
| +14 | injuryChanceCatcherHit | 180 |
| +16 | injuryChanceCollision | 90 |
| +18 | injuryChanceSlideHeadFirst | 350 |
| +1A | injuryChanceSlideFeetFirst | 550 |
| +1C | injuryChancePlayerHit | 180 |
| +1E | injuryChanceOverUsage | 300 |
| +20 | injuryChanceWarmPitch | 2200 |
| +22 | injuryChanceHalfPitch | 9999 |
| +24 | injuryChanceColdPitch | 9999 |

   Net effect: the 38 bytes read from the file into table B are fully discarded; PB values are authoritative for table B.
6. Call `FUN_6800f160(&DAT_68185a60)` and pass its return to `FUN_68082968(&DAT_68113af0, value)` — some initialization of state at `DAT_68113af0` (which sits 0x58 bytes before table A).
7. Call `FUN_6802bd54()` and `FUN_6802bd67()` — likely local-object destructors / SEH teardown (guess).

## 4) OUTPUT / SIDE EFFECTS
- Writes 44 bytes at `DAT_68113b48` (from file; not modified afterward in this function).
- Writes 38 bytes at `DAT_68113b88` (final content = PB values above).
- Whatever `FUN_68082968` writes at `DAT_68113af0`.
- No return value.

## 5) UNCERTAIN
- Helper semantics (`FUN_68082420/25ac/2753/268d` as file open/read/close) are inferred from the `"injury.dat"` string and buffer/size arguments, not confirmed.
- Whether the error reporter `FUN_68082319` aborts or returns (code path continues if it returns).
- Contents and purpose of the 44-byte table A at `DAT_68113b48`.
- Why table B is read from the file and then immediately overwritten — the file read of that block is dead in this function; possibly PB defaults are seeded from the file elsewhere, or it is vestigial.
- Meaning of `FUN_6800f160`/`FUN_68082968` and globals `DAT_68185a60`/`DAT_68113af0` (init/seed is a guess).
- Units of the chance values (likely n/10000 given the 9999 entries, but no consumer code shown here).
- Whether `FUN_6802bd54`/`FUN_6802bd67` are destructors.
