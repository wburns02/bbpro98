# bbpro98: agent rules

Public repo (MIT) of tools and research for FPS Baseball Pro '98. Python codecs live in work/, research lanes in re/.

## Never commit
- Game files or anything the game wrote: *.ASN *.PYR *.PYF *.DAT *.VOL *.dll *.exe, saves, templates, snapshots.
- Decompile dumps (/mnt/nvme/bbpro98/index), third-party tools, Sierra patch notes.
- Secrets of any kind. No network calls from repo code, with one exception: news/hive.py (the hosted news
  sidecar's GLM client), which reads its key at call time from a file outside the repo.

## Paths
- Work copy of the install: /mnt/nvme/bbpro98/work_install. Never write the live install
  (~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98) directly; work/patches/install_live.sh does that.
- Lahman databases: /mnt/nvme/bbpro98/lahman2025/lahman2025.sqlite (2025 release, what build.py uses) and the older
  /mnt/nvme/tlrb2/lahman/lahmansbaseballdb.sqlite (load_csv's schema reference). Open both read-only
  (sqlite3.connect('file:...?mode=ro', uri=True)).
- Large data goes under /mnt/nvme, never /home/will or /tmp.

## Code conventions
- Python 3, standard library (numpy allowed in work/lahman/ratings.py only). No eval/exec, no shell=True.
- Codecs round-trip byte for byte: encode(x, decode(x)) == x. Find c-tree members by name (ctree.parse), never by
  member number; the number differs between files.
- ASN/PYR cipher: seed is per file (ASN bytes 0x310-0x311, PYR bytes 0-1); never hardcode f5dc.
- Tests: python3 -m pytest <dir> -q, run through `capped`. Tests that need game files skip when they are absent.

## Landmines
- Lahman builds: every active roster needs five pitchers. LINEUP.DLL fills a five-man rotation before the batting
  order and borrows position players for it; fewer than eight fielders left means a 0 in the order and a crash at
  LINEUP+0x116e0. Decode a game's setup with work/gamebk.py (game.in) to see it.
- One-league templates (league record byte 2 = 0) show blank league and division fields. Writing text there makes
  Association Data ask to save on every exit, which blocks a scripted sim.
- Player card: the id cell is 10 stock and 14 with bbfix [widen]; read the live push at 6805cb0b, never hardcode.
- Templates for shapes with a 14-team league stop on a Historical/Divisional schedule prompt while minting; copy the
  files before answering it and the ASN has no s records, so the season never plays a game. build.py refuses such
  a template. A season test must count games played after the sim, not just the absence of crashes.
- Hosting: units started from a desktop user session inherit Wayland variables; unset them or x11vnc exits.
- Scripted sims under Wine: a dialog the game raises mid-sim (the draft notice) is not painted until the window sees
  pointer input, and at season end the 'Updating association data' box stays on screen even with input. Move the
  pointer before every screenshot (seasonloop.look) and judge the season by games played, not by the screen.
- Lahman pitch ratings: never copy a donor's pitches verbatim; shift them to the fitted stuff (ratings.stuff). Sim ERA
  moves about 0.1 per point of mean pitch rating, so one cloned ace arsenal gives a sub-1.00 ERA.
- League Management, Team > Data: one click on Ownership turns a Computer team Human with no prompt (only Human to
  Computer asks), and the change is written to the ASN. Never click it in a real association (MLBPA97 is Will's).
  Claim Free Agent is greyed out unless the selected team is Human; claims go through when the league plays a day.
- Hosted game sandbox: with no audio device the menu music fails at once and the shell retries tracks in a busy loop
  that ignores clicks. hosting/run-game.sh gives the sandbox ALSA's null device; never drop that line.
- Lahman builds: template-generated players (roster pads) come out with K 0 and CO near 28 and pitch to a 9+ ERA.
  build.py rates every pad from a blank season (league-average ratings, donor arsenal) and pads pitchers to MIN_PIT
  10 with GS 0.5 so real starters lead the rotation. Never copy a template player verbatim onto a roster.
- League aging: stock rules age a career league (MLBPA97 28.5 in 1997 to 31.1 by 2007). Peak ratings never fall,
  spring training pulls current back to peak, and retirement is age-only past 35. mods\aging.dll (src-latest/mods)
  lowers peak with age and retires by age and ability. New players (FUN_68040da0) top the pool up to 55 per team,
  at least 3 per team, so inflow only grows once retirements pull the pool under 55 per team. Any multi-season check
  must measure league age and per-team roster and pitcher counts each offseason (seasonloop "seasons" prints
  demographics per rollover), not just one season's stats.
- In-game Mods menu: mods\modmenu.dll takes over the main menu's WWW SITE button (EZShell 0x6a006370) and talks to
  news/modbridge.py only through files in <game>/Mods/spool (the hosted game's sandbox has no network). Requests are
  written as .tmp then renamed to .req, claimed by renaming to .work, answered as .rsp; never read a half-written file.
  Without the bridge running the menu times out with a message; it never blocks the game. work/patches/mods_button.py
  relabels the button art (WEB*.BMP, originals kept as .orig).
- Hosted bridge trust boundary: the game sandbox writes the whole Wine prefix, so any directory under it can be
  swapped for a symlink between a check and a use. modbridge holds the spool by descriptor (open_dir walks from /
  with O_NOFOLLOW) and does every list, read, rename, write and remove relative to it; never go back to path strings.
- Windows a mod creates on the game's UI thread get skinned by ODASL.dll's WH_CBT hook, and its subclassed EDIT
  answers WM_NCHITTEST with HTMENU, so text boxes never take focus. modmenu installs its own thread CBT hook first
  and skips the chain for its classes. Top-level popups also need ShowWindow; without WS_VISIBLE they never map.
- Harness lanes: BBLANE=1 (default, ~/.bbpro98_prefix, work_install, :99) and BBLANE=2 (/mnt/nvme/bbpro98/prefix2,
  work_install2 linked as C:\Sierra\BBPRO_98_wk2, :97) run two plans at once; each lane only kills its own game
  processes. The association list is sorted by label and its rows sit at y = 479 + 11n, so a plan's row depends on
  which associations are installed in that lane. A wrong row opens another league; seasonloop.season stops with
  wrong_association when another ASN's mtime moves and this one's game count does not.
- Never rsync --delete into a lane's work copy or a game directory: it removes associations the plans rely on.
  Never pkill by a pattern your own shell's command line contains; pgrep -af "pat[x]" and kill exact PIDs.
- An association's season is not the year in its name: a career league keeps its name. The ASN 'a' record (key not
  league.TEMPLATE_KEY) holds the season date as a u32 at payload offset 14, a PYR birth serial
  (gamedata.association()['season_year']). It moves to the next April at each rollover.
- Lahman database: build.py reads /mnt/nvme/bbpro98/lahman2025/lahman2025.sqlite (work/lahman/load_csv.py from the
  SABR 2025 CSV release, Negro Leagues 1920 to 1948 included). The CSV edition broke some unique keys; load_csv keeps
  those indexes without the constraint. After a new release, rerun work/lahman/teamnames.py.
- ASN rosters (r.dat, 294 bytes): a 126-u16 id window at payload 42. Index 0..24 is the active roster, 25..54 the
  reserves as (id, level) pairs, then two batting orders and two defensive alignments (eight ids each, 0xFFFF
  between) and the pitching staff. Bench hitters appear only in the active slots. league._roster_of flattens the
  window and the roster codec's write path re-sorts it, which wipes the lineups: change a roster by replacing ids in
  place (news/aigm.apply_trade). The PYR has no team field; a player's team is the window that holds his id.
- Ownership is the t record's deciphered byte 0x0c (1 Human, 0 Computer). Computer teams never trade with each other
  (tr.dat has no team-to-team records); they only release and claim. news/aigm.py makes their preseason trades.
- The in-game news reader (modmenu) shows a page title only in the window caption, which a Wine desktop with no
  window manager never draws: bridge pages carry their own heading (modbridge._heading).
- hosting/deploy.sh copies news/*.py plus an explicit list of data files (salary_table.json). A new runtime data
  file under news/ must be added to that list, or the hosted feature silently does nothing.
- Player development focus: news/modbridge.py writes <game>/Mods/focus.txt (pid birth kind assn) and aging.dll
  re-reads it when it changes; at most 5 per association.
