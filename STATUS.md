# bbpro98 status, 2026-10-14

Verified against origin/main on 2026-10-15 01:3x CT (the night of the 14th). Anything not checked this session is
marked "(unverified)". Builders: read this, then AGENTS.md.

## What is live

- Source: origin/main is `a7a6177` (2026-10-15 09:34 CT, "Merge fix/aging-retire-curve"), re-checked 12:55 CT.
  `git describe` says `v1.0.2-180-ga7a6177`: main is 180 commits past the v1.0.2 tag. Releases and the gate's 302
  below were re-checked at the same time and are unchanged.
- Releases (`gh release list`, read only): v1.0.2 (created 2026-10-13), v1.0.1 (2026-10-12) and v1.0.0 (2026-10-12)
  are ALL still drafts. Nothing has been published. Tags v1.0.0, v1.0.1, v1.0.2 exist. v1.0.2 has one asset,
  `bbfix-v1.0.2.zip` (886,262 bytes, 0 downloads), holding README.txt, SHA256SUMS.txt, bbfix.dll, bbfix.ini.sample,
  bblaunch.exe and mods/{aging,modmenu,playercard,rookies,steal}.dll. It does not contain champtext.dll (that mod
  landed after the tag).
- v1.0.3: only a notes draft exists (release/NOTES-v1.0.3.md). It adds champtext.dll and the trace rotation.
  Not tagged.
- Hosted game: https://bbpro98.ecbtx.com answers `302 -> /gate/login?next=/` to an unauthenticated GET, so the
  tunnel, nginx and the PIN gate are up. What the r730 host is running (which commit, which units, bridge state)
  is (unverified): no ssh was used. Last deploy per project notes was 2026-10-14 (champtext on the host,
  bbfix.ini backup `bbfix.ini.bak-20261014`) (unverified).
- Local live install (`~/.bbpro98_prefix/.../BBPRO_98`): the project notes say it carries bbfix.dll with
  playercard, aging, modmenu, rookies and champtext (unverified, not read this session). A game process
  (bblaunch.exe) is running on this machine right now, not started by this lane.
- Rollover is proven in the harness (2026 and 2027 on a 30-team league, per the 2026-10-14 night notes). The
  postseason bracket reader (gamedata.postseason, ASN `po` member) is merged. Both are from project notes
  and merge messages, not re-run here (unverified).

## What is in flight (branches with commits not yet in main, 2026-10-15 01:3x CT)

| Branch | Ahead | Latest commit |
|---|---|---|
| w4-seasonchamp | 3 | seasonloop: champion() reads the bracket inside its own guard |
| w4-champions | 3 | server: champions row for a current file with no season year reads 'Current season' |
| w4-runreport | 2 | runreport: a line counts only when it starts with '{' |
| w4-demogweb | 2 | watch: league() treats a torn PYR like a missing one |
| w3-champpage | 1 | news: postseason page per season, from the po bracket |
| w3-postrecap | 1 | recaps: postseason games get stories, matched to the po bracket |

About 50 worktrees exist under `.claude/worktrees/` (lane/*, n3-*, n10-*, w2-* to w5-*, modbridge, modmenu). Most
are merged and idle. Other lanes edit and merge into main continuously; do not assume main is where you left it,
fetch and rebase before you finish.

## Known broken or risky

- Full pytest run (`news work hosting re/formats tests/holdout`, `-n 2`) has one standing error on main:
  `re/formats/test_roundtrip.py::test_pyr_roundtrip` is a script, not a pytest test (fixture `pyr_path` not found).
  1839 passed, 1 xfailed otherwise (2026-10-15 12:43 CT, branch before its rebase onto `a7a6177`).

- Release checksums: `tools/build_release.sh` writes SHA256SUMS.txt into the folder it is scanning, so the file
  lists itself with a hash that can never match. `sha256sum -c SHA256SUMS.txt` on the unpacked v1.0.2 zip fails on
  exactly that one line (every other file checks out). Pinned by a strict xfail in tests/holdout. Fix: exclude
  SHA256SUMS.txt from the `find`, or write it to a temp name and `mv`.
- `tools/build_release.sh` runs `mkdir -p "$out"` before it refuses an OUT inside the repo, so a refused run still
  leaves an empty folder there. Cosmetic.
- No lint or typecheck config. `ruff check --select F,E9` over the Python folders reports 39 errors on main.
- The full test suite is slow to start on this machine because other lanes hold the shared pytest lock.
- Open from earlier notes, not re-checked: league expansion (work/lahman/expand.py) is CLI only, with no in-game UI
  (unverified).

## Awaits Will

- Publish the three draft releases (v1.0.0, v1.0.1, v1.0.2) by hand, or delete the older two. v1.0.3 notes say they
  add to v1.0.2's text if both go out together.
- Decide when to tag v1.0.3 (champtext.dll plus trace rotation are only in main).
- Review and merge the lane branches above (the orchestrator merges; they are not blocked on Will).

## Superseded

- README.md still says "Status" in terms of the 10/6 wide Statistics screen; it predates the mods, the news
  sidecar and hosting. HANDOFF.md is history up to 2026-10-12, not current state. This file is current state.
