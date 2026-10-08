# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=hcard.py
REFEREE=(python3 -I -B "$RE/targets/hcardref.py" "$T")
AUDIT=text
HOLDOUT=1            # same checks on sim day 10 (paired with day 9), never shown to the lanes
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/stats /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|targets_holdout|/mnt/nvme|/home/will|\.\./|MLBPA97\.H'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: BBShell FUN_680264c0 reads this 0xa8a-byte table and the box-score screen prints it; the sim (BBSIM) fills it when a game ends. Find the struct the table is copied into (decompiles under /mnt/nvme/bbpro98/index/), name every member from how the box-score and game-log screens use it, and port it. Use the H files only to confirm."
  [data]="Your primary route is the DATA: decipher every H file's card, line it up with the plaintext box-score tables in the same file, that day's league file (work/league.py) and stats database (work/stats.py fielding lines), and identify each field by inspection and by diffing games. Use the decompiles only to confirm or when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for the lineup card of one game of a 1997 baseball game (two sides with team, players and their positions, pitchers used, batting order, plus game facts such as date, ballpark, weather), followed by the decoder source. Real decoding: keys say what each value is (batting_order, starter, pinch_hitter, temperature, attendance, ...) and the code reads the deciphered table at fixed struct offsets generically. FAIL-worthy: placeholder names (f12, byte_3a, unk7) for most of the non-contract fields, raw unexplained byte dumps standing in for whole regions, hard-coded games/teams/players/dates, behaviour keyed off file names or sizes, or edits copied through anything but the card fields. Judge the summary and the code.'
