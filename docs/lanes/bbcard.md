# Lane bbcard: a player card from a player list

## What changed

- `news/modbridge.py`: `/news/card/<STEM>/p/<pid>` through op `news`. Text with a heading, the team (or Free agent,
  Retired, Not on a roster), position, age in the association's season, bats/throws, ratings (now and peak, scout
  grades), a batting and a pitching table (one row per period the stats file has him in: Last 7 days, This season,
  Last season, Career), career games by position, his development focus, the news that names him (up to 10, newest
  first, each a link), and links to his development page and the association's news.
- `news/gamedata.py`: `record`, `ratings`, `career_games`; constants `P_PEAK`, `RATING_INDEX`, `PITCH_CODES`, `FLD_SIZE`.
- `src-latest/mods/modmenu.c`: `mm_open_page(path)` export. The reader opens at `path`; the message loop moved out of
  `run_menu` into `pump()` unchanged; `open_news` is `open_reader(owner, "/news/")`.
- `src-latest/mods/playercard.c`: a click on the League Statistics screen opens `/news/card/<assn>/p/<pid>` in the reader
  when `modmenu.dll` is loaded. The built-in card opens when modmenu is absent or `mm_open_page` returns nonzero.
- `news/tests/test_modbridge_card.py`: 32 tests (synthetic ratings, team lines, news order, 404s and traversal refusals,
  the real install and the watcher folder when present).

Tests: `python3 -m pytest news/tests -q` gives 898 passed, 1 skipped (the 1950 association in test_aigm is not on this
machine). `capped` is not installed in this sandbox, so the run was plain pytest. Positive control: with the peak
offset broken (P_PEAK 0x47), `test_hitter_card_shows_now_and_peak_grades` fails.

Builds with the lane's command, zero warnings: `modmenu.dll` and `playercard.dll`.

## Team Statistics screen: what is proven and what is open (round 1, superseded by Round 2 below)

Not hooked in round 1. The state object was not proven then; Round 2 proves it and hooks the screen.

Proven (decompile dump `BBShell/_all.c` and the install files, read only):
- The screen is dialog 0x14. `SHELL.VOL` has a REQ record titled "Team Statistics -" whose number is 0x14. The League
  record ("League Statistics -") is 0x0f, the dialog that `StatsScreen_InitGadgets` installs at `_all.c:9237`
  (`FUN_68038ef0(7, 0xf, ..., &LAB_6800d460)`). So the REQ number is the dialog number.
- The install: `FUN_68036dc0` at `_all.c:40909`, `FUN_68038ef0(0x14, dialog, flag, &LAB_68036ec0)`. Its caller
  `FUN_68036b80` (`_all.c:40811`) passes dialog 0x14. So the callback at mgr+0xc0 is 0x68036ec0 while this screen is up.
- Its click mapping, `FUN_68036fd0` (`_all.c:40936`): the id is cell 10 of a row when that cell's type is 0x2000, read
  from the table at object+0x14 (`_all.c:40965`). The grid is at object+0xfc and the scroll group at object+0xfa
  (`_all.c:40925`).
  Body columns are gadgets 9..0x12, as on the League screen.

Open (why the hook is not written):
- The object passed as `this` to `FUN_68036b80`. Its only direct call site in `BBShell.dll` is at VA 0x68036280. No
  dump function covers that address; it sits between `FUN_68036170` and `FUN_68036300`. Settle it by disassembling
  BBShell.dll at 0x68036200 to 0x68036300 and reading what ECX holds at the call.
- The callback body `LAB_68036ec0` is not in the dumps. The table's layout (its row count and rows pointer) is not read
  anywhere; it is only known from how `FUN_68060740` is called.
- Nothing logs a click on this screen: the probe in `h_event` logs only when mgr+0xc0 is the League callback. A probe
  that logs mgr+0xc0 and the object would settle the callback in game. It is not written.

Roster screens (Team menu): open. Candidates: dialog 0x1d (callback 0x680380e0, installed at `_all.c:41457`, screen
global store at `_all.c:41052`,
click mapping FUN_68038900 at `_all.c:41862`, but the id cell is not established); dialog 0x0c/0x0d (callback 0x6801fad0, installed at `_all.c:23613`,
click mapping FUN_6801fc80 at `_all.c:23709`, but its screen global is not found). Whether the League object's team mode
(`update_stats_team_context`, `_all.c:9100`, same callback 0x6800d460) is the screenshot's screen is not proven. If it
were, the existing hook would already catch the click, and the report says it does not.

## In-game checks (orchestrator)

Setup: bbfix.ini has `load=mods\modmenu.dll` and `load=mods\playercard.dll`, the bridge runs with the game's `--game`,
`--data` and `--backup`, and a season association is in the game.

1. Card through the bridge. Open League Statistics (Players, any period) and click a player's name. The League News
   reader opens with the card. The first line is the title "Name (POS, age)", underlined. The body has Team, Position,
   Age, a Ratings table with Now and Peak columns, Batting and Pitching tables for each period the stats file has,
   "Career games by position" when he has games, "Current focus", and "News" with "No news yet." or the news lines. The
   link list has Player development and Association news.
2. Ratings. For a hitter, the Contact row's grades match the PYR's contact rating now and at peak (scout grades 20 to
   80, step 5). A pitcher shows Stamina, Control, Hold runners, Strikeout (Now only, Peak "-") and only the pitches he
   has.
3. Fallback. Stop the bridge and click a name. The reader shows "No answer from the mods bridge. Is it running?". Close it,
   and the built-in stats card opens exactly as before.
4. modmenu absent. Remove `load=mods\modmenu.dll` from the game's `bbfix.ini` and click a name. The built-in card opens.
5. The game survives. After closing the card from step 1, the League Statistics screen still responds to clicks, and
   a second click opens another card. This is the first run of the reader's nested message loop inside the stats
   screen's input handler, so watch for a hang or a missing repaint.

## Choices made

- Height and weight: the repo decodes no PYR field for them, so the card does not show them.
- Fielding: a hitter's card shows his fielding at his own position only.
- Pitches: a pitch is shown when its now or peak rating is above zero.
- Team: a team roster window that holds him, else the free agent file (`Assn/<STEM>.PYF`) gives Free agent, else Retired.
  If the PYF is unreadable the line is "Not on a roster".
- News: the newest 2000 story files by modification time are read, and a story counts when his full name appears in its
  text or its facts. Transaction events for his id count too. Each item sorts by its season (the association's, for a
  story), then month, day and slot. An event's date is the last played day, so an "Offseason" event sorts before the
  first game of its season. The feed columns are not searched.
- Bridge failure: `mm_open_page` returns 1 after the reader shows its timeout message; the built-in card opens only after
  the reader is closed.
- A 404 from the bridge (a player the PYR does not hold, or an association that is not in the game) also returns 0, so
  the reader keeps the 404 page and the built-in card does not open.
- `test_modbridge_card.py` is a separate file, as `test_modbridge_focus.py` is, because `test_modbridge.py` is already
  700 lines.

## Round 2: Team Statistics (dialog 0x14) is hooked

### What changed

- `src-latest/mods/playercard.c`: `SCREENS[]` holds the League and Team stats screens. A left press (rising edge in
  `h_event`) reads the callback at mgr+0xc0, takes that screen's object from its pointer global, hit-tests its body
  gadgets, maps the visible row through `FUN_68043bf0` with the screen's scroll group, reads the id cell and opens the
  card as in round 1 (`mm_open_page` with `/news/card/<assn>/p/<pid>`, built-in card as fallback).
- Team values: callback 0x68036ec0, object pointer global 0x6808da24, row table at +0x14, scroll group (short) at +0xfa,
  body gadgets 9..0x12 only (the widened 0x30..0x33 belong to League), readable object size 0x5f4.
- League values are unchanged (table +0x3c, group +0x694, size 0x6a0, body 9..0x12 and 0x30..0x33).
- `probe=1` logs every left press, whatever the callback: mgr+0xc0, the screen it names, the League and Team object
  pointers (`obj`, `team_obj`), the current screen id global 0x6808da50 (`cur_screen`), the hit gadget with its top y
  (`gy`), the visible row and table row, the id cell with its type, pid and name, and `no card: <why>` when none opens.

### Evidence (BBShell.dll VAs; objdump -d -M intel; dump line numbers are `BBShell/_all.c`)

Object and callback:
- 0x68036246 `mov ds:0x6808da24,eax`: the Team object. The ctor `FUN_680367e0` is called at 0x68036236 with ecx = esi,
  and esi comes from the allocator 0x680367c0 with 0x5f4 (`push 0x5f4` at 0x68036212).
- 0x680361fe..0x68036206: if the global is set and `[obj] == 0x14`, the open goes straight to 0x6803624b (the code's own
  "already built" test).
- 0x6803627a..0x68036280: `mov ecx, ds:0x6808da24; call 0x68036b80` is the install. It is the only direct call to
  `FUN_68036b80`, and the image holds no dword that is 0x68036b80, so no indirect call either (scanned). It runs only when
  `di == 0` at 0x68036258.
- `FUN_68036dc0` (`_all.c:40909`) calls `FUN_68038ef0(0x14, …, 0x68036ec0)`. The 4th argument is `push 0x68036ec0` at 0x68036dcd.
  `FUN_68038ef0` writes the callback to `_DAT_6808ddd0` (`_all.c:42292`), which is mgr+0xc0 (0x6808dd10 + 0xc0).
- 0x68036ec0 is the callback body: `mov ecx, ds:0x6808da24; push eax; call 0x68037080`. The callback uses the same global,
  so the global is the object that owns the table.

Row table and id cell:
- `FUN_68036c40` fills the team rows through `StatsGrid_FillRowCells` 6805c930, called at 0x68036cb8, 0x68036cd2 and
  0x68036d8b. The table is at obj+0x14 (`lea edi,[esi+0x14]` at 0x68037030 for the click read).
- Layout (`FUN_68060740`, 0x68060740, the same reader League uses): count u16 at table+0, rows pointer at table+4, row
  stride 0xa0, cell i at row+8i (type int32, value at +4), name at row+0x80.
- The id cell is written at 6805cb0b: `push 0x2000` (6805cb06), `push 0xa` (6a 0a), then `call 0x680606a0`. Stock: cell 10.
- bbfix [widen] (`src-latest/bbfix.c:270`, site "term") patches that push to 14. Its other sites, "bound" (6805cafb,
  `cmp bp,0xa` to 14) and "slot" (6805cae2), are in the same function (6805c930 to 6805cb1b).

Answer to the brief's widen question: yes. [widen] moves the Team id cell the way it does on League, because both screens
fill their rows through 6805c930. The mod reads the push at runtime (`ID_PUSH_VA`), so the card uses cell 14 under widen.
Not checked in game.
- Side effect (by reading, not checked in game): the game's own `FUN_68036fd0` still reads cell 10 (`push 0xa` at
  0x6803703c). It is called from `FUN_68036c40` at 0x68036da5 and from `FUN_68037080` at 0x680370a1 (header clicks).
  Under widen cell 10 is a stat cell, so its id list (`FUN_68053e20`, 0x68037069) is empty. The card does not use it.

Association name:
- Team ctor: `call 0x68046580` at 0x680368b2, `mov [ecx+8],eax` at 0x680368ba. The League ctor `FUN_6800ccc0` does the same
  at 0x6800cd6b and 0x6800cd73 (`mov [ecx],7` at 0x6800cd5a gives its id). `FUN_68046580` returns the one singleton
  `DAT_6808e0fc`, so both screens name the same association.
- Name: `(*(char ***)(obj+8))[0x25]`, the same read as League (`FUN_6803da90`, `_all.c:46419`, builds "STATS\<name>.DAT").

Scroll group and body:
- obj+0xfa is zeroed in the ctor (0x680369c6) and set by `FUN_68036dc0` from `FUN_68043810(mgr, 8, 6, 7, 9, rows, …)`.
- The body loop in `FUN_68036dc0` runs ids 9..0x12 (`FUN_680436c0`/`FUN_68043400`, `_all.c:40909`).

### Open (settle in game, the probe logs each)

1. First open. The open function at 0x680361b0 (registered in the request table at `.data` 0x6808ab20, from the call at
   0x68021380) sets `di = 1` after it creates the object (0x68036242). That path skips the install (0x68036255..0x68036258) and calls `FUN_68066fc0` instead. Whether the
   callback is set after the first open is not settled by reading. Check whether the first click on a fresh Team open logs
   `mgr+0xc0=0x68036ec0`; if not and the second open does, the install is on the second open only.
2. Stale callback. `_DAT_6808ddd0` (mgr+0xc0) is written only by `FUN_68038ef0`, and nothing clears it on close. After the
   Team screen closes, mgr+0xc0 keeps 0x68036ec0 until another screen installs its callback. The round-1 League path has
   the same exposure. The probe's `cur_screen` (0x6808da50, set by `FUN_68038ef0`) shows which screen was last installed.
3. Row pitch on the team grid is assumed 11 px (`ROW_H`, the League grid). The probe's `gy` and the hit row check it.
4. Roster screens (Team menu): still open, as in round 1.

### In-game checks (orchestrator)

Setup: as round 1, plus `[playercard] probe=1` in bbfix.ini. Run once with `[widen] enable=1` and once with `enable=0`.

1. Team card. Team menu > Team Statistics (Season). Click a player's name. The News reader opens with the card (round-1
   check 1). The log has, in order: `click ... mgr+0xc0=0x68036ec0 screen=Team obj=0x... team_obj=0x... cur_screen=0x14`,
   `Team hit gadget 0x9..0x12 gy=... vis=... -> scroll group ..., table row ... of ...`, `Team row ... cell 14 type=0x2000 pid=...`
   (cell 10 with widen off), then `playercard: pid ... in the News reader -> 0`.
2. Rows. Click the top, middle and bottom visible rows. Each gives its own pid, and the card's name matches the row.
3. Second open. Close the screen, reopen it from the Team menu and click a name. Log mgr+0xc0 and obj on the first and the
   second open (open item 1).
4. Stale check. Close Team Statistics, then click on the screen you return to. The log must show `screen=none` or a
   non-team callback; a Team card there is a bug (open item 2).
5. Widen. Step 1 with enable=0 must log cell 10 and step 1 with enable=1 must log cell 14. Both must show the card.
6. League still works (round-1 checks 1 to 5).

### Choices made (round 2)

- The Team body is gadgets 9..0x12 only. The widened 0x30..0x33 are not initialised by the Team install, so they are not
  tested.
- A screen-id check on the object (`[obj] == 0x14`) is not used in the click path. The probe logs the id global instead,
  because 0x6808da50 is written by more than one installer (`_all.c:42248`, `42291`, `42345`) and its value for a
  League screen after a child dialog was not established.
- The League constants and checks are unchanged except that they now come from `SCREENS[]`.

Build: `playercard.dll` and `modmenu.dll` with the lane command, zero warnings; `playercard.c` also clean under
`-Wall -Wextra`. Tests: `python3 -m pytest news/tests -q`: 898 passed, 1 skipped (the same 1950 skip as round 1).
`capped` is not installed here, so the run was plain pytest. No Python changed in round 2.

## Gate (orchestrator, in game, 2026-10-12)

Scratch game (:95, MLBPA97 copy, bridge from this worktree), `[playercard] probe=1`.

- Found: one click opened the card about every 250 ms (78 bridge requests from one click). `on_click` ran the reader's
  modal loop before `h_event` recorded the press, so each game tick inside that loop read as a new press. Fixed: the
  edge is recorded first and ticks during an open card are ignored (`in_click`).
- Found: the press after closing a card opened nothing. Tick logging showed the game holding the button down at the
  reader's Close position (613,473) until the next full click: the game sees the press that closes the card but not its
  release. Fixed: `release_game_button` posts WM_LBUTTONUP to the window under the cursor (the screen's FrontOffice
  child, not the FPS_Desktop frame; posting to the active window did nothing) once the card is gone.
- Checks, all passed after the fixes:
  1. Team Statistics, Atlanta: Ainsmith (row 0, pid 1995), Melton (row 13, pid 1792), Wohlers (row 19, pid 101),
     Sudhoff (row 24, pid 1530), Barberie (row 26, pid 1443). Callback 0x68036EC0, cell 14 under widen. The card's lines
     match the screen (Barberie 62 AB 10 H 3 HR; Melton 17 AB 1 H; Sudhoff 186 AB 43 H).
  2. Cards opened back to back without reopening the screen.
  3. Stale: on Team Data the callback is 0x6802ADE0, `screen=none`, no card.
  4. Widen off: cell 10, same pid, card shown.
  5. League Statistics: a team row is refused (pid 1, below 100); Players view, Lopez row 3 pid 109, card matches.
  6. Bridge stopped: the reader says "No answer from the mods bridge" after 20 s; Close opens the built-in card with the
     right lines. The press after the built-in card closes opens the next card.
- Known: with the bridge stopped the built-in card only appears after the reader's 20 s timeout and a Close.
