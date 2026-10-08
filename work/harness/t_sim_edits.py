#!/usr/bin/env python3
"""#11 in-game test of sim data edits through chunkdat.py + simchunks.py and a DLL resource edit through rsrc.py,
checked on screen.

usage: t_sim_edits.py OUTDIR

Builds copies of work-copy files with
  Stadia/NEWYORKA.DAT  info.dat (e957)  name -> "Claude Park", short_name "New York Stadium" -> "Claude Short"
  Stadia/NEWYORKA.DAT  the 9 PB stand panoramas (640x122 raw images, 38-byte header) filled with palette index 253
  Stadia/NEWYORKA.DT   info.dat (e957)  name -> "Claude Yard"
  FPS_Ctrl.dll         STRING 1205/1505 batting/fielding panel "Manager Menu" -> "Skipper Menu", plus a 3000-char
                                        filler string at the unused id 1215 so .rsrc outgrows its section and .reloc
                                        is moved (rsrc.replace_rsrc's growth path, loaded by the real loader)
then starts Arcade Play (Atlanta at New York (A), Yankee Stadium) on :99 and OCRs the Game Updates panel and the batting
menu, and counts magenta (index 253) pixels in the 3D view, where the stands are drawn. Every edited file and every
game state file the run writes is restored (ingame.py).

Seen 2026-10-07: the Game Updates "Stadium:" line is the .DAT short_name (not name, not the .DT name). A crowd_colors
edit (189/24 -> 253/254) changed nothing in the default batting view: the stands there are textured, the crowd
polygons (color 0xf4 / 0xf5, models 12-14 of shape.tbl) were not drawn with the flat crowd colours. The batting
panel's "Manager Menu" is FPS_Ctrl.dll's string resource, and the batting camera draws the PB panoramas (stands, outfield
wall, scoreboards; magenta fill = everything above the grass) over RC field textures: recolouring every shape.tbl
polygon of every model left that frame pixel-identical, so the models are only drawn by other cameras. A bpi.str edit
(SIM.DAT 5200) showed nothing in the batting panel.
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import chunkdat, rsrc, simchunks

WORK = '/mnt/nvme/bbpro98/work_install'


def edit(src, dst, cid, name, fn):
    chunks, meta = chunkdat.split(open(src, 'rb').read())
    hit = [i for i, c in enumerate(chunks) if c[0] == cid]
    if len(hit) != 1:
        sys.exit(f'{src}: {len(hit)} {name} chunks')
    k, tag, data = chunks[hit[0]]
    doc = simchunks.decode(f'{cid:04x}_{name}', data)
    fn(doc)
    chunks[hit[0]] = (k, tag, simchunks.encode(f'{cid:04x}_{name}', doc))
    open(dst, 'wb').write(chunkdat.join(chunks, meta))


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)

    def dat(d):
        assert d['short_name'] == 'New York Stadium', d['short_name']
        d['name'], d['short_name'] = 'Claude Park', 'Claude Short'

    def dt(d):
        assert d['name'] == 'New York Stadium', d['name']
        d['name'] = 'Claude Yard'

    edit(f'{WORK}/Stadia/NEWYORKA.DAT', f'{out}/NEWYORKA.DAT', 0xe957, 'info.dat', dat)
    chunks, meta = chunkdat.split(open(f'{out}/NEWYORKA.DAT', 'rb').read())
    pb = [i for i, c in enumerate(chunks) if c[1] == b'PB']
    for i in pb:
        k, tag, data = chunks[i]
        chunks[i] = (k, tag, data[:38] + bytes([253]) * (len(data) - 38))
    open(f'{out}/NEWYORKA.DAT', 'wb').write(chunkdat.join(chunks, meta))
    edit(f'{WORK}/Stadia/NEWYORKA.DT', f'{out}/NEWYORKA.DT', 0xe957, 'info.dat', dt)
    src = open(f'{WORK}/FPS_Ctrl.dll', 'rb').read()
    rd = f'{out}/fps_ctrl_rsrc'
    man = rsrc.unpack(src, rd)
    blk = [r for r in man['resources'] if r['type'] == 'STRING' and r['name'] == '#76']
    assert len(blk) == 1 and '1215' not in blk[0]['decoded']['strings'], 'block 76'
    blk[0]['decoded']['strings']['1215'] = 'filler ' * 428
    n = 0
    for r in man['resources']:
        if r['type'] == 'STRING':
            for i, v in r['decoded']['strings'].items():
                if v == 'Manager Menu':
                    r['decoded']['strings'][i] = 'Skipper Menu'; n += 1
    assert n == 2, n
    json.dump(man, open(f'{rd}/manifest.json', 'w'), ensure_ascii=False)
    dll = rsrc.pack(rd, src)
    assert rsrc.PE(dll).secs[-1]['rptr'] > rsrc.PE(src).secs[-1]['rptr'], '.reloc did not move'
    open(f'{out}/FPS_Ctrl.dll', 'wb').write(dll)
    plan = {'install': {'Stadia/NEWYORKA.DAT': f'{out}/NEWYORKA.DAT', 'Stadia/NEWYORKA.DT': f'{out}/NEWYORKA.DT',
                        'FPS_Ctrl.dll': f'{out}/FPS_Ctrl.dll'},
            'launch_wait': 22,
            'steps': [['click', 506, 526, 6], ['click', 582, 728, 8], ['click', 750, 692, 25],
                      ['ocr', 'updates', [0, 260, 260, 420], {'expect': ['Claude Short'],
                                                              'absent': ['New York Stadium']}],
                      ['ocr', 'bat_menu', [820, 20, 300, 200], {'expect': ['Skipper Menu'], 'absent': ['Manager'],
                                                                'key': 'yellow'}],
                      ['pixels', 'stands', [243, 207, 650, 443], {'rgb': [255, 0, 255], 'tol': 40, 'min': 50000}]]}
    json.dump(plan, open(f'{out}/plan.json', 'w'), indent=1)
    env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent')
    sys.exit(subprocess.run([sys.executable, f'{HERE}/ingame.py', f'{out}/plan.json', f'{out}/shots'],
                            env=env).returncode)


if __name__ == '__main__':
    main()
