# FPS Baseball Pro '98 Reverse-Engineering Plan: Tiers 1-3
## Scope: index all 14 binaries, decode all data formats, document BBSIM engine

Plan approved 2026-10-06 by Will (allow opus, orchestration only).
Verified existing state: BBShell.dll decompiled (3,728 functions), 20 functions named; Ghidra project loaded with 14 binaries; bbtrace.log oracle verified.

---

## 1. SIZING: Functions and Decompile Footprints per Binary

**14 binaries in install directory** (verified 2026-10-06, sorted by decompile size estimate):

| Binary | Size | Est. Functions | _all.c KB (est.) | Priority | Notes |
|--------|------|-----------------|-----------------|----------|-------|
| BBSIM.dll | 960K | 1200-1400 | 400-500 | P1 | Game engine, entry points, sim logic, RNG, pitch/at-bat/baserunning |
| FastSim.dll | 760K | 800-1000 | 350-450 | P1 | Simulation support, likely reused from BBSIM or parallel logic |
| Baseball.exe | 392K | 300-400 | 150-200 | P1 | Main entry point, window/event loop, game loop orchestration |
| RemotMgr.exe | 366K | 250-350 | 120-180 | P2 | Remote/network manager, possibly multiplayer or coaching |
| Datain.exe | 324K | 250-350 | 120-180 | P2 | Data input, possibly roster/stats import, file format parsing |
| EZShell.dll | 308K | 400-500 | 200-250 | P2 | Shell framework, window management, event dispatch |
| BBShell.dll | 607K | 3728 | 2700 | DONE | UI shell, stats/lineup/draft/hof screens; decompiled, ~20 functions named |
| LineUp.dll | 245K | 250-350 | 120-180 | P2 | Lineup/play-by-play screen, play entry, baserunning UI |
| Upstats.dll | 247K | 250-350 | 120-180 | P2 | Statistics screen, column display, sorting, data binding |
| IC_Cfg.dll | 90K | 80-120 | 40-60 | P3 | Configuration, likely settings dialogs or config file I/O |
| FPS_CT.dll | 95K | 80-120 | 40-60 | P2 | File I/O control (known: opens stats DAT, Assn, PYR, STS) |
| BBCfg.dll | 10K | 20-30 | 10-15 | P3 | Small config DLL |
| ODASL.dll | 43K | 40-60 | 20-30 | P3 | Unknown, probably audio/utility |
| FPS_Ctrl.dll | 37K | 30-50 | 15-25 | P3 | Control, rebase needed (base 0x6d000000) |
| FPS_DCL.dll | 24K | 20-30 | 10-15 | P3 | Rebase needed (base 0x6d000000) |
| FPS_Pal.dll | 7.0K | 10-15 | 5-10 | P3 | Palette, likely utility |

**Estimated total:** 7,200-9,500 functions, ~4.5-5.5 MB decompiled _all.c across 14 binaries.

**BBSIM.dll is the critical path for Tier 3.** It is the game engine and contains all sim logic, formula tables, RNG, entry points. FastSim.dll may be parallel or delegated code. Baseball.exe orchestrates the game loop. LineUp.dll handles play UI (pitch/swing/bunt decisions).

**Tier 1 effort is distributed but front-loaded:** Decompile all 14 (Ghidra, no GLM cost), then label functions in parallel lanes per subsystem. BBSIM labeling demands the most care.

---

## 2. MILESTONES WITH ACCEPTANCE GATES

### M0: Measure (Pre-tier 1)
**Objective:** Establish the decompile snapshot and baseline metrics.

**Task:** Run Ghidra regen for all 14 binaries, collect _functions.tsv for each.
```bash
cd /mnt/nvme/bbpro98
for BIN in Baseball.exe BBSIM.dll FastSim.dll BBShell.dll LineUp.dll Upstats.dll EZShell.dll RemotMgr.exe Datain.exe IC_Cfg.dll FPS_CT.dll BBCfg.dll ODASL.dll FPS_Ctrl.dll FPS_DCL.dll FPS_Pal.dll; do
  bash ghidra_scripts/gh.sh regen "$BIN" && echo "OK: $BIN"
done
# After all complete: for d in index/*/; do wc -l "$d/_all.c" "$d/_functions.tsv"; done
```

**Acceptance Gate M0:**
- [ ] All 14 binaries have _all.c + _functions.tsv in /mnt/nvme/bbpro98/index/<Name>/
- [ ] _functions.tsv row count matches 3,728 + ~4,000-6,000 for others (sanity check)
- [ ] No BBSIM/FastSim _all.c is empty
- [ ] Byte counts logged to /mnt/nvme/bbpro98/work/M0_metrics.txt

**Duration:** 2 hours (Ghidra is slow; run in parallel on multiple Ghidra instances if available, else sequential).

**Landmine:** Ghidra project lock. If pyghidra-mcp stalls, `gh.sh stop` and wait 5s before restart.

---

### M1: Label Tier-1 Functions (P1 binaries: BBSIM, FastSim, Baseball)

**Objective:** Every function in BBSIM, FastSim, and Baseball labeled by subsystem with evidence class.

**Evidence grades (highest to lowest):**
- `CONFIRMED`: Hook trace, screenshot, or verified CRT identifier (malloc, strstr, strlen, printf, fopen, etc.).
- `XREF_CONFIDENT`: Known callees (e.g., calls pitch-generation, calls GDI), no contradictions.
- `STRING_XREF`: String xref (e.g., error message, config key), high confidence.
- `PATTERN_GUESS`: Heuristic only (e.g. lots of additions = math), unconfirmed.
- `UNKNOWN`: Insufficient data.

**Subsystem labels:**
- `CRT`: C runtime (malloc, free, strlen, strcpy, memset, fopen, printf, etc.). Use standard CRT signatures.
- `MATH`: Arithmetic ops, probability, RNG.
- `IO_FILE`: File read/write (Assn, PYR, Stats DAT, STS, SHELL.VOL, INI, BBPRO.NNN).
- `IO_REGISTRY`: Win32 registry or config file parsing.
- `STRUCT_INIT`: Object/state initialization.
- `SIM_PITCH`: Pitch generation, speed/movement/location, pitch types.
- `SIM_SWING`: Batter swing decision, contact formulas, outcome generation.
- `SIM_FIELD`: Fielding, putout/error outcomes, positioning.
- `SIM_BASE`: Baserunning, steal attempts, advance logic.
- `SIM_INJURY`: Injury generation, durability reduction, rating effects.
- `SIM_FATIGUE`: Fatigue accumulation, recovery, performance scaling.
- `SIM_LINEUP`: Active roster management, substitutions, pinch-hit decisions.
- `SIM_GAME`: Game loop, inning/half-inning logic, game-end conditions.
- `RATING`: Player ratings to stat conversion, regression, aging.
- `SEASON`: Season start/end, standings, draft.
- `UI_MAIN`: Main menu, navigation, window creation.
- `UI_STATS`: Statistics screen (BBShell or Upstats), grid rendering, column logic.
- `UI_LINEUP`: Lineup screen (LineUp.dll), play selection, pitch calls.
- `UI_DIALOG`: Dialog boxes, message boxes.
- `UI_RENDER`: Graphics rendering, palette, sprite loading.
- `GDI`: Direct Win32 GDI calls (SetPixel, Rectangle, etc.). Mark as utility.
- `WIN32`: Direct Win32 calls (CreateWindow, PostMessage, etc.). Mark as utility.
- `UNKNOWN`: Insufficient evidence.

**CRITICAL: All P1 labels must include evidence.** Cheap models (GLM-Flash) draft labels; any label that Tier 3 (sim engine) relies on must be confirmed before ship.

**Task per binary (GLM-Flash, Hive.ai, \`z-ai/glm-5.3-flash\`):**

1. **BBSIM.dll:** Split into 4-6 GLM passes. Each pass reads ~150-200 functions from _all.c (by address ranges), identifies subsystem + evidence grade. Output: TSV with addr, name, subsystem, evidence, comment (xref summary or string).

2. **FastSim.dll:** 3-4 passes, same method.

3. **Baseball.exe:** 2-3 passes, lighter load.

**Landmine: CRT drift.** Windows ships many CRT variants (msvcrt, msvcp, etc.). Ghidra may misidentify malloc signatures. Verify malloc/free against known thunks in the binary before trusting the label.

**Acceptance Gate M1:**
- [ ] All 3 binaries have _functions_labeled.tsv (addr, name, subsystem, evidence, comment) in their index dirs.
- [ ] No function is UNKNOWN; all have at least PATTERN_GUESS.
- [ ] 100 random functions sampled and spot-checked: >=80% are XREF_CONFIDENT or higher, <5% fail obvious sanity checks (e.g. math label on obvious GDI call).
- [ ] BBSIM xref graph valid: functions labeled SIM_* call each other with reasonable logic (pitch -> swing -> field, no loops between dissimilar subsystems).

**Landmine: Thiscall stack args.** Handoff notes thiscall helpers at 68043400/680436c0 take 2 stack args + ret 8. Ghidra may parse prototype wrong. Check any high-confidence function that Tier 3 uses.

---

### M2: Label Tier-2 Functions (P2 binaries: EZShell, LineUp, Upstats, RemotMgr, Datain, FPS_CT)

**Objective:** Same subsystem labeling as M1, but lighter verification (PATTERN_GUESS is acceptable).

**Task:** 6 parallel GLM-Flash passes (one per binary). Each outputs _functions_labeled.tsv.

**Acceptance Gate M2:**
- [ ] All 6 binaries have _functions_labeled.tsv.
- [ ] P2 binaries can be cross-checked by known overlaps (e.g. LineUp.dll calls UI_STATS functions in BBShell.dll or Upstats.dll). Spot-check 20 callsites.

**Duration:** 6-8 hours (GLM-Flash, parallel).

---

### M3: Label Tier-3 Functions (P3 binaries: IC_Cfg, ODASL, FPS_Ctrl, FPS_DCL, FPS_Pal, BBCfg)

**Objective:** Labeling with minimal verification (PATTERN_GUESS sufficient).

**Task:** 2 GLM-Flash passes (batch 6 binaries, one pass per 3).

**Acceptance Gate M3:**
- [ ] All 6 binaries have _functions_labeled.tsv.

**Duration:** 2-4 hours.

---

### M4: Tier-1 Verification Loop (P1 subsystem confidence)

**Objective:** Confirm ~50 high-stakes labels in BBSIM via hook traces and screenshots.

**High-stakes functions (examples, to be discovered):**
- SIM_PITCH entry point: called once per pitch, returns speed/movement/type.
- SIM_SWING entry point: called once per swing attempt, returns contact/outcome.
- RATING formula: maps player ratings to ability modifiers.
- RNG seed/next: called every decision, must identify and seed recovery path.
- Fatigue scaling: applied to contact/power/speed, used every at-bat.

**Verification plan:**
1. For each high-stakes function, add a hook in bbfix.c that logs the function entry, args, return value, caller.
2. Replay a captured game (or run a sim day with hook=1 in bbfix.ini).
3. Grep bbtrace.log for the function logs.
4. Cross-reference the log against the known game state (box score, injury list, fatigue visual).
5. Update the evidence grade to CONFIRMED if the log matches expected behavior, XREF_CONFIDENT if plausible but not fully verified.

**Spot-check gates:**
- [ ] >=20 high-stakes functions have CONFIRMED or XREF_CONFIDENT evidence.
- [ ] 0 high-stakes functions labeled are later found incorrect via hook trace.
- [ ] Spot-check 10 random PATTERN_GUESS labels: run a game replay and see if the function is even called; demote to UNKNOWN if not, or upgrade to XREF_CONFIDENT if it is and behavior looks right.

**Duration:** 8-12 hours (hook development + replay testing + analysis).

---

### M5: Data Format Gaps (Tier 2)

**Objective:** List all data formats, mark which are decoded, list gaps.

**Known formats (from NOTES_stats_format.md + HANDOFF.md):**

| Format | File(s) | Status | Notes |
|--------|---------|--------|-------|
| PYR | player/*.pyr | DECODED | dump_pyr.py in research/; starting ratings only (stars never change). |
| ASN | Assn/*.* | PARTIAL | Container format known (table+index pages). Fields unknown. Live ratings live here. |
| Stats DAT | Stats/mlbpa97.DAT | PARTIAL | Decoded: scope 1/2/3, 40-byte batting, 70-byte pitching line. TODO: scope 3 mapping, split types, c16..c34 pitcher fields. |
| STS | StatSets/*.STS | DECODED | 117 bytes: ver, name[33], bat ids[9], pit ids[9]. |
| SHELL.VOL | SHELL.VOL | PARTIAL | VOLM archive. MENU.REQ, DIAL.REQ, gadget specs inside. Widening experiment 2026-10-06 succeeded (extra gadgets render). |
| DIAL.REQ | (inside SHELL.VOL) | PARTIAL | Gadget/UI resource file. Block 13 = stats grid rows. Extra gadgets added via build_wide_vol.py. |
| MENU.REQ | (inside SHELL.VOL) | UNKNOWN | Menu definitions, TBD. |
| Hilights/*.tap | (10-15 per season) | UNKNOWN | Highlight data for play-by-play color, unknown format. |
| bb.cfg / BBPRO.INI | (install root) | PARTIAL | Text config, INI format. bbfix.ini (our hook config) overlays [widen], [trace]. |
| FNX files (0-5.FNX) | (install root) | UNKNOWN | Unknown format, possibly cached data or temp files. |
| ARCDBM.DAT / BPIDBM.DAT | (install root) | UNKNOWN | Database files, unknown format. Possibly team/player databases. |
| Archive/*.* | Archive/ | UNKNOWN | Archive directory, unknown format. Possibly mods or exported data. |

**Task:** Read existing code + notes to find any additional decoders or oracles. Prioritize Stats DAT (used for league stats), ASN (live ratings), and Hilights.

**Acceptance Gate M5:**
- [ ] Master list documented in /home/will/bbpro98/work/DATA_FORMATS.md with status + decoder path.
- [ ] ASN format at least partially decoded (table layout, known fields).
- [ ] Hilights format is attempted (if oracle found via bbcard or in-game screens).

---

### M6: Round-Trip Test Data Formats (Tier 2 execution)

**Objective:** Each format in M5 has a read + write pair that produces bit-identical output.

**Formats with high priority (Tier 2):**
- Stats DAT: reader + write already exist? (parse_stats.py?). Verify on a snapshot (s5) and s10.
- PYR: dump_pyr.py reads; writer needed, round-trip test.
- ASN: reader/writer from existing code or new.
- STS: simple reader/writer (117 bytes), easy.
- Hilights: reader/writer (unknown size/format).
- SHELL.VOL: read (pyghidra_volm.py exists?), write verified 2026-10-06 (build_wide_vol.py), round-trip test.

**Task (GLM-Flash or by hand):**
1. For each format, write or verify round-trip test: `read(file) | write(file2); diff file file2 == zero bytes`.
2. Run on live snapshots (s5, s10).
3. Document any versioning or conditional fields (e.g. Stats DAT v1.0 != v1.1).

**Acceptance Gate M6:**
- [ ] Round-trip tests pass on >=2 snapshot seasons (s5, s10) for all P1 formats (Stats DAT, PYR, ASN, STS).
- [ ] P2 formats (Hilights, SHELL.VOL, MENU.REQ) have readers + at least one write test.
- [ ] Test scripts in /home/will/bbpro98/tests/fmt_*.py (data formats test suite).

---

### M7: BBSIM Entry Points and ABI

**Objective:** Document every function BBSIM.dll exports, and the call signature / behavior of the game engine entry points.

**Task (Tier 3, brain work, no GLM):**
1. Read BBSIM._all.c and filter for exported functions (check export table in binary header via `objdump -T` or Ghidra export list).
2. For each export, determine: call signature (args, return), caller (Baseball.exe or other), frequency (every pitch? every game?), effect on game state.
3. Build a map of entry points: e.g. `StartGame(season, team, opponent) -> game_state*`, `SimPitch(game_state, batter_id, pitcher_id) -> pitch_result`, etc.
4. Cross-check against Baseball.exe game loop to verify call sequence.

**Acceptance Gate M7:**
- [ ] >=10 entry points documented with signature + caller chain.
- [ ] Game loop sequence (start -> play -> end) traced and verified against Baseball.exe disasm.

---

### M8: BBSIM State Structs

**Objective:** Define all major state structs (game state, at-bat state, pitch result, player ratings, injury, fatigue, etc.) with field offsets and types.

**Task (Tier 3, brain + Sonnet verification):**
1. Disassemble BBSIM functions that initialize or mutate game state.
2. Identify struct initialization patterns (memset, field assignments at fixed offsets).
3. Build struct definitions (C struct or comments with field names + offsets).
4. Cross-check against runtime values from hook traces (see M4).

**Landmine: Nested structs.** BBSIM likely uses arrays-of-structs for players, teams, innings. Verify stride (array element size) via pointer arithmetic.

**Acceptance Gate M8:**
- [ ] >=5 major structs documented (game_state, at_bat_state, pitch_result, player_state, team_state).
- [ ] All field offsets verified to match at least one known memory trace.

---

### M9: Pitch-by-Pitch Logic (BBSIM sim engine)

**Objective:** Document the pitch outcome formula: how pitch type/speed/movement + batter ratings + pitcher ratings + fatigue -> contact outcome (miss, foul, single, HR, etc.).

**Task (Tier 3, brain + DeepSeek-Flash holdout checks):**
1. Isolate the function(s) that compute pitch outcome (marked SIM_PITCH or SIM_SWING in M1).
2. Reverse-engineer the formula: what fields are read from pitch and batter/pitcher state, what operations are applied, what is the output?
3. Identify rating-to-outcome mapping: does the code have lookup tables (e.g. "contact rating 75" -> "base chance of contact = 0.67")? Where?
4. Identify RNG calls: what is the RNG function, when is it seeded, how many calls per pitch?
5. Document as pseudo-code or decision tree.

**Validation:** Capture 100 pitch outcomes from a live game (via hook trace). Predict outcome via the formula. Compare predicted distribution (e.g. 30% contact, 10% miss, 60% foul) against observed. Statistical test (chi-square) should pass p>0.05.

**Landmine: Fixed-point math.** Handoff notes "fixed-point conventions." Win32 baseball sims often use Q16 (16-bit fractional) or Q8.8. Look for scale factors (divide by 256, multiply by 0x100, etc.).

**Acceptance Gate M9:**
- [ ] Pitch outcome formula documented (pseudo-code + one example walk-through).
- [ ] >=2 lookup tables identified (e.g. contact%, power%, speed%, endurance%).
- [ ] RNG function identified (name, seed location, state).
- [ ] Predicted vs observed distribution on 100 pitches: chi-square p>0.05.

---

### M10: At-Bat / Baserunning / Fielding / Injury / Fatigue Logic

**Objective:** Document the complete at-bat loop, baserunning AI, fielding outcomes, injury accumulation, and fatigue scaling.

**Task (Tier 3, brain + GLM-Flash spot checks):**
1. At-bat: after pitch outcome (single/double/HR/out), how do runners advance? Are there baserunning AI decisions (steal, aggressive advance)?
2. Fielding: after a hit, how is the fielder/position chosen? What is the error chance? What is a hit's location/difficulty (BABIP-like)?
3. Injury: when is an injury chance computed (slide, collision, overuse)? How does injury rating change durability? Does the game show an injury dialog in-game?
4. Fatigue: when is fatigue applied (every at-bat? every inning?)? How does fatigue rating affect other stats (contact/power/speed)?

**Validation:** Instrument the at-bat function. Replay a game. Compare predicted outcomes (e.g. 162 games, team totals) against in-game statistics screen.

**Acceptance Gate M10:**
- [ ] At-bat, baserunning, fielding, injury, fatigue logic documented (pseudo-code, 5 examples each).
- [ ] 1 full season simulated and compared against in-game stats on Association > Statistics > Teams view (batting PA, R, H, 2B, 3B, HR, RBI, BB, SO within 5% of observed).

---

### M11: Rating to Performance Formulas

**Objective:** Document how player ratings (contact, power, speed, endurance, fielding, pitching) map to ability modifiers applied each at-bat.

**Task (Tier 3, brain + Sonnet):**
1. Find the function that applies ratings to pitch outcome (likely called from SIM_SWING or SIM_PITCH entry).
2. Isolate the formula: e.g. contact_ability = f(contact_rating, fatigue, injury), then contact_chance = base_chance * contact_ability.
3. Verify that ratings are used (not just loaded then discarded).
4. Check for nonlinearities (e.g. power ratings < 50 vs > 50 behave differently).

**Landmine: Regression.** Some older sims regress player ratings year-over-year. Look for age checks or "peak year" references.

**Acceptance Gate M11:**
- [ ] 5+ rating-to-formula mappings documented (contact, power, speed, endurance, fielding/pitching).
- [ ] Nonlinearities or thresholds identified, if any.
- [ ] Formula output spot-checked against hook traces (e.g. contact_ability 0.75 observed in player decision trace).

---

### M12: RNG and Seed Recovery

**Objective:** Identify the RNG function, its state, and whether a game seed is recoverable (enables replay).

**Task (Tier 3, brain):**
1. Find all calls to RNG (likely srand/rand or a custom generator).
2. Determine if RNG is seeded at game start (via date, file-based seed, player choice).
3. Determine if the seed is logged (bbtrace.log or memory dump).
4. If seed is recoverable, document the recovery path (e.g. read from BBPRO.INI, read from memory at addr 0x68xxxxx).

**Landmine: Multiple RNGs.** Some sims use separate RNG for different subsystems (pitch locations vs injury chance). Look for pattern.

**Acceptance Gate M12:**
- [ ] RNG function identified (name, location).
- [ ] RNG state/seed location known.
- [ ] Seed recovery path documented or marked UNKNOWN.

---

## 3. LANDMINES (Verify Before Acting)

### Code-level landmines
- **Thiscall stack args.** Handoff notes helpers at 68043400/680436c0 take 2 stack args + ret 8. Check Ghidra prototype for any function calling these.
- **CRT linking.** Multiple CRT versions in the binary (msvcrt variants). Verify malloc/free symbols before trusting identification.
- **Fixed-point math.** Unknown Q-format (Q8.8? Q16?). Look for scale constants.
- **Base addresses.** Preferred bases: Baseball.exe 0x400000, BBShell 0x68000000, LineUp 0x6b000000, Upstats 0x6c000000, FPS_Ctrl/FPS_DCL 0x6d000000. If a binary is rebased (e.g. 0x10000000 conflicts), Ghidra xrefs may be wrong. Check EZShell rebase status.

### Project-level landmines
- **Stale _all.c.** After Ghidra renames (rename a function in the GUI), _all.c is not auto-updated. Always run `gh.sh regen <BINARY>` after batch renames.
- **Ghidra project lock.** pyghidra-mcp sometimes stalls on multi-binary edits. If stuck, `gh.sh stop` and wait 5s before restart.
- **Wine bbtrace.log rotation.** Max 512 KB by default. If a hook spams the log, truncate or disable that hook.
- **Hook injection failure.** If bblaunch injects bbfix.dll but it crashes on load (unresolved import, bad alloc), the game will crash silently. Check wine.log in logs/<ts>/ dir.

### Data-level landmines
- **SHELL.VOL rebuild.** VOLM archive has a final u32 sentinel at dir-end. Must update when adding/resizing resources. build_wide_vol.py handles it; verify on rebuild.
- **Stats DAT versioning.** Multi-version container; scope fields may differ by version. Don't assume s5 == s10.
- **PYR starting ratings only.** Live ratings in ASN, not PYR. Don't patch PYR for in-game rating changes.
- **Assn format unknowns.** ASN is a container with unknown table layout. May have version fields or conditional sections. Read from game save snapshots to reverse-engineer.

---

## 4. ACCEPTANCE CRITERIA BY TIER

### Tier 1: MAP (M0-M4)

**Acceptance gate (all-or-nothing):**
- [ ] All 14 binaries have _functions_labeled.tsv with subsystem + evidence for 100% of functions.
- [ ] **Spot-check:** 50 random functions, all label grades are XREF_CONFIDENT or higher. <5% are PATTERN_GUESS.
- [ ] **BBSIM-specific:** >=20 SIM_* functions are CONFIRMED or XREF_CONFIDENT, verified via hook trace or xref chain.
- [ ] **Cross-check:** Spot-check 20 callsites between binaries (e.g. LineUp calls BBShell UI functions). Xref map is correct.
- [ ] Deliverable: /mnt/nvme/bbpro98/work/TIER1_LABELED_BINARIES.md (summary table: binary, function count, CONFIRMED %, XREF % PATTERN_GUESS %).

### Tier 2: DATA FORMATS (M5-M6)

**Acceptance gate:**
- [ ] Master list of 12+ formats documented (status = DECODED / PARTIAL / UNKNOWN).
- [ ] >=5 formats (Stats DAT, PYR, ASN, STS, SHELL.VOL) have reader + writer.
- [ ] Round-trip tests pass on >=2 live snapshots (bit-identical output).
- [ ] Deliverable: /mnt/nvme/bbpro98/work/DATA_FORMATS.md (format + decoder path + test result).

### Tier 3: SIM ENGINE (M7-M12)

**Acceptance gate:**
- [ ] Entry points: >=10 BBSIM exports documented (name, signature, caller, purpose).
- [ ] State structs: >=5 major structs with field offsets and verified runtime values.
- [ ] Pitch-by-pitch: formula documented (pseudo-code), RNG identified, predicted distribution within 5% of observed on 100 pitches.
- [ ] At-bat / baserunning / fielding / injury / fatigue: logic documented, 1 full season prediction vs in-game stats within 5%.
- [ ] Rating formulas: >=5 mappings (contact -> ability, etc.), verified via hook trace or formula walk-through.
- [ ] RNG: function identified, seed recovery path documented or marked UNKNOWN.
- [ ] Deliverable: /mnt/nvme/bbpro98/work/BBSIM_SPEC.md (15 sections Artifact, see final-report requirements).

---

## 5. TASK SPECS FOR GLM-FLASH (Hive.ai, z-ai/glm-5.3-flash)

All task specs include full source pasted (never assume GLM can see files it wasn't given). Output is TSV or code, never prose. Verify builder output before trusting; do not accept self-report.

### Task Template: Function Labeling (Tier 1, any binary)

**Input:** Binary name (e.g. BBSIM.dll), address range (e.g. 0x68000000 to 0x68200000), decompiled _all.c excerpt (functions in range).

**Output contract:**
```
addr	name	subsystem	evidence	comment
0x68000000	FUN_68000000	CRT	CONFIRMED	malloc wrapper, alloc size from param
0x68000100	FUN_68000100	SIM_PITCH	XREF_CONFIDENT	calls pitch_speed(batter_id, pitcher_id), calls pitch_move()
0x68000200	FUN_68000200	UNKNOWN	PATTERN_GUESS	arithmetic only, no string/xref
```

**Instructions:**
1. For each function in range:
   a. Read decomp to identify what it does (loops? struct access? calls to known functions?).
   b. Check for string xrefs (e.g. "malloc failed", "Contact rating").
   c. Check for known CRT signatures (malloc, free, strlen, strcpy, fopen, printf, memset, qsort, rand, srand).
   d. Check for known subsystem calls (e.g. calls to DrawText, SetPixel, CreateWindow -> UI; calls to functions labeled SIM_PITCH -> SIM_SWING).
   e. Assign subsystem + evidence using the grades and labels from Section 1.
   f. Output TSV row.
2. CRT functions: check against list of known CRT symbols (will be provided separately).
3. If function is <10 lines and clearly a thunk, mark as CRT.
4. If decomp is truncated or malformed, mark as UNKNOWN.

**Estimated cost:** 5K tokens per 150 functions (one pass, one GLM call for one batch).

**Verification step (not GLM, done by human):** Spot-check output for sanity (no function labeled UI_STATS that has no GDI calls, no SIM_PITCH that never calls batter/pitcher rating lookup, etc.). Re-run batch if >10% are suspicious.

---

### Task Template: Data Format Round-Trip Test

**Input:** Format name (e.g. Stats DAT), reader path (e.g. /home/will/bbpro98/scripts/parse_stats.py), snapshot season (e.g. s5).

**Output contract:**
```
format: Stats DAT
snapshot: s5
reader: parse_stats.py
writer: write_stats.py
read_size: 23487232 bytes
write_size: 23487232 bytes
match: YES (byte-identical)
timestamp: 2026-10-06T15:00:00Z
```

**Instructions:**
1. Run `python reader /path/to/stats/mlbpa97.DAT > /tmp/parsed.json`.
2. Run `python writer /tmp/parsed.json > /tmp/output.DAT`.
3. `diff /path/to/stats/mlbpa97.DAT /tmp/output.DAT` and record match.
4. If mismatch, record first differing byte offset and byte value (expected vs actual).

**Verification:** GLM does not run this task. A human (with a work harness script) runs the test, logs the result, compares against expected on >=2 snapshots.

---

## 6. TIERED-BUILD-LOOP TASK BREAKDOWN

**Orchestration: Claude (this plan, M0-M12 gating).**
**Build: GLM-Flash (Hive.ai) for M1-M3 labeling, M6 round-trip tests.**
**Test/Verify: Sonnet for M4 hook verification, M9-M12 formula validation.**
**Holdout checks: DeepSeek-Flash on M1 labeling before ship.**

### Parallelism
- **M0 Decompile:** Sequential or Ghidra-parallel if feasible (~2 hours).
- **M1-M3 Labeling:** Parallel GLM-Flash lanes per binary (14 binaries, 6-9 parallel passes, 6-8 hours).
- **M4 Verification:** Sequential (one function at a time, hook dev + replay), 8-12 hours.
- **M5-M6 Format work:** Parallel (research ASN, PYR, Hilights) + round-trip tests, 4-6 hours.
- **M7-M12 Tier 3:** Sequential (brain work, no parallelism, Claude + Sonnet), 20-30 hours.

### Cost Estimation

**GLM-Flash (Hive.ai, \`z-ai/glm-5.3-flash\`):**
- M1 (BBSIM + FastSim + Baseball): 3 binaries, ~3,300 functions, 5 passes total, ~5K tokens per pass = 25K tokens. Cost: ~$1.25.
- M2 (6 P2 binaries): ~2,500 functions, 6 passes, ~4K tokens per pass = 24K tokens. Cost: ~$1.20.
- M3 (6 P3 binaries): ~1,500 functions, 2 passes, ~2K tokens per pass = 4K tokens. Cost: ~$0.20.
- **M1-M3 Total: 53K tokens, ~$2.65.**

**Sonnet (verification, test fix loops):**
- M4 hook verification + fixes: ~10K tokens. Cost: ~$1.
- M9-M12 validation + holdout fixes: ~15K tokens. Cost: ~$1.50.
- **Sonnet Total: 25K tokens, ~$2.50.**

**DeepSeek-Flash (holdout check on M1 labels, if Hive labeling is risky):**
- ~5K tokens per pass, 2 passes = 10K tokens. Cost: ~$0.02.

**Claude (this orchestration, escalations):**
- ~0 for plan. ~5K tokens for mid-task escalations if GLM fails. Cost: ~$0.50.

**Estimated total cost: ~$7-8. Time (serial CLIs, no parallelism losses): 40-50 hours over 2-3 weeks.**

---

## 7. PROGRESS CHECKPOINT SCHEME (progress.md updates)

Update `/home/will/bbpro98/work/progress.md` after each milestone completes:

```markdown
## TIER 1: MAP
- [ ] M0: Decompile snapshot (all 14 binaries _all.c + _functions.tsv, metrics logged)
- [ ] M1: Label P1 (BBSIM, FastSim, Baseball) with subsystem + evidence (3 binaries)
- [ ] M2: Label P2 (EZShell, LineUp, Upstats, RemotMgr, Datain, FPS_CT) (6 binaries)
- [ ] M3: Label P3 (IC_Cfg, ODASL, FPS_Ctrl, FPS_DCL, FPS_Pal, BBCfg) (6 binaries)
- [ ] M4: Verify P1 subsystems via hook trace (>=20 functions CONFIRMED)
- [ ] SHIP: TIER1_LABELED_BINARIES.md + all _functions_labeled.tsv

## TIER 2: DATA FORMATS
- [ ] M5: List formats + status, gaps
- [ ] M6: Round-trip tests (Stats DAT, PYR, ASN, STS, SHELL.VOL)
- [ ] SHIP: DATA_FORMATS.md + test suite

## TIER 3: SIM ENGINE
- [ ] M7: Entry points (10+ exports from BBSIM)
- [ ] M8: State structs (5+ major structs, field offsets)
- [ ] M9: Pitch-by-pitch logic (formula + RNG + distribution validation)
- [ ] M10: At-bat/baserunning/fielding/injury/fatigue (full season validation)
- [ ] M11: Rating to performance formulas (5+ mappings)
- [ ] M12: RNG function + seed recovery
- [ ] SHIP: BBSIM_SPEC.md (Artifact, 15 sections)
```

---

## 8. FINAL REPORT REQUIREMENTS (Tier 3 ship)

**Deliverable:** `/home/will/bbpro98/work/BBSIM_SPEC.md` published as Artifact (read-only, 7 sections minimum).

**Sections (each ~500-1000 words, with code examples):**

1. **Overview & Architecture** (game engine, entry points, call graph).
2. **State Structs** (game, at-bat, pitch result, player, team, with field offsets).
3. **Pitch Generation** (pitch type/speed/movement formula, RNG, examples).
4. **Swing Outcome** (contact chance, outcome type, formula + examples).
5. **Fielding & Baserunning** (advance logic, error chance, stolen base AI).
6. **Injury & Fatigue** (accumulation, rating effects, recovery).
7. **Rating to Performance** (contact -> contact ability, power -> power ability, etc., tables + formulas).
8. **RNG & Replay** (RNG function, seed, recovery path).
9. **Validation Results** (100-pitch distribution chi-square, full-season team totals vs in-game stats).
10. **Open Questions** (any unknowns, limitations, future work).
11. **Code Index** (BBSIM function names + addresses for quick lookup).
12. **Glossary** (Q-format explanation, thiscall convention, etc.).
13. **Appendix A: Hook Traces** (sample bbtrace.log output + interpretation).
14. **Appendix B: Round-Trip Data Tests** (Stats DAT, PYR examples).
15. **Appendix C: Formula Derivation** (worked examples, formula discovery process).

**Verification:** Artifact must link to all evidence (bbtrace.log snippets, screenshot, code listings from Ghidra). No unsourced claims.

---

## 9. AUTONOMOUS LOOP RULES

**No check-ins except:**
- If GLM-Flash output fails >3 times on the same batch (real blocker, needs escalation to Claude).
- If a hook crashes the game (stop, debug, document, retry).
- If a data format round-trip test fails (investigate, may need ASN format spec work first).
- If a verification (M4, M9-M12) shows large discrepancies (>20% error), pause and analyze.
- External sends (export data, push to git, email Will).
- Destructive production actions (rebase binaries, modify live game state).
- User-only credentials (Hive API key, GitHub token).

**Otherwise:** Act, log, verify, iterate. Ship on green gates.

---

## SUMMARY (15 lines)

1. **Sizing:** 14 binaries, ~7,200-9,500 functions, ~4.5-5.5 MB decompiled code. BBSIM (960K, 1200-1400 functions) is critical path.
2. **Tier 1 MAP (M0-M4):** Decompile all binaries, label every function by subsystem (CRT/IO/SIM/UI/util) + evidence grade. Verify P1 (BBSIM/FastSim/Baseball) via hook traces.
3. **Tier 2 DATA (M5-M6):** Decode PYR/ASN/Stats-DAT/STS/SHELL.VOL/Hilights. Round-trip test each format (read then write bit-identical). Cost: 0 GLM tokens.
4. **Tier 3 SIM (M7-M12):** Document BBSIM entry points, state structs, pitch/swing/field/injury/fatigue logic, RNG. Validate full-season team totals vs in-game stats within 5%.
5. **Parallelism:** M0 sequential (2h), M1-M3 parallel GLM lanes (6-8h), M4 sequential (8-12h), M5-M6 parallel (4-6h), M7-M12 sequential brain (20-30h). Total: 40-50 hours.
6. **Cost:** GLM-Flash (Hive) ~$2.65, Sonnet ~$2.50, DeepSeek holdout ~$0.02, Claude ~$0.50. Total ~$7-8.
7. **Verification:** Spot-checks + hook traces (M4), round-trip tests (M6), statistical distribution validation (M9), full-season team totals (M10). Threshold: >=80% XREF_CONFIDENT labels, chi-square p>0.05, season totals <5% error.
8. **Landmines:** Thiscall stack args (0x68043400/0x680436c0), CRT linking ambiguity, stale _all.c after Ghidra renames, SHELL.VOL sentinel, Stats DAT versioning, BBSIM fixed-point format unknown.
9. **Task spec template:** Binary name, address range, _all.c excerpt -> TSV (addr, name, subsystem, evidence, comment). No self-report, verify output.
10. **Autonomous loop:** No check-ins unless GLM fails 3x, hook crashes, data format fails, verification >20% error, external send, destructive action, or user credential needed.
11. **Deliverables:** M0 metrics, M1-M3 _functions_labeled.tsv per binary, M4 verified hook traces, M5-M6 DATA_FORMATS.md + test suite, M7-M12 BBSIM_SPEC.md (Artifact, 15 sections).
12. **Highest-stakes subsystems:** SIM_PITCH entry + RNG (pitch generation), SIM_SWING contact formula (outcome), RATING mapping (ability modifiers), FATIGUE scaling (performance).
13. **Evidence grades:** CONFIRMED (hook/screenshot), XREF_CONFIDENT (xref chain or string), STRING_XREF (string match), PATTERN_GUESS (heuristic), UNKNOWN. All P1 labels must be >XREF_CONFIDENT before ship.
14. **Data formats:** 12 identified (PYR decoded, Stats DAT partial, ASN unknown, STS simple, SHELL.VOL partial, Hilights unknown, ARCDBM/FNX/Archive unknown). Round-trip tests on s5 and s10.
15. **Finale:** Tier 3 validates game engine by predicting 100 pitch outcomes and 1 full season of team stats. If distribution matches in-game (chi-square p>0.05, totals <5% error), the sim engine spec is complete and correct.
