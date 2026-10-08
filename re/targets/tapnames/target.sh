# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
# Name the tape fields tapcodec still calls at_0x.. (ROADMAP #10). No lane code runs: the referee checks NAMES.json.
DECODER=NAMES.json
REFEREE=(python3 -I -B "$RE/targets/tapnameref.py" "$T")
AUDIT=text
HOLDOUT=0
EXTRA_RO=(/mnt/nvme/bbpro98/targets_data/tap /mnt/nvme/bbpro98/index)
declare -A FOCUS=(
  [code]="Work from the code: for each field, grep its object offset in /mnt/nvme/bbpro98/index/BBSIM/_all.c (as '+ 0x44', 'param_1 + 0x11' on a 4-byte pointer, 'param_1[0x22]' on a short pointer, and so on), read the functions that set and test it, use the function labels in _functions_labeled.tsv, and check your reading against the values the field takes across the decoded tapes."
)
AUDIT_RULES='This is a list of proposed names for previously unnamed fields in the saved highlight-replay (.tap) format of a 1997 baseball game, each with a meaning, a confidence and verbatim quotes from the decompiled game code (the quotes were mechanically verified to exist in the cited functions), followed by the raw NAMES.json. CLEAN: each name follows from its quoted evidence (the quote shows the field being set, tested or used in a way that supports the meaning), low-confidence names are marked low, and nothing is invented. FAIL-worthy: names whose evidence does not mention or use the field, meanings that contradict the quotes, generic filler meanings, or confident claims with no support. Judge each field.'
