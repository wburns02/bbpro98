# progress.md (lane: code)

## Round 1 (2026-10-08)
Result: voldat.py written; real referee logic PASS on day1 + day2 (run through tools/localref.py, see below).

What I did / learned
* The GDO event grammar comes straight from FastSim's FEVENT module: FUN_6801f748 is a debug printer for the event
  records with the name tables in FastSim.dll (strings read from the PE with a tiny VA->file-offset reader).
  Types 0..8 with fixed sizes in words 2,41,15,7,3,4,4,5,6 (0 enter, 1 exit, 2 plate appearance, 3 substitution,
  4 team event, 5 pitching, 6 batting, 7 fielding, 8 injury). Parses all 23 games exactly to the payload end.
* Box score replay: batting stat codes (AB,B1,B2,B3,HR,RBI,BB,K,..,R,SB) and pitching codes (BFP,..) are plain
  per-event increments; pitcher outs = putout fielding events charged to the pitcher on the mound of the fielding team.
  23/23 box scores match (rows with all-zero counted columns are dropped).
* GDI layout from the decompiles: 0x1ea (490) per team block + 49-byte game block; strings/offsets from LineUp
  FUN_6b00b870, roster/lineup arrays from FastSim FUN_68040a7e, team option checkboxes from FastSim FUN_6806938c with the
  dialog strings (Injuries, Fatigue, DH Rule, Use Ratings, Fielding Errors, Base Stealing, Pitch To Center), weather
  from the Game Options dialog. ADI is enciphered with the GDI seed: date serial x2, game index, 3 zero bytes.
* Unknown-meaning bytes are kept as `_spare_*` keys (derived, but the encoder honours them).

Referee
* The real jail (systemd-run + bwrap) cannot run on this box (no user scope bus). `tools/localref.py` imports the
  real gamebkref with jailutil.jail swapped for a plain `python3 -I voldat.py` subprocess:
  `python3 tools/localref.py [-v]` -> PASS ({"day1": 9 box scores, "day2": 14}); `python3 tools/stress.py N` runs N
  extra random edit-test seeds per file (0 failures for N=12).

Current referee output (tail, via tools/localref.py):
  {"day": "day1", "ok": true, "box_scores": 9}
  {"day": "day2", "ok": true, "box_scores": 14}
  PASS

Open / next ideas
* Real meanings: park_geometry triples, slot_rank, bullpen pair roles, game_class, rain/wind-shift bytes, flags byte of
  pitch events (tags CL SP PLH BLH, only on stat 19).
* Holdout risks: unseen event kinds (types >8), chunk tags other than GDI/ADI/GDO, extra-inning games (handled up to 30
  innings), SH events (not in the visible data; counted as no AB), pitcher changes in the middle of a plate appearance.
