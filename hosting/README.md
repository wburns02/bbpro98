# Hosting the game in a browser

The game runs under Wine on a headless Linux host and is played in a browser through noVNC. Nothing here contains
game files: the host needs its own installed copy (a Wine prefix with `drive_c/Sierra/BBPRO_98`).

```
browser -> Cloudflare Access (one-time PIN) -> cloudflared tunnel -> websockify + noVNC 127.0.0.1:6152
        -> x11vnc 127.0.0.1:5952 -> Xvfb :52 (800x600) <- wine bblaunch.exe
browser -> Cloudflare Access -> cloudflared tunnel (/news) -> news/server.py 127.0.0.1:6153
        <- news-data <- news/watch.py <- the game's Assn/ and Stats/ (read only), GLM-Flash on Hive
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
| `systemd/bbpro98-news-watch.service` | same | writes game stories and columns from the box scores |
| `systemd/bbpro98-news-web.service` | same | serves them at `/news` on 127.0.0.1:6153, read only |
| `index.html` | web dir, next to symlinks to `/usr/share/novnc/*` | landing page: Play (noVNC, autoconnect) and League news |
| `cloudflared.yml.example` | `~/.cloudflared/bbpro98.yml` | tunnel ingress: `/news` to 6153, the rest to 6152 |
| `deploy.sh` | stays here | pushes changed game code, new seasons, the landing page and the news code |

Paths in the units assume `/mnt/data/bbpro98/{prefix,web,bin,news,news-data}`; edit them for another host.

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
7. League news: put the Hive key in `~/.config/hivemodels/api_key.env` on the host (a `HIVEMODELS_API_KEY=` line,
   mode 600; never in the repo or a unit), install the two news units, run `deploy.sh` once (it copies `news/*.py`
   and the codecs they import to `/mnt/data/bbpro98/news`), then
   `systemctl --user enable --now bbpro98-news-web bbpro98-news-watch`. The watcher spends at most
   `BBNEWS_CALLS` model calls and `BBNEWS_TOKENS` output tokens a day and writes template stories after that;
   `/news/status.json` shows the day's use.

## Updating the hosted copy

```
HOST=user@host hosting/deploy.sh --dry-run --mods /mnt/nvme/bbpro98/build/pc --seasons <build.py --install root>
```

Drop `--dry-run` to apply. Game code (top-level DLLs, EXEs, VOLs, `PB.INI`, `mods/*.dll`) is replaced when its
content differs, and only then is the game restarted. New seasons are added; a season already on the host is never
overwritten, because it holds the games played in the browser. The host's `bbfix.ini` is never touched; edit it
there to turn a mod on. The news units restart when their code changes; the game does not.

## Gotchas

- A user systemd manager started from a desktop session inherits `WAYLAND_DISPLAY`, `XDG_SESSION_TYPE=wayland`
  and `XAUTHORITY`. x11vnc then exits at once ("Wayland sessions are as of now only supported via -rawfb"), and
  Wine may pick the wrong display. The units unset all three.
- Wine ignores SIGTERM while the game runs; the game unit stops it with `wineserver -k`.
- One shared desktop: everyone who connects sees and drives the same game.
