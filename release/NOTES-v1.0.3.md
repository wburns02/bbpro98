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
  If the archive move fails partway (a locked file), the next pass finishes it into the same past season folder
  instead of leaving the season split in two.
- When the watcher has stories for only some of the games played (the game keeps box scores for seven sim days, so
  a watcher that is not running through a long sim misses games), the front page says so: "Stories for N of M
  games played."
- Scouting reports use the season year for ages, not the calendar year.
- Rookie class pages: at each rollover the watcher writes the new season's rookie class, linked from the Season box.
- A page per sim day: that day's Around the league column and its stories, linked from the feed.
- Re-simming from an earlier day (a restored save) no longer leaves newer news behind: the watcher moves the newer
  stories aside and sets the last day back.
- The front page has a League box: players on rosters, mean age, how many are 25 or under and 33 or over, and free
  agents.
- Postseason: a postseason page per season (the bracket, series by series, linked from the season links), recaps
  for postseason games (round and game number in the story), and a Champions page per league (one row per season,
  linked from Past seasons once a season has a champion). The in-game News reader shows the League box and the
  Champions page as well.
- Day pages and the Around the league column cover postseason days too, with the series state in place of the
  standings.
- Once the World Series is over, the postseason page leads with a written wrap of the whole postseason (the model
  when one is set up, else the template).

## For people running the source

- work/harness/lanestat.py: a read-only status line for a harness lane (working, stale paint, idle), with
  `--watch` and `--heartbeat`. Judge a stall from it, never by attaching a debugger to the game.
- news/gamedata.py reads the postseason bracket (series, wins, games, champion) from the association file.
- The harness can start a plan from a saved association snapshot (`resume` in the plan).
- news/gamedata.py reports league demographics (age make-up of rosters and free agents) from the ASN, PYR and PYF;
  the harness prints them at every rollover and logs the champion of each season.
- The harness's progress lines carry the lanestat verdict, so a stalled lane shows in its own log.
- work/harness/runreport.py LOG prints one summary of a run log: demographics per rollover with the change in mean
  age, champions, seasons, verdict counts and stops (`--json` for the raw summary). It also counts the offseason
  steps and the sim outcomes (refused, draft ok, draft failed).
- Developer scripts (hookab, simdays, sort_test, play_logged) were hardened.

## Known limits

- Tested under Wine on Linux only, as before.
