# Where the team nickname comes from

World Series text prints "the Chicago Cubs <No Name>": %1 of the champion
format string ("Led by Coach %2, the %0 %1 capture the %8 by %9 the %4 %5 ...")
is the team's nickname field, and Lahman builds leave it empty. Everything below
is from the BBShell decompile (`/mnt/nvme/bbpro98/index/BBShell/_all.c`, cited
by function address and line) and decoded ASN t records.

## 1. The team object, the record, and every write of the nickname

The (runtime) team object holds five fixed strings:

- +0x1c city/name, +0x38 nickname, +0x54 manager, +0x70 abbreviation, +0x80
  location. Set by `FUN_6804ba30` (record -> object, _all.c 59398) and copied
  back by `FUN_6804bb30` (object -> record, 59457); setters `FUN_6804a960`
  (58136), `FUN_6804a9c0` (58166), `FUN_6804aa20` (58196) all wrap
  `FUN_68047d50` (string_copy, 54554). The t record maps to those offsets as
  `FUN_6804ba30` reads it (_all.c 59422-59426, 59427-59428):

  | object | raw t record offset | field |
  |---|---|---|
  | +0x1c | 0x12, 16 chars + NUL | city/name |
  | +0x38 | 0x23, 16 chars + NUL | nickname |
  | +0x54 | 0x34, 17 bytes | manager |
  | +0x70 | 0x45, 3-byte field | abbreviation |
  | +0x80 | 0x4a (param_1+0x4a) | location |
  | stadium member at object +0x94 | 0x53, 0x1d | stadium name, city8 |
  | +0x9c block | 0x7d, 44-byte field | misc block (copied verbatim by build.py too, build.py:594) |

  Verified against decoded bytes: a 256-byte t payload with city at 0x12,
  manager at 0x34, abbrev at 0x45, stadium at 0x53, city8 at 0x74 (probe over
  stock `MLBPA97.ASN` and `_DEFAULT.ASN` under `/mnt/nvme/bbpro98/work_install2/Assn/`,
  decoded with `work/lahman/asnfile.py AsnFile`).

### Where the strings come from at load

`FUN_6804b8c0` (SIM lineup, "load_roster_from_records", 59317) and
`FUN_6804b9a0` ("read_records_into_fields", IO path, 59363) both call
`FUN_6804ba30` / `FUN_6804bc10` to fill a team object from a raw 256-byte t
payload before the roster/lineup objects are attached. The payload is the
enciphered 't' member of the .ASN file itself (seeded per file, decoded with
`work/lahman/asnfile.py AsnFile`), nickname at plain offset 0x23 - there is no
separate nickname file or VOL lookup in this path. `FUN_6804a610`
(57743, callers 6803bf10 and 680482c0) then pushes the object down into the
roster/lineup member at `*(int *)this + 0x98`, and `FUN_6804b8c0`'s roster load
(`set_roster_from_list` via `FUN_68078450`) reads team stats and positions from
raw arrays `param_5`/`param_3` after the team object is set. UNVERIFIED which
association-load function `FUN_6804a610`'s caller `6803bf10` ultimately is
(UI vs Season module vs startup); the data flow shown here is inside BBShell.

### Is it ever saved?

`FUN_6804a690` (57774, "reset_lineup") calls `FUN_6804bb30` (object -> record
buffer) and `FUN_6805bce0` (write the buffer to the record chain). So the team
object strings are written back to an ASN t record there (and in
`FUN_6804b7e0`, 59241). Where `FUN_6804a690` is called on the save path
association close vs lineup rebuild is not pinned down: UNVERIFIED.

### Which screen writes +0x38 (FUN_6802c2a0)?

`FUN_6802c2a0` ("apply_options_to_object", _all.c 33452) copies four text
gadget strings from a dialog object into a team record object:
0x1c from dialog +0xb4 (`FUN_6804a980`, _all.c 33456/58146), **0x38 from
dialog +0xe0** (`FUN_6804a9e0`, 33458/58176), +0x70 from dialog +0x10c
(`FUN_6804aaa0`, 33460), +0x80 from dialog +0x138 (`FUN_6804aa40`, 33462);
each pair is bracketed by `FUN_68043540(&g_GadgetMgr, id)` which reads the
edited text out of gadget 0x1d/0x1e/0x1f/0x21 into the dialog slot (labeled
"get_gadget_text" in that decompile), then calls the setter into the team
object. Its only
caller is the league-data dialog handler `FUN_6802b100` ("options_screen_
handler", 32822), i.e. the "Association Data / League Team Data" screen. The
nickname is an editable text box there, applied when the screen closes or the
user hits the apply gadget (`FUN_6802c2a0` also runs before screens
0x30/0x31/0x45 in that handler, _all.c 32922-32957). The setter it uses,
`FUN_6804a9e0` (58176), is reached only from `FUN_6802c2a0` - so UI edits are
the only source of +0x38 at runtime besides the record copies
`FUN_6804b9a0`/`FUN_6804bc10` at association load.

## 2. Would a stock MLBPA97 champion also print <No Name>?

Yes, by the code path, not a guess. The champion formatter `FUN_68012160`
(_all.c 13681, labeled "build_champ_message") zeroes its argument slots
local_48[0..9] (13723-13728) and then `FUN_68012580` ("copy_team_strings",
13943) fills three of them from one team object: %0 = `FUN_6804a960` (city,
+0x1c), %1 = `FUN_6804a9c0` (nickname, +0x38), %2 = `FUN_6804aa20` (manager,
+0x54). The % substitution walks the format string and, for digit d, takes
`local_48[d-0x30]`; a NULL pointer or empty string substitutes the static
`s_<No_Name>_6808a740` (_all.c 13808-13811, 4 lines):
	```
	pcVar14 = local_48[(char)(cVar3 + -0x30)];
	if ((pcVar14 == (char *)0x0) || (*pcVar14 == '\0')) {
	  pcVar14 = s_<No_Name>_6808a740;
	}
	```
Decoded t records from stock MLBPA97 (_DEFAULT.ASN and MLBPA97.ASN, both
28 t records of 256 bytes, probed from work_install2) have the whole 0x23
field empty for every team including Atlanta (city "Atlanta" at 0x12, nothing
at 0x23; "Braves" appears in no plain file and in no t payload of the
install). The runtime team object gets +0x38 only from the t record at load
(`FUN_6804ba30`) and from the edit screen; the formatter never derives a
nickname from the city, so Sierra's own
1997 files print <No Name> on the World Series screen exactly like a Lahman
build does. UNVERIFIED whether any other screen consumes +0x38: the getter
callers in BBShell are 68012580 (champ text), 68020b40, 68036c40 and the
print/report functions; none that I read is a second nickname display, but I
did not read every report builder. Another possible source (a hardcoded
nickname list in a VOL or DLL, used only by some other screen) cannot be
ruled out from BBShell alone - the champ text path never consults one.

## 3. Smallest fix for Lahman builds

**Decision (orchestrator, 2026-10-14): not the build.py fix below.** Lahman builds already put the whole name
("Chicago Cubs") at 0x12, so a nickname at 0x23 would print "the Chicago Cubs Cubs". Stock files print <No Name> too.
The fix is src-latest/mods/champtext.c: it blanks s_<No_Name>_6808a740 (BBShell .data), so an empty argument prints
nothing and both stock and Lahman associations read "the Chicago Cubs  capture the World Series". The build.py
option below stays as the record of the alternative.

build.py (work/lahman/build.py:577) currently writes only
`put_str(q, 0x12, 32, team_name(t['name']))`. Write the nickname too:

```python
put_str(q, 0x23, 17, lahman_nickname(t['name']))
```

where `lahman_nickname` takes the last word of the Lahman name
("Boston Red Sox" -> "Red Sox"; "Chicago White Sox"; "Los Angeles Angels of
Anaheim" -> strip the trailing "of Anaheim"; "Boston Beaneaters" -> keep as is
if it has no recognizable split). `put_str` (work/lahman/asnfile.py:61) is
strcpy with NUL termination like the game's own field format, so a 17-byte
write is safe.

Risks:

- Long nicknames are clipped by `put_str` at 16 chars (safe, no overflow);
  the World Series text would show the clipped form. UNVERIFIED exact rendering.
- Stale bytes after the NUL (put_str keeps the tail) are always NUL today
  (verified above), so nothing regresses. Rebuilding a 30L association rewrites
  the t records anyway, so this rides the existing rewrite queue
  (`AsnFile.rewrite`, work/lahman/asnfile.py:45) with no new record types.
- Non-alphabetic finishes ("Beaneaters", "Pilgrims", "Federal League" teams)
  would now show up where before they did not. That is cosmetic.
- It writes to every t record's 0x23 field even when the nickname is empty
  (put_str with an empty string writes one NUL byte). That is byte-identical to
  the stock files' 0x23 bytes today (verified NUL above), so no existing data
  changes except for teams that get a nickname.

`FUN_6804bb30` (_all.c 59482) writes the nickname back from the object into the
record buffer, so a nickname written by build.py is round-tripped and, on the
League Team Data screen, editable by hand afterwards - the two paths share the
same field.
