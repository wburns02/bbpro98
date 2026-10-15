#!/bin/bash
# usage: sort_test.sh SHOT HDRX  -- relaunch work copy with current build, Show>Players, click header at HDRX, shot crop
cd /home/will; bash bbpro98/work/patches/relaunch.sh /mnt/nvme/bbpro98/build/bbfix.dll "$1" >/dev/null 2>&1
export DISPLAY=:99; w(){ xdotool mousemove $1 $2; xdotool mousemove $(( $1+3 )) $(( $2+2 )); sleep 0.5; }
w 663 333; bash xc2.sh click 663 333; sleep 1.5; w 681 425; bash xc2.sh click 681 425; sleep 4
w $2 386; bash xc2.sh click $2 386; sleep 3; bash xc2.sh shot "$1s"
python3 -c "
from PIL import Image
Image.open('/home/will/$1s.png').crop((330,380,930,520)).resize((1200,280)).save('/home/will/$1c.png')"
grep -a "CRASH" /mnt/nvme/bbpro98/work_install/bbtrace.log | tail -2
