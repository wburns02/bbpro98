#!/usr/bin/env bash
# Run one lane from a frozen copy of drive.sh, so editing drive.sh never alters a running lane.
# usage: launch.sh <lane> [max_rounds]
set -eu
D=/home/will/bbpro98/re/hfiles; LANE=${1:?lane}; [[ "$LANE" =~ ^[a-z]+$ ]] || exit 2
mkdir -p "$D/audits"; F="$D/audits/drive.$LANE.running.sh"
cp "$D/drive.sh" "$F"; exec bash "$F" "$@"
