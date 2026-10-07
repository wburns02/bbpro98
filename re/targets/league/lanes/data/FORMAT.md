# MLBPA97.ASN: the FPS Baseball Pro '98 league file, member by member

Container: FairCom c-tree Plus superfile, see `re/targets/ctree/lanes/data/FORMAT.md`
(codec `work/ctree.py`).  This file documents the *contents*: each data member's record
layout, byte by byte, with the evidence.  All offsets are payload offsets; "dec" means
after the game byte cipher (seed `f5dc`, `work/fpscipher.py`, plain = INV[stored]).

## Enciphering and the record key

* Two storage classes, per member:
  * **enciphered** members `a, l, d, t, r, xs`: every payload byte is stored as `T[plain]`.
  * **plain** members `s, tr, df, po`: stored as-is.  (Evidence: schedule bytes are clean
    0..31 integers with 0xff sentinels; `xs`/`t` garbage under the no-op reading.)
* **The record key is raw byte 0** (= `T[dec byte 0]`): team/roster/standings records carry
  the plain **team id 1..28** there, `l.dat` the league number 1..2, `d.dat` the division
  number 1..6, `a.dat` the association number.  Fresh league files additionally contain one
  unused *template* record per member with key **100** (`dec byte 0` = 0x51).  Proof: raw
  byte 0 of every live `t/r/xs` record is exactly 1..28 in ascending physical order in all
  eleven files (day01..09, _DEFAULT.ASN, MLBPA96E.ASN); the c-tree index `t.idx` has key
  length 1 over that byte, i.e. the game looks teams up by number.
* Physical record order within a member == key order for the 28-team members, and equals
  the tid order (cross-checked against the `d.dat` division membership and the box-score
  rosters, see "tid mapping").

## tid mapping (the ids the box-score H files use)

tid = the raw key byte = position of the team in `t.dat`.  The order is division order:

```
1-5   NL East    Atlanta, Florida, Montreal, New York (N), Philadelphia
6-10  NL Central Chicago (N), Cincinnati, Houston, Pittsburgh, St. Louis
11-14 NL West    Colorado, Los Angeles, San Diego, San Francisco
15-19 AL East    Baltimore, Boston, Detroit, New York (A), Toronto
20-24 AL Central Chicago (A), Cleveland, Kansas City, Milwaukee, Minnesota
25-28 AL West    Anaheim, Oakland, Seattle, Texas
```

`d.dat` stores these five-team lists explicitly; the names match real 1997 alignment.
Verified against the sim: every day k box score credits players to tid X that appear in
X's `r.dat` roster (100% over 2536 credits, day01..day09, with the `tr.dat` additions
below), and the W/L deltas match box-score results exactly.

## t.dat - team records, 28 x 256 bytes, enciphered

```
+0x00 u8    key (raw = tid; dec = INV[tid])
+0x01 3B    00 00 00
+0x04 u8    unknown (05 Atlanta, 0x30 Florida, 0x2c California-96E; stable per team)
+0x05 7B    01 x7
+0x0c 2B    00 00
+0x0e 4B    03 03 03 03
+0x12 str   team name, NUL-terminated, 40 bytes max (0x12..0x39)
+0x1a ..    day files: 32B of plain-stored junk (RAM pointers, template bytes);
            fresh files: zeros
+0x34/0x3a str  manager name, NUL-terminated (offset 0x34 in fresh files, 0x3a in
            simmed files; located by scanning for the last printable run in 0x30..0x44)
+0x45 str   3-letter abbrev (ATL, FLA, ...)  [fixed in all files]
+0x48 4B    00 00 00 00
+0x4c 4B    38 7e 00 64 (constant)
+0x50 3B    00 00 00
+0x53 str   stadium name, NUL-terminated (max 30)  [fixed in all files]
+0x71 3B    e5 00 00 (after the NUL + junk)
+0x74 8B    city file base name, "ATLANTA.", "MIAMI.DA" + NUL  [fixed in all files]
+0x7d 44B   team-colour/template block, stable per team and identical day vs fresh
            files; byte values {0x0b,0x1a,0x1b,0x25,0x26,0x28,0x29,0x2c,0x30,0x32}
+0xa9 2B    00 00
+0xac u32   per-team constant (1338 Atlanta, 830 Florida, ...); unchanged across days
+0xb0 ..    day files: plain-stored pointers/junk, rewritten by the sim; fresh: zeros
```

Evidence for the name field: "Atlanta" at 0x12 in every file; the referee's edit test
writes a new name there and the trusted c-tree codec still parses the file.

## xs.dat - per-team standings/status, 28 x 16 bytes, enciphered

```
+0x00 u8  key (= tid, raw)
+0x01 u8  wins            (verified: == schedule-derived wins on all 11 files)
+0x02 u8  losses          (verified: == schedule-derived losses on all 11 files)
+0x03 u8  counter (tracks W, lagged on the last day; meaning unconfirmed)
+0x04 u8  00
+0x05 u8  counter (grows with losses over the season; unconfirmed)
+0x06 u8  00
+0x07 u8  counter (grows slowly; unconfirmed)
+0x08..+0x0a 00
+0x0b u8  counter (tracks W closely; unconfirmed)
+0x0c u8  00/01 (1 seen on loss days)
+0x0d s8  current streak, signed (+2 = won 2 straight, 0xff = lost 1; verified pattern)
+0x0e u16 last-8-games win bitmask, LSB = most recent (0x01, 0x03, 0x07, ... verified
          against the day-by-day results of tid 1)
```

## s.dat - schedule + results, 2269 x 17 bytes, plain

2268 regular-season games (162 x 28 / 2) plus one special record: the all-star slot
(July 10, away = home = 0, byte15 = 2).  Fresh files have exactly 2268 records; the sim
adds the all-star record (and rewrites played games in place, which is why day files
carry ~37 tombstones).

```
+0x00 u8   0
+0x01 u8   month 3..9 (fresh _DEFAULT.ASN includes March games)
+0x02 u8   day of month 1..31
+0x03 u8   game slot of the day 0..13
+0x04 u16  aux0 (0 unplayed; ~700..2300 when played; meaning unknown - time/attendance?)
+0x06 u8   away team id (1..28); 81 games per team across the season
+0x07 u8   away runs, 0xff = not yet played
+0x08 u16  aux1 (as aux0)
+0x0a u8   home team id (1..28)
+0x0b u8   home runs, 0xff = not yet played
+0x0c u16  aux2 (as aux0)
+0x0e u8   played flag: 1 = scheduled, 0 = played
+0x0f u8   special flag: 0 = regular game, 2 = all-star placeholder
+0x10 u8   innings played (9 for every completed game seen, 0 unplayed)
```

Home/away orientation: byte 0x0a = home.  Verified against the H files: the box score's
side-0 team (listed first, the visiting side) == byte 6 in 102/104 games, and the s.dat
away/home counts are exactly 81 per team.  Cross-checks that hold on all 11 files:
`sum(W) == sum(L) == number of records with played flag 0` and each team's `W + L` equals
its played games; the games that flip to played between day k-1 and day k are exactly
that day's new box scores ({(tid, runs), (tid, runs)} pairs), verified day01..day09.

## r.dat - roster records, 28 x 294 bytes, enciphered

```
+0x00 u8   key (= tid, raw)
+0x01 u8   01
+0x02 40B  small values 1..60 (per-player small attributes; count varies by team)
+0x2a ..   u16 player ids and (id, flag) pairs, then 8-id lineup groups separated by
           0xffff, then zero padding; total window 0x2a..0x125 (126 u16 slots)
```

Roster semantics: the box scores credit player ids >= 100.  Taking **every u16 >= 100 in
the window at offset 42** covers 2529/2536 credits on day01..day09; the remaining 7
(three players: 833 Montreal, 2176 Boston, 1967 San Francisco, missing from `r.dat` all
season) appear only in `tr.dat` transaction records, whose team byte confirms the club.
The codec's roster = window ids union `tr.dat` ids for that team -> 2536/2536 = 100%.
(The exact sub-structure - active 25 vs. expanded 40 vs. lineup groups - is not needed
by the contract and is only partially mapped: 25 plain ids, then (id, 1) pairs.)

## tr.dat - daily transaction report, 21-byte records, plain

A small working table (36..44 live records on day01..day09, 0 in fresh files), rewritten
in place as the league day advances:

```
+0x00 u16 0
+0x02 u32 league day counter (0x0b2fce on day01, +1 per day; same value as a.dat day2)
+0x06 u16 player id            +0x08 u16 flag (0/1)   +0x0a u16 (0/1)   +0x0c u8 team
+0x0d u16 player id (repeat)   +0x0f u16 flag         +0x11 u16         +0x13 u8 team
+0x14 u8  kind (0x00, 0x02, 0x06 seen)
```

team = the tid (1..28) or 0xff (no team / free agent).  Records with the same player on
both halves look like "signed/assigned" lines.  Only the (player, team) pairs are used
by the codec (roster additions); the rest is exposed as-is.

## a.dat - association (league-office) record, 256 bytes, enciphered

```
+0x00 u8  key (raw 1; template copy has raw key 100)
+0x09 u8  00
+0x0a u32 day the association was created (0x0b1fc0 = 729024 in day files)
+0x0e u32 current league day (0x0b2fce = 733134 on day01, matches tr.dat, +1/day)
+0x12 str association name ("1997 MLBPA Opening Day"; "Default Association" in _DEFAULT)
+0x33/0x3a str second name ("The Dynamix Cup"; "N/A") - offset shifts like the manager
```

## l.dat - leagues, 2 x 46 bytes, enciphered

```
+0x00 u8  key (raw 1 = NL, 2 = AL)
+0x01 u8  league index 0/1
+0x02 u8  01
+0x03 u8  league index 0/1
+0x04 str league name ("National League"/"American League"), NUL-terminated
+0x25 str "NL"/"AL"
+0x28 3B  00
+0x2a 3B  division keys 1,2,3 (NL) / 4,5,6 (AL) into d.dat
+0x2d u8  0x39 (both leagues)
```

## d.dat - divisions, 6 x 30 bytes, enciphered

```
+0x00 u8  key (raw 1..6; order NL E/C/W, AL E/C/W)
+0x01 u8  league index 0/1
+0x02 u8  division index 0..2 within the league
+0x03 str division name ("Eastern"/"Central"/"Western"), NUL-terminated
+0x14 5B  team ids (1..28), 0 padding for 4-team divisions
```

## df.dat - 1 x 100 bytes, plain (present in day files, absent in fresh files)

```
+0x00 u32 0
+0x04 28 x u16  per-team values 257..507 (draft/assignment order? team-keyed)
+0x3c 22 x u16  0x0140 padding
```

## po.dat - 1 x 283 bytes, plain

```
+0x00 u8 x4  01 02 05 07 (four team ids? unchanged day01..day09)
+0x04 u16    7
+0x06 u32    league day (0x0b2f36, slightly behind tr.dat)
+0x0a ..     small counts and 0x40 padding; not mapped (exposed as hex)
```

## sp.dat - 21-byte records, plain, 0 live in all eleven files (749/1398 tombstones)

The member exists only in simmed files; every record is a tombstone.  Exposed as an
empty list; encode never touches it.

## What the codec does with all this

`league.py decode` emits: `teams` (tid, name, stored_name, w, l, roster, abbrev, manager,
stadium, city8, league_idx, division, field_ac, roster_window), `games` (the 2268-game
schedule with month/day/slot, home/away, played, hr/ar, aux words, innings), `specials`
(all-star slot), `leagues`, `divisions`, `association`, `transactions`, `draft`,
`playoff`, `sp`.

`league.py encode in.bin edited.json out.bin` copies in.bin and rewrites, in place, only
the bytes whose edited.json value differs from the file: t.dat name at 0x12 (+NUL), the
xs.dat W/L bytes 1..2, the r.dat id window when the roster set changes (no referee test
does that), and the s.dat game fields (month/day/slot/away/ar/home/hr/played/flag15/
innings/aux).  All writes go back through `T[.]` for the enciphered members.  Since no
key byte (raw byte 0, or s.dat bytes 0..3) and no record length ever changes, the c-tree
indexes stay valid without a rebuild, and a contract edit (rename, +3 wins, +1 run)
changes exactly 3 records.
