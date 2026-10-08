# Task: exact replay model of the runner AI update, FastSim FUN_6804faa1 (FPS Baseball Pro '98)

You are the model builder. Work only inside your lane workspace `$LANE/`. Read `progress.md` there first if it exists,
continue from it, and append to it before you stop (what you tried, what you learned, the current referee output).

## Why
re/sim_model.py replays the simulator's decision functions against simtrace records (a hook mod logged, for every
call of a traced function, each probed getter it called, in order, with arguments and return values). The runner AI
update FUN_6804faa1 (simtrace target `runner_ai`) has no model yet. Write one that re-executes the function from its
inputs and predicts exactly which probed getters it calls, in which order, with which arguments.

## Material (read only)
- Decompile: `/mnt/nvme/bbpro98/index/FastSim/_all.c`, function blocks start with `// ==== <addr>` (FUN_6804faa1 is
  `// ==== 6804faa1`; follow its callees there). Ghidra's MFC names on this code (CMiniDockFrameWnd::OnClose,
  CSplitterWnd ...) are false matches: judge by what the code does.
- Probe list: `/home/will/bbpro98/re/simtrace_probes.py` (`PROBES` = (va, stack args) of every probed getter). Only
  probed getters leave events. An unprobed callee leaves no event of its own, but the probed getters it calls do.
  A probed getter that itself makes calls opens a span: everything it calls is hidden, only its own return shows.
- The trace hook: `/home/will/bbpro98/src-latest/mods/simtrace.c` (record layout, event types).
- Dev records: `/mnt/nvme/bbpro98/targets_data/t3rai/records.jsonl` (2500 runner_ai calls from one simulated season),
  loaded by `t3lib.load(path)`. Library: `/home/will/bbpro98/re/targets/t3lib.py` (read it: the oracle, the record
  fields, top_level(), helpers). Examples of finished replay models of other functions: re/sim_model.py.

Each record: `self` (the this pointer, ecx), `obj` (the first 0x100 bytes of *this before the call), `game` (0x50
bytes of the game state object 0x68143ee0), `mflags` (8 bytes at 0x68114948), `arg`, `ret`, and `ev` (the events;
your replay never gets `ev`, only `t3lib.inputs(record)`). Use `ev` while developing to see what the function did.

## Goal
Write `$LANE/runner_ai.py` (Python 3 stdlib plus `import t3lib`, under 200 KB; it runs alone in a jail, never open
files) defining:
```
def replay(o, r):   # o = oracle, r = t3lib.inputs(record)
```
Re-execute FUN_6804faa1: for every probed getter call the function makes, call `o.x(va, arg1)` (arg1 = the first
stack argument, or omit it) and branch on the value it returns, exactly as the code does; `o.pb(i)` for a PlayBalance
read, `o.other(t, ...)` for any other event type. Decide every branch from `r` and the values the oracle returns,
never from the record's events or per-record tables. A record passes when replay returns having consumed every
top-level event with no Mismatch. Most records leave through the two early exits; the score that matters is the
deep subset (the calls that get past them).

## The referee (do not edit it)
`T3_LANE_ADVISORY=1 python3 /home/will/bbpro98/re/targets/t3ref.py /home/will/bbpro98/re/targets/t3rai $LANE [-v]`
(the variable runs it without the host's jail wrapper, which cannot start inside your workspace; same scoring)
prints `records N ok K | deep D ok M`, the first failures (record index and what the oracle expected), and PASS when
every dev record replays. Then a model audits your code, and the other half of the trace (records you cannot see)
runs as a holdout. Model the function, not the records.
