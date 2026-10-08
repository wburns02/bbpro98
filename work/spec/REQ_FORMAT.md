# MENU.REQ / DIAL.REQ: shell UI layouts (SHELL.VOL)

Codec: `work/reqcodec.py` (decode/encode JSON, byte-exact round trip on both files, reqref PASS + holdout). Container
and round trip from the req GLM code lane; Claude remapped the header lists and every gadget field from the BBShell GUI
library (the same library is linked into EZShell, LineUp and Upstats, each with its own `REQ:REQ:` loader). The lane's
"frame indicators" were misaligned by one u16 (the list count read as the first record's field) and its gadget field
names were guesses; see the superseded note in re/targets/req/lanes/code/FORMAT.md.

## Container
`"IDX:" u32 (4 + 4n) | u32 n | u32 idx[n]`. idx[0] = offset of the first requester, idx[k] = requester k-1 + 8 (the
inner `REQ:` tag). n - 1 requesters back to back, then tail bytes (one NUL). Requester: `"REQ:" u32 (0x80000000 | len)`
holding `"REQ:" u32 hlen <header>` and `"GAD:" u32 glen <gadgets>`. MENU has 35 full screens, DIAL 79 dialogs.

## Header (BBShell FUN_680442b0, requester vtable slot 0)
| Off | Field | Code |
|---|---|---|
| 0 | u16 id | read in the 16-byte block, not kept |
| 2 | s16 x, y, w, h (640x480) | copied to the requester +0xe..+0x15 |
| 10 | u16 style (0x0f full screen, 0x0a dialog), u32 styleFlags (0x40000; 0x40008 on dialogs) | read in the 16-byte block, not used by this loader |
| 16 | text list `labels` (empty in every shipped requester) | slot +0x28 FUN_68044370 into +0xb4 |
| .. | text list `captions` | FUN_68044370 again into +0xb0 |
| .. | rect list `rects` | slot +0x2c FUN_68044440 |

Text list = u16 count, then per text (Dreqtext, load 0x680723d0): s16 x, s16 y, u16 color, u16 font, NUL-terminated
text (up to 255). Draw 0x68072460: `DrawText_Shell(x, y, 0x7d00, font, color, 0, text)`; font < 6 (FNX fonts 0-5).

Rect list = u16 count, then per rect (Dreqrect, load 0x68072680, 12 bytes): s16 x, y, w, h, u16 bgColor, u16 color.
Both colors are remapped through the palette table at 0x6808cc98 on load. Draw 0x680726c0 sets the colors
(FUN_68065790(color, bgColor)) and fills (x, y, w, h). Dialog title bars are two 1-pixel rects one row apart in
colors 12 and 11 (an etched line).

## Gadgets (slot +0x30 FUN_68044510)
`u16 count`, then per gadget a u16 kind read as `class << 8 | type`: the class picks the record layout and the base
C++ class, the type (jump tables at 0x680452a0 / 0x680452b4 / 0x68045318) picks the concrete control class. Then the
object's load (vtable slot 0) reads the rest. The common part (FUN_68065d40):

| Off | Field | Object |
|---|---|---|
| 0 | u8 type, u8 class | |
| 2 | u16 id | +0xc |
| 4 | s16 x, y, w, h (relative to the requester) | +0xe..+0x14 |
| 12 | u16 flags: 1 horizontal / 2 vertical (sliders), 0x10 toggle (latches state bit 8), 0x20 activate on load (vtable +0x4c), 0x40 draw style select (FUN_680727a0) | +0x16 |
| 14 | u16 state: runtime bits 1 pressed, 2 released, 4 redraw, 8 toggled on, 0x20, 0x40, 0x60 hidden/disabled tests; the file holds the initial value (4 or 0x24) | +0x18 |
| 16 | u16 link: a related gadget id (OK and Cancel point at each other, list columns chain) | +0x8 |

Class extras:

| Class | Load | Fields (object offset) | Evidence |
|---|---|---|---|
| 1 edit field (Gadedit) | 0x680746d0 | textColor (+0x1c), activeColor (+0x1e), font (+0x20), maxLength (+0x22) | buffer of maxLength+1 bytes allocated at load; draw 0x68074760 picks activeColor when pressed/toggled; FUN_680659b0 font |
| 2 slider (Gadslide) | 0x68075c90 | total (+0x1c), visible (+0x1e), knobW (+0x20), knobH (+0x22) | knob positions = total - visible + 1 (0x68075d50, 0x68076480); knob size defaults to 2 when 0 |
| 4 labelled (button, text, header; Gadbool and friends) | 0x68075170 | font (+0x1c), textColor (+0x1e), activeColor (+0x20), NUL-terminated label (+0x24) | every class-4 draw (0x68072ab0, 0x68073310, 0x68073620, 0x68073d60, 0x68074020) passes +0x1c as font and +0x1e or +0x20 as color by state |
| 8 cell grid (Gadlist / Scrolist) | 0x68075600 | font (+0x20), bgColor (+0x22), selectColor (+0x24), cellW (+0x26), cellH (+0x28) | colors remapped via 0x6808cc98; hit test 0x68075710: column = dx / cellW + 1, row = dy / cellH + 1; draw 0x6804cea0 fills bgColor and the selected row in selectColor |

Shipped census: class 4: 2354 gadgets, 8: 203, 1: 92, 2: 59. Fonts 0..5; colors are palette slots.
