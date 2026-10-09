"""The "season" step of ingame.py: sim the loaded association's regular season to the end.

    ["season", "30L1998", 7200]        association stem, time limit in seconds

Starts on the League Schedule screen (ctrl+k from Association Data). Each round opens Action > Simulate..., picks
"All games until next Play" (no game is marked Play, so it runs until something stops it) and waits until the
association file on disk stops gaining played games and the screen holds still. The game stops for the mid-June amateur draft notice; that is
answered with a zero-delay automatic draft, the same clicks re/simdays.py uses. Any other stop is screenshotted
(stop_<n>.png), answered with Enter, and the sim reopened, at most MAX_STOPS times. Done when every regular-season
game of the ASN is played. Prints one JSON line per round.
"""
import json
import os
import sys
import time

from PIL import Image, ImageChops, ImageStat

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'news'))
import gamedata  # noqa: E402

REFS = '/mnt/nvme/bbpro98/harness_refs'      # game screenshots (Sierra's art), kept out of the repo
DRAFT_BOX = (465, 465, 815, 535)              # (left, top, right, bottom) of the draft notice body
TITLE_BOX = (335, 295, 420, 322)              # 'Associat' of the title bar; the rest is the association's name
SCREEN = (128, 137, 1152, 905)                # the game's 1024x768 area of the screenshot
UPDATE_BOX = (507, 491, 773, 503)             # 'Updating association data for today' (f_update.png)
QUIET = 60                                    # seconds without a newly played game that end a sim round
MAX_STOPS = 12


def _diff(png, ref, box):
    a = Image.open(png).convert('L').crop(box)
    b = Image.open(os.path.join(REFS, ref)).convert('L').crop(box)
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def _same(a, b):
    x = Image.open(a).convert('L').crop(SCREEN)
    y = Image.open(b).convert('L').crop(SCREEN)
    return ImageStat.Stat(ImageChops.difference(x, y)).mean[0] < 1.0


def settle(h, shots, t_end, gap=20):
    """Wait until the game has finished its end-of-day update: no 'Updating association data' box on screen and two
    screenshots gap seconds apart match. On a draft day the update runs for minutes, past QUIET, and can sit on one
    team longer than gap."""
    a, b = f'{shots}/_settle_a.png', f'{shots}/_settle_b.png'
    h.shot(a)
    while time.time() < t_end:
        time.sleep(gap)
        h.shot(b)
        if _same(a, b) and _diff(b, 'f_update.png', UPDATE_BOX) >= 10.0:
            return
        os.replace(b, a)


def on_assn_data(png):
    """The Association Data screen with no draft notice over it."""
    return _diff(png, 'f_assn.png', TITLE_BOX) < 20.0 and _diff(png, 'f_draft.png', DRAFT_BOX) >= 15.0


def played(asn):
    """(played, scheduled) regular-season games of the ASN; (None, None) while the file is mid-write."""
    try:
        games = gamedata.association(asn)['games']
    except Exception:           # the game rewrites the file in place during a sim
        return None, None
    return sum(1 for g in games if g['played']), len(games)


def run_draft(h, shots, timeout=900):
    """Dismiss the draft notice, open Association > Start/Resume Draft, set Draft Delay Time to 0, start it and wait
    for the Association Data screen."""
    h.click(643, 566); time.sleep(2)     # notice OK
    h.click(445, 330); time.sleep(1.5)   # Association menu
    h.click(483, 490); time.sleep(5)     # Start/Resume Draft
    h.click(593, 330); time.sleep(1.5)   # Action menu
    h.click(646, 523); time.sleep(3)     # Draft Delay Time...
    for _ in range(5):
        h.click(570, 491); time.sleep(0.5)
    h.click(582, 532); time.sleep(2)     # OK
    h.click(593, 330); time.sleep(1.5)   # Action menu
    h.click(652, 422)                    # Start/Continue Draft
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(15)
        png = f'{shots}/_poll.png'
        h.shot(png)
        if on_assn_data(png):
            h.x('key', 'ctrl+k'); time.sleep(6)          # back to the schedule
            return True
    return False


def season(h, shots, stem, limit):
    """Sim to the end of the regular season. True when every scheduled game is played."""
    asn = os.path.join(h.WORK, 'Assn', stem + '.ASN')
    t_end, stops, rnd = time.time() + limit, 0, 0
    while time.time() < t_end:
        n, total = played(asn)
        if total and n == total:
            print(json.dumps({'season': stem, 'done': True, 'played': n, 'rounds': rnd, 'stops': stops}), flush=True)
            return True
        rnd += 1
        h.click(595, 330); time.sleep(2)      # Action
        h.click(615, 346); time.sleep(4)      # Simulate...
        h.click(543, 501); time.sleep(1)      # All games until next "Play"
        h.click(570, 565); time.sleep(10)     # OK
        last, quiet_since = n, time.time()
        while time.time() < t_end and time.time() - quiet_since < QUIET:
            time.sleep(10)
            cur, _ = played(asn)
            if cur is not None and cur != last:
                last, quiet_since = cur, time.time()
        settle(h, shots, t_end)
        png = f'{shots}/_poll.png'
        h.shot(png)
        if _diff(png, 'f_draft.png', DRAFT_BOX) < 15.0:
            ok = run_draft(h, shots)
            print(json.dumps({'round': rnd, 'played': last, 'draft': ok}), flush=True)
            if not ok:
                h.shot(f'{shots}/stuck_draft.png')
                return False
            continue
        cur, total = played(asn)
        if total and cur == total:
            continue
        if on_assn_data(png):                 # the sim ended back on Association Data: return to the schedule
            print(json.dumps({'round': rnd, 'played': cur, 'assn_data': True}), flush=True)
            h.x('key', 'ctrl+k'); time.sleep(6)
            if cur != n:
                continue
        stops += 1
        h.shot(f'{shots}/stop_{stops}.png')
        print(json.dumps({'round': rnd, 'played': last, 'of': total, 'stop': stops}), flush=True)
        if stops > MAX_STOPS:
            return False
        h.x('key', 'Return'); time.sleep(4)
    print(json.dumps({'season': stem, 'done': False, 'timeout': True}), flush=True)
    return False
