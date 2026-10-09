#!/bin/bash
# Runs the game until every Wine process of the prefix exits; systemd restarts it. `run-game.sh stop` stops it.
# The game runs in a bubblewrap sandbox that sees only /usr, /etc, the prefix, the X socket and a /tmp of its own.
# Wine reaches any host path through its "/" shell folder and \\?\unix\ names whatever drive letters exist, so
# without the sandbox the game's file dialogs would let anyone at the browser read and write the host's files.
set -e
PREFIX=/mnt/data/bbpro98/prefix
SBX=/mnt/data/bbpro98/sandbox            # the sandbox's /tmp: wineserver's socket, so `stop` can reach it
mkdir -p -m 700 "$SBX/tmp/home"
# No sound reaches the sandbox (the host's PulseAudio socket would let the game load server modules). Without an audio
# device the menu music fails at once and the shell retries the next track in a busy loop that starves its input, so
# the menu ignores clicks. ALSA's null device takes the sound and drops it.
printf 'pcm.!default { type null }\n' > "$SBX/tmp/home/.asoundrc"
# Wine maps Z: to / and adds a drive for every mounted disk; the game only needs C:.
find "$PREFIX/dosdevices" -mindepth 1 -maxdepth 1 ! -name 'c:' -delete

sbx() {
    exec bwrap --unshare-all --die-with-parent --new-session \
        --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/sbin /sbin \
        --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
        --ro-bind /etc /etc --dev /dev --proc /proc \
        --bind "$SBX/tmp" /tmp --bind /tmp/.X11-unix/X52 /tmp/.X11-unix/X52 \
        --bind "$PREFIX" "$PREFIX" \
        --clearenv --setenv HOME /tmp/home --setenv PATH /usr/bin --setenv WINEPREFIX "$PREFIX" \
        --setenv WINEDEBUG -all --setenv DISPLAY :52 --setenv DBUS_SYSTEM_BUS_ADDRESS unix:path=/nonexistent \
        --chdir "$PREFIX/drive_c/Sierra/BBPRO_98" "$@"
}

if [ "$1" = stop ]; then
    sbx wineserver -k
fi
sbx /bin/sh -c 'wine bblaunch.exe; wineserver -w'
