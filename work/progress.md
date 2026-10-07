# progress (tiered-build-loop, wide stats)
- M0 RESULT 2026-10-06: G0 FAILED. Three positive controls left the Statistics screen unchanged: (1) BBShell imul 0x32 pitch at 0x6804290f (Hall of Fame layout) and 0x6804f7d3, set to 0x10; (2) _DEFAULT.STS last batting id changed; (3) BBShell .data table 0x6808c2e8 entry 0 last id changed (file off 0x8ad0c). The default set also exists in LineUp.dll at 0x35428. Statistics screen config source not located (suspect SHELL.VOL resources, MENU.REQ/DIAL.REQ, or Assn state). Live install restored to pristine and verified.
- Decision: Fallback F (wide stats window from Stats/mlbpa97.DAT) per PLAN_widen_oneshot.md.
- Lesson: bytepatch.py once inserted bytes (old/new length mismatch); fixed with a length assert. Restored from backup.

## 2026-10-06 M-wide: SHELL.VOL widening LOADS
- Crash cause: VOLM dir has a final u32 at 0x234 (end-of-data sentinel) that must also shift by the growth. build_wide_vol.py now does it. No per-file 9-byte header fix needed.
- r6.png: 4 extra gadget columns EX1..EX4 render, name/stat columns narrowed. Good build saved: /mnt/nvme/bbpro98/vol/SHELL_wide_ok_EXhdrs.VOL
- NEXT: code hook so cells 10..14 are filled (FUN_6805c930) + header text for ids 0x28.. (after FUN_6805cb20 in FUN_6800d300).

- 2026-10-06 step 3 done: grid text routine DrawText_Shell 68065650 found and trace-hooked (draw=1). Ghidra names backfilled (backfill_2.py). Wide view screenshot t2b verified 12 cols. Next: regen _all.c, regression screens (pitching, Lineup, Draft, HoF, Career, Players, Accumulated, Change Columns, sim day), revert script, M6.
- 2026-10-06 M5/M6 done: regression screens read (pitching, Players, Teams, Change Columns, News, Data, History, Team Stats/Roster, Draft, sim day) all OK, no faults from widen hooks. install_live.sh run, live screenshot L2 shows 12 cols. revert_live.sh written. Untested: Lineup, Hall of Fame, full season.

## RE tiers 1-3 (2026-10-06 session 9cc76df6)
- Plan: work/RE_PLAN_tiers1-3.md (Opus planner, verified exists). Findings: work/RE_FINDINGS.md.
- [x] M0 decompile all 14 binaries (index/*/_all.c, _functions.tsv; metrics in work/M0_metrics.txt)
- [ ] M1 labeling: source-file anchors first (re/srcmap.py), then call-graph propagation, then GLM for residue

## 2026-10-06 evening
- Renames applied + readback-verified + regen: Baseball, FastSim, BBSIM, BBCfg, FPS_Pal, FPS_DCL, FPS_Ctrl, ODASL.
- Pending: FPS_CT, LineUp, Upstats, EZShell, BBShell labeling (drive_rest.sh), then rename spec + regen, ASN decode, final Artifact report.
- 2026-10-06 night: ALL 14 binaries labeled; renames applied + regen (total ~7516). Remaining: Tier 3 audits (about 5 of 74 audited), PB.INI downstream experiment, ASN field decode. Final report published (see below).
- 2026-10-07: parked at 98% Claude usage. Next, in order: PB.INI controlled experiment, Tier 3 draft audits, ASN fields.

## PB.INI experiment setup (2026-10-07, before compaction)
- Design: arm A baseline (no PB.INI), arm B [PlayBalance] stealChance00Count=100 (idx 54, default -10, consumer 68065947). Observable: steal attempts in day logs; 3 sim days per arm from work_state_s10.
- Data reset = cp -a work_state_s10/{Assn,Stats} over work_install. Logs collected to /mnt/nvme/bbpro98/re/pbexp/armX/ (old logs moved to pbexp/old/).
- Launch: setsid bash /mnt/nvme/bbpro98/re/launch_prof.sh (Xvfb :99, work copy via BBPRO_98_work symlink). Rig: /home/will/xc2.sh (click/shot to $HOME/*.png).
- State problem: work_state_s10 opens at "Monday, January 1, 2007" needing the Free Agent draft before any sim. Path so far: main menu League Management (495,677; needs 2 clicks) > Association menu > Start/Resume Draft (479,491 worked once) > Free Agent Draft screen (Round 1, Boston).
- RIG LANDMINES: clicks on Action drop-down items do NOT register (6 attempts, y=405 Skip Draft); menu-title clicks DO work; Alt+A opens Association; F10+Right x3+Return opens Action drop-down; letter "s" in open drop-down EXECUTED Set Criteria (letters execute items); "d" and "k" no visible effect; Escape needs --clearmodifiers to dismiss stuck menus; Set Criteria dialog cancels via Cancel button click (758,635).
- NEXT: finish getting the draft done (try letters i,f,t on open Action drop-down, or Down-highlight+Enter combos), verify draft completes, then find sim-day path (Action menu Simulate? schedule screen?), sim 3 days, collect logs, repeat for arm B with PB.INI.

## 2026-10-07 GLM window (post-compact)
- [x] PB.INI experiment DONE + validated (stealChance00Count=100: SB 8.9x, CS 11.5x). Null arm A2 confirms: null spread SB 240/228, R swings 18%, so effects >5x spread are resolvable at 10 days. RE_FINDINGS.md updated, committed 0b8dbb7.
- [x] Spec draft headers fixed: params= field (counted getter calls, garbage) replaced with real decompile signatures in all 70 drafts (re/fix_headers.py).
- [~] Tier 3 audits pass 2 (re/audit_spec2.py): taught PB-getter identity FUN_68003170(idx)=*(u32*)(&DAT_6808fde0+idx*4) + per-draft pb_table rows injected. Pass 1 was useless (24/25 PARTIAL from getter-opaqueness false positives). Pass 2: MATCH quality high (verified 68003899, 6800b36e, 68016855 samples). Batch running, 73 files, resumable, max_tokens 16000 (8000 starved reasoning -> fails).
- [~] ASN field decode STARTED via 3-arm byte diff: churn = ring-log rotations in region ~0x7400-0x8600 (rotating byte windows = circular game-results log). Running per-day ASN sequence (asnseq/day01..day10) to get time series. Analyzer ready: re/asndiff2.py (churn regions + constant-delta u16 fields = head pointers/dates/counters).
- Rig ops notes: stale armA Wine Debugger/Program Error dialogs stole focus and broke a sim day (kill stale wine dialogs by exact pid; xdotool windowfocus the Baseball window). simdays.py SKIP_MENU=1 resumes from schedule screen.
- 2026-10-07 ~10:20 DONE: audit pass 2 complete, 72/73 graded (55 MATCH, 17 PARTIAL annotated with CORRECTIONS; FUN_68054d4a_consumer unaudited, slice over budget twice). Spec index + work/spec + work/spec_audit committed (595cc13). ASN decode advanced (date fields, tail results log, aggregate region). PB.INI null distribution banked. All LLM work on Hive; interactive session Z.AI-only for orchestration.
- 2026-10-07 ~10:45: fix tier done on Hive: 14 RULES v2 sections (superseding corrected rules) appended to PARTIAL drafts, all 17 PARTIALs annotated. Open for next session: pass-3 verification audit of the v2 rules; ASN semantic anchoring (box scores or FPS_CT read paths); FUN_68054d4a_consumer audit.
- 2026-10-07 ~14:40 tiered loop (tbl-20261007T142541Z-3e042e): near-term goals 1-3 DONE. Pass 3: 14/14 v2 RESOLVED (2 after one fix round), merged into bodies, post-merge spot audit MATCH + one propagated quote fixed inline (68023dd3). FUN_68054d4a_consumer chunk-audited PARTIAL, annotated. Commits 6b9b4bd. Remaining: ASN semantics, BBSIM cross-check, FID false matches, format round-trips.
