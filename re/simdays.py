#!/usr/bin/env python3
"""Sim N days in the BBPro98 work copy and collect the result state.
usage: simdays.py N OUTDIR   (assumes game running at main menu; live-config work install)"""
import subprocess, sys, time, os
import numpy as np
from PIL import Image

N = int(sys.argv[1]); OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
XC = '/home/will/xc2.sh'
def click(x, y):
    subprocess.run([XC, 'click', str(x), str(y)])
def shot(name):
    subprocess.run([XC, 'shot', name])
    p = os.path.expanduser(f'~/{name}.png')
    for _ in range(10):
        if os.path.exists(p): break
        time.sleep(0.5)
    return np.asarray(Image.open(p).convert('L'), dtype=int)

UPD = np.asarray(Image.open('/home/will/f2.png').convert('L'), dtype=int)  # verified updating-dialog shot
SCH = np.asarray(Image.open('/home/will/f3.png').convert('L'), dtype=int)  # verified schedule shot
UPD_BOX = (slice(485, 556), slice(508, 780))   # dialog body region
DRAFT = np.asarray(Image.open('/home/will/f_draft.png').convert('L'), dtype=int)  # "ready for the Amateur draft" dialog
DRAFT_BOX = (slice(465, 535), slice(465, 815))
ASSN = np.asarray(Image.open('/home/will/f_assn.png').convert('L'), dtype=int)   # Association Data screen
TITLE_BOX = (slice(295, 322), slice(335, 800))

def state():
    a = shot('poll')
    d_upd = np.abs(a[UPD_BOX] - UPD[UPD_BOX]).mean()
    d_sch = np.abs(a[UPD_BOX] - SCH[UPD_BOX]).mean()
    return ('updating' if d_upd < d_sch else 'schedule'), d_upd, d_sch

def draft_pending(a=None):
    a = shot('poll') if a is None else a
    return np.abs(a[DRAFT_BOX] - DRAFT[DRAFT_BOX]).mean() < 15.0

def run_draft(timeout=900):
    """mid-June amateur draft: the association will not sim past it. Dismiss the notice, open the draft
    (Association > Start/Resume Draft), set Draft Delay Time to 0, Start/Continue Draft and wait for the game to return
    to the Association Data screen"""
    click(643, 566); time.sleep(2)     # notice OK
    click(445, 330); time.sleep(1.5)   # Association menu
    click(483, 490); time.sleep(5)     # Start/Resume Draft
    click(593, 330); time.sleep(1.5)   # Action menu
    click(646, 523); time.sleep(3)     # Draft Delay Time...
    for _ in range(5):
        click(570, 491); time.sleep(0.5)   # slider left arrow, down to 0 seconds
    click(582, 532); time.sleep(2)     # OK
    click(593, 330); time.sleep(1.5)   # Action menu
    click(652, 422)                    # Start/Continue Draft
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(15)
        a = shot('poll')
        if np.abs(a[TITLE_BOX] - ASSN[TITLE_BOX]).mean() < 20.0 and not draft_pending(a):
            return True
    return False

def wait_done(timeout=int(os.environ.get('SIM_TIMEOUT', '240'))):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(10)
        click(645, 535)   # repaint nudge
        time.sleep(3)
        if draft_pending(): return 'draft'
        st, du, ds = state()
        # the schedule body changes with the day's games (an empty league panel reads ~34 from the reference shot), so
        # also accept a screen clearly farther from the updating dialog than from the schedule
        if st == 'schedule' and (ds < 30.0 or du - ds > 12.0):
            return True
    return False

open(f'{OUT}/.mark', 'w').close()
# main menu -> league management (skip when already on the schedule screen)
if os.environ.get('SKIP_MENU') != '1':
    click(495, 677); time.sleep(2); click(495, 677); time.sleep(4)
day = 0
while day < N:
    if draft_pending():
        ok = run_draft()
        print(f'amateur draft: done={ok}', flush=True)
        if not ok: shot('stuck_draft'); break
    click(440, 329); time.sleep(1.5)   # Association menu
    click(445, 395); time.sleep(3)     # Schedule
    click(593, 330); time.sleep(2)     # Action menu
    click(616, 346); time.sleep(3)     # Simulate...
    click(543, 486); time.sleep(1)     # Today's games only
    click(571, 565); time.sleep(8)     # OK
    ok = wait_done()
    if ok == 'draft':       # the notice ends the day's sim before any games: draft, then sim the same day again
        ok = run_draft()
        print(f'amateur draft: done={ok}', flush=True)
        if ok: continue
        shot('stuck_draft'); break
    print(f'day {day+1}: done={ok}', flush=True)
    if ok and os.environ.get('SNAP_DAYS') == '1':   # per-day game.bki/bko + the box-score files written that day
        subprocess.run(['bash', '-c', f'W=/mnt/nvme/bbpro98/work_install; D="{OUT}/day{day+1}"; mkdir -p "$D"; '
                        f'cp -a "$W/game.bki" "$W/game.bko" "$D/"; find "$W/Stats" -maxdepth 1 -newer "{OUT}/.mark" '
                        f'-iname "MLBPA97.[HN]*" -exec cp -a {{}} "$D/" \\;; touch "{OUT}/.mark"'])
    if not ok:
        shot(f'stuck_day{day+1}'); break
    day += 1
# collect
subprocess.run(['bash', '-c', f'W=/mnt/nvme/bbpro98/work_install; cp -a "$W/Assn" "$W/Stats" "$W"/bbtrace.log "{OUT}/" 2>/dev/null; true'])
print('collected to', OUT)
