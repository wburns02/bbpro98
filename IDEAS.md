# BBPro98 ideas (captured 2026-10-06, not started)

## GLM-Flash (Hive.ai) inside the game (recaps, news feed, season previews, awards, scouting reports DONE 2026-10-09)

Shipped: option 1, the sidecar. news/watch.py captures every box score the game writes (it keeps only seven sim days
of them), writes a story per game and an 'Around the league' column per date with GLM-Flash, checked so every number
in a story is one of the facts, with a template fallback. Cap: 1000 calls and 3M output tokens a day
(BBNEWS_CALLS, BBNEWS_TOKENS). news/server.py serves the pages behind the same Access login as the game.
Season pieces (news/season.py): a preview once per association from last season's lines of each roster, and the
awards once every regular-season game is played (MVP by runs created, Cy Young by a points score, top 3 each, plus the
division champions), at /news/<ASSN>/preview and /awards. Lahman-built teams show their full names
(work/lahman/teamnames.py, shipped to news-data by deploy.sh).
Scouting reports (news/scout.py): one per team per association, ratings on the 20-80 scale plus last season's line,
at /news/<ASSN>/team/<tid> with the graded roster; at most 3 model reports per watcher scan so a backfill never
starves box-score capture.
Still open from the list below: rookie bios. Shipped since: AI GM (news/aigm.py, preseason computer-team trades) and
the contract and salary system (news/contracts.py, payroll pages in news/server.py).

Goal: use z-ai/glm-5.3-flash through the Hive API to add AI features to FPS Baseball Pro '98.

Constraints (from existing setup)
- Game is a 1998 Win32 binary running under Wine. bblaunch.exe already injects bbfix.dll, so in-process hooks are possible.
- Hive API is streaming-only, exposes no reasoning control (a `reasoning` field is ignored), so use a large max_tokens. Key lives at ~/.config/hivemodels/api_key.env. Never embed the key in a DLL or the repo.
- Cost is about $0.05 in / $0.17 out per 1M tokens, so per-game calls are cheap, per-pitch calls are not worth the latency.

Architecture options (recommended order)
1. Sidecar process (recommended). A Python service outside the game reads bbtrace.log, box scores, hilights/*.tap and the decoded Stats/Assn files, calls Hive, and shows output in a separate window or local web page. Zero risk to the game's stability, no TLS inside a 1998 process, works under Wine or native.
2. Hook plus file drop. bbfix.dll writes events (game final, injury, trade, draft pick) to a spool directory, the sidecar answers with text files. Lets the game trigger features without network code in the DLL.
3. In-game text injection. Hook text drawing or dialogs to show generated text inside the game UI. Highest effort, most fragile, do last if at all.

Feature candidates
- Post-game recaps and play-by-play color from box scores.
- League news feed, season previews, award write-ups from decoded stats (depends on the stats decode and advanced-stat work).
- Scouting reports and rookie bios from ratings.
- AI GM: trade and free-agent suggestions written back through ASN edits (needs the ASN write path; BBEdit or TXTTODAT are the known routes).
- Contract and salary system (the game has none) as a layer in the sidecar, with the LLM only for flavor, not for numbers.

Open questions
- Does any feature need to appear inside the game window, or is the companion page enough.

Dependencies: none left. Stats DAT, ASN, box scores (H files) and play-by-play (game.bko, tapes) all have codecs in work/.

## Import real historical data from Lahman (captured 2026-10-06, DONE 2026-10-08: work/lahman/, every season 1871-2019)
Will: import real historical data from Lahman's database into the game.
Notes: handoff says Lahman files were downloaded on the Mac and a rating-model fit exists (contact~AVG, power~HR, speed~SB, endurance~GS). Write path options: PYR (starting ratings, round-trip writer pyr_io.py exists) for rosters/ratings, and Stats DAT (format now decoded, see work/NOTES_stats_format.md) for historical stat lines. Open questions: which seasons, how to map Lahman playerID to game ids 100+i, and whether the game accepts more than the 1997 roster size.

## Click into active/retired players from the Career data screen (captured 2026-10-06, DONE 2026-10-08: src-latest/mods/playercard.c)
Will: be able to click a player in the Career data screen (active and retired) and open their detail.
Related to the panel-widening work in BBShell.dll (stats grid hit-testing).

## Ten from the sister sims (captured 2026-10-15, not started; report https://claude.ai/artifact/FHYoQk7NozZxDWfsmLqLjX)
Read across ~/puresim/docs/IDEAS.md, ~/tlrb2/IDEAS.md, ~/itp/docs/formats and ~/ClaudeBall (Long Season), checked
against what bbpro98 ships. Measured gap behind item 1: Lahman builds rate players against their own league-year and
the engine plays every era in one PB.INI environment. Lane seasons (tmp/full_*/stats) vs Lahman Teams totals: 1884
BA .288 vs .243, HR/AB .0408 vs .0063, BB/AB .172 vs .045; 1927 HR/AB .0316 vs .0118; 1998 HR/AB .0387 vs .0303.
1. Era run environments: absolute-level rating shift in work/lahman/ratings.py, PB override hook as fallback.
2. Per-player career arcs: a hidden trait hashed from (pid, birth) in aging.c shifts decline onset and size.
3. Hall of Fame: ballot five years after retirement, scored on real Lahman plus simmed seasons.
4. Record book and records chase, with the real Lahman record as the bar in historical leagues.
5. AI GM with team modes (contender, rebuilder), needs-weighted value, a July deadline window.
6. Real midseason moves in historical replays from Lahman Appearances stints, graded by replay.py.
7. Draft room page: the class on 20-80 with fogged grades, picks against needs, grades revisited later.
8. My Player: follow one career (game log, milestones, weekly column, offseason focus as training plan).
9. Scouting fog: seeded per-team noise on the 20-80 view used by aigm, scout and the draft room.
10. Dynasty referee: a ten-season lane-2 soak with bands on age, rosters, era rates, games and crashes.
