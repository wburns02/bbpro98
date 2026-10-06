#!/bin/bash
# usage: relaunch.sh DLL SHOTNAME  -- installs DLL into the WORK copy (never live), relaunches from it, navigates to Stats, Show>Retired Players, shots
L=/mnt/nvme/bbpro98/work_install
LIVE=/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98
[ "$(realpath $L)" = "$(realpath $LIVE)" ] && { echo REFUSED: target is live install; exit 9; }
for p in $(pgrep -f 'C:.Sierra.BBPRO_98_work.(bblaunch|Baseball).exe|winedb[g]\.exe'); do kill $p; done; sleep 3
cp "$1" $L/BBShell.dll
(setsid bash /home/will/bb_launch_work.sh >/dev/null 2>&1 &); sleep 20
bash /home/will/bbpro98/work/patches/nav_stats.sh "$2a"
export DISPLAY=:99
bash /home/will/xc2.sh click 660 329; sleep 1.5
xdotool mousemove 705 440; xdotool mousemove 708 441; sleep 0.5; bash /home/will/xc2.sh click 708 440; sleep 5
bash /home/will/xc2.sh shot "$2b"
