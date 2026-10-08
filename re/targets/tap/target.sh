# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=voldat.py
REFEREE=(python3 -I -B "$RE/targets/voldatref.py" "$T")
AUDIT=text
HOLDOUT=1            # 3 unseen highlight files + unseen random edits
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/tap /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|targets_holdout|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: BBSIM writes and replays highlights (strings 'hilights\%s', '%s\%s%03u.tap', '%s\highlight*.tap', 'NoHighlights'); grep those in /mnt/nvme/bbpro98/index/BBSIM/_all.c, follow the writer and the replay reader to the record structs, and name every field from its use (game/inning/score state, the play, player and team records, animation/ball data)."
  [data]="Your primary route is the DATA: hexdump the .tap files and MLBPA97.NQ0 (the queue: a small header then records like the .tap ones), find the header, the record boundaries and sizes, the text (date, teams, score, inning, outs, batter-pitcher), the team/player blocks and the per-frame play data, and infer meanings from the values; confirm in BBSIM (grep 'hilights' and '.tap')."
)
AUDIT_RULES='This is a summary of what a decoder reports for the saved highlight replays (.tap) and the highlight queue (.NQ0) of a 1997 baseball game, one JSON per file, followed by the decoder source. Real decoding: the header and each record are named for what they mean (date, teams, score, inning, outs, batter/pitcher, player and team blocks, the play/animation frames with positions and timing), counts/offsets/padding are derived ("_" keys) and recomputed, and the code parses records generically. FAIL-worthy: placeholder names for most fields, regions kept as opaque blobs or byte lists, hard-coded content, or an encoder that copies the input instead of rebuilding. Judge the summary and the code.'
