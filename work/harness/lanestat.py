"""Read-only status of a harness lane's in-game run: is it working or stalled?

    python3 work/harness/lanestat.py [--lane 2] [--secs 5] [--shot PATH | --no-shot] [--watch SECS] [--heartbeat SECS]

Prints one JSON line: the lane's game pids, their CPU ticks over --secs seconds, the newest write in the
work copy's Assn and Stats, the last non-periodic bbtrace.log line with its age, what the screen shows,
and a verdict ('no_game', 'working', 'stale_paint', 'idle'). Takes no input, touches no process, writes nothing
inside the work copy (the shot lands in a new tempfile.mkstemp file unless --shot says otherwise), attaches no
debugger. Judge a stall from this line, not by attaching a debugger (the attach thread faults under wow64).
"""
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import time

import seasonloop


def ticks(pid, proc='/proc'):
    """utime + stime of pid in clock ticks, or None when it is gone. The stat command name is in
    parentheses and may hold spaces and ')', so split after the last ')' (ingame.ancestors does too)."""
    try:
        with open(os.path.join(proc, str(pid), 'stat'), 'rb') as fh:
            line = fh.read().decode('ascii', 'replace')
    except OSError:
        return None
    rest = line.rsplit(')', 1)[1].split()
    return int(rest[11]) + int(rest[12])       # field 3 is rest[0]: utime 14 -> 11, stime 15 -> 12


def newest(dirs):
    """(path, mtime) of the newest regular file directly inside the given dirs; (None, None) when none."""
    best, when = None, None
    for d in dirs:
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if not e.is_file(follow_symlinks=False):
                            continue
                        m = e.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        continue
                    if when is None or m > when:
                        best, when = e.path, m
        except OSError:
            continue
    return best, when


def last_trace(path, skip=('HANDLES', 'CRTFDS'), tail=2_000_000):
    """The last bbtrace.log line that is not a periodic HANDLES / CRTFDS line, reading at most the last
    `tail` bytes (the file reaches 150 MB)."""
    size = os.path.getsize(path)
    with open(path, 'rb') as fh:
        if size > tail:
            fh.seek(size - tail)
        data = fh.read(tail)
    for line in reversed(data.decode('utf-8', 'replace').splitlines()):
        line = line.strip()
        if line and not any(tok in line for tok in skip):
            return line
    return None


def trace_age(line, now=None):
    """Seconds since the line's HH:MM:SS stamp (today); None when the line has no stamp. A stamp up to 300 s ahead of
    now (the game's clock a little ahead of ours) is age 0, not a day old; further ahead, it is yesterday's."""
    m = re.match(r'(\d{2}):(\d{2}):(\d{2})\.', line or '')
    if not m:
        return None
    now = datetime.datetime.now() if now is None else now
    stamp = now.replace(hour=int(m[1]), minute=int(m[2]), second=int(m[3]), microsecond=0)
    age = (now - stamp).total_seconds()
    if age < 0:
        return 0.0 if age > -300 else age + 86400.0
    return age


def screen(png):
    """The first classifier that matches: 'busy', 'champ', 'sched', 'assn', a notice name, else 'other'."""
    if seasonloop.busy(png):
        return 'busy'
    if seasonloop.on_champ(png):
        return 'champ'
    if seasonloop.on_sched(png):
        return 'sched'
    if seasonloop.on_assn_data(png):
        return 'assn'
    return seasonloop.notice(png) or 'other'


def verdict(dticks, write_age, trace_age, scr):
    """'no_game' with no pid; 'working' when the game burns ticks or Assn/Stats or the trace moved inside
    120 s; else 'stale_paint' when the busy box is up (a stale paint, not a hang), else 'idle'. None ages
    count as old."""
    if dticks is None:
        return 'no_game'
    if dticks > 20 or (write_age is not None and write_age < 120) or (trace_age is not None and trace_age < 120):
        return 'working'
    return 'stale_paint' if scr == 'busy' else 'idle'


def status(lane, secs=5.0, shot=None, no_shot=False):
    """The dict main prints. Sets BBLANE, imports ingame inside, takes and reads the shot the same way."""
    os.environ['BBLANE'] = lane
    import ingame

    pids = ingame.game_pids()
    dticks = None
    if pids:
        first = {p: ticks(p) or 0 for p in pids}
        time.sleep(secs)
        dticks = sum(max(0, (ticks(p) or 0) - first[p]) for p in pids)

    path, mtime = newest([os.path.join(ingame.WORK, 'Assn'), os.path.join(ingame.WORK, 'Stats')])
    write_age = None if mtime is None else time.time() - mtime

    tpath = os.path.join(ingame.WORK, 'bbtrace.log')
    tline = last_trace(tpath) if os.path.exists(tpath) else None
    tage = trace_age(tline)

    scr = None
    if not no_shot:
        png = shot
        if not png:     # a fresh mode-600 file, never a guessable name in a shared directory
            fd, png = tempfile.mkstemp(prefix=f'lanestat_lane{lane}_', suffix='.png')
            os.close(fd)
        try:
            ingame.shot(png)
            scr = screen(png)
        finally:
            if not shot:
                os.unlink(png)

    return {'lane': lane, 'pids': pids, 'dticks': dticks,
            'newest': {'path': path, 'age_s': write_age},
            'trace': {'line': tline, 'age_s': tage},
            'screen': scr, 'verdict': verdict(dticks, write_age, tage, scr)}


def watch(lane, every, secs=5.0, no_shot=False, heartbeat=600.0, status_fn=None, out=print,
          clock=time.time, sleep=time.sleep, limit=None):
    """Print one JSON line each time the verdict or the newest write changes (else on a heartbeat). KeyboardInterrupt
    stops the loop quietly; limit (tests) stops it after that many status calls. Returns 0."""
    if status_fn is None:
        status_fn = status
    last, last_at = None, clock()
    calls = 0
    try:
        while True:
            s = status_fn(lane, secs, None, no_shot)
            calls += 1
            key = (s['verdict'], s['newest']['path'])
            if last is None:
                why = 'first'
            elif key != last[0]:
                why = 'change'
            elif clock() - last_at >= heartbeat:
                why = 'heartbeat'
            else:
                why = None
            if why is not None:
                out(json.dumps(dict(s, t=round(clock(), 1), why=why)))
                last, last_at = (key, why), clock()
            if limit is not None and calls >= limit:
                return 0
            sleep(every)
    except KeyboardInterrupt:
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='read-only status of an in-game lane')
    ap.add_argument('--lane', default='1', choices=('1', '2'))
    ap.add_argument('--secs', type=float, default=5, help='seconds between the two tick reads')
    ap.add_argument('--shot', default=None, help='where to put the screenshot (default a scratch file)')
    ap.add_argument('--no-shot', action='store_true')
    ap.add_argument('--watch', type=float, default=None, metavar='SECS',
                    help='poll and print a line on every verdict or newest-write change')
    ap.add_argument('--heartbeat', type=float, default=600.0, metavar='SECS',
                    help='with --watch, print a line after this many unchanged seconds')
    a = ap.parse_args(argv)

    if a.heartbeat <= 0:
        ap.error('--heartbeat needs a positive interval of seconds')
    if a.watch is not None:
        if a.watch <= 0:
            ap.error('--watch needs a positive interval of seconds')
        if a.shot is not None:
            ap.error('--watch writes many shots: only the default scratch file or --no-shot')
        return watch(a.lane, a.watch, a.secs, a.no_shot, a.heartbeat)

    print(json.dumps(status(a.lane, a.secs, a.shot, a.no_shot)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
