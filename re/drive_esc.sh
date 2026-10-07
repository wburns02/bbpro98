#!/bin/bash
cd /mnt/nvme/bbpro98/re
for B in FastSim BBSIM; do
  while pgrep -f "[l]abel_glm.py $B" >/dev/null; do sleep 20; done
  python3 label_glm.py $B 4 >> glm_retry_$B.log 2>&1
  python3 label_escalate.py $B glm10
  python3 label_escalate.py $B deepseek10
  python3 label_escalate.py $B merge
done
echo ALLDONE
