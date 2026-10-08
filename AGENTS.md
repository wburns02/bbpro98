# bbpro98: agent rules

Public repo (MIT) of tools and research for FPS Baseball Pro '98. Python codecs live in work/, research lanes in re/.

## Never commit
- Game files or anything the game wrote: *.ASN *.PYR *.PYF *.DAT *.VOL *.dll *.exe, saves, templates, snapshots.
- Decompile dumps (/mnt/nvme/bbpro98/index), third-party tools, Sierra patch notes.
- Secrets of any kind. No network calls from repo code.

## Paths
- Work copy of the install: /mnt/nvme/bbpro98/work_install. Never write the live install
  (~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98) directly; work/patches/install_live.sh does that.
- Lahman database: /mnt/nvme/tlrb2/lahman/lahmansbaseballdb.sqlite, open read-only
  (sqlite3.connect('file:...?mode=ro', uri=True)).
- Large data goes under /mnt/nvme, never /home/will or /tmp.

## Code conventions
- Python 3, standard library (numpy allowed in work/lahman/ratings.py only). No eval/exec, no shell=True.
- Codecs round-trip byte for byte: encode(x, decode(x)) == x. Find c-tree members by name (ctree.parse), never by
  member number; the number differs between files.
- ASN/PYR cipher: seed is per file (ASN bytes 0x310-0x311, PYR bytes 0-1); never hardcode f5dc.
- Tests: python3 -m pytest <dir> -q, run through `capped`. Tests that need game files skip when they are absent.
