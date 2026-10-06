#!/bin/bash
# play_bbpro98.sh : run FPS Baseball Pro '98 (fixed build) on the REAL desktop
export WINEPREFIX=$HOME/.bbpro98_prefix WINEDEBUG=-all
export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0
[ -z "$DISPLAY" ] && export DISPLAY=:0
[ -z "$XAUTHORITY" ] && export XAUTHORITY=$(ls /run/user/$(id -u)/.mutter-Xwaylandauth.* 2>/dev/null | head -1)
cd "$WINEPREFIX/drive_c/Sierra/BBPRO_98" && exec wine bblaunch.exe
