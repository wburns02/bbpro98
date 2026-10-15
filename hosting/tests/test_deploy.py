"""deploy.sh stops when an rsync fails instead of reading the failure as "nothing changed"."""
import os
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1] / 'deploy.sh'


def run(tmp_path, rsync_body):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name, body in (('rsync', rsync_body), ('ssh', 'exit 0')):
        p = bindir / name
        p.write_text('#!/bin/bash\n' + body + '\n')
        p.chmod(0o755)
    src = tmp_path / 'install'
    src.mkdir()
    env = dict(os.environ, PATH='%s:%s' % (bindir, os.environ['PATH']), HOST='nobody@nowhere', SRC=str(src),
               NAMES=str(tmp_path / 'none.json'))
    return subprocess.run(['bash', str(DEPLOY), '--dry-run'], env=env, capture_output=True, text=True, timeout=60)


def test_clean_dry_run_succeeds(tmp_path):
    r = run(tmp_path, 'exit 0')
    assert r.returncode == 0, r.stderr
    assert 'game files unchanged' in r.stdout


def test_changes_are_reported(tmp_path):
    r = run(tmp_path, 'echo "<f.st...... ${@: -2:1}"; echo ".d..t...... ./"')
    assert r.returncode == 0, r.stderr
    assert 'news, create and bridge units would restart' in r.stdout and 'the game would restart' in r.stdout
    assert '.d..t' not in r.stdout


def test_failed_rsync_stops_the_deploy(tmp_path):
    r = run(tmp_path, 'echo "rsync: connection unexpectedly closed" >&2; exit 12')
    assert r.returncode == 12
    assert 'deploy: rsync failed (exit 12)' in r.stderr
    assert 'unchanged' not in r.stdout


def test_one_failed_rsync_late_in_the_run_stops_it(tmp_path):
    # Only the gate copy fails: everything before it ran, nothing after it (the game step) did.
    r = run(tmp_path, 'case "$*" in *gate.py*) exit 23;; esac; exit 0')
    assert r.returncode == 23
    assert 'gate.py' in r.stderr and 'game files unchanged' not in r.stdout
