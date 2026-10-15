"""Start the news watcher and the mods bridge with one command."""

import argparse
import os
import shlex
import subprocess
import sys
import time

POLL_SECONDS = 0.2
KILL_AFTER = 5.0


def commands(args):
    here = os.path.dirname(os.path.abspath(__file__))
    watch = [sys.executable, os.path.join(here, "watch.py"),
             "--game", args.game, "--data", args.data]
    if args.db:
        watch += ["--db", args.db]
    if args.no_llm:
        watch.append("--no-llm")
    bridge = [sys.executable, os.path.join(here, "modbridge.py"),
              "--game", args.game, "--data", args.data, "--backup", args.backup]
    if args.db:
        bridge += ["--db", args.db]
    if args.templates:
        bridge += ["--templates", args.templates]
    return [watch, bridge]


def _name(argv):
    if not isinstance(argv, list):
        return os.path.basename(argv)
    for a in argv:
        if isinstance(a, str) and a.endswith(".py"):
            return os.path.splitext(os.path.basename(a))[0]
    return "child"


def _stop(procs):
    for p in procs:
        try:
            p.terminate()
        except OSError:
            pass
    deadline = time.time() + KILL_AFTER
    for p in procs:
        while p.poll() is None and time.time() < deadline:
            time.sleep(POLL_SECONDS)
    for p in procs:
        if p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass
        try:
            p.wait(timeout=KILL_AFTER)
        except Exception:
            pass


def run(cmds, popen=subprocess.Popen):
    procs = []
    code = 0
    try:
        for cmd in cmds:
            p = popen(cmd)
            procs.append(p)
            print("play: started %s (pid %d)" % (_name(cmd), p.pid), flush=True)
        first = None
        while first is None:
            for p in procs:
                if p.poll() is not None:
                    first = p
                    break
            if first is None:
                time.sleep(POLL_SECONDS)
        code = first.returncode
        print("play: %s exited with code %s" % (_name(first.args), code), flush=True)
        others = [p for p in procs if p is not first]
        _stop(others)
        for p in [first] + others:
            try:
                p.wait(timeout=KILL_AFTER)
            except Exception:
                pass
        return code
    except KeyboardInterrupt:
        print("play: interrupted", flush=True)
        _stop(procs)
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="play.py",
                                 description="Start the news watcher and the mods bridge.")
    ap.add_argument("--game", required=True, help="game folder (holds Assn and Stats)")
    ap.add_argument("--data", default="~/bbnews", help="news data folder (default ~/bbnews)")
    ap.add_argument("--backup", default="~/bbnews-backup",
                    help="bridge backup folder (default ~/bbnews-backup)")
    ap.add_argument("--db", help="Lahman database passed to watcher and bridge")
    ap.add_argument("--templates", help="templates folder for Build a Season")
    ap.add_argument("--no-llm", action="store_true", help="watcher flag, no LLM recaps")
    ap.add_argument("--dry-run", action="store_true", help="print the commands and exit")
    args = ap.parse_args(argv)

    args.data = os.path.expanduser(args.data)
    args.backup = os.path.expanduser(args.backup)
    assn = os.path.join(args.game, "Assn")
    if not os.path.isdir(assn):
        print("play: %s has no Assn folder; not a game folder?" % args.game, flush=True)
        raise SystemExit(2)

    cmds = commands(args)
    if args.dry_run:
        for c in cmds:
            print(shlex.join(c), flush=True)
        return 0

    os.makedirs(args.data, exist_ok=True)
    os.makedirs(args.backup, exist_ok=True)
    return run(cmds)


if __name__ == "__main__":
    sys.exit(main())
