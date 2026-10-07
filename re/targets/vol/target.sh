# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=codec.py
REFEREE=(python3 -I -B "$RE/targets/arcref.py" "$T")
AUDIT=text           # the referee's --audit listing (names, sizes, first bytes) + codec.py go to Haiku as text
HOLDOUT=0
EXTRA_RO=(/mnt/nvme/bbpro98/work_install /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: port the VOL reader from EZShell's Utility\\Volume.cpp (decompile /mnt/nvme/bbpro98/index/EZShell/_all.c around lines 44900-45100, strings s___Utility_Volume_cpp) exactly: header, directory records, subdirectory records, per-entry headers. Use the files only to confirm."
  [data]="Your primary route is the DATA: parse the directory of SHELL1.VOL (one subdirectory, 41 PCX entries) by inspection, then SHELL2.VOL (several subdirectories, PCX + WAV), then SHELL.VOL. Use the decompile only to confirm or when stuck."
)
AUDIT_RULES='This is the listing of entries a decoder extracted from a 1997 baseball game'"'"'s VOL archives (name, size, first 16 bytes hex), followed by the decoder source. Real decoding: names look like DOS 8.3 file names with optional directory prefixes, PCX entries start with 0a, WAV entries start with 52494646 (RIFF), sizes are plausible and add up. A cheat stores the whole archive or big undecoded slabs in one entry, invents names, or hard-codes offsets/sizes for these specific files instead of parsing the directory. Judge the listing and the code.'
