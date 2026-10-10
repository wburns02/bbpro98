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
mods\playercard.dll  Click a player row on the League Statistics screen to open his career card.
mods\steal.dll     Experimental base-stealing switch (off unless you set [steal] mode).
bbfix.ini.sample   Copy to bbfix.ini and edit.
SHA256SUMS.txt     Checksums of every file above.

The in-game Mods menu (modmenu.dll) is not in this zip: it needs the news bridge (news/modbridge.py in the
source) running beside the game, which is only set up for the Linux hosting scripts.

Install
-------
1. Back up your Baseball Pro '98 folder (at least the Assn folder: your associations).
2. Copy bbfix.dll, bblaunch.exe and the mods folder into the folder that holds Baseball.exe.
3. Copy bbfix.ini.sample to bbfix.ini in the same folder. Remove from [mods] load= any mod you do not want.
4. Start the game with bblaunch.exe.

Uninstall: delete bbfix.dll, bblaunch.exe, bbfix.ini and the mods folder, and start Baseball.exe again.
aging.dll and rookies.dll change players when a season rolls over; those changes stay in your associations after
an uninstall. Keep the backup from step 1 if you may want them back.
