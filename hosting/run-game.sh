#!/bin/bash
# Runs the game until every Wine process of the prefix exits; systemd restarts it.
cd /mnt/data/bbpro98/prefix/drive_c/Sierra/BBPRO_98
wine bblaunch.exe
wineserver -w
