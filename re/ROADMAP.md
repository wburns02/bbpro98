# Full-unlock roadmap (2026-10-07)

Goal: any change to the game: every data file and asset readable AND writable, and arbitrary game logic patchable.
Supersedes the status column of `re/formats/STATUS.md` (2026-10-06, stale). Method for every item: a GLM-5.3-Flash
lane loop (`re/targets/drive.sh <target> <lane>`) scored by a Claude-written mechanical referee, Haiku audit, Claude
final verification. Fable/Opus only when a lane stalls 2-3 rounds.

## Done
| Item | Read | Write | Where |
|---|---|---|---|
| PYR rosters/ratings | yes | yes, byte round-trip | BBPRO98_package/research/pyr_io.py |
| mlbpa97.DAT season/career stat lines | yes, screen-verified | no | work/lib.py, work/bbstats.py |
| MLBPA97.H?? per-game box scores | yes, 1.0000 incl. holdout | trivial (plaintext tables) | re/hfiles/lanes/data/hdecode.py |
| ASN news pool | yes | no | RE_FINDINGS.md |
| SOUND.DAT (227 WAV clips) | yes | yes, byte round-trip + resize | work/sounddat.py |
| `00 01 06 07` chunk container: SIM.DAT, Stadia/*.DAT/*.DT (57 files) | yes | yes, 57/57 byte round-trip + resize/delete | work/chunkdat.py |
| Raw chunk images (340 chunks, 25.8 MB: stadium stands PB/RC, field AF/GF) + PAL: palettes | yes, rendered | yes (38-byte header + w*h indices) | RE_FINDINGS 2026-10-07 |
| File cipher, any seed (PYR, ASN, H-file 2698-byte table) | yes | yes | work/fpscipher.py; algorithm re/targets/cipher/lanes/data/CIPHER.md (GLM data lane, round 2; 82/82 + 36/36 holdout) |
| VOL archives (SHELL, SHELL1, SHELL2: 83 entries) | yes | yes, byte round-trip + add/resize | work/volcodec.py; format re/targets/vol/lanes/code/FORMAT.md (GLM code lane, round 1) |
| c-tree Plus superfiles: ASN, eos, Stats DAT, SCHEDTMP.DAT (records + B-tree indexes) | yes | yes: rewrite (incl. grow), add, delete with index + free-space upkeep; 8/8 files + 4 holdout saves | work/ctree.py; format re/targets/ctree/lanes/data/FORMAT.md (GLM data lane, round 2) |
| Compressed chunk graphics: SCR: screens (6), multi-frame sprites (60), FNT: fonts (5); 'crush' LZ | yes, eyeballed | yes, byte round-trip + edit, all 71 | work/chunkgfx.py; format re/targets/chunkgfx/lanes/data/FORMAT.md (GLM data lane, round 3) |
| Shell BMX (MENUBRS, STADIA) + FNX fonts (0-5) | yes, eyeballed | yes, byte round-trip + edit | work/shellgfx.py (GLM data lane, round 1) |
| Shell PCX (59, inside the VOLs) + PLX palettes | yes: standard 8-bit PCX, no embedded palette (BB0.PAL); MU0/MU1.PLX = raw 768-byte RGB | standard tools | none needed |
| PlayBalance (872 sim knobs) | yes | via PB.INI overlay, effect verified (SB 8.9x) | re/pb_params.tsv |
| Standard media: BMP, WAV, AVI (Cinepak), TTF, ICO | standard tools | standard tools | none needed |

## Open, by wave
| # | Item | Gap | Referee (mechanical) | Size |
|---|---|---|---|---|
| 1 | DBM sprite/animation archives (ARCDBM x3 LOD, BPIDBM, NUMDBM x3, OVERDBM, NOVDBM, GAMEDBM, DMP) | "crushed" bitmaps, codec unknown | targets/imgref.py: decode, byte round-trip, edit survives, pixel-art stats, Haiku vision | L, RUNNING |
| 2 | ASN main payload (teams, divisions, standings, schedule, results) | c-tree superfile, names enciphered (f5dc); member layouts (a, l, d, t, r, s, xs) unknown; needs #2a | day-to-day snapshot diffs (asnseq) must match the decoded box scores (W/L, runs) + round-trip | M |
| 3 | mlbpa97.DAT writer | falls out of #2a | round-trip + edit a stat, re-read with lib.load | S |
| 5a | VOL DAT entries (18: AGEPLYR, ASNEW, ASNEWS, ASSERTXT, BOXTEXT, MENU, PGEND, PGENFRST, PGENLAST, ...) | layouts unknown (some plain text) | per-file round-trip + game-visible edit | S-M |
| 6 | UI layout: DIAL.REQ, MENU.REQ (screens, gadgets, columns) | format unknown (block 13 = stats-grid rows known) | round-trip + edit (move a gadget) + Wine screenshot diff | L |
| 4 | H-file 2698-byte first table semantics (now plaintext: league, team names, stadium codes, ...) | field layout | diff across sim days vs ASN/box-score truth | S |
| 7a | Chunk semantics: HS ('DAT:' tables, 28 stadia), MI/STA: stadium info, GID:, @C, UN, MS; HMI MIDI music (HMIMIDIP, 13 chunks: standard HMP, convert with hmp2mid) | layouts unknown | per-chunk round-trip + game-visible edit | S-M |
| 8 | SIM.DAT chunk semantics, INJURY.DAT, pgen*.dat, HHA.DAT, bb.cfg, .apc/.pyc/.pyf, ARC, hilights .tap, STS writer | unknown or reader-only | per-format: round-trip + cross-check against decoded ASN/H/DAT truth | S-M each |
| 9 | Code hook framework | bbfix.dll injects + logs only; no detours | a hook replaces one known function (e.g. steal chance) and the season stat shifts as predicted vs a null arm | L (Claude/Sonnet design) |
| 10 | Function labels (M1-M3), sim formulas (M9-M11), RNG + seed (M12) | ~1350/3800 P1 labelled; RNG not located | xref consistency; formula predicts logged pitch outcomes; seeded replay is deterministic | L |
| 11 | Automated in-game test harness | partial (probe_screen.sh, simdays.py) | itself the referee for 6 and 9 | M |

Order: wave 1 = #1 (running 2026-10-07; VOL, cipher, c-tree, shell BMX/FNX, chunk graphics done). Next: #2 + #3 (now unblocked), #4. Wave 2 = #2, #3, #5, #7 (independent, one target each, 1-2 lanes). Wave 3 = #6, #8, #9,
#10, #11 (#9 and #11 unlock arbitrary logic changes; #6 unlocks arbitrary screen changes).

## Budget per target
GLM-5.3-Flash via Hive for all lane rounds (cents per round, cap 8 rounds/lane), Haiku for audits (~$0.01-0.05
each), Claude for the referee (once per target) and the final check. No pay-per-token Anthropic API.
