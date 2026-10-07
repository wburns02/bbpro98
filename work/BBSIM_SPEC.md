# BBSIM / FastSim simulation spec (Tier 3)

Status: DRAFT. Evidence grades: tables (addresses, PB indices, defaults) are generated from code facts and spot-checked; narrative rules are GLM-Flash drafts checked against the decompile only where marked.

## Architecture (CONFIRMED by reading code)
- BBSIM.dll (animated) and FastSim.dll (no animation) are twins built from the same C++ modules (assert strings: BBSim_*.cpp / FastSim_F*.cpp). Read FastSim for pure logic, BBSIM as cross-check.
- 872 tunable ints (0x368) live in the [PlayBalance] section of PB.INI (read by BBSIM FUN_68039455 via GetPrivateProfileIntA, FastSim has its own copy). Defaults are compiled in the DLL; PBINI.TXT documents 831 and 405 of its defaults differ from the DLL: trust the DLL. Tables: work/pb_table_BBSIM.tsv, pb_table_FastSim.tsv.
- Two reader styles: (a) INIT LOADERS copy PB values into plain globals at start (e.g. FUN_68050eb0 bat-power zones, FUN_6800a7ad look/discipline/checkChance), the decision logic is in functions that read those globals by data xref; (b) DIRECT READERS call the getter (BBSIM FUN_68002cd0, FastSim FUN_68003170) at decision time (e.g. relief and pinch-hit FUN_68044cbd in FastSim, 112 params).
- The game writes pitch-outcome diagnostics when [Debug] flags are set in BBPRO.INI and Fast=0 (prlog.txt, pitchres.log, sub.log, hit.log), see RE_FINDINGS.md.


## Audited rules (CONFIRMED against decompile by Claude)
### Batter look-type selection, FastSim FUN_6800cccc (called by FUN_6800b36e)
Weighted random choice of one of 8 "type" indices (what the hitter looks for; type meaning inferred from PB names lookPrimaryType / lookBestType, not proven):
1. For each tracked type i: A[i] = count from the batter's table (+0x6b0), B[i] = value from the table at +0x29e. If B[i] == 0, A[i] -= 25, and if a second field there is > 0, A[i] -= 25 again.
2. A[cur] += 50, where cur = the current primary type.
3. With row = FUN_6800f1c0 (0..2) and col = FUN_6800f1e0 (0..2) from the game-state object at 0x68143ee0 (likely count state, not proven): A[best] += PB lookBestType<row><col>CountAdjust and A[cur] += PB lookPrimaryType<row><col>CountAdjust (tables at 0x6808cf28 and 0x6808cef8, 3x3 ints, stride 12 / 4).
4. sumA = sum A, sumB = sum B. If both 0: W[cur] = 1. If only sumA == 0: W = B. If only sumB == 0: W = A. Else W[i] = (A[i]*sumB + B[i]*sumA) * 100 / (sumA*sumB) (integer division).
5. total = sum W. If 0, result = cur. Else r = rand(total); subtract W[0..7] in order; first index where r goes negative wins. Result stored at caller+0xe5.
Caveat: the three calls Ghidra names CSplitterWnd::IsTracking are an FID false match (they supply loop bound, cur, and best). Their real identity is unresolved.
### Init loaders (CONFIRMED tables): FUN_6802baf7 (19 injury chances, u16 at 0x68113b88..), FUN_68050eb0 (20 bat zone and hit angle ints at 0x68097608..), FUN_6800a7ad (48 look/discipline/checkChance/swingSpeed ints at 0x6808cef8..).
### Relief and pinch-hit, FUN_68044cbd (112 params): draft only, part 1 audited (batter slot = (battingIndex + param_2) % 9, on-deck = (slot+1)%9, 10-slot in-game array search). Rest unaudited.

## Function index (FastSim PB-consuming functions)
| FastSim addr | module | PB params | audit |
|---|---|---|---|
| 68044cbd_part1 | chunked | 112 | CONFIRMED part 1 only |
| 68044cbd | chunked | 112 | GLM draft, unaudited |
| 6802fe35 | FastSim_FPLAYRS2 | 72 | GLM draft, unaudited |
| 6802d9c9 | FastSim_FPLAYRS2 | 72 | GLM draft, unaudited |
| 68019866 | FastSim_FGAME | 50 | GLM draft, unaudited |
| 68052bd5 | ? | 49 | GLM draft, unaudited |
| 6800a7ad | FastSim_FRUNNRS2 | 48 | CONFIRMED |
| 68023dd3 | FastSim_FGAME | 36 | GLM draft, unaudited |
| 68053248 | ? | 32 | GLM draft, unaudited |
| 680460cc | FastSim_FROSTER | 32 | GLM draft, unaudited |
| 6804684c | ? | 26 | GLM draft, unaudited |
| 68047511 | ? | 23 | GLM draft, unaudited |
| 6800da34 | FastSim_fbattr2d | 23 | GLM draft, unaudited |
| 680371f8 | ? | 22 | GLM draft, unaudited |
| 68050eb0 | FastSim_FRUNNRS2 | 20 | table CONFIRMED; narrative WRONG (FID noise) |
| 6802baf7 | FastSim_FINJURY | 19 | CONFIRMED table + flow |
| 680537ad | ? | 16 | GLM draft, unaudited |
| 6800b36e | FastSim_fbattr2d | 16 | GLM draft, unaudited |
| 6804a357 | ? | 13 | GLM draft, unaudited |
| 68040a7e | FastSim_FGAME | 11 | GLM draft, unaudited |
| 6803aad7 | ? | 11 | GLM draft, unaudited |
| 6800dcc4 | FastSim_fbattr2d | 11 | GLM draft, unaudited |
| 68036e91 | ? | 10 | GLM draft, unaudited |
| 6803122b | ? | 10 | GLM draft, unaudited |
| 6803e684 | FastSim_FROSTER | 9 | GLM draft, unaudited |
| 6800e5db | FastSim_fbattr2d | 9 | GLM draft, unaudited |
| 68036a52 | ? | 7 | GLM draft, unaudited |
| 6800e826 | FastSim_fbattr2d | 7 | GLM draft, unaudited |
| 6805ecfd | FastSim_FTHROW | 6 | GLM draft, unaudited |
| 6805d960 | ? | 6 | GLM draft, unaudited |
| 68053b36 | ? | 6 | GLM draft, unaudited |
| 6803853e | ? | 6 | GLM draft, unaudited |
| 6801a0ad | ? | 6 | GLM draft, unaudited |
| 68014f7b | ? | 6 | GLM draft, unaudited |
| 68001935 | FastSim_FACT | 6 | GLM draft, unaudited |
| 6805dd30 | FastSim_FTHROW | 5 | GLM draft, unaudited |
| 680447dc | ? | 5 | GLM draft, unaudited |
| 680346aa | ? | 5 | GLM draft, unaudited |
| 68054b0a | ? | 4 | GLM draft, unaudited |
| 68036d52 | ? | 4 | GLM draft, unaudited |
| 6800d44f | FastSim_fbattr2d | 4 | GLM draft, unaudited |
| 6805be15 | ? | 3 | GLM draft, unaudited |
| 6804a64d | ? | 3 | GLM draft, unaudited |
| 6803a5ff | ? | 3 | GLM draft, unaudited |
| 68036c6c | ? | 3 | GLM draft, unaudited |
| 6802ef90 | ? | 3 | GLM draft, unaudited |
| 6805e93b | FastSim_FTHROW | 2 | GLM draft, unaudited |
| 6805db11 | ? | 2 | GLM draft, unaudited |
| 68049d61 | ? | 2 | GLM draft, unaudited |
| 680382d9 | ? | 2 | GLM draft, unaudited |
| 68030a6f | ? | 2 | GLM draft, unaudited |
| 68003899 | ? | 2 | GLM draft, unaudited |
| 6805dc50 | ? | 1 | GLM draft, unaudited |
| 6805dab6 | ? | 1 | GLM draft, unaudited |
| 6805da5e | ? | 1 | GLM draft, unaudited |
| 6805c22c | ? | 1 | GLM draft, unaudited |
| 68053d2e | ? | 1 | GLM draft, unaudited |
| 680506fd | ? | 1 | GLM draft, unaudited |
| 6804d70e | FastSim_FRUNNER | 1 | GLM draft, unaudited |
| 68043fcf | ? | 1 | GLM draft, unaudited |
| 6803aa6b | ? | 1 | GLM draft, unaudited |
| 6803a6f0 | ? | 1 | GLM draft, unaudited |
| 68039750 | FastSim_FBALL | 1 | GLM draft, unaudited |
| 68023268 | FastSim_FFIELD | 1 | GLM draft, unaudited |
| 68022316 | ? | 1 | GLM draft, unaudited |
| 68021fca | ? | 1 | GLM draft, unaudited |
| 68020f87 | FastSim_FARCADE | 1 | GLM draft, unaudited |
| 68016855 | ? | 1 | GLM draft, unaudited |
| 6800d6be | FastSim_fbattr2d | 1 | GLM draft, unaudited |
| 6800d51a | FastSim_fbattr2d | 1 | GLM draft, unaudited |

Per-function drafts: work/spec/FUN_<addr>.md (also /mnt/nvme/bbpro98/re/spec/). 7 drafts hand-audited by Claude (6802baf7, 68050eb0, 6800a7ad, 6800cccc, 68044cbd part 1, table checks); all 73 drafts machine-audited by GLM-Flash in progress (re/spec_audit/), verdicts PARTIAL-heavy; see RE_FINDINGS for calibration of false positives. FUN_68036e91 draft corrected (pitchOutChance indices 14..23). PB.INI A/B validation: stealChance00Count=100 raised SB 9x over 10 sim days (2026-10-07).

## Open work
- Trace data xrefs from the init-loaded globals to their consumers and spec those (the actual formulas).
- Validate: pitch outcome mix from prlog.txt, substitution Chance values from sub.log, PB.INI override experiment.
