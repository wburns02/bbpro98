#!/bin/bash
# Restores the live game to the pristine 2006-end backup state (bbfix.dll, SHELL.VOL, BBShell.dll) and removes bbfix.ini.
LIVE=/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98; B=/mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06
# Same guard as install_live.sh: never replace DLLs under a running live game.
P=$(realpath ~/.bbpro98_prefix)
for pid in $(pgrep -f 'Sierra.BBPRO_98.(bblaunch|Baseball)'); do
    wp=$(tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | sed -n 's/^WINEPREFIX=//p')
    { [ -z "$wp" ] || [ "$(realpath -m "$wp")" = "$P" ]; } && { echo "REFUSED: live game running (pid $pid)"; exit 2; }
done
[ -d "$LIVE" ] || { echo "REFUSED: no live game at $LIVE"; exit 5; }
files=(bbfix.dll SHELL.VOL BBShell.dll)
for f in "${files[@]}"; do [ -f "$B/$f" ] || { echo "REFUSED: missing backup $B/$f"; exit 5; }; done
# Stage and verify all three before replacing any, so a failed copy never leaves a mixed install.
for f in "${files[@]}"; do
    cp "$B/$f" "$LIVE/$f.new" && cmp -s "$B/$f" "$LIVE/$f.new" || {
        for g in "${files[@]}"; do rm -f "$LIVE/$g.new"; done; echo "FAILED $f; live game unchanged"; exit 1; }
done
for f in "${files[@]}"; do mv -f "$LIVE/$f.new" "$LIVE/$f" || { echo "FAILED moving $f into place"; exit 1; }; done
rm -f "$LIVE/bbfix.ini"; echo reverted
