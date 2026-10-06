# BBPro98 wide stats: one-shot plan (2026-10-06)

Provenance: Opus planner (read-only, could not write the file) returned a plan that reuses the offsets from the failed patch_widen.py (0x41d0f, 0x5ba22, 0x5cebe, 0x5cf4a). 0x41d0f maps to VA 0x6804290f, inside FUN_680428a0, which is the Hall of Fame data screen layout ("Processing Hall Of Fame Data"), not the Statistics screen. That is the likely reason the earlier patch left the Statistics screen unchanged. Its "verified" claims (STS 149 bytes, 14 u32 loops) are unverified. Treat that plan as a hypothesis list only.

## Rules for the whole run
- Work only on a COPY: /mnt/nvme/bbpro98/work_install (cp -a of the pristine backup /mnt/nvme/bbpro98_backups/BBPRO_98_2006-end_2026-10-06, run via a copy of bb_launch99.sh pointed at it). Live install is touched only at M6 after everything is verified.
- Every milestone is accepted only by a screenshot Claude reads itself. No agent self-reports. Every patch has a positive control (a visible change that proves the patch is the cause).
- Patch script: python, asserts original bytes, idempotent, has revert. One script per milestone, stored in /home/will/bbpro98/work/patches/.
- progress.md in /home/will/bbpro98/work/ records current milestone, last verified screenshot, decisions.
- Only interrupt the user for: money, external send, destructive action on the live install, a login only they can do.

## M0 Find the real Statistics screen (Claude, no builders)
Index: /mnt/nvme/bbpro98/index/BBShell/_all.c, _functions.tsv. Known siblings: FUN_680428a0 (Hall of Fame data), a "Processing Old Statistics" variant near _all.c line 47977, title strings "Batting/Fielding Statistics" (line 9588) and "Pitching Statistics" (line 9591). Steps:
1. grep the callers of the functions that reference those title strings and the "Processing ..." strings; list every layout function that uses the 0x32 pitch (grep "0x32" near column arrays at +0x148).
2. Instrument, do not guess: in the work copy, patch ONLY the 0x32 immediate of one candidate to 0x10 (positive control), launch, open League Management > Association > Statistics (clicks in the rig notes), screenshot. The candidate whose patch visibly squeezes the Statistics columns is the real layout function. Repeat per candidate until one matches. Revert between candidates.
3. Output: NOTES section with the real function address, how column count (8) is determined, and the 8-slot loop.
Go/no-go G0: found and positive control visible within 8 candidates. If not found, jump to Fallback F.

## M1 Narrow columns (proves pitch is the lever)
Patch the real function's pitch 50 -> 40. Accept: screenshot shows the 8 columns visibly narrower, labels still legible, no crash. Rollback: revert script.

## M2 More columns on screen, existing stat set
Raise the displayed count in the real grid from 8 to 12 (column loop count and the per-column ctrl array, which holds obj+0x148 + 4*n; check the array capacity in the constructor, and what fills slots 9..12). Initially fill extra slots with ids already in the id table (OBP, SLG, Production, ISO) via a patched default. Accept: 12 columns visible with correct headings, values plausible against bbstats.py output for the same player (spot check 3 players), pitching view also correct. If the control array or id table cannot hold more than 8 without overflow (id table stride 0x80, ids region 0x50 B at 0x6808c2e8), extend by relocating or by redirecting the extra 4 slots to a new data block placed in a code cave. Go/no-go G2: if relocation needs more than 2 builder rounds failing, use Fallback F.

## M3 Change Columns dialog + .STS round trip
Make the dialog expose 12 slots and persist them. STS is currently 117 bytes (u32 ver, 33 B name, 2 x [3, 9 ids]); the new format needs 12 ids per block. Accept: change slot 10 in the dialog, save, reopen game, the choice persists and displays; old 117 byte STS files still load (or are converted by the patch script). Positive control: the saved STS differs by the expected bytes.

## M4 Wider panel / art
Only if screenshots after M2 show the dead space is insufficient. Try, in order: (a) use unused space in the existing 640x480 art (the user said there is plenty of space); (b) larger canvas only for the Statistics screen. Do not repeat the global window size patch (proven to break all screens).

## M5 Regression
Open: main menu, Lineup, Draft, Standings, Career data, Hall of Fame; play one sim day; check bbtrace.log for crashes or error dialogs. Compare against pristine screenshots.

## M6 Ship
Copy patched DLL(s) + STS to the live install (~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98) with a revert script that restores from the backup; append notes to NOTES_stats_format.md; update memory file project_bbpro98_modding.md.

## Fallback F (pre-decided, no user question)
F9 overlay window reading Stats/mlbpa97.DAT via work/bbstats.py: AVG, OBP, SLG, OPS, ISO, K, BB plus OPS+, wOBA, FIP, WAR. Built by GLM-Flash against bbstats.py, tested by screenshot. Triggered at G0 or G2 failure.

## Tier assignment
Claude: M0, all RE, gates, screenshot reading. GLM-Flash (Hive): patch scripts, STS converter, overlay code, from self-contained task files with pasted source. Sonnet: running the screenshot click sequences and regression. No Kimi, no Opus unless a gate asks and the user allows it.

## Optional indexing
Skip bulk GLM labeling for now: M0 is targeted grep plus control patches. Label functions only if M2 stalls on understanding a specific function (then chunk _all.c around the call graph of that function, not the whole 2.7 MB).
