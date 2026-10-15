#!/bin/bash
# usage: probe_screen.sh SHOT MENUX MENUY ITEMX ITEMY  -- restart WORK copy (keeps its current DLL/VOL), nav to Stats, open menu at MENUX,MENUY, click item, shot
[[ $1 =~ ^[A-Za-z0-9_-]+$ && $2 =~ ^[0-9]+$ && $3 =~ ^[0-9]+$ && $4 =~ ^[0-9]+$ && $5 =~ ^[0-9]+$ ]] || {
    echo "usage: probe_screen.sh SHOT MENUX MENUY ITEMX ITEMY (SHOT [A-Za-z0-9_-], the rest digits)"; exit 2; }
W=/mnt/nvme/bbpro98/work_install; export DISPLAY=:99
for p in $(pgrep -f 'C:.Sierra.BBPRO_98_work.(bblaunch|Baseball).exe|winedb[g]\.exe'); do kill $p; done; sleep 3
(setsid bash /home/will/bb_launch_work.sh >/dev/null 2>&1 &); sleep 20
bash /home/will/bbpro98/work/patches/nav_stats.sh "$1_0"
X=/home/will/xc2.sh
bash $X click "$2" "$3"; sleep 1; xdotool mousemove "$4" "$5"; xdotool mousemove "$(($4+2))" "$(($5+1))"; sleep .4
bash $X click "$4" "$5"; sleep 5; bash $X shot "$1"
