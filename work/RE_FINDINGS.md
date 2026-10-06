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
