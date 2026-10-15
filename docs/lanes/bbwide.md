# Lane bbwide: three open League Statistics widen questions

> SOURCE LIMIT, read first. `work/BBShell.asm`, `BBShell.dll` and the Ghidra dump (`/mnt/nvme/bbpro98/index`) were
> not present when this note was written (not in the worktree `work/`, not in the main checkout, `/mnt/nvme/bbpro98`
> absent, `find / -iname 'BBShell*'` empty). No asm line below was read for this note. Every instruction quoted is
> text that an earlier session recorded in a repo file, cited as `file:line`. Anything only the disassembly can answer
> is marked **not found**. `[inference]` marks a conclusion drawn from cited facts, not seen in code.
>
> Keys: BC `docs/lanes/bbcard.md`, NW `work/NOTES_widen.md`, BF `src-latest/bbfix.c`, PC `src-latest/mods/playercard.c`,
> FM `re/targets/misc8/lanes/data/FORMAT.md`, BG `re/ghidra/backfill_1.py`, VB `work/patches/build_wide_vol.py`,
> NS `work/NOTES_stats_format.md`, PL `work/PLAN_widen_oneshot.md`, RC `work/reqcodec.py`. BBShell.dll, ImageBase 0x68000000.

## 1. Team Statistics screen

### Build and fill (repo asm notes)
- Open function 0x680361b0 (BC:151). Object: `push 0x5f4` at 0x68036212, ctor FUN_680367e0 called at 0x68036236,
  `mov ds:0x6808da24,eax` at 0x68036246 (BC:111-112). Object is 0x5f4 bytes, League's is 0x6a0 (PC:65, 64).
- Install: `mov ecx, ds:0x6808da24 / call 0x68036b80` at 0x6803627a..0x68036280 (BC:115) -> FUN_68036dc0 ->
  FUN_68038ef0(0x14, ..., `push 0x68036ec0` at 0x68036dcd) (BC:118). Dialog number 0x14 is the REQ record titled
  "Team Statistics -" (BC:29-30).
- Body: the loop in FUN_68036dc0 inits gadgets 9..0x12 with FUN_680436c0 / FUN_68043400 (BC:147). Scroll group from
  `FUN_68043810(mgr, 8, 6, 7, 9, rows, ...)`, stored at obj+0xfa (BC:146).
- Rows: FUN_68036c40 fills them through StatsGrid_FillRowCells 6805c930, calls at 0x68036cb8, 0x68036cd2, 0x68036d8b
  (BC:124-125). Row table at obj+0x14, row stride 0xa0, cell i at row+8i, name at row+0x80 (BC:126-127).
- Click: FUN_68036fd0 reads cell 10 as the id cell, `push 0xa` at 0x6803703c (BC:135-136); called from 0x68036da5 and from
  FUN_68037080 at 0x680370a1, which is the header-click path (BC:136, 120).

### Same draw path as League?
- Fill: **yes, proven**. 6805c930 is the League fill too, so bbfix sites slot 6805cae2, bound 6805cafb, term 6805cb0b
  (BF:268-270) already run on Team rows. In-game gate: Team id cell is 14 under widen, card opens
  (BC:202-204, 207). Row layout holds it: 15 cells end at row+0x78, name at row+0x80 (BC:126-127).
- Draw: ListGrid_DrawRows 680758f0 is called from the grid gadget handler 68077d5b and calls the per-gadget callback at
  `[this+0x1c]` (NW:148, 150). That is gadget-class code, so Team's class 8 body gadgets very likely go through it too
  [inference: BC:37 says Team body columns are gadgets 9..0x12 "as on the League screen"].
- Cell callback: League registers thunk 0x6800ea40 -> StatsGrid_CellCallback 6800ec00 for every body gadget
  (`f1(0x6808dd10, id, 0x6800ea40)`, BF:257-258). Which callback Team's init loop passes: **not found**.
  Evidence it is a different one: 6800ec00 maps visible rows with the screen's scroll group (PC:11-12), and the
  group offsets differ, League obj+0x694 vs Team obj+0xfa, tables +0x3c vs +0x14 (PC:47-51, 64-65). One callback
  cannot read both from a single global [inference]. Its address is in the Team code between 0x68036c40 and 0x68037080.
- Column id table 0x6808c2e8 (stride 0x80, ids region 0x50 B, name +0x50, name2 +0x5d; BG:14, 23-28): whether Team's grid
  copies ids into its own `this+0x6c` through StatsGrid_InitHeaders 6805cb20 (FM:28-29) is **not found**. h_slot reads
  `[esi+ecx*4+0x6c]` and the view at `[esi+0xe8]` (BF:249-250), so the Team object must carry both at those offsets
  for the shared fill to read real ids. **Not found.** If it does not, cells 10..13 hold ext_id(garbage) or 0
  (`ext_id` returns 0 for view >= 2, BF:244). Harmless today: nothing draws them.

### Column count and pitch
- Count: 8 stat ids per view, in a 10-u32 block `[3, 0, 8 ids]` (FM:22-24, 28-29); fill loop bound `cmp bp,0xa`
  at 6805cafb (BF:269, bytes 66 83 fd 0a). Shared with League.
- Pitch: not a code constant. It is REQ gadget geometry: League body columns are gadgets 0x0b..0x12 at x=0xd7+49n, w=0x32
  in MENU.REQ requester id 15 (VB:4-5, 45-52). The `imul cx,cx,0x32` at 0x6804290f is HallOfFame_DataLayout 680428a0,
  not a stats screen (PL:3; BG:6). Team's pitch is in the REQ 0x14 record: **not found** (SHELL.VOL is not in the repo
  and nothing decodes that record).

### Verdict: which bbfix sites need a Team twin
| site (BF:268-279) | VA | Team |
|---|---|---|
| slot / bound / term | 6805cae2 / 6805cafb / 6805cb0b | shared function 6805c930, no twin. Needs the `this+0xe8` view check above. |
| hdr | 6805cbe7 | in 6805cb20; Team has no ext header gadgets, so unused. No twin. |
| cell | 6800ec2c (`mov cx,bx / sub cx,9`, BF:272) | **twin** at Team's cell callback (cell = gadget id - 0x26 for ids >= 0x30). Address not found. |
| init | 6800d3aa (`push 0 / mov eax,[esi+0x34]`, BF:273) | **twin** after the 9..0x12 loop in FUN_68036dc0, for ids 0x30..0x33 with Team's callback. Address not found. |
| hdrrng | 6800d442 (`push 0x1c`, BF:274) | **twin** only if FUN_68036dc0 has a header range bound. Not found. |
| click | 6800d74f (`cmp si,0x1c`, BF:275) | **twin** at the header range check on the FUN_68037080 path (0x680370a1 region). Not found. |
| vt8, rd1..rd3 | 68081f7c, 680721d7, 68072227, 68072255 | class-level, shared. w_vt8 keys on gadget id 8, w_redraw on group id 9 (BF:286, 292); Team passes 8 and 9 to FUN_68043810 (BC:146), so likely work unchanged [inference]. |

Plus one latent fix that exists today: FUN_68036fd0 `push 0xa` at 0x6803703c (BC:135-137). Under widen cell 10 is a stat
cell, so the game's own Team click-to-id reads garbage. The card mod does not use it. A twin patches it to 14.
Not widen-specific code: the REQ 0x14 record needs 4 body gadgets 0x30..0x33 added with `build_wide_vol.py`'s method
(VB:54-71), and PC's `SCREENS[1].ext` (PC:65) set to 1.

**Effort: 4 to 5 new sites** (init, cell, click, 0x6803703c, plus hdrrng if present; 6 if the header path has two range
checks), **plus one REQ record edit.** If sorting is skipped and only a static 12-column display is wanted: 2 sites
(init, cell) plus the REQ edit.

To close with the asm: `grep -n "68036dc0:" work/BBShell.asm`, read the callback constant pushed before each
`call 0x680436c0`; then `grep -n "68036c40:"` for what `this` is when it calls 6805c930.

## 2. Sorted-column highlight

**Not found.** The color source and the compare are not recorded anywhere in the repo.

### What is established
- Body text is drawn by DrawText_Shell 68065650, cdecl `x,y,w,font,color,flags,char*text` (NW:148). By BF:305-309 the
  frame is stk[1]=x, stk[2]=y, stk[3]=w, stk[4]=font, stk[5]=color, stk[6]=flags, stk[7]=text. So the color argument is
  stk[5]. The existing `[trace] draw=1` hook logs x, y, font but **not stk[5] or stk[6]** (BF:308).
- Ext cells reach the same callback. `h_init` registers thunk 0x6800ea40 for ids 0x30..0x33 (BF:257-258), and `h_cell`
  at 6800ec2c turns gadget id into cell index (`bx>=0x30 ? bx-0x26 : bx-9`, BF:255). Stock cells are 0..9, ext cells
  10..13. Any test in 6800ec00 that sees cell index, slot or gadget id against a sorted-column field behaves
  differently for them. Which test: **not found**.
- Sort is set by FUN_6800d740, whose range check is `cmp si,0x1c` at 6800d74f (bytes 66 83 fe 1c, BF:275), raised to
  0x20 so the ext header ids 0x1d..0x20 are accepted (HANDOFF.md:48). `si` is the clicked header gadget id
  (stock 0x15..0x1c, VB:50). What it stores (header id, body id, slot or cell) and where (global or
  `obj+X`): **not found**.
- HANDOFF.md:48 records "Not done: sorted-column yellow highlight on ext body cells", so stock cells do highlight and
  ext cells do not. The yellow value itself is **not found**.

### Why ext cells miss it
**Not found.** Two candidates, neither confirmed:
- H1, code: the callback chooses the color argument by comparing against a stored sorted column, and the stored value
  or the compare is built for ids 0x0b..0x12 / cells 2..9 only. Ext cells (10..13, ids 0x30..0x33) then never match.
- H2, data: the highlight comes from the body gadget's REQ fields. Class 8 has `font, bgColor, selectColor, cellW, cellH`
  (RC:17). The ext bodies were authored as `font=4, bgColor=1, selectColor=0xc, cellW=colw, cellH=0xb` (VB:60-61),
  values chosen by hand. The stock body gadget values were never read back (VB:48-52 copies geometry only). If the
  game uses `selectColor` or a header `activeColor` (RC:16, VB:63-64 sets `textColor=1, activeColor=2`) for the sorted
  column, the fix is in the VOL, not in a hook.

### Smallest hook
Cannot be named from the repo. Plan that names it with one run, no code beyond a log field:
1. Extend h_dt (BF:308) to print stk[5] and stk[6]. Open League Statistics, Show > Players, sort a stock column, log;
   sort an ext column, log. Cells in the sorted column should show a different stk[5] than the rest.
2. The `stack:` walk already printed by h_dt gives the return address inside 6800ec00 that pushed the color. The
   instruction that picks it is the compare to widen. If it is a `cmp` on a global or `[obj+X]`, the fix is a one-site
   immediate or handler patch at that compare (same shape as `bound`/`click`, BF:269, 275). If stk[5] is the same
   for all cells, H2 applies and the fix is the REQ edit, zero hook sites.

To close with the asm: `grep -n "6800ec00:" work/BBShell.asm`, read down to the `call 0x68065650` (or the thunk that
reaches it) and note what is pushed fifth, then trace that register to its compare.

## 3. Change Columns dialog

### What is established
- Functions: ChangeColumns_Init 6805da80, ChangeColumns_Show 6805db20 (BG:11-12; NW:123-124). StatSets_LoadAll 6805c780,
  StatSet_LoadFile 6805d7d0, StatSet_SaveFile 6805d8e0 (BG:8-10). The dialog slot-button code is said to live in
  0x6805c600..0x6805c66f (NW:122), with a `mov edi,7` at 0x6805c622 (NW:12-13; `work/patch_widen.py:93`). That script is the one whose
  other offsets were wrong and whose "verified" claims were not (NW:127; PL:3), so treat both as unverified.
- Table: g_StatSets 0x6808c2e8, stride 0x80 per set, set index = `this+0xe4` (BG:14). Per set: 2 views x 10 u32 = 0x50
  bytes of ids, name 13 B at +0x50, name2 33 B at +0x5d (BG:23-28; NS:39). View v ids start at `0x6808c2e8 + 0x80*set +
  0x28*v`. Slot 0 is the constant 3, slot 1 is 0, slots 2..9 are the 8 stat ids (FM:22-24). BG:14 and NS:39 count it as
  "count + 9 ids", which agrees once slot 1 is the Name column (gadget 0x0a is the Name body, VB:43, and its cell is
  0x0a-9 = 1, BF:272) [inference]. Both sources give 8 editable stat ids.
- The grid reads the active slot as `[esi+ecx*4+0x6c]` at 6805cae2 (BF:268; NW:137), `esi+0x6c` being a copy made by
  StatsGrid_InitHeaders 6805cb20 (FM:28-29). Slots >= 10 were redirected to ext_tab by h_slot (BF:249-250). So **ext ids
  are not in g_StatSets at all**; they live in bbfix.ini `[widen] bat=, pit=` (BF:243, 297-301).
- File: `StatSet_LoadFile` rejects anything but size 0x75 (117 B) or version != 1 (FM:15-16). Consumers: callers 6805c780
  and 6805dbd0 (FM:15).

### How the dialog fills and writes its 8 buttons
**Not found.** The code that labels the 8 buttons from the ids, and the handler that writes a pick back into
`ids[2..9]` of set `[this+0xe4]`, are in 6805da80 / 6805db20 and their callees; no instruction from them is recorded. The REQ record
number of the dialog and whether its slot buttons are text gadgets or baked art: **not found**.

### Is a 12-slot dialog feasible without new art
Not shown. Documented blockers, each with its address:
1. Record size: 2 blocks x 14 u32 = 0x70 bytes cannot sit in the 0x50 ids region; it overruns name (+0x50) and name2 (+0x5d)
   (NW:127; BG:23-28). Fix needs the 0x80 stride changed everywhere the table is indexed. Number of index sites: **not found**.
2. File format: 117 B, checked at 6805d7d0 (FM:15-16). A 12-id STS needs that check changed (site not found) and new
   ids written by 6805d8e0 (loop count not found). Old `.STS` files would also need a converter (PL:26).
3. Dialog UI: 4 more slot buttons are REQ gadgets. build_wide_vol.py already adds class 4/8 gadgets with no bitmap
   (VB:60-71), so buttons alone need no art if they are plain gadgets. Whether the dialog frame has room, or has 8 baked
   cut-outs: **not found.**
Cheaper route that avoids 1 and 2: keep ext ids outside StatSet, in a sidecar keyed by `(set index [this+0xe4], view
[esi+0xe8])`, and read it in h_slot instead of ext_tab. Still needs blocker 3 and the unlocated write handler. Untried.

**Verdict: keep the ext columns ini-only (bbfix.ini `[widen] bat=/pit=`); a user-editable 12-slot dialog needs a bigger
StatSet record, a new .STS size, a larger REQ dialog and the unlocated slot loop, and none of those has been shown.**

To close with the asm: `grep -n "6805da80:\|6805db20:" work/BBShell.asm`, find the loop over 8 buttons and the store
into `0x6808c2e8 + ...`; count the places that multiply by 0x80 or 0x28.

## 4. Confidence

| Section | Level | One thing a runtime probe must confirm |
|---|---|---|
| 1 Team Statistics | LOW (fill path alone is HIGH: game-verified gate, BC:201-207) | The cell callback address Team's init loop passes to FUN_680436c0. Run `[trace] cell=1 draw=1` on Team Statistics and compare the callback frame with 0x6800ea40 / 6800ec00. Also that the Team object holds ids at `+0x6c` and the view at `+0xe8`. |
| 2 Sorted-column highlight | LOW (nothing found) | The value of `stk[5]` (color) at DrawText_Shell for a sorted stock cell, an unsorted cell, and a sorted ext cell, with the stack walk to the instruction that chose it. Decides H1 vs H2. |
| 3 Change Columns | MEDIUM for the data-layout blockers (two agreeing sources, FM and BG, plus the 117 B check); LOW for dialog mechanics | Change slot 9 in the dialog, Save, then read the 0x80 entry or the saved `.STS`: confirms the write target is `ids[view*10 + 2..9]` and the file stays 117 B. |
