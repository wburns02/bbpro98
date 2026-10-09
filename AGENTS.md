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
- Lahman database: /mnt/nvme/tlrb2/lahman/lahmansbaseballdb.sqlite, open read-only
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
