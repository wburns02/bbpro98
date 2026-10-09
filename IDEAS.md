# BBPro98 ideas (captured 2026-10-06, not started)

## GLM-Flash (Hive.ai) inside the game (recaps and the news feed DONE 2026-10-09: news/, hosted at /news)

Shipped: option 1, the sidecar. news/watch.py captures every box score the game writes (it keeps only seven sim days
of them), writes a story per game and an 'Around the league' column per date with GLM-Flash, checked so every number
in a story is one of the facts, with a template fallback. Cap: 1000 calls and 3M output tokens a day
(BBNEWS_CALLS, BBNEWS_TOKENS). news/server.py serves the pages behind the same Access login as the game.
Still open from the list below: season previews, award write-ups, scouting reports, AI GM, contracts.

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
Will: import real historical data from Lahman's database into the game. Not to be actioned now.
Notes: handoff says Lahman files were downloaded on the Mac and a rating-model fit exists (contact~AVG, power~HR, speed~SB, endurance~GS). Write path options: PYR (starting ratings, round-trip writer pyr_io.py exists) for rosters/ratings, and Stats DAT (format now decoded, see work/NOTES_stats_format.md) for historical stat lines. Open questions: which seasons, how to map Lahman playerID to game ids 100+i, and whether the game accepts more than the 1997 roster size.

## Click into active/retired players from the Career data screen (captured 2026-10-06, DONE 2026-10-08: src-latest/mods/playercard.c)
Will: be able to click a player in the Career data screen (active and retired) and open their detail. Not to be actioned now.
Related to the panel-widening work in BBShell.dll (stats grid hit-testing).
