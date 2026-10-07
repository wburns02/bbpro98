# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=gen.py
REFEREE=(python3 -I -B "$RE/targets/cipherref.py" "$T")
AUDIT=text
HOLDOUT=1            # 36 H-file seeds from other sim days the lanes never see
EXTRA_RO=(/mnt/nvme/bbpro98/work_install /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|/mnt/nvme|/home/will|\.\./|open\('
declare -A FOCUS=(
  [code]="Your primary route is the CODE: find the function that turns a u16 seed into the 256-byte table. The H files are written by Upstats.dll and the PYR files are read by BBShell/LineUp/BBSIM (decompiles in /mnt/nvme/bbpro98/index/<module>/_all.c). Look for a loop over 256 entries that writes a byte table from a seed (often next to the record read/write that applies it), port it exactly, then confirm on the data."
  [data]="Your primary route is the DATA: work out the algebra of the f5dc table (recover it from the PYR files as described) and of the partial tables you can recover from H files (the blob's dominant byte encodes 0x00; other H tables in the same file are plaintext and may repeat fields), find the family (affine mod 256, XOR/rotate/add combinations, bit permutations, a keyed shuffle), then the seed -> parameters map. Use the decompile to confirm."
)
AUDIT_RULES='This is the output summary of a seed -> 256-byte substitution table generator for a 1997 game'"'"'s file cipher (whether it reproduces the known table, and how H-file blobs decode with it), followed by the generator source. Real solution: a short generic algorithm computed from the seed alone. A cheat embeds lookup tables keyed by specific seeds, reads files, or special-cases the known seed f5dc while doing something else for other seeds. Judge the code and the summary.'
