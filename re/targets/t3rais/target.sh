# Target config for re/targets/drive.sh (Claude-owned): bake-off tier 3, runner_ai exact replay (re/bakeoff/t3_setup.sh)
DECODER=runner_ai.py
REFEREE=(python3 -I -B "$RE/targets/t3ref.py" "$T")
AUDIT=text
HOLDOUT=1
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/t3rai /mnt/nvme/bbpro98/index/FastSim /home/will/bbpro98/src-latest/mods/simtrace.c)
LEAK_RE='targets_holdout|/mnt/nvme|/home/will|\.\./|__closure__|import gc|import inspect|from inspect|sys\._getframe|f_locals|open\('
declare -A FOCUS=(
  [code]="Read the decompile of FUN_6804faa1 and every callee down to the probed getters, compare with the dev records' top-level events, and model the branches."
)
AUDIT_RULES='This is a referee summary for a replay model of one decompiled function of a 1998 baseball simulator, followed by the model source. The model gets an oracle (o.x / o.pb / o.other) that returns recorded getter values in call order and raises on any call the real function would not make. Real modeling: the code re-executes the decompiled logic, deciding each branch from the input bytes (r["obj"], r["game"], r["mflags"], r["self"]) and the values the oracle returns, with named fields. FAIL-worthy: reading the record events or anything outside its arguments, lookup tables keyed by record index or input bytes, try/except loops that probe the oracle with candidate getters until one matches (searching instead of modeling), or tampering with the oracle internals.'
RE_SRC=/mnt/nvme/bbpro98/bakeoff/mask3/re
