# FastSim game logic model (roadmap #10, M10 + M11)

The at-bat, baserunning, defensive-manager, fielding, pitching-change, injury and fatigue logic of FastSim.dll, the
engine behind Association day simulation. The pitch-by-pitch batter logic (swing, timing, contact) is in
work/SIM_PITCH_MODEL.md (M9); this document covers everything around it. Every formula marked **[refereed]** is
replayed exactly by re/sim_model.py against in-game traces (src-latest/mods/simtrace.c): the model consumes the
function's own event stream (every PlayBalance read, every RNG draw, every probed getter, in call order) and must
reproduce its return value or the fields it writes. Sections marked **[decompile]** are read from the decompile and
the disassembly but not yet replayed.

PB numbers are [PlayBalance] indices in decimal (names and DLL defaults: work/pb_table_FastSim.tsv). Values quoted
are the DLL defaults, which apply because the game ships no PB.INI. `mod(n)` is the main RNG (DAT_68185a60, the
LFSR in SIM_PITCH_MODEL.md); `chance(p)` is `(step() & 0xfff) < p * 0x29`; `range(lo, hi)` is `lo + step() % span`.

## Architecture: decisions are tables, outcomes are physics

FastSim does not look up hit/out outcomes in tables. A plate appearance runs the 3D simulation at a fixed time step:

1. Pitch selection (FUN_6803080a, weighted by type and count) and **pitch execution** (FUN_6803122b, below) place
   the ball at the plate with a velocity and movement.
2. The batter's swing (M9) and **contact** (FUN_68053d2e) launch the ball: FUN_68054d4a / FUN_6803b82c set its
   initial velocity vector from bat speed, swing angle and timing error.
3. FUN_6803aad7 integrates ball flight every frame (gravity, drag, bounces, walls).
4. **Fielder selection** (FUN_68022ea4): every fielder's time to the ball's path is computed and the fastest one
   (time to point plus a per-position reaction delay, PB 475-492 scaled by fielding ability) is sent. Deterministic,
   no RNG.
5. Fielders run (per-frame movement), the **catch roll** (FUN_68014f7b) decides clean catch or error, then the
   **throw** (FUN_6805dd30): range check, wild-throw roll, throw speed (FUN_6805d960).
6. Runners move every frame (FUN_680519e0 update_runner_positions, FUN_6804faa1 runner AI): advance decisions compare
   the runner's time to the next base with the ball's / fielder's time, so an extra base, a throw-out or a score all
   emerge from speeds and distances.

So hit type (single/double/HR), BABIP and advancement are not formulas: they are the result of the launch vector, the
park, the fielders' positions and speeds, and the runners' speeds. What IS formula-driven, and documented here, is
every probabilistic decision layered on top: the managers' choices, the catch and throw rolls, pitch control, leads,
injuries and fatigue.

## At-bat

### Pitch execution (FUN_6803122b) [refereed: 12,492 pitches]

Uses a separate pitch RNG (DAT_68113d88) for control, movement and scatter, and the main RNG for velocity.

```
t       = pitch type thrown (0 fb, 1 cb, 2 cu, 3 sl, 4 sb, 5 kb, 6 si, 7 st)
rating  = pitcher's rating for t (6803e377);   AS, CO, MO = arm strength, control, movement (6803e39f 1/2/3)
fatigue state 3 (tired):     rating *= PB616 (90) / 100;  AS *= PB617 (90) / 100
fatigue state 4 (exhausted): rating *= PB618 (75) / 100;  AS *= PB619 (75) / 100
effCO   = CO * rating / 100 * PB622 (70) / 100;   missCO = pitchRNG.mod(100) - effCO   (control OK iff missCO < 1)
effMO   = MO * rating / 100 * PB623 (100) / 100;  missMO = pitchRNG.mod(100) - effMO   (movement OK iff missMO < 1)
velocity = PB[388+3t] (base) + mod(PB[389+3t]) (range) + AS * PB[390+3t] / 100, then +-5 for effort
box     = (PB[412+2t], PB[413+2t]);  if control failed: box += missCO * PB624 (30) / 100 on both axes
location = aim + (pitchRNG.mod(box.x), pitchRNG.mod(box.y))
movement is scaled by effMO
failed movement (missMO >= 1), by type:
  fastball:     pitchRNG.mod(100) < 2*AS - 100  -> velocity loss
  cb/cu/sl/sb:  pitchRNG.chance(50)             -> the pitch changes type (hangs)
  sinker:       AS < 50: mod(100) < 50 -> type change;  else <33 loss, <66 type change
  velocity loss = PB627 (5) * missMO / 100 + pitchRNG.mod(PB626 (6)) + PB625 (0)
```

The swing, timing and contact that follow are M9 (SIM_PITCH_MODEL.md).

## Baserunning

### Offensive manager (FUN_68054b0a) [refereed: 6,889]

Runs once per pitch for the batting side (gated by FUN_6803cc73, which always returns 0 in FastSim). Each roll sets a
bit in the play flags at view+0x83:

```
v2 = steal(2) * PB157 (100) / 100;  if mod(100) < 100 - speed(runner on 1st): v2 = 0;  if mod(100) < v2: flags |= 0x41
v3 = steal(3) * PB157 / 100;        if mod(100) < 100 - speed(runner on 2nd): v3 = 0;  if mod(100) < v3: flags |= 0x42
h  = hit_run() * PB158 (100) / 100; if mod(100) < h: flags |= 0x10   (hit and run)
else: s = sacrifice() * PB159 (100) / 100; if mod(100) < s: flags |= 0x80   (bunt)
q  = squeeze() * PB160 (60) / 100;  if mod(100) < q: flags |= 0x20
```

So a steal needs two rolls: a speed gate (a runner with speed 70 passes 70% of the time) and the steal chance.

### Steal chance (FUN_68052bd5, base 2 or 3) [refereed: 30,000]

Additive, clamped to 0..100. Zero unless the manager allows running (flag 0x40) and the base ahead is open.

```
v  = PB[54 + strikes + 3*balls]                       count table (stealChance{balls}{strikes}Count)
v += speed bucket:  speed <= PB66 (29) -> PB70 (-80), <= PB67 (39) -> PB71 (-40), <= PB68 (59) -> PB72 (-5),
                    <= PB69 (79) -> PB73 (15), else PB74 (20)
v += hold bucket (pitcher's hold rating): <= PB75 (19) -> PB79 (30), <= PB76 -> PB80 (15), <= PB77 -> PB81 (5),
                    <= PB78 (79) -> PB82 (-20), else PB83 (-40)
v += PB85 (base 2) / PB84 (base 3) when the pitcher is not facing the runner (6800f680 == 0)
v += PB86 when not in the windup (680556c0 == 0);  v += PB87 when the pitcher is wild (6804935e)
base 2: outs == 2 -> CH >= PB88 (59): +PB89 (10); CH <= PB90 (39): +PB91 (-10)
        outs < 2  -> CH >= PB92 (59): +PB93 (-5); CH <= PB94 (39): +PB95 (5)        (CH = batter contact)
base 3: +PB[96 + outs] (-15/-10/-50);  CH >= PB99 (59): +PB100 (-5)
v += PB102 (-50) when the batting side trails by PB101 (3) or more
```

### Hit and run (FUN_68053248) [refereed: 26,472]

Gate: runner on 1st, 3rd empty, outs < 2, batter flag 6802fd50 clear. Then, clamped 0..100:
`PB103 (25)` + score (`< -2` PB104, `== -2` PB105, `== +1` PB106, `> +1` PB107) + PB108 (-45) when 1st and 2nd are
both occupied + runner speed bucket (PB109-111 thresholds -> PB112-115) + batter contact bucket (PB116-118 -> PB119-122)
+ batter power bucket (PB123-125 -> PB126-129, high power lowers it) + PB130 (-30) for a wild pitcher + count
(3 balls PB131, else 2 strikes PB132, else even count PB133, else 0-1 PB134).

### Sacrifice bunt (FUN_680537ad) [refereed: 16,872]

Gate: outs < 2, strikes < 2, runner on 1st, 3rd empty, contact <= PB135 (69) and power <= PB136 (39). Then:
`PB137 (10)` + PB138 (50) if the batter is a pitcher + PB139 (-25) with one out; when the manager is "close"
(68039356): + PB140 (30), + PB143 (-25) if CH <= PB141 and PH <= PB142, + PB144 (30) with 0 outs and 1st+2nd
occupied, + PB147 (10) with 1 out and CH >= PB145, PH >= PB146; a pitcher batting with CH <= PB148 and
PH <= PB149 adds PB150 (20). Clamped 0..100.

### Squeeze (FUN_68053b36) [refereed: 13,236]

Gate: runner on 3rd, exactly one out, manager flag, CH <= PB151 (59), PH <= PB152 (39). Then count: balls + strikes
< 2 -> PB153 (15); 1-1 or 2-0 -> PB154 (10); else 0. + PB156 (10) if the runner on 3rd has speed >= PB155 (69).

### Lead off (FUN_680508a4, runner) [refereed: 131]

```
lead = LEAD[0][mod(8)]   (.data 68097570: row 0 = 1 1 1 1 1 1 2 3; rows 1-3 exist but FastSim always uses row 0)
if no "go" sign (flag 0x40 at runner+0x74 clear):
    keep the lead only if lead < HOLD[runner+0x7d / 20][pitcher rating (+0x93) / 20]   (.data 68097590, 5x5, 1..4)
else (or when kept): the manager flag 0x40 for the side must be set, else no lead
no lead: runner+0x86 = -1
lead > 0: state +0x82 = 3, +0x7e = 4, jump timer +0x87 = 4 - (rating >> 4) - lead + 400 / runner+0x105
```

### Pickoff score (FUN_68036d52) [refereed: 10,990]

Gate: runner on 1st with 2nd empty, or runner on 2nd with 3rd empty. Result (a short, not clamped):
`PB10 (0) + steal(target base) + PB11 (-10) + PB12 (5) * lead + (4 - clamp(pitches since last throw, 0, 4)) * PB13
(-10)`, where lead = runner+0x7e of the runner being held and the pitch counter is the short at mgr+0x34ce.

### Advancement on balls in play [decompile]

No table. Every frame FUN_680519e0 moves each runner along the base path at a speed from the speed rating;
FUN_6804faa1 (runner AI) decides to go, hold or return by comparing the runner's time to the next base with the
ball's state (in the air / fielded) and the fielder's throw time. Tag-ups, extra bases and throw-outs are outcomes
of that race.

## Defensive manager

### Situation rolls (FUN_680382d9, once per pitch) [refereed: 12,500]

Builds the defensive play flags (word at mgr+0x3496):

```
clear 8
if FUN_6803cc73() < 3:
    if 68011570: clear 0x65
    if 68011570 or cc73 == 0: set fielder positioning (6803853e), 68035228
    if mod(100) < charge(0) * PB46 (50) / 100: set 1           (charge 1st base)
    if mod(100) < charge(2) * PB46 / 100:      set 1 | 4       (charge 3rd base)
    if cc73 == 0:
        if mod(100) < pickoff():  set 0x20
        if mod(100) < pitchout(): set 0x40
        if 0x400 not yet set:
            p = pitch_around()
            if p > 0: d = mod(100); if d < p * PB47 (100) / 100: set 0x200 (intentional walk) elif d < p: set 0x100
            set 0x400 (decided for this batter)
```

### Infield charge chance (FUN_68036a52, side 0 = 1st, 2 = 3rd) [refereed: 25,000]

R is the rating word at player+0x83 (FUN_68039140). Zero when the score is lopsided (lead > 1 or deficit > 2) unless the team flag 68049594 says otherwise; requires a
bunt situation (runner on 2nd with 3rd open, or on 1st with 2nd open) and outs < 2:
`PB0 (0) / PB1 (-20)` + `(50 - R(mgr+0x67 player)) * PB2 (25) / 100` + `(R(charging fielder, slot
mgr+0x349e+4*side) - 50) * PB3 (25) / 100` + sacrifice()
+ PB4 (-20); at 3rd also + PB5 (20) with 1st and 2nd occupied and + PB6 (20) with a runner on 3rd.

### Pitch around chance (FUN_680371f8) [refereed: 3,904]

From inning > PB24 (5), with a runner on 2nd or 3rd and 1st open, a close game (deficit within the count of bases-
loaded-able runners + 2, lead < 3): `PB25 (15)` + inning (7-8 PB26, 9+ PB27) + power-bucket comparison of the batter
and the on-deck hitter (batter 2+ buckets better PB28 (65), 1 better PB29, equal PB30/31, 1 worse PB32, 2+ worse PB33)
+ the same on contact (PB34-39) + PB41 (20) if the on-deck GF rating <= PB40 (50) + outs (PB42-44) + PB45 (15) with
2nd and 3rd occupied. Clamped 0..100. Rating buckets are rating / 20 (FUN_68038b39: <20, <40, <60, <80, else 4).

### Pitchout score (FUN_68036e91) [refereed: 6,889]

Considered only when the manager flag is set and the score is close (the gate depends on which of hit-and-run /
steal 2nd / steal 3rd is likeliest and on the runners). Fires if the best steal chance >= PB14 (25) or the hit-and-run
chance >= PB15 (25): `PB16 (25)` + balls (0: PB17 5, 1: PB18 0, 2: PB19 -25, 3: PB20 -100) + inning 8 PB21 (5) /
9+ PB22 (10) + PB23 (-5) at home.

### Fielder positioning (FUN_6803853e) [refereed: 13,239 (st11)]

Sets the defensive alignment object 0x680c8f98 once per pitch: per mode g (0 and 1) slots a (0..3), b (0..3) and
c (0..4). Mode 0 gets (a, 2, 2): a = 2 when FUN_68039356 && FUN_6800f640 && margin >= -1 && outs <= 1, else 1 when
FUN_68039356 && !FUN_68038ed0, else 0 when FUN_68032ff0 == 0 || outs > 1, else 3 (margin = FUN_68056985(3) -
FUN_68056985(4), outs = FUN_68002c80). Then the pull band moves c: the batter's pull rating (FUN_68038e90) >=
PB48 defPosHighPull (80) one way, <= PB49 defPosLowPull (19) the other, FUN_6802fd50 == 1 (batter side) swapping the
directions. Mode 1 gets (0, b, 2): b = 0 late and level (this+0x348e == 0, inning > 8, FUN_6800f640, margin 0, outs
< 2), 1 or 3 on two margin tests, else 2; on b = 2 the power rating (FUN_68038e70) moves b up at >= PB52
defPosHighPower (85) and down at <= PB53 defPosLowPower (20) (b = 3: only the down test). Then the pull band again,
and on b = 2 / 3 the pull-extra band (PB50 / PB51, 60 / 39) and a b move when FUN_6800f1e0 and FUN_6800f1c0 differ by
more than one. Shifts clamp at the ends. Checked: every getter, PB read and slot write in order, and the object's 0x20
bytes from +9 after the call. Spec: work/spec/FUN_6803853e.md.

## Fielding

### Fielder selection (FUN_68022ea4) [refereed: 508 (st11)]

Walks the ball's flight path one point per step (FUN_6803997d), counting steps n. A point counts when it is reachable
(FUN_68023be0 false) and its height z <= 0xe0. At the first counting point every fielder (this+0xb+4k, k = 0..8)
scores time to the point (FUN_68003988 on fielder+8: distance / speed) + reaction delay (FUN_68021fca), as 16-bit
values; the lowest score below n wins, the first on ties. No score below n: the next counting point. When the path
ends (FUN_6803997d false or FUN_68002e30) the nearest fielder wins (FUN_6802644a). The delay per position is
PB475-483 (delayBase*) plus FA * PB484-492 (delayFAPct*, negative: better fielders react sooner), loaded into the
tables at 6808e940.. by FUN_68023dd3. No RNG.

### Catch roll (FUN_68014f7b) [refereed: 5,470]

```
gates (ball catchable, fielder in position, manager flag 0x20, ...) -> 1 directly when closed
base   = POS_ADJ[position] + FA / max(PB461 (10), 1) + PB460 (90)
         POS_ADJ = PB468 1B 4, PB469 2B 3, PB470 3B 1, PB471 SS 2, PB466 P 0, PB467 C 2, PB474 RF 4, PB473 CF 4, PB472 LF 4
chance = base + PB462 (-60) diving, else + PB463 (-60) leaping
if time to the ball < 1.0 s (680072f0 < 10 tenths): chance += PB464 (-10) + (10 - tenths) * PB465 (-3)
draw = mod(100);  draw < chance -> caught
else if draw >= base -> error (a miss with base > draw <= chance is a clean hit: the ball was not catchable)
     error kind = count of ERR_TYPE[row] <= mod(100), row by play (3 / 0 / 2 / 1), ERR_TYPE (.rdata 6808a100) =
     [[30,50,75,85], [15,40,60,90], [25,55,70,90], [15,40,70,90]]  -> kind 0..4 (0 = fumble, higher = worse)
```

### Throw (FUN_6805dd30) [refereed: 2,584]

```
max distance = (FA-AS byte +0x98 * PB494 (200) / 100 + PB493 (100)) * 30; a longer throw is cut to it
if distance > 0x546 (45 ft) and the manager flag 0x20 is set:
    good = GOOD_POS[position] (PB497-505) + FA * PB496 (10) / 100 + PB495 (90)
    if not chance(good): wild throw: distance += range(150, 300), angle += range(-0x4000, 0x4000)
throw speed (FUN_6805d960) from distance and arm strength
```

## Pitching changes

### Starter is done (FUN_6804a357) [refereed: 8,736]

```
thresh = PB[173 + clamp(inning, 1, 9)]   (starterToastThreshInn1..9: -20 -25 -21 -17 -13 -7 -1 5 11)
       + PB183 (6) * (inning - 9) past the 9th + PB184 (2) for the away team
       + PB185 (-4) if the bullpen has thrown < 50 * clamp(9 - inning, 1, 8) pitches, PB186 (4) if > 100 * that
score  = stamina stat 7 + 3 * (inning - 1)            (DAT_68096db0 = 1 per out)
       + outs this inning (or 3 when the inning is over for the home team)
       + 2 * own runs - 2 * opponent runs + 2 * clamp(inning - 4, 0, inning)
replace when score < thresh
```

### Reliever is done (FUN_6804a64d) [refereed: 3,151]

True when the pitcher is flagged (6804935e) or his stamina left (stat 3 - stats 10 - 11) is below
`(K stat 0x20 + 51) * PB187 (10) / 100`, or when the lead is within PB188 (2) .. PB189 (0) and the pitcher has
status bit 0x10.

### Relief selection (FUN_68043d91) [refereed: 3,904]

Keeps the warming reliever (status bit 8) unless the current pitcher is fine: the starter by FUN_6804a357, a
reliever by FUN_6804a64d, fatigue state <= 2, not ahead late (inning > 7 with a lead), and no injury (stat 2 == 0).

## Injury

### Injury check (FUN_6802bde7, event) [refereed: 29,890]

`injured iff injuryRNG.mod(PB[852 + event]) == 0` on the separate injury RNG (DAT_68113af0), so the chance per event
is 1 / PB: run through 1st 1/7500, throw 1/6500, run bases 1/8500, field fly 1/1800, grounder 1/2200, hit by pitch
1/28, batter swing 1/6500, batter hit 1/180, catcher hit 1/180, collision 1/90, slide head-first 1/350, feet-first
1/550, player hit 1/180, overuse 1/300, warm-up pitch 1/2200 (PB852-868).

### Injury type (FUN_6802be53, category) [refereed: 6]

`draw = mod(999) + 1`; the first entry of the category's table in injury.dat (SIM.DAT) with threshold >= draw names
the injury; days out = its duration roll (dice), rerolled once with the reroll dice when below reroll_below; then the
after-effect roll. Full replay including the RNG sequence.

## Fatigue

### Stamina left (FUN_680491d4, team, pitcher) [refereed: 5,000]

```
cap  = K stat 0x20 + 51
left = clamp(stamina (H stat 3) - (pitches G10 + G11), 0, cap) * 100 / cap
for the pitcher in the game, when G4 < G3: left = G[x] * left / G[y] (scaled by the current outing)
```

### Fatigue state (FUN_68049d61) [refereed: 5,000]

```
G4 < G3 / 2 -> 0 (cold),  G4 < G3 -> 1 (warming),  left > PB172 (20) -> 2 (ready),
left > PB173 (0) -> 3 (tired, ratings x PB616/617),  else 4 (exhausted, x PB618/619)
```
(G3 = warm-up needed, G4 = warm-up done; warm-up seconds per pitch PB167-171.)

## Validation

re/sim_model.py replays every record of a trace; `rng` checks every main and injury RNG draw replays from the
recorded state, chaining through each nested target's own record. Trace st7 (184,489 records, days 11-14 of the 1997
association, v1 probes) and st8 (307,718 records, the same days, v2 probes: 27 targets, 148 hooks, 1.39 GB). Every row
is ok with 0 bad; skipped rows are records whose nested target or events were dropped by a trace cap.

| check | st7 | st8 (v2) |
|---|---|---|
| rng | 184,096 ok, 393 overflow | 293,154 ok, 14,550 overflow, 14 nested dropped |
| steal | 30,000 | 58,991 |
| hit_run / sacrifice / squeeze | 26,472 / 16,872 / 13,236 | 25,000 / 17,487 / 13,585 |
| offman / pitchout / pickoff | 6,889 / 6,889 / 10,990 | 12,500 / 12,500 / 13,585 |
| pitch | 12,492 | 12,743 |
| catch / catch_adj | 5,470 / 51 | 5,599 / 51 |
| inj_check / inj_type | 29,890 / 6 | 25,000 / 5 |
| stamina / fatigue | 5,000 / 5,000 | 5,000 / 5,000 |
| def_mgr / def_strategy / def_ratings | | 12,500 / 25,000 / 3,904 |
| lead / throw | | 131 / 2,584 |
| replace_p / relief_chk / relief_pick | | 8,736 / 3,151 / 3,904 |

Trace st11 (simtrace v3, 2026-10-08: variable-length records, 112 probes, flat logging for the two looping targets,
the alignment writes as L events, the flight-path z in FUN_6803997d's X): 117,187 records, every check above ok with
0 bad, plus positioning 13,239 and find_fielder 508 (v2 records overflowed on both). find_fielder needs the z, so it
is skipped on traces without it.

Trace quirks the referee absorbs, all from re/simtrace.c: ev() drops an X event identical to the one before it (two
calls of the same getter with the same argument in a row show up once; Tape.x reuses the previous value); a probed
target past its record cap writes its events inline into the caller's record (the throw skips past throw_speed's);
unprobed virtual calls (the throw's +0x1c, +0x3c and the lob's +0xc) put their callees' events at top level
(Tape.skip_to).

Season gate (2026-10-08): a 49-day season run in the work copy, stopped at the June 13 amateur draft, then
Association > Statistics: all 14 NL teams match the STATS.DAT decoder exactly on AB, R, H, HR, RBI, BB and SO (98 of
98 cells). re/simdays.py now runs the draft itself (notice OK, Start/Resume Draft, Draft Delay Time 0,
Start/Continue Draft) and sims on; checked from the saved June 13 state through June 15.

## Rating mappings (M11)

| rating (object offset) | used by | mapping | nonlinearity |
|---|---|---|---|
| speed (FUN_68038e10) | steal, hit and run, squeeze, offensive manager | 5 buckets (PB66-69 / PB109-111 / PB155) -> additive PB adjust; also a linear gate `mod(100) < 100 - speed` zeroes the steal | step function + linear gate |
| contact CH (batter +0x95, 68038e50) | steal, hit and run, sacrifice, squeeze, pitch around | buckets (thresholds 39/59/69/79) -> additive; max-CH gates for bunts | step |
| power PH (batter +0x99, 68038e70) | hit and run, sacrifice, squeeze, pitch around | buckets, high power lowers bunt / hit-and-run | step |
| pitcher hold (68055650) | steal | 5 buckets PB75-78 -> PB79-83 | step |
| fielding FA (+0x97) | catch, throw, reaction delay | catch: +FA/10 linear; throw: +FA*10/100; delay: FA * PB484-492 / 100 | linear, clamped by chance |
| arm strength AS | pitch velocity, throw range | velocity + AS * PB390.. / 100; throw range (AS * 200 / 100 + 100) * 30; fatigue scales AS | linear, then x0.9 / x0.75 by fatigue |
| control CO, movement MO, pitch rating | pitch execution | effCO = CO * rating * 70 / 10^4; miss = mod(100) - effCO | product of two ratings |
| stamina (H3, K0x20) | stamina left, fatigue, starter/reliever done | linear percent of (K0x20 + 51) | thresholds at 20 / 0 |
| pull / power (positioning) | fielder positioning | thresholds PB48-53 | step |

## Worked examples

Generated by `re/sim_examples.py TRACE 5` (each record shown passed its model).

### v2 trace (st8), 2 per target

How to read the pitch around record #14520: inning 6 > PB24 (5), runner on 2nd only, close game, so the base is PB25
(15). Batter power 99 / contact 57 and on-deck power 77 / contact 55 bucket to 4, 2, 3, 2; power buckets differ by 1:
+PB29 (35); contact buckets equal but the batter's contact is not lower: nothing. On-deck 68038eb0 = 49 <= PB40 (50):
+PB41 (20). No outs: +PB42 (-50). 15 + 35 + 20 - 50 = 20 = 0x14, the recorded return. Throw #1243: distance 3658 is
under the arm cap, over 0x546 with manager flag 0x20 set, so chance(GOOD_POS + FA * PB496 / 100 + PB495) = C1(95)
succeeds; 3658 >= PB772 * 30 (900) so the ball goes by throw_speed(3658).

### replace_p (2 examples)

```
#101 this=0x6812bf66 arg=0x0 ret=0x6812f500
    X31[6800f200](68143ee0)=0x68143e01 PB[174]=-20 PB[175]=-25 PB[176]=-21 PB[177]=-17 PB[178]=-13 PB[179]=-7
    PB[180]=-1 PB[181]=5 PB[182]=11 X31[6800f200](68143ee0)=0x68143e01 X53[68020a50](68143ee0)=0
    X3[68002c80](68143ee0)=0x68143e00 X107[68056985](68143ee0,1,0)=0 X31[6800f200](68143ee0)=0x68143e01
    X107[68056985](68143ee0,0,0)=0 G[f170:7]=0
#104 this=0x68114ba8 arg=0x0 ret=0x68117800
    X31[6800f200](68143ee0)=0x68143e01 PB[174]=-20 PB[175]=-25 PB[176]=-21 PB[177]=-17 PB[178]=-13 PB[179]=-7
    PB[180]=-1 PB[181]=5 PB[182]=11 PB[184]=2 X31[6800f200](68143ee0)=0x68143e01 X53[68020a50](68143ee0)=0
    X107[68056985](68143ee0,0,0)=0 X31[6800f200](68143ee0)=0x68143e01 X107[68056985](68143ee0,1,0)=0 G[7476:7]=0
```

### relief_pick (2 examples)

```
#103 this=0x6812bf66 arg=0x0 ret=0x681433d0
    X97[68049663](6812bf66)=0x6812bf01 Z<replace_p> X93[68041d83](6812bf66)=0x1957660 F[f170]=2
    X31[6800f200](68143ee0)=0x68143e01 X93[68041d83](6812bf66)=0x1957660 G[f170:2]=0
    X93[68041d83](6812bf66)=0x1957660 X93[68041d83](6812bf66)=0x1957660 X86[6803d9f9](6812eed6,0)=0x6812f14c
    X92[68041d33](6812bf66,-1)=0
#16931 this=0x6812bf66 arg=0x0 ret=0x68131cfe
    X88[6803dec5](68131f9c,8)=1 X97[68049663](6812bf66)=0x6812bf00 Z<relief_chk> X93[68041d83](6812bf66)=0x1958430
    F[697c]=0 X31[6800f200](68143ee0)=0x68143e08 X107[68056985](68143ee0,1,0)=0 X107[68056985](68143ee0,0,0)=2
    X93[68041d83](6812bf66)=0x1958430 G[697c:2]=0 X93[68041d83](6812bf66)=0x1958430
    X93[68041d83](6812bf66)=0x1958430 X86[6803d9f9](681366e2,0)=0x68136958 H[66e2:0]=1718
    X94[68047c98](6812bf66,1718)=1 G[c344:3]=21 G[c344:4]=0 G[c344:3]=21 H[c0aa:3]=23 K[c756:32]=57 G[cc80:3]=19
    G[d5bc:3]=39 G[def8:3]=39 G[e834:3]=42 G[f170:3]=39 G[faac:3]=20 G[faac:4]=0 G[faac:3]=20 H[f812:3]=103
    K[febe:32]=85 G[3e8:3]=16 G[3e8:4]=0 G[3e8:3]=16 H[14e:3]=112 K[7fa:32]=68 G[d24:3]=19 G[d24:4]=0 G[d24:3]=19
    H[a8a:3]=124 K[1136:32]=73 G[1660:3]=18 G[1660:4]=0 G[1660:3]=18 H[13c6:3]=127 K[1a72:32]=76 G[1f9c:3]=16
    G[1f9c:4]=16 G[1f9c:3]=16 H[1d02:3]=104 K[23ae:32]=53 G[28d8:3]=23 G[3214:3]=17 G[3b50:3]=23 G[448c:3]=23
    G[448c:4]=0 G[448c:3]=23 H[41f2:3]=93 K[489e:32]=42 G[4dc8:3]=15 G[5704:3]=16 G[5704:4]=0 G[5704:3]=16
    H[546a:3]=94 K[5b16:32]=43 G[6040:3]=36 G[697c:3]=22 G[72b8:3]=15 G[7bf4:3]=15 G[8530:3]=23 G[8e6c:3]=19
    G[97a8:3]=18 G[a0e4:3]=16 X107[68056985](68143ee0,0,0)=2 X107[68056985](68143ee0,1,0)=0
    X92[68041d33](6812bf66,10)=0x1957bb0
```

### def_strategy (2 examples)

```
#106 this=0x680a21e5 arg=0x0 ret=0x68140000
    X3[68002c80](68143ee0)=0x68143e00 X69[68032ff0](680a57b7)=0 X37[6800f600](680a57b7)=0 X38[6800f640](680a57b7)=0
    X107[68056985](68143ee0,3,0)=0x68143e00 X107[68056985](68143ee0,4,0)=0x68143f00
#2813 this=0x680a21e5 arg=0x0 ret=0xffffffeb
    X3[68002c80](68143ee0)=0x68143e01 X69[68032ff0](680a57b7)=0x19318c8 X37[6800f600](680a57b7)=0
    X38[6800f640](680a57b7)=0 X107[68056985](68143ee0,3,0)=0x68143f00 X107[68056985](68143ee0,4,0)=0x68143e00
    PB[0]=0 PB[2]=25 X80[68039140](1931240)=0x193003f PB[3]=25 X80[68039140](1959008)=0x195003c Z<sacrifice>
    PB[4]=-20
```

### def_ratings (2 examples)

```
#113 this=0x680a21e5 arg=0x0 ret=0x0
    X31[6800f200](68143ee0)=0x68143e01 X3[68002c80](68143ee0)=0x68143e00 X107[68056985](68143ee0,3,0)=0x68143e00
    X107[68056985](68143ee0,4,0)=0x68143f00 X69[68032ff0](680a57b7)=0 X37[6800f600](680a57b7)=0
    X38[6800f640](680a57b7)=0 X36[6800f570](680a57b7)=0 PB[24]=5
#14520 this=0x680a21e5 arg=0x0 ret=0x14
    X31[6800f200](68143ee0)=0x68143e06 X3[68002c80](68143ee0)=0x68143e00 X107[68056985](68143ee0,3,0)=0x68143e00
    X107[68056985](68143ee0,4,0)=0x68143f00 X69[68032ff0](680a57b7)=0 X37[6800f600](680a57b7)=0x1931960
    X38[6800f640](680a57b7)=0 X36[6800f570](680a57b7)=1 PB[24]=5 X19[68009610](68143ee0)=0
    X96[68049594](68114ba8)=0 PB[25]=15 X76[68038e70](1931780)=99 X75[68038e50](1931780)=57
    X76[68038e70](1931638)=77 X75[68038e50](1931638)=55 X72[68038b39](680a21e5,99)=4 X72[68038b39](680a21e5,57)=2
    X72[68038b39](680a21e5,77)=3 X72[68038b39](680a21e5,55)=2 PB[29]=35 X78[68038eb0](1931780)=49 PB[40]=50
    PB[41]=20 PB[42]=-50
```

### def_mgr (2 examples)

```
#114 this=0x680a21e5 arg=0x0 ret=0x680a567b
    X85[6803cc73](68114948,1,0)=0 X14[68005ec0](680a567b,8)=0x20000 X42[68011570](680a2158)=0x680a2101
    X14[68005ec0](680a567b,101)=0x20000 X42[68011570](680a2158)=0x680a2101 Z<positioning> X71[68035228](680a21e5)=9
    PB[46]=50 Z<def_strategy> M1(100)=21 PB[46]=50 Z<def_strategy> M1(100)=68 Z<pickoff> M1(100)=84 Z<pitchout>
    M1(100)=92 X23[680098e0](680a567b,1024)=1025 Z<def_ratings> X2[68002c40](680a567b,1024)=0x20400
#297 this=0x680a21e5 arg=0x0 ret=0x400
    X85[6803cc73](68114948,1,0)=0 X14[68005ec0](680a567b,8)=1024 X42[68011570](680a2158)=0x680a2101
    X14[68005ec0](680a567b,101)=1024 X42[68011570](680a2158)=0x680a2101 Z<positioning> X71[68035228](680a21e5)=9
    PB[46]=50 Z<def_strategy> M1(100)=77 PB[46]=50 Z<def_strategy> M1(100)=90 Z<pickoff> M1(100)=45 Z<pitchout>
    M1(100)=56 X23[680098e0](680a567b,1024)=1024
```

### throw (2 examples)

```
#1243 this=0x1ef5a0 arg=0x1931c90 ret=0x0
    X1[68002bf0](680a1f88,2028972)=8932 X8[680030c0](1931ca8,1)=0 X28[6800a4a0](1ef63d,1746371792)=0x78b0731
    X0[68002bb0](1ef63d,2028972)=3658 PB[494]=200 PB[493]=100 X52[6801e71c](680ca168)=0x680ca168
    X46[680155c0](680ca168)=0 X33[6800f270](68114948,1,32)=1 PB[496]=10 PB[495]=90 C1(95)=1 PB[772]=30
    Z<throw_speed> X20[68009690](6809f515,85)=85 X14[68005ec0](1ef5b8,110)=128 X9[68003fcb](1ef5a8,0)=0
    X8[680030c0](1ef5b8,512)=512 X59[68026380](680d26b0,13)=0 X59[68026380](680d26b0,12)=0x1ef868
    X56[680249f4](1ef868,7)=0 X57[68024af3](1ef5a0,0)=0
#14342 this=0x1efb30 arg=0x1ef5a0 ret=0x1efb30
    X1[68002bf0](680a1fb4,2030396)=-32768 X8[680030c0](1ef5b8,1)=0 X28[6800a4a0](1efbcd,1746371792)=0xebf0008
    X0[68002bb0](1efbcd,2030396)=3929 PB[494]=200 PB[493]=100 X52[6801e71c](680ca168)=0x680ca168
    X46[680155c0](680ca168)=0 X33[6800f270](68114948,0,32)=1 PB[496]=10 PB[495]=90 C1(93)=1 PB[772]=30
    Z<throw_speed> X20[68009690](6809f515,90)=90 X14[68005ec0](1efb48,110)=0x20090 X9[68003fcb](1efb38,0)=0
    X9[68003fcb](1efb38,3)=0 X8[680030c0](1efb48,512)=512 X59[68026380](680d26b0,13)=0
    X59[68026380](680d26b0,12)=0x1ef868 X56[680249f4](1ef868,7)=0 X57[68024af3](1efb30,0)=0x1efb30
```

### lead (2 examples)

```
#14333 this=0x19318c8 arg=0x0 ret=0x8
    M1(8)=0 X23[680098e0](193193c,64)=1 X100[68050ae0](1931240)=0 X19[68009610](68143ee0)=1
    X33[6800f270](68114948,1,64)=1 X104[68050b90](19318c8)=1 X100[68050ae0](1931240)=0 X40[6800f780](1931240)=75
#15666 this=0x19318c8 arg=0x0 ret=0x6
    M1(8)=6 X23[680098e0](193193c,64)=0 X19[68009610](68143ee0)=0 X33[6800f270](68114948,0,64)=1
    X104[68050b90](19318c8)=8 X100[68050ae0](1931240)=0 X40[6800f780](1931240)=96
```

### relief_chk (2 examples)

```
#16450 this=0x6812bf66 arg=0x0 ret=0x0
    X93[68041d83](6812bf66)=0x1958430 X93[68041d83](6812bf66)=0x1958430 X93[68041d83](6812bf66)=0x1958430
    H[66e2:3]=51 G[697c:10]=0 G[697c:11]=0 K[6d8e:32]=0 PB[187]=10 X95[6804935e](6812bf66)=0
    X107[68056985](68143ee0,1,0)=0 X107[68056985](68143ee0,0,0)=2 PB[188]=2 PB[189]=0
#17742 this=0x6812bf66 arg=0x0 ret=0x1
    X93[68041d83](6812bf66)=0x1957bb0 X93[68041d83](6812bf66)=0x1957bb0 X93[68041d83](6812bf66)=0x1957bb0
    H[1d02:3]=104 G[1f9c:10]=2 G[1f9c:11]=15 K[23ae:32]=53 PB[187]=10 X95[6804935e](6812bf66)=1
    X107[68056985](68143ee0,1,0)=0 X107[68056985](68143ee0,0,0)=2 PB[188]=2 PB[189]=0
```
