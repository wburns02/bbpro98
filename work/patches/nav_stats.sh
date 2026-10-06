#!/bin/bash
# usage: nav_stats.sh SHOTNAME  (game already at main menu on :99)
export DISPLAY=:99; X=/home/will/xc2.sh
w(){ xdotool mousemove $1 $2; xdotool mousemove $(( $1+3 )) $(( $2+2 )); sleep 0.5; }
bash $X click 500 677; sleep 6
bash $X click 643 556; sleep 5
bash $X click 643 566; sleep 8
w 445 330; bash $X click 445 330; sleep 1.5
w 445 383; bash $X click 445 383; sleep 6
w 900 900; sleep 1
bash $X shot $1
