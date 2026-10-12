# Lane bbnewassn: Create New Association asks for the season year

Create New Association (League Management) opens a New Association window: a season year, a Negro Leagues checkbox,
Build (the Build a Season bridge op) and a button to the game's own structures dialog. Mods menu > Build a Season is
unchanged.

## What changed

- `src-latest/mods/modmenu.c`
  - detour on `BBShell.dll` VA `0x68004ef0` (the menu item's screen-8 entry; see Gate correction below).
  - the Build a Season window is now `open_build(owner, newassn)`: same class, same `build_proc`; the New Association
    mode adds the game's-structures button, a bridge check on open (`ping`), and a 290-pixel client height.
  - the message loop moved out of `run_menu` into `run_loop`, shared by both windows.
  - `win_destroyed` posts a `WM_NULL` when the last window closes. Without it `run_loop` stays in `GetMessage` until
    the next message arrives, so the stock path can wait for a mouse move. This also covers the Mods menu.
  - `bbfix.ini [modmenu] newassn` (default 1; 0 leaves the game's command alone). A refused detour logs and keeps the
    Mods menu.
- `news/modbridge.py` `_ping`: header `build=1` when Build a Season can run (db and templates set), else `build=0`
  with `NO_BUILD_TEXT` as the body. Nothing else in the bridge changed.
- `news/tests/test_modbridge.py`: `test_ping` expects `build=1`; `test_ping_says_build_is_off_without_a_database_or_templates`.
- `src-latest/test/mmtest.py`: the real-bridge check's stub context gets `db=None, templates=None` (the ping now reads them).
- `release/bbfix.ini.sample` and `release/README.txt`: `newassn=1` and one paragraph.

## Evidence for the hook (BBShell.dll, image base 0x68000000)

Source: `/mnt/nvme/bbpro98/work_install/BBShell.dll`, decompile dump `BBShell/_all.c`.

- `menu_event_handler` = `FUN_680068d0`, `void __thiscall (void *this, short param_1)`: `this` in ECX, the command
  on the stack (`[esp+4]` at entry), `ret 4`. Entry bytes (file offset `0x5cd0`):
  `56 8b f1 | 66 8b 4c 24 08` = `push esi; mov esi,ecx; mov cx,[esp+8]`. Eight bytes, whole instructions, position
  independent; the next instruction `0f bf c1` starts at `+8`. These are the detour's `expect` bytes, `n = 8`.
- Dispatch: `movsx eax,cx; sub eax,3; cmp eax,0x25; ja`, then byte table at `0x68006a08` indexed by `cmd-3`, then
  `jmp [0x680069d0 + idx*4]`. Command `0xe` gives index `0xb`, byte `0x01`, slot 1 = `0x6800691e`.
- `0x6800691e`: `c6 46 04 01` (`this+4 = 1`), `8b ce`, `call 0x68007050` (`FUN_68007050`, `init_new_association`,
  `__fastcall(this)`; it copies `s_New_Association_6808a248`), `8b ce`, `call 0x68005720` (`FUN_68005720`,
  `__fastcall(this)`), `5e` (pop esi), `c2 04 00` (ret 4). This is the stock path; the detour skips it when our window
  takes the command, so `this+4` stays 0. The byte is in the stock dialog's state, not the menu's, and nothing on our
  path reads it (no stock dialog opens); in game, check that League Management still works after the window closes.
- Callers in the dumps: `FUN_68007050` and `FUN_68005720` are each called only from `FUN_680068d0`. So every route to
  the stock dialog passes through this switch.
- Menu item: SHELL.VOL MENU.DAT item with `command_id = 14`, caption `"Create New Association...\x01Ctrl+W"`
  (`re/targets/volmisc/lanes/code/FORMAT.md`: "menu_event_handler case 0xe = 14 = New Association").
- `BBShell` is loaded and freed per screen; bbfix applies the hook each time it maps (see bbmod.h). Expect
  `applied 1 hooks to BBShell.dll` in bbtrace.log (the "MOD" lines).

## Bridge reply

`op=ping` now returns `status=ok, version=1, build=1` (body empty) or `build=0` with `NO_BUILD_TEXT` as the body. The
New Association window reads it on open: `build=1` enables Build; anything else shows the body, disables Build and says
"Build is off". A bridge that does not answer gives "No answer from the mods bridge. Is it running?" after 20 s; no
spool folder gives "The mods bridge is not set up (no Mods\spool folder)." at once.

Year range: the window checks the year like Build a Season does (MLB 1871..2099, Negro Leagues 1920..1948, both
constants in modmenu.c), and the bridge refuses a year outside its database range with its own message ("Pick a year
from 1871 to 2025 for MLB."), which the window shows. The range is not sent in the ping; Build a Season never got it
from the bridge either.

## Checks run here

- `python3 -m pytest news/tests -q`: 868 passed, 1 skipped (`test_aigm.py:444`, needs the 1950 association, not on this
  machine). `capped` is not on this sandbox's PATH, so the run was plain pytest.
- `modmenu.dll`, the release command: zero warnings. `-Wall -Wextra` adds only the old `mm_set_spool` unused warning.
- `src-latest/test/mmtest.py` (Wine): 7 of 8 pass. Check 8 (`window shown`) fails on untouched HEAD too; the sandbox
  has no display. With Xvfb on `:97` (GLX off) `mmtest.exe visible` prints `VISIBLE 1`.
- Scratch probe (not in the repo) runs the real `run_newassn()` under Xvfb with a fake bridge:
  - bridge build=1: Build enabled, "Bridge: ready"; year 1998 sends `op=build`, `year=1998`, `league=mlb`; the
    reply shows "Done."; stock=0 after Close.
  - bridge build=1, "Game's own structures...": window gone, `run_newassn()` returns 1 (the stock handler runs).
  - bridge build=0: Build off; the bridge's text in the box; stock returns 1.
  - no bridge: "No answer ... Is it running?" after 20 s; Build off; Close returns 0.
  - no spool folder: "The mods bridge is not set up (no Mods\spool folder)." at once; Build off.
  - stock clicked while the ping is out: window gone, returns 1 (the button is not disabled while busy).
  - the window also returned 1 when no window could be created (no display).
- Not checked here: the detour in the real game (needs BBShell and the game), and the stock dialog after our window.

## In-game steps (BBLANE=N, bridge running with --db and --templates)

Setup: `[mods] load` includes `mods\modmenu.dll`; `[modmenu] newassn=1` or no key. Start the bridge (news/modbridge.py).

1. Start the game. In bbtrace.log expect `MOD modmenu: applied 1 hooks to BBShell.dll` once the shell maps.
2. League Management > Create New Association (or Ctrl+W). Expect a window titled "New Association", status
   "Bridge: ready", Build enabled, no stock requester behind it.
3. Season `1998`, Negro Leagues unchecked, Build. Status "Building the season... N s", then "Done."; the box shows
   "Built <label> (<stem>). Pick it from the association list." with the label and stem the bridge made. Close.
4. Reopen the association list: the 1998 association is in it (sorted by label; check the row).
5. Create New Association > Game's own structures... The window closes and the game's own New Association dialog
   opens at once. Cancel it. Then Create New Association again: our window opens again.
6. Season `1900`, Build. The box shows "Pick a year from 1871 to 2025 for MLB."; status "The build failed."
7. Stop the bridge. Create New Association: after about 20 s, "No answer from the mods bridge. Is it running?"; Build
   off; Game's own structures... still works.
8. Set `newassn=0` in bbfix.ini and restart. Create New Association goes straight to the game's dialog (no window).
9. Mods menu > Build a Season: unchanged (no game's-structures button; Build works; year 1998 builds).

Reading the result: step 4 is the proof the season was made. Steps 5 and 7 prove the stock path and the no-bridge
text. Step 5 also shows the game is not left in a bad state: after our window closes, League Management works.

## Gate correction (orchestrator, in game, 2026-10-12)

The hook above was wrong. In the scratch game, a probe that logged every call to `0x680068d0` saw only `cmd=0` timer
ticks while Main > Create New Association opened the stock dialog; `cmd=14` arrived only when the stock dialog's **OK**
was pressed. `0x680068d0` is the New Association screen's own button handler (the gadget dialog 0xc callback
`0x68006150` calls it), so the lane's detour left the menu stock and hijacked the stock OK button.

What the menu really runs: the menu item calls its action through its vtable (`call [eax+0x28]` at `0x68047262`, a probe
on the target logged return address `0x68047265`), and the action is `0x68004ef0`, screen table `0x6808aad0[8]`
(dumped from the file: slot 8 = `0x68004ef0`). That function (not decompiled in the dumps) makes the 0x1ef8-byte screen
object at `0x6808d804` and calls `FUN_68005720` (the stock dialog) when the object's flag at +4 is set. It is not
reached through the screen switch `FUN_68046430` (a probe there saw only screen 6). Entry bytes `64 a1 00 00 00 00`
(`mov eax,fs:[0]`), plain `ret`, no stack arguments. `FUN_68005720` itself cannot be detoured: its `mov ecx,0x6808dd10`
at +3 is under a base relocation and bbfix refuses it.

Fix: modmenu detours `0x68004ef0` (6 bytes) instead; the original runs when the game's structures button is pressed.
Checked in the scratch game (:95, lane bridge with --db/--templates): the menu opens the New Association window with
"Bridge: ready"; 1998 > Build gave "Built 1998 Major Leagues (30L1998)" and "1998 Major Leagues" in Load Association;
"Game's own structures..." opens the stock dialog and its Cancel returns to Association Data with the menus working;
Close leaves the game usable.
