#!/bin/bash
# launches the game from the WORK copy (never the live install)
export WINEPREFIX=$HOME/.bbpro98_prefix WINEDEBUG=+profile DISPLAY=:99 PULSE_SINK=bbnull
cd $WINEPREFIX/drive_c/Sierra/BBPRO_98_work && exec wine bblaunch.exe
