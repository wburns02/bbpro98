# bbpro98: builder card

Full project rules and the long landmine list: CLAUDE.md (read it before touching the game, the harness or the
hosted bridge). Handoff history: HANDOFF.md. Current state and open items: STATUS.md.

## 1. What this is
Public MIT repo (github.com/wburns02/bbpro98) of tools and research for Front Page Sports Baseball Pro '98 (Sierra,
1997), a 32-bit Windows game run under Wine on Linux. It holds: format codecs (work/, re/formats/), the mod engine
and mods in C (src-latest/, built with zig cc into bbfix.dll plus mods\*.dll), installers (work/patches/), a Lahman
season builder (work/lahman/), a Wine test harness (work/harness/), a news sidecar and the in-game Mods menu bridge
(news/), and the browser hosting kit (hosting/). No game files are in the repo and none may ever be added.
Live: https://bbpro98.ecbtx.com (PIN gate; an unauthenticated GET answers 302 to /gate/login). It runs on the
r730 host as systemd user units, deployed by hosting/deploy.sh. Releases: GitHub drafts that Will publishes by hand.

## 2. Install
No package install. Python 3 standard library only (numpy only in work/lahman/ratings.py). For tests you also need
`pytest` (xdist optional) and `Pillow` (the mods_button test). To build the DLLs: `pip install ziglang==0.16.0`.
Paths in many scripts are hard coded to the author's machine (/home/will, /mnt/nvme); do not "fix" them in passing.

## 3. Run locally (needs a game folder holding Assn/ and Stats/; never the live install)
- News watcher plus bridge, one command: `python3 news/play.py --game GAME --data DATA --backup BACKUP --no-llm`
- Watcher once, no model calls: `python3 news/watch.py --game GAME --data DATA --once --no-llm`
- News pages (read only): `python3 news/server.py --data DATA --port FREEPORT`
- Bridge alone: `python3 news/modbridge.py --game GAME --data DATA --backup BACKUP`
- PIN gate: `python3 hosting/gate.py --pin-file F --secret-file S --port FREEPORT`
- Build a release zip (OUT must be outside the repo): `tools/build_release.sh OUT PYTHON` where PYTHON has ziglang
  installed (CI uses `python`; locally /mnt/nvme/bbpro98/zigenv/bin/python3).
Never bind 8765, 8766, 8794, 8795, 8799 (live services). Check `ss -ltn` and pick a free high port.
Builders never launch the game, Wine, Xvfb or the harness.

## 4. Test
- Everything (the real suites): `capped -t 1500 python3 -m pytest news work hosting re/formats -q -p no:cacheprovider -n 2`
  Measured 2026-10-15 12:43 CT (plus tests/holdout): 1839 passed, 1 xfailed, 1 error in 30 s. The error is not a
  regression: `re/formats/test_roundtrip.py` is a script (`python3 re/formats/test_roundtrip.py <file.pyr>`) whose
  `test_pyr_roundtrip(pyr_path)` pytest collects and cannot feed, so it errors on main since af2f7a6. Treat exactly
  that one error as the baseline (or add `--deselect re/formats/test_roundtrip.py::test_pyr_roundtrip`); any other
  failure is yours.
  Tests that need game files skip when the files are absent. `capped` caps RAM at 4G and kills a runaway.
  Shared machine: at most `-n 2`. Other lanes may hold a lock; wrap a full run in
  `flock /home/will/.local/state/burn-week/pytest.lock <cmd>` during burn week.
- One file: `python3 -m pytest news/tests/test_aigm.py -q -p no:cacheprovider` (swap in any file under news/tests,
  work/lahman/tests, work/harness/tests, hosting/tests).
- Holdout suite (15 tests, about 6 s, offline, no game files, no Wine): `python3 -m pytest tests/holdout -q -p no:cacheprovider`
  Do not edit tests/holdout to make a change pass. One test there is a strict xfail that pins a real bug
  (SHA256SUMS.txt lists itself); when the bug is fixed the test fails until its marker is removed.
- Codecs must round trip byte for byte: `encode(x, decode(x)) == x`. A claim about a game file format needs that test.

## 5. Lint and typecheck
There is no lint or typecheck config in the repo. The check that works: `ruff check --select F,E9 news hosting work/patches work/harness work/lahman`.
Today it reports 39 errors on main (mostly unused imports; work/patches/bytepatch.py and liveguard.py import for
side effect on purpose). Do not add more. No typechecker is used. `python3 -m py_compile <file>` is the minimum.

## 6. Deploy and verify
- Code: commit on a branch, merge to main in the integration checkout, `git push` to GitHub. Pushing does NOT deploy.
- Hosted game and news: `HOST=user@host hosting/deploy.sh [--dry-run]` (rsync, ships changed code only, restarts a
  unit only when its files changed; never `--delete`). Run it only when Will's workflow asks; builders use `--dry-run`.
  A new runtime data file under news/ must be added to deploy.sh's explicit list or the feature silently does nothing.
- Live local install: `work/patches/install_live.sh` (refuses while a game runs in the live prefix, or when
  BBShell.dll is not pristine, or when a listed MODS file is missing) and `revert_live.sh`. Builders never run them.
- Release: `git tag vX.Y.Z && git push --tags` makes CI (windows-release.yml) build the zip and open a DRAFT release.
  Will publishes. windows-build.yml builds on pushes touching src-latest/, release/ or tools/build_release.sh.
  Verify with `gh release list` (read only). The version string is only `git describe --tags --always --dirty`.
- Verify hosted: `curl -s -o /dev/null -w '%{http_code}' https://bbpro98.ecbtx.com/` is 302 (gate). Anything else is news.

## 7. Migrations
No database. Lahman data is a sqlite file opened read only: `sqlite3.connect('file:...?mode=ro', uri=True)`.
Game file formats are the schema: change a codec only with a byte for byte round trip test.

## 8. Layout map
- news/modbridge.py: spool bridge for the in-game Mods menu (trust boundary, descriptor based)
- news/create.py: Create a Player (adds a record to an association's PYR and PYF; backup first, append only)
- news/aigm.py: AI trades rewrite two roster windows inside an ASN; validate() checks the result
- news/focus.py: focus.txt rules (parsed in C by aging.dll)
- news/watch.py, server.py, gamedata.py, season.py, scout.py, recap.py: the news sidecar and its readers
- hosting/gate.py: PIN gate (HMAC cookie, lockouts, safe_next); nginx.conf, systemd/, deploy.sh, run-game.sh
- work/league.py, ctree.py, fpscipher.py: ASN/PYR/c-tree codecs and the per-file cipher (`league._forward(seed)`)
- work/lahman/: build.py makes a playable association from a Lahman season; expand.py adds teams
- work/patches/: install_live.sh, revert_live.sh, bytepatch.py (asserts old bytes), liveguard.py, mods_button.py
- work/harness/: Wine driver (seasonloop.py, ingame.py, lanestat.py). Needs a running game; builders skip it
- src-latest/: bbfix.c, bblaunch.c, bbmod.h, mods/*.c (aging, rookies, playercard, modmenu, champtext, steal)
- tools/build_release.sh and release/: the zip recipe, README.txt, bbfix.ini.sample, release notes drafts
- re/ and work/spec/: reverse engineering, Ghidra scripts, format specs. Read mostly, edit rarely
- docs/lanes/*.md: per-lane evidence notes (bbcard, bbpost, bbnickname...)
- tests/holdout/: the independent regression suite described in section 4

## 9. Landmines already paid for (details in CLAUDE.md)
- Stale update box: at season end and over the idle postseason schedule the "Updating association data" box stays
  painted. Judge a run by games played and Assn mtimes, never by the screen.
- Never attach winedbg (or any debugger) to a running game: the attach faults under wow64, the crash handler takes
  the process and the lane's run is lost. Use `python3 work/harness/lanestat.py --lane 2 --no-shot` (read only).
- Wine runs leave winedevice.exe on the system D-Bus and fill the quota, which killed the GNOME session twice. Any
  wine run: `export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/nonexistent` and finish with `wineserver -k`.
- League aging: judge any aging or retirement change by league mean age and per-team roster and pitcher counts each
  offseason, never one season's stats; the retirement curve (v3, 2026-10-15) holds the mean flat at about 145
  departures a season (CLAUDE.md "League aging").
- Never `pkill -f` a pattern your own command line contains; `pgrep -af "pat[x]"` and kill exact PIDs.
- Cipher seeds are per file (ASN bytes 0x310-0x311, PYR bytes 0-1); never hardcode f5dc. Find c-tree members by
  name (ctree.parse), never by member number.
- Edit ASN rosters in place (news/aigm.apply_trade). The roster codec's write path re-sorts the window and wipes
  the lineups. A PYR has no team field.
- Lahman builds: every roster needs five pitchers (fewer leaves a 0 in the order and a crash at LINEUP+0x116e0);
  never copy a donor's pitches verbatim; never copy a template player verbatim onto a roster.
- One-league templates show blank league and division fields. Writing text there makes Association Data ask to
  save on every exit, which blocks a scripted sim. Never write a team nickname at t record 0x23 for Lahman builds.
- Never click Ownership in League Management on a real association (turns a Computer team Human with no prompt).
- Bridge spool: hold the directory by descriptor (open_dir with O_NOFOLLOW) and work relative to it; never go
  back to path strings. Requests go .tmp, .req, claimed as .work, answered .rsp. Never read a half written file.
- A full harness season takes 60 to 90 minutes: never run it under `capped` (its timeout kills the sim mid write).
- bbtrace.log rotates to bbtrace.1.log past `[trace] max_mb`; readers of a whole run read both files.
- Hosted sandbox: hosting/run-game.sh gives ALSA's null device; never drop that line (menu music busy loop).
- Version strings: never hand edit one; they come from `git describe`. A dirty tree ships as `-dirty`.
- Build outputs (dll, exe, zip, pdb, lib) never go inside the repo tree. build_release.sh refuses an OUT in the repo.

## 10. Never touch
- The live install `~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98` and any game file (*.ASN *.PYR *.PYF *.DAT *.VOL
  *.dll *.exe), saves, templates, snapshots. Work copy: /mnt/nvme/bbpro98/work_install (a lane may be using it).
- Another lane's worktree or running game. Other worktrees are under .claude/worktrees/; stay in your own.
- /mnt/nvme/bbpro98/index (decompile dumps), Sierra patch notes, third party tools. None are committed.
- Secrets: the Hive key file, hosting PIN and secret files (~/.config/bbpro98/), Cloudflare tokens. Never print, copy
  or commit them. news/hive.py is the only repo code allowed to make a network call.
- Real photos or likenesses (portraits are generated only). Real prefix of the hosted host. `rsync --delete` into any
  game directory or lane work copy.
- Published history: never rewrite tags v1.0.0 to v1.0.2 or force push main.
- tests/holdout/: do not weaken or delete a test to get green. Fix the product or report the conflict.
