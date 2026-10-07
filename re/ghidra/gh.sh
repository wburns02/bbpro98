#!/bin/bash
# Live Ghidra access for the BBPro98 project (/mnt/nvme/bbpro98/ghidra_proj, Ghidra 12.1.4, pyghidra-mcp on 127.0.0.1:18765).
# usage: gh.sh start|stop|status|bins
#        gh.sh [-b BINARY] decomp ADDR|NAME | xrefs ADDR|NAME | disasm ADDR [COUNT] | search REGEX | rename ADDR NEWNAME | proto ADDR 'PROTOTYPE' | comment ADDR TEXT | save
#        gh.sh batch SPEC.py      (stop server, apply renames/labels/structs, restart; see gh_batch.py, backfill_1.py)
#        gh.sh regen [BINARY]     (stop server, re-export decompile to /mnt/nvme/bbpro98/index/<name>/_all.c, restart)
D=/mnt/nvme/bbpro98; export GHIDRA_INSTALL_DIR=/mnt/nvme/ghidra/ghidra_12.1.4_PUBLIC
PY=$D/ghidra_venv/bin/python; C="$PY $D/ghidra_scripts/mcpc.py"; BIN=BBShell.dll
[ "$1" = "-b" ] && { BIN=$2; shift 2; }
js(){ python3 -c "import json,sys;print(json.dumps(dict(zip(sys.argv[1::2],sys.argv[2::2]))))" "$@"; }
up(){ ss -ltn | grep -q 127.0.0.1:18765; }
case "$1" in
 start) up && { echo already up; exit 0; }
   (setsid nohup $D/ghidra_venv/bin/pyghidra-mcp -t streamable-http -p 18765 --project-path $D/ghidra_proj/BBShell.gpr > $D/ghidra_mcp.log 2>&1 & echo $! > $D/ghidra_mcp.pid)
   for i in $(seq 60); do up && { echo up; exit 0; }; sleep 2; done; echo FAILED; exit 1;;
 stop) up || { echo not running; exit 0; }; $C save >/dev/null 2>&1; kill -INT $(cat $D/ghidra_mcp.pid)
   for i in $(seq 30); do kill -0 $(cat $D/ghidra_mcp.pid) 2>/dev/null || break; sleep 2; done
   kill -0 $(cat $D/ghidra_mcp.pid) 2>/dev/null && kill -TERM $(cat $D/ghidra_mcp.pid); sleep 2; echo stopped;;
 status) up && echo up || echo down;;
 bins) $C list_project_binaries | grep '"name"';;
 decomp) $C decompile_function "$(js binary_name $BIN name_or_address $2)" | python3 -c "import sys,json;d=json.loads(sys.stdin.read());print(d['name']);print(d['code'])";;
 xrefs) $C list_xrefs "$(js binary_name $BIN name_or_address $2)";;
 disasm) $C disassemble "$(js binary_name $BIN address $2 count ${3:-20})" | python3 -c "import sys;print(sys.stdin.read())" ;;
 search) $C search_code "$(js binary_name $BIN query "$2")" | head -80;;
 rename) $C rename_function "$(js binary_name $BIN name_or_address $2 new_name $3)"; $C save >/dev/null;;
 proto) $C set_function_prototype "$(js binary_name $BIN function_name_or_address $2 prototype "$3")"; $C save >/dev/null;;
 comment) $C set_comment "$(js binary_name $BIN target $2 comment "$3" comment_type plate)"; $C save >/dev/null;;
 save) $C save;;
 batch) bash $0 stop; $PY $D/ghidra_scripts/gh_batch.py "$2" 2>&1 | grep -v "^WARNING\|^INFO\|^$"; bash $0 start;;
 regen) N=${2:-BBShell.dll}; bash $0 stop; $GHIDRA_INSTALL_DIR/support/analyzeHeadless $D/ghidra_proj BBShell -process $N -noanalysis -scriptPath $D/ghidra_scripts -postScript ExportDecomp.java $D/index/${N%.*} > $D/ghidra_regen.log 2>&1; tail -2 $D/ghidra_regen.log | cut -c1-160; bash $0 start;;
 *) sed -n 2,8p $0;;
esac
