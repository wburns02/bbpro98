# Audit reconciliation (2026-10-07)

Getter identity verified: FUN_68003170(idx) = *(u32*)(&DAT_6808fde0 + idx*4);
pb_table addr column == base + idx*4 (checked idx 771: 0x680909ec - 0x6808fde0 = 0xC0C = 771*4).
Bullets flagged FP cite indices whose names and defaults match pb_table_FastSim.tsv.

| function | audit | bullets | FP | remaining |
|---|---|---|---|---|
| FUN_68001935 | MATCH | 1 | 0 | 68001935 (rules 2 & 4): minor imprecision only — draft writes `dist(Fi→P)`/`dist(F→P)`, while the decompile's distance calls use fielder+0x08 as the point (`uVa |
| FUN_68003899 | PARTIAL | 1 | 0 | 68003899 (rule 4, final `FUN_68005b80` call): draft formula passes `(int)this+0x32` — the *address* of the speed slot — as the first argument. The decompile pas |
| FUN_6800b36e | MATCH | 1 | 0 | Caveat only: the swing-type adjust getters at FUN_68003170(0x261)/FUN_68003170(0x262)/FUN_68003170(0x263) (indices 609/610/611, in the `+0xbd` == 1/2/3 branches |
| FUN_6800cccc_consumer | PARTIAL | 2 | 0 | 6800cccc: rule 4 (and the INPUTS framing "row/col index into PB tables") — PB attribution unsupported. FUN_6800cccc contains no call to FUN_68003170 anywhere; t; 6800cccc: rule 6 first branch — "W[cur |
| FUN_6800d44f | MATCH | 1 | 0 | Caveat only: the worked example (`ch == pr, expS == 0 → 70`) and the "90%/100%" readings rest on the unverified assumption `FUN_68005b80(v,p) = v*p/100`; the de |
| FUN_6800d51a | MATCH | 1 | 0 | 6800d51a–6800d5xx: All structural claims verified against the decompile: initial store `*(int *)(param_1 + 0xfa) = iVar1` after `CSplitterWnd::IsTracking(DAT_68 |
| FUN_6800d6be | MATCH | 1 | 0 | 6800d6be (FUN_68005b80 call site): width-only caveat — draft describes the rating at `+0xf1` as u8 (`*(u8*)(param_1+0xf1)`), but the decompile passes a 4-byte r |
| FUN_6800da34 | MATCH | 1 | 0 | 6800da34: caveat only — the veryBad/bad/med/good triples are stated as bare literals (1,80,-41)/(2,40,-41)/(3,25,-39)/(4,19,-40), but the decompile fetches them |
| FUN_6800dcc4 | MATCH | 1 | 0 | Caveat: the pitcher-record chain in Rule 3 omits the `FUN_68041d83` wrapper shown in the decompile (`local_2c = FUN_68041d83(&DAT_68114ba8 + CONCAT31(extraout_v |
| FUN_6800e5db | PARTIAL | 1 | 0 | Rule 4 (argument to FUN_6803e0d5): draft writes `FUN_6803e0d5(&(*(param_1+0x70))+0x29e)`, i.e. address of the pointer field plus 0x29e, but the decompile passes |
| FUN_6800e826 | MATCH | 1 | 0 | 6800e864: caveat only — draft's rule 3 "`*(int*)(obj+4)`" presumes `FUN_6803da2b` returns a pointer that is dereferenced (`*piVar4` feeds `0x14 - *piVar4`); the |
| FUN_68014f7b | MATCH | 1 | 0 | 68014f7b (time-pressure block): caveat only — the decompile calls `FUN_680072f0()` twice (`iVar8 = FUN_680072f0(); if (iVar8 < 10) { ... sVar5 = FUN_680072f0(); |
| FUN_68016855 | MATCH | 1 | 0 | 68016855: caveat only — the PURPOSE line's "returns TRUE **only** when … reaches at least PB[possibleOutFrames]" slightly overstates exclusivity: the `this == ( |
| FUN_68019866 | PARTIAL | 4 | 0 | 0x680c8fc8: rule 4's claim that the normal-IF pairs are "written in this order ... (fc8/fca, fcc/fce, fd0/fd2, fd4/fd6)" is contradicted. The decompile stores `; 0x680c8fe0: rule 4's normal-OF order " |
| FUN_6801a0ad | MATCH | 1 | 0 | 6801a0ad: caveat only — rule 17's "nothing in the loops writes it" is true of the code visible in this decompile, but the loops call FUN_6801abdc/FUN_68014c70,  |
| FUN_68020f87 | MATCH | 1 | 0 | Caveat only: OUTPUT's "values 0..3" is not enforced by this function — the initial slot write `*(uint *)(param_1 + 2 + local_10 * 4) = local_20;` stores the raw |
| FUN_68021fca | MATCH | 1 | 0 | Caveat only: decompile computes `return (short)iVar1 + (short)uVar2` (sum of two truncated shorts) vs. draft's `(short)(R + S)`; numerically identical after ret |
| FUN_68022316 | PARTIAL | 1 | 0 | 68022316: Draft rule 4 asserts a direct memory test — "If byte at `0x6809f510` != 0" — and lists `0x6809f510` in INPUTS as a "global byte flag" read directly. T |
| FUN_68023268 | MATCH | 1 | 0 | 68023268: minor ordering nit only — draft rule 4 writes the sum as `FUN_6805da5e(...) + (short)FUN_68003988(...)`, while the decompile evaluates `FUN_68003988(t |
| FUN_68023dd3 | PARTIAL | 1 | 0 | 0x6808e98c: draft claims only two dwords in 0x6808e940–0x6808e9d8 are untouched (0x6808e964 and 0x6808e9b4); the decompile leaves a third gap dword unwritten —  |
| FUN_6802baf7 | MATCH | 1 | 0 | 6802baf7: minor omission only — the draft doesn't mention the installed SEH/scope frame (`puStack_c = &LAB_6802bd5d`, `uStack_10 = *unaff_FS_OFFSET`, `local_8`  |
| FUN_6802d9c9 | MATCH | 1 | 0 | 6802d9c9: caveat only — structure fully verified (FUN_6802e64c(param_1) first; 24 direct 32-bit stores to 0x680963b0/d0/f0 blocks from consecutive indices 0x184 |
| FUN_6802ef90 | MATCH | 1 | 0 | 6802ef90: no contradicted claims. Getter indices check out (0x181=385 sureStrikeDist, 0x182=386 closeStrikeDist, 0x183=387 closeBallDist); branch semantics matc |
| FUN_6802fe35 | MATCH | 1 | 0 | Caveat: the draft never states the actual getter indices; the decompile shows 72 consecutive verbatim calls FUN_68003170(0x274)…FUN_68003170(0x2bb) (final call  |
| FUN_68030a6f | MATCH | 1 | 0 | Caveat: in cases 0/2/3 the running max starts at 0 with strict `>` (`local_28 < local_14[local_24]`, `local_40 < local_14[local_3c]`), so candidate[0] is also k |
| FUN_680346aa | PARTIAL | 3 | 0 | 680346aa (update path, rule 12 tail): draft truncates mid-clause ("if dy>4 → chance +=") and never states the added value; decompile completes it as `if (4 < lo; 680346aa (update path, after the dx/dy |
| FUN_68036a52 | MATCH | 1 | 0 | Caveat only: §1's "returns 0 in all other cases" and §4's "−40" example hold only for the low 16 bits under extra assumptions — when gated out the full return i |
| FUN_68036c6c | MATCH | 1 | 0 | 68036c6c: caveat only — draft header says object `0x680a57b7` is read "via three getters" but lists four functions; per the decompile, `FUN_68038e10(iVar6)` is  |
| FUN_68036d52 | MATCH | 1 | 0 | Caveat only: draft's "All arithmetic in 16-bit shorts" is slightly loose — decompile casts operands to short (e.g. `(4 - (short)iVar1) * (short)uVar8`, `(short) |
| FUN_68036e91 | MATCH | 1 | 0 | Caveat only: the draft omits two non-contradicted details — FUN_68056985 is invoked with a third argument `(void *)0x0` in the decompile (`FUN_68056985(&DAT_681 |
| FUN_680371f8 | PARTIAL | 2 | 0 | FUN_68003170(0x1c) branch (draft §3 rule 5): draft cites `pitchAroundChancePH2BatAdjust` default as (10); verified table row 28 default is 65. Decompile support; Draft §3 rule 7 "Net dR contribution ( |
| FUN_680382d9 | MATCH | 1 | 0 | 0x680382d9: only caveat — the INPUTS claim that the `param_1+0x3496` field is "at least 16 bits" overstates what this decompile evidences: the highest bit touch |
| FUN_6803853e | MATCH | 1 | 0 | All auditable claims check out against the decompile: signature `void __fastcall FUN_6803853e(int param_1)`; entry reads `FUN_6800f200(0x68143ee0)`, `FUN_680569 |
| FUN_68039750 | MATCH | 1 | 0 | in-range branch (after `uVar3 = FUN_6807d2f6(local_8,0x4000,local_10)`): the dead store is a 4-byte write `_local_18 = CONCAT22(uStack_16,(short)uVar3)`, i.e. i |
| FUN_6803a5ff | MATCH | 1 | 0 | 6803a5ff: minor caveat only — the temp fetch is short-circuited (`p_Var2 == DAT_68096a54) && (uVar1 = FUN_6803bdb0(0x68114948), (short)CONCAT31(...) == DAT_6809 |
| FUN_6803a6f0 | MATCH | 1 | 0 | 6803a6f0: caveat only — FUN_6803bdf0's return is compared/stored as a full 32-bit value (`CONCAT31(extraout_var,uVar1) == DAT_68096a5c`, `DAT_68096a5c = CONCAT3 |
| FUN_6803aa6b | MATCH | 1 | 0 | Caveat only: the copy direction of `FUN_68014b50(&DAT_68114908,param_1)` (dest=DAT_68114908, source=param_1) and the "full copy back" semantics of `FUN_6803bab0 |
| FUN_6803e684 | MATCH | 1 | 0 | 6803e684 (tail beyond draft's declared truncation point): the full decompile continues after derived[2]←slot0x21 — derived[3]←slot0x22 (`FUN_6803e39f(this+0x774 |
| FUN_68040a7e | PARTIAL | 1 | 0 | 68040a7e (draft step 6.2, wrong branch structure): draft claims "If id == 0, skip to 6.13", but the decompile's `if (iVar4 != 0) {` guard encloses steps 6.3–6.1 |
| FUN_68043fcf | MATCH | 1 | 0 | Caveat (phrasing only): R5's "Pass B runs iff PB[posPlayerPitchingRuns] <= (int)(bVar2 - bVar3)" omits that the getter call `iVar6 = FUN_68003170(0x303)` (0x303 |
| FUN_680447dc | MATCH | 2 | 0 | 0x680447dc: All structural claims verified — PB getter indices 0xa7/0xa8/0xa9/0xaa/0xab map to table rows 167–171 (warmupSecsPerWarmPitch/QuickPitch/MaintPitch/; Caveat: helper semantics (FUN_68002dd0 |
| FUN_68044cbd_part1 | MATCH | 1 | 0 | 68044cbd (bench-scan loop): minor caveat — draft renders the combined-rating case as `param_1 == 2`, but the decompile uses the bare `else` of the `param_1==0`/ |
| FUN_680460cc | MATCH | 1 | 0 | Caveats (non-contradictions): §4's log claim is incomplete — the decompile gates the "=== Check_For_Sub ===" block on an additional inner check (`FUN_680825ac(l |
| FUN_68047511 | MATCH | 1 | 0 | FUN_68003170(0x176)–(0x179) / (0x17b)–(0x17d): caveat only — the decompile does call these new-def threshold/adjust getters in exactly the claimed nested-`<` st |
| FUN_68049d61 | MATCH | 1 | 0 | 68049d61: caveat only — the PURPOSE line "raises a flag when the pitcher **first** drops out of the top two states" could be read as a one-time latch, but the d |
| FUN_6804a357 | MATCH | 1 | 0 | 6804a357 (PB loads 0xae–0xb6, table indexed by `FUN_6800f0e0(local_8,1,9)`): caveat only — the per-inning defaults cited in rule 1 (−20/−25/−21/−17/−13/−7/−1/5/ |
| FUN_6804a64d | PARTIAL | 1 | 0 | FUN_6804a64d (opponent-index derivation, rule 4): draft inverts the ternary. Decompile computes `local_18 = (uint)(*(int *)((int)param_1 + 0x17330) != 1)`, i.e. |
| FUN_6804d70e | PARTIAL | 1 | 0 | 6804d70e (draft §3 rule 2, reachability note): The claim that the TRUE branch is "Reachable only when rule 1's gate was passed via FUN_68009700 true, the 0x6809 |
| FUN_680506fd | MATCH | 1 | 0 | Caveat only: the `+1` increment (after `FUN_6800f600(0x680a57b7) == 0`) can transiently produce 4 at `param_1+0x82`; the draft's PURPOSE line "value 2 or 3" hol |
| FUN_68050eb0 | MATCH | 1 | 0 | Caveat only (not a contradiction): draft rules 2–3 compress the resource fetches into singular phrasing ("FUN_6808423b(0x13d) fetches a resource", "FUN_6808423b |
| FUN_68052bd5 | MATCH | 2 | 0 | All structure, gates, PB indices (0x36–0x66/54–102), comparison directions, non-PB constants (0x40, 0x89, 0x6b, 0x7b, 0x68143ee0, 0x68114948, 0x68114ba8, 0x173b; Caveat only: the "returns 0 on failed  |
| FUN_68053248 | PARTIAL | 4 | 0 | 68053248 (rule 5, SP bands): draft hardcodes cutoffs 39/59/79/80 as fixed constants; the decompile reads all three SP thresholds from PlayBalance — `FUN_6800317; 68053248 (rule 6, CH bands): draft har |
| FUN_680537ad | MATCH | 1 | 0 | Caveat only: Rule 2's phrase "same call site is reused for both thresholds" is loosely worded — the decompile contains two separate but identical `IsTracking(*( |
| FUN_68053b36 | MATCH | 1 | 0 | 68053b36: caveat only — the decompile's second else-if condition contains `local_c = sVar1` (with `sVar1 = local_c` = 0 from the prologue `local_c = 0; sVar1 =  |
| FUN_68053d2e_consumer | PARTIAL | 6 | 1 | Rule 3 (view-state-2 gate): comparison inverted. Decompile: `uVar5 = FUN_68082999(&DAT_68185a60,100); iVar4 = FUN_68003170(0x301); if (iVar4 < (int)uVar5) { loc; Rule 7 table, row "−3, −4": outcomes i |
| FUN_68054b0a | MATCH | 1 | 0 | Caveat only: the draft's shorthand `FUN_68038e10(ctx+0x91)` / `(ctx+0x95)` omits the dereference — the decompile passes the value read from the struct (`FUN_680 |
| FUN_6805be15 | MATCH | 1 | 0 | 6805be15: caveat only — draft rule 4 lists the {1,6} flag (`local_20`) with the other position flags, but the decompile computes it later (after the threshold b |
| FUN_6805c22c | MATCH | 1 | 0 | 6805c2a2/6805c2b6: caveat only — Ghidra shows `_local_14 = CONCAT22(uStack_12, sVar2);` after `FUN_6807c1c0(*(short *)((int)this + 0x16), local_14, 0x1555)`; th |
| FUN_6805d960 | MATCH | 1 | 0 | 6805d9a0/6805d9c8 (branch structure): Rule 7's "truncated to short for return" is slightly imprecise — the decompile truncates at each store (`local_8 = (short) |
| FUN_6805da5e | MATCH | 1 | 0 | 6805da5e: All structural claims verified — FUN_68002bb0(param_2,param_1) with reversed arg order, FUN_6805d960(this,iVar2) returning short, FUN_68003170(0x34c)  |
| FUN_6805dab6 | MATCH | 1 | 0 | Caveat only: draft's "flat constant" phrasing is slightly loose — the slop is fetched at runtime via `FUN_68003170(0x34c)` (idx 0x34c = 844 = throwTimeSlop, def |
| FUN_6805db11 | MATCH | 1 | 0 | Caveat: the "upper 24 bits mirror the high bytes of the last helper result" holds exactly only on the true path (`return CONCAT31((int3)(uVar4 >> 8),1)` after ` |
| FUN_6805dc50 | MATCH | 1 | 0 | 6805dc50: caveat — the draft's truncation note covers only `FUN_68003988`'s result, but the decompile also truncates the baseline to short (`sVar2 = FUN_6802326 |
| FUN_6805dd30 | MATCH | 1 | 0 | Caveat (structural clarity, not a contradiction): rule 12's `FUN_6805dc50(this,param_1)` sits inside the scatter branch in the decompile — `bVar3 = FUN_68082a2d |
| FUN_6805e93b | MATCH | 1 | 0 | Caveat: `param_1+0x06` is written as a full 4-byte store, not a u8 as the INPUTS layout guesses — decompile: `*(uint *)((int)param_1 + 6) = CONCAT31(extraout_va |
| FUN_6805ecfd | MATCH | 1 | 0 | 0x68143ee0: minor caveat only — draft says the byte is "read twice," but the decompile shows three `FUN_68002c80(0x68143ee0)` call sites (two within the forced- |

Totals: 83 bullets, 1 false positives, 82 still to review

## FUN_68001935 (MATCH)
- 68001935 (rules 2 & 4): minor imprecision only — draft writes `dist(Fi→P)`/`dist(F→P)`, while the decompile's distance calls use fielder+0x08 as the point (`uVa

## FUN_68003899 (PARTIAL)
- 68003899 (rule 4, final `FUN_68005b80` call): draft formula passes `(int)this+0x32` — the *address* of the speed slot — as the first argument. The decompile pas

## FUN_6800b36e (MATCH)
- Caveat only: the swing-type adjust getters at FUN_68003170(0x261)/FUN_68003170(0x262)/FUN_68003170(0x263) (indices 609/610/611, in the `+0xbd` == 1/2/3 branches

## FUN_6800cccc_consumer (PARTIAL)
- 6800cccc: rule 4 (and the INPUTS framing "row/col index into PB tables") — PB attribution unsupported. FUN_6800cccc contains no call to FUN_68003170 anywhere; t; 6800cccc: rule 6 first branch — "W[cur] = 1, rest 0" is contradicted. The decompile performs only `aiStack_24[local_58] = 1;` under `if ((local_84 == 0) && (loc

## FUN_6800d44f (MATCH)
- Caveat only: the worked example (`ch == pr, expS == 0 → 70`) and the "90%/100%" readings rest on the unverified assumption `FUN_68005b80(v,p) = v*p/100`; the de

## FUN_6800d51a (MATCH)
- 6800d51a–6800d5xx: All structural claims verified against the decompile: initial store `*(int *)(param_1 + 0xfa) = iVar1` after `CSplitterWnd::IsTracking(DAT_68

## FUN_6800d6be (MATCH)
- 6800d6be (FUN_68005b80 call site): width-only caveat — draft describes the rating at `+0xf1` as u8 (`*(u8*)(param_1+0xf1)`), but the decompile passes a 4-byte r

## FUN_6800da34 (MATCH)
- 6800da34: caveat only — the veryBad/bad/med/good triples are stated as bare literals (1,80,-41)/(2,40,-41)/(3,25,-39)/(4,19,-40), but the decompile fetches them

## FUN_6800dcc4 (MATCH)
- Caveat: the pitcher-record chain in Rule 3 omits the `FUN_68041d83` wrapper shown in the decompile (`local_2c = FUN_68041d83(&DAT_68114ba8 + CONCAT31(extraout_v

## FUN_6800e5db (PARTIAL)
- Rule 4 (argument to FUN_6803e0d5): draft writes `FUN_6803e0d5(&(*(param_1+0x70))+0x29e)`, i.e. address of the pointer field plus 0x29e, but the decompile passes

## FUN_6800e826 (MATCH)
- 6800e864: caveat only — draft's rule 3 "`*(int*)(obj+4)`" presumes `FUN_6803da2b` returns a pointer that is dereferenced (`*piVar4` feeds `0x14 - *piVar4`); the

## FUN_68014f7b (MATCH)
- 68014f7b (time-pressure block): caveat only — the decompile calls `FUN_680072f0()` twice (`iVar8 = FUN_680072f0(); if (iVar8 < 10) { ... sVar5 = FUN_680072f0();

## FUN_68016855 (MATCH)
- 68016855: caveat only — the PURPOSE line's "returns TRUE **only** when … reaches at least PB[possibleOutFrames]" slightly overstates exclusivity: the `this == (

## FUN_68019866 (PARTIAL)
- 0x680c8fc8: rule 4's claim that the normal-IF pairs are "written in this order ... (fc8/fca, fcc/fce, fd0/fd2, fd4/fd6)" is contradicted. The decompile stores `; 0x680c8fe0: rule 4's normal-OF order "RF, CF, LF (fe0/fe2, fe4/fe6, fe8/fea)" is contradicted. The decompile writes `_DAT_680c8fe8`/`_DAT_680c8fea` first (`FUN_; 0x680c8fec / 0x680c9010 / 0x680c9034: the same IF 3rd/4th-pair swap occurs in every remaining IF block, contradicting the draft's ascending "1B, 2B, 3B, SS" wri; 0x680c9004 / 0x680c9028: the same OF reversal occurs in the remaining OF blocks: guardLeft writes `0x32b`/`0x32c`→`_DAT_680c900c`/`_DAT_680c900e` first and `0x3

## FUN_6801a0ad (MATCH)
- 6801a0ad: caveat only — rule 17's "nothing in the loops writes it" is true of the code visible in this decompile, but the loops call FUN_6801abdc/FUN_68014c70, 

## FUN_68020f87 (MATCH)
- Caveat only: OUTPUT's "values 0..3" is not enforced by this function — the initial slot write `*(uint *)(param_1 + 2 + local_10 * 4) = local_20;` stores the raw

## FUN_68021fca (MATCH)
- Caveat only: decompile computes `return (short)iVar1 + (short)uVar2` (sum of two truncated shorts) vs. draft's `(short)(R + S)`; numerically identical after ret

## FUN_68022316 (PARTIAL)
- 68022316: Draft rule 4 asserts a direct memory test — "If byte at `0x6809f510` != 0" — and lists `0x6809f510` in INPUTS as a "global byte flag" read directly. T

## FUN_68023268 (MATCH)
- 68023268: minor ordering nit only — draft rule 4 writes the sum as `FUN_6805da5e(...) + (short)FUN_68003988(...)`, while the decompile evaluates `FUN_68003988(t

## FUN_68023dd3 (PARTIAL)
- 0x6808e98c: draft claims only two dwords in 0x6808e940–0x6808e9d8 are untouched (0x6808e964 and 0x6808e9b4); the decompile leaves a third gap dword unwritten — 

## FUN_6802baf7 (MATCH)
- 6802baf7: minor omission only — the draft doesn't mention the installed SEH/scope frame (`puStack_c = &LAB_6802bd5d`, `uStack_10 = *unaff_FS_OFFSET`, `local_8` 

## FUN_6802d9c9 (MATCH)
- 6802d9c9: caveat only — structure fully verified (FUN_6802e64c(param_1) first; 24 direct 32-bit stores to 0x680963b0/d0/f0 blocks from consecutive indices 0x184

## FUN_6802ef90 (MATCH)
- 6802ef90: no contradicted claims. Getter indices check out (0x181=385 sureStrikeDist, 0x182=386 closeStrikeDist, 0x183=387 closeBallDist); branch semantics matc

## FUN_6802fe35 (MATCH)
- Caveat: the draft never states the actual getter indices; the decompile shows 72 consecutive verbatim calls FUN_68003170(0x274)…FUN_68003170(0x2bb) (final call 

## FUN_68030a6f (MATCH)
- Caveat: in cases 0/2/3 the running max starts at 0 with strict `>` (`local_28 < local_14[local_24]`, `local_40 < local_14[local_3c]`), so candidate[0] is also k

## FUN_680346aa (PARTIAL)
- 680346aa (update path, rule 12 tail): draft truncates mid-clause ("if dy>4 → chance +=") and never states the added value; decompile completes it as `if (4 < lo; 680346aa (update path, after the dx/dy adjustments): the roll and its action are omitted from the rules (only implied by PURPOSE "rolls against it"); decompile:; 680346aa (update path, trailing block): entirely absent from the draft; decompile: `if ((DAT_681147a0 == 0) && (uVar5 = FUN_68038f40(0x680a57b7), (uVar5 & 0xff)

## FUN_68036a52 (MATCH)
- Caveat only: §1's "returns 0 in all other cases" and §4's "−40" example hold only for the low 16 bits under extra assumptions — when gated out the full return i

## FUN_68036c6c (MATCH)
- 68036c6c: caveat only — draft header says object `0x680a57b7` is read "via three getters" but lists four functions; per the decompile, `FUN_68038e10(iVar6)` is 

## FUN_68036d52 (MATCH)
- Caveat only: draft's "All arithmetic in 16-bit shorts" is slightly loose — decompile casts operands to short (e.g. `(4 - (short)iVar1) * (short)uVar8`, `(short)

## FUN_68036e91 (MATCH)
- Caveat only: the draft omits two non-contradicted details — FUN_68056985 is invoked with a third argument `(void *)0x0` in the decompile (`FUN_68056985(&DAT_681

## FUN_680371f8 (PARTIAL)
- FUN_68003170(0x1c) branch (draft §3 rule 5): draft cites `pitchAroundChancePH2BatAdjust` default as (10); verified table row 28 default is 65. Decompile support; Draft §3 rule 7 "Net dR contribution (defaults): ≥2 → +20": contradicted by verified defaults

## FUN_680382d9 (MATCH)
- 0x680382d9: only caveat — the INPUTS claim that the `param_1+0x3496` field is "at least 16 bits" overstates what this decompile evidences: the highest bit touch

## FUN_6803853e (MATCH)
- All auditable claims check out against the decompile: signature `void __fastcall FUN_6803853e(int param_1)`; entry reads `FUN_6800f200(0x68143ee0)`, `FUN_680569

## FUN_68039750 (MATCH)
- in-range branch (after `uVar3 = FUN_6807d2f6(local_8,0x4000,local_10)`): the dead store is a 4-byte write `_local_18 = CONCAT22(uStack_16,(short)uVar3)`, i.e. i

## FUN_6803a5ff (MATCH)
- 6803a5ff: minor caveat only — the temp fetch is short-circuited (`p_Var2 == DAT_68096a54) && (uVar1 = FUN_6803bdb0(0x68114948), (short)CONCAT31(...) == DAT_6809

## FUN_6803a6f0 (MATCH)
- 6803a6f0: caveat only — FUN_6803bdf0's return is compared/stored as a full 32-bit value (`CONCAT31(extraout_var,uVar1) == DAT_68096a5c`, `DAT_68096a5c = CONCAT3

## FUN_6803aa6b (MATCH)
- Caveat only: the copy direction of `FUN_68014b50(&DAT_68114908,param_1)` (dest=DAT_68114908, source=param_1) and the "full copy back" semantics of `FUN_6803bab0

## FUN_6803e684 (MATCH)
- 6803e684 (tail beyond draft's declared truncation point): the full decompile continues after derived[2]←slot0x21 — derived[3]←slot0x22 (`FUN_6803e39f(this+0x774

## FUN_68040a7e (PARTIAL)
- 68040a7e (draft step 6.2, wrong branch structure): draft claims "If id == 0, skip to 6.13", but the decompile's `if (iVar4 != 0) {` guard encloses steps 6.3–6.1

## FUN_68043fcf (MATCH)
- Caveat (phrasing only): R5's "Pass B runs iff PB[posPlayerPitchingRuns] <= (int)(bVar2 - bVar3)" omits that the getter call `iVar6 = FUN_68003170(0x303)` (0x303

## FUN_680447dc (MATCH)
- 0x680447dc: All structural claims verified — PB getter indices 0xa7/0xa8/0xa9/0xaa/0xab map to table rows 167–171 (warmupSecsPerWarmPitch/QuickPitch/MaintPitch/; Caveat: helper semantics (FUN_68002dd0 = max(v,1), FUN_6800f0e0 = clamp, FUN_68049d61 purpose) remain unverifiable from this decompile alone, but the draft alre

## FUN_68044cbd_part1 (MATCH)
- 68044cbd (bench-scan loop): minor caveat — draft renders the combined-rating case as `param_1 == 2`, but the decompile uses the bare `else` of the `param_1==0`/

## FUN_680460cc (MATCH)
- Caveats (non-contradictions): §4's log claim is incomplete — the decompile gates the "=== Check_For_Sub ===" block on an additional inner check (`FUN_680825ac(l

## FUN_68047511 (MATCH)
- FUN_68003170(0x176)–(0x179) / (0x17b)–(0x17d): caveat only — the decompile does call these new-def threshold/adjust getters in exactly the claimed nested-`<` st

## FUN_68049d61 (MATCH)
- 68049d61: caveat only — the PURPOSE line "raises a flag when the pitcher **first** drops out of the top two states" could be read as a one-time latch, but the d

## FUN_6804a357 (MATCH)
- 6804a357 (PB loads 0xae–0xb6, table indexed by `FUN_6800f0e0(local_8,1,9)`): caveat only — the per-inning defaults cited in rule 1 (−20/−25/−21/−17/−13/−7/−1/5/

## FUN_6804a64d (PARTIAL)
- FUN_6804a64d (opponent-index derivation, rule 4): draft inverts the ternary. Decompile computes `local_18 = (uint)(*(int *)((int)param_1 + 0x17330) != 1)`, i.e.

## FUN_6804d70e (PARTIAL)
- 6804d70e (draft §3 rule 2, reachability note): The claim that the TRUE branch is "Reachable only when rule 1's gate was passed via FUN_68009700 true, the 0x6809

## FUN_680506fd (MATCH)
- Caveat only: the `+1` increment (after `FUN_6800f600(0x680a57b7) == 0`) can transiently produce 4 at `param_1+0x82`; the draft's PURPOSE line "value 2 or 3" hol

## FUN_68050eb0 (MATCH)
- Caveat only (not a contradiction): draft rules 2–3 compress the resource fetches into singular phrasing ("FUN_6808423b(0x13d) fetches a resource", "FUN_6808423b

## FUN_68052bd5 (MATCH)
- All structure, gates, PB indices (0x36–0x66/54–102), comparison directions, non-PB constants (0x40, 0x89, 0x6b, 0x7b, 0x68143ee0, 0x68114948, 0x68114ba8, 0x173b; Caveat only: the "returns 0 on failed gate" and "[0,100]" claims rest on the draft's own flagged guess that FUN_68014c70 is a clamp — the decompile shows only t

## FUN_68053248 (PARTIAL)
- 68053248 (rule 5, SP bands): draft hardcodes cutoffs 39/59/79/80 as fixed constants; the decompile reads all three SP thresholds from PlayBalance — `FUN_6800317; 68053248 (rule 6, CH bands): draft hardcodes 39/59/69/70; decompile uses `FUN_68003170(0x74)` (116), `FUN_68003170(0x75)` (117), `FUN_68003170(0x76)` (118) agai; 68053248 (rule 7, PH bands): draft hardcodes 39/59/79/80 and never mentions `hnrChanceLowPHThresh`; decompile uses `FUN_68003170(0x7b)` (idx 123 = hnrChanceLowP; 68053248 (§2, "All 31 hnrChance* PB parameters"): the decompile makes 32 distinct getter calls spanning `FUN_68003170(0x67)`–`FUN_68003170(0x86)` (idx 103–134),

## FUN_680537ad (MATCH)
- Caveat only: Rule 2's phrase "same call site is reused for both thresholds" is loosely worded — the decompile contains two separate but identical `IsTracking(*(

## FUN_68053b36 (MATCH)
- 68053b36: caveat only — the decompile's second else-if condition contains `local_c = sVar1` (with `sVar1 = local_c` = 0 from the prologue `local_c = 0; sVar1 = 

## FUN_68053d2e_consumer (PARTIAL)
- Rule 3 (view-state-2 gate): comparison inverted. Decompile: `uVar5 = FUN_68082999(&DAT_68185a60,100); iVar4 = FUN_68003170(0x301); if (iVar4 < (int)uVar5) { loc; Rule 7 table, row "−3, −4": outcomes inverted. Decompile: `case -4: case -3: uVar5 = FUN_68082999(&DAT_68185a60,100); local_20 = (uint)((int)uVar5 < local_34);`; Rule 10 (update message): condition inverted. Decompile: `FUN_6804869a(&DAT_68114ba8 + (uint)(*(int *)((int)param_1 + 0x7b) == 0) * 0x173be,4);` — the `+0x173BE; Rule 10 (FUN_68054d4a call): parameter count/grouping wrong. Draft lists 6 args with `&{local_48, local_44, local_38}` merged; decompile passes 7: `FUN_68054d4a; OUTPUT/SIDE EFFECTS: write range off by one byte. Last store `*(undefined2 *)(local_30 + 0x1d) = local_74;` is a 2-byte write, so DAT_680a58de bytes 0xD–0x1E ar

## FUN_68054b0a (MATCH)
- Caveat only: the draft's shorthand `FUN_68038e10(ctx+0x91)` / `(ctx+0x95)` omits the dereference — the decompile passes the value read from the struct (`FUN_680

## FUN_6805be15 (MATCH)
- 6805be15: caveat only — draft rule 4 lists the {1,6} flag (`local_20`) with the other position flags, but the decompile computes it later (after the threshold b

## FUN_6805c22c (MATCH)
- 6805c2a2/6805c2b6: caveat only — Ghidra shows `_local_14 = CONCAT22(uStack_12, sVar2);` after `FUN_6807c1c0(*(short *)((int)this + 0x16), local_14, 0x1555)`; th

## FUN_6805d960 (MATCH)
- 6805d9a0/6805d9c8 (branch structure): Rule 7's "truncated to short for return" is slightly imprecise — the decompile truncates at each store (`local_8 = (short)

## FUN_6805da5e (MATCH)
- 6805da5e: All structural claims verified — FUN_68002bb0(param_2,param_1) with reversed arg order, FUN_6805d960(this,iVar2) returning short, FUN_68003170(0x34c) 

## FUN_6805dab6 (MATCH)
- Caveat only: draft's "flat constant" phrasing is slightly loose — the slop is fetched at runtime via `FUN_68003170(0x34c)` (idx 0x34c = 844 = throwTimeSlop, def

## FUN_6805db11 (MATCH)
- Caveat: the "upper 24 bits mirror the high bytes of the last helper result" holds exactly only on the true path (`return CONCAT31((int3)(uVar4 >> 8),1)` after `

## FUN_6805dc50 (MATCH)
- 6805dc50: caveat — the draft's truncation note covers only `FUN_68003988`'s result, but the decompile also truncates the baseline to short (`sVar2 = FUN_6802326

## FUN_6805dd30 (MATCH)
- Caveat (structural clarity, not a contradiction): rule 12's `FUN_6805dc50(this,param_1)` sits inside the scatter branch in the decompile — `bVar3 = FUN_68082a2d

## FUN_6805e93b (MATCH)
- Caveat: `param_1+0x06` is written as a full 4-byte store, not a u8 as the INPUTS layout guesses — decompile: `*(uint *)((int)param_1 + 6) = CONCAT31(extraout_va

## FUN_6805ecfd (MATCH)
- 0x68143ee0: minor caveat only — draft says the byte is "read twice," but the decompile shows three `FUN_68002c80(0x68143ee0)` call sites (two within the forced-
