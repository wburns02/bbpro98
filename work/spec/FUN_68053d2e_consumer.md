# FUN_68053d2e consumer of init-loaded PB globals

DRAFT (GLM-Flash, unaudited)

**PURPOSE**
Resolves one batter's swing against the pitched ball: rolls a contact outcome (0–5), applies a bat-power/handle modifier from the balance tables, and if contact is made, simulates the batted ball and writes the result into the play record.

**INPUTS**
- `param_1+0x6b` — view/renderer object; `param_1+0x7b` — team/side flag (0 selects the `+0x173BE` update target, nonzero the base `&DAT_68114ba8`) *(guess: home/away)*
- `DAT_680a224c` — game-state object (pitch data via `FUN_6800f750`, more via `FUN_68055730`)
- `DAT_680a2254` (`local_4c`) — current pitch/at-bat object (`FUN_6800f3d0`, `FUN_6802fc70`, `FUN_6802e67c`, `FUN_6802e615`)
- `DAT_68114948` — rating table read by `FUN_680556e0` *(guess: batter timing/eye rating)*
- `DAT_68185a60` — RNG state (consumed by `FUN_68082999`)
- `DAT_680a58de` — play record, both read (gate at entry) and written
- `local_58` — accumulated swing-timing value; filled via `FUN_6800bb2c(&local_5c)` block *(guess)*; `local_28`/`local_24` — pitch location vs. swing aim *(guess)*; `local_48`/`local_44`/`local_38` — initial batted-ball vector

**RULES**
1. **Gates:** run only if `FUN_6800f450(DAT_680a58de)==0`, the close/tracking checks pass, and `FUN_6803cc73() < 2` (or view state == 2).
2. **Rating:** `rating = FUN_680556e0(DAT_68114948, …)`; forced to **100** if `FUN_6803cc73() < 2`.
**Flag** `local_18 = (FUN_68009560(FUN_6800f3d0(DAT_680a2254)) <= rating/100)`; cleared if `FUN_6802fc70(DAT_680a2254)==1`; if view state == 2, cleared when `FUN_68003170(0x301) < rand(100)` (PB[0x301=769, failedCheckContactChance] < rand(100)). (Never read afterward — see UNCERTAIN.)
4. **Timing accumulation:** `local_c = (local_64 * local_38 * 0x2C0) / 40000` (0x2C0 = 704); `local_54 = 0x24 − FUN_68009560(local_c)` (0x24 = 36); `local_58 += FUN_6807c09c(local_54, local_c)`.
5. **Contact probability:** `local_34 = FUN_68009470(100, local_58)` — used as a 0–100 percentage threshold below.
6. **Whiff check:** `hi16(combined) = FUN_68005c40(local_28, local_24).hi * 200 + rand(0..200) − 100`; if `FUN_68009560(hi16) > rating` → outcome = **5** (no contact).
**Outcome roll:** otherwise `ratio = low16(combined) * 100 / rating`, switch on `ratio` (rand = `rand(100)`, threshold = `local_34`):
| ratio | outcome |
|---|---|
| 0 | 2 |
| 1 | rand < local_34 ? 2 : 3 |
| 2 | rand < local_34 ? 3 : 5 |
| −5, −6 | rand < local_34 ? 0 : 5 |
| −3, −4 | rand < local_34 ? 1 : 0 |
| −1, −2 | rand < local_34 ? 2 : 1 |
| other | 5 |
9. **Contact condition:** contact made iff `outcome != 5` **and** `FUN_68009560(local_58) < 0x4000` (16384).
**Power/handle modifier:** `local_10 = FUN_68005b80(local_10, local_34)`, then `local_14 = *(int *)(&DAT_68097608 + outcome*4) + rand(*(uint *)(&DAT_68097618 + outcome*4))` (static arrays indexed 0–5 by outcome; no getter feeds these arrays; the function's only getter call is `FUN_68003170(0x301)` (rule 3), then `local_10 = FUN_68005b80(local_10, local_14)`.

**On contact:** zero-init `&local_7c` via `FUN_68011090(&local_7c,0,0,0)`; call `FUN_68054d4a(param_1, local_5c, (short)local_58, local_10, &local_70, &local_68, &local_7c)` (7 args; `&local_70` holds {local_48, local_44} via local_6c, `&local_68` holds local_38, `&local_7c` receives {local_7c, local_78, local_74}); copy pitch fields (`FUN_6802e67c(DAT_680a2254, buf, 0x1e)`) plus the batted-ball result into `DAT_680a58de+0xD..0x1E`; finalize via `FUN_6802fca0`/`FUN_68009c2c`; if view state == 3 set `DAT_681147a0 = 2`; post update message 4 to `&DAT_68114ba8 + 0x173BE` when `param_1+0x7b == 0`, else to `&DAT_68114ba8`; refresh document (`FUN_6802e615`, `FUN_68055770`, `InvalidateObjectCache`).
replaces OUTPUT/SIDE EFFECTS (first bullet): Play record `DAT_680a58de` offsets 0xD–0x1E written (pitch fields + batted-ball result; final store `*(undefined2 *)(local_30 + 0x1d) = local_74;` is a 2-byte write).
- `DAT_681147a0 = 2` when view state == 3.
- UI/document update messages; RNG state advanced (2–4 rolls per call).

**UNCERTAIN**
- Semantics of helpers `FUN_68009560` (abs? scale?), `FUN_68009470` (clamp to 100?), `FUN_68005b80` (combine/apply modifier), `FUN_6807c09c`, `FUN_68005c40` — formulas above are verbatim but their meaning is inferred.
- Meaning of outcome codes 0–5; only 5 is clearly "no contact" (initial value, default case, excluded from contact path).
- `local_18` is written (rule 3) but never read in this listing — dead store or a use the decompiler dropped.
- Initial value of `local_58` — presumed filled by `FUN_6800bb2c` writing through `&local_5c`, unverified.
- What `local_1c` (rating) and `DAT_68114948` represent; what `FUN_6803cc73()` returns (game mode?).
- Many calls are mislabeled by Ghidra as MFC methods (`CSplitterWnd::IsTracking`, `OnClose`, etc.); real callee identities unknown.
- Whether `FUN_68082999(&DAT_68185a60, n)` is uniform [0, n) — inferred from `rand(100)` vs. percentage and `rand(201)−100` usage.
- Physical meaning of the `704/40000` scaling and the 16384 contact threshold.


CORRECTIONS (audit pass 2, GLM-Flash vs decompile; findings verified shaped, apply when editing):
- Rule 3 (view-state-2 gate): comparison inverted. Decompile: `uVar5 = FUN_68082999(&DAT_68185a60,100); iVar4 = FUN_68003170(0x301); if (iVar4 < (int)uVar5) { local_18 = 0; }` — `local_18` is cleared when PB[0x301=769, failedCheckContactChance] < rand(100), not when `rand(100) < PB[failedCheckContactChance]` as drafted.
- Rule 7 table, row "−3, −4": outcomes inverted. Decompile: `case -4: case -3: uVar5 = FUN_68082999(&DAT_68185a60,100); local_20 = (uint)((int)uVar5 < local_34);` → outcome **1** when rand < local_34, else **0**; draft says `rand < local_34 ? 0 : 1`.
- Rule 8: unsupported PlayBalance citation. Decompile contains no `FUN_68003170` call with 700/704; the modifier reads static arrays: `uVar5 = FUN_68082999(&DAT_68185a60,*(uint *)(&DAT_68097618 + local_20 * 4)); local_14 = *(int *)(&DAT_68097608 + local_20 * 4) + uVar5;`. The only getter call in the whole function is `FUN_68003170(0x301)` (rule 3), so `PBG[batPowerHandleBase]`/`PBG[batPowerHandleRange]` is not supported by this decompile.
- Rule 10 (update message): condition inverted. Decompile: `FUN_6804869a(&DAT_68114ba8 + (uint)(*(int *)((int)param_1 + 0x7b) == 0) * 0x173be,4);` — the `+0x173BE` variant is selected when `param_1+0x7b == 0`, not when `!= 0` (INPUTS line "0 selects first of two update targets" is likewise backwards).
- Rule 10 (FUN_68054d4a call): parameter count/grouping wrong. Draft lists 6 args with `&{local_48, local_44, local_38}` merged; decompile passes 7: `FUN_68054d4a(param_1,local_5c,(short)_local_58,local_10,&local_70,&local_68,&local_7c);` where `&local_70` holds {local_48, local_44} (via local_6c) and `&local_68` holds local_38 as two separate pointer arguments.
- OUTPUT/SIDE EFFECTS: write range off by one byte. Last store `*(undefined2 *)(local_30 + 0x1d) = local_74;` is a 2-byte write, so DAT_680a58de bytes 0xD–0x1E are written, not 0xD–0x1D.

CORRECTIONS HISTORY (audit pass 2 findings; rules above were rewritten accordingly):
- Rule 3 (view-state-2 gate): comparison inverted. Decompile: `uVar5 = FUN_68082999(&DAT_68185a60,100); iVar4 = FUN_68003170(0x301); if (iVar4 < (int)uVar5) { local_18 = 0; }` — `local_18` is cleared when PB[0x301=769, failedCheckContactChance] < rand(100), not when `rand(100) < PB[failedCheckContactChance]` as drafted.
