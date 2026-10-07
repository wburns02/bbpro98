# BBSIM / FastSim simulation spec (Tier 3)

Status: DRAFT, audit pass 2 (2026-10-07). 73 function drafts; 70 audited by GLM-Flash against the FastSim decompile with the verified PlayBalance-getter identity (FUN_68003170(idx) = *(u32*)(&DAT_6808fde0+idx*4)) and per-draft pb_table rows injected: 55 MATCH, 17 PARTIAL (each PARTIAL draft carries a CORRECTIONS section quoting the findings); 1 draft (FUN_68054d4a_consumer) unaudited, its slice exceeded the audit budget twice. Draft headers' params= field (which counted PB-getter calls) was replaced with real decompile signatures. Independent validation: PB.INI stealChance00Count experiment (SB 8.9x, CS 11.5x, outside the arm-pair null spread; RE_FINDINGS.md). Pass 1 (untrained prompt) was discarded: 24/25 PARTIALs were false positives from getter opaqueness; re/spec_audit_v1 keeps them.

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
### Relief and pinch-hit, FUN_68044cbd (this,2 args; the old "112 params" header counted PB-getter calls): draft in 2 chunks, see audit for part 1 (batter slot = (battingIndex + param_2) % 9, on-deck = (slot+1)%9, 10-slot in-game array search). Rest unaudited.

## Function index (FastSim PB-consuming functions)
| FastSim addr | module | PB params | audit |
|---|---|---|---|
| 68044cbd_part1 | chunked | 112 | CONFIRMED part 1 only |
| 68044cbd | chunked | 112 | PARTIAL (pass 2, see re/spec_audit/FUN_68044cbd.txt) |
| 68 MATCH (audit pass 2) RS2 | 72 | GLM draft, unaudited |
| 68 MATCH (audit pass 2) RS2 | 72 | GLM draft, unaudited |
| PARTIAL (pass 2, see re/spec_audit/FUN_68019 MATCH (audit pass 2) M draft, unaudited |
| 68052bd5 | ? |  PARTIAL (pass 2, see re/spec_audit/FUN_6800a7 PARTIAL (pass 2, see re/spec_audit/FUN_68023 PARTIAL (pass 2, see re/spec_audit/FUN_68053248.txt)  | MATCH (audit pass 2) |
| 68023dd3 | FastSim_FGAME | 36 | GLM draft, unaudited | MATCH (audit pass 2)  GLM draft, unaudited |
| 680460cc | F MATCH (audit pass 2) GLM draft, unaudited |
 PARTIAL (pass 2, see re/spec_audit/FUN_680371f8.txt) GLM dr MATCH (audit pass 2) ft, unaudited |
| 6800da34 | FastSim_fbattr2d | 23 | GLM draf MATCH (audit pass 2) 8 | ? | 22 | GLM draft, u MATCH (audit pass 2) | FastSim_FRUNNRS2 | 20 | table CONFIR MATCH (audit pass 2) FID noise) |
| 6802baf7 MATCH (audit pass 2) 9 | CONFIRMED table + flow |
| 6805 PARTIAL (pass 2, see re/spec_audit/FUN_68040 PARTIAL (pass 2, see re/spec_audit/FUN_6803aad7.txt) d |
|  MATCH (audit pass 2) ttr2d | 16 | GLM draft, MATCH (audit pass 2) 7 | ? | 13 | GLM draft, MATCH (audit pass 2) e | FastSim_FGAME | 11 | GLM draft,  MATCH (audit pass 2)  | ? | 11 | GLM draft, unaudited |
|  PARTIAL (pass 2, see re/spec_audit/FUN_6800 MATCH (audit pass 2)  GLM draft, unaudited |
| 68036e91 |  MATCH (audit pass 2) audited |
| 6803122b | ? | 10 | GLM MATCH (audit pass 2) 6803e684 | FastSim_FRO MATCH (audit pass 2) unaudited |
| 6800e5db MATCH (audit pass 2) 9 | GLM draft, unaudit MATCH (audit pass 2) 7 | GLM draft, unaudit MATCH (audit pass 2) Sim_fbattr2d | 7 | GLM MATCH (audit pass 2) 6805ecfd | FastSim_FTHROW | 6 | G MATCH (audit pass 2) | 6805d960 | ? | 6 | GLM draft, una MATCH (audit pass 2) ? | 6 | GLM draft, una MATCH (audit pass 2) ? | 6 | GLM draft, una PARTIAL (pass 2, see re/spec_audit/FUN_6803 MATCH (audit pass 2) draft, unaudited |
| 6 MATCH (audit pass 2) draft, unaudited |
| 68001935 | FastS MATCH (audit pass 2) t, unaudited |
| 6805d MATCH (audit pass 2)  5 | GLM draft, unaudi PARTIAL (pass 2, see re/spec_audit/FUN_6804 MATCH (audit pass 2) ft, unaudited |
| 6803 MATCH (audit pass 2) ft, unaudited |
| 6805 MATCH (audit pass 2) ft, unaudited |
| 68036d52 | ? | 4  MATCH (audit pass 2)  |
| 6800d44f | FastSi MATCH (audit pass 2) raft, unaudited |
| MATCH (audit pass 2) |
| 68 MATCH (audit pass 2) raft, unaudited |
| 68 PARTIAL (pass 2, see re/spec_audit/FUN_6800 MATCH (audit pass 2) ted |
| 6802ef90 | ? | MATCH (audit pass 2) ted |
| 6805e93b | Fas MATCH (audit pass 2) draft, unaudited |
| 6 MATCH (audit pass 2) draft, u MATCH (audi MATCH (audit pass 2) ass 2) 30a6f | ? |  PARTIAL (pass 2, see re/spec_audit/FUN_6804 MATCH (audit pass 2) 899 | ? | 2 | GLM draf MATCH (audit pass 2) c50 | ? | 1 | GLM draf MATCH (audit pass 2) ab6 | ? | 1 | GLM draft, unaudited MATCH (audit pass 2) | GLM draft, unaudited |
| 6805c22c MATCH (audit pass 2) unaudited |
| 68053d2e PARTIAL (pass 2, see re/spec_audit/FUN_6802 MATCH (audit pass 2) | 680506fd | ? | 1 | GLM draft, unau MATCH (audit pass 2) astSim_FRUNNER | 1 | G MATCH (audit pass 2) | 68043fcf | ? | 1 | GLM draft, unaud MATCH (audit pass 2) | 1 | GLM draft, unaudited |
| 6803a6 MATCH (audit pass 2) , unaudited |
| 68039750 | FastSim_FBALL | 1 | GLM draft, unaudited |
| 68023268 | FastSim_FFIELD MATCH (audit pass 2) dited |
| 68022 MATCH (audit pass 2) ATCH (audit pass 2) 21fca | ? | 1 | GLM dr PARTIAL (pass 2, see re/spec_audit/FUN_6802 MATCH (audit pass 2) Sim_FARCADE | 1 | GLM draft, unaudit MATCH (audit pass 2) 1 | GLM draft, unaudit MATCH (audit pass 2) Sim_fbattr2d | 1 | GLM draft, unaudit MATCH (audit pass 2) Sim_fbattr2d | 1 | GLM draft, unaudit MATCH (audit pass 2) fts: work/spec/FUN_<addr>.md (also /mnt/nvme/bbpro98/re/spec/). 7 drafts hand-audited by Claude (6802baf7, 68050eb0, 6800a7ad, 6800cccc, 68044cbd part 1, table checks); all 73 drafts machine-audited by GLM-Flash in progress (re/spec_audit/), verdicts PARTIAL-heavy; see RE_FINDINGS for calibration of false positives. FUN_68036e91 draft corrected (pitchOutChance indices 14..23). PB.INI A/B validation: stealChance00Count=100 raised SB 9x over 10 sim days (2026-10-07).

## Open work
- Trace data xrefs from the init-loaded globals to their consumers and spec those (the actual formulas).
- Validate: pitch outcome mix from prlog.txt, substitution Chance values from sub.log, PB.INI override experiment.
