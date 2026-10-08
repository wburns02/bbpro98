# FastSim pitch model (roadmap #10, M9)

The pitch-by-pitch batter logic of FastSim.dll (source file `.\FastSim\fbattr2d.cpp`, the batter's swing setup) and the
bat-ball contact resolver that follows it. BBSIM.dll is the same code plus the 3D layer (same PB parameter names, same
LFSR); its twin addresses are not mapped yet. Every formula below is checked by exact replay against an in-game trace
(see Validation): the model reproduces the outputs and the RNG state of every recorded call.

PB numbers are [PlayBalance] indices (decimal, as in work/pb_table_FastSim.tsv; PB.INI is not shipped, so the DLL
defaults apply). The defaults differ from the doc defaults in that table, so quote the DLL column.

## RNG

| what | where | notes |
|---|---|---|
| step | FUN_68082ae1 | Galois LFSR: `s = (s >> 1) ^ (s & 1 ? 0xa3000000 : 0)`, returns the new state. Period 2^32-1 (maximal, checked by brute force). |
| `mod(n)` | FUN_68082999 (thiscall on a state) | `n < 2 ? 0 : step() % n`; always advances. |
| `range(lo, hi)` | FUN_680829dc | `lo + step() % (hi-lo+1)` (or `lo` when the span is < 2). |
| `chance(p)` | FUN_68082a2d | `(step() & 0xfff) < p * 0x29` (p in percent of 4096/41). |
| `dice(n, faces, base)` | FUN_68082a7c | `base + sum(range(1, faces))` n times, always on the main state. |
| main state | DAT_68185a60 | Seeded from time() at startup; src-latest/mods/seed.c pins it (M12). |
| batter state | DAT_680a2128 | Reseeded from the main state in the batter constructor (FUN_6800b0e6 area). Used only by the swing decision. |

Consecutive outputs are correlated: the mod-100 correlation of two successive draws is about 0.25, because each step
shifts the state one bit. So the sum of k dice is wider than k independent dice (5d14: sd 10.98 vs 9.01), and "swing if
either of two draws passes" happens less often than `p + (1-p)p`. An RNG-replacement mod (swap FUN_68082ae1 for a
better generator) would change the game's statistics, not just its sequence.

## Call order per pitch

FUN_6800b36e (batter swing setup), once per pitch per batter object:

1. FUN_6800cccc look type: weighted draw over pitch types (lookPrimary / lookBestType count tables).
2. FUN_6800d0eb look location; FUN_6800d3de, FUN_6800d44f.
3. FUN_6800d51a type identification, FUN_6800d6be location identification.
4. **FUN_6800da34 timing** (below).
5. FUN_6800e5db.
6. **FUN_6800e043 swing decision** (below). FUN_6800ec38 instead when FUN_6803cc73 >= 2 (it always returns 0 in FastSim).
7. If swinging: identification again, then FUN_6800e826 check swing, then FUN_6800ec38 adjust.
8. Swing parameters: angle +0x11f, direction +0x123, bat speed +0x125.

Then, when the ball reaches the plate, **FUN_68053d2e contact** (below), which calls FUN_68054d4a to launch a batted ball.
Fair/foul and hit/out are decided later by ball flight and fielding; a take is a ball or strike by location.

## Batter object fields

| offset | meaning |
|---|---|
| +0x89 u16 | order flags: 0x100 bunt, 0x200 hit and run, 0x400 take |
| +0x8b u16 | bit 4 = swinging |
| +0x8d | batter hand |
| +0x95 | discipline rating (also the check-swing rating) |
| +0x99 | bat speed rating |
| +0x9d | direction (pull) rating |
| +0xbd | swing type: 0 power, 1 normal, 2 contact, 3 bunt |
| +0xf1, +0xf5, +0xf9 | timing rating, timing penalty, penalty-off flag |
| +0xfa | looked-for pitch type |
| +0x107, +0x109 i16 | aim location x, y (pitch-location grid units) |
| +0x10f, +0x110 | looking-for type matched, location matched |
| +0x111, +0x112 | perfect-timing flag, timing offset |
| +0x11a | discipline after adjustments (FUN_6800dcc4) |
| +0x11e | swing flag |
| +0x11f, +0x123 i16, +0x125 | swing angle, swing direction, bat speed |
| +0x129 | check-swing budget |
| +0x139 | check swing: 1 checked, 2 failed check |

Game object 0x68143ee0: +0x4a batting-side pointer, +0x4e balls, +0x4f strikes. Pitch object (DAT_680a224c): +0x7d
pitcher hand, +0xeb / +0xed location x / y, +0x105 speed, +0x10d batter guessed it. Manager flags: u16 at
0x68114948 + side*2 + 2 (side = game+0x4a != 0x68143ee2), bit 0x80 = swing away.

## Timing (FUN_6800da34)

```
v = rating(+0xf1) * idRatingTimingWeight(512) / 100
if !+0xf9: v -= +0xf5
if type == bunt: t = dice(1, 30, -15)                                   # timingBunt*        532-534
elif v < 50: t = dice(1, 80, -41)                                       # timingVeryBad*     513-516
elif v < 65: t = dice(2, 40, -41)                                       # timingBad*         517-520
elif v < 72: t = dice(3, 25, -39)                                       # timingMed*         521-524
elif v < 80: t = dice(4, 19, -40)                                       # timingGood*        525-528
else:        t = dice(5, 14, -38)                                       # timingVeryGood*    529-531
+0x112 = t; +0x111 = (|t| < 1)
```

Rating sets the spread of the timing error, not its mean: every bracket is centred near 0.

## Swing decision (FUN_6800e043)

Zone of the aim location (FUN_6802ef90), `d = max(|x|, |y|)`: `d <= sureStrikeDist(385)=3` sure strike (0),
`<= closeStrikeDist(386)=5` close strike (1), `<= closeBallDist(387)=5` close ball (2), else sure ball (3).

Discipline (FUN_6800dcc4, into +0x11a):

```
d = ( rating(+0x95) * disciplineRatingCHPct(561)/100 + exp * disciplineRatingExpPct(562)/100
      + disciplineRatingBase(559) + countAdj[balls][strikes] (570..)
      + situational adjusts 563..569 ) * disciplineRatingPct(560) / 100
```

Situational adjusts include the hot/cold zone: DAT_68096410[pitch type +0xfa][pitcher hand != batter hand][grid cell
((4-y)/3)*3 + (x+4)/3], value 0 = minus zone (MinusZoneAdjust 567 = -30), 2 = plus zone (566). Lower d = more swings.

Approach table DAT_6808cfb8[strikes][balls]:

| strikes \ balls | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 0 | 0 | 3 | 3 | 3 |
| 1 | 1 | 1 | 3 | 3 |
| 2 | 2 | 2 | 2 | 2 |

```
if bunt order: swing = (zone != 3), type = bunt
elif hit-and-run order: swing, type = contact
elif take order: no swing
elif manager swing-away flag: swing, type = power
elif zone == 3: no swing
else: r() = batter_rng.mod(100); look = type matched and location matched; cold = hot/cold cell == 0
  mode 0: swing = d < r(); if not: swing = (d < r()) and look       type = look ? power : normal
  mode 1: swing = look or guessed or (cold and location matched) or d < r()            type = normal
  mode 2: zone 0/1 swing; zone 2 swing = d < r()                    type = (look or guessed or cold) ? normal : contact
  mode 3: look: swing, type power; guessed or cold: swing = d < r(), type normal; else no swing
```

## Check swing (FUN_6800e826) and adjust (FUN_6800ec38)

Urge = adjustUnitsDiag(736)=12 / Horiz(737)=4 / Vert(738)=8 times the location-identification error, plus the
timing-identification error weights (739-742). If urge > budget +0x129 and `rand(100) < urge - budget`, the check
succeeds when `rand(100) < base DAT_6808cf88[type] + rating(+0x95) * DAT_6808cf98[type] / 100`: +0x139 = 1 (checked),
else 2 (failed check). No check with two strikes on a zone 0/1 pitch. Adjust then moves the aim +0x107/+0x109 toward
the true pitch location and shrinks the timing error.

## Swing parameters (end of FUN_6800b36e)

- Angle +0x11f: tenths of a degree from swingAngleTenthDegrees* (605-615, base 70, power +50, contact -50, high +100,
  low -50), stored as deg * 8192 / 45.
- Direction +0x123: `((rating(+0x9d) + type adj) * 2 - 100) / 5` degrees, to angle units (0x10000 = 360), negated for
  batter hand +0x8d == 1.
- Bat speed +0x125: `swingSpeedBase(599)=71 + rating(+0x99) * swingSpeedPHPct(600)=8 / 100 + typeAdj` (601-604: power
  +10, normal 0, contact -15, bunt -100), then adjusted for pitch speed through averagePitchSpeed(848)=90,
  fastPitchBatSlowdownPct(849) and slowPitchBatSpeedupPct(850) (exact form not replayed: the trace records +0x125 as
  an input of contact). 0 for a bunt or a checked swing.

## Contact (FUN_68053d2e, fastcall on the view; batter at view+0x6b)

```
if pitch-record flags (0x680a58de+0x1f) & 2, or not swinging (+0x8b bit 4), or +0x139 == 1: return
if +0x139 == 2: main.mod(100)                       # failedCheckContactChance(769) draw; result unused
c     = timing(+0x112) * pitch speed(+0x105) * 704 / 40000           # signed, truncating
spray = direction(+0x123) + atan2_bb(36 - |c|, c)                   # 0x10000 = 360 degrees, short
thr   = cos_bb(spray) * 100 >> 14
vert  = (pitch.y - aim.y) * 200 + main.mod(201) - 100
if |vert| > 100: zone = 5 (miss)
else, ex = pitch.x - aim.x:
   ex  0        -> 2
   ex  1        -> 2 if main.mod(100) < thr else 3
   ex  2        -> 3 if roll else 5
   ex -1, -2    -> 2 if roll else 1
   ex -3, -4    -> 1 if roll else 0
   ex -5, -6    -> 0 if roll else 5
   otherwise    -> 5
exit = batspeed(+0x125) * thr / 100 * (base[zone] + main.mod(range[zone])) / 100
launch (FUN_68054d4a) if zone != 5 and |spray| < 0x4000 (90 degrees): angle = hitAngleCount{type} d hitAngleFaces +
   hitAngleBase (power/normal 3d20, contact 3d20-3, bunt 10d7-10)
```

Bat zones, table DAT_68097608 (PB 700-707):

| zone | name | base | range |
|---|---|---|---|
| 0 | handle | 25 | 25 |
| 1 | dull | 70 | 10 |
| 2 | sweet | 92 | 6 |
| 3 | end | 80 | 10 |
| 4 | (past the end) | hitAngleCountPower 3 | hitAngleCountBunt 10 |
| 5 | miss | hitAngleCountNormal 3 | 3 (drawn even on a miss) |

`atan2_bb` is FUN_6807c09c (octant table at 0x6809dc7c, 513 bytes) and `cos_bb` FUN_6807cb88 (Q14 quarter-wave table
at 0x6809de80, 0x401 u16). With timing error 0 the spray is just the swing direction and the batter hits the sweet spot
at full bat speed; the timing error pulls (early, c > 0) or pushes the ball and the cosine scales the exit speed down.

## Worked example (trace pt2)

One pitch, batter in the "med" timing bracket, count 0-1, pitch speed 93:

1. Timing: rating +0xf1 66, penalty skipped (+0xf9 = 1), v = 66 -> med, dice(3, 25, -39) from main state 0xb7330f96
   sums to 39 -> t = 0, perfect flag 1.
2. Swing: aim (5, 1) -> max 5 -> zone 1 (close strike). Approach[1 strike][0 balls] = mode 1. Type matched, location not,
   not guessed, not a cold cell -> random: d = 42, batter_rng.mod(100) = 86 from state 0xa1987cb4, 42 < 86 -> swing,
   type normal. Model P(swing) = (99-42)/100 = 0.57.
3. Contact: timing 0 -> c = 0 -> spray = direction -182 (about -1.0 degree). thr = cos(-182) * 100 >> 14 = 99. Pitch
   location (5, 1) equals the adjusted aim, so vert = mod(201) - 100 is within 100 and ex = 0 -> sweet spot. Exit =
   72 * 99 / 100 = 71, times (92 + mod(6) = 2) / 100 = 66. Launched at spray -182, speed 66: the trace's launch call
   received exactly these.

## Validation

Mod src-latest/mods/pitchtrace.c detours FUN_6800e043, FUN_6800da34, FUN_68053d2e and FUN_68054d4a and writes
760-byte records (inputs, RNG states before/after, outputs). re/pitch_model.py replays them. Two sim runs from the day-10
snapshot (pt1 2 days, pt2 4 days), 67,548 records:

| check | result |
|---|---|
| swing decision exact replay (swing flag, type, batter RNG after) | 18,425 / 18,425 |
| timing exact replay (offset, perfect flag, main RNG after) | 28,073 / 28,073 |
| contact exact replay (launched, spray, exit speed, main RNG) | 21,050 / 21,050 |
| swing rate vs model probability, 1,795 random decisions, 10 bins | chi2 12.35, dof 10, p 0.262 (1,368 swings vs 1,362.0) |
| contact bat-zone rolls, 98 random | p 0.237 |
| exit-speed draw, sweet spot, n 4,025, uniform 0..5 | chi2 7.79, dof 5, p 0.168 |
| timing offsets vs uniform-state LFSR dice, per bracket | verybad p .936, med .131, good .374, verygood .208, bunt .662; **bad p < 0.001** (n 10,234) |
| timing offsets vs ideal independent dice | rejected for every multi-dice bracket (p down to 1e-279) |

Gate: exact replay on all three, swing and contact outcome distributions p > 0.05. PASS
(output: /mnt/nvme/bbpro98/re/hookab/pitch_model_pt1pt2.txt).

Open: the 2d40 "bad" timing bracket deviates from the uniform-state LFSR distribution at n = 10k (sd 18.11 vs 18.08,
small but significant) while exact replay is perfect, so the formula is right and the effect is in which LFSR states
the game reaches. Ruled out: duplicate samples, a short cycle (period is maximal), selection by the +0xf5 penalty,
on-cycle vs uniform sampling. Not gated; worth a look if someone builds an RNG mod.

Reproduce:

```
MODNAME=pitchtrace bash re/hookab.sh ARM on DAYS bbfix.dll pitchtrace.dll     # bbfix.ini [pitchtrace] mode=on
mv /mnt/nvme/bbpro98/work_install/pitchtrace.bin /mnt/nvme/bbpro98/re/hookab/ARM/
python3 re/pitch_model.py /mnt/nvme/bbpro98/re/hookab/ARM/pitchtrace.bin
```

## Rating mappings found here (M11 input)

| rating | field | used by | effect |
|---|---|---|---|
| discipline | +0x95 | FUN_6800dcc4 | `* 60 / 100` into d; higher d = fewer swings at random pitches |
| discipline | +0x95 | FUN_6800e826 | check-swing success `base[type] + rating * pct[type] / 100` |
| timing | +0xf1 | FUN_6800da34 | bracket thresholds 50/65/72/80 pick the dice; spread shrinks with rating |
| bat speed | +0x99 | FUN_6800b36e | `71 + rating * 8 / 100` (+ type adjust) = bat speed, linear in exit speed |
| direction | +0x9d | FUN_6800b36e | `(rating*2 - 100) / 5` degrees of pull |

Nonlinearity: timing is a step function of the rating (five brackets), the others are linear.
