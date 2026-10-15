# bbfix v1.0.3 (draft, not published)

Changes since v1.0.2. v1.0.2 is itself still an unpublished draft, so if both go out together these notes add to
its text; they do not replace it.

## In the zip

- **mods\champtext.dll** (new, in the default `[mods] load=` list): the season-end texts (the World Series champion
  screen and its notices) no longer show `<No Name>` where a team or player name belongs.
- **bbfix.dll**: bbtrace.log no longer grows without bound (one 30-team season reached 158 MB). Past
  `[trace] max_mb` (default 64) it moves to bbtrace.1.log and starts fresh, so the two files use about twice that
  much at most. `max_mb=0` keeps the old unlimited behavior. Add the `[trace]` lines from bbfix.ini.sample to an
  existing bbfix.ini to change the limit; without them the default applies.

## League News (the Python watcher and its pages, from the source)

- `python3 news/play.py` starts the watcher and the Mods menu's bridge with one command. Ctrl+C stops both; a
  second Ctrl+C during shutdown ends them at once.
- Past seasons: at the rollover the watcher archives the season's news, and each league has a page per past season.
  The player card's News tab reads those archived seasons too.
- When the watcher has stories for only some of the games played (the game keeps box scores for seven sim days, so
  a watcher that is not running through a long sim misses games), the front page says so: "Stories for N of M
  games played."
- Scouting reports use the season year for ages, not the calendar year.

## For people running the source

- work/harness/lanestat.py: a read-only status line for a harness lane (working, stale paint, idle), with
  `--watch` and `--heartbeat`. Judge a stall from it, never by attaching a debugger to the game.
- news/gamedata.py reads the postseason bracket (series, wins, games, champion) from the association file.
- The harness can start a plan from a saved association snapshot (`resume` in the plan).

## Known limits

- Tested under Wine on Linux only, as before.
