#!/usr/bin/env bash
# Run headless Claude Code (subscription auth) inside the same jail drive.sh gives GLM lanes, for the 2026-10-08 model
# bake-off: claude_jail.sh <model> <workdir|-> [claude args...]. Prompt on stdin.
#  - bwrap + pasta netns with re/hfiles/sandbox/egress.nft (internet only: no loopback, LAN, tailnet, link-local).
#  - $HOME is a tmpfs: no user CLAUDE.md, rules, memory, hooks, settings or MCP; only ~/.claude/.credentials.json is
#    bound, read-only (a token refresh cannot be written back, so it never forks the host session's refresh token).
#  - workdir (if given) is the only writable host path; RO_PATHS (newline-separated "src[:dst]") are bound read-only.
set -u
M=${1:?model}; W=${2:?workdir or -}; shift 2
H=/home/will; RE=$H/bbpro98/re
b=(
  --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin --symlink usr/sbin /sbin
  --ro-bind /etc /etc --tmpfs /run --dir /run/systemd/resolve
  --ro-bind "$RE/hfiles/sandbox/resolv.conf" /run/systemd/resolve/stub-resolv.conf --proc /proc --dev /dev --tmpfs /tmp
  --tmpfs "$H" --ro-bind "$H/.local/bin/claude" "$H/.local/bin/claude"
  --ro-bind "$H/.local/share/claude" "$H/.local/share/claude"
  --dir "$H/.claude" --ro-bind "$H/.claude/.credentials.json" "$H/.claude/.credentials.json"
)
while IFS= read -r p; do
  [ -n "$p" ] || continue
  src=${p%%:*}; dst=${p#*:}; [ "$dst" = "$p" ] && dst=$src
  b+=(--ro-bind "$src" "$dst")
done <<< "${RO_PATHS:-}"
cd=/tmp
if [ "$W" != - ]; then b+=(--bind "$W" "$W"); cd=$W; fi
pasta --config-net --ipv4-only --no-map-gw --dns-forward 169.254.1.1 -t none -u none -T none -U none --quiet -- \
  bash -c 'nft -f "$1" && shift && exec "$@"' _ "$RE/hfiles/sandbox/egress.nft" \
bwrap "${b[@]}" --chdir "$cd" --unshare-user --uid 1000 --gid 1000 --unshare-pid --unshare-ipc --unshare-uts \
  --die-with-parent --new-session --clearenv --setenv HOME "$H" --setenv PATH "$H/.local/bin:/usr/bin" \
  --setenv LANG C.UTF-8 --setenv TERM dumb --setenv DISABLE_AUTOUPDATER 1 --setenv CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC 1 \
  "$H/.local/bin/claude" -p --model "$M" --strict-mcp-config --setting-sources "" --no-session-persistence "$@"
