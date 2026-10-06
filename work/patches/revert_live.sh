#!/bin/bash
# Restores the live game to the pristine 2006-end backup state (bbfix.dll, SHELL.VOL, BBShell.dll) and removes bbfix.ini.
LIVE=/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98; B=/mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06
for f in bbfix.dll SHELL.VOL BBShell.dll; do cp $B/$f $LIVE/$f; cmp $B/$f $LIVE/$f || { echo FAILED $f; exit 1; }; done; rm -f $LIVE/bbfix.ini; echo reverted
