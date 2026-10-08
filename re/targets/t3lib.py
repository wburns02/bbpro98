"""Bake-off tier 3 library (Claude-owned, read only for lanes): the runner_ai trace records and the oracle a replay
model runs against. Python 3 stdlib only; the referee copies this file next to the lane's runner_ai.py in its jail.

  load(path)        -> list of record dicts (one JSON line each, see re/bakeoff/t3_extract.py)
  inputs(rec)       -> what replay() gets: the record without its events and after-call values (post, ret, rm1, ri1)
  make_oracle(rec)  -> (oracle, finished): replay(oracle, inputs(rec)) re-executes the function; finished() says whether
                       every top-level event was consumed
  top_level(rec)    -> the top-level events (nested getter spans collapsed, as sim_model.Tape does)
  i32 / s16 / s8 / s16v / cdiv: the integer helpers sim_model.py uses
"""
import json, struct, types


class Mismatch(Exception):
    pass


def load(path):
    out = []
    for l in open(path):
        d = json.loads(l)
        for k in ('game', 'mflags', 'obj', 'xf', 'post'): d[k] = bytes.fromhex(d[k])
        d['ev'] = [tuple(e) for e in d['ev']]
        out.append(d)
    return out


AFTER = ('ev', 'post', 'ret', 'rm1', 'ri1')   # what the call produced: never shown to the model


def inputs(rec):
    return {k: v for k, v in rec.items() if k not in AFTER}


def top_level(rec):
    """events outside nested getter spans: a Y marker opens the span of a probed getter that makes calls; its own X
    (the getter's return) closes it and is kept when the span is outermost; everything inside is dropped"""
    out, stack = [], []
    for e in rec['ev']:
        t = e[0]
        if t == 'Y': stack.append(e[1]); continue
        if t == 'X' and stack and stack[-1] == e[1]:
            stack.pop()
            if stack: continue
        elif stack: continue
        out.append(e)
    return out


def fmt(e):
    t, g, idx, a, b, r, va = e
    if t == 'X': return f'X[{va:x}](ecx={a & 0xffffffff:#x}, arg1={b}, arg2={idx})={r}'
    if t == 'P': return f'PB[{idx}]={r}'
    if t == 'L': return f'align(a={a}, b={b}, c={idx})'
    return f'{t}(gen={g}, idx={idx}, a={a}, b={b})={r}'


def make_oracle(rec):
    ev = top_level(rec)
    pos = [0]

    def nxt(t, what):
        if pos[0] >= len(ev): raise Mismatch(f'model wants {what}, record has no more events')
        e = ev[pos[0]]
        if e[0] != t: raise Mismatch(f'model wants {what}, record has {fmt(e)} (event {pos[0]})')
        pos[0] += 1
        return e

    def x_ev(va, arg1):
        i = pos[0]
        n = ev[i] if i < len(ev) else None
        if i and (n is None or n[0] != 'X' or n[6] != va or arg1 is not None and n[4] & 0xffffffff != arg1 & 0xffffffff):
            p = ev[i - 1]
            if p[0] == 'X' and p[6] == va and (arg1 is None or p[4] & 0xffffffff == arg1 & 0xffffffff):
                return p
        e = nxt('X', f'getter {va:x}')
        if e[6] != va: raise Mismatch(f'model wants getter {va:x}, record has {fmt(e)} (event {pos[0] - 1})')
        if arg1 is not None and e[4] & 0xffffffff != arg1 & 0xffffffff:
            raise Mismatch(f'getter {va:x} arg1 {e[4] & 0xffffffff:#x}, model {arg1 & 0xffffffff:#x} (event {pos[0] - 1})')
        return e

    def x(va, arg1=None):
        """the return of probed getter va (unsigned 32 bit), called next; arg1 (when given) must equal the recorded
        first stack argument. simtrace drops an X identical to the one before it, so a repeated identical call
        returns the previous value without consuming an event."""
        return x_ev(va, arg1)[5] & 0xffffffff

    def x2(va, arg1=None):
        """as x, but returns (value, idx): idx is the X event's extra word (the second stack argument, or what simtrace
        logs there for that getter, e.g. the flight-path step's new z for FUN_6803997d)"""
        e = x_ev(va, arg1)
        return e[5] & 0xffffffff, e[2]

    def align(a, b, c):
        """FUN_6801a4b1(a, b, c) (simtrace event L): the alignment slots the function sets; checked, nothing returned"""
        e = nxt('L', f'align({a}, {b}, {c})')
        if (e[3], e[4], e[2]) != (a, b, c):
            raise Mismatch(f'model align({a}, {b}, {c}), record has {fmt(e)} (event {pos[0] - 1})')

    def pb(i):
        e = nxt('P', f'PB[{i}]')
        if e[2] != i: raise Mismatch(f'model wants PB[{i}], record has PB[{e[2]}] (event {pos[0] - 1})')
        return e[5]

    def other(t, gen=None, a=None):
        """any other event type (S speed, G/H/K stat reads, F/W fatigue, M/R/C RNG): returns (idx, a, b, r). Not X, P or L:
        those are outputs or have their own checked calls"""
        if t in ('X', 'Y', 'P', 'L'): raise Mismatch(f'other({t!r}): use the dedicated oracle call')
        e = nxt(t, t)
        if gen is not None and e[1] != gen or a is not None and e[3] != a:
            raise Mismatch(f'model wants {t} gen {gen} a {a}, record has {fmt(e)} (event {pos[0] - 1})')
        return e[2], e[3], e[4], e[5]

    o = types.SimpleNamespace(x=x, x2=x2, align=align, pb=pb, other=other)
    return o, (lambda: pos[0] == len(ev))


def i32(b, o): return struct.unpack_from('<i', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def s16(b, o): return struct.unpack_from('<h', b, o)[0]


def s8(v):
    v &= 0xff
    return v - 0x100 if v >= 0x80 else v


def s16v(v):
    v &= 0xffff
    return v - 0x10000 if v >= 0x8000 else v


def cdiv(a, b):
    """C integer division (truncates toward zero)"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def deep(rec):
    """records that get past the function's two early exits (more than 4 top-level events): the scored subset"""
    return len(top_level(rec)) > 4
