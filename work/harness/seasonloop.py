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

def say(**fields):
    """One run.log line: the fields JSON-encoded with 't' (the clock time) as the last key."""
    print(json.dumps(dict(fields, t=time.strftime('%H:%M:%S'))), flush=True)


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
CHAMP_BOX = (330, 470, 950, 750)              # body of the World Series champions photo (f_champ.png)
POST_HELD = 6                                 # still looks 20 s apart that bring the postseason wait to reopen the sim
BUSY_STILL = 12                               # still busy looks (4 min, the ASN unchanged) that mark the update box stale
CHAMP_HELD = 6                                # champion looks still up after a Return before one more Return is sent
LIST_Y, LIST_DY, LIST_ROWS = 479, 11, 9       # Open Association list: first row's y, row pitch, rows shown unscrolled


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


def on_sched(png):
    """The League Schedule screen."""
    return _diff(png, 'f_sched.png', SCHED_BOX) < 20.0


def on_champ(png):
    """The World Series champions photo (a full-screen picture with no menu bar)."""
    return _diff(png, 'f_champ.png', CHAMP_BOX) < 20.0


def busy(png):
    """The 'Updating association data for today' box is on screen: the game is working, do not touch it."""
    return _diff(png, 'f_update.png', UPDATE_BOX) < 10.0


def health(h, secs=2.0, scr=None):
    """lanestat's verdict for the lane h drives, as fields for a progress line: the game's CPU ticks over `secs`
    seconds (no sleep without game pids), the age of the newest Assn/Stats write and of the last bbtrace.log line.
    Never raises: a failure is {'verdict': 'error', 'error': <exception class name>}."""
    try:
        import lanestat          # lanestat imports this module at its top
        gp = getattr(h, 'game_pids', None)
        pids = list(gp() or []) if callable(gp) else []
        dticks = None
        if pids:
            first = {p: lanestat.ticks(p) or 0 for p in pids}
            time.sleep(secs)
            dticks = sum(max(0, (lanestat.ticks(p) or 0) - first[p]) for p in pids)
        _, mtime = lanestat.newest([os.path.join(h.WORK, 'Assn'), os.path.join(h.WORK, 'Stats')])
        write_age = None if mtime is None else int(round(time.time() - mtime))
        tpath = os.path.join(h.WORK, 'bbtrace.log')
        tage = lanestat.trace_age(lanestat.last_trace(tpath)) if os.path.exists(tpath) else None
        tage = None if tage is None else int(round(tage))
        return {'verdict': lanestat.verdict(dticks, write_age, tage, scr), 'dticks': dticks,
                'write_age_s': write_age, 'trace_age_s': tage}
    except Exception as e:
        return {'verdict': 'error', 'error': type(e).__name__}


def sim(h, shots):
    """From the schedule: Action > Simulate..., All games until next "Play", OK. First confirms the screen is the
    League Schedule: after one ctrl+k from Association Data, or refused with no click at all otherwise."""
    png = f'{shots}/_sim.png'
    look(h, png)
    if on_assn_data(png):
        h.x('key', 'ctrl+k'); time.sleep(6)
        look(h, png)
    if not on_sched(png):
        shutil.copyfile(png, f'{shots}/sim_refused.png')
        say(**{'sim': 'refused'})
        return False
    h.click(595, 330); time.sleep(2)      # Action
    h.click(615, 346); time.sleep(4)      # Simulate...
    h.click(543, 501); time.sleep(1)      # All games until next "Play"
    h.click(570, 565); time.sleep(10)     # OK
    return True


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
            say(season=stem, done=True, played=n, rounds=rnd, stops=stops)
            return True
        if rnd == 1 and n == start and _other_mtimes(asn) != others:
            # A wrong row in the association list opens another league, and the sim plays that one instead.
            say(season=stem, done=False, wrong_association=True)
            return False
        rnd += 1
        if not sim(h, shots):                 # refused off the schedule: treat the round as a stop
            last, cur, total = n, n, None
        else:
            last, quiet_since, shown = n, time.time(), time.time()
            while time.time() < t_end and time.time() - quiet_since < QUIET:
                time.sleep(10)
                cur, _ = played(asn)
                if cur is not None and cur != last:
                    last, quiet_since = cur, time.time()
                if time.time() - shown >= PROGRESS:
                    say(round=rnd, progress=last, of=total, **health(h))
                    shown = time.time()
            cur, total = played(asn)
        if total and cur == total:            # season over: the loop top reports it; nothing on screen to answer
            continue
        settle(h, shots, t_end)
        png = f'{shots}/_poll.png'
        look(h, png)
        if _diff(png, 'f_draft.png', DRAFT_BOX) < 15.0:
            ok = run_draft(h, shots)
            say(round=rnd, played=last, draft=ok)
            if not ok:
                look(h, f'{shots}/stuck_draft.png')
                return False
            continue
        cur, total = played(asn)
        if total and cur == total:
            continue
        if on_assn_data(png):                 # the sim ended back on Association Data: return to the schedule
            say(round=rnd, played=cur, assn_data=True)
            h.x('key', 'ctrl+k'); time.sleep(6)
            if cur != n:
                continue
        stops += 1
        look(h, f'{shots}/stop_{stops}.png')
        say(round=rnd, played=last, of=total, stop=stops)
        if stops > MAX_STOPS:
            return False
        h.x('key', 'Return'); time.sleep(4)
    say(season=stem, done=False, timeout=True)
    return False


def assn_row(assn_dir, stem):
    """stem's row in the Open Association list (0 is the top), or None: the list holds every association in assn_dir
    but _DEFAULT, sorted by its label (gamedata.association's name). None too when stem is missing or any label
    cannot be read (a row counted wrong would open another league)."""
    labels = []
    for path in glob.glob(os.path.join(assn_dir, '*')):
        base, ext = os.path.splitext(os.path.basename(path))
        if ext.lower() != '.asn' or base.upper() == '_DEFAULT':
            continue
        try:
            labels.append((gamedata.association(path)['name'], base.lower()))
        except (OSError, ValueError, KeyError, IndexError, struct.error):
            return None
    rows = [base for _, base in sorted(labels)]
    return rows.index(stem.lower()) if stem.lower() in rows else None


def reopen(h, stem):
    """Open stem's association from the Open Association list (ctrl+l, its row, Open). False, with no input, when its
    row is unknown or below the rows the list shows without scrolling."""
    n = assn_row(os.path.join(h.WORK, 'Assn'), stem)
    if n is None or n >= LIST_ROWS:
        return False
    h.x('key', 'ctrl+l'); time.sleep(4)
    h.click(575, LIST_Y + LIST_DY * n); time.sleep(1)
    h.click(735, 538); time.sleep(12)                # Open
    return True


def postseason(h, shots, t_end, max_sims=8, asn=None):
    """After the last regular-season game: wait for the season-complete notice while the playoffs play, reopening the
    sim only after POST_HELD unchanged looks. A busy look ('Updating association data') is progress and never sims,
    unless it holds still BUSY_STILL looks (a stale paint over the idle game: one Return);
    a champion look ('Led by Coach ..., the ... capture the World Series') is answered with Return, and after it the
    sim never reopens: a still screen with no notice reopens the association (asn given), True when that shows the
    season-complete notice, else it stops with champion_idle;
    a refused sim counts as one of max_sims. When asn is given, any other association file changing stops it with
    wrong_association and no more input."""
    a, b = f'{shots}/_post_a.png', f'{shots}/_post_b.png'
    look(h, a)
    if asn is not None:
        others = _other_mtimes(asn)
    held, sims, champ, stale, stamp, champ_held, n = 0, 0, False, 0, None, 0, 0
    shown = time.time()
    while time.time() < t_end:
        if notice(a) == 'complete':
            say(postseason='complete', sims=sims)
            return True
        time.sleep(20)
        look(h, b)
        if asn is not None and _other_mtimes(asn) != others:
            say(postseason='wrong_association')
            return False
        held = held + 1 if _same(a, b) else 0
        os.replace(b, a)
        if time.time() - shown >= PROGRESS:
            b_now = busy(a)
            say(postseason='waiting', screen='busy' if b_now else 'other', held=held, stale=stale, sims=sims,
                **health(h, scr='busy' if b_now else None))
            shown = time.time()
        if busy(a):
            # Under Wine the update box can stay painted over the idle schedule after the update ends (2025 run,
            # October 6: an hour with no input). An update writes the ASN within seconds, so a box that holds still
            # BUSY_STILL looks with the ASN unchanged is a stale paint; Return repaints it, as in season()'s stops.
            now = os.stat(asn).st_mtime_ns if asn is not None and os.path.exists(asn) else None
            stale = stale + 1 if held and now == stamp else 0
            stamp, held = now, 0
            if stale >= BUSY_STILL:
                shutil.copyfile(a, f'{shots}/stale_post.png')
                say(postseason='stale_update_box')
                h.x('key', 'Return'); time.sleep(4)
                stale = 0
                look(h, a)
                shown = time.time()
            champ_held = 0
            continue
        stale = 0
        if on_champ(a) and not champ:
            champ = True
            say(postseason='champion')
            shutil.copyfile(a, f'{shots}/champion.png')
            h.x('key', 'Return'); time.sleep(4)
            held = 0
            champ_held = 1                 # the look that showed the photo when the Return was sent
            look(h, a)
            if on_champ(a):                # the extra look right after the Return is a champion look too
                champ_held += 1
            continue
        if champ and on_champ(a):
            held = 0
            champ_held += 1
            if champ_held == CHAMP_HELD and n < 3:
                # The photo is still up CHAMP_HELD looks after the last Return: the game ignored it. One more
                # Return, at most 3 times; after that keep waiting as before.
                n += 1
                h.x('key', 'Return'); time.sleep(4)
                say(postseason='champion_retry', n=n)
                champ_held = 0
            continue
        champ_held = 0
        if held < POST_HELD or notice(a) == 'complete':
            continue
        if champ:
            # After the World Series the sim must never reopen: 2025 run, 20:56, a ctrl+k from the screen left after
            # the champion's Return opened another association's schedule and simmed its games. The 21:24 probe
            # showed why: the game writes <stem>.eos, closes the association and shows another one (MLBPA97).
            # Reopening this one brings up the season-complete notice that offseason() answers.
            shutil.copyfile(a, f'{shots}/post_champ_idle.png')
            if asn is not None and reopen(h, os.path.splitext(os.path.basename(asn))[0]):
                look(h, a)
                if notice(a) == 'complete':
                    say(postseason='complete', sims=sims, reopened=True)
                    return True
                shutil.copyfile(a, f'{shots}/post_reopen.png')
            say(postseason='champion_idle', sims=sims)
            return False
        if sims >= max_sims:
            break
        sims += 1
        if _diff(a, 'f_assn.png', TITLE_BOX) < 20.0:
            h.x('key', 'ctrl+k'); time.sleep(6)
        elif _diff(a, 'f_sched.png', SCHED_BOX) >= 20.0:
            shutil.copyfile(a, f'{shots}/post_stop_{sims}.png')
            h.x('key', 'Return'); time.sleep(4)
        say(postseason='sim', n=sims)
        sim(h, shots)
        held = 0
        look(h, a)
        shown = time.time()
    look(h, f'{shots}/stuck_post.png')
    say(postseason='stuck', sims=sims)
    return False


def offseason(h, shots, t_end):
    """From the season-complete notice to opening day: Start New Season, the free agent draft, spring training. True
    once spring training has run and Association Data shows no notice."""
    sprung, stray = False, 0
    shown = time.time()
    png, prev = f'{shots}/_poll.png', f'{shots}/_poll_prev.png'
    while time.time() < t_end:
        if os.path.exists(png):
            os.replace(png, prev)
        look(h, png)
        kind = notice(png)
        if time.time() - shown >= PROGRESS:
            say(offseason='waiting', notice=kind, sprung=sprung, stray=stray)
            shown = time.time()
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
        say(offseason=kind, sprung=sprung)
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
    pyf = _find(assn_dir, stem + '.PYF')
    return gamedata.demographics(_find(assn_dir, stem + '.ASN'), _find(assn_dir, stem + '.PYR'), pyf, year)


def champion(asn_path):
    """The season's champion from the files on disk, for one run.log line. Never raises: a log line must not stop a
    run. No bracket yet ('season', 'champion': None); a bracket gives complete, runner_up and the World Series score
    with the champion's wins first (the series order follows b['champion']). A torn or odd file can raise more than
    OSError and ValueError from the parsers (assn_row catches the same set), so the whole read is guarded."""
    try:
        return _champion(asn_path)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, struct.error) as e:
        return {'season': None, 'champion': None, 'error': str(e) or type(e).__name__}


def _champion(asn_path):
    b = gamedata.postseason(asn_path)
    a = gamedata.association(asn_path)
    year = a['season_year']

    def name(tid):
        t = a['teams'].get(tid)
        return t['name'] if t else 'team %d' % tid

    if b is None:
        return {'season': year, 'champion': None}
    out = {'season': year, 'complete': b['complete'], 'champion': None, 'runner_up': None, 'series': None}
    tid = b['champion']
    if tid is None:
        return out
    out['champion'] = name(tid)
    rounds = b.get('rounds') or []
    if len(rounds) > 2 and rounds[2]['series']:
        s = rounds[2]['series'][0]
        if tid in s['teams']:
            i = s['teams'].index(tid)
            out['runner_up'] = name(s['teams'][1 - i])
            out['series'] = '%d-%d' % (s['wins'][i], s['wins'][1 - i])
    return out


def seasons(h, shots, stem, n, limit, year):
    """Play n seasons with an offseason before each and after the last, measuring the league after every offseason.
    True when every season played all its games and every offseason reached opening day."""
    assn = os.path.join(h.WORK, 'Assn')
    say(**{'demographics': 'loaded', **demographics(assn, stem, year - 1)})
    t_end = time.time() + (n + 1) * limit
    png = f'{shots}/_poll.png'
    look(h, png)
    if notice(png) not in NOTICES:                      # mid-season: finish it first (a notice means the offseason)
        h.x('key', 'ctrl+k'); time.sleep(6)
        asn_path = os.path.join(assn, stem + '.ASN')
        if not (season(h, shots, stem, limit) and postseason(h, shots, t_end, asn=asn_path)):
            return False
        say(**dict(champion(asn_path), at='mid'))
    asn_path = os.path.join(assn, stem + '.ASN')
    for k in range(n + 1):
        if not offseason(h, shots, t_end):
            return False
        h.x('key', 'ctrl+s'); time.sleep(8)
        _snap(h, assn, stem, f'{shots}/roll_{k}')
        say(**{'demographics': k, **demographics(assn, stem, year + k)})
        if k == n:
            return True
        h.x('key', 'ctrl+k'); time.sleep(6)
        if not (season(h, shots, stem, limit) and postseason(h, shots, t_end, asn=asn_path)):
            return False
        _snap(h, assn, stem, f'{shots}/complete_{k}')   # the season-complete state, before the rollover ages anyone
        say(**dict(champion(asn_path), at=k))
    return True


def _snap(h, assn, stem, out):
    """Copy the association's files (and its Stats .DAT) as they are on disk now into out/Assn and out/Stats."""
    for sub, d in (('Assn', assn), ('Stats', os.path.join(h.WORK, 'Stats'))):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
        for f in glob.glob(os.path.join(d, '*')):
            if os.path.basename(f).lower().startswith(stem.lower() + '.'):
                shutil.copy2(f, os.path.join(out, sub))
