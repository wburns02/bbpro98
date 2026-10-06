# FUN_68053d2e consumer of init-loaded PB globals

DRAFT (GLM-Flash, unaudited)

**PURPOSE**
Resolves one batter's swing against the pitched ball: rolls a contact outcome (0–5), applies a bat-power/handle modifier from the balance tables, and if contact is made, simulates the batted ball and writes the result into the play record.

**INPUTS**
- `param_1+0x6b` — view/renderer object; `param_1+0x7b` — team/side flag (0 selects first of two update targets) *(guess: home/away)*
- `DAT_680a224c` — game-state object (pitch data via `FUN_6800f750`, more via `FUN_68055730`)
- `DAT_680a2254` (`local_4c`) — current pitch/at-bat object (`FUN_6800f3d0`, `FUN_6802fc70`, `FUN_6802e67c`, `FUN_6802e615`)
- `DAT_68114948` — rating table read by `FUN_680556e0` *(guess: batter timing/eye rating)*
- `DAT_68185a60` — RNG state (consumed by `FUN_68082999`)
- `DAT_680a58de` — play record, both read (gate at entry) and written
- `local_58` — accumulated swing-timing value; filled via `FUN_6800bb2c(&local_5c)` block *(guess)*; `local_28`/`local_24` — pitch location vs. swing aim *(guess)*; `local_48`/`local_44`/`local_38` — initial batted-ball vector

**RULES**
1. **Gates:** run only if `FUN_6800f450(DAT_680a58de)==0`, the close/tracking checks pass, and `FUN_6803cc73() < 2` (or view state == 2).
2. **Rating:** `rating = FUN_680556e0(DAT_68114948, …)`; forced to **100** if `FUN_6803cc73() < 2`.
3. **Flag** `local_18 = (FUN_68009560(FUN_6800f3d0(DAT_680a2254)) <= rating/100)`; cleared if `FUN_6802fc70(DAT_680a2254)==1`; if view state == 2, cleared when `rand(100) < PB[failedCheckContactChance]`. (Never read afterward — see UNCERTAIN.)
4. **Timing accumulation:** `local_c = (local_64 * local_38 * 0x2C0) / 40000` (0x2C0 = 704); `local_54 = 0x24 − FUN_68009560(local_c)` (0x24 = 36); `local_58 += FUN_6807c09c(local_54, local_c)`.
5. **Contact probability:** `local_34 = FUN_68009470(100, local_58)` — used as a 0–100 percentage threshold below.
6. **Whiff check:** `hi16(combined) = FUN_68005c40(local_28, local_24).hi * 200 + rand(0..200) − 100`; if `FUN_68009560(hi16) > rating` → outcome = **5** (no contact).
7. **Outcome roll:** otherwise `ratio = low16(combined) * 100 / rating`, switch on `ratio` (rand = `rand(100)`, threshold = `local_34`):

   | ratio | outcome |
   |---|---|
   | 0 | 2 |
   | 1 | rand < local_34 ? 2 : 3 |
   | 2 | rand < local_34 ? 3 : 5 |
   | −5, −6 | rand < local_34 ? 0 : 5 |
   | −3, −4 | rand < local_34 ? 0 : 1 |
   | −1, −2 | rand < local_34 ? 2 : 1 |
   | other | 5 |

8. **Power/handle modifier:** `local_10 = FUN_68005b80(local_10, local_34)`, then `local_14 = PBG[batPowerHandleBase][outcome] + rand(PBG[batPowerHandleRange][outcome])` (both arrays indexed 0–5 by outcome), then `local_10 = FUN_68005b80(local_10, local_14)`.
9. **Contact condition:** contact made iff `outcome != 5` **and** `FUN_68009560(local_58) < 0x4000` (16384).
10. **On contact:** call `FUN_68054d4a(param_1, local_5c, (short)local_58, local_10, &{local_48, local_44, local_38}, &out{local_7c, local_78, local_74})`; copy pitch fields (`FUN_6802e67c(DAT_680a2254, buf, 0x1e)`) plus the batted-ball result into `DAT_680a58de+0xD..0x1D`; finalize via `FUN_6802fca0`/`FUN_68009c2c`; if view state == 3 set `DAT_681147a0 = 2`; post update message 4 to `DAT_68114BA8` (or `+0x173BE` variant if `param_1+0x7b != 0`); refresh document (`FUN_6802E615`, `FUN_68055770`, `InvalidateObjectCache`).

**OUTPUT/SIDE EFFECTS**
- Play record `DAT_680a58de` offsets 0xD–0x1D written (pitch fields + batted-ball result).
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
