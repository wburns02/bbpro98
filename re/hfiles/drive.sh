#!/usr/bin/env bash
# Driver: GLM-5.3-Flash builds the H-file decoder in rounds; the oracle scores each round;
# on PASS a Haiku session audits the decoder for truth leakage. No Claude Opus/Sonnet in the loop.
# usage: drive.sh [max_rounds]   (log: run.log, final state: STATUS)
set -u
D=/home/will/bbpro98/re/hfiles; cd "$D"
MAX=${1:-8}
ORACLE="python3 $D/check_hdecode.py $D/hdecode.py"
echo "RUNNING $(date -Is)" > STATUS
last=""
for r in $(seq 1 "$MAX"); do
  echo "=== round $r $(date -Is)" | tee -a run.log
  prompt="$(cat TASK.md)

This is round $r of $MAX. Latest referee output (tail):
${last:-<no decoder yet>}"
  timeout 3600 glm --yolo -p "$prompt" >> "glm_round$r.log" 2>&1
  echo "glm exit $?" >> run.log
  out=$($ORACLE 2>&1 | tail -n 14); echo "$out" >> run.log; last="$out"
  if echo "$out" | grep -q '^PASS'; then
    pit=$(echo "$out" | sed -n 's/^pit: cell accuracy \([0-9.]*\).*/\1/p')
    # mechanical leak guard, then Haiku audit
    if grep -nE 'asnseq|mlbpa97\.DAT|\.ASN|\.PYR|check_hdecode|/mnt/nvme|/home/will' hdecode.py >> run.log; then
      echo "LEAK GUARD: decoder references forbidden paths" | tee -a run.log
      last="$out
LEAK GUARD FAILED: hdecode.py references forbidden paths (see grep). Remove them; the decoder may read only argv[1]."
      continue
    fi
    timeout 1200 claude -p --model claude-haiku-4-5-20251001 --dangerously-skip-permissions \
      "Audit /home/will/bbpro98/re/hfiles/hdecode.py against /home/will/bbpro98/re/hfiles/TASK.md. Check: (1) it reads only the file in sys.argv[1] and the Python stdlib (no other file, env var, network, or embedded lookup table of per-player stat values copied from the truth); (2) every claim in HFILE_FORMAT.md that the code relies on matches the code. Run 'python3 /home/will/bbpro98/re/hfiles/hdecode.py /mnt/nvme/bbpro98/re/asnseq/day01/Stats/MLBPA97.H10' and confirm it prints sane JSON for a day the referee never scores. End your reply with exactly one line: VERDICT: CLEAN or VERDICT: LEAK <reason>." \
      > "haiku_audit$r.log" 2>&1
    v=$(grep -o 'VERDICT: [A-Z]*.*' "haiku_audit$r.log" | tail -n 1); echo "$v" >> run.log
    if [[ "$v" == "VERDICT: CLEAN"* ]]; then
      if awk -v p="${pit:-0}" 'BEGIN{exit !(p>=0.99)}'; then
        echo "DONE round $r $(date -Is) | $v" | tee STATUS; exit 0
      fi
      last="$out
Batting PASS and audit clean. Now bring pitching to >= 0.99."
    else
      last="$out
Haiku audit: $v. Fix it."
    fi
  fi
done
echo "STOPPED after $MAX rounds $(date -Is) | last: $(echo "$last" | grep -E '^(bat|pit|PASS|FAIL)' | tr '\n' ' ')" | tee STATUS
exit 1
