#!/bin/sh
# x11vnc -afteraccept hook. After a long idle the game's window on :52 stays black until the pointer moves,
# and a viewer that connects and only looks (phones send no motion until a tap) sees a black screen.
# Nudge the pointer one pixel and back once the viewer is attached so the game repaints.
echo "$(date '+%F %T') nudge client=${RFB_CLIENT_IP:-?}" >> /mnt/data/bbpro98/vnc-nudge.log
( sleep 1; DISPLAY=:52 xdotool mousemove_relative 1 0 mousemove_relative -- -1 0 ) >/dev/null 2>&1 &
