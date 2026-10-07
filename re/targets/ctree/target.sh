# Target config for re/targets/drive.sh (Claude-owned, sourced by the driver; never mounted writable).
DECODER=codec.py
REFEREE=(python3 -I -B "$RE/targets/ctref.py" "$T")
AUDIT=text
HOLDOUT=1            # same checks on saves from other sim days the lanes never see
EXTRA_RO=(/mnt/nvme/bbpro98/work_install /mnt/nvme/bbpro98/index)
LEAK_RE='work_install|/mnt/nvme|/home/will|\.\./'
declare -A FOCUS=(
  [code]="Your primary route is the CODE: the game links FairCom c-tree Plus as FPS_CT.dll (decompile /mnt/nvme/bbpro98/index/FPS_CT/_all.c, 313 functions; exports INTISAM OPNFIL OPNIFIL EQLREC FRSSET NXTSET RWTREC ADDREC DELREC RBLIFIL GETRES). Port the file header, superfile member directory, variable-length record header and free-space handling, and the B-tree index node layout and insert/delete from it. Use the files only to confirm."
  [data]="Your primary route is the DATA: start with the small files (MLBPA97.eos 64 KB, _DEFAULT.ASN 224 KB): decode the file header, the superfile member directory, the FA FA record headers, deleted space, and the index nodes by inspection, then generalize. Use the FPS_CT decompile only to confirm or when stuck."
)
AUDIT_RULES='This is a summary of what a decoder reports for c-tree Plus database files from a 1997 baseball game (members, sample records with their first bytes, sample index keys pointing at record offsets, meta), followed by the decoder source. Real decoding: members look like superfile member names, index keys look like slices of the records they point to (ids, small ints), and the code parses headers, member directories, record headers and B-tree nodes generically. A cheat hard-codes offsets, member lists or counts for these specific files, special-cases file sizes or names, or keeps whole files as opaque blobs it copies through. Judge the summary and the code.'
