# Full-unlock roadmap (2026-10-07)

Goal: any change to the game: every data file and asset readable AND writable, and arbitrary game logic patchable.
Supersedes the status column of `re/formats/STATUS.md` (2026-10-06, stale). Method for every item: a GLM-5.3-Flash
lane loop (`re/targets/drive.sh <target> <lane>`) scored by a Claude-written mechanical referee, Haiku audit, Claude
final verification. Fable/Opus only when a lane stalls 2-3 rounds.

## Done
| Item | Read | Write | Where |
|---|---|---|---|
| PYR rosters/ratings | yes | yes, byte round-trip | BBPRO98_package/research/pyr_io.py |
| mlbpa97.DAT stats DB: every stat record (bat 17, pit 32, fielding 9x8, 20 split tables; scopes recent/season/career/last-season/matchup) | yes, box-score deltas days 1-9 + holdout | yes, in-place by field name; scope/pid via work/ctree.py | work/stats.py (GLM data lane, round 1) |
| MLBPA97.H?? per-game box scores | yes, 1.0000 incl. holdout | trivial (plaintext tables) | re/hfiles/lanes/data/hdecode.py |
| ASN news pool | yes | no | RE_FINDINGS.md |
| SOUND.DAT (227 WAV clips) | yes | yes, byte round-trip + resize | work/sounddat.py |
| `00 01 06 07` chunk container: SIM.DAT, Stadia/*.DAT/*.DT (57 files) | yes | yes, 57/57 byte round-trip + resize/delete | work/chunkdat.py |
| Raw chunk images (340 chunks, 25.8 MB: stadium stands PB/RC, field AF/GF) + PAL: palettes | yes, rendered | yes (38-byte header + w*h indices) | RE_FINDINGS 2026-10-07 |
| File cipher, any seed (PYR, ASN, H-file 2698-byte table) | yes | yes | work/fpscipher.py; algorithm re/targets/cipher/lanes/data/CIPHER.md (GLM data lane, round 2; 82/82 + 36/36 holdout) |
| VOL archives (SHELL, SHELL1, SHELL2: 83 entries) | yes | yes, byte round-trip + add/resize | work/volcodec.py; format re/targets/vol/lanes/code/FORMAT.md (GLM code lane, round 1) |
| c-tree Plus superfiles: ASN, eos, Stats DAT, SCHEDTMP.DAT (records + B-tree indexes) | yes | yes: rewrite (incl. grow), add, delete with index + free-space upkeep; 8/8 files + 4 holdout saves | work/ctree.py; format re/targets/ctree/lanes/data/FORMAT.md (GLM data lane, round 2) |
| Compressed chunk graphics: SCR: screens (6), multi-frame sprites (60), FNT: fonts (5); 'crush' LZ | yes, eyeballed | yes, byte round-trip + edit, all 71 | work/chunkgfx.py; format re/targets/chunkgfx/lanes/data/FORMAT.md (GLM data lane, round 3) |
| League file ASN (teams, names, managers, stadiums, divisions, W/L, rosters, schedule with dates/scores/innings, transactions, playoff, draft) | yes, day-pair diffs vs box scores + holdout day10/s10 | yes, in-place edit | work/league.py (GLM data lane, round 1) |
| DBM sprite archives (ARCDBM x3 LOD, BPIDBM, NUMDBM x3, OVERDBM, NOVDBM, GAMEDBM) | yes, eyeballed (players, overhead views, jersey numerals; some frames are multi-pose strips) | yes, byte round-trip + edit, crush LZ | work/dbmcodec.py (GLM code lane, round 4) |
| Shell BMX (MENUBRS, STADIA) + FNX fonts (0-5) | yes, eyeballed | yes, byte round-trip + edit | work/shellgfx.py (GLM data lane, round 1) |
| Shell PCX (59, inside the VOLs) + PLX palettes | yes: standard 8-bit PCX, no embedded palette (BB0.PAL); MU0/MU1.PLX = raw 768-byte RGB | standard tools | none needed |
| PlayBalance (872 sim knobs) | yes | via PB.INI overlay, effect verified (SB 8.9x) | re/pb_params.tsv |
| Standard media: BMP, WAV, AVI (Cinepak), TTF, ICO | standard tools | standard tools | none needed |
| Code hook framework (mods): detour, register-level midhook, call-site redirect, verified patch; per-module, relocation-safe, all-or-nothing | n/a | yes: a mod DLL listed in bbfix.ini [mods] hooks any BBShell/BBSIM/FastSim/... function; A/B on 8 sim days: steal mod zero SB 2 vs 89 off, max 523 (5.9x), pass 71 | src-latest/bbmod.h (SDK), src-latest/bbfix.c, src-latest/mods/steal.c, src-latest/test/hktest.py, re/hookab.sh + re/hookab_score.py |

## Open, by wave
| # | Item | Gap | Referee (mechanical) | Size |
|---|---|---|---|---|
| 1b | DMP.DAT (10 frames, not DBM layout) | unknown | imgref | S |
| 5a | VOL DAT entries (18: AGEPLYR, ASNEW, ASNEWS, ASSERTXT, BOXTEXT, MENU, PGEND, PGENFRST, PGENLAST, ...) | layouts unknown (some plain text) | per-file round-trip + game-visible edit | S-M |
| 6 | UI layout: DIAL.REQ, MENU.REQ (screens, gadgets, columns) | container + gadget record sizes known (Claude, 114/114); field meanings open. Lanes running: re/targets/req | round-trip + edit (move a gadget) + Wine screenshot diff | L |
| 4 | H-file 2698-byte first table semantics (now plaintext: league, team names, stadium codes, ...) | field layout | diff across sim days vs ASN/box-score truth | S |
| 7a | Chunk semantics (lanes running: re/targets/chunks, 126 chunks + 8 held-out stadiums): HS ('DAT:' tables, 28 stadia), MI/STA: stadium info, GID: fence geometry, WT, XT; SIM.DAT @C cameras, MI injuries, PB strings, UN, MS, OL; HMI MIDI music (HMIMIDIP, 13 chunks: standard HMP, convert with hmp2mid) | layouts unknown | per-chunk round-trip + game-visible edit | S-M |
| 8 | SIM.DAT chunk semantics, INJURY.DAT, pgen*.dat, HHA.DAT, bb.cfg, .apc/.pyc/.pyf, ARC, hilights .tap, STS writer | unknown or reader-only | per-format: round-trip + cross-check against decoded ASN/H/DAT truth | S-M each |
| 10 | Function labels (M1-M3), sim formulas (M9-M11), RNG + seed (M12) | ~1350/3800 P1 labelled; RNG not located | xref consistency; formula predicts logged pitch outcomes; seeded replay is deterministic | L |
| 11 | Automated in-game test harness | partial (probe_screen.sh, simdays.py) | itself the referee for 6 and 9 | M |

Order: wave 1 done 2026-10-07 (DBM, VOL, cipher, c-tree, shell BMX/FNX, chunk graphics). #2 league and #3 stats done 2026-10-07. Now: #4, #1b. Wave 2 = #2, #3, #5, #7 (independent, one target each, 1-2 lanes). Wave 3 = #6, #8, #9,
#10, #11 (#9 and #11 unlock arbitrary logic changes; #6 unlocks arbitrary screen changes).

## Budget per target
GLM-5.3-Flash via Hive for all lane rounds (cents per round, cap 8 rounds/lane), Haiku for audits (~$0.01-0.05
each), Claude for the referee (once per target) and the final check. No pay-per-token Anthropic API.
