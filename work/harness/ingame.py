#!/usr/bin/env python3
"""In-game check of an edit: install files into the WORK copy, launch the game on the :99 display, drive it with
clicks and keys, OCR screenshots for expected / absent text, then restore the originals (sha256 verified) and stop
the game. Never touches the live install.

usage: ingame.py PLAN.json SHOTDIR

PLAN: {"install": {"SHELL.VOL": "/path/to/edited/SHELL.VOL", ...},   keys are paths inside the work copy
       "launch_wait": 20,
       "steps": [["click", x, y, wait], ["key", "ctrl+w", wait], ["move", x, y], ["wait", s], ["shot", name],
                 ["ocr", name, [x, y, w, h] | null, {"expect": [..], "absent": [..]}]],
       "keep": false}                                             keep = leave the edit installed and the game up
Screen coordinates are the 1280x1024 :99 root window. "ocr" takes its own screenshot. Text match is case-insensitive
and ignores runs of whitespace. Exit 0 = every ocr step passed.
"""
import hashlib, json, os, re, shutil, signal, subprocess, sys, time

WORK = '/mnt/nvme/bbpro98/work_install'
LIVE = os.path.realpath(os.path.expanduser('~/.bbpro98_prefix/drive_c/Sierra/BBPRO_98'))
LAUNCH = os.path.expanduser('~/bb_launch_work.sh')
GAME = re.compile(r'C:.Sierra.BBPRO_98_work.(bblaunch|Baseball)\.exe|winedbg')
ENV = dict(os.environ, DISPLAY=':99')


def sha(p):
    with open(p, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def game_pids():
    out = subprocess.run(['pgrep', '-af', 'BBPRO_98_work|winedbg'], capture_output=True, text=True).stdout
    return [int(l.split()[0]) for l in out.splitlines() if GAME.search(l)]


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


def x(*args):
    subprocess.run(['xdotool', *map(str, args)], env=ENV, check=True)


def click(px, py):
    x('mousemove', px, py); time.sleep(0.2); x('mousemove', px + 2, py + 1); time.sleep(0.3)
    x('mousedown', 1); time.sleep(0.15); x('mouseup', 1)


def shot(path):
    subprocess.run(['import', '-window', 'root', path], env=ENV, check=True)


def ocr(png, box, scratch):
    """Text of the region, tesseract on grayscale x3, normal and negated (the shell draws light-on-dark too)."""
    texts = []
    for neg in (False, True):
        pre = f'{scratch}/ocr_{"n" if neg else "p"}.png'
        cmd = ['magick', png]
        if box:
            cmd += ['-crop', '%dx%d+%d+%d' % (box[2], box[3], box[0], box[1]), '+repage']
        cmd += ['-colorspace', 'Gray', '-resize', '300%'] + (['-negate'] if neg else []) + [pre]
        subprocess.run(cmd, check=True)
        texts.append(subprocess.run(['tesseract', pre, '-', '--psm', '6'], capture_output=True, text=True).stdout)
    return '\n'.join(texts)


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
    ok = True
    try:
        for dst, src in ((os.path.realpath(os.path.join(WORK, r)), s) for r, s in plan.get('install', {}).items()):
            shutil.copyfile(src, dst)
        subprocess.Popen(['setsid', 'bash', LAUNCH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(plan.get('launch_wait', 20))
        for st in plan['steps']:
            op = st[0]
            if op == 'click':
                click(st[1], st[2]); time.sleep(st[3] if len(st) > 3 else 1)
            elif op == 'key':
                x('key', st[1]); time.sleep(st[2] if len(st) > 2 else 1)
            elif op == 'move':
                x('mousemove', st[1], st[2]); time.sleep(0.3)
            elif op == 'wait':
                time.sleep(st[1])
            elif op == 'shot':
                shot(f'{shots}/{st[1]}.png')
            elif op == 'ocr':
                png = f'{shots}/{st[1]}.png'
                shot(png)
                text = norm(ocr(png, st[2], shots))
                want = st[3] if len(st) > 3 else {}
                miss = [t for t in want.get('expect', []) if norm(t) not in text]
                bad = [t for t in want.get('absent', []) if norm(t) in text]
                good = not miss and not bad
                ok &= good
                print(json.dumps({'ocr': st[1], 'ok': good, 'missing': miss, 'present': bad}))
                with open(f'{shots}/{st[1]}.txt', 'w') as fh:
                    fh.write(text)
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
    print('PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
