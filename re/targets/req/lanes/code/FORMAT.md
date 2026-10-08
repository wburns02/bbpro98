# MENU.REQ / DIAL.REQ — shell UI layout (FPS Baseball Pro '98)

> **Superseded 2026-10-07 by work/spec/REQ_FORMAT.md + work/reqcodec.py.** The container and round trip below are right.
> The header "frame indicators" are misaligned by one u16 (it is a u16 count + 12-byte rects x, y, w, h, bgColor, color;
> "entry" and "frameTerm" are the count and the next rect's color), "spare"/captionCount are two Dreqtext list
> counts, and most gadget field names are wrong (e.g. class 1 "spare" = edit maxLength, class 8 "tailKind" = cellH).
> Kept as the lane record.

Solved 2026-10-07, GLM `code` lane round 1. The codec is `req.py`; the JSON it
decodes is described in its docstring. Every field below is evidenced either by
the BBShell decompile (`/mnt/nvme/bbpro98/index/BBShell/_all.c`) or by a data
fact over all 114 requesters of the two files (052 menus + 79 dialogs; values
from `analyze.py` in the data lane).

## File container

    "IDX:" u32 idxLen (= 4 + 4n) | u32 n | u32 idx[n]

- `idx[0]` = byte offset of the first requester container; `idx[k]` = offset of
  requester k-1 + 8 (it points at the inner `"REQ:"` tag).  Verified on both
  files: MENU n=36, DIAL n=80 → 35 + 79 requesters (Claude's trusted parse
  `reqref.py::parse` checks this).
- The n-1 requesters follow back to back immediately after the IDX table,
  then the tail bytes (a single NUL in the shipped files).

Loader evidence: BBShell `FUN_680442b0` (line 52602) seeks the `"REQ:"` tag in
the resource via `FUN_68063450` (line 83022, tag matcher over a 25-byte tag
buffer at `this+0x4c`), reads 16 bytes of the container tag, then fills
`this+0xe..0x12` and calls requester-object vtable slots `+0x28`, `+0x2c`,
`+0x30`.  `FUN_68063a30/FUN_68051380` (called from `FUN_68063450`) manage the
seek state; the `0x6c/0x70/0x66` members are the current offset, the block
length and the tag-entry cursor, i.e. the table walk above.

## Requester container

    "REQ:" u32 (0x80000000 | bodyLen) {
        "REQ:" u32 hlen   <header bytes>
        "GAD:" u32 glen   <gadget section>
    }

`bodyLen` has bit 31 set (container flag).  Always exactly one header section
and one gadget section (472 + 674 = 114 requesters verified).

## Header section (per requester)

    u16 id          requester number; sequential 3..37 in MENU, 3..81 in DIAL
    s16 x, y        position on the 640x480 screen (menus at 0,0; dialogs centered)
    s16 w, h        size (640x480 for full screens; dialogs e.g. 554x275)
    u16 boxStyle    0x0f (full screen/bordered box, 46 requesters) or
                    0x0a (plain dialog, 68 requesters)
    u32 titleFlags  bit 0x40000 set on every requester = draw the title text;
                    bit 0x8 additionally set on all plain dialogs (0x0a).
                    Co-occurrence is exact: 0x0a ⇔ 0x40008, 0x0f ⇔ 0x40000.
    u16 spare       0 in every requester (kept as `_spare`, preserved by encode)
    u16 captionCount 0..5 title captions (35 MENU/68 DIAL have ≥ 1)
    captions × captionCount:
        s16 textX, textY    position of the caption inside the requester
                            (menus: y = 15 for in-screen titles, 150 for
                            "NA:" placeholders; dialogs: y = 5, x ≈ centered)
        u16 titleClass      0 = menu-screen title (34 captions), 1 = dialog
                            title (everything else)
        u16 titleFont       0 = small dialog title font, 5 = large title font
                            (the "applyCorrections"-era value seen on all
                            full-screen titles)
        char text[] + NUL   the caption ("Exhibition Play",
                            "Exit League Management?", ...; some headers carry
                            several: 'Set Criteria' dialog has groups).
    frame indicators (decorative line/arrow records; 79 DIAL panels draw these,
    no MENU requester has any):
        × n  u16 entry      shape kind (2/12 = rule lines seen, 11/4/6/10/8/1/18
                            also occur)
             s16 x, y       position inside the requester
             s16 w, h       extent (e.g. x=1, y=16, w=dialogW-2, h=1 = a
                            horizontal rule under the title bar)
             u16 flags      0, or 12 seen twice
        u16 tailTerm        0x0b after indicator records (65 requesters),
                            0x0c for 2 requesters, 0 when the requester has
                            neither captions nor indicators (12 DIAL panels).
                            Stored as the `frameTerm` content key.
Data fact for the walk: every requester header parses with this grammar
(captions + 12-byte indicators + terminator) with zero remainder — verified on
all 114 requesters by the codec round trip and by the referee's trusted parser.

## Gadget section ("GAD:" u32 glen)

    u16 count
    count gadget records:
        u8 type     control kind.  Observed (count over 2708 gadgets):
                    0 = static text/box, 1 = button, 2 = month/list item label,
                    3 = text row (list body), 4 = list column, 5 = state
                    label/prompt, 6 = panel/filler, 7 = heading, 9 = sheet
                    panel, 10 = edit field, 11 = arrow button, 13 = header
                    text, 15 = border segment, 16/17 = misc labels,
                    18 = cell header, 19 = row header, 20 = grid body,
                    21 = underline, 22 = (type 0 word) spacer, 23 = action
                    button, 24 = month cell.
                    Names are per the labels they carry: type 1 carries
                    'OK'/'Cancel'/'Continue' etc., type 11 the scrollbar arrows
                    (18x16), type 4/0x13 the list column bodies/headers.
        u8 class    record layout: 4 = labelled, 1/2 = link/scroll bar,
                    8 = list box body.  (The referee's trusted parser accepts
                    exactly these.)
        u16 id      gadget id, unique within the requester (1..331 seen); the
                    link fields below reference these ids.
        s16 x, y    position relative to the requester; y can be negative
        s16 w, h    size
        then by class:

### class 4 (labelled) — 12 bytes + label
        u16 hitFlags    0x40 (active), 0x50/0x60 (arrow/misc) seen
        u16 textFlags   0x24 (text drawn) / 4 (no text: buttons whose label
                        comes from the game)
        u16 linkA       0, or the sibling gadget id (e.g. OK ⇄ Cancel,
                        scrollbar arrow ⇄ its bar: 'OK' linkA=56 id=55,
                        'Cancel' linkA=55 id=56)
        s16 labelY      label y offset (0)
        s16 dataB       0, or the row/slot number (e.g. 'Team 1:' 0x29)
        u16 dataC       0 or 15 (label colour/style, 15 on every labelled
                        button)
        char label[] + NUL  the gadget text (may be empty; e.g. the plain
                        heading records carry 64/128 spaces or a blank).

### class 1 (link/tab) — 14 bytes
        u16 hitFlags    0x40 (or 0 for a stub)
        u16 argKind     4
        u16 focusItem   row/list item id the click maps (0x1d, 0x11, ...)
        u16 drawStyle   0x0c
        u16 destClass   0x0d
        u16 mapsTo      the gadget id whose text this row updates (e.g. the
                        'Team N' label id 32)
        u16 spare       0x20 (or 0x18/0x08 for stacked columns)

### class 2 (scroll bar) — 14 bytes
        u16 hitFlags    0x42 (or 2)
        u16 argKind     4
        u16 linkTo      the gadget id at the other end of the bar (40/12/68/64)
        s16 scrollPage  0x64 = 100 (the scrollable page/count)
        u16 drawStyle   0x0a / 0x0c
        u16 valClass    0x11
        u16 mapsTo      the linked gadget id

### class 8 (list box) — 16 bytes
        u16 hitFlags    0x40
        u16 argKind     4 (or 0x24 for list headers)
        u16 param       the row/first-row id (0x3f = 63 'title row'), or 0
        u16 argKind2    4
        u16 rowStep     1 (rows), or 0/9
        s16 colGap      3 / 0x0c / 2 / 0 — the gap between columns, or for a
                        column body the own previous-column link slot
        u16 colWidth    the column body width (0x32 = 50 on 'Amateur Draft',
                        repeated per column), or the row height (0xa4/0x8e)
        u16 tailKind    0x0b (column body, chained), 0x0c/0x0d (last column,
                        chained differently), 0x11 (row body)

Data facts: class census is
MENU {class 4: 1365, class 8: 177, class 1: 37, class 2: 31} and
DIAL {class 4: 626, class 8: 26, class 1: 63, class 2: 28}.  The per-class
byte counts are exactly 12 + len(label) + 1 (class 4), 14 (1/2), 16 (8); the
referee's FIXED table is {1: 26, 2: 26, 4: 24, 8: 28} counting the shared
`type/class/id/x/y/w/h` prefix.

## List-box column chain (the known edit case)

DIAL requester 13 (League Statistics) and MENU 12/17 (Standings/Roster
columns) chain their columns: a type-4/class-8 body record's `colGap` slot
carries the PREVIOUS column id (4-1 = 3 means the first column links to the
header); the type-0x13/class-4 header's `linkA` slot carries the NEXT header
id.  Ids run 4, 3, 2, ... down the row and jump back up for the next group.

## Editing rules (how the encoder rebuilds)

- The encoder always writes the canonical layout: requesters back to back,
  the IDX table recomputed, the tail bytes kept verbatim.
- Every JSON leaf besides `_spare` is content: a caption may be added/moved/
  relabelled (the caption count in the header is recomputed), a gadget may be
  added/deleted/moved/relabelled with any length (the GAD count and length
  are recomputed), and `frameIndicators` entries may be edited.
- Labels/captions are stored as latin-1 text (what the file holds); control
  bytes inside an existing label (a quirk of type-7 headings that reuse part
  of the record as padding) are preserved verbatim.
- `frameTerm` must be 0x0b/0x0c when indicators exist and 0 otherwise —
  decode preserves the shipped value; the encoder's default (0x0b with
  indicators, 0 without) matches every shipped requester.
