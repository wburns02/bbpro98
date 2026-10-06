@echo off
REM Run from C:\Sierra\BBPRO_98 (copy the contents of the "game" folder there).
REM bblaunch starts Baseball.exe and injects bbfix.dll (fixes the season-sim crash, logs actions to bbtrace.log).
cd /d "%~dp0"
start "" bblaunch.exe
