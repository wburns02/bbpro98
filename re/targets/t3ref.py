"""Referee for the 2026-10-08 bake-off tier 3: an exact replay model of FastSim FUN_6804faa1 (the runner AI update,
simtrace target runner_ai) scored against the st8 trace. Claude-owned: lanes must not edit it.

usage: python3 t3ref.py <target_dir> <lane_dir> [-v]        score <lane>/runner_ai.py on the dev records
       python3 t3ref.py <target_dir> <lane_dir> --holdout   the other half of the trace (the lane cannot read it)
       python3 t3ref.py <target_dir> <lane_dir> --audit X   summary for the audit

Contract for <lane>/runner_ai.py (stdlib + t3lib only, under 200 KB; runs in a bwrap jail, no network, no files):
  def replay(o, r): re-execute FUN_6804faa1 for one call. r = t3lib.inputs(record) (this pointer, the 0x100 bytes of
  *this before the call, the game state and manager flag bytes, ...; never the after-call ret / post / RNG states); o = the oracle: o.x(va, arg1=None) returns the
  next probed getter's recorded value (o.x2 the pair (value, idx)), o.align(a, b, c) checks an alignment-slot write
  (simtrace event L), o.pb(i) a PlayBalance read, o.other(t, gen, a) any other event. A call the
  function would not make, or a different getter / argument, raises t3lib.Mismatch and fails the record. The record
  passes when replay returns having consumed every top-level event.
Isolation: the records and the oracle live in this (host) process. The jail runs t3run.py, which imports runner_ai and
forwards each oracle call over a pipe, so the graded code never sees recorded events (dev or holdout) and never
writes the result.
Score: records ok out of all, and the deep subset (records past the two early exits). PASS = every dev record ok.
targets: files.json {"dev": records.jsonl, "holdout": records.jsonl, "module": lane file stem (default runner_ai),
         "ret_bits": 0 | 8 | 16 | 32 (when set, replay must also return the function's result: the low bits of eax),
         "post_u32": [byte offsets] (instead of ret_bits: replay returns a list of the u32 values the call leaves at
         those offsets of the record's 0x20-byte post snapshot, for void functions whose effect is a memory write)}
Other simtrace targets reuse this referee unchanged: <module>.replay(o, r) with the same oracle (re/bakeoff/t3_extract.py
NAME writes their records).
"""
import collections, json, os, selectors, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
import t3lib
from jailutil import RefError, fail

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT, LINE_MAX, BUF_MAX = 900, 1 << 20, 1 << 24


class Lane:
    """the jailed shim (t3run.py) as a line-JSON peer, under one overall deadline"""
    def __init__(self, cmd, env, cwd):
        self.err = tempfile.TemporaryFile()
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, env=env, cwd=cwd)
        self.rfd, self.wfd = self.p.stdout.fileno(), self.p.stdin.fileno()
        os.set_blocking(self.wfd, False)
        self.rsel = selectors.DefaultSelector(); self.rsel.register(self.rfd, selectors.EVENT_READ)
        self.rwsel = selectors.DefaultSelector(); self.rwsel.register(self.rfd, selectors.EVENT_READ)
        self.rwsel.register(self.wfd, selectors.EVENT_WRITE)
        self.buf, self.deadline = b'', time.monotonic() + TIMEOUT

    def _wait(self, sel):
        left = self.deadline - time.monotonic()
        if left <= 0: fail(f'timeout {TIMEOUT}s')
        return [(k.fd, ev) for k, ev in sel.select(left)]

    def _read(self):
        chunk = os.read(self.rfd, 65536)
        if not chunk: fail('lane process exited' + ('' if J.QUIET else f': {self.stderr_tail()}'))
        self.buf += chunk
        if len(self.buf) > BUF_MAX: fail('protocol: lane flooded its output')

    def send(self, msg):
        """never blocks on a full pipe while the lane blocks on its own: whatever the lane writes meanwhile is
        buffered (a desynced or flooding lane then fails on the deadline or BUF_MAX, never hangs the referee)"""
        data = json.dumps(msg).encode() + b'\n'
        while data:
            for fd, _ in self._wait(self.rwsel):
                if fd == self.rfd: self._read()
                else:
                    try: data = data[os.write(self.wfd, data[:65536]):]
                    except BlockingIOError: pass

    def recv(self):
        while b'\n' not in self.buf:
            if len(self.buf) > LINE_MAX: fail('protocol line too long')
            if self._wait(self.rsel): self._read()
        line, self.buf = self.buf.split(b'\n', 1)
        if len(line) > LINE_MAX: fail('protocol line too long')
        try:
            m = json.loads(line)
        except ValueError:
            fail('protocol: not JSON')
        if not isinstance(m, dict): fail('protocol: not an object')
        return m

    def stderr_tail(self):
        self.err.seek(0, 2); n = self.err.tell(); self.err.seek(max(0, n - 400))
        return self.err.read().decode('utf-8', 'replace').strip()

    def close(self):
        if self.p.poll() is None: self.p.kill()
        self.p.wait(); self.err.close()


def _int(v, none=False):
    if none and v is None: return v
    if type(v) is not int or abs(v) >= 1 << 64: fail('protocol: bad argument')
    return v


def score(lane, recs, ret_bits=0, post_u32=()):
    """one record at a time: send its inputs, answer the shim's oracle calls from the host-side oracle, then judge"""
    res = {'n': len(recs), 'ok': 0, 'deep': 0, 'deep_ok': 0, 'fail': []}
    ierr = lane.recv().get('import_error')
    if ierr: res['import_error'] = str(ierr)[:300]
    for k, r in enumerate(recs):
        d = t3lib.deep(r); res['deep'] += d
        try:
            o, finished = t3lib.make_oracle(r)
            lane.send({'rec': {a: v.hex() if isinstance(v, bytes) else v for a, v in t3lib.inputs(r).items()}})
            herr = None
            while True:
                m = lane.recv()
                if 'done' in m:
                    cerr = m['done']
                    err = herr or (cerr if cerr is None or isinstance(cerr, str) else 'protocol: bad done')
                    if err is None and not finished(): err = 'replay returned before consuming every event'
                    if err is None and post_u32:
                        rv = m.get('ret')
                        want = [t3lib.u32(r['post'], k) for k in post_u32]
                        if not (type(rv) is list and len(rv) == len(want) and all(type(v) is int for v in rv)):
                            err = f'return {str(rv)[:80]}, want a list of {len(want)} ints (post u32 at {list(post_u32)})'
                        elif [v & 0xffffffff for v in rv] != want:
                            err = f'post u32 at {list(post_u32)}: model {[v & 0xffffffff for v in rv]}, recorded {want}'
                    elif err is None and ret_bits:
                        rv, want = m.get('ret'), r['ret'] & ((1 << ret_bits) - 1)
                        if type(rv) is not int or rv & ((1 << ret_bits) - 1) != want:
                            err = f'return {rv!r}, recorded {want} (low {ret_bits} bits of eax)'
                    break
                if herr is not None:
                    lane.send({'m': 1}); continue
                try:
                    if 'x' in m and isinstance(m['x'], list) and len(m['x']) == 2:
                        v = o.x(_int(m['x'][0]), _int(m['x'][1], True))
                    elif 'x2' in m and isinstance(m['x2'], list) and len(m['x2']) == 2:
                        v = list(o.x2(_int(m['x2'][0]), _int(m['x2'][1], True)))
                    elif 'al' in m and isinstance(m['al'], list) and len(m['al']) == 3:
                        v = o.align(*(_int(a) for a in m['al']))
                    elif 'pb' in m:
                        v = o.pb(_int(m['pb']))
                    elif 'o' in m and isinstance(m['o'], list) and len(m['o']) == 3 and isinstance(m['o'][0], str):
                        v = list(o.other(m['o'][0][:4], _int(m['o'][1], True), _int(m['o'][2], True)))
                    else:
                        fail('protocol: unknown request')
                except t3lib.Mismatch as e:
                    herr = str(e); lane.send({'m': 1}); continue
                lane.send({'v': v})
        except (RefError, OSError) as e:   # a dead, hung or misbehaving lane fails this record and every one after it
            msg = J.err(e) if isinstance(e, RefError) else f'lane pipe: {e.strerror}'
            for j, rr in enumerate(recs[k:]):
                if j: res['deep'] += t3lib.deep(rr)
                if len(res['fail']) < 400: res['fail'].append([rr['i'], t3lib.deep(rr), msg if not j else 'not run'])
            return res
        if err is None:
            res['ok'] += 1; res['deep_ok'] += d
        elif len(res['fail']) < 400:
            res['fail'].append([r['i'], d, err[:240]])
    lane.send({'end': 1})
    return res


def run(lane_dir, recfile, hold, module='runner_ai', ret_bits=0, post_u32=()):
    w = tempfile.mkdtemp(prefix='t3ref.', dir='/mnt/nvme/bbpro98/tmp' if os.path.isdir('/mnt/nvme/bbpro98/tmp') else None)
    try:
        open(f'{w}/{module}.py', 'wb').write(J.read_file(lane_dir, f'{module}.py', 200_000))
        shutil.copyfile(f'{HERE}/t3lib.py', f'{w}/t3lib.py')   # the records never go into w: the oracle stays here
        recs = t3lib.load(recfile)
        # The advisory path is for lanes already inside drive.sh's jail, which has no user bus for systemd-run. It needs
        # the marker drive.sh binds at /run/bbpro98-lane-jail (only root could create it on the host), no user bus,
        # and not the holdout, so the opt-in can never unjail lane code on the host.
        advisory = (os.environ.get('T3_LANE_ADVISORY') == '1' and not hold and os.path.exists('/run/bbpro98-lane-jail')
                    and not os.path.exists(f'/run/user/{os.getuid()}/bus'))
        if advisory:
            shutil.copyfile(f'{HERE}/t3run.py', f'{w}/t3run.py')
            cmd, env = [sys.executable, '-I', '-B', f'{w}/t3run.py', w, module], None
        else:
            cmd, env = J.jail_cmd(f'{HERE}/t3run.py', w, ['/w', module], name='t3run.py', max_size=100_000, writable=False)
        lane = Lane(cmd, env, w)
        try:
            return score(lane, recs, ret_bits, post_u32)
        finally:
            lane.close()
    finally:
        shutil.rmtree(w, ignore_errors=True)


def main():
    a = sys.argv[1:]
    if len(a) < 2: sys.exit(__doc__)
    tgt, lane = a[0], a[1]
    files = json.load(open(f'{tgt}/files.json'))
    hold = '--holdout' in a
    try:
        mod = files.get('module', 'runner_ai')
        if not (mod.isidentifier() and mod not in ('t3lib', 't3run')): raise RefError('bad module name in files.json')
        rb = files.get('ret_bits', 0)
        if rb not in (0, 8, 16, 32): raise RefError('bad ret_bits in files.json')
        pu = files.get('post_u32', [])
        if not (type(pu) is list and len(pu) <= 8 and all(type(k) is int and 0 <= k <= 0x1c for k in pu)) or pu and rb:
            raise RefError('bad post_u32 in files.json')
        res = run(lane, files['holdout' if hold else 'dev'], hold, mod, rb, tuple(pu))
    except RefError as e:
        print(f'error: {J.err(e)}'); print('FAIL'); sys.exit(1)
    if res.get('import_error'):
        print(f'{mod}.py did not import' + ('' if hold else f": {res['import_error']}"))
    print(f"records {res['n']} ok {res['ok']} | deep (past the early exits) {res['deep']} ok {res['deep_ok']}")
    if '--audit' in a:
        k = collections.Counter(m.split(',')[0][:60] for _, _, m in res['fail'])
        print('failure kinds:', dict(k.most_common(10)))
    elif not hold:
        fl = sorted(res['fail'], key=lambda f: -f[1])
        for i, d, m in fl[:12 if '-v' in a else 6]: print(f"  #{i}{' deep' if d else ''}: {m}")
    ok = res['ok'] == res['n'] and res['n'] > 0
    print('PASS' if ok else f"FAIL deep {res['deep_ok']}/{res['deep']} all {res['ok']}/{res['n']}")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
