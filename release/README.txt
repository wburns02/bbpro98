bbfix for Front Page Sports: Baseball Pro '98
=============================================

Source: https://github.com/wburns02/bbpro98 (MIT). No game files are included; you need your own copy of the
game, patched to its last official version.

Tested under Wine on Linux only. This build has not been run on real Windows. If you try it there, please open an
issue with what you saw.

What is in the zip
------------------
bbfix.dll          Stability fixes and the mod loader. Reads bbfix.ini next to Baseball.exe.
bblaunch.exe       Starts Baseball.exe with bbfix.dll loaded. Start the game with this from now on.
mods\aging.dll     Veterans decline and retire by age and ability, so a career league stays near a real age mix.
                   Reads mods\focus.txt (player development focus) when it exists.
mods\rookies.dll   Generated players get ratings drawn like real players', so new stars appear once the old
                   ones retire.
mods\playercard.dll  Click a player row on the League Statistics screen to open his career card. With modmenu.dll
                   and the bridge running, the card is a picture page: a generated portrait (no likenesses), ratings,
                   this season's lines and a Career tab with his real seasons plus the seasons your association has
                   played (the watcher saves each one at season end). Without them its own text card opens.
                   The mouse wheel scrolls the statistics list.
mods\modmenu.dll   The main menu's WWW SITE button opens a Mods window: the loaded mods, League News, Create a
                   Player and Build a Season. The three tools need the bridge below; without it they time out
                   with a message and the game carries on. League Management's Create New Association opens the
                   Build a Season window as New Association (pick the season year), with a button to the game's
                   own structures dialog; [modmenu] newassn=0 leaves that command to the game.
mods\champtext.dll The season-end texts no longer print "<No Name>" for the team nickname, which no association
                   fills ("the Chicago Cubs <No Name> capture the World Series").
mods\steal.dll     Experimental base-stealing switch (off unless you set [steal] mode).
bbfix.ini.sample   Copy to bbfix.ini and edit.
SHA256SUMS.txt     Checksums of every file above.

The Mods menu's bridge
----------------------
The game cannot reach the network, so modmenu.dll leaves requests as files in <game>\Mods\spool and a small
Python program from the source answers them. It runs on Linux beside a Wine install (Python 3, standard library):

  git clone https://github.com/wburns02/bbpro98 && cd bbpro98
  G=~/.wine/drive_c/Sierra/BBPRO_98                 # your game folder (holds Assn and Stats)
  python3 news/play.py --game "$G"                  # starts watch.py and modbridge.py together

That one command starts the watcher to keep the news current as you play, and the bridge to answer the game's
requests; when one of them exits or you press Ctrl+C, the other stops with it. It makes the data folders
(~/bbnews and ~/bbnews-backup by default; change them with --data and --backup) and refuses to run when the game
folder has no Assn. Keep it running across season ends too: the watcher saves each finished season for the card's
Career tab, and a season it never saw played is not saved. The real seasons before your association need the
bridge's --db (below). Build a Season also needs --db (a Lahman database, work/lahman/load_csv.py) and
--templates (minted with work/lahman); without them it says it is not set up. Pass those to play.py with --db and
--templates and it forwards them to the bridge, --db to the watcher too; --no-llm makes the watcher skip the
recap writer. Create a Player copies each file it changes to --backup first.

Install
-------
1. Back up your Baseball Pro '98 folder (at least the Assn folder: your associations).
2. Copy bbfix.dll, bblaunch.exe and the mods folder into the folder that holds Baseball.exe.
3. Copy bbfix.ini.sample to bbfix.ini in the same folder. Remove from [mods] load= any mod you do not want.
4. Start the game with bblaunch.exe.

Uninstall: delete bbfix.dll, bblaunch.exe, bbfix.ini and the mods folder, and start Baseball.exe again.
aging.dll and rookies.dll change players when a season rolls over; those changes stay in your associations after
an uninstall. Keep the backup from step 1 if you may want them back.
