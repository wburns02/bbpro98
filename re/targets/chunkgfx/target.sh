# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=codec.py
REFEREE=(python3 -I -B "$RE/targets/imgref.py" "$T")
AUDIT=image          # contact sheets from `REFEREE <lane> --audit <dir>` go to a vision model
HOLDOUT=0            # no hidden truth for art; round-trip + edit test + vision audit are the gates
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/chunkgfx /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|targets_data|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: in the BBSIM decompile (/mnt/nvme/bbpro98/index/BBSIM/_all.c) the 'SCR:' reader is FUN_680b0c20 (~line 100655, magic 0x3a524353), the 'FNT:' reader is near line 96507 (0x3a544e46), and the multi-frame bitmap 'uncrush' is in Dbm.cpp (lines ~17200-17440, 'DBMImage uncrush bug'). Port them exactly, then write the matching encoders."
  [data]="Your primary route is the DATA: start with the multi-frame chunks (per-frame header: raw size, compressed size, flags, then the stream; 32x16 frames are tiny) and the SCR: screens (640x480, 'SCR:' + sizes + a row/offset table), find the compression by inspection, then the fonts. Use the decompile to confirm. The DBM sprite lanes (read-only, /home/will/bbpro98/re/targets/dbm/lanes/*/progress.md, codec.py) may already have found the same 'crush' scheme."
)
AUDIT_RULES='These are contact sheets of frames decoded from a 1997 baseball game'"'"'s simulation graphics (magenta = sheet background, not game art): full-screen 640x480 overlay screens, small animated sprite strips (scoreboard and wall text, jersey or number sprites), and bitmap font glyphs. Real decoded art shows recognizable shapes: text, digits, players, field, scoreboard or UI pieces, with clean edges, possibly with odd colours if the palette is wrong. A failed decode shows noise, diagonal streaks, repeated garbage rows, or random static. Judge each sheet.'
