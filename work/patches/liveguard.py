"""Import first. Refuses to run if any argv path resolves inside the live game install."""
import os, sys
LIVE=os.path.realpath(os.path.expanduser('~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98'))
for a in sys.argv[1:]:
    if os.path.realpath(a).startswith(LIVE+os.sep) or os.path.realpath(a)==LIVE:
        sys.exit(f'REFUSED: {a} is inside the live install ({LIVE}). Use /mnt/nvme/bbpro98/work_install.')
