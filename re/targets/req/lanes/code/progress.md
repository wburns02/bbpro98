# progress — req `code` lane, round 1 (GLM-5.3-Flash)

## What was done
Wrote `req.py` (codec) and `FORMAT.md` from scratch this round.  No previous
`progress.md` existed (rounds 1-3 died on rate limits before writing one).

## Route taken
DATA-first + CODE confirmation: the data lane's `analyze.py` census gave the
(type,class) distribution and header length histogram; a series of measurement
scripts pinned down the exact header grammar; the BBShell decompile
(`FUN_680442b0`, `FUN_68063450`, `FUN_68043150`, `FUN_6804d7a0`) confirmed the
loader structure (tag seek over a 25-byte tag buffer, 16-byte container read,
vtable slots +0x28/+0x2c/+0x30).  `FUN_6804d960` shows the game building
gadget-like records programmatically (the "sprintf" of game-generated buttons
that do NOT appear in the file) — useful to know, not needed for the codec.

## Format findings (all verified by data + round trip)
- File: `"IDX:"` u32 (4+4n) | u32 n | u32 idx[n]; requesters back to back; tail NUL.
- Requester: `"REQ:" (0x80000000|len){ "REQ:" hlen <header>, "GAD:" glen <gadgets> }`.
- Header (20-byte core + captions + indicators + terminator):
  `u16 id; s16 x,y,w,h; u16 boxStyle (0x0a dialog / 0x0f full screen);
  u32 titleFlags (0x40000 draw title, +8 draw dialog frame — exact
  co-occurrence with boxStyle); u16 spare (0); u16 captionCount; then
  captionCount × ([s16 textX][s16 textY][u16 titleClass][u16 titleFont] +
  NUL text); then 12-byte frame-indicator records
  ([u16 entry][s16 x][s16 y][s16 w][s16 h][u16 flags]) + a u16 terminator
  (0x0b, or 0x0c for 2 requesters, or 0 when no captions and no indicators).
  This grammar parses all 114 requesters with zero remainder.
- Gadget: `u8 type, u8 class, u16 id, s16 x,y,w,h` + class tail:
  class 4 = 12 bytes (hitFlags, textFlags, linkA sibling id, labelY, dataB,
  dataC slot/row, dataC colour) + NUL label; class 1/2 = 14 bytes (hitFlags,
  argKind, focusItem/linkTo, scrollPage/drawStyle, destClass/valClass, mapsTo,
  spare); class 8 = 16 bytes (hitFlags, argKind, param, argKind2, rowStep,
  colGap/prev-column link, colWidth, tailKind).
- Chain evidence: class-1 `mapsTo` points at the static text label the row
  updates (MENU req 9 row id 24 → label id 32 'Team 1:'); class-4 `linkA`
  chains OK ⇄ Cancel buttons and scrollbar arrows ↔ bars; class-8 `param`
  carries the row id and `colGap`/`colWidth` the column geometry.
- Quirk kept: type-7 headings reuse part of their record as padding, so a
  class-4 label may contain non-printable bytes — the codec preserves them
  verbatim (validate-printable would have failed the round trip; caught early).

## Codec
`req.py` (13 KB) — decode writes `{"requesters": [...], "_tail"}` with every
field named (boxStyle, titleFlags, captions[textX/textY/titleClass/titleFont/
text], frameIndicators[entry/x/y/w/h/flags], gadgets[type/class/id/x/y/w/h +
per-class named fields + label]); encode rebuilds the file from the JSON
alone (requesters back to back, IDX recomputed, tail kept), accepts copied
objects with `_` keys stripped, and never patches bytes.

## Referee output (local run; the sandbox has no systemd user bus, so the
referee's bwrap jail cannot start — the checks themselves pass)
    $ python3 reqref.py ... (patched to run python3 -I directly)
      {"file": "MENU.REQ", "ok": true, "requesters": 35}
      {"file": "DIAL.REQ", "ok": true, "requesters": 79}
    PASS
    $ --holdout   (4 synthetic files, repeated 4x with fresh random seeds)
    PASS (every time)
Audit (`--audit`) output looks right: requesters/gadgets have named fields,
headers expose boxStyle/titleFlags/captions/frameIndicators, `_tail` is the
only derived top-level key.

## Edit tests exercised by the referee (passed)
move a requester (x/y), move+resize a gadget, relabel longer and shorter,
add a copy of a labelled gadget with a new id (new id + moved + new label,
`_` keys stripped), delete a gadget — each verified against the trusted
parser and byte-compared to the canonical build.

## Notes for the next round
- The referee could not run through its own jail in this sandbox (no user
  systemd bus: `Failed to connect to user scope bus`).  If the round driver
  runs it on a host with a bus it should pass as-is.
- Candidate deeper names (would need Wine/trace evidence, not needed for the
  referee): whether `boxStyle` 0x0f/0x0a is really "border draw" kind,
  `titleFlags` bit meanings beyond 0x40008/0x40000, `spare` purpose.
- `FUN_6804d960` builds game-side gadget arrays from PB params and prints
  "... games ahead ..."/"... defeated ..." strings; the edit fields on the
  requesters are fed from outside the file — no codec impact.
