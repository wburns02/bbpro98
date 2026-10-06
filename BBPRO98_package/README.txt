FPS Baseball Pro '98 - fixed build (v1.1 patch + Win9x/NT crash fixes)
=====================================================================
INSTALL (Windows 10/11, the Optiplex):
 1. Copy everything inside the "game" folder to  C:\Sierra\BBPRO_98   (path matters: bbfix looks for C:\Sierra)
 2. Copy PLAY_BBPRO98.bat into that folder and double-click it (or run bblaunch.exe).
    First run: tick "Don't show this again" on the 256-colour message, OK.
 3. Mods: run BBArch.exe in that folder -> Restore the .ARC files in "mods" (2001/2002 seasons) into the Assn folder.
 4. Action log: C:\Sierra\BBPRO_98\bbtrace.log  (open in a viewer that follows the file, e.g. PowerShell:  Get-Content bbtrace.log -Wait)

WHAT THE FIXES ARE (see research\):
 - Five DLLs share the same preferred load address; on NT-style Windows they reload elsewhere -> crash. Pre-rebased in this package.
 - The game leaves a window alive after unloading its DLL, and doesn't unregister window classes -> bbfix.dll cleans up.
 STATUS: verified on macOS/Wine (Apple Silicon): 30 straight sim days, draft, ~1700 games, 0 faults. NOT yet tested on real Windows.
 If it misbehaves on Windows, keep bbtrace.log - it shows the exact call that failed.

NOT INCLUDED: the original game CD image (you already have it) and the Wine test harness (Mac-only).
