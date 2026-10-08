#!/usr/bin/env python3
"""#11 in-game test of a logic.dat (fielding assignments) edit, read off the 3D view.

usage: t_logic_edit.py OUTDIR [--stock]

--stock is the control: the shipped SIM.DAT with the same BBPRO.INI; it passes when the other backup jobs ARE read
(so the edit run's "none read" means something).

BBSIM draws each fielder's current logic.dat job and action above him ("%s %s (%d/3)", the COVER_1B name table,
FUN_6802d919, e.g. "BACKUP_HOME DO_LOGIC (0/3)", "RELAY CHASE_BALL")
when the [Debug] ShowPlayerLogic key of BBPRO.INI is 1 (read at startup into DAT_680c2cd4, FUN_6808d980). This test
builds
  SIM.DAT    (chunkdat + simchunks)  every backup job (BACKUP_1B, 2B, 3B, RF, CF, LF, BOTH) of every logic.dat row
                                     -> BACKUP_HOME; covers, cutoffs and relays are kept
  BBPRO.INI  the work copy's, plus [Debug] DebugEnabled=1 (BBSIM FUN_6808e793 reads the other [Debug] keys,
             FUN_6807bddf, only when it is set) and ShowPlayerLogic=1
then starts Arcade Play with Visitors control set to Computer (as t_shape_edit.py), so the sim plays itself, and OCRs
the 3D frames for the job names. Pass = BACKUP_HOME read in at least MIN_FRAMES frames and none of the replaced backup
jobs read anywhere.

Seen 2026-10-08: PASS, BACKUP_HOME in 8/20 frames, no other backup job; the --stock control read BACKUP_1B, CF, LF
and RF. The labels are small black text: OCR = crop of the 3D view, black colour key, x4, tesseract --psm 11. Setting every job of every row to BACKUP_HOME stops the game at the first ball in play with
"Cover.cpp:453" (FUN_68018f46 asserts that FUN_6802e950 finds a fielder for the base): a row needs its covers.
Every edited file and every state file the run writes is restored (ingame.py).
"""
import json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import chunkdat, simchunks

WORK = '/mnt/nvme/bbpro98/work_install'
JOB, BACKUPS, FRAMES, MIN_FRAMES = 7, (4, 5, 6, 8, 9, 10, 11), 20, 2
FIELD = [0, 224, 1280, 800]        # the 3D view below the scoreboard; the labels are small black text


def set_jobs(node, job):
    n = 0
    for k, v in node.items():
        if isinstance(v, dict):
            n += set_jobs(v, job)
        elif v in BACKUPS and not k.startswith('_'):
            node[k] = job; n += 1
    return n


def main():
    out = os.path.abspath(sys.argv[1])
    stock = '--stock' in sys.argv[2:]
    os.makedirs(out, exist_ok=True)
    chunks, meta = chunkdat.split(open(f'{WORK}/SIM.DAT', 'rb').read())
    hit = [i for i, c in enumerate(chunks) if c[0] == 0x6be6]
    assert len(hit) == 1, hit
    k, tag, data = chunks[hit[0]]
    doc = simchunks.decode('6be6_logic.dat', data)
    names = doc['_jobs']
    n = sum(set_jobs(doc[s], JOB) for s in ('infield', 'outfield', 'bunt', 'special', 'batting_practice'))
    assert n == 308 + 464 + 308 + 24 + 48 + 24 + 8, n            # the shipped backup jobs
    new = simchunks.encode('6be6_logic.dat', doc)
    assert simchunks.decode('6be6_logic.dat', new) == doc, 're-decode differs'
    chunks[hit[0]] = (k, tag, new)
    open(f'{out}/SIM.DAT', 'wb').write(chunkdat.join(chunks, meta))
    if stock:
        shutil.copyfile(f'{WORK}/SIM.DAT', f'{out}/SIM.DAT')
    ini = open(f'{WORK}/BBPRO.INI', 'rb').read()
    assert b'[Debug]' not in ini, 'work BBPRO.INI already has [Debug]'
    open(f'{out}/BBPRO.INI', 'wb').write(ini.rstrip(b'\r\n') + b'\r\n[Debug]\r\nDebugEnabled=1\r\nShowPlayerLogic=1\r\n')
    job = names[str(JOB)]
    others = [names[str(b)] for b in BACKUPS]
    print('control: shipped SIM.DAT' if stock else f'{n} jobs set to {job}')
    steps = [['click', 506, 526, 6], ['click', 582, 728, 8], ['click', 750, 692, 25],
             ['click', 560, 450, 2, 3], ['click', 630, 506, 4],      # right-click the 3D view, Game Options
             ['click', 48, 60, 3],                                     # Play Modes tab (lower tab row)
             ['click', 137, 127, 2], ['click', 120, 146, 2],          # Visitors Control -> Computer
             ['click', 233, 442, 3]]                                   # OK
    for i in range(FRAMES):
        steps += [['ocr', f'f{i:02d}', FIELD, {'key': 'black', 'psm': 11, 'scale': 400}], ['wait', 1.5]]
    plan = {'install': {'SIM.DAT': f'{out}/SIM.DAT', 'BBPRO.INI': f'{out}/BBPRO.INI'}, 'launch_wait': 22,
            'steps': steps}
    json.dump(plan, open(f'{out}/plan.json', 'w'), indent=1)
    env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    r = subprocess.run([sys.executable, f'{HERE}/ingame.py', f'{out}/plan.json', f'{out}/shots'],
                       env=env, capture_output=True, text=True)
    print(r.stdout, end='')
    norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
    seen, wrong = 0, set()
    for i in range(FRAMES):
        try:
            text = norm(open(f'{out}/shots/f{i:02d}.txt').read())
        except OSError:
            continue
        seen += norm(job) in text
        wrong |= {o for o in others if norm(o) in text}
    ok = r.returncode == 0 and (len(wrong) >= 2 if stock else seen >= MIN_FRAMES and not wrong)
    print(f'{job} read in {seen}/{FRAMES} frames (need {MIN_FRAMES}); other job names read: {sorted(wrong) or "none"}:',
          'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
