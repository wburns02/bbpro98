# Win32 resources (.rsrc) of the game's PE files

Codec: `work/rsrc.py` (Claude, 2026-10-07). Standard PE/COFF resource format; this file records what the game's
binaries actually contain and the layout details a byte-exact rewrite has to keep.

## What is in the binaries

| File | Resources |
|---|---|
| BBSIM.dll | 27 dialogs, 6 menus (in-game popup menus: Pause, Help, Game Options, Replay, CAMS, Lineup, Exit Stadium), 3 bitmaps, 6 custom type 240 |
| FastSim.dll | 28 dialogs, 5 menus |
| FPS_Ctrl.dll | 4 dialogs (Control Setup, joystick mapping), 43 string blocks: the 3D game's batting/pitching/fielding/baserunning panel captions ("Normal", "Contact", "Power", "Bunt", "Manager Menu", "Steal 2nd", ...) |
| EZShell.dll | 11 dialogs, 6 string blocks |
| Baseball.exe | 34 bitmaps, icons, version |
| RemotMgr.exe | 17 dialogs |
| BBShell, BBCfg, FPS_CT, FPS_DCL, FPS_Pal, IC_Cfg, LineUp, BBArch, BB_CTRL, BBUpdate, Datain | dialogs, icons, version, a few raw blobs |
| Preview/Preview.EXE (Borland) | icons, group icon, version |
| WEBPOST.EXE, WINTDIST.EXE (IExpress packages) | named RCDATA (CABINET, TITLE, UPROMPT, ...), icons, version |
| bbfix.dll, bblaunch.exe, ODASL.dll, Upstats.dll, mods/*.dll | none |

STRING ids: block b holds ids (b-1)*16 .. (b-1)*16+15. FPS_Ctrl "Manager Menu" = ids 1205 (batting, block 76) and
1505 (fielding, block 95). The batting panel draws these, not SIM.DAT bpi.str (5200), whose edit shows nothing there.

## Decoded types (JSON in manifest.json)

DIALOG and DIALOGEX (header, font, every item with class/text/id/rect/styles and creation data), MENU and MENUEX
(item tree), STRING (`{"strings": {id: text}}`, empty slots omitted), ACCELERATOR, VERSION (node tree; the fixed
VS_FIXEDFILEINFO kept as hex). A decoder is used only when its re-encode is exact; otherwise the resource is a raw file
(res/*.bin). BITMAP is written as a .bmp (14-byte BITMAPFILEHEADER added, stripped on pack). Every codec-type resource
in the game decodes.

## Layout a byte-exact rebuild must keep

1. Directory tables breadth first (root, all type tables, all name tables), names before ids, names sorted
   case-insensitively; then the 16-byte data entries in tree order; then the name strings (types, then names, each
   once).
2. The data area starts at the 16-aligned end of the strings (MS linker) or right after them (Borland). The original
   start is stored as `dirs._data_at` and kept when it still lies past the tables.
3. Data in the order of the original .res file, which is not the tree order. Each datum is 4-aligned with zero fill.
   IExpress leaves non-zero filler ("PADDING...") and non-default gaps between data. Those are stored per resource as
   `after` (hex) and kept when the next datum stays 4-aligned.
4. The bytes after the last datum inside the raw size are the manifest `pad`.
5. Section VirtualSize and DataDirectory[2].Size: the MS linker sets both to the 4-aligned length. IExpress page-aligns
   VirtualSize and leaves the directory size unaligned. The differences are `vsize_extra` / `dd_extra`.
6. The PE checksum is recomputed only when the original was valid (non-zero and correct).

## Growth

If the new section fits the old raw size and virtual span, it is written in place. Otherwise .rsrc grows to the
aligned size and .reloc (the only section after it in every MS-linked game binary) moves behind it: its section
header VA and raw pointer, DataDirectory[5] and SizeOfImage are updated; overlay data after .reloc is kept. Nothing
else points into either section. Growth is refused when anything but .reloc follows .rsrc (Preview.EXE has .debug
after it; in-place edits there still work).

## Verification (2026-10-07)

- `rsrc.py verify`: byte-exact unpack/pack of all 20 PE files with resources in the work copy.
- Edit fuzz: every dialog/menu/string text lengthened or shortened, packed, re-read: 20/20 decode back to the
  edited JSON; 13 of them grew past their section and moved .reloc.
- In game (work/harness/t_sim_edits.py PASS): FPS_Ctrl.dll strings 1205/1505 "Manager Menu" -> "Skipper Menu" plus a
  3000-char filler string to force growth. The game loaded the grown DLL and drew "Skipper Menu" in the batting panel.
