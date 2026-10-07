# FUN_6803aad7 (void __fastcall FUN_6803aad7(short *param_1))

DRAFT (GLM-Flash, unaudited)

**1) PURPOSE**
Simulates one batted-ball trajectory frame-by-frame (launch → flight → bounces → roll → rest, max 299 frames) with surface/weather-dependent friction and restitution, recording a waypoint list and key event frames/positions.

**2) INPUTS**
Struct at `param_1` (decompile uses `short*`; offsets below are byte offsets):
- `+0x1C/+0x20/+0x24`: ball position x,y,z (z = height; written `<<6` in arc mode)
- `+0x28/+0x2C/+0x30`: velocity x,y,z
- `+0x34/+0x38/+0x3C`: acceleration vector (gravity; built by `FUN_6803a8e9`)
- `+0x0C`: flags; bit `0x20` (tested via `FUN_680030c0`) selects precomputed-arc mode (guess)
- `+0x06` block: launch data read by `FUN_6807d31c` (direction, guess); `+0x56`: launch speed (guess)
- `+0x52`: frame count N, `+0x54`: arc-height param, `+0x88/+0x8A`: arc target x,y (all meanings guessed from use)
- `+0x00–0x0B`, `+0x58/+0x5C`: saved at entry, restored at exit; `+0x58/+0x5C` rewritten on bounce/wall hit (event state, guess)
- Globals: `0x68114948` (surface/park state: turf flag, wet flag, temperature), `0x681783e8` (field-bounds/wall data), `DAT_6808a55c` (wall-bounce percent table, signed char, indexed by `FUN_6803be80`)
- PB: `rollFrictionGrass`=9, `rollFrictionTurf`=7, `bounceVertGrassPct`=30, `bounceHorizGrassPct`=75, `bounceVertDirtPct`=35, `bounceHorizDirtPct`=80, `bounceVertTurfPct`=40, `bounceHorizTurfPct`=80, `bounceWetAdjust`=−3, `bounceHotAdjust`=3, `bounceColdAdjust`=−3

**3) RULES**
1. Init: `waypoint[0]` (array at `+0x60`, 12 B/entry: 3 ints x,y,z) = position; `+0xE70–0xE77`=0; `+0xE78/+0xE7C/+0xE80/+0xE84/+0xE88` = −1. Velocity built from speed `+0x56` and `FUN_6807d31c(+0x06)` via `FUN_68011090`/`FUN_6807d14c`; accel zeroed then `FUN_6803a8e9`.
2. Arc mode (bit `0x20` set): `+0xE78 = +0x52`. For i = 1..N: pos.xy from `FUN_6803bbe0(·,6)`/`bba0`/`bc10(i)`/`bc50(N)`/`bb60` toward `(+0x88,+0x8A)`; height = (`FUN_68009440(+0x54, FUN_6803bb40(i·2^15, N))` << 6) + `waypoint[0].z`; store `waypoint[i]`. Then velocity = `FUN_6803bab0(waypoint[N] − waypoint[N−1])` (delta; helper semantics guessed).
3. Main loop, ≤299 iterations, while `FUN_6807c959(vel)` ≠ 0 OR height ≠ 0. Per iteration:
   - **3.1 Roll** (height==0 && vz==0): friction = `PB[rollFrictionGrass]`; if `FUN_6803be30(0x68114948)`≠0 → `PB[rollFrictionTurf]`. Velocity copy → `FUN_6803bc90` → `FUN_6803bce0(friction)` → `FUN_6803bd30(·,1000)`; each component that becomes 0 is reset to **1** if original <0, **−1** if original ≥1, else left 0 (as coded); result added back to velocity. If `FUN_6807c959(vel)` < 256 (`0x100`) → velocity = 0 (rest).
   - **3.2 Airborne** otherwise: vel += accel; `FUN_6803a941(ball, vel, frame)`; `FUN_6803aa6b(vel)`.
   - **3.3 Landing marker**: if `+0xE78`==−1 && vz < 1 && height < 14401 (`0x3841`) → `+0xE78` = frame (pre-increment index).
   - **3.4** frame++; pos += vel.
   - **3.5 Bounce** (height < 0): if `+0xE7C`==−1 → `+0xE7C` = frame. With P = `waypoint[frame−1]`, h = height (<0), D = P.z − h: `pos.x −= (P.x − pos.x)·h/D`; `pos.y −= (P.y − pos.y)·h/D` (integer division); height = 0.
     Surface (in order): dirt if `FUN_6805989d(FUN_68002ce0(param_1[0], param_1[1]))`; else turf if `FUN_6803be30(0x68114948)`==1; else grass → (vert,horiz) = `PB[bounceVert/Horiz{Dirt|Turf|Grass}Pct]


CONTINUATION (GLM-Flash, covers the decompile after the stop point; unaudited):

1. Wet tweak: if `FUN_6803cce3(0x68114948)`&0xff ≠ 0 → `vert += FUN_68003170(0x2ed)`; `horiz += FUN_68003170(0x2ed)`.
2. Temp tweak: `t = FUN_6803bdb0(0x68114948)`; `t < 0x32` → both `+= FUN_68003170(0x2ef)`; `t ≥ 0x51` → both `+= FUN_68003170(0x2ee)`; `0x32..0x50` → none.
3. Bounce scale: `vel.x = FUN_68005b80(vel.x, horiz)`; `vel.y = FUN_68005b80(vel.y, horiz)`; `vel.z = FUN_68005b80(-vel.z, vert)` (vel x/y/z at `param_1+0x14/0x16/0x18`).
4. Clamp: `vel.z = FUN_6800f0e0(vel.z, 0, 0xc80)`.
5. Dead bounce: if `vel.z < 0x100` → `param_1[0x12..13]=0`, `param_1[0x18..19]=0`; if `*(param_1+0x740)==-1` → `= frame`.
6. Post-bounce reset: `FUN_68002ca0(local_d4,0,0,0)` → `*(param_1+0x2c)`/`param_1[0x2e]`; zero vec `FUN_68011090(·,0,0,0)` → `FUN_68014b50(param_1+0x1a,·)`; `FUN_6803a8e9(param_1+0x1a)`.
7. Per frame: `FUN_6803a588(param_1)`.
8. Off-field: if `FUN_6805990d(&DAT_681783e8, param_1)` == 0:
9. — crossing test `FUN_68059a13(&local_3c, param_1, local_b0)`&0xff == 0 → if `*(param_1+0x744)==-1` → `= frame`.
10. — else (crossed): `FUN_6803a5cd(param_1)`; `FUN_68002ca0(local_e8,0,0,0)` → `*(param_1+0x2c)`/`param_1[0x2e]`.
11. — wall reflect: `s = FUN_6807c6f4(param_1+0x14)`; `s = FUN_68005b80(s, (char)(&DAT_6808a55c)[FUN_6803be80(0x681783e8)])`; `FUN_6807c661(param_1+0x14, s, local_b0[0])`; if `*(param_1+0x73e)==-1` → `= frame`; if `*(param_1+0x742)==-1` → `= frame`.
12. Trail: `local_3c = *param_1`; `local_38 = param_1[2]`; `FUN_68014b50(param_1 + frame*6 + 0x30, param_1+0xe)`.
13. Loop exits when `FUN_6807c959(param_1+0x14)`==0 && height==0, or frame ≥ 299; then `*(param_1+0x73a) = frame`.
14. First-bounce spot: `CString::CString(&local_34)`; `FUN_6803a4fc(param_1,·,*(param_1+0x73c))` → `FUN_68002ce0(·)` → `*(param_1+0x22) = *ret`.
15. If `*(param_1+0x744)` ≠ -1: `FUN_6803a4fc(param_1,·,*(param_1+0x744))` → `FUN_68002ce0(·)` → `*(param_1+0x26) = *ret`.
16. Rest spot: `FUN_6803a4fc(param_1,·,*(param_1+0x73a))` → `FUN_68002ce0(·)` → `*(param_1+0x24) = *ret`.
17. Restore scalars: `*param_1 = local_18`; `param_1[2] = local_14`; `*(param_1+3) = local_5c`; `param_1[5] = local_58`; `*(param_1+0x2c) = local_10`; `param_1[0x2e] = local_c`.
18. Restore vecs: `FUN_68014b50(param_1+0xe,&local_54)`; `FUN_68014b50(param_1+0x14,&local_68)`; `FUN_68014b50(param_1+0x1a,&local_74)`; `*(u8*)(param_1+0x746) = 1`; return.


CORRECTIONS (audit pass 2, GLM-Flash vs decompile; findings verified shaped, apply when editing):
- 6803aad7: arc-mode target is `FUN_680110d0(&local_7c,(int)param_1[0x22],(int)param_1[0x23])` — bytes +0x44/+0x46, not "+0x88/+0x8A"; decompile never reads +0x88/+0x8A.
- 6803aad7: roll zero-reset applies only to x/y (`local_90`←+0x28, `local_8c`←+0x2C); vel z (+0x30, `local_88`) is copied but never ==0-checked — "each component" is wrong for z.
- 6803aad7: only the `FUN_6803a4fc(·,·,*(param_1+0x744))` refresh of `local_34` is inside the `+0x744 != -1` branch; `FUN_68002ce0` and the `*(param_1+0x26)` (byte +0x4C) store execute unconditionally — draft item 15 misplaces the branch boundary.
