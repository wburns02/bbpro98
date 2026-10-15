#!/bin/bash
# Push game-side changes from this machine to the hosted copy.
#
#   HOST=user@host hosting/deploy.sh [--dry-run] [--mods DIR] [--seasons DIR]...
#
# Replaced on the host when their content differs: the game's top-level *.dll, *.exe and *.VOL, PB.INI, and
# every mods/*.dll (from the install and from --mods). bbfix.ini is the host's own (it carries the [mods] lines)
# and is never copied. Seasons (--seasons points at a build.py --install root holding Assn/ and Stats/) are only
# added: an association that already exists on the host keeps its files, because those carry the progress played
# in the browser. The game unit restarts only when a replaced file changed, since a restart ends the session in
# the browser. The landing page (index.html) and the news sidecar's code are copied too; the news units and the Create a
# Player form (news/createweb.py) restart on a change. So are the PIN gate and its nginx config (the gate restarts and nginx reloads on a change).
set -euo pipefail

SRC=${SRC:-$HOME/.bbpro98_prefix/drive_c/Sierra/BBPRO_98}
DST=${DST:-/mnt/data/bbpro98/prefix/drive_c/Sierra/BBPRO_98}
HOST=${HOST:?set HOST=user@host}
DRY=()
MODS=()
SEASONS=()
while [ $# -gt 0 ]; do
  case $1 in
    --dry-run) DRY=(--dry-run) ;;
    --mods) MODS+=("$2"); shift ;;
    --seasons) SEASONS+=("$2"); shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
[ -d "$SRC" ] || { echo "no install at $SRC" >&2; exit 1; }

# sent <rsync args...>: run rsync and print only the lines for files actually sent ("<f"); timestamp-only and
# directory lines are not changes. A failed rsync (host down, disk full, a path missing) stops the deploy: callers
# use it as x=$(sent ...), which set -e turns into an exit, instead of reading "nothing changed".
sent() {
  local out rc=0
  out=$(rsync --itemize-changes "${DRY[@]}" -e ssh "$@") || rc=$?
  if [ $rc -ne 0 ]; then
    echo "deploy: rsync failed (exit $rc) for ${*: -2:1} -> ${*: -1}" >&2
    return $rc
  fi
  printf '%s\n' "$out" | grep '^<f' || true
}

changed=0
push() {  # push <rsync args...>: run rsync, print what it changed, count code changes
  local out
  out=$(sent -rl --checksum "$@")
  if [ -n "$out" ]; then
    echo "$out"
    changed=1
  fi
}

push --include='*.dll' --include='*.DLL' --include='*.exe' --include='*.EXE' --include='*.VOL' \
     --include='PB.INI' --exclude='*' "$SRC/" "$HOST:$DST/"
[ -d "$SRC/mods" ] && push --include='*.dll' --exclude='*' "$SRC/mods/" "$HOST:$DST/mods/"
for m in "${MODS[@]}"; do
  push --include='*.dll' --exclude='*' "$m/" "$HOST:$DST/mods/"
done

for s in "${SEASONS[@]}"; do
  for sub in Assn Stats; do
    [ -d "$s/$sub" ] || { echo "no $sub/ in $s" >&2; exit 1; }
  done
  # Never the template stand-ins build.py symlinks into its install root.
  rsync -rt --omit-dir-times --ignore-existing --itemize-changes "${DRY[@]}" -e ssh \
    --exclude='MLBPA96E.PYR' --exclude='_DEFAULT.*' \
    --include='*.ASN' --include='*.PYR' --include='*.PYF' --exclude='*' "$s/Assn/" "$HOST:$DST/Assn/"
  rsync -rt --omit-dir-times --ignore-existing --itemize-changes "${DRY[@]}" -e ssh \
    --include='*.DAT' --exclude='*' "$s/Stats/" "$HOST:$DST/Stats/"
done

# The landing page noVNC's web root serves at /: Play and League news. Static; nothing restarts for it.
WEB=${WEB:-/mnt/data/bbpro98/web}
web=$(sent -l --checksum "$(cd "$(dirname "$0")" && pwd)/index.html" "$HOST:$WEB/index.html")
[ -n "$web" ] && echo "$web"

# The news sidecar: its own code plus the read-only codecs it imports. Its units restart on a change; the game does not.
NEWS=${NEWS:-/mnt/data/bbpro98/news}
REPO=$(cd "$(dirname "$0")/.." && pwd)
[ ${#DRY[@]} -eq 0 ] && ssh "$HOST" "mkdir -p '$NEWS/news' '$NEWS/work' /mnt/data/bbpro98/news-data"
# salary_table.json is the contracts pricing table watch.py loads; without it the payroll pages stay empty.
news=$(sent -rl --checksum --include='*.py' --include='salary_table.json' --exclude='*' \
         "$REPO/news/" "$HOST:$NEWS/news/")
more=$(sent -rl --checksum "$REPO/work/ctree.py" "$REPO/work/hdecode.py" "$REPO/work/league.py" "$REPO/work/stats.py" \
         "$HOST:$NEWS/work/")
news+=${news:+${more:+$'\n'}}$more
# The Lahman season builder, run by the in-game Mods menu's bridge (news/modbridge.py) for Build a Season.
[ ${#DRY[@]} -eq 0 ] && ssh "$HOST" "mkdir -p '$NEWS/work/lahman'"
more=$(sent -rl --checksum --include='*.py' --exclude='*' "$REPO/work/lahman/" "$HOST:$NEWS/work/lahman/")
news+=${news:+${more:+$'\n'}}$more
# Full team names for Lahman-built associations (work/lahman/teamnames.py writes it; it is not in the repo).
NAMES=${NAMES:-/mnt/nvme/bbpro98/teamnames.json}
if [ -f "$NAMES" ]; then
  more=$(sent -l --checksum "$NAMES" "$HOST:/mnt/data/bbpro98/news-data/teamnames.json")
  news+=${news:+${more:+$'\n'}}$more
fi
if [ -n "$news" ]; then
  echo "$news"
  if [ ${#DRY[@]} -eq 0 ]; then
    ssh "$HOST" 'systemctl --user restart bbpro98-news-web bbpro98-news-watch bbpro98-create bbpro98-bridge && systemctl --user is-active bbpro98-news-web bbpro98-news-watch bbpro98-create bbpro98-bridge'
  else
    echo "dry run: the news, create and bridge units would restart"
  fi
fi

# The PIN gate (gate.py) and the nginx in front of everything (nginx.conf). The PIN itself lives on the host in
# ~/.config/bbpro98/gate_pin and is never copied. A gate change restarts the gate; a config change reloads nginx.
GATE=${GATE:-/mnt/data/bbpro98/gate}
[ ${#DRY[@]} -eq 0 ] && ssh "$HOST" "mkdir -p '$GATE/tmp'"
HOSTING=$(cd "$(dirname "$0")" && pwd)
g=$(sent -l --checksum "$HOSTING/gate.py" "$HOST:$GATE/gate.py")
c=$(sent -l --checksum "$HOSTING/nginx.conf" "$HOST:$GATE/nginx.conf")
[ -n "$g$c" ] && echo "$g${g:+${c:+$'\n'}}$c"
if [ ${#DRY[@]} -eq 0 ]; then
  [ -n "$g" ] && ssh "$HOST" 'systemctl --user restart bbpro98-gate && systemctl --user is-active bbpro98-gate'
  [ -n "$c" ] && ssh "$HOST" 'systemctl --user reload-or-restart bbpro98-proxy && systemctl --user is-active bbpro98-proxy'
fi

if [ "$changed" = 1 ] && [ ${#DRY[@]} -eq 0 ]; then
  ssh "$HOST" 'systemctl --user restart bbpro98-game && systemctl --user is-active bbpro98-game'
elif [ "$changed" = 1 ]; then
  echo "dry run: the game would restart"
else
  echo "game files unchanged: no restart"
fi
