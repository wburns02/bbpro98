# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=stats.py
REFEREE=(python3 -I -B "$RE/targets/statsref.py" "$T")
AUDIT=text
HOLDOUT=1            # same checks on sim day 10 (paired with day 9) and a season-10 save the lanes never see
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/stats /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|targets_holdout|/mnt/nvme|/home/will|\.\./|MLBPA97\.H'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: the stats screens and the sim's stat accumulation live in Upstats.dll, BBShell.dll and BBSIM.dll (decompiles under /mnt/nvme/bbpro98/index/). Find the code that builds the 22/36/150-byte records and the split lines (what each word counts, which split each line is), and the column headers the stats screens print, and name every field from them. Use the day files only to confirm."
  [data]="Your primary route is the DATA: diff consecutive days record by record against that day's box scores (MLBPA97.H*), and check sums across lines of one player (splits add up to totals, fielding lines add up across positions) to identify every record type, split key and field. Use the decompiles only to confirm or when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for the stats database of a 1997 baseball game (stat records grouped by scope, kind and period with sample fields), followed by the decoder source. Real decoding: field names say what each number counts (ab, hr, po, a, e, ip_outs, ...), groups have meaningful kinds/periods (season, career, last season, recent, team, fielding by position, splits vs LHP/RHP, home/away, by month ...), and the code parses c-tree records generically. FAIL-worthy: field names that are placeholders (m8_aa, field_a, a1, col_x) for most fields of a record type, kinds like rec22/other for whole record types, hard-coded offsets/records/players for these files, or copying edits through anything but the records. Judge the summary and the code.'
