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

## Team Statistics screen: what is proven and what is open

Not hooked. The brief allows only proven targets, and the state object for this screen is not proven.

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
