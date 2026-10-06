# FPS Baseball Pro '98 - handoff (written 2026-10-06 from the MacBook session)

## Where things are (this Optiplex, user `will`)
- Game install (Wine prefix): ~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98  (Wine 11 staging, WinXP mode)
- Launch on the real desktop: ~/play_bbpro98.sh  (also app-menu entry "FPS Baseball Pro 98")
- Hidden-display test rig (Xvfb :99): ~/xc2.sh (click/shot), ~/seasons.sh (multi-season driver), ~/st.sh (status), ~/fullseason.sh, ~/replay.sh
- Season-end snapshots: ~/seasons/s2 .. s10 (Assn + Stats). s_k = state at end of season 1996+k (s10 = end of 2006). 1997 opening data: ~/bbpro98/BBPRO98_package/game/Assn
- Full package: ~/bbpro98/BBPRO98_package (game/, mods/, research/)
- Latest bbfix source: ~/bbpro98/src-latest/bbfix.c, bblaunch.c  (build: i686-w64-mingw32-gcc -O2 -shared -static-libgcc -o bbfix.dll bbfix.c -Wno-incompatible-pointer-types). NOTE research/src in the package is an OLDER copy.
- Action log written by the game: <install>/bbtrace.log (every file open, DLL load, window, timer, crash, dialog)

## What was fixed (and why the game crashed on NT-style Windows/Wine)
1. Five DLLs share preferred base 0x10000000 -> rebased on disk (EZShell 6A.., LineUp 6B.., Upstats 6C.., FPS_DCL 6D..).
2. Game leaves a window alive after unloading its shell DLL + never unregisters window classes -> bbfix.dll destroys windows / unregisters classes on FreeLibrary.
3. Game _sopen()s the season stats file (stats\MLBPA97.dat) once per game and never closes it (FPS_CT.dll); at ~2048 CRT fds -> "Error writing association data". bbfix.dll sweeps stats descriptors older than 90s (keeps the 2 oldest).
bblaunch.exe starts Baseball.exe suspended and injects bbfix.dll. Official v1.1 patch (BB9811PT) is applied but does NOT fix the above.

## Verified
10 consecutive seasons (1997-2006), 0 crashes, 0 error dialogs, ~2,400 sim games/season, fd count flat (5-90).

## Lessons / gotchas
- Never run `pkill -f <pattern>` inside an ssh command: the pattern matches the ssh shell itself and kills it. Put commands in a script file.
- Game ignores synthetic clicks sent through Wine; real X11 clicks (xdotool) work. Wine does not repaint after a sim: wiggle the mouse before screenshots.
- Simulate dialog: select "All games until next Play". Draft screens need an OK click per pick.
- The .PYR holds STARTING ratings only (stars never change across seasons); live ratings live elsewhere (ASN). PYR format is decoded: ~/bbpro98/BBPRO98_package/research/dump_pyr.py (+ notes_formats.md).

## Open threads
- Stats sanity check: use in-game Association > History / Statistics / Standings to see champions + leaders per year; check whether production drops after 1997 stars retire (league mean age rose 28.7 -> 31.7 over 8 seasons; rookies avg CH/PH ~44.6/44.6).
- Mods (user's folder): 2001/2002 season ARCs restore via BBArch.exe (work). BBEdit98 not installed (needs Wine + VB6/Jet). bbnames/bbdraft are 16-bit DOS (need DOSBox).
- Ideas the user wants: player creator (via free-agent pool), contract/salary system (game has none), rating model from Lahman stats (Lahman files were downloaded on the Mac; correlation results: contact~AVG, power~HR, speed~SB, endurance~GS).
- Not yet tested on real Windows.

## Update 2026-10-06 (Ubuntu/Fedora Optiplex session): wide Statistics screen SHIPPED to live
- Result: League Statistics shows 12 columns (batting adds OBP, SLG, Pro, Iso; pitching adds ER, HR, K/9, BB/9) in Career/Season/Players/Teams views. Verified by screenshot on the live install and a sim day (work copy).
- Mechanism: SHELL.VOL wide5 (extra gadgets in DIAL.REQ block 13, large block moved to end because block starts above ~0xfe9x fail to load) + in-memory hooks in bbfix.dll (src-latest/bbfix.c, 7 sites in BBShell.dll, all-or-nothing, on-disk BBShell.dll stays pristine). Config: <install>/bbfix.ini ([widen] bat/pit ids; stat id = SPRPLYR third-table index + 13).
- Install/revert: work/patches/install_live.sh, revert_live.sh (restores bbfix.dll, SHELL.VOL, BBShell.dll from /mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06). Never edit live directly; work copy = /mnt/nvme/bbpro98/work_install (launch with ~/bb_launch_work.sh; relaunch.sh installs build there).
- Build: zig cc (pip ziglang in /mnt/nvme/bbpro98/zigenv): python -m ziglang cc -target x86-windows-gnu -O2 -shared -o bbfix.dll bbfix.c -Wno-incompatible-pointer-types -lpsapi
- Trace: bbfix.ini [trace] draw=1 match=TEXT logs grid text + caller chain (DrawText_Shell 68065650); cell=1; text=1 (GDI, unused by grid).
- Ghidra is the source of truth: project /mnt/nvme/bbpro98/ghidra_proj (14 binaries), query with ~/../mnt/nvme/bbpro98/ghidra_scripts/gh.sh (decomp/xrefs/rename/batch/regen). Rename or type everything in Ghidra the same step you learn it.
- Not verified: Lineup (in-game play) screen, Hall of Fame screen, Team Statistics (not widened, 8 cols), Change Columns dialog still edits 8 slots (ext columns fixed by ini, not user-editable), full season run with hooks.
- Landmine: thiscall helpers 680436c0/68043400 take 2 stack args and `ret 8`.
