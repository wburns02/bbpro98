#!/bin/bash
# Installs the wide-stats mod (and any MODS) into the LIVE game: bbfix.dll (hooks BBShell in memory), bbfix.ini, wide6 SHELL.VOL (wide5 rebuilt with the VOL size header fixed). BBShell.dll stays pristine on disk.
LIVE=/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98; B=/mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06; V=/mnt/nvme/bbpro98/vol/SHELL_wide6.VOL; D=/mnt/nvme/bbpro98/build/bbfix.dll
# Refuse only a game in the live prefix: scratch prefixes (hosting, modmenu tests) run the same exe path.
P=$(realpath ~/.bbpro98_prefix)
for pid in $(pgrep -f 'Sierra.BBPRO_98.(bblaunch|Baseball)'); do
    wp=$(tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | sed -n 's/^WINEPREFIX=//p')
    { [ -z "$wp" ] || [ "$(realpath -m "$wp")" = "$P" ]; } && { echo "REFUSED: live game running (pid $pid)"; exit 2; }
done
[ -d "$LIVE" ] || { echo "REFUSED: no live game at $LIVE"; exit 5; }
for f in "$D" "$V" "$B/BBShell.dll"; do [ -f "$f" ] || { echo "REFUSED: missing $f"; exit 5; }; done
cmp -s "$LIVE/BBShell.dll" "$B/BBShell.dll" || { echo "REFUSED: live BBShell.dll not pristine"; exit 3; }
# MODS="/path/a.dll /path/b.dll" also installs those mods into $LIVE/mods and lists them under [mods] load.
load=""; mods=()
for m in $MODS; do [ -f "$m" ] || { echo "REFUSED: no mod $m"; exit 4; }; mods+=("$m"); load="$load${load:+,}mods\\$(basename "$m")"; done
# Stage every file as .new next to its target, then move them all into place: a failed copy (full disk, missing
# source) leaves the live game exactly as it was instead of a new DLL with an old VOL.
staged=()
stage() { staged+=("$2.new"); cp "$1" "$2.new" && cmp -s "$1" "$2.new"; }
abort() { rm -f "${staged[@]}"; echo "FAILED: $1; live game unchanged"; exit 1; }
stage "$D" "$LIVE/bbfix.dll" || abort bbfix.dll
stage "$V" "$LIVE/SHELL.VOL" || abort SHELL.VOL
staged+=("$LIVE/bbfix.ini.new")
{ printf '[widen]\nenable=1\nbat=49,50,57,52\npit=262,251,276,277\n\n[trace]\ntext=0\ncell=0\ndraw=0\nmatch=\n'
  [ -z "$load" ] || printf '\n[mods]\nload=%s\n' "$load"; } > "$LIVE/bbfix.ini.new" || abort bbfix.ini
if [ ${#mods[@]} -gt 0 ]; then
    mkdir -p "$LIVE/mods" || abort mods
    for m in "${mods[@]}"; do stage "$m" "$LIVE/mods/$(basename "$m")" || abort "$(basename "$m")"; done
fi
for s in "${staged[@]}"; do mv -f "$s" "${s%.new}" || { echo "FAILED: moving $s into place"; exit 1; }; done
# modmenu.dll takes over the WWW SITE button; relabel it MODS (originals kept as WEB*.BMP.orig).
case " $MODS " in *modmenu.dll*) python3 "$(dirname "$0")/mods_button.py" "$LIVE/Sshell" || exit 1;; esac
echo installed
