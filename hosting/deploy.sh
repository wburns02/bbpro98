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
# the browser.
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

changed=0
push() {  # push <rsync args...>: run rsync, print what it changed, count code changes
  local out
  # Only lines for files actually sent ("<f"); timestamp-only and directory lines are not changes.
  out=$(rsync -rl --checksum --itemize-changes "${DRY[@]}" -e ssh "$@" | grep '^<f' || true)
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

# The news sidecar: its own code plus the read-only codecs it imports. Its units restart on a change; the game does not.
NEWS=${NEWS:-/mnt/data/bbpro98/news}
REPO=$(cd "$(dirname "$0")/.." && pwd)
[ ${#DRY[@]} -eq 0 ] && ssh "$HOST" "mkdir -p '$NEWS/news' '$NEWS/work' /mnt/data/bbpro98/news-data"
news=$(rsync -rl --checksum --itemize-changes "${DRY[@]}" -e ssh --include='*.py' --exclude='*' \
         "$REPO/news/" "$HOST:$NEWS/news/" | grep '^<f' || true)
news+=$(rsync -rl --checksum --itemize-changes "${DRY[@]}" -e ssh \
          "$REPO/work/ctree.py" "$REPO/work/hdecode.py" "$REPO/work/league.py" "$REPO/work/stats.py" \
          "$HOST:$NEWS/work/" | grep '^<f' || true)
if [ -n "$news" ]; then
  echo "$news"
  if [ ${#DRY[@]} -eq 0 ]; then
    ssh "$HOST" 'systemctl --user restart bbpro98-news-web bbpro98-news-watch && systemctl --user is-active bbpro98-news-web bbpro98-news-watch'
  else
    echo "dry run: the news units would restart"
  fi
fi

if [ "$changed" = 1 ] && [ ${#DRY[@]} -eq 0 ]; then
  ssh "$HOST" 'systemctl --user restart bbpro98-game && systemctl --user is-active bbpro98-game'
elif [ "$changed" = 1 ]; then
  echo "dry run: the game would restart"
else
  echo "game files unchanged: no restart"
fi
