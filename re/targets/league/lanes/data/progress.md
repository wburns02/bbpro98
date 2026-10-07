# progress.md - league lane "data", round 1

## Status: referee-equivalent checks PASS on all 11 visible files

`league.py` (13.3 KB, stdlib only) implements `decode in.bin out.json` and
`encode in.bin edited.json out.bin`.  The box has no systemd user bus, so
`asnref.py` itself cannot run here (jailutil's `systemd-run --user` fails before my
code is even started); `scripts/reflocal.py` runs the *same* asnref checks with the
bwrap jail replaced by a direct `python3 -I -B` run.  Output:

```
day01..day09  ok, roster_hit 100% (212/212 ... 346/346), edit test ok on day05, day09
_DEFAULT.ASN  ok, edit test ok
MLBPA96E.ASN  ok
PASS
```

Decode takes 0.17 s per file (limit 600 s); the JSON is ~390 KB (limit 64 MB).

## What the file is (full detail in FORMAT.md)

* Container = c-tree superfile (solved).  Two storage classes: members a/l/d/t/r/xs are
  stored enciphered with the f5dc byte cipher; members s/tr/df/po are stored plain.
* **The raw byte 0 of every a/l/d/t/r/xs record is the plain record key** (T[dec0]):
  tid 1..28 for team/roster/standings records, 1..2 leagues, 1..6 divisions, 100 for the
  unused template records in fresh files.  This killed all alignment guesswork.
* tid 1..28 = t.dat order = division order (NL E/C/W then AL E/C/W); confirmed by
  d.dat's explicit team lists, by the 81 home games per tid in the schedule, and by
  2536/2536 box-score roster credits.
* t.dat (28 x 256, enc): name at 0x12 (NUL-terminated), abbrev at 0x45, stadium at 0x53,
  city8 at 0x74, manager at 0x34 (fresh files) / 0x3a (simmed files) - located
  dynamically; tail holds plain-stored junk in simmed files.
* xs.dat (28 x 16, enc): **byte 1 = wins, byte 2 = losses** (exact match with
  schedule-derived records on all 11 files; this is what makes the +3-wins edit work);
  byte 13 = signed streak, bytes 14..15 = last-8-games win bitmask, several other
  small counters unmapped.
* s.dat (2269 x 17, plain): month/day/slot, away tid + away runs (0xff = unplayed),
  home tid + home runs, played flag (byte 14: 0 = played), special flag (byte 15:
  2 = all-star placeholder with tids 0/0), innings (byte 16).  2268 regular games +
  1 all-star slot.  Away = byte 6 / home = byte 10 verified against the H files'
  side-0/side-1 order (102/104, plus the exact 81/81 home split).
* r.dat (28 x 294, enc): player-id window at 42.. (126 u16 slots).  Roster = every
  u16 >= 100 in the window, unioned with tr.dat (player, team) pairs -> 2536/2536 = 100%
  of box-score credits (r.dat alone misses 3 players all season: 833 Montreal,
  2176 Boston, 1967 San Francisco - they only ever appear in tr.dat).
* tr.dat (21 B, plain): league-day counter + two (pid, flags, team) entries + kind byte.
* a.dat (association: created-day u32, current-day u32, two strings), l.dat (2 leagues),
  d.dat (6 divisions with 5-team lists), df.dat (28 per-team u16s + padding, plain),
  po.dat (unmapped, exposed as hex), sp.dat (0 live records everywhere).

## encode design (why it is exact)

encode copies in.bin and patches, in place, only the bytes that differ from
edited.json: t.dat name at 0x12 (+NUL), xs.dat bytes 1..2, r.dat id window (roster
edits; never exercised by the referee), s.dat game fields.  Every write to an
enciphered member goes back through `T[.]`.  No key byte (raw 0, or s.dat bytes 0..3)
and no record length changes, so the c-tree indexes stay valid without a rebuild:

* encode(x, decode(x)) == x byte-for-byte on all 11 files (verified with cmp).
* the referee's edit (rename + 3 wins + 1 run) changes exactly 3 records (limit 8),
  and the trusted work/ctree.py parse of the edited file is consistent.
* bulk-edit stress test (rename every team, +1/+2 every W/L, +1 run on all 104 played
  games, replace one roster id per team): edited JSON round-trips exactly, trusted
  parse still clean, second-generation identity holds.

## Decisions worth remembering

* FRANCHISE_ALIASES = {'California': 'Anaheim'}: MLBPA96E.ASN (a 1996-season file)
  stores "California" but the referee's known-28 names require "Anaheim" (the 1997
  rename).  decode reports the canonical name and keeps the stored string in
  `stored_name`; encode only touches the field when the canonical name is edited, so
  round-trip identity on 96E still holds.  This is the one piece of non-structural
  knowledge in the codec and it is documented in FORMAT.md.
* The game filter for `games` = real tids both sides and flag15 == 0.  A month-window
  filter (4..9) broke _DEFAULT.ASN because real schedules open in March; dropped.
* Roster-change detection compares the edited set against decode's roster
  (window union tr.dat) so the round-trip never rewrites r.dat.

## Open / not needed for the referee

* Meaning of xs.dat bytes 3..12 (several W-correlated counters), s.dat aux0/1/2
  (values ~700..2300 when played - game time or attendance?), t.dat +0x04 and +0xac
  (per-team constants), the 0x7d colour/template block, r.dat's exact sub-structure
  (active 25 vs expanded 40 vs lineup groups), po.dat.
* The manager/second-string offset shift between fresh (0x34) and simmed (0x3a) files;
  the codec scans for the last printable run instead of trusting a fixed offset.
* sp.dat is all tombstones in every file seen; its live layout is unknown.

## How to re-verify

```
python3 league.py decode <day>/MLBPA97.ASN out.json
python3 league.py encode <day>/MLBPA97.ASN out.json rt.bin   # cmp with the original
python3 scripts/reflocal.py <target_dir> <this lane dir> -v  # asnref checks, jail stubbed
```

The real `asnref.py` needs a systemd user bus (absent in this shell); the driver
environment has it (the c-tree lane's referee ran fine there in round 2).
