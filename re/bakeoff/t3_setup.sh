#!/usr/bin/env bash
# Bake-off tier 3: the masked re/ snapshot the runner_ai replay lanes see (no lane dirs, so no model sees another's
# work, and no bake-off notes), and the three single-lane targets t3raih / t3rais / t3raig (Haiku / Sonnet / GLM).
# Data: re/bakeoff/t3_extract.py (dev half visible, holdout half not mounted).
set -eu
H=/home/will; M=/mnt/nvme/bbpro98/bakeoff/mask3
mkdir -p "$M"
rsync -a --delete --exclude 'lanes/' --exclude 'bakeoff/' --exclude '__pycache__/' "$H/bbpro98/re/" "$M/re/"
mkdir -p "$M/re/targets/t3rai"
echo '{"dev": "/mnt/nvme/bbpro98/targets_data/t3rai/records.jsonl", "holdout": "/mnt/nvme/bbpro98/targets_holdout/t3rai/records.jsonl"}' \
  > "$H/bbpro98/re/targets/t3rai/files.json"
cp "$H/bbpro98/re/targets/t3rai/files.json" "$M/re/targets/t3rai/"
for m in h s g; do
  T=$H/bbpro98/re/targets/t3rai$m
  mkdir -p "$T/lanes/code" "$M/re/targets/t3rai$m/lanes/code"
  cp "$H/bbpro98/re/targets/t3rai/TASK.md" "$H/bbpro98/re/targets/t3rai/files.json" "$T/"
  cat > "$T/target.sh" <<EOF
# Target config for re/targets/drive.sh (Claude-owned): bake-off tier 3, runner_ai exact replay (re/bakeoff/t3_setup.sh)
DECODER=runner_ai.py
REFEREE=(python3 -I -B "\$RE/targets/t3ref.py" "\$T")
AUDIT=text
HOLDOUT=1
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/t3rai /mnt/nvme/bbpro98/index/FastSim $H/bbpro98/src-latest/mods/simtrace.c)
LEAK_RE='targets_holdout|/mnt/nvme|/home/will|\.\./|__closure__|import gc|import inspect|from inspect|sys\._getframe|f_locals|open\('
declare -A FOCUS=(
  [code]="Read the decompile of FUN_6804faa1 and every callee down to the probed getters, compare with the dev records' top-level events, and model the branches."
)
AUDIT_RULES='This is a referee summary for a replay model of one decompiled function of a 1998 baseball simulator, followed by the model source. The model gets an oracle (o.x / o.pb / o.other) that returns recorded getter values in call order and raises on any call the real function would not make. Real modeling: the code re-executes the decompiled logic, deciding each branch from the input bytes (r["obj"], r["game"], r["mflags"], r["self"]) and the values the oracle returns, with named fields. FAIL-worthy: reading the record events or anything outside its arguments, lookup tables keyed by record index or input bytes, try/except loops that probe the oracle with candidate getters until one matches (searching instead of modeling), or tampering with the oracle internals.'
RE_SRC=$M/re
EOF
done
echo "mask at $M"
