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
