# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=league.py
REFEREE=(python3 -I -B "$RE/targets/asnref.py" "$T")
AUDIT=text
HOLDOUT=1            # same checks on a sim day (paired with day09) and a season save the lanes never see
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/league /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|targets_holdout|/mnt/nvme|/home/will|\.\./|MLBPA97\.H'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: find where BBShell/BBSIM read and write the league members (team records, rosters, schedule, standings) in the decompiles under /mnt/nvme/bbpro98/index/ (start from the c-tree wrapper calls in BBSIM/_all.c lines 16455-16760 and the IFIL tables that name each member and give its record length), recover the C struct layouts from the field accesses, and port them. Use the day files only to confirm."
  [data]="Your primary route is the DATA: dump each day's ASN with the c-tree codec, decipher the records, and diff consecutive days against that day's box scores (which teams won, the runs) to locate wins, losses, played flags, scores and roster slots by inspection. Use the decompiles only to confirm or when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for the league file of a 1997 baseball game (28 teams with names, W/L records and roster player ids; the schedule with home/away team ids, played flags and runs), followed by the decoder source. Real decoding: W/L and runs vary plausibly, rosters hold ~25-40 ids per team, and the code reads record fields from the c-tree records generically (deciphered bytes at fixed struct offsets). A cheat hard-codes standings, game results, rosters or team lists, keys behaviour off file sizes or names, derives results from anything but the league file passed on the command line, or stores a shadow copy of the JSON inside the file. Judge the summary and the code.'
