# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=codec.py
REFEREE=(python3 -I -B "$RE/targets/imgref.py" "$T")
AUDIT=image          # contact sheets from `REFEREE <lane> --audit <dir>` go to a vision model
HOLDOUT=0            # no hidden truth for art; round-trip + edit test + vision audit are the gates
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/shellgfx /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|targets_data|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: the 'FNX:' reader is in the EZShell decompile (/mnt/nvme/bbpro98/index/EZShell/_all.c ~line 43464, magic 0x3a584e46; the same reader is in BBShell/_all.c ~109021, LineUp ~41248, Upstats ~42675). Find the BMX reader the same way (callers of the FNX loader's neighbours, the shell's bitmap loader, MENUBRS / STADIA usage). Port them exactly, then write the matching encoders."
  [data]="Your primary route is the DATA: BMX starts with a directory (u32 offset, u16 w, u16 h, u16 ?, ... per entry; first offset = directory size) and the gaps between offsets are smaller than w*h, so the rows are compressed (try RLE / transparent-run schemes); FNX starts 'FNX:' + a small header + a u16 offset table per glyph (4.FNX: 11 bytes per glyph at height 11 = one byte per row). Work it out by inspection, confirm with the decompile."
)
AUDIT_RULES='These are contact sheets of frames decoded from a 1997 baseball game'"'"'s front-end shell graphics (magenta = sheet background, not game art): menu bar / button pieces, stadium name banners, and bitmap font glyphs (letters, digits, punctuation). Real decoded art shows recognizable shapes: readable glyphs, UI bars or banner text with clean edges, possibly with odd colours if the palette is wrong. A failed decode shows noise, diagonal streaks, repeated garbage rows, or random static. Judge each sheet.'
