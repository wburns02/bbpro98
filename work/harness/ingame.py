#!/usr/bin/env python3
"""In-game check of an edit: install files into the WORK copy, launch the game on the :99 display, drive it with
clicks and keys, OCR screenshots for expected / absent text, then restore the originals (sha256 verified) and stop
the game. Never touches the live install.

usage: ingame.py PLAN.json SHOTDIR

PLAN: {"install": {"SHELL.VOL": "/path/to/edited/SHELL.VOL", ...},   keys are paths inside the work copy
       "launch_wait": 20, "exe": "BBArch.exe" (optional: start this program of the work copy instead of bblaunch.exe),
       "steps": [["click", x, y, wait, button (1 left default, 3 right)], ["key", "ctrl+w", wait], ["move", x, y], ["wait", s], ["shot", name],
                 ["ocr", name, [x, y, w, h] | null, {"expect": [..], "absent": [..], "key": "yellow"}],
                 ["pixels", name, [x, y, w, h], {"rgb": [r, g, b], "tol": 30, "min": n, "max": m}],
                 ["copy", "Assn/X.ASN", name]],                    copy = save a work-copy file as SHOTDIR/name now
       "keep": false}                                             keep = leave the edit installed and the game up
Game state the run writes (game.sav / game.in of an unfinished game, ezshell.cfg, BBPRO.INI, league and stats files) is
put back too: every file of the work copy is listed before the launch, the small state files (top-level files under
4 MB and the Assn, Archive, Stats, StatSets, tapes, hilights dirs) are copied aside, and afterwards changed state files
are restored and files the run created are deleted. A change to any other file is reported and fails the run.
Screen coordinates are the 1280x1024 :99 root window. "ocr" takes its own screenshot. Text match is case-insensitive
and ignores runs of whitespace. "key" adds a pass that keeps only pixels of that colour (KEYS), for coloured text on a
busy background (the 3D game's yellow-on-gray panels; black for the debug labels over the field); "psm" (tesseract page
mode, default 6; 11 = sparse text) and "scale" (percent, default 300) tune the pass. "pixels" counts the pixels of the region within tol (max
channel difference) of rgb and checks min <= count <= max (either bound optional), for edits that are not text. Exit 0 = every ocr step passed.
"""
import hashlib, json, os, re, shutil, signal, subprocess, sys, time

WORK = '/mnt/nvme/bbpro98/work_install'
LIVE = os.path.realpath(os.path.expanduser('~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98'))
LAUNCH = os.path.expanduser('~/bb_launch_work.sh')
GAME = re.compile(r'C:.Sierra.BBPRO_98_work.(bblaunch|Baseball|BBArch)\.exe|winedbg')
EXES = ('BBArch.exe',)       # other programs a plan may start ("exe")
ENV = dict(os.environ, DISPLAY=':99')


def sha(p):
    with open(p, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def game_pids():
    out = subprocess.run(['pgrep', '-af', 'BBPRO_98_work|winedbg'], capture_output=True, text=True).stdout
    mine = ancestors()
    return [int(l.split()[0]) for l in out.splitlines() if GAME.search(l) and int(l.split()[0]) not in mine]


def ancestors():
    """This process and its parents: a shell whose command line mentions the game is not the game."""
    out, pid = set(), os.getpid()
    while pid > 1 and pid not in out:
        out.add(pid)
        try:
            with open(f'/proc/{pid}/stat') as fh:
                pid = int(fh.read().rsplit(')', 1)[1].split()[1])
        except OSError:
            break
    return out


def stop_game():
    for p in game_pids():
        try:
            os.kill(p, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(20):
        if not game_pids():
            return
        time.sleep(0.5)
    for p in game_pids():
        os.kill(p, signal.SIGKILL)


STATE_DIRS = ('Assn', 'Archive', 'Stats', 'StatSets', 'tapes', 'hilights')


def listing():
    out = {}
    for root, dirs, files in os.walk(WORK):
        for f in files:
            p = os.path.join(root, f)
            st = os.lstat(p)
            out[os.path.relpath(p, WORK)] = (st.st_size, st.st_mtime_ns)
    return out


def is_state(rel, size):
    top = rel.split(os.sep)[0]
    return (os.sep not in rel and size < 4 << 20) or top in STATE_DIRS


def save_state(dst):
    before = listing()
    for rel, (size, _) in before.items():
        if is_state(rel, size):
            os.makedirs(os.path.dirname(f'{dst}/{rel}'), exist_ok=True)
            shutil.copy2(os.path.join(WORK, rel), f'{dst}/{rel}')
    return before


def restore_state(src, before, installed):
    """Put the work copy back as save_state found it; installed paths are restored by the caller. True = clean."""
    clean = True
    after = listing()
    for rel in sorted(set(after) - set(before)):
        os.remove(os.path.join(WORK, rel))
        print('removed new file', rel)
    for rel, meta in sorted(before.items()):
        if rel in installed or after.get(rel) == meta:
            continue
        if is_state(rel, meta[0]):
            shutil.copy2(f'{src}/{rel}', os.path.join(WORK, rel))
            print('restored state file', rel)
        else:
            print('CHANGED (not restorable):', rel); clean = False
    return clean


def x(*args):
    subprocess.run(['xdotool', *map(str, args)], env=ENV, check=True)


def click(px, py, button=1):
    x('mousemove', px, py); time.sleep(0.2); x('mousemove', px + 2, py + 1); time.sleep(0.3)
    x('mousedown', button); time.sleep(0.15); x('mouseup', button)


def shot(path):
    subprocess.run(['import', '-window', 'root', path], env=ENV, check=True)


KEYS = {'yellow': '(r>0.6&&g>0.6&&b<0.4)?0:1', 'white': '(r>0.85&&g>0.85&&b>0.85)?0:1',
        'black': '(r<0.12&&g<0.12&&b<0.12)?0:1'}


def ocr(png, box, scratch, key=None, psm=6, scale=300):
    """Text of the region, tesseract on grayscale x3, normal and negated (the shell draws light-on-dark too), and with
    key, on the pixels of that colour only (black on white)."""
    texts = []
    for mode in ('p', 'n') + ((key,) if key else ()):
        pre = f'{scratch}/ocr_{mode}.png'
        cmd = ['magick', png]
        if box:
            cmd += ['-crop', '%dx%d+%d+%d' % (box[2], box[3], box[0], box[1]), '+repage']
        if mode in KEYS:
            cmd += ['-fx', KEYS[mode], '-resize', f'{scale}%', pre]
        else:
            cmd += ['-colorspace', 'Gray', '-resize', f'{scale}%'] + (['-negate'] if mode == 'n' else []) + [pre]
        subprocess.run(cmd, check=True)
        texts.append(subprocess.run(['tesseract', pre, '-', '--psm', str(psm)], capture_output=True, text=True).stdout)
    return '\n'.join(texts)


def count_pixels(png, box, rgb, tol):
    """Pixels of box [x, y, w, h] in png within tol of rgb in every channel (raw RGB via ImageMagick)."""
    raw = subprocess.run(['magick', png, '-crop', '%dx%d+%d+%d' % (box[2], box[3], box[0], box[1]), '+repage',
                          '-depth', '8', 'rgb:-'], capture_output=True, check=True).stdout
    return sum(1 for i in range(0, len(raw) - 2, 3)
               if all(abs(raw[i + k] - rgb[k]) <= tol for k in range(3)))


def norm(s):
    return re.sub(r'\s+', ' ', s).strip().lower()


def main():
    plan = json.load(open(sys.argv[1]))
    shots = os.path.abspath(sys.argv[2])
    os.makedirs(shots, exist_ok=True)
    if os.path.realpath(WORK) == LIVE:
        sys.exit('REFUSED: the work copy resolves to the live install')
    backup = f'{shots}/_orig'
    os.makedirs(backup, exist_ok=True)
    saved = {}
    for rel, src in plan.get('install', {}).items():
        dst = os.path.realpath(os.path.join(WORK, rel))
        if not dst.startswith(os.path.realpath(WORK) + os.sep) or dst.startswith(LIVE + os.sep):
            sys.exit(f'REFUSED: {rel} is outside the work copy')
        bk = f'{backup}/{rel.replace("/", "__")}'
        if os.path.exists(dst):
            shutil.copy2(dst, bk)
            saved[dst] = (bk, sha(dst))
        else:
            saved[dst] = (None, None)
    stop_game()
    before = None if plan.get('keep') else save_state(f'{shots}/_state')
    ok = True
    try:
        for dst, src in ((os.path.realpath(os.path.join(WORK, r)), s) for r, s in plan.get('install', {}).items()):
            shutil.copyfile(src, dst)
        exe = plan.get('exe')
        if exe is None:
            cmd = ['setsid', 'bash', LAUNCH]
        elif exe in EXES:                                  # same environment as the launch script
            cmd = ['setsid', 'bash', '-c', 'export WINEPREFIX=$HOME/.bbpro98_prefix WINEDEBUG=-all DISPLAY=:99 '
                   'PULSE_SINK=bbnull; cd "$WINEPREFIX/drive_c/Sierra/BBPRO_98_work" && exec wine "$1"', 'bb', exe]
        else:
            sys.exit(f'REFUSED: exe {exe!r} is not one of {EXES}')
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(plan.get('launch_wait', 20))
        for st in plan['steps']:
            op = st[0]
            if op == 'click':
                click(st[1], st[2], st[4] if len(st) > 4 else 1); time.sleep(st[3] if len(st) > 3 else 1)
            elif op == 'key':
                x('key', st[1]); time.sleep(st[2] if len(st) > 2 else 1)
            elif op == 'move':
                x('mousemove', st[1], st[2]); time.sleep(0.3)
            elif op == 'wait':
                time.sleep(st[1])
            elif op == 'shot':
                shot(f'{shots}/{st[1]}.png')
            elif op == 'pixels':
                png = f'{shots}/{st[1]}.png'
                shot(png)
                want = st[3]
                n = count_pixels(png, st[2], want['rgb'], want.get('tol', 30))
                good = want.get('min', 0) <= n <= want.get('max', n)
                ok &= good
                print(json.dumps({'pixels': st[1], 'ok': good, 'count': n}))
            elif op == 'ocr':
                png = f'{shots}/{st[1]}.png'
                shot(png)
                want = st[3] if len(st) > 3 else {}
                text = norm(ocr(png, st[2], shots, want.get('key'), want.get('psm', 6), want.get('scale', 300)))
                miss = [t for t in want.get('expect', []) if norm(t) not in text]
                bad = [t for t in want.get('absent', []) if norm(t) in text]
                good = not miss and not bad
                ok &= good
                print(json.dumps({'ocr': st[1], 'ok': good, 'missing': miss, 'present': bad}))
                with open(f'{shots}/{st[1]}.txt', 'w') as fh:
                    fh.write(text)
            elif op == 'copy':
                src = os.path.realpath(os.path.join(WORK, st[1]))
                if not src.startswith(os.path.realpath(WORK) + os.sep) or os.sep in st[2]:
                    sys.exit(f'REFUSED: copy {st[1]!r} -> {st[2]!r}')
                found = os.path.exists(src)
                if found:
                    shutil.copy2(src, f'{shots}/{st[2]}')
                print(json.dumps({'copy': st[1], 'found': found}))
            else:
                sys.exit(f'unknown step {op}')
    finally:
        if not plan.get('keep'):
            stop_game()
            for dst, (bk, h) in saved.items():
                if bk is None:
                    os.remove(dst)
                else:
                    shutil.copyfile(bk, dst)
                    if sha(dst) != h:
                        print(f'RESTORE FAILED: {dst}'); ok = False
            print('restored', len(saved), 'file(s)')
            ok &= restore_state(f'{shots}/_state', before,
                                {os.path.relpath(d, os.path.realpath(WORK)) for d in saved})
    print('PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
