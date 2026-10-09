#!/bin/bash
# Runs the game until every Wine process of the prefix exits; systemd restarts it.
# Wine maps Z: to / and adds a drive for every mounted disk; the game only needs C:. Without this, its file dialogs
# would let anyone at the browser read and write the host's files.
find /mnt/data/bbpro98/prefix/dosdevices -mindepth 1 -maxdepth 1 ! -name 'c:' -delete
cd /mnt/data/bbpro98/prefix/drive_c/Sierra/BBPRO_98
wine bblaunch.exe
wineserver -w
