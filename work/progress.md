# progress (tiered-build-loop, wide stats)
- M0 RESULT 2026-10-06: G0 FAILED. Three positive controls left the Statistics screen unchanged: (1) BBShell imul 0x32 pitch at 0x6804290f (Hall of Fame layout) and 0x6804f7d3, set to 0x10; (2) _DEFAULT.STS last batting id changed; (3) BBShell .data table 0x6808c2e8 entry 0 last id changed (file off 0x8ad0c). The default set also exists in LineUp.dll at 0x35428. Statistics screen config source not located (suspect SHELL.VOL resources, MENU.REQ/DIAL.REQ, or Assn state). Live install restored to pristine and verified.
- Decision: Fallback F (wide stats window from Stats/mlbpa97.DAT) per PLAN_widen_oneshot.md.
- Lesson: bytepatch.py once inserted bytes (old/new length mismatch); fixed with a length assert. Restored from backup.

## 2026-10-06 M-wide: SHELL.VOL widening LOADS
- Crash cause: VOLM dir has a final u32 at 0x234 (end-of-data sentinel) that must also shift by the growth. build_wide_vol.py now does it. No per-file 9-byte header fix needed.
- r6.png: 4 extra gadget columns EX1..EX4 render, name/stat columns narrowed. Good build saved: /mnt/nvme/bbpro98/vol/SHELL_wide_ok_EXhdrs.VOL
- NEXT: code hook so cells 10..14 are filled (FUN_6805c930) + header text for ids 0x28.. (after FUN_6805cb20 in FUN_6800d300).
