# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=dmp.py
REFEREE=(python3 -I -B "$RE/targets/dmpref.py" "$T")
AUDIT=text
HOLDOUT=1            # synthetic files built from the real paths (shuffled, resized, perturbed)
EXTRA_RO=(/mnt/nvme/bbpro98/work_install /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: BBSIM FUN_68024001 (dmp.cpp) loads the file into 0xf86-byte path objects (constructor FUN_68023f28); FastSim FDMP.cpp has a twin. Find every reader of those objects in /mnt/nvme/bbpro98/index/BBSIM/_all.c and FastSim/_all.c (who indexes the path array, which path index is used for which play: fielder run, throw, catch, slide, ...; what each of the 31 frame words and the two header words drive) and name them from that use. Use the file's numbers only to confirm."
  [data]="Your primary route is the DATA: the 31 words per frame look like 10 (x, y, z) points plus one more value; work out which point is which body part or object (heights, distances between points that stay constant = limb lengths, which points move most), what the extra word and the two header words are, and how duplicate paths relate; then confirm in the BBSIM/FastSim code (FUN_68024001 loads the file) what each path index is used for."
)
AUDIT_RULES='This is a summary of what a decoder reports for the motion-path file of a 1997 baseball game (66 paths of keyframes; each frame 31 signed 16-bit values), followed by the decoder source. Real decoding: keys say what each value is (e.g. named body parts or objects with x/y/z, a time/tick or flag word, header fields with a stated meaning, a per-path description of the motion it drives) and the code reads the offset table and frames generically. FAIL-worthy: placeholder names (j3, p7_x, w12, unk) for most values, invented meanings contradicted by the code, hard-coded path data, or an encoder that copies the input file instead of rebuilding from the JSON. Judge the summary and the code.'
