# Task: a semantic read/write codec for the UI layout files MENU.REQ / DIAL.REQ (FPS Baseball Pro '98)

You are the codec builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
`MENU.REQ` (35 full screens) and `DIAL.REQ` (79 dialogs) in SHELL.VOL define every screen of the game's shell: each
"requester" is a screen or dialog, each "gadget" a control on it. Editing them moves, resizes, relabels, adds or
removes controls. The container is known; what is missing is the meaning of every field.

## Format facts (verified by Claude on all 114 requesters)
- `"IDX:" u32 (4 + 4n) | u32 n | u32 idx[n]`: idx[0] = offset of the first requester, idx[k] = offset of requester
  k-1 plus 8 (it points at the inner "REQ:" tag). n - 1 requesters follow back to back, then tail bytes (one NUL).
- Requester: `"REQ:" u32 (0x80000000 | len)` containing exactly two sections:
  `"REQ:" u32 hlen` = header: `u16 id, s16 x, s16 y, s16 w, s16 h`, then more fields and the title (some headers
  carry long sub-records, up to ~800 bytes), and `"GAD:" u32 glen` = `u16 count` + count gadget records.
- Gadget record: `u8 type, u8 class, u16 id, s16 x, s16 y, s16 w, s16 h`, then by class: class 4 = 12 more bytes and a
  NUL-terminated label; class 1 and 2 = 14 more bytes; class 8 = 16 more bytes. Coordinates are 640x480 screen
  pixels and can be negative.
- Known from an earlier edit (DIAL.REQ requester 13, League Statistics): a type 4 / class 8 record is a list-box
  column body `id, x, y, w, h, 0x40, 4, <previous column id>, 4, 1, 0x0c, <w again>, 0x0b`, a type 0x13 / class 4
  record a column header `id, x, y, w, h (0x0f), 0x50, 4, <next header id>, 0, 1, 2` + label. Ids chain columns.
- The game loads requesters through IDX, so requester order and count matter to the game; gadget order and count do
  not have a fixed limit known to us.

## Goal
Write `$LANE/req.py` (Python 3 stdlib only, under 300 KB; it runs alone in a jail, never import or open other files):
```
python3 req.py decode in.bin out.json
python3 req.py encode in.bin edited.json out.bin
```
`decode` writes at least
`{"requesters": [{"index": i, "id", "x", "y", "w", "h", <named header fields>, "gadgets": [{"id", "x", "y", "w", "h",
"label" (class 4 only), <named fields>}, ...]}, ...]}` with the values of the trusted parse above (signed x/y/w/h).
- Keys starting with `_` are derived (lengths, counts, offsets) and are recomputed by the encoder. Every other leaf is
  content and must be editable: the encoder rebuilds the whole file from the JSON (gadgets may be added, deleted,
  moved, relabelled with any length; a copied gadget object with its `_` keys removed must encode).
- Name things for what they are. Numbered placeholders (f12, w3, unk7) for most keys fail the referee's generic-name
  check and the audit; byte lists / hex strings for more than 25% of the file fail the dump budget.
- `encode(x, decode(x)) == x` byte for byte; the output of an edit must be the canonical layout (requesters back to
  back, IDX recomputed, the tail bytes kept).

## The referee (do not edit it)
`python3 /home/will/bbpro98/re/targets/reqref.py /home/will/bbpro98/re/targets/req $LANE [-v]`
on `/mnt/nvme/bbpro98/targets_data/req/{MENU,DIAL}.REQ` (read only): schema against a trusted parser, header string
coverage, dump budget, generic-name cap, round trip, and edits checked by the trusted parser (move a requester,
move/resize a gadget, relabel two gadgets, add a copy of a gadget with a new id, delete a gadget). Then a model audits
your code and a decode summary, and the same checks run on held-out synthetic files built from the real requesters
(both files mixed, shuffled, perturbed). Decode generically: never hard-code requester data, counts or offsets.

## Tools and budget
- Decompiles: `/mnt/nvme/bbpro98/index/{BBShell,EZShell,LineUp,Upstats}/_all.c` (BBShell FUN_680442b0 reads a
  requester; FUN_68063450 seeks a tag).
- You are GLM-5.3-Flash. For a hard sub-problem you may ask DeepSeek: write a self-contained task file (paste all data
  it needs; it cannot see files) and run `cloud-code --file <task.txt> --mode full --llm-service hive --model deepseek/deepseek-v4.1-flash`.
- Do not run Wine or the game. Do not edit anything outside `$LANE/`. Do not git push.
- Document the format in `$LANE/FORMAT.md` (every header and gadget field per type/class, with the evidence: code
  addresses or data facts).

Stop when the referee prints PASS and your names are backed by evidence, or when you are out of ideas for this round.
Always leave `req.py` runnable and `progress.md` updated.

## Parallel lanes
Several GLM lanes work on this at once in `/home/will/bbpro98/re/targets/req/lanes/<lane>/`. At the start of every
round read the other lanes' `progress.md` and `FORMAT.md` (read-only to you) and reuse anything verified.
