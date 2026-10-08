#!/usr/bin/env python3
"""#11 in-game test of an edited league archive (Archive/*.ARC) restored by the game's own archive utility.

usage: t_arc_restore.py OUTDIR

Builds Archive/MLBPA97.ARC with arccodec.py + league.py: the archived MLBPA97.ASN's trophy "The Dynamix Cup" ->
"The Claude Cup", re-imploded by arccodec (the other two entries keep their shipped streams). Then two runs:
  1. BBArch.exe (ingame.py "exe", started from its own drive K:, see ingame.py): select "1997 MLBPA Opening Day"
     under Archived Associations, Restore..., pick the Assn directory, answer Yes to the overwrite / create
     prompts. The restored files are copied out before ingame.py puts the work copy back. Pass = Assn/MLBPA97.ASN,
     Assn/MLBPA97.PYR and Stats/MLBPA97.DAT byte-equal to the edited archive's entries (so FPS_DCL.dll exploded
     arccodec's implode stream) and the ASN's trophy is The Claude Cup.
  2. The game with those three files installed: League > Association Data shows "The Claude Cup".

BBArch, seen 2026-10-08: the restore picker is a Save dialog (typing the directory name + Return picks it); the ASN
and PYR go to the chosen directory, the DAT to \\STATS of the same drive, overwritten without asking.
"That association already exists in K:\\ASSN, would you like to overwrite it?" (Yes at 543,542; the second Yes click
answers "The directory K:\\STATS does not exist, would you like to create it?" when there is no Stats, else lands on
nothing). Starting BBArch rewrites Assn/MLBPA96E.ASN (restored by ingame.py). PASS 2026-10-08: all three restored files
byte-equal to the edited archive's entries (FPS_DCL.dll explodes arccodec's implode stream), trophy shown in the
shell.
"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import arccodec

WORK = '/mnt/nvme/bbpro98/work_install'
TROPHY = 'The Claude Cup'
YES = ['click', 543, 542, 6]
OUT_FILES = {'ASN': 'Assn/MLBPA97.ASN', 'PYR': 'Assn/MLBPA97.PYR', 'DAT': 'Stats/mlbpa97.DAT'}


def run(plan, out, name):
    json.dump(plan, open(f'{out}/{name}.json', 'w'), indent=1)
    env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    r = subprocess.run([sys.executable, f'{HERE}/ingame.py', f'{out}/{name}.json', f'{out}/{name}'],
                       env=env, capture_output=True, text=True)
    print(r.stdout, end='')
    return r.returncode == 0


def trophy(asn, out):
    subprocess.run([sys.executable, f'{os.path.dirname(HERE)}/league.py', 'decode', asn, f'{out}/t.json'], check=True)
    return json.load(open(f'{out}/t.json'))['association'][0]['trophy']


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    ent = f'{out}/entries'
    arccodec.unpack(f'{WORK}/Archive/MLBPA97.ARC', ent)
    asn = f'{ent}/MLBPA97.ASN'
    with tempfile.TemporaryDirectory(dir=out) as td:
        subprocess.run([sys.executable, f'{os.path.dirname(HERE)}/league.py', 'decode', asn, f'{td}/a.json'],
                       check=True)
        a = json.load(open(f'{td}/a.json'))
        assert a['association'][0]['trophy'] == 'The Dynamix Cup', a['association'][0]
        a['association'][0]['trophy'] = TROPHY
        json.dump(a, open(f'{td}/a.json', 'w'))
        subprocess.run([sys.executable, f'{os.path.dirname(HERE)}/league.py', 'encode', asn, f'{td}/a.json',
                        f'{td}/MLBPA97.ASN'], check=True)
        os.replace(f'{td}/MLBPA97.ASN', asn)
    arccodec.pack(ent, f'{out}/MLBPA97.ARC')
    want = {k: open(f'{ent}/MLBPA97.{k}', 'rb').read() for k in OUT_FILES}

    steps = [['move', 240, 180], ['wait', 2],
             ['ocr', 'lists', [10, 60, 380, 230], {'expect': ['1997 MLBPA Opening Day', 'Archive']}],
             ['click', 90, 223, 1.5],                                   # Archived: 1997 MLBPA Opening Day
             ['click', 435, 213, 4],                                    # Restore...
             ['key', 'ctrl+a', 0.5], ['key', 'BackSpace', 0.3]]
    steps += [['key', c, 0.2] for c in ('A', 's', 's', 'n')]
    steps += [['key', 'Return', 6], ['shot', 'prompt1'], YES,                     # "Assn" + Return picks it
              ['shot', 'prompt2'], YES, ['wait', 8], ['shot', 'done'],
              ['ocr', 'final', [0, 20, 490, 330], {'absent': ['Expanding']}]]
    steps += [['copy', v, k] for k, v in OUT_FILES.items()]
    ok1 = run({'install': {'Archive/MLBPA97.ARC': f'{out}/MLBPA97.ARC'}, 'exe': 'BBArch.exe', 'launch_wait': 12,
               'steps': steps}, out, 'restore')
    got = {}
    for k in OUT_FILES:
        try:
            got[k] = open(f'{out}/restore/{k}', 'rb').read()
        except OSError:
            got[k] = None
    same = {k: got[k] == want[k] for k in OUT_FILES}
    t = trophy(f'{out}/restore/ASN', out) if got['ASN'] else None
    print(f'restore run: {"ok" if ok1 else "FAIL"}; restored == archive entries: {same}; trophy {t!r}')
    if not (ok1 and all(same.values()) and t == TROPHY):
        print('FAIL'); sys.exit(1)

    ok2 = run({'install': {v: f'{out}/restore/{k}' for k, v in OUT_FILES.items()}, 'launch_wait': 22,
               'steps': [['click', 500, 677, 6], ['click', 643, 556, 5], ['click', 643, 566, 8], ['move', 900, 900],
                         ['ocr', 'assn_data', None, {'expect': [TROPHY], 'absent': ['Dynamix']}]]}, out, 'shell')
    print('shell run:', 'ok' if ok2 else 'FAIL')
    print('PASS' if ok2 else 'FAIL')
    sys.exit(0 if ok2 else 1)


if __name__ == '__main__':
    main()
