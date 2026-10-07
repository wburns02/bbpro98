# BMX and FNX (front-end shell graphics)

Solved 2026-10-07 by the GLM data lane, round 1. The authoritative spec is the docstring of `codec.py` (installed as
`work/shellgfx.py`). Claude's verification notes:

- imgref PASS on all 8 files (MENUBRS.BMX 24 frames, STADIA.BMX 7, fonts 0-4 97 glyphs, font 5 95 glyphs).
- Contact sheets inspected by eye with bb0.pal: STADIA = six 320-wide two-colour stadium skyline silhouettes;
  MENUBRS = menu buttons and arrows; fonts 0-4 = shaded 8-bit glyphs with ink in indices 1-3 (recoloured at draw time);
  font 5 = large 8-bit glyphs.
- BMX stores each bitmap as w*h-10 bytes (the last 10 pixels are implicit zero). The encoder refuses a frame whose
  last 10 pixels are non-zero rather than silently dropping the edit (Claude's change). Bytes after the last bitmap
  are an orphaned bitmap (deleted directory entry), kept as a `tail` frame.
- Fonts 0-4 end with 288 bytes of DOS `dir` listing junk from the original tool; kept as an opaque frame.
