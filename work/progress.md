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
