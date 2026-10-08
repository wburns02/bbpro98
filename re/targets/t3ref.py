"""Referee for the 2026-10-08 bake-off tier 3: an exact replay model of FastSim FUN_6804faa1 (the runner AI update,
simtrace target runner_ai) scored against the st8 trace. Claude-owned: lanes must not edit it.

usage: python3 t3ref.py <target_dir> <lane_dir> [-v]        score <lane>/runner_ai.py on the dev records
       python3 t3ref.py <target_dir> <lane_dir> --holdout   the other half of the trace (the lane cannot read it)
       python3 t3ref.py <target_dir> <lane_dir> --audit X   summary for the audit

Contract for <lane>/runner_ai.py (stdlib + t3lib only, under 200 KB; runs in a bwrap jail, no network, no files):
  def replay(o, r): re-execute FUN_6804faa1 for one call. r = t3lib.inputs(record) (this pointer, the 0x100 bytes of
  *this before the call, the game state and manager flag bytes, ...); o = the oracle: o.x(va, arg1=None) returns the
  next probed getter's recorded value, o.pb(i) a PlayBalance read, o.other(t, gen, a) any other event. A call the
  function would not make, or a different getter / argument, raises t3lib.Mismatch. The record passes when replay
  returns having consumed every top-level event.
Score: records ok out of all, and the deep subset (records past the two early exits). PASS = every dev record ok.
targets: files.json {"dev": records.jsonl, "holdout": records.jsonl}
"""
import collections, json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import RefError, fail

HERE = os.path.dirname(os.path.abspath(__file__))


def run(lane, recfile):
    w = tempfile.mkdtemp(prefix='t3ref.', dir='/mnt/nvme/bbpro98/tmp' if os.path.isdir('/mnt/nvme/bbpro98/tmp') else None)
    try:
        src = J.read_file(lane, 'runner_ai.py', 200_000)
        open(f'{w}/runner_ai.py', 'wb').write(src)
        shutil.copyfile(f'{HERE}/t3lib.py', f'{w}/t3lib.py')
        shutil.copyfile(recfile, f'{w}/records.jsonl')
        if os.environ.get('T3_LANE_ADVISORY') != '1':   # host (drive.sh never sets it): jailed, fail closed
            r = J.jail(f'{HERE}/t3run.py', w, [], name='t3run.py', max_size=100_000, timeout=900, writable=False)
        else:   # explicit opt-in, for lanes that are already inside drive.sh's jail (no user bus for systemd-run there);
            # an advisory score only, the host referee is authoritative
            import subprocess
            shutil.copyfile(f'{HERE}/t3run.py', f'{w}/t3run.py')
            r = subprocess.run([sys.executable, '-I', '-B', f'{w}/t3run.py', w], capture_output=True, text=True,
                               timeout=900, cwd=w)
        line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ''
        try:
            return json.loads(line)
        except ValueError:
            fail('harness produced no result')
    finally:
        shutil.rmtree(w, ignore_errors=True)


def main():
    a = sys.argv[1:]
    if len(a) < 2: sys.exit(__doc__)
    tgt, lane = a[0], a[1]
    files = json.load(open(f'{tgt}/files.json'))
    hold = '--holdout' in a
    try:
        res = run(lane, files['holdout' if hold else 'dev'])
    except RefError as e:
        print(f'error: {J.err(e)}'); print('FAIL'); sys.exit(1)
    if res.get('import_error'):
        print('runner_ai.py did not import' + ('' if hold else f": {res['import_error']}"))
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
