#!/usr/bin/env bash
# Bake-off tier 2: build the masked re/ + work/ snapshot the gamebk blind re-run lanes see in place of the real ones
# (drive.sh RE_SRC / WORK_SRC), and the three single-lane targets gamebkh / gamebks / gamebkg (Haiku / Sonnet / GLM).
# Masked: every lane dir, every gamebk* target dir (TASK, WINNER, the solved lanes), work/gamebk.py,
# work/spec/GAMEBK_FORMAT.md, the RE_FINDINGS gamebk section, the ROADMAP gamebk rows, re/bakeoff itself.
set -eu
H=/home/will/bbpro98; M=/mnt/nvme/bbpro98/bakeoff/mask
mkdir -p "$M"
rsync -a --delete --exclude 'lanes/' --exclude 'targets/gamebk*/' --exclude 'bakeoff/' --exclude '__pycache__/' \
  "$H/re/" "$M/re/"
rsync -a --delete --exclude 'gamebk.py' --exclude 'spec/GAMEBK_FORMAT.md' --exclude '__pycache__/' "$H/work/" "$M/work/"
python3 -I -B - "$M" <<'PY'
import re, sys
M = sys.argv[1]
f = M + '/work/RE_FINDINGS.md'
t = open(f).read()
t2 = re.sub(r'## 2026-10-08: game hand-off files.*?(?=^## )', '', t, flags=re.S | re.M)
assert t2 != t
t2 = '\n'.join(l for l in t2.split('\n') if not re.search(r'\bGD[IO]\b|game\.bk[io]|gamebk', l))
open(f, 'w').write(t2)
f = M + '/re/ROADMAP.md'
t = open(f).read().split('\n')
t = [l for l in t if not re.search(r'game\.bk[io]|gamebk', l)]
open(f, 'w').write('\n'.join(t))
for n in ('HCARD', 'TAP', 'MISC8'):  # cross-format specs that cite GDI offsets
    f = f'{M}/work/spec/{n}_FORMAT.md'
    t = open(f).read().split('\n')
    open(f, 'w').write('\n'.join(l for l in t if not re.search(r'\bGD[IO]\b', l)))
PY
for m in h s g; do
  T=$H/re/targets/gamebk$m
  mkdir -p "$T/lanes/code" "$M/re/targets/gamebk$m/lanes/code"
  cp "$H/re/targets/gamebk/TASK.md" "$H/re/targets/gamebk/files.json" "$T/"
  # target.sh = gamebk's, plus the masked mount sources; FOCUS keeps only the code lane (the lane that solved it)
  sed -e '/^\[data\]=/d' -e 's/^  \[data\]=.*$//' "$H/re/targets/gamebk/target.sh" | grep -v '^  \[data\]' > "$T/target.sh"
  printf 'RE_SRC=%s/re\nWORK_SRC=%s/work\n' "$M" "$M" >> "$T/target.sh"
done
# TASK.md tells the lane to run gamebkref.py on re/targets/gamebk: give the masked tree that dir with files.json only
# (the data day list; no TASK, WINNER or lanes), as the original run's lanes could
mkdir -p "$M/re/targets/gamebk"
cp "$H/re/targets/gamebk/files.json" "$M/re/targets/gamebk/"
echo "mask at $M"
