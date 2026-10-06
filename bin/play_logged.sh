#!/bin/bash
# play_logged.sh : real-desktop launcher that records everything, every run.
# Per-run dir /mnt/nvme/bbpro98/logs/<ts>/: wine.log (stderr, err+process+loaddll+timestamp),
# windows.log (500ms poll of window geometry/state/focus), bbtrace.log copy, exit.txt.
export WINEPREFIX=$HOME/.bbpro98_prefix
export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0
[ -z "$DISPLAY" ] && export DISPLAY=:0
[ -z "$XAUTHORITY" ] && export XAUTHORITY=$(ls /run/user/$(id -u)/.mutter-Xwaylandauth.* 2>/dev/null | head -1)
export WINEDEBUG=err+all,+process,+loaddll,+timestamp
G=$WINEPREFIX/drive_c/Sierra/BBPRO_98
D=/mnt/nvme/bbpro98/logs/$(date +%Y%m%d-%H%M%S); mkdir -p "$D"
ls -t /mnt/nvme/bbpro98/logs | tail -n +31 | while read o; do rm -rf "/mnt/nvme/bbpro98/logs/$o"; done
{ echo "start $(date +%T.%N)"; xdpyinfo | grep dimensions; xrandr 2>/dev/null | grep ' connected'; } > "$D/env.txt" 2>&1
( while :; do
    for w in $(xdotool search --name "Baseball|FPS" 2>/dev/null); do
      echo "$(date +%T.%N) $w $(xdotool getwindowgeometry $w 2>&1 | tr '\n' ' ') $(xprop -id $w _NET_WM_STATE 2>&1 | cut -c1-120) focus=$(xdotool getwindowfocus 2>/dev/null)"
    done; sleep 0.5; done ) > "$D/windows.log" 2>&1 &
MON=$!
cd "$G"; wine bblaunch.exe > "$D/wine.log" 2>&1; RC=$?
kill $MON 2>/dev/null
{ echo "exit rc=$RC at $(date +%T.%N)"; journalctl --since "-3min" --no-pager 2>/dev/null | grep -iE "wine|Baseball|segfault|mutter|xwayland" | tail -20; } > "$D/exit.txt" 2>&1
cp "$G/bbtrace.log" "$D/bbtrace.log" 2>/dev/null
echo "$D"
