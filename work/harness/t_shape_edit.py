#!/usr/bin/env python3
"""#11 in-game test of a shape.tbl (stadium 3D models) edit through chunkdat.py + simchunks.py, seen in the auto-play
cameras.

usage: t_shape_edit.py OUTDIR

Builds a copy of Stadia/NEWYORKA.DAT with every polygon of every shape.tbl model (947d) set to palette index 253
(magenta in the 3D palette, as in t_sim_edits.py): color and color2, except color2 of textured polygons (flag 0x10), starts Arcade Play (Atlanta at New York (A)), sets Visitors control
to Computer in Game Options > Play Modes so the sim plays itself, and screenshots the game every 2.5 s. The batting
camera draws the PB panoramas, not the models (t_sim_edits.py), so the models only show in the ball-in-play and
between-plays cameras. Pass = magenta pixels in at least MIN_FRAMES frames. A run of the same plan on the unedited
file (2026-10-08) had 0 magenta pixels in all 20 frames, so magenta can only come from the edit.

Seen 2026-10-08 (12 of 24 frames are 3D field views, the rest the batting camera): color2 is the fill. With color
alone set to 253, only outlines, foul lines, bases, the rubber and the flags turned magenta (about 5,000 px a frame);
with color2 too, the stands, walls, infield dirt and warning track filled (270,000-650,000 px). On textured polygons
(flag 0x10, color2 0) color is the texture frame: 253 drew the scoreboards black.
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import chunkdat, simchunks

WORK = '/mnt/nvme/bbpro98/work_install'
MAGENTA, FRAMES, MIN_FRAMES, MIN_PIXELS = 253, 24, 4, 100000


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    chunks, meta = chunkdat.split(open(f'{WORK}/Stadia/NEWYORKA.DAT', 'rb').read())
    hit = [i for i, c in enumerate(chunks) if c[0] == 0x947d]
    assert len(hit) == 1, hit
    k, tag, data = chunks[hit[0]]
    doc = simchunks.decode('947d_shape.tbl', data)
    n = 0
    for m in doc['models']:
        for lv in m['levels']:
            for p in lv['parts']:
                for v in p['variants']:
                    for po in v['polygons']:
                        po['color'] = MAGENTA; n += 1
                        if not po['flags'] & 0x10:
                            po['color2'] = MAGENTA
    new = simchunks.encode('947d_shape.tbl', doc)
    assert simchunks.decode('947d_shape.tbl', new) == doc, 're-decode differs'
    chunks[hit[0]] = (k, tag, new)
    open(f'{out}/NEWYORKA.DAT', 'wb').write(chunkdat.join(chunks, meta))
    print(f'{n} polygons in {len(doc["models"])} models recoloured')
    steps = [['click', 506, 526, 6], ['click', 582, 728, 8], ['click', 750, 692, 25],
             ['click', 560, 450, 2, 3], ['click', 630, 506, 4],      # right-click the 3D view, Game Options
             ['click', 48, 60, 3],                                     # Play Modes tab (lower tab row)
             ['click', 137, 127, 2], ['click', 120, 146, 2],          # Visitors Control -> Computer
             ['click', 233, 442, 3]]                                   # OK
    for i in range(FRAMES):
        steps += [['pixels', f'f{i:02d}', [0, 0, 1280, 1024], {'rgb': [255, 0, 255], 'tol': 40}], ['wait', 2.5]]
    plan = {'install': {'Stadia/NEWYORKA.DAT': f'{out}/NEWYORKA.DAT'}, 'launch_wait': 22, 'steps': steps}
    json.dump(plan, open(f'{out}/plan.json', 'w'), indent=1)
    env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    r = subprocess.run([sys.executable, f'{HERE}/ingame.py', f'{out}/plan.json', f'{out}/shots'],
                       env=env, capture_output=True, text=True)
    print(r.stdout, end='')
    counts = [json.loads(l)['count'] for l in r.stdout.splitlines() if l.startswith('{"pixels"')]
    seen = sum(c >= MIN_PIXELS for c in counts)
    ok = r.returncode == 0 and len(counts) == FRAMES and seen >= MIN_FRAMES
    print(f'magenta in {seen}/{len(counts)} frames (need {MIN_FRAMES} with >= {MIN_PIXELS} px):',
          'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
