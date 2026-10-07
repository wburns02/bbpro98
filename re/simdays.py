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

def state():
    a = shot('poll')
    d_upd = np.abs(a[UPD_BOX] - UPD[UPD_BOX]).mean()
    d_sch = np.abs(a[UPD_BOX] - SCH[UPD_BOX]).mean()
    return ('updating' if d_upd < d_sch else 'schedule'), d_upd, d_sch

def wait_done(timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(10)
        click(645, 535)   # repaint nudge
        time.sleep(3)
        st, du, ds = state()
        if st == 'schedule' and ds < 30.0:
            return True
    return False

# main menu -> league management (skip when already on the schedule screen)
if os.environ.get('SKIP_MENU') != '1':
    click(495, 677); time.sleep(2); click(495, 677); time.sleep(4)
for day in range(N):
    click(440, 329); time.sleep(1.5)   # Association menu
    click(445, 395); time.sleep(3)     # Schedule
    click(593, 330); time.sleep(2)     # Action menu
    click(616, 346); time.sleep(3)     # Simulate...
    click(543, 486); time.sleep(1)     # Today's games only
    click(571, 565); time.sleep(8)     # OK
    ok = wait_done()
    print(f'day {day+1}: done={ok}', flush=True)
    if not ok:
        shot(f'stuck_day{day+1}'); break
# collect
subprocess.run(['bash', '-c', f'W=/mnt/nvme/bbpro98/work_install; cp -a "$W/Assn" "$W/Stats" "$W"/bbtrace.log "{OUT}/" 2>/dev/null; true'])
print('collected to', OUT)
