"""Bake-off tier 3 harness (Claude-owned): runs inside the referee's jail with cwd /w holding t3lib.py, the lane's
runner_ai.py and records.jsonl. For every record: replay(oracle, inputs) must consume exactly the record's top-level
events through the oracle. Prints one JSON line: totals plus the failures (record index, deep or not, message)."""
import contextlib, json, os, sys

W = sys.argv[1] if len(sys.argv) > 1 else '/w'
sys.path.insert(0, W)
import t3lib

recs = t3lib.load(W + '/records.jsonl')
res = {'n': len(recs), 'ok': 0, 'deep': 0, 'deep_ok': 0, 'fail': []}
with contextlib.redirect_stdout(sys.stderr):   # lane prints go to stderr, never into the result line
    try:
        import runner_ai
        rep = runner_ai.replay
    except Exception as e:
        rep, res['import_error'] = None, f'{type(e).__name__}: {e}'[:300]
    for r in recs:
        d = t3lib.deep(r)
        res['deep'] += d
        if rep is None: continue
        o, finished = t3lib.make_oracle(r)
        try:
            rep(o, t3lib.inputs(r))
            err = None if finished() else 'replay returned before consuming every event'
        except t3lib.Mismatch as e:
            err = str(e)
        except Exception as e:
            err = f'{type(e).__name__}: {e}'
        if err is None:
            res['ok'] += 1; res['deep_ok'] += d
        elif len(res['fail']) < 400:
            res['fail'].append([r['i'], d, err[:240]])
os.write(1, (json.dumps(res) + '\n').encode())
