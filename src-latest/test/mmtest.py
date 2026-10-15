#!/usr/bin/env python3
"""Unit test of the Mods menu's spool protocol (src-latest/mods/modmenu.c), under Wine. Builds mmtest.exe (which
includes modmenu.c) and runs it against a fake bridge thread in this process: the request bytes, the response parsing,
TAB values, timeouts, a missing spool folder and mm_clean, the bridge heartbeat (alive.txt) and mm_open_page's
immediate return without one. Checks 7 and 12 run the real news/modbridge.py when it imports.
usage: python3 mmtest.py OUTDIR   (needs the zig env at /mnt/nvme/bbpro98/zigenv and wine; prints SKIP and exits 0
when either is missing)"""
import os
import shutil
import subprocess
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ZIG = ['/mnt/nvme/bbpro98/zigenv/bin/python', '-m', 'ziglang', 'cc', '-target', 'x86-windows-gnu', '-O2', '-Isrc-latest']
ENV = dict(os.environ, WINEPREFIX='/mnt/nvme/bbpro98/hktest_prefix', WINEDEBUG='-all',
           WINEDLLOVERRIDES='mscoree,mshtml=;winedbg.exe=d', DBUS_SYSTEM_BUS_ADDRESS='unix:path=/nonexistent', DISPLAY='')


def wpath(p):
    """Z: path of a unix path, with the trailing backslash a spool folder needs."""
    return 'Z:' + p.replace('/', '\\')


class Bridge(threading.Thread):
    """Fake bridge: takes the first q*.req in the spool and answers it with reply (None: no bridge at all)."""

    def __init__(self, spool, reply):
        super().__init__(daemon=True)
        self.spool, self.reply = spool, reply
        self.req = None

    def run(self):
        if self.reply is None:
            return
        deadline = time.time() + 60
        while time.time() < deadline:
            names = [n for n in os.listdir(self.spool) if n.startswith('q') and n.endswith('.req')]
            if names:
                rid = names[0][1:-4]
                with open(os.path.join(self.spool, names[0]), 'rb') as f:
                    self.req = f.read()
                tmp = os.path.join(self.spool, 'r%s.tmp' % rid)
                with open(tmp, 'wb') as f:
                    f.write(self.reply)
                os.replace(tmp, os.path.join(self.spool, 'r%s.rsp' % rid))
                return
            time.sleep(0.01)


def parse(stdout):
    """(id, [(key, value)], body or None, last status line) from mmtest.exe's output (bytes in, latin-1 text out)."""
    head, sep, body = stdout.partition(b'BODY\n')
    rid, hdr, status = None, [], None
    for ln in head.decode('latin-1').split('\n'):
        if ln.startswith('ID '):
            rid = ln[3:]
        elif ln.startswith('H '):
            k, _, v = ln[2:].partition('=')
            hdr.append((k, v))
        elif ln:
            status = ln
    return rid, hdr, (body.decode('latin-1') if sep else None), status


def main():
    if len(sys.argv) != 2:
        print('usage: python3 mmtest.py OUTDIR')
        return 2
    if not os.path.exists(ZIG[0]) or shutil.which('wine') is None:
        print('SKIP: zig env or wine missing')
        return 0
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    build_env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=os.path.join(out, 'zigcache'),
                     ZIG_LOCAL_CACHE_DIR=os.path.join(out, 'zigcache'))
    exe = os.path.join(out, 'mmtest.exe')
    try:
        subprocess.run(ZIG + ['-o', exe, 'src-latest/test/mmtest.c', '-lgdi32', '-luser32'], cwd=ROOT, env=build_env,
                       check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print('FAIL build: %s' % e)
        return 1

    def run(args, extra=None, timeout=60):
        env = dict(ENV, **extra) if extra else ENV
        try:
            return subprocess.run(['wine', 'mmtest.exe'] + args, cwd=out, env=env, capture_output=True, timeout=timeout)
        finally:
            subprocess.run(['wineserver', '-k'], env=ENV)

    def fresh(name):
        d = os.path.join(out, 'spool-' + name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        return d + os.sep

    def exchange(spool, op, kv, reply, extra=None):
        br = Bridge(spool, reply)
        br.start()
        r = run(['send', wpath(spool), op] + kv, extra)
        br.join(30)
        return r, br

    def leftover(spool, prefix, suffix):
        return [n for n in os.listdir(spool) if n.startswith(prefix) and n.endswith(suffix)]

    results = []

    def check(n, name, ok, detail=''):
        results.append(ok)
        print('%s %d %s%s' % ('PASS' if ok else 'FAIL', n, name, '' if ok else ': ' + detail))

    # 1. ping round trip: request bytes, parsed headers, body with CR LF kept, response deleted
    sp = fresh('ping')
    r, br = exchange(sp, 'ping', [], b'status=ok\r\nversion=1\r\n\r\nhello\r\nworld')
    rid, hdr, body, st = parse(r.stdout)
    check(1, 'ping round trip',
          r.returncode == 0 and ('status', 'ok') in hdr and ('version', '1') in hdr and body == 'hello\r\nworld'
          and br.req == b'op=ping\r\n' and not leftover(sp, 'r', '.rsp'),
          'rc %d hdr %r body %r req %r out %r' % (r.returncode, hdr, body, br.req, r.stdout[:200]))

    # 2. request fields
    sp = fresh('create')
    r, br = exchange(sp, 'create', ['first', 'Pat', 'last', 'Doe'], b'status=ok\r\npid=7\r\n\r\nmade')
    check(2, 'create fields', r.returncode == 0 and br.req == b'op=create\r\nfirst=Pat\r\nlast=Doe\r\n',
          'rc %d req %r' % (r.returncode, br.req))

    # 3. TAB inside a header value
    sp = fresh('tab')
    r, br = exchange(sp, 'news', ['path', '/news/'], b'status=ok\r\nlink.0=Home\t/news/\r\n\r\n')
    _, hdr, _, _ = parse(r.stdout)
    check(3, 'TAB in header value', r.returncode == 0 and ('link.0', 'Home\t/news/') in hdr, 'hdr %r' % hdr)

    # 4. timeout with no bridge: exit 2 within 25 s, no request left behind
    sp = fresh('timeout')
    t0 = time.time()
    r, _ = exchange(sp, 'ping', [], None, {'MMTEST_TIMEOUT_MS': '2000'})
    el = time.time() - t0
    check(4, 'timeout', r.returncode == 2 and el < 25 and not leftover(sp, 'q', '.req'),
          'rc %d after %.1f s, left %r' % (r.returncode, el, leftover(sp, 'q', '.req')))

    # 5. no spool folder: exit 3
    missing = os.path.join(out, 'no-such-spool') + os.sep
    r = run(['send', wpath(missing), 'ping'])
    check(5, 'no spool folder', r.returncode == 3 and b'SEND' in r.stdout,
          'rc %d out %r' % (r.returncode, r.stdout[:100]))

    # 6. clean drops control characters
    r = run(['clean', 'a\tb\nc'])
    check(6, 'clean drops control characters', r.stdout == b'[abc]\n', 'out %r' % r.stdout)

    # 8 (run first, numbered last): make_win shows its window
    r = run(['visible'])
    check(8, 'window shown', r.stdout == b'VISIBLE 1\n', 'out %r err %r' % (r.stdout, r.stderr[-200:]))

    # 9-11. the bridge's heartbeat: alive.txt missing, fresh or a minute old
    def alive(spool):
        r = run(['alive', wpath(spool)])
        return r.stdout.decode('latin-1').strip(), r

    def beat_file(spool, age=0):
        path = os.path.join(spool, 'alive.txt')
        with open(path, 'w') as f:
            f.write('%d\n' % (time.time() - age))
        os.utime(path, (time.time() - age,) * 2)

    sp = fresh('alive-none')
    got, r = alive(sp)
    check(9, 'no alive.txt', got == 'ALIVE 0', 'out %r err %r' % (r.stdout[:100], r.stderr[-200:]))
    sp = fresh('alive-fresh')
    beat_file(sp)
    got, r = alive(sp)
    check(10, 'fresh alive.txt', got == 'ALIVE 1', 'out %r err %r' % (r.stdout[:100], r.stderr[-200:]))
    sp = fresh('alive-old')
    beat_file(sp, 60)
    got, r = alive(sp)
    check(11, 'alive.txt 60 s old', got == 'ALIVE 0', 'out %r err %r' % (r.stdout[:100], r.stderr[-200:]))

    # 13. mm_open_page with no bridge running: returns 1 at once, no request in the spool, no window
    t0 = time.time()
    outs = []
    for name, age in (('open-none', None), ('open-old', 60)):
        sp = fresh(name)
        if age:
            beat_file(sp, age)
        r = run(['open', wpath(sp), '/news/card/TEST77/p/1'], timeout=20)
        outs.append((r.stdout.decode('latin-1').strip(), leftover(sp, 'q', '')))
    check(13, 'open_page with no bridge', outs == [('OPEN 1', [])] * 2 and time.time() - t0 < 20, 'out %r' % outs)

    # 14-15. load_hots: a huge hots count is clamped (no 2e9-step loop on the UI thread); x + w that wraps is refused
    t0 = time.time()
    try:
        got = run(['hots', 'status=ok|hots=2000000000|hot.0=10,10,50,20\t/news/x'], timeout=30).stdout
    except subprocess.TimeoutExpired:
        got = b'timed out'
    check(14, 'huge hots count', got == b'HOTS 1\n' and time.time() - t0 < 30, 'out %r' % got[:100])
    r = run(['hots', 'status=ok|hots=2|hot.0=2147483640,0,100,10\t/news/a|hot.1=0,0,680,450\t/news/b'])
    check(15, 'wrapping hot rect', r.stdout == b'HOTS 1\n', 'out %r' % r.stdout[:100])

    # 7. the real bridge, when it imports
    sys.path.insert(0, os.path.join(ROOT, 'news'))
    try:
        import modbridge
    except ImportError:
        modbridge = None
    if modbridge is None:
        print('SKIP 7 real bridge: news/modbridge.py does not import')
        print('SKIP 12 real bridge beat: news/modbridge.py does not import')
    else:
        tree = os.path.join(out, 'tree')
        shutil.rmtree(tree, ignore_errors=True)
        os.makedirs(os.path.join(tree, 'Assn'))
        os.makedirs(os.path.join(tree, 'Stats'))
        ctx = types.SimpleNamespace(game=tree, data=tree, db=None, templates=None)
        sp = fresh('real')
        stop, err = threading.Event(), []

        def pump():
            while not stop.is_set():
                try:
                    modbridge.process_spool(ctx, os.path.abspath(sp))
                except Exception as e:  # reported as a FAIL below
                    err.append(repr(e))
                    return
                time.sleep(0.05)

        th = threading.Thread(target=pump, daemon=True)
        th.start()
        try:
            r = run(['send', wpath(sp), 'ping'])
        finally:
            stop.set()
            th.join(10)
        _, hdr, _, _ = parse(r.stdout)
        check(7, 'real bridge ping', r.returncode == 0 and ('status', 'ok') in hdr and ('version', '1') in hdr and not err,
              'rc %d hdr %r err %r out %r' % (r.returncode, hdr, err, r.stdout[:200]))

        # 12. the real beat() makes a fresh alive.txt
        sp = fresh('alive-real')
        modbridge.beat(os.path.abspath(sp))
        got, r = alive(sp)
        check(12, 'real bridge beat', got == 'ALIVE 1', 'out %r err %r' % (r.stdout[:100], r.stderr[-200:]))

    fails = results.count(False)
    print('%d checks, %d failures' % (len(results), fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
