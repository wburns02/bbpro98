#!/bin/bash
# Linux launcher (needs 32-bit capable Wine: sudo apt install wine wine32  (or wine-staging))
# One-time:  export WINEPREFIX=~/.bbpro98_prefix; winecfg -v winxp ; mkdir -p ~/.bbpro98_prefix/drive_c/Sierra
#            cp -r game ~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98
export WINEPREFIX=${WINEPREFIX:-$HOME/.bbpro98_prefix}
cd "$WINEPREFIX/drive_c/Sierra/BBPRO_98" && exec wine bblaunch.exe
