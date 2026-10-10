#!/usr/bin/env bash
# Builds the Windows binaries of a bbfix release from src-latest with zig cc (pip install ziglang) into OUT, then
# zips them with the sample ini and the release notes. Binaries never go in the repo: OUT must be outside it.
#   tools/build_release.sh OUT [PYTHON]       PYTHON defaults to python3 (it must have the ziglang package)
set -euo pipefail
out=${1:?usage: build_release.sh OUT [PYTHON]}
py=${2:-python3}
repo=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$out"
out=$(cd "$out" && pwd)
case "$out/" in "$repo"/*) echo "OUT must be outside the repo" >&2; exit 2 ;; esac
rm -rf "$out/stage"; mkdir -p "$out/stage/mods"
cc() { "$py" -m ziglang cc -target x86-windows-gnu -O2 -Wno-incompatible-pointer-types -I"$repo/src-latest" "$@"; }
cc -shared -o "$out/stage/bbfix.dll" "$repo/src-latest/bbfix.c" -lpsapi
cc -o "$out/stage/bblaunch.exe" "$repo/src-latest/bblaunch.c"
for m in aging rookies playercard steal; do
    [ -f "$repo/src-latest/mods/$m.c" ] || continue
    cc -shared -o "$out/stage/mods/$m.dll" "$repo/src-latest/mods/$m.c" -lgdi32 -luser32
done
rm -f "$out"/stage/*.pdb "$out"/stage/*.lib "$out"/stage/mods/*.pdb "$out"/stage/mods/*.lib
cp "$repo/release/bbfix.ini.sample" "$repo/release/README.txt" "$out/stage/"
ver=$(git -C "$repo" describe --tags --always --dirty)
(cd "$out/stage" && find . -type f | sort | xargs sha256sum > SHA256SUMS.txt)
rm -f "$out/bbfix-$ver.zip"
(cd "$out/stage" && "$py" -m zipfile -c "$out/bbfix-$ver.zip" .)
echo "$out/bbfix-$ver.zip"
