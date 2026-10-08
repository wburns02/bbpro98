#!/bin/bash
# Roadmap #9 referee arm: restore one snapshot into the WORK copy, run the game with bbfix.dll + mods/steal.dll in the
# given mode, sim N days, collect Assn/Stats/bbtrace into /mnt/nvme/bbpro98/re/hookab/ARM.
# usage: hookab.sh ARM MODE DAYS [BBFIX_DLL] [STEAL_DLL]      MODE = pass|zero|max|scale|off (off = no [mods])
set -u
ARM=$1 MODE=$2 DAYS=$3
SP=/tmp/claude-1000/-home-will/8d342f9f-a447-4453-8414-200a2f7813d7/scratchpad
FIX=${4:-$SP/bbfix_new.dll} MOD=${5:-$SP/steal.dll}
W=/mnt/nvme/bbpro98/work_install BASE=/mnt/nvme/bbpro98/re/asnseq/day10 OUT=/mnt/nvme/bbpro98/re/hookab/$ARM
LIVE=/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98
[ "$(realpath $W)" = "$(realpath $LIVE)" ] && { echo REFUSED: target is live install; exit 9; }
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/nonexistent DISPLAY=:99
kill_work(){ for p in $(pgrep -f 'C:.Sierra.BBPRO_98_work.(bblaunch|Baseball).exe|winedb[g]\.exe|winedb[g] --auto'); do kill $p; done; sleep 4; }
kill_work
[ -f $W/PB.INI ] && { echo "REFUSED: PB.INI present in work copy"; exit 7; }
[ -f $W/bbfix.dll.pre_mods ] || cp $W/bbfix.dll $W/bbfix.dll.pre_mods
rm -rf "$OUT"; mkdir -p "$OUT"
for d in Assn Stats; do find "$W/$d" -mindepth 1 -delete; cp -a "$BASE/$d/." "$W/$d/"; done
mkdir -p $W/mods; cp "$MOD" $W/mods/steal.dll; cp "$FIX" $W/bbfix.dll
python3 - "$W/bbfix.ini" "$MODE" <<'P'
import sys, configparser
p, mode = sys.argv[1], sys.argv[2]
c = configparser.ConfigParser(); c.optionxform = str; c.read(p)
for s in ('mods', 'steal'):
    if c.has_section(s): c.remove_section(s)
if mode != 'off':
    c['mods'] = {'load': 'mods\\steal.dll'}; c['steal'] = {'mode': mode, 'pct': '100'}
with open(p, 'w') as fh: c.write(fh)
P
cp $W/bbfix.ini "$OUT/bbfix.ini"
(setsid bash /home/will/bb_launch_work.sh >"$OUT/launch.log" 2>&1 &); sleep 25
python3 /home/will/bbpro98/re/simdays.py "$DAYS" "$OUT" > "$OUT/sim.log" 2>&1
kill_work
grep -a "MOD " $W/bbtrace.log > "$OUT/mod_lines.txt"
echo "ARM $ARM done: $(grep -c 'done=True' $OUT/sim.log)/$DAYS days; $(tail -1 $OUT/mod_lines.txt)"
