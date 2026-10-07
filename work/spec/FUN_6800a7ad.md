# FUN_6800a7ad (/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */ void FUN_6800a7ad(void))

DRAFT (GLM-Flash, unaudited)

**1) PURPOSE**
Initialization routine for the fast-sim module: attempts to load the data file "numbers.inf" into an in-memory table, then copies 48 batter-decision balance parameters from the PB[] table into a contiguous runtime parameter block.

**2) INPUTS**
- No arguments (void).
- PB[] entries: the 48 named parameters listed below (all read unconditionally).
- String constant at 0x6808d040, symbol `s_numbers_inf` → "numbers.inf" (name inferred from Ghidra symbol; '.' rendered as '_').
- Scratch buffer `local_5c[18]` (72 bytes) — used as a file/context handle (guess: parser or file-stream context).
- Global table/collection at `DAT_680a2140` — target of the file load (contents/structure unknown).
- Byte array at `DAT_680a2008` (written at indices 0x10–0x1F).

**3) RULES**
1. Establish an SEH exception frame (saves FS:[0], handler → LAB_680ac4b); body executes under it.
2. Initialize the 72-byte context (`FUN_68082420`).
3. Attempt to open/read "numbers.inf" (`FUN_680825ac`). Success test is `(ret & 0xff) != 0`. On failure, skip rules 4–5.
4. On success, derive a key/index from the context (`FUN_6808520a`) and test it against `DAT_680a2140` (`FUN_68083b7e`, boolean).
5. Only if that test passes: load the file data into `DAT_680a2140` (`FUN_680840be`), then close/release the context (`FUN_6808268d`). No close is visible on the failure path.
6. Fill 16 bytes: for i = 0x10 to 0x1F, `DAT_680a2008[i] = (char)('/' - i)` — i.e. bytes at 0x680a2018–0x680a2027 receive 0x1F, 0x1E, … 0x10 descending.
7. Copy 48 dwords from PB[] in fixed order into the contiguous block at 0x6808cef8–0x6808cfb7 (this always executes, independent of rules 3–5):
   - 0x6808cef8–0x6808cf24: `lookPrimaryType{0–3}{0–2}CountAdjust` (row-major: type 0 counts 0,1,2; type 1 counts 0,1,2; …)
   - 0x6808cf28–0x6808cf54: `lookBestType{0–3}{0–2}CountAdjust`
   - 0x6808cf58–0x6808cf84: `disciplineRating{0–3}{0–2}CountAdjust`
   - 0x6808cf88–0x6808cf94: `checkChanceBase{Power,Normal,Contact,Bunt}`
   - 0x6808cf98–0x6808cfa4: `checkChanceCHPct{Power,Normal,Contact,Bunt}`
   - 0x6808cfa8–0x6808cfb4: `swingSpeed{Power,Normal,Contact,Bunt}Adjust`
8. Leave the try block, call `FUN_6800ac42()` and `FUN_6800ac55()` (likely SEH/unwind helpers per their placement around the handler label), return.

No thresholds or probability formulas appear in this function; the only arithmetic is the byte-fill in rule 6 and the straight parameter copies in rule 7.

**4) OUTPUT/SIDE EFFECTS**
- Writes 48 dwords to the runtime parameter block at 0x6808cef8–0x6808cfb7 (consumed elsewhere; not in this function).
- Writes 16 bytes at 0x680a2018–0x680a2027.
- May populate/modify the table at `DAT_680a2140` from numbers.inf.
- Opens and (conditionally) closes a file; temporarily modifies the FS:[0] SEH chain.
- No return value. `local_14 = 0x10` is assigned but never read in the visible code.

**5) UNCERTAIN**
- Semantics of `FUN_68082420/25ac/520a/83b7e/840be/8268d` — inferred as init/open/get-key/test/load/close; the key from `FUN_6808520a` and the meaning of the `DAT_680a2140` check are unknown.
- Exact filename string (assumed "numbers.inf" from symbol name).
- Purpose of the 0x1F–0x10 byte fill; no consumer visible here.
- Whether `FUN_6800ac42`/`FUN_6800ac55` are SEH teardown, destructors, or real logic.
- Meaning of the 4×3 index space (0–3 × 0–2) in the look/discipline tables (likely batter class × count state, but not determinable from this function).
- Whether the numbers.inf load influences the parameter block — in this code the two are independent; the PB copies run regardless.
- Call frequency (one caller, 0x68050eb0; one-time vs. per-game init not determinable here).
