# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=voldat.py
REFEREE=(python3 -I -B "$RE/targets/gamebkref.py" "$T")
AUDIT=text
HOLDOUT=1            # unseen sim days (their box scores) + more random edits
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/gamebk /mnt/nvme/bbpro98/index)
LEAK_RE='targets_data|targets_holdout|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: follow the readers and writers in the decompiles (BBShell renames game.in/game.out to game.bki/game.bko near _all.c line 80818; the GDI reader is near line 80560, the GDO reader near 81615, tag DAT_6808c89c; grep \"game.in\", \"game.out\", \"GDI:\", \"GDO:\" in BBSIM and FastSim for the sim side that reads GDI and writes GDO) to the structs and the event codes, and name everything from that use."
  [data]="Your primary route is the DATA: decipher each GDI record, hexdump GDI and GDO, line the GDO event stream up against the matching box score (decode the day's MLBPA97.H?? files with the H layout facts in TASK.md and the referee output), and infer each event code from what it does to the box score. Confirm in the code."
)
AUDIT_RULES='This is a summary of what a decoder reports for the two hand-off files of one simulated day of a 1997 baseball game (game.bki: the per-game setup the shell sends to the simulator, enciphered; game.bko: the per-game result the simulator sends back, a play-by-play event stream), followed by the decoder source. Real decoding: the cipher is implemented, fields are named for what they mean (teams, managers, stadium, rosters, lineups, pitching staff, events with batter/pitcher/fielders/outcome), the box-score rows are DERIVED by replaying the decoded events (not copied from anywhere, not hard-coded), counts/lengths are "_" keys the encoder recomputes, and the code parses generically. FAIL-worthy: placeholder names for most fields, records kept as opaque blobs or byte lists, hard-coded content or box scores, or an encoder that copies the input instead of rebuilding. Judge the summary and the code.'
