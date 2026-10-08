#!/usr/bin/env python3
"""#11 in-game test of an injury name edit, seen in the association news after a simulated day.

usage: t_injury_edit.py PRISTINE_SHELL.VOL OUTDIR

The injury names the shell prints are not the sims' injury.dat text (part / detail / condition: no binary reads those
fields; BBSIM and FastSim only use an injury's number, duration and after roll). They are strings 83..287 of section 0
of SHELL.VOL ASNEWS.DAT and TMNEWS.DAT, injury number n at index 82 + n ("bruised cheekbone" = injury 1).
This test builds
  SHELL.VOL  (volcodec + strtable)  every injury name in ASNEWS.DAT and TMNEWS.DAT -> "claudeitis"
  PB.INI     [PlayBalance] injuryChance* = 1 for the per-play checks, so the sim's rand(odds) == 0 test
             (BBSIM FUN_68038517, FastSim's copy) passes on every check and the day's games produce injuries
then opens the league, simulates today's games (the re/simdays.py chain), opens the news and OCRs it.
Every edited file, PB.INI and the league state the day writes are restored or removed afterwards (ingame.py).

Seen 2026-10-08: the Association News (Association > News, ctrl+z) Injuries box lists the day's injuries as
"ANA RF Tim Salmon (claudeitis) is day-to-day (severity = 12%)."; with PB.INI the first day of the season (April 15)
filled it, with the shipped odds an injury in one day is rare.
"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import strtable, volcodec

NAME = 'claudeitis'
FIRST, COUNT = 83, 205
ODDS = ['injuryChanceRunThroughFirst', 'injuryChanceThrowBall', 'injuryChanceRunBases', 'injuryChanceFieldFlyBall',
        'injuryChanceFieldGrounder', 'injuryChanceBatterSwing']


def main():
    src, out = sys.argv[1], os.path.abspath(sys.argv[2])
    steps_file = sys.argv[3] if len(sys.argv) > 3 else None
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='injvol', dir=out) as td:
        volcodec.unpack(src, td)
        man = json.load(open(f'{td}/manifest.json'))
        path = {e['name']: f'{td}/{e["file"]}' for e in man['entries']}
        for n in ('ASNEWS.DAT', 'TMNEWS.DAT'):
            s = strtable.decode(open(path[n], 'rb').read())
            sec = s['sections'][0]
            assert sec[FIRST - 1] == '' and sec[FIRST] == 'bruised cheekbone' and sec[FIRST + COUNT] == 'up to a week', n
            sec[FIRST:FIRST + COUNT] = [NAME] * COUNT
            open(path[n], 'wb').write(strtable.encode(s))
        volcodec.pack(td, f'{out}/SHELL.VOL')
    with open(f'{out}/PB.INI', 'w', newline='\r\n') as fh:
        fh.write('[PlayBalance]\n' + ''.join(f'{k}=1\n' for k in ODDS))
    steps = json.load(open(steps_file)) if steps_file else STEPS
    plan = {'install': {'SHELL.VOL': f'{out}/SHELL.VOL', 'PB.INI': f'{out}/PB.INI'}, 'launch_wait': 22,
            'steps': steps}
    json.dump(plan, open(f'{out}/plan.json', 'w'), indent=1)
    env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    sys.exit(subprocess.run([sys.executable, f'{HERE}/ingame.py', f'{out}/plan.json', f'{out}/shots'],
                            env=env).returncode)


SIM_DAY = [['click', 440, 329, 1.5], ['click', 445, 395, 3], ['click', 593, 330, 2], ['click', 616, 346, 3],
           ['click', 543, 486, 1], ['click', 571, 565, 8]]
STEPS = ([['click', 500, 677, 6], ['click', 643, 556, 5], ['click', 643, 566, 8]] + SIM_DAY +
         [s for i in range(4) for s in (['wait', 10], ['click', 645, 535, 2])] +
         [['shot', 'schedule'], ['key', 'ctrl+z', 5], ['move', 900, 900],
          ['ocr', 'news', None, {'expect': [NAME, 'is day-to-day'], 'absent': ['bruised', 'sprained', 'strained']}]])


if __name__ == '__main__':
    main()
