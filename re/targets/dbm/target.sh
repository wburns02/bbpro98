# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=codec.py
REFEREE=(python3 -I -B "$RE/targets/imgref.py" "$T")
AUDIT=image          # contact sheets from `REFEREE <lane> --audit <dir>` go to a vision model
HOLDOUT=0            # no hidden truth for art; round-trip + edit test + vision audit are the gates
EXTRA_RO=(/mnt/nvme/bbpro98/work_install /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: port Dbm.cpp from the BBSIM decompile exactly (FUN_6801ea00 open/count check, the per-bitmap header read, and the uncrush decompressor around the 'DBMImage uncrush bug' strings), then write the matching crusher for encode. Use the files only to confirm."
  [data]="Your primary route is the DATA: parse the offset table, then study the per-bitmap headers and compressed streams in the small files first (NOVDBM, NUMDBM4) and find the compression scheme (RLE/LZ/transparency runs) by inspection. Use the decompile only to confirm or when stuck. Borrow anything verified from the code lane's notes."
)
AUDIT_RULES='These are contact sheets of frames decoded from a 1997 baseball game'"'"'s sprite archives (magenta = sheet background, not game art). Real decoded art shows recognizable shapes: baseball players in poses, digits or jersey numbers, crowd, field or UI pieces, with clean edges, possibly with odd colours if the palette is wrong. A failed decode shows noise, diagonal streaks, repeated garbage rows, or random static. Judge each sheet.'
