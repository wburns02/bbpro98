# Hosting the game in a browser

The game runs under Wine on a headless Linux host and is played in a browser through noVNC. Nothing here contains
game files: the host needs its own installed copy (a Wine prefix with `drive_c/Sierra/BBPRO_98`).

```
browser -> Cloudflare Access (one-time PIN) -> cloudflared tunnel -> websockify + noVNC 127.0.0.1:6152
        -> x11vnc 127.0.0.1:5952 -> Xvfb :52 (800x600) <- wine bblaunch.exe
```

Every listener binds to 127.0.0.1. The tunnel is the only way in, and Access sits in front of every path,
`/websockify` included.

## Files

| File | Goes to | Does |
|---|---|---|
| `systemd/bbpro98-xvfb.service` | `~/.config/systemd/user/` | virtual display `:52` |
| `systemd/bbpro98-vnc.service` | same | x11vnc on that display, localhost only, shared |
| `systemd/bbpro98-web.service` | same | websockify serving noVNC from the web dir |
| `systemd/bbpro98-game.service` | same | the game; restarts when it exits |
| `run-game.sh` | `/mnt/data/bbpro98/bin/` | starts `bblaunch.exe`, waits for the prefix's wineserver |
| `index.html` | web dir, next to symlinks to `/usr/share/novnc/*` | opens noVNC with autoconnect and scaling |
| `cloudflared.yml.example` | `~/.cloudflared/bbpro98.yml` | tunnel ingress to 127.0.0.1:6152 |

Paths in the units assume `/mnt/data/bbpro98/{prefix,web,bin}`; edit them for another host.

## Setup

1. Install `xorg-x11-server-Xvfb x11vnc novnc python3-websockify wine` (Fedora names).
2. Copy the Wine prefix with the installed game to `/mnt/data/bbpro98/prefix`.
3. Install the files above, then `loginctl enable-linger $USER` and
   `systemctl --user enable --now bbpro98-xvfb bbpro98-vnc bbpro98-web bbpro98-game`.
4. Check locally: `ssh -L 16152:127.0.0.1:6152 host`, open http://127.0.0.1:16152/.
5. Create the tunnel and a system unit running
   `cloudflared --no-autoupdate --config ~/.cloudflared/bbpro98.yml tunnel run`.
6. Create the Access application (self-hosted, the hostname, an allow policy for your own email), then the
   proxied CNAME `<hostname> -> <tunnel-id>.cfargotunnel.com`. Access first, DNS second: in the other order the
   game is public for the minutes in between, and noVNC here has no password.

## Gotchas

- A user systemd manager started from a desktop session inherits `WAYLAND_DISPLAY`, `XDG_SESSION_TYPE=wayland`
  and `XAUTHORITY`. x11vnc then exits at once ("Wayland sessions are as of now only supported via -rawfb"), and
  Wine may pick the wrong display. The units unset all three.
- Wine ignores SIGTERM while the game runs; the game unit stops it with `wineserver -k`.
- One shared desktop: everyone who connects sees and drives the same game.
