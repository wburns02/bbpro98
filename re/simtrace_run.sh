#!/bin/bash
# Roadmap #10 trace arm: hookab.sh with the simtrace mod, then the trace and the probe table it was built with
# (re/simtrace_probes.py, read by simtrace_dump.records to map probe ids) are moved into the arm's output directory.
# usage: simtrace_run.sh ARM DAYS SIMTRACE_DLL ["k=v ..." simtrace ini keys]
set -u
ARM=$1 DAYS=$2 DLL=$3 KV=${4:-}
SP=/tmp/claude-1000/-home-will/8d342f9f-a447-4453-8414-200a2f7813d7/scratchpad
W=/mnt/nvme/bbpro98/work_install OUT=/mnt/nvme/bbpro98/re/hookab/$ARM HERE=$(dirname "$(realpath "$0")")
rm -f $W/simtrace.bin
MODNAME=simtrace MODKV="$KV" bash "$HERE/hookab.sh" "$ARM" on "$DAYS" "$SP/bbfix_new.dll" "$DLL"
[ -f $W/simtrace.bin ] && mv $W/simtrace.bin "$OUT/" && cp "$HERE/simtrace_probes.py" "$OUT/"
ls -la "$OUT/simtrace.bin"
