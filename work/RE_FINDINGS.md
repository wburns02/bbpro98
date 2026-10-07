# RE findings (running log, tiers 1-3)

## 2026-10-06 M0 measured (replaces plan section 1 estimates)
Functions / decompiled KB per binary (from /mnt/nvme/bbpro98/index/*/_functions.tsv, _all.c):
BBShell 3728/2696, BBSIM 3763/2456, FastSim 2974/2100, EZShell 1862/1028, LineUp 1659/972, Upstats 1633/1012,
FPS_CT 313/416, ODASL 170/140, Baseball 118/80, IC_Cfg 97/76, FPS_Ctrl 89/60, FPS_DCL 56/76, FPS_Pal 20/12, BBCfg 20/20.
Total about 16,500 functions, about 11 MB. The plan estimated 7,200-9,500 and 5 MB. Plan listed 16 binaries; the Ghidra
project has 14 (no RemotMgr.exe, Datain.exe). Raw: ~/bbpro98/work/M0_metrics.txt.

## Structural findings
- BBSIM.dll and FastSim.dll both statically link MFC (FID_conflict, CString, OnClose, IsTracking, ...). Large noise share.
- Assert strings expose original source filenames. BBSIM: BBSim_{Runner,Earnedr,Sync,Throw,Dbm,Act,Cams,Event,Roster,Tag,Vcr,
  Cover,Field,Status,Ball,Injury,Player,Smodel,Realism,Umpire,Game,...}.cpp. FastSim has the same modules as FastSim_F*.cpp
  (FRUNNER, FEARNEDR, FSYNC, FTHROW, FDBM, FACT, FEVENT, FROSTER, FTAG, FCAMS, FCOVER, FFIELD, FBALL, FINJURY, FSMODEL,...).
  So FastSim = the sim modules without animation/graphics; BBSIM = same plus 3D (TSpace_*.cpp, Graphics_*.cpp, Utility_*.cpp).
  Read FastSim for pure logic, use BBSIM as a cross-check twin.
- Assert call is FUN_680aa8f9(file,line,msg) in BBSIM. Source-file attribution script: /mnt/nvme/bbpro98/re/srcmap.py.
- The game has built-in debug logging switched by ini section [Debug]: DrawPitchPath, InjuryLog, PitchResultLog (writes
  pitchres_log), PitchSelLog, PitchVisible. Free ground truth for Tier 3. Not yet tried.
- Baseball.exe is only 118 functions (launcher). The sim lives in BBSIM/FastSim.
- INJURY.DAT is loaded by BBSim_Injury.cpp (data file not previously listed).

## PlayBalance table (Tier 3 anchor, found 2026-10-06)
- BBSIM FUN_68039455 = PB_LoadIni: reads 0x368 (872) int params from [PlayBalance] in PB.INI (next to the exe, not shipped) via
  GetPrivateProfileIntA into global table DAT_680bc2d0 (defaults baked in the DLL data). Names: pointer array 0x680bb530.
- BBSIM FUN_6803954f = PB_DumpToFile: writes all current values to pb.txt (the game can dump its own tuning table).
- BBSIM FUN_68002cd0 = PB_Get(idx): returns table[idx]. 72 callers pass constant indexes, covering 871 of 872 params.
- Sierra documented 831 params in PBINI.TXT (90 KB, with entry types: base value, percent modifier, adjustment, dice
  Count/Faces/Base, weights, dividers). 41 params are undocumented. 405 documented defaults differ from the DLL defaults:
  trust the DLL (pb_table_BBSIM.tsv col dll_default), not the doc.
- So a PB.INI file is an official, supported way to change sim behavior with no hooks. Not yet tried.
- Sim decision core = ~71 functions (work/sim_core_bbsim.tsv, sorted by param count). Largest: 68056fbc relief/pinch-hit
  logic (112 params, BBSim_Roster), 6803a479 and 6803c8f5 (pitch speed/selection, BBSim_Players2), 6801f976 fielder positioning,
  68065947 steal chance, 6800b2fd baserunner lead logic, 6802c303 catch chance, 68065fba hit-and-run, 680583cb pinch runner.
- Files: re/pbtable.py builds pb_table_<bin>.tsv. FastSim table addresses not yet derived (needs name-array and table addresses).

## Built-in debug logs WORK (verified 2026-10-06, work copy)
- Needs BBPRO.INI: [Sim] Fast=0 (BBSIM engine; FastSim never applies the log flags, its FUN_680621e0 has no callers) and
  [Debug] DebugEnabled=1 plus RandomLog/HitLog/PitchResultLog/PitchSelLog/EventLog/InjuryLog/SubsLog/PlaySetupLog=1.
  Gate is BBSIM FUN_6807cb44 (applies the flags), called only when DebugEnabled != 0.
- One simulated day (15 games, April 4 1997) wrote to the game dir: pitchres.log (u32 counts, raw table behind prlog.txt),
  prlog.txt (pitch outcome by ball-strike count: balls/swinging strikes/called strikes/fouls/in play, counts and percentages),
  sub.log (substitution decisions with "Chance = N" values), hit.log (88 KB, mostly zero bytes, 1195 records), game.txt
  (per-game stadium, weather). hilights/ gets files. Saved copies: /mnt/nvme/bbpro98/re/debuglogs/.
- No random/event/injury log files appeared yet (maybe none triggered, or different path). Open item.
- Use for Tier 3 validation: prlog.txt gives real pitch-outcome distributions per count for chi-square checks.
- Caution: Fast=0 sims are slower; the work INI is now Fast=0 with debug on (original: re/BBPRO.INI.orig).

## GLM labeling pilot (Baseball.exe, 99 residue functions, 3 batches, 0 failures)
Output looks plausible and cites strings/callees. Needs the audit gate (spot check 100 across binaries) before trusting.

## Tier 3 spec draft audit log (2026-10-06)
- FUN_6802baf7 (FastSim_FINJURY init): audited by Claude against decompile. Open/read sizes (0x2c, 0x26), 19 PB indices 0x354..0x366 written as u16 at DAT_68113b88+0..0x24, discard of file-read table B: all correct. Grade CONFIRMED. GLM draft accuracy on init-style functions is good; formula-heavy functions still need audit.
- Spec drafts: re/spec/FUN_*.md (68 of 69; one repeatedly fails, likely the largest). Hive streams can hang: label_glm.py ex.map blocks on a hung batch; kill and use label_escalate.py.

## Label audit gate, FastSim (2026-10-06, Claude read 40 of 2353 against the decompile)
- Accuracy: 38/40 acceptable, 2 wrong or unsupported (680371f8 mislabeled UI_MAIN splitter, it is a PB-driven sim function; 68008e05 cites an MFC FID collision). ~5% wrong, at the limit.
- Evidence mix from GLM residue: XREF_CONFIDENT 46%, STRING_XREF 12%, PATTERN_GUESS 38%, UNKNOWN 4%. Below the 80% target as a distribution, so the gate was applied by policy instead: only XREF_CONFIDENT and STRING_XREF names are written to Ghidra; PATTERN_GUESS and UNKNOWN never are.
- Noise filter: labels whose support cites IsTracking, _AFX_*, CSplitterWnd, CControlBar (Ghidra FID collisions) are dropped (22 in FastSim).
- Applied via gh.sh batch: Baseball 94, FastSim 1255 renames (re/rename_spec_Baseball_FastSim.py). Verified by decomp readback. Renamed names are SUBSYS_short_name; treat as XREF_CONFIDENT at best, not CONFIRMED.
- Hive streams can hang; label_glm.py then stalls on ex.map. Fix used: kill it, run label_escalate.py (split 10, then DeepSeek-Flash).

- Audit (Claude vs decompile): FUN_68050eb0 (FRUNNRS2 init): the 20 PB->global writes (0x68097608..0x68097654, indices 0x2bc..0x2cf) CONFIRMED exactly; the draft's "MFC property sheet" narrative is a Ghidra FID false match (EnableStackedTabs) and is WRONG as semantics. FUN_6800a7ad: 48 PB->global copies (0x6808cef8..0x6808cfb4) CONFIRMED, numbers.inf load plus 0x1f..0x10 byte fill CONFIRMED.
- Key structural finding: many of the 69 PB-reading FastSim functions are INIT LOADERS (copy PB into plain globals). The decision logic lives in functions that read those globals by data xref, not by getter call. Spec must follow the data xrefs from the globals (e.g. 0x6808cef8 look/discipline/checkChance block, 0x68097608 bat zone block) to find the real consumers. Direct readers (e.g. BBSIM 68056fbc relief logic, 112 params) are the exception and read PB at decision time.
- Rule for drafts: trust tables (addresses, indices, defaults), distrust narrative semantics that cite MFC classes.

## PB.INI experiment (2026-10-06)
- Placed PB.INI with [PlayBalance] phForPitcherBase=77 and stealChance00Count=-999 next to the work exe (C:\Sierra\BBPRO_98_work\PB.INI), ran under WINEDEBUG=+profile, simulated one day via the UI.
- CONFIRMED (Wine +profile trace): the game opens that exact file at runtime and reads all [PlayBalance] keys by name; PROFILE_Load shows phForPitcherBase=77 and stealChance00Count=-999 parsed. So PB.INI is a working, supported behavior-tuning path with no hooks.
- NOT confirmed: the downstream effect on sim outcomes. sub.log and prlog.txt append across runs and the sim is not seeded identically, so a one-day before/after compare is noise. Needs a controlled design (same saved state, many days, compare aggregate rates) before claiming an effect size.
- PB_DumpToFile (pb.txt) is wired to dialog button 0xbfa in the in-game debug options dialog (FUN_6807c3fc), not run automatically.
- Test file kept at re/PB.INI.test; removed from the work copy.

## ASN payload probe (2026-10-06, Claude)
- No plaintext, additive-shift or XOR-encoded (all 255 constants) occurrences of Astros/Yankees/Houston/Red Sox in MLBPA97.ASN. Team and player names are not stored as strings in the ASN; payloads are numeric ids and small-int fields (team record 0 payload starts 01 1d 1d 1d a6 01 ...). Names likely live in PYR or other files and are joined by id. ASN stays PARTIAL: container + framing verified, field semantics unknown.
- Renames applied and readback-verified: IC_Cfg (66), FPS_CT (217, c-tree engine: IO_FILE_* / IO_REGISTRY_* names).
- LineUp: 761 renames applied (518 grade + 31 name collisions); sample audit of 3 read against decompile: all consistent (lineup role lookup, click match, scrollbar setup).
- Upstats: 817 renames applied; 3-function sample read, consistent (ctree close chain, record write, read wrapper).
- EZShell: 924 renames applied; 3-function sample read, consistent (scalar deleting destructor, child notify loop, SEH cleanup stub).
- BBShell: 1703 renames applied; 3-function sample read: one clear (simple select dialog setup), two are generic SEH/dtor thunks whose names are guesses (low value).

## PB.INI controlled experiment (2026-10-07, GLM-Flash session)
- Rig: work copy configured EXACTLY like live (Fast=1, no [Debug] section, no weather.dat; debug-logged Fast=0 config crashes at BBShell FUN_68054f70 NULL-getter after weather.dat open fail; the sim's paint stalls on "Updating association data" until a click). Sim-day chain: League Mgmt (495,677 x2) > Association (440,329) > Schedule (445,395) > Action (593,330) > Simulate... (616,346) > Today's games only (543,486) > OK (571,565). Driver: re/simdays.py.
- State: live install's April-2 1997 association copied into work (pristine base; live was left there by the 10/6 regression run). Work Stats had 63 stale MLBPA97.Hxx highlight files that live lacks; they must be deleted to match.
- Validation: [PlayBalance] stealChance00Count=100 (default -10, idx 54, reader FUN_68065947). 10 sim days per arm from identical state. Trace confirms PB.INI key load; 76k runtime PB reads observed.
- Result: SB 240 -> 2148 (8.9x), CS 20 -> 230 (11.5x); AB within 0.7%; R +23%, RBI +21% (second-order), GIDP -34%. Effect size ~50x the observed AB noise, so seed variance cannot explain it. VALIDATED: the PB knob reaches sim behavior end to end.
- Batting stat columns (from NOTES_stats_format.md): c0 AB, c1-4 H splits, c5 RBI, c6 BB, c7 SO, c8 IBB, c9 HBP, c12 G, c13 R, c14 SB, c15 CS, c16 GIDP.
- Open: seed differs between arms (no seed control) - fine for large effects; for <20% effects, run a second baseline arm for the null distribution.

## GLM-Flash spec audits (2026-10-07, in progress)
- re/audit_spec.py sends each of 73 drafts + its decompile slice to GLM-Flash; verdicts in re/spec_audit/*.txt.
- Calibration: verdict claims of "wrong index/param count/constant" are checkable and the two sampled (FUN_68036e91, FUN_6802baf7 param count) verified TRUE. Claims of "invented PB names/defaults" are FALSE POSITIVES when the names+defaults match pb_table_FastSim.tsv (the audit sees only the decompile, where PB reads are opaque getter calls; e.g. 6802baf7's injuryChance table 0x354-0x366 matches the INI table exactly).
- FUN_68036e91 draft had real fabrications (index 25 vs real 0xe..0x17, params=10 vs 1); CORRECTION header added, mapping verified: pitchOutChance* indices 14..23.

## PB.INI null distribution (2026-10-07, armA2)
- Second baseline arm (armA2, same state, 10 sim days, own seed) vs armA. Null spread (A vs A2): AB 16036/16516 (3.0%), R 1398/1646 (17.7%), SB 240/228 (5%), CS 20/4, SO 3602/3558 (1.2%), BB 1102/1084, HR 424/520 (20%).
- Treatment armB vs null mean: SB 2148 vs ~234 mean = +1914, about 160x the SB null spread. CS 230 vs ~12. The stealChance00Count validation stands; seed variance cannot touch it.
- Noise floor for this rig at 10 days: R and HR swing ~20% between identical-config arms, AB/SO/BB ~1-3%. Any future single-knob validation must predict an effect larger than the relevant null spread, or run longer/multi-seed arms. Second-order effects of the steal knob (AB -0.7%, SO -3%) are within noise.
- Ops: a stale armA "Wine Debugger"/"Program Error" dialog pair left on :99 stole focus and broke a sim day (day-5 done=False while the sim actually completed); kill stale wine dialogs by exact pid before arms, and focus the Baseball window (xdotool windowfocus) before click chains.
- re/simdays.py: SKIP_MENU=1 env resumes the day loop directly from the schedule screen.

## ASN per-day sequence decode (2026-10-07)
- Method: 10 sim days from one pristine state, ASN snapshot per day (re/asnseq/day01..10, re/asnseq_drive.sh). Analyzer re/asndiff2.py: churn regions + constant-delta u16 fields.
- Date fields: 13 u16 sites increment by exactly +1 per sim day (12238..12247, i.e. 0x2FCE..0x2FD7: low byte = day counter 0xCE..0xD7, high byte 0x2F constant), and 11 u16 sites hold the same counter shifted (0xCE00, 0xCF00, ..). These are sim-date stamps scattered across record structures. Offsets in re/asnseq/analysis.tsv.
- Tail history log: last 32KB before EOF (0x298000..0x2A0000) is an append-style results log. Each sim day writes at record starts ending in 0x1a (0x29801a, 0x29821a, 0x29861a, .. advancing by 0x200-sector steps), 66B..1KB+ per day (matches variable game counts), 9.7KB over 10 days, wraps inside the 32KB window.
- 0x7e00..0x9500: NOT a ring. Fixed-site daily aggregates (0x7e2b, 0x7e46, 0x7e8a, 0x7f63.. change every day; some intermittently). Intermittent sites are player/stat rows that MOVE when stats reorder, which produced the rotation-like signatures in the 3-arm diff. Date field interpretation: value = (era<<8)|day (0x2FCE = era 47, day 206 of era).
- ~~Names are NOT in the ASN (10/6 probe)~~ WRONG, see 2026-10-07 correction below: names are stored, enciphered with the f5dc substitution table.

## ASN tail region = Association News pool (2026-10-07, box-score-anchored)
- The 0x27E000..0x29A800 tail (wider than the old 0x298000..0x2A0000 window) is a chain of 512-byte news blocks. Each block: 29-byte header (bytes 2-3 = u16 LE chain pointer to the previous day's block, verified 0x29A200->0x27E600->0x27E400), then 25-byte news records at +0x15+25k (k=0..18; k=0 is a head record: `00 12` + chain ptr), then a slot-array tail that false-positives as records. Full decode: re/tail_log_decode.md (builder: GLM-Flash on Hive, id joins verified by me).
- 25-byte record: [0-1]=player id (PYR, verified: 1973=Bob Wagner 2B, 833=Jorge Posada C, 881=Darren Lewis CF, 534=Ray Eibel 2B, 371=Curtis Goodwin CF, 1660=Dave Maas LF, 2276=John Aragon SS, 924=Vizcaino, 1341=Angel Scanlan 2B), [6]=status flag (08=active claim, ff=idle history, 00=head), [7-8]=related player id (NOT team/money; 2276-Aragon rows carry 2176 Sam Wagner, same position), [13]=event id (stable per player-event across saves; 08=free-agent claim), [14-17]=u24 pointer into the Pool-B detailed news store, [21-22]=date (era<<8)|day, [23]=0x0B constant, [24]=00.
- April 11 ground truth: the 14 identical `08` rows for player 1973 are the "submitted claim for free agent 2B Bob Wagner" pile-on (one per claiming team's copy; team ids are not in these records - they live in the Pool-B text store). Awarded items = different byte-6/13 combo, not in this save pair.
- Second news store: 39-byte records (`fa fa 27` magic) at 0x30000..0x6D500, stride 39, with 3-byte back-pointers (verified: backptr = rec-39) and an embedded 25-byte news entry; ~749 on day10. Pointers decoded only.
- Game results (box scores) are NOT in the news pool. Candidate: 34-byte `fa fa 22` lineup records in 0x30000..0x6D500 (28 of them; 0x31613..0x31A00 changed on the April 11 sim). Decoding those is the next anchoring step for per-game stats.
- Date base: era 47 day 206 = April 3, day 214 = April 11 (203 = Mar 31 opener); news is written one day ahead of the save's sim date (day10 file already holds 0x2FD7/April 12 items).

## Claude spot-check of the GLM run (2026-10-07 afternoon)
- PB.INI steal A/B: reproduced exactly from raw Stats DAT with work/lib.py (scope 1 SB 240/228 stock vs 2148 treated; CS 20/4 vs 230). Wine +profile logs: armB loaded only stealChance00Count=100; armA/armA2 had no [PlayBalance] section. Prior-season scope 3 identical across arms (same start state). VALID.
- Hand-fixed defects: 680371f8 max-stackable 145 verified against pb_table defaults and the decompile (PH and CH blocks use the same rating diff, getters read twice). 6804684c rows 348-351 verified. 68023dd3 e98c gap verified (body correct; the history bullet misquotes e988 as 0x1f9, it is 0x1f7).
- WRONG fix found: 6800cccc_consumer's PB attribution had been removed because its globals are not the PB table base. They are PB-cached globals: FUN_6800a7ad copies PB[0x217..0x22e] into 0x6808cef8..0x6808cf54. Restored. Lesson: before denying PB attribution for a global, check the PB cache map (84 globals, 0x6808cef8..0x6808e9d8, every `_DAT_x = FUN_68003170(idx)` in FastSim _all.c). Only this draft made that denial.

### Remaining spot checks (2026-10-07, Haiku read-only, Claude-verified where noted)
- FUN_6800cccc rule 5 (uninitialized weights): VALID. `int aiStack_24 [8];` (FastSim _all.c:7683) is never memset; the sumA==sumB==0 branch writes only `aiStack_24[local_58] = 1` (7721-7722); the total and RNG-walk loops read all 8 entries (7741, 7749). Claude confirmed the quoted lines.
- FUN_68054d4a spec: VALID on every rule Haiku checked. Claude confirmed the PB attribution Haiku mislabelled: DAT_68097628/38/48 are filled by a second PB cache-init block, `_DAT_68097628 = FUN_68003170(0x2c4)` .. `_DAT_68097648 = FUN_68003170(0x2cc)` (_all.c:47776-47784), three 4-entry arrays (count/faces/base x swing type). DAT_68185a60 is the FUN_680829dc object, not PB.
- ASN news pool (lines above): flag byte, related-player id, stable event id and (era<<8)|day date VALID against a 10-day dump (re/audit/news_dump.txt, re/audit/dump_news.py). The "c23=0x0B constant" check found 8% exceptions, but the dumper does not exclude the slot-array tail the finding already calls false positives, so not a contradiction. Reports: re/audit/haiku_spot_*.md.

## Per-game box scores (Stats/MLBPA97.Hxx) decoded (2026-10-07)
Solved by the GLM-5.3-Flash "data" lane in round 2 (re/hfiles/lanes/data/hdecode.py, format in HFILE_FORMAT.md there).
The files are NOT encrypted as a whole: they are a chain of tables `02 65 | u16 unk | u16 count | u16 recsize | count*recsize`.
recsize 40 = batting line, 70 = pitching line, same u16 layout as the season lines in mlbpa97.DAT minus the leading
[scope, 2] pair; id field has 0x8000 ORed in for the second side; id < 100 = team-total row. Only the first table
(unk=0xffff, 1 x 2698 bytes) is obfuscated and is not needed for the box score (the 0x31-dominated histogram came from it).
Verified by Claude: referee 1.0000 bat + pit on days 2-7 (1544 batters, 427 pitchers) and on held-out days 8-10
(643 / 176) that the lane never saw; Haiku audit CLEAN; decoder is 3.3 KB with no embedded tables.
Open: the obfuscated 2698-byte first table (likely play-by-play or lineup/game header).

## Correction + new findings (2026-10-07, Claude)
- ASN names ARE stored. The 10/6 probe only tried shift/XOR. All shipped PYR (3) and ASN (3, seed bytes at 0x310) use seed `f5dc` and one identical 256-byte substitution table (recoverable from PYR player ids). Decoding MLBPA97.ASN with it yields the team record "Houston ... Larry Dierker ... HOU ... The Astrodome" at plain offset ~0x5090.
- The table is not affine mod 256 (mods used T(x)=(m*x+c)&255) but has XOR-linear blocks (fwd[4..7] = 82 a6 8a ae). MSVC/Borland rand + Fisher-Yates variants tested: no match. Generator search = target `re/targets/cipher`.
- H-file blob: `02 65 ffff 0100 8a0a` + 2-byte per-file seed + 2696 bytes enciphered with that seed's table (dominant byte = 0x00).
- c-tree Plus family: SCHEDTMP.DAT, Assn/{MLBPA97,_DEFAULT,MLBPA96E}.ASN, Assn/MLBPA97.eos, Stats/{mlbpa97,mlbpa96e,_DEFAULT}.DAT all share header bytes 0x28-0x2f `81 00 00 02 00 00 00 80` and `FA FA` record headers (u32 total, u32 payload_len, u32, u32; payload at +18). Engine = FPS_CT.dll; wrapper = BBSIM `\Fps_ct\Ctree\Ctree.cpp` (OPNFIL host 0x200 + OPNIFIL members). Codec target `re/targets/ctree`.
- SOUND.DAT: u16 count (227) + (count+1) u32 offsets (last = file size) + RIFF WAVs, all mono (164 x 16-bit 22050, 62 x 8-bit 11025, 1 x 8-bit 22050). Read/write: `work/sounddat.py`, round-trip verified.
- volx.py is misaligned (crashes on SHELL2.VOL). Real layout: "VOLM", u32 1, u16 fields, directory name with trailing backslash, u16 count, u32 offset, entries name\0 + u16 + u32; game reader EZShell `Utility\Volume.cpp`. Codec target `re/targets/vol`.
- SIM.DAT and Stadia/*.DAT/*.DT share a `00 01 06 07` tagged-chunk container (tags 'PB', 'MA', 'AB', 'MI').
