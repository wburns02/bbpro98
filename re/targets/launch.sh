#!/usr/bin/env bash
# Run a frozen copy of drive.sh so later edits to the driver cannot corrupt a running lane (bash reads scripts lazily).
set -eu
[[ "${1:-}" =~ ^[a-z0-9]+$ && "${2:-}" =~ ^[a-z]+$ ]] || { echo "usage: launch.sh <target> <lane> [max]" >&2; exit 2; }
F=/home/will/bbpro98/.audits/drive.$1.$2.running.sh
mkdir -p /home/will/bbpro98/.audits; cp /home/will/bbpro98/re/targets/drive.sh "$F"
exec bash "$F" "$@"
