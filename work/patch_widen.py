#!/usr/bin/env python3
"""Retired. This was a first try at widening the Statistics screen from 8 to 12 columns: four byte patches to
BBShell.dll (0x41d0f, 0x5ba22, 0x5cebe, 0x5cf4a) and 12-column STS files, written straight into the live install.
0x41d0f lies in the Hall of Fame screen layout, not the Statistics screen, and the screen never changed
(work/PLAN_widen_oneshot.md). bbfix [widen] does the widening now. The old code is in git history (3ca74a8)."""
import sys


def main():
    sys.exit('patch_widen.py is retired: its offsets patch the Hall of Fame screen and it wrote the live install '
             'directly. Use bbfix [widen] (see work/NOTES_widen.md).')


if __name__ == '__main__':
    main()
