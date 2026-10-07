#!/bin/bash
# wait for day01, then chain days 02..10 each into its own snapshot dir
while ! grep -q collected /mnt/nvme/bbpro98/re/asnseq/day01.log 2>/dev/null; do sleep 10; done
for i in $(seq -w 2 10); do
  SKIP_MENU=1 python3 /mnt/nvme/bbpro98/re/simdays.py 1 /mnt/nvme/bbpro98/re/asnseq/day$i \
    > /mnt/nvme/bbpro98/re/asnseq/day$i.log 2>&1
  grep -q collected /mnt/nvme/bbpro98/re/asnseq/day$i.log || { echo "day$i FAILED"; break; }
done
echo ASNSEQ-DONE
