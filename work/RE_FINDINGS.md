# RE findings (running log, tiers 1-3)

## 2026-10-06 M0 measured (replaces plan section 1 estimates)
Functions / decompiled KB per binary (from /mnt/nvme/bbpro98/index/*/_functions.tsv, _all.c):
BBShell 3728/2696, BBSIM 3763/2456, FastSim 2974/2100, EZShell 1862/1028, LineUp 1659/972, Upstats 1633/1012,
FPS_CT 313/416, ODASL 170/140, Baseball 118/80, IC_Cfg 97/76, FPS_Ctrl 89/60, FPS_DCL 56/76, FPS_Pal 20/12, BBCfg 20/20.
Total about 16,500 functions, about 11 MB. The plan estimated 7,200-9,500 and 5 MB. Plan listed 16 binaries; the Ghidra
project has 14 (no RemotMgr.exe, Datain.exe). Raw: ~/bbpro98/work/M0_metrics.txt.

## Structural findings
- BBSIM.dll and FastSim.dll both statically link MFC (FID_conflict, CString, OnClose, IsTracking, ...). Large noise share.
- Assert strings expose original source filenames. BBSIM: BBSim_{Runner,Earnedr,Sync,Throw,Dbm,Act,Cams,Event,Roster,Tag,Vcr,
  Cover,Field,Status,Ball,Injury,Player,Smodel,Realism,Umpire,Game,...}.cpp. FastSim has the same modules as FastSim_F*.cpp
  (FRUNNER, FEARNEDR, FSYNC, FTHROW, FDBM, FACT, FEVENT, FROSTER, FTAG, FCAMS, FCOVER, FFIELD, FBALL, FINJURY, FSMODEL,...).
  So FastSim = the sim modules without animation/graphics; BBSIM = same plus 3D (TSpace_*.cpp, Graphics_*.cpp, Utility_*.cpp).
  Read FastSim for pure logic, use BBSIM as a cross-check twin.
- Assert call is FUN_680aa8f9(file,line,msg) in BBSIM. Source-file attribution script: /mnt/nvme/bbpro98/re/srcmap.py.
- The game has built-in debug logging switched by ini section [Debug]: DrawPitchPath, InjuryLog, PitchResultLog (writes
  pitchres_log), PitchSelLog, PitchVisible. Free ground truth for Tier 3. Not yet tried.
- Baseball.exe is only 118 functions (launcher). The sim lives in BBSIM/FastSim.
- INJURY.DAT is loaded by BBSim_Injury.cpp (data file not previously listed).

## PlayBalance table (Tier 3 anchor, found 2026-10-06)
- BBSIM FUN_68039455 = PB_LoadIni: reads 0x368 (872) int params from [PlayBalance] in PB.INI (next to the exe, not shipped) via
  GetPrivateProfileIntA into global table DAT_680bc2d0 (defaults baked in the DLL data). Names: pointer array 0x680bb530.
- BBSIM FUN_6803954f = PB_DumpToFile: writes all current values to pb.txt (the game can dump its own tuning table).
- BBSIM FUN_68002cd0 = PB_Get(idx): returns table[idx]. 72 callers pass constant indexes, covering 871 of 872 params.
- Sierra documented 831 params in PBINI.TXT (90 KB, with entry types: base value, percent modifier, adjustment, dice
  Count/Faces/Base, weights, dividers). 41 params are undocumented. 405 documented defaults differ from the DLL defaults:
  trust the DLL (pb_table_BBSIM.tsv col dll_default), not the doc.
- So a PB.INI file is an official, supported way to change sim behavior with no hooks. Not yet tried.
- Sim decision core = ~71 functions (work/sim_core_bbsim.tsv, sorted by param count). Largest: 68056fbc relief/pinch-hit
  logic (112 params, BBSim_Roster), 6803a479 and 6803c8f5 (pitch speed/selection, BBSim_Players2), 6801f976 fielder positioning,
  68065947 steal chance, 6800b2fd baserunner lead logic, 6802c303 catch chance, 68065fba hit-and-run, 680583cb pinch runner.
- Files: re/pbtable.py builds pb_table_<bin>.tsv. FastSim table addresses not yet derived (needs name-array and table addresses).

## Built-in debug logs WORK (verified 2026-10-06, work copy)
- Needs BBPRO.INI: [Sim] Fast=0 (BBSIM engine; FastSim never applies the log flags, its FUN_680621e0 has no callers) and
  [Debug] DebugEnabled=1 plus RandomLog/HitLog/PitchResultLog/PitchSelLog/EventLog/InjuryLog/SubsLog/PlaySetupLog=1.
  Gate is BBSIM FUN_6807cb44 (applies the flags), called only when DebugEnabled != 0.
- One simulated day (15 games, April 4 1997) wrote to the game dir: pitchres.log (u32 counts, raw table behind prlog.txt),
  prlog.txt (pitch outcome by ball-strike count: balls/swinging strikes/called strikes/fouls/in play, counts and percentages),
  sub.log (substitution decisions with "Chance = N" values), hit.log (88 KB, mostly zero bytes, 1195 records), game.txt
  (per-game stadium, weather). hilights/ gets files. Saved copies: /mnt/nvme/bbpro98/re/debuglogs/.
- No random/event/injury log files appeared yet (maybe none triggered, or different path). Open item.
- Use for Tier 3 validation: prlog.txt gives real pitch-outcome distributions per count for chi-square checks.
- Caution: Fast=0 sims are slower; the work INI is now Fast=0 with debug on (original: re/BBPRO.INI.orig).

## GLM labeling pilot (Baseball.exe, 99 residue functions, 3 batches, 0 failures)
Output looks plausible and cites strings/callees. Needs the audit gate (spot check 100 across binaries) before trusting.

## Tier 3 spec draft audit log (2026-10-06)
- FUN_6802baf7 (FastSim_FINJURY init): audited by Claude against decompile. Open/read sizes (0x2c, 0x26), 19 PB indices 0x354..0x366 written as u16 at DAT_68113b88+0..0x24, discard of file-read table B: all correct. Grade CONFIRMED. GLM draft accuracy on init-style functions is good; formula-heavy functions still need audit.
- Spec drafts: re/spec/FUN_*.md (68 of 69; one repeatedly fails, likely the largest). Hive streams can hang: label_glm.py ex.map blocks on a hung batch; kill and use label_escalate.py.

## Label audit gate, FastSim (2026-10-06, Claude read 40 of 2353 against the decompile)
- Accuracy: 38/40 acceptable, 2 wrong or unsupported (680371f8 mislabeled UI_MAIN splitter, it is a PB-driven sim function; 68008e05 cites an MFC FID collision). ~5% wrong, at the limit.
- Evidence mix from GLM residue: XREF_CONFIDENT 46%, STRING_XREF 12%, PATTERN_GUESS 38%, UNKNOWN 4%. Below the 80% target as a distribution, so the gate was applied by policy instead: only XREF_CONFIDENT and STRING_XREF names are written to Ghidra; PATTERN_GUESS and UNKNOWN never are.
- Noise filter: labels whose support cites IsTracking, _AFX_*, CSplitterWnd, CControlBar (Ghidra FID collisions) are dropped (22 in FastSim).
- Applied via gh.sh batch: Baseball 94, FastSim 1255 renames (re/rename_spec_Baseball_FastSim.py). Verified by decomp readback. Renamed names are SUBSYS_short_name; treat as XREF_CONFIDENT at best, not CONFIRMED.
- Hive streams can hang; label_glm.py then stalls on ex.map. Fix used: kill it, run label_escalate.py (split 10, then DeepSeek-Flash).

- Audit (Claude vs decompile): FUN_68050eb0 (FRUNNRS2 init): the 20 PB->global writes (0x68097608..0x68097654, indices 0x2bc..0x2cf) CONFIRMED exactly; the draft's "MFC property sheet" narrative is a Ghidra FID false match (EnableStackedTabs) and is WRONG as semantics. FUN_6800a7ad: 48 PB->global copies (0x6808cef8..0x6808cfb4) CONFIRMED, numbers.inf load plus 0x1f..0x10 byte fill CONFIRMED.
- Key structural finding: many of the 69 PB-reading FastSim functions are INIT LOADERS (copy PB into plain globals). The decision logic lives in functions that read those globals by data xref, not by getter call. Spec must follow the data xrefs from the globals (e.g. 0x6808cef8 look/discipline/checkChance block, 0x68097608 bat zone block) to find the real consumers. Direct readers (e.g. BBSIM 68056fbc relief logic, 112 params) are the exception and read PB at decision time.
- Rule for drafts: trust tables (addresses, indices, defaults), distrust narrative semantics that cite MFC classes.

## PB.INI experiment (2026-10-06)
- Placed PB.INI with [PlayBalance] phForPitcherBase=77 and stealChance00Count=-999 next to the work exe (C:\Sierra\BBPRO_98_work\PB.INI), ran under WINEDEBUG=+profile, simulated one day via the UI.
- CONFIRMED (Wine +profile trace): the game opens that exact file at runtime and reads all [PlayBalance] keys by name; PROFILE_Load shows phForPitcherBase=77 and stealChance00Count=-999 parsed. So PB.INI is a working, supported behavior-tuning path with no hooks.
- NOT confirmed: the downstream effect on sim outcomes. sub.log and prlog.txt append across runs and the sim is not seeded identically, so a one-day before/after compare is noise. Needs a controlled design (same saved state, many days, compare aggregate rates) before claiming an effect size.
- PB_DumpToFile (pb.txt) is wired to dialog button 0xbfa in the in-game debug options dialog (FUN_6807c3fc), not run automatically.
- Test file kept at re/PB.INI.test; removed from the work copy.

## ASN payload probe (2026-10-06, Claude)
- No plaintext, additive-shift or XOR-encoded (all 255 constants) occurrences of Astros/Yankees/Houston/Red Sox in MLBPA97.ASN. Team and player names are not stored as strings in the ASN; payloads are numeric ids and small-int fields (team record 0 payload starts 01 1d 1d 1d a6 01 ...). Names likely live in PYR or other files and are joined by id. ASN stays PARTIAL: container + framing verified, field semantics unknown.
- Renames applied and readback-verified: IC_Cfg (66), FPS_CT (217, c-tree engine: IO_FILE_* / IO_REGISTRY_* names).
- LineUp: 761 renames applied (518 grade + 31 name collisions); sample audit of 3 read against decompile: all consistent (lineup role lookup, click match, scrollbar setup).
- Upstats: 817 renames applied; 3-function sample read, consistent (ctree close chain, record write, read wrapper).
- EZShell: 924 renames applied; 3-function sample read, consistent (scalar deleting destructor, child notify loop, SEH cleanup stub).
- BBShell: 1703 renames applied; 3-function sample read: one clear (simple select dialog setup), two are generic SEH/dtor thunks whose names are guesses (low value).

## PB.INI controlled experiment (2026-10-07, GLM-Flash session)
- Rig: work copy configured EXACTLY like live (Fast=1, no [Debug] section, no weather.dat; debug-logged Fast=0 config crashes at BBShell FUN_68054f70 NULL-getter after weather.dat open fail; the sim's paint stalls on "Updating association data" until a click). Sim-day chain: League Mgmt (495,677 x2) > Association (440,329) > Schedule (445,395) > Action (593,330) > Simulate... (616,346) > Today's games only (543,486) > OK (571,565). Driver: re/simdays.py.
- State: live install's April-2 1997 association copied into work (pristine base; live was left there by the 10/6 regression run). Work Stats had 63 stale MLBPA97.Hxx highlight files that live lacks; they must be deleted to match.
- Validation: [PlayBalance] stealChance00Count=100 (default -10, idx 54, reader FUN_68065947). 10 sim days per arm from identical state. Trace confirms PB.INI key load; 76k runtime PB reads observed.
- Result: SB 240 -> 2148 (8.9x), CS 20 -> 230 (11.5x); AB within 0.7%; R +23%, RBI +21% (second-order), GIDP -34%. Effect size ~50x the observed AB noise, so seed variance cannot explain it. VALIDATED: the PB knob reaches sim behavior end to end.
- Batting stat columns (from NOTES_stats_format.md): c0 AB, c1-4 H splits, c5 RBI, c6 BB, c7 SO, c8 IBB, c9 HBP, c12 G, c13 R, c14 SB, c15 CS, c16 GIDP.
- Open: seed differs between arms (no seed control) - fine for large effects; for <20% effects, run a second baseline arm for the null distribution.

## GLM-Flash spec audits (2026-10-07, in progress)
- re/audit_spec.py sends each of 73 drafts + its decompile slice to GLM-Flash; verdicts in re/spec_audit/*.txt.
- Calibration: verdict claims of "wrong index/param count/constant" are checkable and the two sampled (FUN_68036e91, FUN_6802baf7 param count) verified TRUE. Claims of "invented PB names/defaults" are FALSE POSITIVES when the names+defaults match pb_table_FastSim.tsv (the audit sees only the decompile, where PB reads are opaque getter calls; e.g. 6802baf7's injuryChance table 0x354-0x366 matches the INI table exactly).
- FUN_68036e91 draft had real fabrications (index 25 vs real 0xe..0x17, params=10 vs 1); CORRECTION header added, mapping verified: pitchOutChance* indices 14..23.

## PB.INI null distribution (2026-10-07, armA2)
- Second baseline arm (armA2, same state, 10 sim days, own seed) vs armA. Null spread (A vs A2): AB 16036/16516 (3.0%), R 1398/1646 (17.7%), SB 240/228 (5%), CS 20/4, SO 3602/3558 (1.2%), BB 1102/1084, HR 424/520 (20%).
- Treatment armB vs null mean: SB 2148 vs ~234 mean = +1914, about 160x the SB null spread. CS 230 vs ~12. The stealChance00Count validation stands; seed variance cannot touch it.
- Noise floor for this rig at 10 days: R and HR swing ~20% between identical-config arms, AB/SO/BB ~1-3%. Any future single-knob validation must predict an effect larger than the relevant null spread, or run longer/multi-seed arms. Second-order effects of the steal knob (AB -0.7%, SO -3%) are within noise.
- Ops: a stale armA "Wine Debugger"/"Program Error" dialog pair left on :99 stole focus and broke a sim day (day-5 done=False while the sim actually completed); kill stale wine dialogs by exact pid before arms, and focus the Baseball window (xdotool windowfocus) before click chains.
- re/simdays.py: SKIP_MENU=1 env resumes the day loop directly from the schedule screen.
