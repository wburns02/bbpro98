# lane code: progress (FUN_6804faa1, runner AI update)

## Round 1 status (2026-10-08)
- `runner_ai.py` written. Referee (advisory run, `T3_LANE_ADVISORY=1`):
  `records 2500 ok 2500 | deep (past the early exits) 173 ok 173` and PASS.
- Fuzz (20000 random oracle/obj runs, outside the lane): no Python exceptions in any branch.

## What the function does (decompile + callees, all read)
- Gate: `6800f8f0` (the OnClose name is a false match: it is `FUN_680030c0(this+0x4341, 2)` on 0x680a2158). Returns when
  the bit is clear. 1435 dev records exit here.
- `6800a260` = action code at P+0xe. `6802a8b7` (unprobed, `advance_step`) walks the step counter P+0x18 through the
  action's table entry (count from `DAT_680d3f28 + code*8`), resets the action (`6802aa9f`) on flag 8.
- State `*(int*)(P+0x79)` must be 2, 3 or 4: dev has 1435 gate exits, 892 state exits, 173 records past both
  (state 2: 103, state 3: 42, state 4: 28 over all records past the gate).
- Action codes: 0x30-0x32 (group 1: flag-driven step, the "else if" arm, the IsTracking arm), 0x33-0x35 (group 2:
  moves P+0x64/P+0x66 by the lead/hold roll), 0x41 (group 3: reset).
- `CSplitterWnd::IsTracking` is `6800f780`: `*(int*)(DAT_680a224c + 0x105)` (probed, leaf). The name is right here.
- `68082999(&DAT_680a64b0, 5)` = RNG mod 5, one 'M' event (gen 0).
- Table counts: `DAT_680d3f28` is filled at load from `HHA.DAT` (magic 0x6969, then 64 eight-byte entries at offset
  2 + 8*code; the first word is the entry's width). `6802a33a` only reads it, `6802a50e` only at teardown, so the
  values are constant. Embedded as `COUNT` from `/home/will/bbpro98/BBPRO98_package/game/HHA.DAT`.
- Not model inputs: `game` and `mflags` (every read of them is a probe: 68009610, 6800f270, 6802fc40), and the
  P+0x74 / P+0x76 flag words (every read is a probe). Only `obj` and the oracle values are needed.

## Coverage of the dev records (line trace of runner_ai.py)
- Hit: gate, state 2/3/4 tests, the group-1 chain for 0x20/0x10/0x1/0x2/0x80 probes (no RNG), group 3 (0x41), the
  68033f70 == 1 arm, the tail 0x608 / 0x82 write.
- NOT hit in dev (transcribed from the decompile, unverified by the referee):
  - group 2 (0x33-0x35): no dev record has that action code.
  - `bcond` / IsTracking arm / `tracking_step`: `6800f780` never appears in dev top-level events.
  - the RNG 'M' events (68082999): none in dev, so the P+0x78 countdown reset is untested.
  - `advance_step` table path (0x12 nonzero, bit 0x4 and 0x100 clear): all 82 dev records with a nonzero table
    pointer have bit 4 set and return early, so `COUNT` never affects a dev branch.
  - the 0x10 arm when P+0x78 == 0 and the 0x2 arm's P+0x7e < 1 path.

## Choices made (for the audit)
- arg1 passed for `6800f270` and `6802fc40` (the `bVar1` index; dev shows zero high bytes, and the referee passes).
- `tracking_step` treats a zero divisor as a zero quotient (the game would fault there; no dev record reaches it).
- `count_of` returns 0 outside the 64 entries (unreachable: action codes are < 0x40 where the table is read).
- Helpers 6802a8b7 / 6802a6b1 / 6802aa9f are inlined; their probed calls are emitted in order.

## Open risks
- Holdout: the untested paths above (group 2, IsTracking arm, RNG countdown, table path). They rest on the decompile
  reading, which was checked line by line against the decompile text.
- COUNT correctness depends on the shipped HHA.DAT being the file the game loads (the same package, not verified in
  a run).
