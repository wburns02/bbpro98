# Data chunks of SIM.DAT and Stadia/*.DAT / *.DT

Codec: `work/simchunks.py` (decode / encode JSON; the layout is picked by the chunk id, the first 4 characters of the
name, e.g. `947d_ANAHEIM.bin`). The containers are work/chunkdat.py; the bitmaps cb7c txfill.dbm and 7709 txmap.dbm
are DBM multi-frame images, work/chunkgfx.py.

Verified 2026-10-07: byte-exact round trip on every data chunk of the 28 stadiums (20 visible + 8 holdout) and
SIM.DAT, and `re/targets/voldatref.py` PASS visible and `--holdout` (target: re/targets/chunks files minus cb7c /
7709). chunkgfx round-trips all 56 texture chunks, holdout included. Layouts come from the BBSIM / FastSim / BBShell
loaders (Claude); the chunks GLM data lane found most record sizes (its FORMAT.md is kept as the lane record).

The container key of a chunk is a hash of its file name (chunkdat.py `name_key`, BBSIM FUN_680b0665); the low u16
is the id used below.

| id | name | where | content |
|----|------|-------|---------|
| 947d | shape.tbl | stadium .DAT | 3D models of the park |
| ce8c | wall.tbl | stadium .DAT | ground polygons and outfield walls |
| e957 | info.dat | stadium .DAT / .DT | stadium info |
| e6e7 | cams.cfg | SIM.DAT | camera views and saved slots |
| e1a4 | injury.dat | SIM.DAT | injuries |
| 6be6 | logic.dat | SIM.DAT | fielding assignments |
| b0e7 | numbers.inf | SIM.DAT | uniform number placement |
| 5200 | bpi.str | SIM.DAT | in-game menu strings |
| bb43 | sndvol.cfg | SIM.DAT | dead (6 u16 nothing reads) |

All integers little-endian. JSON keys starting with `_` are derived or kept only for a byte-exact rebuild.
Fixed strings keep bytes an older, longer value left after the NUL as `_..._tail`.

## Offset-table resources (wall.tbl "GID:", shape.tbl "DAT:")

`XXX:` u32 payload size; payload = u32 offsets (from the payload start) ending with 0, then the records in that
order. BBSIM FUN_680a8926 (GID:) / FUN_680a7e26 (DAT:) turn the offsets into pointers.

### wall.tbl (BBSIM Ts_grnd.cpp)

Record (one per ground): s16 x_extent, s16 y_extent, s16 edge count, s16 polygon count, u16 polygon table offset
(= 10 + 12 * edges), the edges, the polygons.

Edge (12): s8 nx, s8 ny, s16 x, s16 y, s16 wall_height_start, s16 wall_height_end, s16 twin_edge.
(nx, ny) is the outward normal (128 = 1.0): a position is inside a polygon when every edge has
n . (pos - point) <= 0 (FUN_680a82f0 via FUN_680a8364). The JSON stores the inward normal (`inward_normal_x/y`, the
negation) so the whole s8 range stays editable. twin_edge names the edge of a neighbouring polygon (1-based);
unshared edges are walls (FUN_680a866d), with heights at both ends interpolated by FUN_680a8fff (1/30 ft; 300 = 10 ft).

Polygon (10): s16 first_edge, u8 edge_count (edges first_edge .. +count-1, 0-based), u8 slope, s16 base_height,
s16 at_0x6, s16 slope_edge. Height = base_height + slope * (n . (pos - point of slope_edge)) >> 12 (FUN_680a83e9).
Every shipped ground is flat (slope 0).

### shape.tbl (BBSIM Ts_model.cpp)

Model header (26): u8 flags (0x40 depth-sort parts, FUN_680a92ca; 0x80 has instance states), u8 at_0x1 (0), u16
at_0x2 (0), s16 state count, u16 state offset (kept as `_state_off` when there are none), s16 level count, u16 level
offset, s16 radius (+0xc, visibility test FUN_680a90e0), s16 box min x, y, z, box max x, y, z.

Level (6): s16 at_0x0 (0, or 0xff = null on 8 levels), s16 part count, u16 part offset. Only level 0 is drawn.

Part (14): u8 state_slot (0xff = null; the slot's value picks the variant, clamped, FUN_680a9cb0, or hides the part
when it is 0xff, FUN_680aa7b0), u8 depth_vertex, u8 depth_ref_vertex (0xff = null), u8 vertex count, u16 vertex
offset, s16 variant count, u16 variant offset, s16 at_0xa (0), s16 at_0xc (0).
Vertices: s16 x, y, z. Parts may share a vertex list; the JSON has each part's vertices inline and `_shares` = the
index (over all levels) of the earlier part whose list it reuses. The encoder keeps the sharing while the two lists
stay equal and writes a new list once they differ.

Variant (8): u8 kind (0 = polygon list, the only kind shipped), u8 at_0x1 (0), s16 polygon count, u16 polygon
offset, s16 at_0x6 (0).

Polygon (8, FUN_680a6381): u8 flags (bits 0-1 type: 0 always drawn, 1 back-face tested against normal_vertex, 2
never; 0x80; 0x10 shade; 0x08), u8 color, u8 color2 (0xf4 / 0xf5 = crowd, painted with info.dat's crowd colors),
u8 x2 runtime (cleared by the loader FUN_680a7e26; nonzero leftovers kept as `_runtime`), u8 normal_vertex (0xff =
null), u16 offset of the 0xff-terminated vertex index list.
Seen in game (work/harness/t_shape_edit.py, 2026-10-08): color2 is the fill and color the outline (setting only color
recolours edges, foul lines, bases and flags; color2 fills stands, walls and dirt). With flag 0x10 (color2 0) color
is a texture frame, the scoreboards. The models are drawn by the ball-in-play cameras only, not the batting camera.

Shipped byte order (the encoder reproduces it): header, levels; per level its part table, then the vertex lists its
parts use first (first-use order), then per part its variants, per variant its polygon table followed by each
polygon's index list; the state bytes last.

## info.dat (e957)

Both forms start "STA:" u32 size.

.DT (74 bytes; BBShell 20565 / EZShell 15289): u8 version 1, name[63], u8 dome, u8 turf (the shell's stadium +0x2c /
+0x30). turf = 1 for CINCINNA, MINNESOT, MONTREAL, PHILADEL, HOUSTON, PITTSBUR, SEATTLE, TORONTO.

.DAT (BBSIM FUN_6806f2eb / FastSim 53230 copy bytes 8..101 to the stadium object +0x12; BBSIM FUN_6806c898 =
FastSim 52208 seek 0x66 for the rest):

| off | field |
|-----|-------|
| 8 | name[63] |
| 71 | u8 dome (MINNESOT, MONTREAL, HOUSTON, SEATTLE, TORONTO) |
| 72 | short_name[30] |
| 102 | s16 version, must be 6 |
| 104 | s16 sky_color: 0 = the default 0x47 / 0x4f, else DAT_681ec12c (HOUSTON 66) |
| 106 | s16 field_pattern: stored + 1 at stadium +0x82, the field palette load_game_palettes (BBSIM FUN_680303dd) picks: 0 fatrf.pal artificial turf (CINCINNA, MINNESOT, MONTREAL, PHILADEL, STLOUIS), 1 fglin.pal mow lines, 2 fgchx.pal checkered, 3 fgcrc.pal circles (BALTIMOR); +0x7e is the options override (0 = this default); FUN_68038070 = turf test for the field markings |
| 108 | s16 wall_bounce: stadium +0x20; when build_ball_path (BBSIM FUN_680498d7) bounces the ball off the wall (FUN_6806d950) it keeps DAT_680b35ac[v] percent of its speed: 0 = 30, 1 = 15, 2 = 29 (higher values read past the 3-byte table). Shipped 1 or 2 (2 at ANAHEIM, BOSTON, CINCINNA, DETROIT, MILWAUKE, MINNESOT, MONTREAL, NEWYORKN, PHILADEL, SANDIEGO, STLOUIS) |
| 110 | s16 color_cycle_frames (DAT_681cc090; FUN_68074849 steps every 1000 ticks) |
| 112 | 2 x 2 s16 crowd_colors (FUN_6807491f: polygon color 0xf4 -> pair 1, 0xf5 -> pair 2) |
| 120 | 4 x (s16 start, count, step) palette_cycles, rotated by FUN_6806d066 (KANSASCI 227, 3, 1: the fountains) |
| 144 | left_field_pole x, y (+8) |
| 148 | right_field_pole x, y (+0x18) |
| 152 | dugouts: 2 x (x, y), DAT_681ec100 / 104, picked by side in FUN_68019330 |
| 160 | on_deck_circles: 2 x (x, y), DAT_681ec108 / 10c, FUN_68061c40 |
| 168 | s16 n, then n x (s16 x, y, flag) fence outline; no loader reads it |

## cams.cfg (e6e7, BBSIM Cams.cpp; FUN_680143a4 loads, FUN_680145a3 / FUN_68014a4a save)

5078 bytes. u16 version 0x10, s32 view (+0x69), s32 target (+0x6d), s32 multi_camera (+0x71; added to the record
index for view 6), 15 camera records at 14 (views 0..5 one record each, view 6 = multi camera = records 6..14),
s32 current_slot at 404, then 10 slots: used flags at 408, names[64] at 418, s32 view at 1058, s32 target at 1098,
s32 multi at 1138, 15 records each (390 bytes) at 1178.
Camera record (26): s32 x, s32 y, s16 pitch, s16 roll, s16 at_0xc (no Cams.cpp code addresses record +0xc, i.e. view object +0x81 + 0x1a * view; 0 in all 165 shipped and saved records), s16 heading, s32 distance (clamped 30..60000 on
load), s32 z, s16 zoom (+0x5b).
Shipped slot names: Behind home plate (fixed), Behind home plate (tracking), Multi camera view, First base seats,
Third base seats, Trail ball, Batter, Trail selected player, Over dugout, Blimp view.

## injury.dat (e1a4, BBSIM FUN_68038227 / FUN_68038583)

22 s16 offsets (19 category tables, injuries, durations, after rolls; contiguous, derived), 19 s16 default odds
(replaced at load by settings 0x354 + i via FUN_68002cd0, DAT_680bc2d0), then:
- 19 category tables: s16 n, n x (s16 cumulative threshold against rand 1..999, s16 injury number).
- 205 injuries x 96: s16 number (= i + 1, derived), s16 duration (1-based), s16 after_roll (1-based), part[30],
  detail[30], condition[30] (e.g. Cheek / Cheek-bone / bruised).
- 46 durations x 16: s16 number (derived), roll (s16 dice, sides, base), s16 reroll_below, reroll (dice, sides,
  base). Days = base + sum of `dice` x (rand(sides) + 1); below reroll_below the reroll set decides
  (objdump 0x68038900).
- 12 after rolls x 8: s16 number (derived), dice, sides, base. The result is the injury's severity percent (record
  +4, FUN_68038583). FUN_6805b23c clamps it to 0..100, stores it as the player's in-game stat 2 and, once per game
  (flag 0x30), scales ratings 0x14, 0x15, 0, 1 and the nine FUN_6804e8f6 ratings by (100 - severity) / 100
  (FUN_68005bd0); the log line is "%s(%s) suffered a %d%% injury". Bases 9998 / 9997 (rolls 1 and 2, used by 97
  injuries) give 9999 / 9998, which the clamp turns into 100 (ratings zeroed for the rest of the game). Separately,
  duration 46 (base 9998) gives 9999 days, which BBShell treats as never healing (player +0x80 == 9999 is skipped by
  the daily heal FUN_68055540; FUN_680555b0 likewise).

No binary reads part / detail / condition: BBSIM and FastSim use only an injury's number, duration and after roll.
The names the shell prints are SHELL.VOL ASNEWS.DAT / TMNEWS.DAT section 0 strings 83..287 (injury n at 82 + n,
strtable.py); t_injury_edit.py (2026-10-08) renamed them all and read "(claudeitis) is day-to-day" in the news.
The per-play odds are PB.INI [PlayBalance] injuryChance* (pb_table_BBSIM.tsv idx 852-870): an injury happens when
rand(odds) == 0, so 1 = every check.

## logic.dat (6be6, BBSIM Act.cpp FUN_68001b9b)

5 u16 section offsets (derived), then 9-byte rows: byte k is the job of fielder k (1B, 2B, 3B, SS, P, C, RF, CF, LF;
fielder +0x2ad, FUN_680010ef / FUN_6802cf75). Jobs (the "COVER_1B" name table): 0 COVER_1B, 1 COVER_2B, 2 COVER_3B,
3 COVER_HOME, 4 BACKUP_1B, 5 BACKUP_2B, 6 BACKUP_3B, 7 BACKUP_HOME, 8 BACKUP_RF, 9 BACKUP_CF, 10 BACKUP_LF,
11 BACKUP_BOTH, 12 CUTOFF, 13 RELAY, 14 DO_LOGIC (the JSON carries this legend as `_jobs`).

| section | rows | index |
|---------|------|-------|
| infield | 120 | runners * 15 + (Grounder, Linedrive, Popfly) * 5 + ball to (1B, 2B, 3B, SS, P) |
| outfield | 72 | runners * 9 + (Single, Extra Base, Fly) * 3 + ball to (RF, CF, LF) |
| bunt | 32 | runners * 4 + ball to (1B, 3B, P, C) |
| special | 72 | event * 8 + runners; events STRIKE_OUT, WALK_ON_BALLS, INTENTIONAL_WALK, PICKOFF_1B, PICKOFF_2B, PICKOFF_3B, WILD_PITCH, RUNNER_STEALING, BATTER_HIT |
| batting_practice | 1 | |

Runner states 0..7: No runners, Runner on 1st, Runner on 2nd, Runners on 1st & 2nd, Runner on 3rd, Runners on 1st &
3rd, Runners on 2nd & 3rd, Bases loaded. The JSON nests the rows by these names, e.g.
`infield["Runner on 1st"]["Grounder"]["SS"]["2B"]` = the second baseman's job on a grounder to short.

A row needs its covers: every job of every row set to BACKUP_HOME stops the game at the first ball in play with
"Cover.cpp:453" (FUN_68018f46 asserts that FUN_6802e950 finds a fielder for the base). BBPRO.INI [Debug]
DebugEnabled=1 + ShowPlayerLogic=1 draws "%s %s (%d/3)" (job, action, e.g. "BACKUP_HOME DO_LOGIC (0/3)",
"RELAY CHASE_BALL") in small black text above each fielder; t_logic_edit.py reads them.

## numbers.inf (b0e7, BBSIM FUN_6800b2fd reads it whole, FUN_6800fa2b reads rows)

756 rows x 8. Row = (animation - 0x15) * 28 + side * 14 + frame, animation = FUN_6800adb0() (0x15..0x2f), side =
player +0x8d = batting side, 0 left / 1 right (FUN_6800b807 copies bats from roster +0x26, the pgen 1 L / 2 R / 3 S
less 1; a switch hitter takes the side opposite the pitcher's throws +0x7d), frame < 14. Row: s16 font (index into DAT_680b8370), s16 glyph_frame (digit glyph = glyph_frame +
digit * 3 * k, +1 / +2 for the left / right digit of a two-digit number), s16 x, s16 y. Unused rows are
(-1, 0, 0, 0), null in the JSON.

## bpi.str (5200, Utility/Strpool.cpp FUN_680adbfe)

u16 version 1, u16 count, count u16 offsets (from the strings), u16 total, the NUL-terminated strings back to back
(28: Swing Type:, Swing Loc:, Manager Menu, ...).

## sndvol.cfg (bb43)

6 u16 (128, 102, 64, 128, 1, 4). BBSIM.dll still has the name (VA 0x680c5070) but nothing references it; volumes come
from the [Sounds] settings keys (SoundsOn, ActionVol, ...). Kept as `unused_values`.

## Open

- info.dat fence flag: the outline has no reader, so the flag is inert.
- Game-visible edit tests (#11): shape.tbl (t_shape_edit.py), logic.dat (t_logic_edit.py), injury names
  (t_injury_edit.py) done.
