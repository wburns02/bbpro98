# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=voldat.py
REFEREE=(python3 -I -B "$RE/targets/voldatref.py" "$T")
AUDIT=text
HOLDOUT=1            # unseen random edits (more and different leaves) on the same files
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/voldat /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: grep the decompiles under /mnt/nvme/bbpro98/index/ (BBShell, Upstats, EZShell, BBSIM, ...) for each file name (MENU, WEATHER, ASNEW), follow the loader to the structs and to where each field and string index is used, and name everything from that use. Use the files only to confirm."
  [data]="Your primary route is the DATA: hexdump each file, find the headers, offset tables, record sizes and string pools by inspection, and infer what each table means from its contents. Use the decompiles (grep the file names) to confirm meanings or when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for the shell menu definitions, the per-city weather climate table, and the new-association defaults of a 1997 baseball game (one JSON per data file), followed by the decoder source. Real decoding: tables and fields are named for what they mean (news templates by event, name lists with weights, climate by month, menu items with ids/actions, ...), offsets/counts are derived ("_" keys) and recomputed by the encoder, and the code parses each layout generically. FAIL-worthy: placeholder names for most fields, whole files or regions kept as opaque blobs or byte lists, hard-coded content, or an encoder that patches strings into the original bytes without rebuilding offsets. Judge the summary and the code.'
