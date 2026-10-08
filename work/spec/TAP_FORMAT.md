# Instant-replay tapes (hilights/*.tap) and the tape queue (MLBPA97.NQ0)

Codec: `work/tapcodec.py` (decode/encode JSON). Every byte is a named field. It round-trips all 7 sample files
(4 tapes, 1 queue holding 5 tapes, 2 more tapes) byte for byte and passes `re/targets/voldatref.py` visible and
`--holdout`. Coverage is off for this target (`re/targets/tap/files.json`): the printable runs left in a tape are int
words in the frame records and stale string padding, which the codec keeps byte-exact.

The tap data lane (`re/targets/tap/lanes/data`) won with a tokenizer: printable runs became text and everything else
became u32 "playback words". Its NQ0 container was right. Its FORMAT.md calls FUN_6807ac99 the writer; that is the
snapshot restore. Claude mapped the rest from BBSIM (the Vcr object):
- file: FUN_680737fc save, FUN_680736c4 load, FUN_68079e75 checksum check, FUN_680ac5f3 checksum
- snapshot: FUN_6807adde write (size checked as 0x41b by FUN_6807ac99 restore)
- frames: FUN_68079aee write, FUN_680ac376 raw record, FUN_680ac3f7 delta record

## File

| Off | Size | Field |
|---|---|---|
| 0x00 | 2 | u16 version 0x2b |
| 0x02 | 80 | caption, NUL-padded (Vcr +0x367). The replay menu shows it. Stale bytes after the NUL are kept. |
| 0x52 | 2 | u16 frame count (Vcr +0x359) |
| 0x54 | 4 | u32 tape length (Vcr +0x1b) = file size - 0x5c |
| 0x58 | 4 | u32 checksum of the tape (Vcr +0x1f) |
| 0x5c | len | tape: snapshot (0x41b bytes), then frames |

Checksum (FUN_680ac5f3): for each tape byte, MSB first, `hi = c & 0x8000; c = (c << 1) & 0xffffffff; c |= bit;
if hi: c ^= 0x1021`. It is CRC-16/XMODEM shifted through a 32-bit register that is never masked, so the stored value
is 32 bits. The loader rejects a tape whose checksum does not match. Encode recomputes length, count and checksum.

## Queue (MLBPA97.NQ0)

u16 version (5), then per entry u16 tag (0x4000 | id), u32 length, and a whole tape file. The sample holds ids 1..5.
JSON: `{"version", "tapes": [{"id", "tape": <tape JSON>}]}`.

## Snapshot (0x41b bytes, FUN_6807adde)

The snapshot is the game state when the tape was saved, after the play. The caption describes the situation before
it (highlight004: caption "TOR 1, PIT 0 T-3rd O-0 Loaded", snapshot PIT 1 run and 1 out).

| Off | Size | Field | Writer |
|---|---|---|---|
| 0 | 2 | batting side, 0 away, 1 home (FUN_680027c0) | FUN_6806a8d4 |
| 2 | 2 | inning-state +0x00 (0xc020 or 0xc021 in the data) | |
| 4 | 2 × 0x22 | team state (away, home), layout below | |
| 72 | 4 | u8 balls, strikes, outs, inning (init 0, 0, 0, 1) | |
| 76 | 2 | u16 clock: +150 per half inning (FUN_6806acc0), read by FUN_6806a578 | |
| 78 | 2 × 0xcd | team records (away, home), layout below | FUN_68032f7b, object +0x45d |
| 488 | 41 | game setup, layout below | |
| 529 | 14 | stadium data file ("TORONTO.DAT") | FUN_6806fa61 |
| 543 | 14 × 36 | persons: 9 fielders, then 5 offense (batter, runners, on-deck) | FUN_6802e385, FUN_68061b28 |
| 1047 | 4 | u32 object +0x7e (or +0x82 when +0x7e is 0); 1 in the data | FUN_6804d42d |

Team state (0x22 bytes, accessors FUN_6806a0e5 / FUN_6806a1d4 / FUN_6806a25a / FUN_6806a2e0):
u8 runs, 30 × u8 runs per inning, u8 hits (+0x1f, FUN_68027840 counts a hit and clears the count), u8 errors (+0x20,
FUN_680268f0 charges the fielding side), u8 left on base (+0x21, FUN_68027880 adds to it). The box line prints R, H, E
from these. JSON trims scoreless innings past the 9th.

Team record (0xcd bytes), copied by the game-set init FUN_68031e2f from the GDI team block:
byte 0 = GDI team byte (team id), byte 1 = GDI team +5, then GDI team +0x0c..+0xd6:

| Off | Size | Field |
|---|---|---|
| 0x02 | 17 | name (team +0x0c) |
| 0x13 | 17 | alt name (team +0x1d), empty in the data |
| 0x24 | 17 | manager (team +0x2e) |
| 0x35 | 5 | abbrev (team +0x3f) |
| 0x3a | 9 | team +0x44..+0x4c, zero in the data |
| 0x43 | 33 | stadium (team +0x4d) |
| 0x64 | 9 | city8: the 8-character DOS stem of the stadium file ("PITTSBUR", "TORONTO.") |
| 0x6d | 96 | uniform palette, 32 RGB triples (two 16-shade ramps) |

Game setup (41 bytes at object +0x5f7):

| Off | Field |
|---|---|
| 0 | u8 game mode: GDI 0x3e6, or 5 when GDI 0x3e7 is 4. Tested for 0..5 across BBSIM. |
| 1 | u8 GDI 0x3e7 (0 when the mode was forced to 5) |
| 2 | u8 GDI 0x3e8 |
| 3 | 14-byte stadium file: home city (GDI 0x3eb) with its "." replaced by ".dat", or ".dat" appended (FUN_68031e2f) |
| 17 | 14-byte association file ("MLBPA97.NQ0") from GDI 0x3f4 |
| 31 | u32 day serial (proleptic Gregorian ordinal + 365, as in the H card), u8 month 0..11, u8 day 0..30, u16 year. Set together by FUN_680327ed(serial), called from FUN_68031e2f; the screen prints "%s, %s %d, %d" from them. |
| 39 | 2 × u8 per side: 1 when team bytes +0x1b × 3 + +0x1c × 4 + +0x1d × 2 < 0x480 (`low_rating`) |

JSON keeps year, month (1-based), day (1-based); encode rebuilds the serial. A date that does not match its serial
would be kept raw as `_raw_date`.

Person (36 bytes): first name 17, last name 17, u16 uniform number (actor +0x70, +0x81, +0x6e). Unused slots are
empty; the data repeats a runner in several offense slots.

## Frame (FUN_68079aee)

1. Camera, 28 bytes (FUN_680157e8 on the global camera at 0x680d5460): u16 +0x58, u16 +0x5b, u16 angle +0x11,
   u16 angle +0x15, 3 × i32 position +0x05/+0x09/+0x0d (the debug overlay prints "(%d, %d, %d) [%04hx, %04hx, %04hx]"
   from +0x05..+0x15), 3 × u16 +0x61, u16 +0x67.
2. Ball flight (FUN_680490ca on the ball): u8 flag (+0xe8c, cleared after writing), u32 +0xe70. When the flag is 1:
   u32 n (+0xe74), u32 +0xe78, +0xe7c, +0xe80, +0xe84, +0xe88, then n + 1 points of 3 × i32 (+0x60). JSON keeps the
   path only when present; n comes from the point count.
3. State record, 408 bytes. Frame 0 stores it whole (FUN_680ac376). Every later frame stores u32 k, then k pairs
   of (u32 word index 0..101, u32 new value) for the words that changed, in ascending order (FUN_680ac3f7). Every
   stored word changes; encode re-deltas by comparison and reproduces the files exactly.

State record:

| Off | Size | Field |
|---|---|---|
| 0 | 30 | ball (FUN_68048e56): u16 state +0x0c, u16 +0x50, u16 +0x52, 3 × s16 position +0x00, 3 × s16 velocity +0x06, u32 +0x44, +0x40, +0x4c |
| 30 | 8 | u16 sim +0xe92, u32 sim +0xea8, u16 global 0x680b80b4 (FUN_6800972a) |
| 38 | 4 | u32 fielding object +0x2f |
| 42 | 9 × 18 | fielders: actor (10) + u32 +0x2a5 + u32 +0x2a9 (FUN_6802d8a3). Order 1B, 2B, 3B, SS, P, C, RF, CF, LF in the data. |
| 204 | 5 × 26 | offense: actor + u32 +0x2b9, +0x2a9, +0x2ad, +0x2b1 (FUN_6805de6a) |
| 334 | 6 × 10 | umpires: actor only. 1B, 2B, 3B, home (0, -225), two line umpires at (±4879, 4879). |
| 394 | 2 | u16 +0x1d (FUN_68078374) |
| 396 | 6 | u32 +0x3390, u16 +0x3394 (FUN_68047f66) |
| 402 | 4 | u8 global 0x681ec180, 3 bytes global 0x681ec194 (FUN_6806eed4) |
| 406 | 2 | u16 written from an uninitialized local (FUN_68079de6), stack garbage |

Actor (10 bytes, FUN_68005985): s16 x (+4), s16 y (+6), u16 z (+0x10, about 144 standing), s16 heading (+0x0e,
-32768 faces home), u8 animation (+0x1e), u8 +0x2e. Units are 1/30 ft with home plate at (0, 0) and +x toward
first base: 1B bag (1909, 1909), 2B (0, 3818), pitcher y = 1815 (60.5 ft), batter (±60, 0).

Field names (ROADMAP #10, 2026-10-08). The 29 fields first stored as `at_0x<offset>` now decode under the names
below; encode still accepts the old `at_0x` keys. Evidence quotes and full meanings: `work/spec/TAP_NAMES.json`
(referee re/targets/tapnameref.py, PASS; Claude-gated). `low` = only the tape save/load pair touches the offset, so the
meaning rests on the tape values. `global_..` fields stay unlabelled.

| Old key | Name | Conf. | Meaning |
|---|---|---|---|
| actor.at_0x2e | animation_frame_index | high | u8 frame index of the actor's current animation: FUN_68003c86 (advance_anim_frame) adds the step at +0x2a each step, clamps it to 0 when it runs negative, pins it to framecount-1 at the ends and reverses, and FUN_68003fe3 (set_anim_frame) seeds it when an animation is armed. |
| camera.at_0x58 | camera_save_probe_word | low | u16 word of the global camera the Vcr save path probes before capturing: FUN_680156ca reads it with a 2-byte membuf call (FUN_680ac2be) and fails the save if it reads back short, and the restore counterpart FUN_680157e8 probes it identically with FUN_680ac31a. |
| camera.at_0x5b | camera_extent_bound | high | u16 display extent bound of the global camera: FUN_680133a6's camera-script cases compute it as FUN_6800fd60((extent << 4) / config entry, 0x80, 0x1000): a clamp between 0x80 and 0x1000: or copy it from the camera config entry, and FUN_68014256 continues to use it as the pan extent. |
| camera.at_0x61 | camera_look_target | medium | 3 x u16 point (x +0x61, y +0x63, z +0x65) the global camera looks at: FUN_68015653 derives the pitch angle from (target_z +0x65 - camera position_z) with the delta/angle helpers FUN_680a4d50 (vector difference) and FUN_680a467c over camera +0x61, so +0x61..+0x65 behaves as the look-at target point. |
| camera.at_0x67 | camera_target_roll_word | low | u16 word that follows the target point (x +0x61, y +0x63, z +0x65) of the global camera: FUN_6801539c picks either camera +0x67 or the actor head +0x16 as the third word of the camera target vector, so +0x67 reads as the roll word of the target vector. |
| ball.at_0x50 | ball_pitch_segment_flag | low | u16 per-ball flag cleared to 0 on every trajectory segment recompute: FUN_6804a62c (called from the pitch/batted-ball rebuilds FUN_68048550 and FUN_6804870b after clearing the +0x30 event bits) sets ball +0x50 = 0 alongside the velocity rebuild. |
| ball.at_0x52 | ball_flight_time | medium | u16 flight time of the ball in 1/69-second ticks (the 0x45 constant is config +0x6b, the 69 scale): FUN_68048550 computes it as max(1, distance / FUN_6804a62c) from the squared speed extent and stores speed = time * 0x45 >> 1, the pitch init FUN_6804870b sets it to 1. |
| ball.at_0x44 | catch_point | medium | Packed field point (s16 x low word, s16 y high word) where the ball comes down to catchable height: the path builder FUN_680498d7 stores the path point at frame +0xe78 here; |
| ball.at_0x40 | blend_start_point | medium | Packed field point (s16 x, s16 y) the ball's projected spot is blended from: FUN_68048550 copies the throw target here and FUN_6804870b copies the ball's launch position (x,y) here, before the path builder overwrites +0x44; |
| ball.at_0x4c | exit_point | medium | Packed field point (s16 x, s16 y) where the ball leaves the field: FUN_680498d7 stores the path point at frame +0xe88 when the ball goes out, otherwise the catch-height point (same as +0x44). |
| sim.at_0xe92 | sim_event_flags | medium | u16 bit-flag word of the sim object (set with flags_or_set FUN_68002760, cleared with FUN_68002c20, toggled with FUN_6800a1c0 on this+0xe92): the pitch setup FUN_68008f35 sets 0x200 and 0x40, FUN_680090dc toggles 0x100, and FUN_68008c42 mirrors it into the working copy +0xe94 each step. |
| sim.at_0xea8 | current_fielder_index | high | u32 index of the player of the play (the fielder making the play) in the sim object: the get helpers FUN_68009388/FUN_680093c9 read it (stashing the previous value at +0xeac) via FUN_680081f0 when < 9 else 0, the play-select FUN_6800940a sets it from param_2, and the pitch routines FUN_680090dc/FUN_6800921d reset it to 9 (no fielder) between plays. |
| fielders.at_0x2a5 | fielder_assignment_id | low | u32 assignment id stored in the tape fielder extras right after the 10-byte actor: the tape fielder copy FUN_6802d8a3 stores it (4-byte membuf call) and its counterpart FUN_6802d82d reads it back first, proving it is the first fielder-extra word. |
| fielders.at_0x2a9 | fielder_cover_flag | low | u32 second fielder-extra word the tape copy FUN_6802d8a3 appends after +0x2a5, and its restore counterpart FUN_6802d82d probes in the same order, proving it belongs to the fielder extras. |
| offense.at_0x2b9 | runner_new_base | medium | u32 base ordinal the offense person is headed to: FUN_68060f39 sets +0x2b9 = param_2 + local_10 and clamps it to 3 when it passes 3, FUN_6805ee76 copies play state +0x2b1 into +0x2b9, and FUN_68060391 copies +0x2b9 back into +0x2b1 and tests it == 3 (home) when the play logic completes. |
| offense.at_0x2a9 | runner_base_copy | low | u32 offense word the tape copy FUN_6805de6a appends after the +0x2b9 word (order +0x2b9, +0x2a9, +0x2ad, +0x2b1), and its restore counterpart FUN_6805ddac reads back in the same order, proving it belongs to the offense extras. |
| offense.at_0x2ad | fielder_assign_base | medium | u32 base/assignment id the offense person is assigned for this play: the fielder finder FUN_6802e950 selects the fielder whose +0x2ad equals a base ordinal (0..3), the runner-state init FUN_6805da51 indexes the bag-position table with it, and the anim select FUN_6805dcf2 arms the 0x2b anim when it is nonzero. |
| offense.at_0x2b1 | runner_logic_state | high | u32 play-logic state the offense person is running through: FUN_6802d942 returns the string 'DO_LOGIC' + +0x2b1 * 0xd confirming it is the do-logic state selector, the runner tick FUN_6805e207 steps +0x2b1 toward the play target +0x2b9 and triggers FUN_6802956e when it reaches 3 (home), and FUN_6805e063 counts it down one state at a time. |
| record.at_0x1d | umpire_crew_spare_word | low | Trailing u16 of the umpire crew object (global 0x681ec578; |
| pitch.at_0x3390 | pitch_marker_frames | medium | u32 script marker count of the precipitation/pitching overlay: the init FUN_68047dc5 sets it to 0x672 (1650), runs its for-loop that many times building the offset table, then resets it to FUN_68048340() * 200 + 400 (400 or 600); |
| pitch.at_0x3394 | pitch_sway_offset | high | u16 sway offset of the precipitation/pitching overlay sprite: the per-frame tick FUN_6804809c increments or decrements it (branching on the event flags), wraps it with FUN_68016e40(delta, 0, 0x640), and applies it as (delta >> 4) against the count at +0x3390 to place the sprite via FUN_680b11f0. |
| state.at_0x00 | inning_brick_header | low | u16 header word of the team/inning state brick: the snapshot copy FUN_6806a8d4 writes the batting side (FUN_680027c0) and then this word (a 2-byte membuf write at param_1, brick offset +0x00). |
| snapshot.at_0x7e | playing_surface | high | Field surface/pattern in effect, saved with the replay: +0x7e is the user setting (0 = use the stadium's), +0x82 is the stadium's info.dat 0x6a field pattern + 1. |
| ball_flight.at_0xe70 | ball_flight_frame_index | high | u32 current index into the ball's recorded flight-path frames: the per-frame step FUN_6804877d tests index < frame total (+0xe74) and increments it before copying the frame's point (the vec3 copy FUN_68016d20 over +0xe70 * 0xc + +0x60) to the live flight, and the restore path FUN_68048f5c reads it back first. |
| path.at_0xe78 | catch_height_frame | high | Flight-path frame index at which the ball first comes down to catchable height: the path builder FUN_680498d7 inits it to -1 and sets it to the first frame where the vertical speed is not positive and the height is under 0x3841; |
| path.at_0xe7c | first_bounce_frame | high | Flight-path frame index of the ball's first contact: FUN_680498d7 sets it (once, from -1) on the first frame the height goes below 0 (ground bounce, which then applies the surface bounce constants) or on the first wall rebound. |
| path.at_0xe80 | roll_start_frame | high | Flight-path frame index at which the ball stops bouncing and starts to roll: after a bounce FUN_680498d7 damps the vertical speed, and the first time it falls under 0x100 it zeroes height and vertical speed and records the frame here (-1 until then). |
| path.at_0xe84 | wall_bounce_frame | medium | Flight-path frame index of the first wall rebound: when the fair-territory/field test FUN_6806d84a fails and FUN_6806d950 can step the ball back inside, FUN_680498d7 reflects the velocity and records the frame here (also as the first bounce if none yet); |
| path.at_0xe88 | leaves_park_frame | medium | Flight-path frame index at which the ball leaves the playing field for good: FUN_680498d7 records it when the field test FUN_6806d84a fails and FUN_6806d950 cannot bring the ball back (over the fence or out of play); |

## JSON keys

```
{caption, snapshot: {state: {batting_side, inning_brick_header, teams: [{runs, linescore, hits, errors, left_on_base}] x2,
                             balls, strikes, outs, inning, clock},
                     team_records: [{team_id, setup_5, name, alt_name, manager, abbrev, unused_0x44, stadium, city8,
                                     uniform_palette: [[r, g, b]] x32}] x2,
                     game: {game_mode, setup_mode, setup_0x3e8, stadium_file, association_file,
                            date: {year, month, day}, low_rating: [a, b], _day_serial},
                     stadium_dat, fielders: [{first_name, last_name, number}] x9, offense: [...] x5, playing_surface},
 frames: [{camera: {...}, ball_flight: {ball_flight_frame_index, path?: {catch_height_frame.., points: [[x, y, z]]}}, record: {...}}],
 _frame_count, _tape_length, _checksum, _stale_strings?}
```

`_` keys are derived and ignored on encode, except `_stale_strings` (path -> original field hex), which puts the
bytes after a string's NUL back when that string is unchanged.
