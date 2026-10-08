# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=voldat.py
REFEREE=(python3 -I -B "$RE/targets/voldatref.py" "$T")
AUDIT=text
HOLDOUT=1            # the same chunks of 8 unseen stadiums
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/chunks /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: the chunks are loaded by id from SIM.DAT and Stadia/*.DAT in BBSIM / FastSim / Baseball (grep /mnt/nvme/bbpro98/index/*/_all.c for the chunk ids as hex constants, e.g. 0xce8c, 0x947d, 0xe957, 0xe1a4, 0xe6e7, and for the tags GID:, DAT:, STA:); follow each loader to the struct it fills and to where each field is used (ball-vs-wall collision, camera placement, injury selection, park factors, ...) and name every field from that use. Use the files only to confirm."
  [data]="Your primary route is the DATA: compare each chunk across the 20 visible stadiums (what is constant, what scales with known park dimensions: 1997 fence distances, wall heights, the Green Monster in BOSTON, the Astrodome in HOUSTON is held out), find the record sizes and tables by inspection, and name fields from what they measure. Confirm in the decompiles (grep the chunk ids as hex constants) when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for binary data chunks of a 1997 baseball game: per-stadium fence/wall geometry (@W "GID:"), stadium info ("STA:" name and coordinates), the HS "DAT:" tables, the WT and XT tables, and from SIM.DAT the camera list (@C), the injury table (MI), UI strings (PB), and the MS / OL / UN tables (one JSON per chunk), followed by the decoder source. Real decoding: tables, records and fields are named for what they mean (fence points with x/y in game units or feet and wall heights, camera names with positions, injuries with body part / severity / duration, ...), counts/offsets are derived ("_" keys) recomputed by the encoder, and the code parses each layout generically. FAIL-worthy: placeholder names for most fields, chunks kept as opaque blobs, byte lists or long unnamed word lists, hard-coded content, or an encoder that patches the original bytes instead of rebuilding. Judge the summary and the code.'
