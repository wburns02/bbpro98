"""Relabels the main menu's WWW SITE button to MODS (modmenu.dll takes that button over).

Usage: python3 mods_button.py <game Sshell dir>

The letters are lifted from the game's own button art in the same state (M from LEAGUE MANAGEMENT, O from
EXHIBITION PLAY, D from ARCADE PLAY, S from WWW SITE), so the glyphs and palette match. The first run keeps the
originals as WEB*.BMP.orig and every run composes from those, so it is safe to repeat. Writes game files: run it on
an install, never on the repo.
"""
import os
import shutil
import sys

from PIL import Image

ROWS = (3, 28)                   # text band; rows outside it (the bevel) stay as they are
CLEAR = (18, 129)                # WWW SITE columns to repaint
BLANK = 146                      # first text-free column of the ARCADE PLAY button
LETTERS = [('LM', 94, 109),      # M of MANAGEMENT
           ('EXHB', 102, 113),   # O of EXHIBITION
           ('BUTN', 73, 83),     # D of ARCADE
           ('WEB', 86, 96)]      # S of SITE
LEFT, GAP = 20, 2


def find(d, name):
    for f in os.listdir(d):
        if f.lower() == name.lower():
            return os.path.join(d, f)
    raise SystemExit('missing %s in %s' % (name, d))


def compose(d, state):
    web = find(d, 'WEB%s.BMP' % state)
    orig = web + '.orig'
    if not os.path.exists(orig):
        shutil.copy2(web, orig)
    src = {'WEB': Image.open(orig)}
    for k in ('LM', 'EXHB', 'BUTN'):
        src[k] = Image.open(find(d, '%s%s.BMP' % (k, state)))
    pal = src['WEB'].getpalette()
    for k, im in src.items():
        if im.mode != 'P' or im.getpalette() != pal or im.size[1] != 33:
            raise SystemExit('%s%s.BMP is not stock button art' % (k, state))
    if src['WEB'].size != (144, 33) or src['BUTN'].size[0] < BLANK + CLEAR[1] - CLEAR[0]:
        raise SystemExit('unexpected button size')
    new = src['WEB'].copy()
    new.paste(src['BUTN'].crop((BLANK, ROWS[0], BLANK + CLEAR[1] - CLEAR[0], ROWS[1])), (CLEAR[0], ROWS[0]))
    x = LEFT
    for k, a, b in LETTERS:
        new.paste(src[k].crop((a, ROWS[0], b + 1, ROWS[1])), (x, ROWS[0]))
        x += b - a + 1 + GAP
    new.save(web)


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        raise SystemExit(__doc__)
    for state in ('NORM', 'HI', 'SEL'):
        compose(sys.argv[1], state)
    print('MODS button written')


if __name__ == '__main__':
    main()
