"""Bake-off tier 3 lane shim (Claude-owned): runs inside the referee's jail with cwd /w holding t3lib.py and the lane's
model (runner_ai.py, or files.json's module), and nothing else. The trace records and the oracle stay in the host referee (t3ref.py); this process
only sees each record's inputs and forwards every oracle call over its stdin/stdout, so the graded code can neither
read the recorded events nor write the result.

Protocol, one JSON line each way: host -> {"rec": inputs (bytes fields as hex)} | {"end": 1};
shim -> {"x": [va, arg1]} | {"x2": [va, arg1]} | {"al": [a, b, c]} | {"pb": i} | {"o": [t, gen, a]}, host -> {"v": value} | {"m": 1} (mismatch);
shim -> {"done": null | error, "ret": replay's return (int, list of ints or null)} after replay returns or raises."""
import json, os, sys

W = sys.argv[1] if len(sys.argv) > 1 else '/w'
MODULE = sys.argv[2] if len(sys.argv) > 2 else 'runner_ai'
sys.path.insert(0, W)
proto_out = os.fdopen(os.dup(1), 'w')
proto_in = sys.stdin
os.dup2(2, 1)                       # lane prints go to stderr, never onto the protocol channel
sys.stdout = sys.stderr
import t3lib

BYTES = ('game', 'mflags', 'obj', 'xf')


def ask(msg):
    proto_out.write(json.dumps(msg) + '\n'); proto_out.flush()
    r = json.loads(proto_in.readline())
    if 'm' in r: raise t3lib.Mismatch('mismatch')
    return r['v']


class Oracle:
    __slots__ = ()
    def x(self, va, arg1=None): return ask({'x': [va, arg1]})
    def x2(self, va, arg1=None): return tuple(ask({'x2': [va, arg1]}))
    def align(self, a, b, c): return ask({'al': [a, b, c]})
    def pb(self, i): return ask({'pb': i})
    def other(self, t, gen=None, a=None): return tuple(ask({'o': [t, gen, a]}))


try:
    rep, ierr = __import__(MODULE).replay, None
except Exception as e:
    rep, ierr = None, f'{type(e).__name__}: {e}'[:300]
proto_out.write(json.dumps({'import_error': ierr}) + '\n'); proto_out.flush()
o = Oracle()
for line in proto_in:
    m = json.loads(line)
    if 'end' in m: break
    r = {k: bytes.fromhex(v) if k in BYTES else v for k, v in m['rec'].items()}
    try:
        if rep is None: raise RuntimeError(f'{MODULE}.py did not import')
        ret, err = rep(o, r), None
        if not (ret is None or type(ret) is int and abs(ret) < 1 << 64 or type(ret) in (list, tuple) and len(ret) <= 8
                and all(type(v) is int and abs(v) < 1 << 64 for v in ret)): ret, err = None, 'replay returned a non-int'
        if type(ret) is tuple: ret = list(ret)
    except t3lib.Mismatch:
        ret, err = None, 'mismatch'
    except Exception as e:
        ret, err = None, f'{type(e).__name__}: {e}'[:240]
    proto_out.write(json.dumps({'done': err, 'ret': ret}) + '\n'); proto_out.flush()
