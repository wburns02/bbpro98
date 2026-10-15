import argparse
import os
import shlex
import subprocess
import sys
import time

import play


def ns(**kw):
    d = dict(game="G", data="D", backup="B", db=None, templates=None, no_llm=False)
    d.update(kw)
    return argparse.Namespace(**d)


def test_commands_minimal():
    here = os.path.dirname(os.path.abspath(play.__file__))
    (w, b) = play.commands(ns())
    assert w[:2] == [sys.executable, os.path.join(here, "watch.py")]
    assert b[:2] == [sys.executable, os.path.join(here, "modbridge.py")]
    for cmd in (w, b):
        assert "--game" in cmd
        assert cmd[cmd.index("--game") + 1] == "G"
        assert "--data" in cmd
        assert cmd[cmd.index("--data") + 1] == "D"
        assert "--once" not in cmd
        assert "--db" not in cmd
    assert w[w.index("--data") + 1] == "D"
    assert b[b.index("--backup") + 1] == "B"
    assert "--no-llm" not in w
    assert "--templates" not in b


def test_commands_full():
    here = os.path.dirname(os.path.abspath(play.__file__))
    (w, b) = play.commands(ns(db="d.db", templates="T", no_llm=True))
    assert w[w.index("--db") + 1] == "d.db"
    assert "--no-llm" in w
    assert b[b.index("--db") + 1] == "d.db"
    assert b[b.index("--templates") + 1] == "T"
    assert "--no-llm" not in b
    assert all(os.path.isabs(c[1]) for c in (w, b))


def _mkgame(tmp_path):
    g = tmp_path / "game"
    (g / "Assn").mkdir(parents=True)
    return str(g)


def test_main_dry_run(tmp_path, capsys):
    g = _mkgame(tmp_path)
    rc = play.main(["--game", g, "--data", str(tmp_path / "d"),
                    "--backup", str(tmp_path / "b"), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 2
    assert "watch.py" in lines[0]
    assert lines[0].startswith(shlex.quote(sys.executable))
    assert "--db" not in lines[0] and "--no-llm" not in lines[0]
    assert "modbridge.py" in lines[1]
    assert "--backup" in lines[1] and "--templates" not in lines[1]
    assert "--dry-run" not in lines[0]


def test_main_refuses_no_assn(tmp_path, capsys):
    g = str(tmp_path / "notagame")
    (tmp_path / "notagame").mkdir()
    try:
        play.main(["--game", g, "--data", str(tmp_path / "d"),
                   "--backup", str(tmp_path / "b")])
        assert False, "should have raised SystemExit"
    except SystemExit as e:
        assert e.code == 2
    out = capsys.readouterr().out
    assert "Assn" in out


def test_run_first_exit_stops_other():
    quick = [sys.executable, "-c", "import sys,time; time.sleep(0.2); sys.exit(3)"]
    slow = [sys.executable, "-c", "import time; time.sleep(30)"]
    t0 = time.time()
    rc = play.run([quick, slow])
    dt = time.time() - t0
    assert rc == 3
    assert dt < 10, dt
    # the slow child must have been terminated: no stray python holding 30 s sleep
    out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    assert "time.sleep(30)" not in out


def test_run_names_children_by_their_place(capsys):
    quick = [sys.executable, "-c", "import sys; sys.exit(0)"]
    slow = [sys.executable, "-c", "import time; time.sleep(30)"]
    assert play.run([slow, quick]) == 0
    out = capsys.readouterr().out
    assert "play: started watch (pid " in out and "play: started bridge (pid " in out
    assert "play: bridge exited with code 0" in out


def test_run_second_interrupt_kills_at_once():
    class Proc:
        pid, args = 1, ["x"]

        def __init__(self):
            self.terminated = self.killed = False

        def poll(self):
            raise KeyboardInterrupt

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return 0

    procs = [Proc(), Proc()]
    feed = list(procs)
    assert play.run([["a"], ["b"]], popen=lambda cmd: feed.pop(0)) == 0
    assert all(p.terminated and p.killed for p in procs)
