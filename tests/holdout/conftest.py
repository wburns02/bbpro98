"""Holdout suite wiring: puts the repo's module folders on sys.path (the code is flat scripts, not a package).
No game files, no network, no Wine. Every test builds its own files under tmp_path."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ('news', 'work', 'hosting', os.path.join('work', 'patches'), os.path.join('tests', 'holdout')):
    path = os.path.join(REPO, sub)
    if path not in sys.path:
        sys.path.insert(0, path)
