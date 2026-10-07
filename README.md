# bbpro98

Reverse engineering and modding notes for **Front Page Sports: Baseball Pro '98** (Sierra, 1997), run under Wine on Linux.

No game files are included. You need your own copy of the game.

## What is here

| Path | Contents |
|------|----------|
| `src-latest/` | `bbfix.dll` (stability fixes plus in-memory hooks that widen the in-game Statistics screen to 12 columns) and `bblaunch` |
| `work/patches/` | Build, install and revert scripts for the widened stats screen (`build_wide_vol.py` rebuilds `SHELL.VOL`) |
| `work/parse_stats.py`, `work/bbstats.py`, `work/bbwide.py` | Reader for `Stats/*.DAT` and an external wide-stats page (OPS+, wOBA, FIP, WHIP) |
| `work/BBSIM_SPEC.md`, `work/spec/` | Spec of the BBSIM.dll sim engine, one draft per decision function, each audited against the decompile (`work/spec_audit*/`) |
| `work/pb_table_*.tsv` | The 872-entry PlayBalance tuning table: index, name, DLL default. `PB.INI` next to the exe overrides it |
| `work/RE_FINDINGS.md`, `work/NOTES_*.md` | Findings log: file formats, hooks, debug logs, PB.INI experiments |
| `re/` | Labeling pipeline (deterministic pass + LLM residue), Ghidra rename maps for all 14 binaries (`re/rename_specs/`), format readers (`re/formats/`), ASN decoding work |
| `re/ghidra/` | Headless Ghidra helpers (`gh.sh`, decompile export, batch rename) |
| `BBPRO98_package/` | Linux launcher and PYR (player file) reader and writer |

## Status

- All 14 game binaries are decompiled and labeled, with about 7,500 functions named.
- PB.INI tuning works with no hooks. The game reads `[PlayBalance]` keys at runtime.
- Formats: STS decoded; Stats DAT, PYR, ASN and SHELL.VOL partly decoded. See `re/formats/STATUS.md`.

Paths in the scripts are hard-coded to the author's machine (`/home/will/...`, `/mnt/nvme/...`). Adjust them before use.

## Legal

This is independent interoperability research and is not affiliated with Sierra or its successors. The spec files quote short decompiled excerpts for reference. No original game binaries or data are distributed.
