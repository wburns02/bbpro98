# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=voldat.py
REFEREE=(python3 -I -B "$RE/targets/voldatref.py" "$T")
AUDIT=text
HOLDOUT=1            # unseen files (2 stat sets, an older .pyf) + unseen random edits
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/misc8 /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|targets_holdout|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: follow each loader in the decompiles (HHA.DAT: BBSIM FUN_68035f31 'Hranim.cpp' and the per-animation parser FUN_6803634f; bb.cfg: EZShell, grep \"bb.cfg\"; .STS: BBShell StatSet_LoadFile/StatSet_SaveFile and the g_StatSets ids users; .apc: BBShell around the PC0: tag DAT_6808bbe8; .pyc/.pyf: BBShell around the PPD: tag DAT_6808be08) to the structs and to where each field is used, and name everything from that use."
  [data]="Your primary route is the DATA: hexdump each file, find headers, records and tables by inspection, and infer meanings from the values (cross-check STS stat ids against the stat name table in the BBShell decompile, .pyc/.pyf ids against player ids). Confirm in the loaders named in TASK.md."
)
AUDIT_RULES='This is a summary of what a decoder reports for several small data files of a 1997 baseball game (HHA.DAT home-run/hit animation table, bb.cfg launcher config, .STS stat-column sets, .apc champions history, .pyc/.pyf player id lists), one JSON per file, followed by the decoder source. Real decoding: fields are named for what they mean (stat set name and the stat ids of each column for batters and pitchers, champion lines by year, player ids, animation records with their frame data, config options), counts/offsets/stale padding are derived ("_" keys) and recomputed, and the code parses each layout generically. FAIL-worthy: placeholder names for most fields, files kept as opaque blobs or byte lists, hard-coded content, or an encoder that copies the input instead of rebuilding. Judge the summary and the code.'
