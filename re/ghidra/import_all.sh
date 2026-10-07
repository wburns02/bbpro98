#!/bin/bash
# imports pristine game binaries into the shared project (preferred PE bases; BBSIM/FastSim share 0x68000000 with BBShell, they are never co-resident at that base at runtime: record real bases from bbtrace 'DLL loaded' lines)
G=/mnt/nvme/ghidra/ghidra_12.1.4_PUBLIC; B=/mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06
exec $G/support/analyzeHeadless /mnt/nvme/bbpro98/ghidra_proj BBShell -import $B/Baseball.exe $B/EZShell.dll $B/FPS_CT.dll $B/LineUp.dll $B/Upstats.dll $B/FPS_DCL.dll $B/BBSIM.dll $B/FastSim.dll $B/ODASL.dll $B/BBCfg.dll $B/FPS_Ctrl.dll $B/FPS_Pal.dll $B/IC_Cfg.dll
