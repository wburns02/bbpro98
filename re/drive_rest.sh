#!/bin/bash
cd /mnt/nvme/bbpro98/re
for B in BBCfg FPS_Pal FPS_DCL FPS_Ctrl IC_Cfg ODASL FPS_CT LineUp Upstats EZShell BBShell; do
  python3 label_det.py $B >> det_$B.log 2>&1
  timeout 2700 python3 label_glm.py $B 4 >> glm_rest.log 2>&1
  python3 label_escalate.py $B glm10
  python3 label_escalate.py $B deepseek10
  python3 label_escalate.py $B merge
done
echo ALLDONE
