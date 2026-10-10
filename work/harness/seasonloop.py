"""The "season" step of ingame.py: sim the loaded association's regular season to the end.

    ["season", "30L1998", 7200]        association stem, time limit in seconds

Starts on the League Schedule screen (ctrl+k from Association Data). Each round opens Action > Simulate..., picks
"All games until next Play" (no game is marked Play, so it runs until something stops it) and waits until the
association file on disk stops gaining played games and the screen holds still. The game stops for the mid-June amateur draft notice; that is
answered with a zero-delay automatic draft, the same clicks re/simdays.py uses. Any other stop is screenshotted
(stop_<n>.png), answered with Enter, and the sim reopened, at most MAX_STOPS times. Done when every regular-season
game of the ASN is played. Prints one JSON line per round.

    ["seasons", "MLBPA97", 2, 7200, 2007]  association stem, seasons to play, seconds per season, year of the next
                                           season to start

Plays seasons back to back with an offseason before each and one after the last: the season-complete notice is
answered with Association > Start New Season, the free agent draft with a zero-delay automatic draft, the spring
notice with Association > Start Spring Training. After every offseason it saves (ctrl+s), copies the association
files to SHOTDIR/roll_<n>/ and prints a JSON line of the league's demographics (rostered players' mean age and age
histogram, free agents, retired players), so a change to aging or retirement is measured each offseason rather than
only at the end. A loaded association that is mid-season plays out its season first.
"""
import collections
import datetime
import glob
import json
import os
import shutil
import struct
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
PROGRESS = 600                                # seconds between progress lines while a round runs
NOTICE_BOX = (450, 462, 830, 535)             # body of the game's centred notice dialogs
NOTICES = {'complete': 'f_complete.png', 'fa': 'f_fa.png', 'spring': 'f_spring.png', 'amateur': 'f_draft.png'}
SCHED_BOX = (335, 295, 470, 322)              # 'League Sch' of the schedule's title bar (f_sched.png)


def _diff(png, ref, box):
    a = Image.open(png).convert('L').crop(box)
    b = Image.open(os.path.join(REFS, ref)).convert('L').crop(box)
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def _same(a, b):
    x = Image.open(a).convert('L').crop(SCREEN)
    y = Image.open(b).convert('L').crop(SCREEN)
    return ImageStat.Stat(ImageChops.difference(x, y)).mean[0] < 1.0


def look(h, png):
    """Screenshot after moving the pointer over the banner above the game's dialogs: under Wine a dialog the game
    raises during a sim (the draft notice) is not painted until the window sees input."""
    h.x('mousemove', 640, 200); time.sleep(0.3)
    h.x('mousemove', 650, 205); time.sleep(1.5)
    h.shot(png)


def settle(h, shots, t_end, gap=20, still=4):
    """Wait until the game has finished its end-of-day update: two screenshots gap seconds apart match and either no
    'Updating association data' box is on screen or the screen has held still for `still` gaps. Without look()'s
    pointer move the update box stays painted over the draft notice while the game sits idle, and even with it the
    box can stay up on an idle screen."""
    a, b = f'{shots}/_settle_a.png', f'{shots}/_settle_b.png'
    look(h, a)
    held = 0
    while time.time() < t_end:
        time.sleep(gap)
        look(h, b)
        held = held + 1 if _same(a, b) else 0
        if held and (held >= still or _diff(b, 'f_update.png', UPDATE_BOX) >= 10.0):
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


def notice(png):
    """Which notice is on screen: 'complete' (season over), 'fa' or 'amateur' (a draft is due), 'spring', or None.
    The closest pair of references is 16 apart over NOTICE_BOX; a match is under 8."""
    d = {k: _diff(png, ref, NOTICE_BOX) for k, ref in NOTICES.items()}
    best = min(d, key=d.get)
    return best if d[best] < 8.0 else None


def assoc_item(h, y):
    h.click(445, 330); time.sleep(1.5)   # Association menu
    h.click(477, y); time.sleep(2)


def start_draft(h):
    """From a draft notice: dismiss it, open Association > Start/Resume Draft, set Draft Delay Time to 0, start it."""
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


def run_draft(h, shots, timeout=900):
    """Run the mid-season draft and go back to the schedule once the Association Data screen is up."""
    start_draft(h)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(15)
        png = f'{shots}/_poll.png'
        look(h, png)
        if on_assn_data(png):
            h.x('key', 'ctrl+k'); time.sleep(6)          # back to the schedule
            return True
    return False


def sim(h):
    """From the schedule: Action > Simulate..., All games until next "Play", OK."""
    h.click(595, 330); time.sleep(2)      # Action
    h.click(615, 346); time.sleep(4)      # Simulate...
    h.click(543, 501); time.sleep(1)      # All games until next "Play"
    h.click(570, 565); time.sleep(10)     # OK


def _other_mtimes(asn):
    """{path: mtime} of every other association file in asn's directory."""
    d = os.path.dirname(asn)
    return {p: os.stat(p).st_mtime_ns for p in glob.glob(os.path.join(d, '*.ASN')) + glob.glob(os.path.join(d, '*.asn'))
            if os.path.basename(p).lower() != os.path.basename(asn).lower()}


def season(h, shots, stem, limit):
    """Sim to the end of the regular season. True when every scheduled game is played."""
    asn = os.path.join(h.WORK, 'Assn', stem + '.ASN')
    t_end, stops, rnd = time.time() + limit, 0, 0
    others = _other_mtimes(asn)
    start, _ = played(asn)
    while time.time() < t_end:
        n, total = played(asn)
        if total and n == total:
            print(json.dumps({'season': stem, 'done': True, 'played': n, 'rounds': rnd, 'stops': stops}), flush=True)
            return True
        if rnd == 1 and n == start and _other_mtimes(asn) != others:
            # A wrong row in the association list opens another league, and the sim plays that one instead.
            print(json.dumps({'season': stem, 'done': False, 'wrong_association': True}), flush=True)
            return False
        rnd += 1
        sim(h)
        last, quiet_since, shown = n, time.time(), time.time()
        while time.time() < t_end and time.time() - quiet_since < QUIET:
            time.sleep(10)
            cur, _ = played(asn)
            if cur is not None and cur != last:
                last, quiet_since = cur, time.time()
            if time.time() - shown >= PROGRESS:
                print(json.dumps({'round': rnd, 'progress': last, 'of': total}), flush=True)
                shown = time.time()
        cur, total = played(asn)
        if total and cur == total:            # season over: the loop top reports it; nothing on screen to answer
            continue
        settle(h, shots, t_end)
        png = f'{shots}/_poll.png'
        look(h, png)
        if _diff(png, 'f_draft.png', DRAFT_BOX) < 15.0:
            ok = run_draft(h, shots)
            print(json.dumps({'round': rnd, 'played': last, 'draft': ok}), flush=True)
            if not ok:
                look(h, f'{shots}/stuck_draft.png')
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
        look(h, f'{shots}/stop_{stops}.png')
        print(json.dumps({'round': rnd, 'played': last, 'of': total, 'stop': stops}), flush=True)
        if stops > MAX_STOPS:
            return False
        h.x('key', 'Return'); time.sleep(4)
    print(json.dumps({'season': stem, 'done': False, 'timeout': True}), flush=True)
    return False


def postseason(h, shots, t_end, max_sims=8):
    """After the last regular-season game: wait for the season-complete notice while the playoffs play, reopening
    the sim whenever the screen holds still for three looks without it."""
    a, b = f'{shots}/_post_a.png', f'{shots}/_post_b.png'
    look(h, a)
    held, sims = 0, 0
    while time.time() < t_end:
        if notice(a) == 'complete':
            print(json.dumps({'postseason': 'complete', 'sims': sims}), flush=True)
            return True
        time.sleep(20)
        look(h, b)
        held = held + 1 if _same(a, b) else 0
        os.replace(b, a)
        if held < 3 or notice(a) == 'complete':
            continue
        if sims >= max_sims:
            break
        sims += 1
        if _diff(a, 'f_assn.png', TITLE_BOX) < 20.0:
            h.x('key', 'ctrl+k'); time.sleep(6)
        elif _diff(a, 'f_sched.png', SCHED_BOX) >= 20.0:
            shutil.copyfile(a, f'{shots}/post_stop_{sims}.png')
            h.x('key', 'Return'); time.sleep(4)
        print(json.dumps({'postseason': 'sim', 'n': sims}), flush=True)
        sim(h)
        held = 0
        look(h, a)
    look(h, f'{shots}/stuck_post.png')
    print(json.dumps({'postseason': 'stuck', 'sims': sims}), flush=True)
    return False


def offseason(h, shots, t_end):
    """From the season-complete notice to opening day: Start New Season, the free agent draft, spring training. True
    once spring training has run and Association Data shows no notice."""
    sprung, stray = False, 0
    png, prev = f'{shots}/_poll.png', f'{shots}/_poll_prev.png'
    while time.time() < t_end:
        if os.path.exists(png):
            os.replace(png, prev)
        look(h, png)
        kind = notice(png)
        if kind == 'complete':
            h.click(643, 556); time.sleep(2)
            assoc_item(h, 456); time.sleep(10)          # Start New Season
        elif kind in ('fa', 'amateur'):
            start_draft(h)
            t_draft = time.time() + 1800
            while time.time() < min(t_end, t_draft):
                time.sleep(15)
                look(h, png)
                if notice(png) or _diff(png, 'f_assn.png', TITLE_BOX) < 20.0:
                    break
        elif kind == 'spring':
            h.click(643, 566); time.sleep(2)
            assoc_item(h, 507)                          # Start Spring Training
            settle(h, shots, t_end)
            sprung = True
        elif sprung and _diff(png, 'f_assn.png', TITLE_BOX) < 20.0:
            return True
        elif not (os.path.exists(prev) and _same(prev, png)):
            time.sleep(10)                              # still working (the rollover's update runs for minutes)
            continue
        else:
            stray += 1
            shutil.copyfile(png, f'{shots}/off_stop_{stray}.png')
            if stray > MAX_STOPS:
                break
            if _diff(png, 'f_assn.png', TITLE_BOX) >= 20.0 and _diff(png, 'f_sched.png', SCHED_BOX) >= 20.0:
                h.x('key', 'Return')
            time.sleep(10)
        print(json.dumps({'offseason': kind, 'sprung': sprung}), flush=True)
    look(h, f'{shots}/stuck_offseason.png')
    return False


def _find(d, name):
    """d/name matched case-insensitively (the game writes MLBPA97.pyf next to MLBPA97.PYR)."""
    hits = [p for p in glob.glob(os.path.join(d, '*')) if os.path.basename(p).lower() == name.lower()]
    return hits[0] if hits else None


def demographics(assn_dir, stem, year):
    """The league's age make-up from the files on disk, ages as of July 1 of `year`: rostered players (in any
    team's r record), free agents (the .pyf list) and retired players (in the PYR but on neither), plus the smallest
    roster and the fewest pitchers (PYR position P) on any team."""
    recs = {}
    for p in gamedata._records(_find(assn_dir, stem + '.PYR')):
        pid = p[0] | p[1] << 8
        if pid >= 100 and gamedata._pname(p):
            recs[pid] = p
    roster, sizes = set(), []
    for t in gamedata.association(_find(assn_dir, stem + '.ASN'))['teams'].values():
        roster |= set(t['roster'])
        mine = [recs[i] for i in t['roster'] if i in recs]
        sizes.append((len(mine), sum(p[gamedata.P_POS] == 1 for p in mine)))
    fa = set()
    pyf = _find(assn_dir, stem + '.PYF')
    if pyf:
        with open(pyf, 'rb') as fh:
            b = fh.read()
        n = struct.unpack_from('<h', b, 8)[0]
        fa = set(struct.unpack_from('<%dH' % n, b, 10))

    def age(pid):
        try:
            born = datetime.date.fromordinal(struct.unpack_from('<I', recs[pid], 0x1a)[0] - 365)
        except (ValueError, OverflowError):
            return None
        return year - born.year - ((7, 1) < (born.month, born.day))

    ra = [a for a in map(age, roster & set(recs)) if a is not None]
    fa_a = [a for a in map(age, fa & set(recs)) if a is not None]
    return {'year': year, 'rostered': len(ra), 'mean_age': round(sum(ra) / max(1, len(ra)), 2),
            'le25': sum(a <= 25 for a in ra), 'ge33': sum(a >= 33 for a in ra),
            'hist': dict(sorted(collections.Counter(ra).items())), 'fa': len(fa_a),
            'fa_mean_age': round(sum(fa_a) / max(1, len(fa_a)), 2), 'retired': len(set(recs) - roster - fa),
            'players': len(recs), 'roster_min': min((n for n, _ in sizes), default=0),
            'pitchers_min': min((k for _, k in sizes), default=0)}


def seasons(h, shots, stem, n, limit, year):
    """Play n seasons with an offseason before each and after the last, measuring the league after every offseason.
    True when every season played all its games and every offseason reached opening day."""
    assn = os.path.join(h.WORK, 'Assn')
    print(json.dumps({'demographics': 'loaded', **demographics(assn, stem, year - 1)}), flush=True)
    t_end = time.time() + (n + 1) * limit
    png = f'{shots}/_poll.png'
    look(h, png)
    if notice(png) not in NOTICES:                      # mid-season: finish it first (a notice means the offseason)
        h.x('key', 'ctrl+k'); time.sleep(6)
        if not (season(h, shots, stem, limit) and postseason(h, shots, t_end)):
            return False
    for k in range(n + 1):
        if not offseason(h, shots, t_end):
            return False
        h.x('key', 'ctrl+s'); time.sleep(8)
        _snap(h, assn, stem, f'{shots}/roll_{k}')
        print(json.dumps({'demographics': k, **demographics(assn, stem, year + k)}), flush=True)
        if k == n:
            return True
        h.x('key', 'ctrl+k'); time.sleep(6)
        if not (season(h, shots, stem, limit) and postseason(h, shots, t_end)):
            return False
        _snap(h, assn, stem, f'{shots}/complete_{k}')   # the season-complete state, before the rollover ages anyone
    return True


def _snap(h, assn, stem, out):
    """Copy the association's files (and its Stats .DAT) as they are on disk now into out/Assn and out/Stats."""
    for sub, d in (('Assn', assn), ('Stats', os.path.join(h.WORK, 'Stats'))):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
        for f in glob.glob(os.path.join(d, '*')):
            if os.path.basename(f).lower().startswith(stem.lower() + '.'):
                shutil.copy2(f, os.path.join(out, sub))
