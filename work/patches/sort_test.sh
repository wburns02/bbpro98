#!/bin/bash
# usage: sort_test.sh SHOT HDRX  -- relaunch work copy with current build, Show>Players, click header at HDRX, shot crop
[[ $1 =~ ^[A-Za-z0-9_-]+$ && $2 =~ ^[0-9]+$ ]] || { echo "usage: sort_test.sh SHOT HDRX (SHOT [A-Za-z0-9_-], HDRX digits)"; exit 2; }
cd /home/will; bash bbpro98/work/patches/relaunch.sh /mnt/nvme/bbpro98/build/bbfix.dll "$1" >/dev/null 2>&1
export DISPLAY=:99; w(){ xdotool mousemove $1 $2; xdotool mousemove $(( $1+3 )) $(( $2+2 )); sleep 0.5; }
w 663 333; bash xc2.sh click 663 333; sleep 1.5; w 681 425; bash xc2.sh click 681 425; sleep 4
w $2 386; bash xc2.sh click $2 386; sleep 3; bash xc2.sh shot "$1s"
python3 -c "
import sys
from PIL import Image
Image.open(sys.argv[1]).crop((330,380,930,520)).resize((1200,280)).save(sys.argv[2])" "/home/will/${1}s.png" "/home/will/${1}c.png"
cat /mnt/nvme/bbpro98/work_install/bbtrace.1.log /mnt/nvme/bbpro98/work_install/bbtrace.log 2>/dev/null | grep -a "CRASH" | tail -2
