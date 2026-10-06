# mlbpa97.DAT (Stats container) - findings 2026-10-06, snapshot s5

Container: 512-byte pages, NOT enciphered. Page 1-2 = table directory (names bsa/bsg/bsh/bsj/bsl/bsm/bsr/bss/bst/bsu, psa..psu, bt/pt/ft/di + .idx).
Record stream (parse_stats.py, valid after filtering): 
  fafa | u32 total | u32 payload_len | u32 recno | u32 logical_off | payload   (total = payload_len + 18)
  Records straddle page boundaries (data pages have no per-page header).
  Scanner yields false positives inside index pages: keep only u16[0] in {0,1,2,3,16,17} and payload_len in {22,36,40,70,150}.
Payload = u16 array: [scope(1/2/3), 2, player_id, ...stats]. scope: 1,2,3 unknown mapping (3 = current-season-like region early in file).
Lengths: 22 = 8 stats (small split row, e.g. pitcher batting AB,H,2B,3B,HR,BB,SO), 36 = 15 stats split row,
  70 = 32-stat full line, 40 = fielding/other, 150 = big table (mostly zeros, ratings/zones?).
Verified relation: Maddux 70-byte line AB 934 == sum of six 36-byte rows (172+171+159+160+166+106) = monthly splits. So 36-byte rows are splits that sum to the 70-byte total.
bbcard (DOS) under dosbox-staging+Xvfb: creates INI, never produces HTML headless (stalls). Not a usable oracle yet.
TODO: map scope ids and split types; map 70-byte columns (AB,H,2B,3B,HR,BB,...); confirm via in-game Statistics screen; then reader + advanced metrics.

## VERIFIED 2026-10-06 (game screen vs file, s5 = end of 2001, 6/6 players exact)
scope 1 = season just completed (2001). scope 2 = career accumulated. scope 3 = TBD (a different split, AB differs from scope 1).
40-byte BATTING line, u[3+i]:
 c0 AB, c1 singles (1B), c2 2B, c3 3B, c4 HR, c5 RBI, c6 BB, c7 SO, c8/c9 = IBB,HBP (order unconfirmed), c10 SH(?), c11 SF(?),
 c12 G, c13 R, c14 SB, c15 CS, c16 GIDP(?).   H = c1+c2+c3+c4 (NOT a stored field).
70-byte PITCHING line shares c0..c15 with the batting layout (opponent batting vs the pitcher); c16.. = pitcher-only fields (TBD).
Display screen: Association > Statistics > Show > Players; columns Avg AB R H HR RBI BB SO.
Rig: ~/bb_launch99.sh launches on :99 with PULSE_SINK=bbnull (silent). Do NOT disable the Wine audio driver (game spins at 70% CPU in an MCI retry loop).
The live install now holds the s5 snapshot (Assn+Stats). Restore s10: cp -a ~/seasons/s10/Assn/. and Stats/. into the install.

70-byte PITCHING line, verified on 4 pitchers (Embree, Glavine, Maddux, Smoltz; 2001):
 c0..c16 as batting (opponent line vs pitcher): c0 AB, c1 1B, c2 2B, c3 3B, c4 HR, c5 RBI, c6 BB, c7 SO, c8/c9 IBB,HBP, c11 SF, c13 R allowed, c14 SB allowed, c15 CS.
 c12 and c16 = G (appearances). c18 = outs recorded (IP = c18/3, shown x.1/x.2). c19 = batters faced. c20 W, c21 L, c22 SV.
 c26 = ER (ERA = 9*ER/IP). c25 = GS or CG (31/35/14/26 for Maddux/Smoltz/Embree/Glavine, unconfirmed). c23 = 0/1 (SHO?).
Season length: pitchers show ~40 G, hitters ~162 G.

WIDEN-PANEL EXPERIMENT 2026-10-06 (reverted, files identical to backup):
- Stat sets: StatSets/*.STS 117 bytes: u32 ver=1, name[33], then two blocks (batting, pitching) each u32 3 + 9 u32 stat ids. 8 visible columns.
- FrontOffice window created in BBShell.dll 0x6803a457 (CreateWindowEx) with push 0x280 (w) / 0x1e0 (h) at 0x6803a43f/0x6803a43a; centering uses 0x140/0xf0 at 0x6803a40d/0x6803a423.
- SuperShell/other EZShell windows take size from fields [obj+0xc0]/[obj+0xc4], set to 0x280/0x1e0 at EZShell 0x6a00594e/0x6a005958 and 0x6a0117e3/0x6a0117ed.
- Patching these to 960x720 enlarges the windows (verified in bbtrace) but art stays 640x480 and the rest is black; window also not centered. Need per-screen layout/art work.

FEASIBILITY SPIKE (full widening), 2026-10-06:
- Stats screen draws no child windows; one custom grid class in BBShell.dll (layout fn 0x680428a0, column pitch imul 0x32 = 50 px at 0x6804290f; column ctrl array at obj+0x148; helpers 0x68040a40, 0x68040b50).
- Column ids live in a global table at 0x6808c2e8, stride 0x80 per stat set: 0x50 bytes of ids (2 blocks of [3, 9 ids]: batting, pitching), name at +0x50 (13 B), name2 at +0x5d (33 B). Save/load = fn near 0x6805d9xx, file = u32 ver + 33 B name + 80 B ids (117 B).
- So 8 stat columns is baked into: id table size, .STS format, Change Columns dialog slot buttons (8 across), grid layout, 640x480 art. Widening needs all five changed together.
- Disassembly dump: work/BBShell.asm (objdump -d -M intel BBShell.dll).

## WIDEN-PANEL M0 RESULT and FALLBACK F (2026-10-06)
- Three positive controls changed nothing on the Statistics screen: BBShell imul 0x32 at 0x6804290f (Hall of Fame layout) and 0x6804f7d3 set to 0x10; _DEFAULT.STS last batting id edited; BBShell .data table 0x6808c2e8 entry 0 last id edited (file off 0x8ad0c, id 0x11 -> 0x30). LineUp.dll also embeds the default id table (0x35428). The active column config for the League Statistics screen is not in any of those; suspect SHELL.VOL resources (VOLM archive, contains MENU.REQ, DIAL.REQ) or Assn state. Ghidra index of BBShell.dll: /mnt/nvme/bbpro98/index/BBShell/ (3727 functions).
- Fallback shipped: /home/will/bbpro98/work/bbwide.py (+ bbwide.sh). Local web page on 127.0.0.1:8099, 24 batting and 21 pitching columns incl. OBP, SLG, OPS, ISO, BB%, K%, BB/K, wOBA, OPS+, oWAR~, WHIP, K/9, BB/9, HR/9, H/9, K/BB, FIP, ERA+, pWAR~. Team total rows (ids below 100) are excluded from rows and league constants. Verified against bbstats.py and by hand (A-Rod 1997 s9 line).
