#!/bin/bash
# Installs the wide-stats mod into the LIVE game: bbfix.dll (hooks BBShell in memory), bbfix.ini, wide6 SHELL.VOL (wide5 rebuilt with the VOL size header fixed). BBShell.dll stays pristine on disk.
LIVE=/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98; B=/mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06; V=/mnt/nvme/bbpro98/vol/SHELL_wide6.VOL; D=/mnt/nvme/bbpro98/build/bbfix.dll
[ -n "$(pgrep -f 'Sierra.BBPRO_98.(bblaunch|Baseball)')" ] && { echo "REFUSED: live game running"; exit 2; }
cmp -s $LIVE/BBShell.dll $B/BBShell.dll || { echo "REFUSED: live BBShell.dll not pristine"; exit 3; }
cp $D $LIVE/bbfix.dll && cp $V $LIVE/SHELL.VOL && printf '[widen]\nenable=1\nbat=49,50,57,52\npit=262,251,276,277\n\n[trace]\ntext=0\ncell=0\ndraw=0\nmatch=\n' > $LIVE/bbfix.ini && echo installed
