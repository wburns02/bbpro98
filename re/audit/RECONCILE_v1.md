# Audit reconciliation (2026-10-07)

Getter identity verified: FUN_68003170(idx) = *(u32*)(&DAT_6808fde0 + idx*4);
pb_table addr column == base + idx*4 (checked idx 771: 0x680909ec - 0x6808fde0 = 0xC0C = 771*4).
Bullets flagged FP cite indices whose names and defaults match pb_table_FastSim.tsv.

| function | audit | bullets | FP | remaining |
|---|---|---|---|---|
| FUN_68003899 | PARTIAL | 4 | 0 | 68003899: INPUTS/RULE 1 invent `PB[speedPct]` with "default 5" as a direct operand; decompile computes the second operand via an omitted call: `iVar1 = FUN_6800; 68003899: INPUTS/RULE 2 invent `PB[spe |
| FUN_6800a7ad | PARTIAL | 2 | 0 | 0x6800ac4b: draft rule 1 states handler → `LAB_680ac4b`; decompile shows `puStack_c = &LAB_6800ac4b;` — draft dropped a digit, wrong handler address.; 0x6808cef8–0x6808cfb4: draft (§2, rule 7) claims  |
| FUN_6800d44f | PARTIAL | 4 | 1 | 6800d44f (header): "params=4" contradicted — decompile signature is `void __fastcall FUN_6800d44f(int param_1)`, exactly one parameter; no second through fourth; 6800d44f (§2 "PB: idRatingBase=20, idR |
| FUN_6800d51a | PARTIAL | 3 | 1 | 6800d51a (rule 3, §2): Draft claims `FUN_68005b80`'s second arg is `PB[idRatingTypeWeight]` (default 100). Decompile contradicts: `iVar1 = FUN_68003170(0x1fe); ; 6800d51a (rule 3, §4/§5): `FUN_6800317 |
| FUN_6800d6be | PARTIAL | 3 | 2 | 6800d6be (§2 inputs): "+0xf1 (u8): rating passed through the PB weight" — unsupported: decompile accesses it as `*(int *)(param_1 + 0xf1)` (width u8 not shown)  |
| FUN_6800da34 | PARTIAL | 7 | 2 | Rule 3 band triples (1,80,-41)/(2,40,-41)/(3,25,-39)/(4,19,-40): unsupported — decompile assigns `local_10/local_c/local_14` from `FUN_68003170(0x202..0x204)`, ; Rule 3 veryGood triple (5,14,-38): uns |
| FUN_6800e5db | PARTIAL | 5 | 2 | 6800e5db (header): draft claims "params=9"; decompile signature is `void __fastcall FUN_6800e5db(int param_1)` — exactly one parameter.; 6800e5db (rule 1): draft asserts second arg is `PB[adjustUnitsC |
| FUN_68016855 | PARTIAL | 2 | 1 | 68016855: Rule 4b branch condition is imprecise. Draft states `If i == start` using the cached `start` from Rule 3. Decompile re-calls the getter every iteratio |
| FUN_68020f87 | PARTIAL | 2 | 0 | 68020f87: Budget claim "PB[likelyOutFrames] (default 20)" is invented/unsupported. Decompile reads the budget via a getter call with constant 0x34a on every inn; 68020f87: OUTPUT claim "Writes four dw |
| FUN_68021fca | PARTIAL | 4 | 1 | 68021fca: Draft asserts "No other logic, branches, or thresholds exist in this function" and lists only two operations. Contradicted: the decompile body contain; 68021fca: Draft claims "`PB` is only r |
| FUN_68022316 | PARTIAL | 3 | 0 | FUN_68003170 / return of FUN_68022316: draft's rule 6 and §2 claim the threshold is `PB[likelyOutFrames]` with "default 20" and quote "exact code: `PB[likelyOut; 0x6809f510 gate (draft §2 and rule 4): |
| FUN_68023268 | PARTIAL | 3 | 0 | §3.5/§3.8/§3.10/§4 ("PB[relaySlop]" as a direct read): the decompile shows the added term is a helper call, `uVar8 = FUN_68003170(0x344);`, at both slop sites (; §1/§3.10 ("default 12"): no literal `1 |
| FUN_6802baf7 | PARTIAL | 4 | 2 | 6802baf7 (header): "params=19" is contradicted by the decompile signature `void FUN_6802baf7(void)` — the function takes no arguments. The 19 corresponds to the; 6802baf7 §5 table: all 19 "Default" va |
| FUN_6802ef90 | PARTIAL | 4 | 2 | 6802ef90: draft header claims `params=3`; decompile signature is `undefined4 __cdecl FUN_6802ef90(undefined4 param_1)` — a single 4-byte stack parameter, not th; 6802ef90 OUTPUT: "pure function of `pa |
| FUN_6802fe35 | PARTIAL | 7 | 0 | FUN_6802fe35 header "params=72": decompile signature is `undefined4 * __fastcall FUN_6802fe35(undefined4 *param_1)` — exactly one parameter; 72 is not a paramet; 0x68096690–0x680967ac (§1 purpose, §3  |
| FUN_68030a6f | PARTIAL | 2 | 1 | 68030a6f: draft header claims `params=2`; decompile signature is `void __fastcall FUN_68030a6f(int param_1)` — a single argument, and no second parameter is ref |
| FUN_68036c6c | PARTIAL | 3 | 0 | 68036c6c: "params=3" — decompile signature is `short FUN_68036c6c(int param_1)`; exactly one int parameter is declared and used, no second/third argument appear; 68036c6c: "via three getters" — the de |
| FUN_68036d52 | PARTIAL | 5 | 1 | 68036d52: header claims `params=4`, but the decompile signature is `short __fastcall FUN_68036d52(int param_1)` — a single int parameter.; 68036d52: "so with defaults, more pitches → higher chance via |
| FUN_68036e91 | MISMATCH | 7 | 1 | 68036e91: header claims `params=10`; decompile signature is `short __fastcall FUN_68036e91(int param_1)` — a single int parameter.; 68036e91: rule 3 claims both gate thresholds are `PB[...]` index 25; |
| FUN_68039750 | PARTIAL | 1 | 0 | FUN_68039750 (rule 11 / INPUTS "PB[throwHeightPct] = 70"): draft asserts the second argument to FUN_68005b80 is the constant 70 and omits a helper call entirely |
| FUN_6803a6f0 | PARTIAL | 2 | 0 | 6803a6f0: scale-argument sourcing wrong/omitted — draft claims the 2nd arg of `FUN_68005b80` is `PB[ballWindSpeedPct]`, but the decompile computes it as `iVar2 ; 6803a6f0: invented constant "(default  |
| FUN_6803aa6b | PARTIAL | 3 | 0 | 6803aa7c: Draft rule 3 / PURPOSE / INPUTS claim the second setter gets `PB[ballAirResistancePct]` (default 95) "read directly by this function". Decompile contr; 6803aa7c: Draft omits the call `FUN_68 |
| FUN_68043fcf | PARTIAL | 1 | 0 | post-Pass-A gate (code between the Pass A loop ending at LAB_68043ffc and the Pass B loop ending at LAB_6804419c): draft §2/R5 claims the Pass-B threshold is `P |
| FUN_680447dc | PARTIAL | 3 | 1 | 680447dc: header claims "params=5", but the decompile signature is `void __fastcall FUN_680447dc(void *param_1)` — a single argument. No 5-parameter form exists; 680447dc: OUTPUT line "Calls FUN_68049 |
| FUN_68049d61 | PARTIAL | 4 | 1 | 68049d61: rule 6's "holds with defaults" (exhaustedThresh < tiredThresh) rests on the unsupported defaults; the decompile supports only that the `FUN_68003170(0; 68049d61: purpose says the flag is rai |
| FUN_6804a64d | PARTIAL | 5 | 1 | 6804a64d (header): draft claims `params=3`; decompile signature is `bool __fastcall FUN_6804a64d(void *param_1)` — exactly one parameter, and no second/third ar; 6804a64d (§2 PB line, §3 rule 1): draf |
| FUN_680506fd | PARTIAL | 2 | 0 | 0x680506fd (§1, §3 rule 2): threshold source is invented — the decompile computes the compare operand via a call, `iVar4 = FUN_68003170(0x2d4);`, then tests `(i; 0x680506fd (§3 rule 2): "default thres |

Totals: 95 bullets, 20 false positives, 75 still to review

## FUN_68003899 (PARTIAL)
- 68003899: INPUTS/RULE 1 invent `PB[speedPct]` with "default 5" as a direct operand; decompile computes the second operand via an omitted call: `iVar1 = FUN_6800; 68003899: INPUTS/RULE 2 invent `PB[speedBase]` with "default 20"; decompile addend is `uVar2 = FUN_68003170(0x2d6);` consumed as `(short)iVar1 + (short)uVar2` —; 68003899: RULE 4 writes the first operand as `(int)this+0x32`, which denotes the address; decompile passes the value read from that address: `FUN_68005b80((int); 68003899: OUTPUT claim "No PB writes; no other state touched" cannot be supported — `FUN_68003170`, `FUN_68005b80`, `FUN_68005b50` bodies are not in the decompi

## FUN_6800a7ad (PARTIAL)
- 0x6800ac4b: draft rule 1 states handler → `LAB_680ac4b`; decompile shows `puStack_c = &LAB_6800ac4b;` — draft dropped a digit, wrong handler address.; 0x6808cef8–0x6808cfb4: draft (§2, rule 7) claims 48 dwords are copied "from the PB[] table" as "straight parameter copies"; decompile shows each dword is a gett

## FUN_6800d44f (PARTIAL)
- 6800d44f (header): "params=4" contradicted — decompile signature is `void __fastcall FUN_6800d44f(int param_1)`, exactly one parameter; no second through fourth; 6800d44f (§2 "PB: idRatingBase=20, idRatingCHPct=100, idRatingExpPct=90, idRatingPitchRatPct=100"; also §3.2 "(default 90%)", §3.3 "(default 100%)"): invented c; 6800d44f (§1 "against a fixed base"): base is not fixed — it is `iVar5 = FUN_68003170(0x1fa)` fetched at runtime immediately before the store.

## FUN_6800d51a (PARTIAL)
- 6800d51a (rule 3, §2): Draft claims `FUN_68005b80`'s second arg is `PB[idRatingTypeWeight]` (default 100). Decompile contradicts: `iVar1 = FUN_68003170(0x1fe); ; 6800d51a (rule 3, §4/§5): `FUN_68003170` is missing from the draft's enumerated helper lists ("called helpers (FUN_68082999, FUN_68005b80, FUN_6800f7f0, FUN_680

## FUN_6800d6be (PARTIAL)
- 6800d6be (§2 inputs): "+0xf1 (u8): rating passed through the PB weight" — unsupported: decompile accesses it as `*(int *)(param_1 + 0xf1)` (width u8 not shown) 

## FUN_6800da34 (PARTIAL)
- Rule 3 band triples (1,80,-41)/(2,40,-41)/(3,25,-39)/(4,19,-40): unsupported — decompile assigns `local_10/local_c/local_14` from `FUN_68003170(0x202..0x204)`, ; Rule 3 veryGood triple (5,14,-38): unsupported — decompile uses `FUN_68003170(0x211)`, `FUN_68003170(0x212)`, `FUN_68003170(0x213)`; values not visible.; Rule 3 bunt triple (1,30,-15): unsupported — decompile uses `FUN_68003170(0x214)`, `FUN_68003170(0x215)`, `FUN_68003170(0x216)`; values not visible.; "params=23": unsupported as stated — FUN_6800da34 has a single parameter (`int param_1`); 23 only matches the PB id span 0x200–0x216 (0x17 entries), not the fun; Rule 3 slot semantics (local_10=count, local_c=faces, local_14=base): decompile only establishes call order `FUN_68082a7c(local_10,local_c,local_14)`; per-slot 

## FUN_6800e5db (PARTIAL)
- 6800e5db (header): draft claims "params=9"; decompile signature is `void __fastcall FUN_6800e5db(int param_1)` — exactly one parameter.; 6800e5db (rule 1): draft asserts second arg is `PB[adjustUnitsCHPct]` with "default 40"; decompile passes `iVar1 = FUN_68003170(0x246)` — no literal 40 exists i; 6800e5db (rule 4): draft writes `FUN_6803e0d5(&(*(param_1+0x70))+0x29e)`; decompile is `FUN_6803e0d5(*(int *)(param_1 + 0x70) + 0x29e)` — the pointer stored at 

## FUN_68016855 (PARTIAL)
- 68016855: Rule 4b branch condition is imprecise. Draft states `If i == start` using the cached `start` from Rule 3. Decompile re-calls the getter every iteratio

## FUN_68020f87 (PARTIAL)
- 68020f87: Budget claim "PB[likelyOutFrames] (default 20)" is invented/unsupported. Decompile reads the budget via a getter call with constant 0x34a on every inn; 68020f87: OUTPUT claim "Writes four dwords (values 0..3)" cannot be supported for the initial store. Decompile writes IsTracking's return unclamped: `*(uint *)(

## FUN_68021fca (PARTIAL)
- 68021fca: Draft asserts "No other logic, branches, or thresholds exist in this function" and lists only two operations. Contradicted: the decompile body contain; 68021fca: Draft claims "`PB` is only read" (Side Effects). Unsupported: `PB` is never referenced in the decompile; the only operations are `FUN_68023b00((undefi; 68021fca: Draft's PURPOSE ("base quantity ... plus the `generalSlop` balance parameter") presents the `generalSlop` identity as fact; the decompile only shows `

## FUN_68022316 (PARTIAL)
- FUN_68003170 / return of FUN_68022316: draft's rule 6 and §2 claim the threshold is `PB[likelyOutFrames]` with "default 20" and quote "exact code: `PB[likelyOut; 0x6809f510 gate (draft §2 and rule 4): draft claims a direct read — "If byte at `0x6809f510` != 0". Decompile shows the value is obtained via a call: `cVar1 = F; §4 output line: "true when `frames − base ≥ 20` (with default PB)" — contradicted for the same reason as above; the comparison operand is `FUN_68003170(0x34a)`'

## FUN_68023268 (PARTIAL)
- §3.5/§3.8/§3.10/§4 ("PB[relaySlop]" as a direct read): the decompile shows the added term is a helper call, `uVar8 = FUN_68003170(0x344);`, at both slop sites (; §1/§3.10 ("default 12"): no literal `12`/`0xC` exists anywhere in the decompile; the slop value is whatever `FUN_68003170(0x344)` returns. The "default 12" cons; §4 ("reads PB[relaySlop]"): same evidence

## FUN_6802baf7 (PARTIAL)
- 6802baf7 (header): "params=19" is contradicted by the decompile signature `void FUN_6802baf7(void)` — the function takes no arguments. The 19 corresponds to the; 6802baf7 §5 table: all 19 "Default" values (7500, 6500, 8500, 1800, 2200, 28, 28, 28, 6500, 180, 180, 90, 350, 550, 180, 300, 2200, 9999, 9999) appear nowhere i

## FUN_6802ef90 (PARTIAL)
- 6802ef90: draft header claims `params=3`; decompile signature is `undefined4 __cdecl FUN_6802ef90(undefined4 param_1)` — a single 4-byte stack parameter, not th; 6802ef90 OUTPUT: "pure function of `param_1` and the PB table" — the draft never mentions `FUN_68003170`, which the decompile calls three times to fetch the thr

## FUN_6802fe35 (PARTIAL)
- FUN_6802fe35 header "params=72": decompile signature is `undefined4 * __fastcall FUN_6802fe35(undefined4 *param_1)` — exactly one parameter; 72 is not a paramet; 0x68096690–0x680967ac (§1 purpose, §3 rule 7): draft claims the table is copied "verbatim" from PB fields with "no scaling"; decompile shows every entry is a he; §2 "PB table entries: pitchObj<B><S>Count{Establish|Outside|Best|BestCenter|FastCenter|Plus}Weight": invented field names; decompile contains only numeric `FUN_; §3 rule 7 ordering ("situationIndex 00,01,02,10,… consistent with balls*3+strikes"; "weightIndex order = Establish, Outside, Best, BestCenter, FastCenter, Plus"; §3 note "default weights sum to 100 in every count (e.g. 0-0: 0+25+0+0+0+75; 3-2: 0+0+20+10+20+50)": no numeric weight constants appear anywhere in the decompil; §4 "since it is global, the last-constructed instance's PB values win": table population never reads `param_1` — all 72 stores use fixed IDs via `FUN_68003170`;; §5 "the eight `0x45` (69) defaults at `this+0x97`–`this+0xbb`": decompile sets nine dwords to 0x45 — `+0x9b`, `+0x97` (copied from `+0x9b`), `+0xa3`, `+0xa7`, `

## FUN_68030a6f (PARTIAL)
- 68030a6f: draft header claims `params=2`; decompile signature is `void __fastcall FUN_68030a6f(int param_1)` — a single argument, and no second parameter is ref

## FUN_68036c6c (PARTIAL)
- 68036c6c: "params=3" — decompile signature is `short FUN_68036c6c(int param_1)`; exactly one int parameter is declared and used, no second/third argument appear; 68036c6c: "via three getters" — the decompile makes four calls against `0x680a57b7`: `FUN_68032ff0(0x680a57b7)`, `FUN_6800f600(0x680a57b7)`, `FUN_6800f570(0x680; 68036c6c: PB constants `holdChanceBase=0`, `holdChanceMinRunnerSpeed=30`, `holdChanceAdjust=100` (and the derived output claim "With defaults: 0 or 100") — cann

## FUN_68036d52 (PARTIAL)
- 68036d52: header claims `params=4`, but the decompile signature is `short __fastcall FUN_68036d52(int param_1)` — a single int parameter.; 68036d52: "so with defaults, more pitches → higher chance via `(4-p)*-10`" is derived from the unsupported `pitchesMult=-10`; the decompile gives no sign or mag; 68036d52: the draft presents the coefficients as a `PB[...]` table but omits that they are fetched via four `FUN_68003170(n)` calls with indices 10, 0xb, 0xc, 0; 68036d52: rule 5's `lead = FUN_68038e30(R2 == 0 ? R1 : R2)` reuses R1/R2 from rule 1, but the decompile re-invokes the getters (`if (iVar2 == 0) { iVar1 = FUN_6

## FUN_68036e91 (MISMATCH)
- 68036e91: header claims `params=10`; decompile signature is `short __fastcall FUN_68036e91(int param_1)` — a single int parameter.; 68036e91: rule 3 claims both gate thresholds are `PB[...]` index 25; decompile uses two distinct lookups: `iVar5 = FUN_68003170(0xe), iVar5 <= iVar11 || (iVar5 ; 68036e91: rule 4 claims base value is `PB[...]` index 25; decompile: `uVar12 = FUN_68003170(0x10); local_2c = (short)uVar12;` — index 0x10 (16), a third distinc; 68036e91: rule 5 ball-count adjustments (+5 / 0 / −25 / −100) cannot be supported; decompile shows only opaque lookups `FUN_68003170(0x11)` / `(0x12)` / `(0x13); 68036e91: rule 7 home adjustment (−5) cannot be supported; decompile shows only `FUN_68003170(0x17)` behind `*(int *)(param_1 + 0x348e) == 1`.; 68036e91: rule 3's shared "(25)" implies base value and both thresholds come from one table entry; decompile contradicts this with three separate indices 0xe, 0

## FUN_68039750 (PARTIAL)
- FUN_68039750 (rule 11 / INPUTS "PB[throwHeightPct] = 70"): draft asserts the second argument to FUN_68005b80 is the constant 70 and omits a helper call entirely

## FUN_6803a6f0 (PARTIAL)
- 6803a6f0: scale-argument sourcing wrong/omitted — draft claims the 2nd arg of `FUN_68005b80` is `PB[ballWindSpeedPct]`, but the decompile computes it as `iVar2 ; 6803a6f0: invented constant "(default 40)" — no `40`/`0x28` exists in the decompile; the only immediates on the cache-miss path are `0x2db` (arg to `FUN_6800317

## FUN_6803aa6b (PARTIAL)
- 6803aa7c: Draft rule 3 / PURPOSE / INPUTS claim the second setter gets `PB[ballAirResistancePct]` (default 95) "read directly by this function". Decompile contr; 6803aa7c: Draft omits the call `FUN_68003170(0x2df)` entirely from RULES; the decompile inserts it between the `FUN_6803bd30(&DAT_68114908,iVar1)` store and the; 6803aa6b (PURPOSE): "updates its air-resistance-related values (one from a helper call, one from `PB[ballAirResistancePct]`, one hardcoded 100)" — only two of t

## FUN_68043fcf (PARTIAL)
- post-Pass-A gate (code between the Pass A loop ending at LAB_68043ffc and the Pass B loop ending at LAB_6804419c): draft §2/R5 claims the Pass-B threshold is `P

## FUN_680447dc (PARTIAL)
- 680447dc: header claims "params=5", but the decompile signature is `void __fastcall FUN_680447dc(void *param_1)` — a single argument. No 5-parameter form exists; 680447dc: OUTPUT line "Calls FUN_68049d61 per updated record" is contradicted by the decompile, which calls `FUN_68049d61(param_1,local_c)` unconditionally afte

## FUN_68049d61 (PARTIAL)
- 68049d61: rule 6's "holds with defaults" (exhaustedThresh < tiredThresh) rests on the unsupported defaults; the decompile supports only that the `FUN_68003170(0; 68049d61: purpose says the flag is raised "when the pitcher first drops out" of the top two states; decompile re-raises on every ≤1→≥2 transition — `if ((1 < iV; 68049d61: rule 2's "(each fetched twice; same values)" — the decompile re-fetches via `FUN_6803e1b2(this_00,3)` and `FUN_6803e1b2(this_00,4)` before each compar

## FUN_6804a64d (PARTIAL)
- 6804a64d (header): draft claims `params=3`; decompile signature is `bool __fastcall FUN_6804a64d(void *param_1)` — exactly one parameter, and no second/third ar; 6804a64d (§2 PB line, §3 rule 1): draft asserts the threshold's second operand is `PB[pitcherToastPctPitchesLeft]` (index 10); decompile computes `iVar10 = FUN_; 6804a64d (§2 PB line, §3 rule 5): draft asserts the upper lead bound is `PB[pitcherToastMaxLead]` (2); decompile uses `iVar13 = FUN_68003170(0xbc); if (((int)((; 6804a64d (§2 PB line, §3 rule 5): draft asserts the lower lead bound is `PB[pitcherToastMinLead]` (0); decompile uses `iVar13 = FUN_68003170(0xbd), iVar13 <= (i

## FUN_680506fd (PARTIAL)
- 0x680506fd (§1, §3 rule 2): threshold source is invented — the decompile computes the compare operand via a call, `iVar4 = FUN_68003170(0x2d4);`, then tests `(i; 0x680506fd (§3 rule 2): "default threshold 60" is unsupported/contradicted — no literal 60 (0x3c) appears in the decompile; the only constant feeding the compar
