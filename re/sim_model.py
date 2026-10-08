#!/usr/bin/env python3
"""Roadmap #10 M10 referee: replays the documented sim logic (work/SIM_LOGIC_MODEL.md) against simtrace records
(src-latest/mods/simtrace.c, read by re/simtrace_dump.py). usage: sim_model.py simtrace.bin [...]

Checks, per traced function:
  rng        every record: each main (gen 1) and injury (gen 2) RNG call replays from the state before the call, and
             the state after the call is reached
  inj_check  n = PB[0x354 + event]; injured iff injury_rng.mod(n) == 0
  inj_type   the whole roll (injury number, days out, reroll, after-roll) from injury.dat in the work copy's SIM.DAT
  stamina    the stamina-left formula, exact
  fatigue    the fatigue level, exact
  steal, hit_run, sacrifice, squeeze, pickoff, pitchout   the manager ratings, exact replay of every getter / PB read
  offman     the offensive manager's rolls and the flags it sets (steal 2nd/3rd, hit-and-run, bunt, squeeze)
  catch      the catch / error roll and the error kind; catch_adj the fielding table load
  pitch      pitch execution: control and movement rolls, velocity roll, scatter box, failed-movement outcome
A model replays the record's events through a Tape (exact order, arguments and PB values); 'skipped' means a nested
record was dropped by its cap or the record overflowed.
Exits 1 if any check has a mismatch.
"""
import collections, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, '..', 'work')]
import chunkdat, simchunks
from pitch_model import PB, Rng, cdiv
from simtrace_dump import NAMES, records, fmt_ev
from simtrace_probes import PROBES

WORK = '/mnt/nvme/bbpro98/work_install'


def injury_dat():
    for k, tag, d in chunkdat.split(open(os.path.join(WORK, 'SIM.DAT'), 'rb').read())[0]:
        if chunkdat.KNOWN.get(k | int.from_bytes(tag, 'little') << 16) == 'injury.dat':
            return simchunks.dec_injury(d)
    raise SystemExit('injury.dat not in SIM.DAT')


INJ = injury_dat()


def i32(b, o):
    return struct.unpack_from('<i', b, o)[0]


def s16(b, o):
    return struct.unpack_from('<h', b, o)[0]


def xev(r, va):
    """X events (getter returns) of the probe at `va`"""
    return [e for e in r['ev'] if chr(e[0]) == 'X' and PROBES[e[1]][0] == va]


def ev_of(r, *types):
    return [e for e in r['ev'] if chr(e[0]) in types]


class Mismatch(Exception):
    pass


class Skip(Exception):
    """the record cannot be replayed (a nested target's record was dropped by its cap)"""


class Tape:
    """The record's events outside nested getter spans (Y id ... X id), consumed in call order by a model that
    re-executes the function: each pb() / x() / speed() / stat() must be the next event, with the same index and
    arguments, and returns the recorded value. done() fails if events are left over."""

    def __init__(self, r):
        self.ev, self.orig, stack = [], [], []
        for j, e in enumerate(r['ev']):
            t = chr(e[0])
            if t == 'Y': stack.append(e[1]); continue
            if t == 'X' and stack and stack[-1] == e[1]:
                stack.pop()
                if stack: continue
            elif stack: continue
            self.ev.append(e); self.orig.append(j)
        self.i = 0
        self.kids = r.get('kids', {})

    def _next(self, t, what):
        if self.i >= len(self.ev): raise Mismatch(f'model wants {what}, record has no more events')
        e = self.ev[self.i]
        if chr(e[0]) != t: raise Mismatch(f'model wants {what}, record has {fmt_ev(e)} (event {self.i})')
        self.i += 1
        return e

    def pb(self, i):
        e = self._next('P', f'PB[{i}]')
        if e[2] != i: raise Mismatch(f'model wants PB[{i}], record has PB[{e[2]}] (event {self.i - 1})')
        if e[5] != PB[i]: raise Mismatch(f'PB[{i}] read {e[5]}, table {PB[i]}')
        return e[5]

    def x(self, va, arg1=None):
        """the next getter return (unsigned 32 bit); arg1, when given, must be the recorded first stack argument"""
        n = self.ev[self.i] if self.i < len(self.ev) else None
        if self.i and (n is None or chr(n[0]) != 'X' or PROBES[n[1]][0] != va
                       or arg1 is not None and n[4] & 0xffffffff != arg1 & 0xffffffff):
            p = self.ev[self.i - 1]   # simtrace.c ev() drops an X event identical to the previous one: a repeated call
            if chr(p[0]) == 'X' and PROBES[p[1]][0] == va and (arg1 is None or p[4] & 0xffffffff == arg1 & 0xffffffff):
                return p[5] & 0xffffffff
        e = self._next('X', f'getter {va:x}')
        if PROBES[e[1]][0] != va:
            raise Mismatch(f'model wants getter {va:x}, record has {fmt_ev(e)} (event {self.i - 1})')
        if arg1 is not None and e[4] & 0xffffffff != arg1 & 0xffffffff:
            raise Mismatch(f'getter {va:x} arg {e[4] & 0xffffffff:#x}, model {arg1 & 0xffffffff:#x}')
        return e[5] & 0xffffffff

    def mod(self, n):
        """main RNG mod(n): its recorded result (check_rng separately proves the value replays)"""
        e = self._next('M', f'main mod({n})')
        if e[1] != 1 or e[3] != n: raise Mismatch(f'model wants main mod({n}), record has {fmt_ev(e)} (event {self.i - 1})')
        return e[5]

    def call(self, name, arg=None):
        """a nested target: returns its recorded eax"""
        e = self._next('Z', f'call of {name}')
        if NAMES[e[1]] != name: raise Mismatch(f'model calls {name}, record calls {NAMES[e[1]]} (event {self.i - 1})')
        if arg is not None and e[4] != arg: raise Mismatch(f'{name} called with {e[4]}, model {arg}')
        k = self.kids.get(self.orig[self.i - 1])
        if k is None: raise Skip(f'{name} record dropped')
        return k['ret']

    def take(self, t, gen=None, a=None, what=''):
        """the next event of type t (and RNG generator gen / first operand a when given)"""
        e = self._next(t, what or t)
        if gen is not None and e[1] != gen or a is not None and e[3] != a:
            raise Mismatch(f'model wants {what or t} gen {gen} a {a}, record has {fmt_ev(e)} (event {self.i - 1})')
        return e

    def speed(self):
        return self._next('S', 'runner speed')[5]

    def stat(self, t, idx):
        """the next player stat read: t 'G' FUN_6803e1b2, 'H' FUN_6803da2b, 'K' FUN_6803e2e1; returns the int read"""
        e = self._next(t, f'stat {t}[{idx}]')
        if e[2] != idx: raise Mismatch(f'model wants stat {t}[{idx}], record has {fmt_ev(e)} (event {self.i - 1})')
        return e[5]

    def peek(self):
        """the type letter of the next event, or None at the end (does not consume)"""
        return chr(self.ev[self.i][0]) if self.i < len(self.ev) else None

    def fat(self):
        """the next fatigue state read (FUN_6803df0d)"""
        return self._next('F', 'fatigue state')[5]

    def skip_to(self, va, arg1=None):
        """consume events up to the next getter va (with first stack argument arg1): the span of an unprobed virtual
        call, whose callees' events are top-level"""
        while self.i < len(self.ev):
            e = self.ev[self.i]
            if chr(e[0]) == 'X' and PROBES[e[1]][0] == va and (arg1 is None or e[4] & 0xffffffff == arg1 & 0xffffffff):
                return
            self.i += 1
        raise Mismatch(f'model skips to getter {va:x}, record has none')

    def done(self):
        if self.i != len(self.ev): raise Mismatch(f'{len(self.ev) - self.i} events left: {fmt_ev(self.ev[self.i])} ...')


def s8(v):
    v &= 0xff
    return v - 0x100 if v >= 0x80 else v


def s16v(v):
    v &= 0xffff
    return v - 0x10000 if v >= 0x8000 else v


def model_steal(r):
    """FUN_68052bd5(runner view, base 2 or 3): steal chance 0..100, additive"""
    t, base = Tape(r), r['arg']
    v = 0
    gate = t.x(0x6800f270) & 0xff   # manager flag 0x40 for the batting side
    if gate:
        if base == 2:
            gate = t.x(0x68032ff0) != 0 and t.x(0x6800f600) == 0          # runner on first, second open
        elif base == 3:
            gate = t.x(0x6800f600) != 0 and t.x(0x6800f640) == 0          # runner on second, third open
        else: gate = False
    if gate:
        count = [t.pb(0x36 + i) for i in range(12)]                       # stealChance{balls}{strikes}Count
        strikes = t.x(0x6800f1e0) & 0xff
        balls = t.x(0x6800f1c0) & 0xff
        outs = t.x(0x68002c80) & 0xff
        runs_bat = t.x(0x68056985) & 0xff
        runs_fld = t.x(0x68056985) & 0xff
        sp = t.speed()
        hold = t.x(0x68055650) & 0xff                                     # pitcher hold
        v = count[strikes + balls * 3]
        for k in range(4):                                                # speed buckets
            if not t.pb(0x42 + k) < sp: v += t.pb(0x46 + k); break
        else: v += t.pb(0x4a)
        for k in range(4):                                                # hold buckets
            if not t.pb(0x4b + k) < hold: v += t.pb(0x4f + k); break
        else: v += t.pb(0x53)
        if t.x(0x6800f680) == 0: v += t.pb(0x55 if base == 2 else 0x54)
        if t.x(0x680556c0) == 0: v += t.pb(0x56)
        if t.x(0x6804935e) & 0xff: v += t.pb(0x57)
        if base == 2:
            hi, lo = (0x58, 0x5a) if outs == 2 else (0x5c, 0x5e)
            ch = t.x(0x68038e50)                                          # batter CH (contact)
            if t.pb(hi) <= ch: v += t.pb(hi + 1)
            ch = t.x(0x68038e50)
            if ch <= t.pb(lo): v += t.pb(lo + 1)
        else:
            if outs in (0, 1, 2): v += t.pb(0x60 + outs)
            ch = t.x(0x68038e50)
            if t.pb(99) <= ch: v += t.pb(100)
        if s16v(runs_bat - runs_fld) <= t.pb(0x65): v += t.pb(0x66)
    t.done()
    want = min(max(s16v(v), 0), 100)
    if r['ret'] & 0xffff != want: return f'steal chance {r["ret"] & 0xffff}, model {want}'
    return None


def model_offman(r):
    """FUN_68054b0a: offensive manager sets steal/hit-run/sacrifice/squeeze flags by RNG rolls"""
    t = Tape(r)
    if t.x(0x6803cc73) == 0:
        # steal 2nd
        pb = t.pb(0x9d)
        v = cdiv(pb * s16v(t.call('steal', 2)), 100)
        sp = t.speed()
        if t.mod(100) < 100 - sp:
            v = 0
        if t.mod(100) < v:
            t.x(0x68002c40, 0x41)
        # steal 3rd
        pb = t.pb(0x9d)
        v = cdiv(pb * s16v(t.call('steal', 3)), 100)
        sp = t.speed()
        if t.mod(100) < 100 - sp:
            v = 0
        if t.mod(100) < v:
            t.x(0x68002c40, 0x42)
        # hit and run, else sacrifice
        pb = t.pb(0x9e)
        v = cdiv(pb * s16v(t.call('hit_run')), 100)
        if t.mod(100) < v:
            t.x(0x68002c40, 0x10)
        else:
            pb = t.pb(0x9f)
            v = cdiv(pb * s16v(t.call('sacrifice')), 100)
            if t.mod(100) < v:
                t.x(0x68002c40, 0x80)
        # squeeze
        pb = t.pb(0xa0)
        v = cdiv(pb * s16v(t.call('squeeze')), 100)
        if t.mod(100) < v:
            t.x(0x68002c40, 0x20)
    t.done()
    return None


def model_squeeze(r):
    """FUN_68053b36(runner view): squeeze bunt chance 0..100"""
    t = Tape(r)
    v = 0
    outs = t.x(0x68002c80) & 0xff
    third = t.x(0x6800f640)
    if third != 0 and outs == 1:
        if t.x(0x68039356) & 0xff:
            a = t.x(0x68038e50)
            if a >= 1 << 31:
                a -= 1 << 32
            if a <= t.pb(0x97):
                b = t.x(0x68038e70)
                if b >= 1 << 31:
                    b -= 1 << 32
                if b <= t.pb(0x98):
                    strikes = t.x(0x6800f1e0) & 0xff
                    balls = t.x(0x6800f1c0) & 0xff
                    if balls + strikes < 2:
                        v = s16v(t.pb(0x99))
                    elif (balls == 1 and strikes == 1) or (balls == 2 and strikes == 0):
                        v = s16v(t.pb(0x9a))
                    t.x(0x6800f640)
                    sp = t.speed()
                    if t.pb(0x9b) <= sp:
                        v = s16v(t.pb(0x9c) + v)
    t.done()
    want = min(max(s16v(v), 0), 100)
    if r['ret'] & 0xffff != want:
        return f'squeeze chance {r["ret"] & 0xffff}, model {want}'
    return None


def model_pickoff(r):
    """FUN_68036d52(param_1): pickoff attempt score (short)"""
    t = Tape(r)
    local_14 = 0
    iVar1 = t.x(0x68032ff0)
    iVar2 = t.x(0x6800f600)
    iVar3 = t.x(0x6800f640)
    if (iVar1 != 0 and iVar2 == 0) or (iVar2 != 0 and iVar3 == 0):
        uVar4 = s16v(t.pb(10))
        uVar5 = s16v(t.call('steal', 3 - (iVar2 == 0)))
        uVar6 = s16v(t.pb(0xb))
        if iVar2 == 0:
            t.x(0x68032ff0)
        else:
            t.x(0x6800f600)
        local_18 = s16v(t.x(0x68038e30))
        uVar7 = s16v(t.pb(0xc))
        lead = s16v(int.from_bytes(r['xf'][:2], 'little'))
        iVar1 = 0 if lead < 0 else (4 if lead > 4 else lead)
        uVar8 = s16v(t.pb(0xd))
        local_14 = s16v((4 - iVar1) * uVar8 + uVar7 * local_18 + uVar5 + uVar6 + uVar4)
    t.done()
    want = s16v(local_14) & 0xffff
    if r['ret'] & 0xffff != want:
        return f'pickoff score {r["ret"] & 0xffff}, model {want}'
    return None


def model_pitchout(r):
    """FUN_68036e91: pitchout score (short)"""
    t = Tape(r)
    local_2c = 0
    inning = t.x(0x6800f200) & 0xff
    balls = t.x(0x6800f1c0) & 0xff
    runs3 = t.x(0x68056985, 3) & 0xff
    runs4 = t.x(0x68056985, 4) & 0xff
    diff = runs3 - runs4
    on2 = t.x(0x6800f600)
    on3 = t.x(0x6800f640)
    hit_run = s16v(t.call('hit_run'))
    steal2 = s16v(t.call('steal', 2))
    steal3 = s16v(t.call('steal', 3))
    best = max(steal2, steal3)
    mgr = t.x(0x68039356) & 0xff
    if hit_run < best:
        if steal3 < steal2 or steal3 < hit_run:
            if on3 == 0 or on2 == 0:
                if on3 == 0 and on2 == 0:
                    gate = runs3 == runs4 or diff == -1
                else:
                    gate = diff == -1 or diff == -2
            else:
                gate = diff == -2 or diff == -3
        else:
            if on3 == 0:
                gate = runs3 == runs4 or diff == -1
            else:
                gate = diff == -1 or diff == -2
    else:
        gate = runs3 == runs4 or diff == -1
    if mgr == 1 and gate:
        if t.pb(0xe) <= best or t.pb(0xf) <= hit_run:
            local_2c = s16v(t.pb(0x10))
            if balls == 0:
                local_2c = s16v(t.pb(0x11) + local_2c)
            elif balls == 1:
                local_2c = s16v(t.pb(0x12) + local_2c)
            elif balls == 2:
                local_2c = s16v(t.pb(0x13) + local_2c)
            elif balls == 3:
                local_2c = s16v(t.pb(0x14) + local_2c)
            if inning == 8:
                local_2c = s16v(t.pb(0x15) + local_2c)
            elif inning > 8:
                local_2c = s16v(t.pb(0x16) + local_2c)
            if int.from_bytes(r['xf'][:4], 'little', signed=True) == 1:
                local_2c = s16v(t.pb(0x17) + local_2c)
    t.done()
    want = s16v(local_2c) & 0xffff
    if r['ret'] & 0xffff != want:
        return f'pitchout {r["ret"] & 0xffff}, model {want}'
    return None


def model_hit_run(r):
    """FUN_68053248(runner view): hit-and-run chance 0..100, additive"""
    t = Tape(r)
    v = 0
    r1 = t.x(0x68032ff0)
    if r1 == 0:
        b2 = False
    else:
        r2 = t.x(0x6800f600)
        if r2 == 0:
            b2 = False
        else:
            r3 = t.x(0x6800f640)
            b2 = r3 == 0
    r1b = t.x(0x68032ff0)
    if r1b != 0:
        r3b = t.x(0x6800f640)
        b1 = r3b == 0
    else:
        b1 = False
    outs = t.x(0x68002c80) & 0xff
    if b1 and outs < 2:
        flag = t.x(0x6802fd50)
        if flag == 0:
            v = t.pb(0x67)
            t.x(0x68032ff0)
            sp = t.speed()
            ra = t.x(0x68038e50) & 0xff
            rb = t.x(0x68038e70) & 0xff
            strikes = t.x(0x6800f1e0) & 0xff
            balls = t.x(0x6800f1c0) & 0xff
            runs3 = t.x(0x68056985) & 0xff
            runs4 = t.x(0x68056985) & 0xff
            d = s16v(runs3 - runs4)
            if d < -2:
                v = s16v(v + t.pb(0x68))
            elif d == -2:
                v = s16v(v + t.pb(0x69))
            elif d == 1:
                v = s16v(v + t.pb(0x6a))
            elif d > 1:
                v = s16v(v + t.pb(0x6b))
            if b2:
                v = s16v(v + t.pb(0x6c))
            if t.pb(0x6d) < sp:
                if t.pb(0x6e) < sp:
                    if t.pb(0x6f) < sp:
                        v = s16v(v + t.pb(0x73))
                    else:
                        v = s16v(v + t.pb(0x72))
                else:
                    v = s16v(v + t.pb(0x71))
            else:
                v = s16v(v + t.pb(0x70))
            if t.pb(0x74) < ra:
                if t.pb(0x75) < ra:
                    if t.pb(0x76) < ra:
                        v = s16v(v + t.pb(0x7a))
                    else:
                        v = s16v(v + t.pb(0x79))
                else:
                    v = s16v(v + t.pb(0x78))
            else:
                v = s16v(v + t.pb(0x77))
            if t.pb(0x7b) < rb:
                if t.pb(0x7c) < rb:
                    if t.pb(0x7d) < rb:
                        v = s16v(v + t.pb(0x81))
                    else:
                        v = s16v(v + t.pb(0x80))
                else:
                    v = s16v(v + t.pb(0x7f))
            else:
                v = s16v(v + t.pb(0x7e))
            if t.x(0x6804935e) & 0xff:
                v = s16v(v + t.pb(0x82))
            if balls == 3:
                v = s16v(v + t.pb(0x83))
            elif strikes == 2:
                v = s16v(v + t.pb(0x84))
            elif balls == strikes:
                v = s16v(v + t.pb(0x85))
            elif strikes == 1 and balls == 0:
                v = s16v(v + t.pb(0x86))
    t.done()
    want = min(max(s16v(v), 0), 100)
    if r['ret'] & 0xffff != want:
        return f'hit_run chance {r["ret"] & 0xffff}, model {want}'
    return None


def model_sacrifice(r):
    """FUN_680537ad(runner view): sacrifice bunt chance 0..100"""
    t = Tape(r)
    sg = lambda v: v - (1 << 32) if v >= (1 << 31) else v
    outs = t.x(0x68002c80) & 0xff
    strikes = t.x(0x6800f1e0) & 0xff
    b1 = t.x(0x68032ff0) != 0 and t.x(0x6800f640) == 0
    b2 = t.x(0x68032ff0) != 0 and t.x(0x6800f600) != 0 and t.x(0x6800f640) == 0
    v = 0
    if outs < 2 and strikes < 2 and b1:
        g = sg(t.x(0x68038e50))
        if g <= t.pb(0x87):
            g = sg(t.x(0x68038e70))
            if g <= t.pb(0x88):
                v = s16v(t.pb(0x89))
                if t.x(0x68049594) & 0xff:
                    v = s16v(v + t.pb(0x8a))
                if outs == 1:
                    v = s16v(v + t.pb(0x8b))
                if t.x(0x68039356) & 0xff:
                    v = s16v(v + t.pb(0x8c))
                    g = sg(t.x(0x68038e50))
                    if g <= t.pb(0x8d):
                        g = sg(t.x(0x68038e70))
                        if g <= t.pb(0x8e):
                            v = s16v(v + t.pb(0x8f))
                    if outs == 0 and b2:
                        v = s16v(v + t.pb(0x90))
                    if outs == 1:
                        g = sg(t.x(0x68038e50))
                        if t.pb(0x91) <= g:
                            g = sg(t.x(0x68038e70))
                            if t.pb(0x92) <= g:
                                v = s16v(v + t.pb(0x93))
                if t.x(0x68049594) & 0xff:
                    g = sg(t.x(0x68038e50))
                    if g <= t.pb(0x94):
                        g = sg(t.x(0x68038e70))
                        if g <= t.pb(0x95):
                            v = s16v(v + t.pb(0x96))
    t.done()
    want = min(max(s16v(v), 0), 100)
    if r['ret'] & 0xffff != want:
        return f'sacrifice chance {r["ret"] & 0xffff}, model {want}'
    return None


CATCH_POS_PB = [0x1d4, 0x1d5, 0x1d6, 0x1d7, 0x1d2, 0x1d3, 0x1da, 0x1d9, 0x1d8]   # 6808e940[pos], set by catch_adj
ERR_TYPE = [[30, 50, 75, 85], [15, 40, 60, 90], [25, 55, 70, 90], [15, 40, 70, 90]]  # .rdata 6808a100, by error kind


def model_catch_adj(r):
    """FUN_68023dd3: copies PB 0x1d2..0x1ec into the fielding tables at 6808e940..6808e9d8"""
    t = Tape(r)
    for i in [*range(0x1d2, 0x1db), 0x1f1, 0x1f2, *range(0x1f3, 0x1fa), *range(0x1db, 0x1ed)]: t.pb(i)
    t.done()
    return None


def model_catch(r):
    """FUN_68014f7b(fielder): 1 = clean catch. draw = mod(100); caught iff draw < chance; a miss with
    draw >= base is an error whose kind (0..4) comes from a second mod(100) against ERR_TYPE"""
    t, obj = Tape(r), r['obj']
    ret = r['ret'] & 0xff
    if not (t.x(0x68009740) & 0xff and t.x(0x6804efb5) & 0xff and not t.x(0x680155c0) & 0xff
            and t.x(0x6800f270) & 0xff):
        t.done()
        return None if ret == 1 else f'gate closed, ret {ret}'
    if not t.x(0x680099c0) & 0xff and not t.x(0x68002fb0) & 0xff:
        t.done()
        return None if ret == 1 else f'no-play gate, ret {ret}'
    add = t.pb(0x1cc)
    div = max(t.pb(0x1cd), 1)
    base = s16v(PB[CATCH_POS_PB[i32(obj, 100)]] + cdiv(obj[0x97], div) + add)
    if t.x(0x6802d4c0) & 0xff: chance = s16v(t.pb(0x1ce) + base)
    elif t.x(0x6802d47d) & 0xff: chance = s16v(t.pb(0x1cf) + base)
    else: chance = base
    if s32(t.x(0x680072f0)) < 10:
        a = t.pb(0x1d0)
        f = s16v(t.x(0x680072f0))
        chance = s16v((10 - f) * t.pb(0x1d1) + a + chance)
    if t.x(0x68015590) & 0xff:
        t.x(0x68008756, 0)
        return None if ret == 0 else f'no-draw path, ret {ret}'   # 68014e20 (unprobed) follows
    draw = s16v(t.mod(100))
    if draw < chance: want = 1
    else:
        kind = 0
        if base <= draw:
            if t.x(0x68009980) & 0xff: row = 3
            elif t.x(0x68009700) & 0xff: row = 0
            else: row = 2 if s32(t.x(0x68002d70)) < 0x1c3 else 1
            d2 = s16v(t.mod(100))
            while kind < 4 and ERR_TYPE[row][kind] <= d2: kind += 1
        if r['over']: return None if ret == 0 else f'missed draw {draw} >= {chance}, ret {ret}'
        t.x(0x68008756, kind)
        if kind: t.x(0x68007395)
        want = 0
        if draw >= base:
            # 68014e20 (unprobed, its events are top-level) then 68041cd5 ends the record
            last = [e for e in t.ev[t.i:] if chr(e[0]) == 'X']
            if not last or PROBES[last[-1][1]][0] != 0x68041cd5: return f'error path does not end in 68041cd5'
            t.i = len(t.ev)
    t.done()
    if ret != want: return f'catch {ret}, model {want} (draw {draw}, chance {chance}, base {base})'
    return None


def model_pitch(r):
    """FUN_6803122b core (after pitch selection 6803080a and the aim helpers): control and movement rolls, velocity
    roll, location scatter box, movement scale, and the failed-movement outcome. Pitch RNG = 68113d88 (gen 0)."""
    t = Tape(r)
    k = next((j for j, e in enumerate(t.ev) if chr(e[0]) == 'X' and PROBES[e[1]][0] == 0x6803e39f and e[4] == 1), None)
    if k is None or k == 0: raise Skip('no pitch execution in record')
    t.i = k - 1
    typ = t.ev[t.i][4]
    rating = s32(t.x(0x6803e377))                                       # pitch rating of the thrown type
    as_ = s32(t.x(0x6803e39f, 1))                                       # arm strength
    fat = t.take('F')[5]
    if fat == 3: rating = cdiv(rating * t.pb(0x268), 100); as_ = cdiv(as_ * t.pb(0x269), 100)
    elif fat == 4: rating = cdiv(rating * t.pb(0x26a), 100); as_ = cdiv(as_ * t.pb(0x26b), 100)
    co = cdiv(cdiv(s32(t.x(0x6803e39f, 2)) * rating, 100) * t.pb(0x26e), 100)
    miss_co = t.take('M', 0, 100)[5] - co
    mo = cdiv(cdiv(s32(t.x(0x6803e39f, 3)) * rating, 100) * t.pb(0x26f), 100)
    miss_mo = t.take('M', 0, 100)[5] - mo
    t.take('M', 1, PB[0x185 + 3 * typ], 'velocity roll')                 # 6802edfd: base + mod(range) + AS * pct / 100
    bx, by = PB[0x19c + 2 * typ], PB[0x19d + 2 * typ]
    if not miss_co < 1:
        inc = cdiv(miss_co * t.pb(0x270), 100)
        bx, by = s16v(bx + inc), s16v(by + inc)
    t.take('M', 0, bx, 'scatter x'); t.take('M', 0, by, 'scatter y')
    t.x(0x6800f220, s16v(mo))
    t.x(0x68005cc0, 99)
    t.x(0x6800a4a0)
    if not miss_mo < 1:
        out = 2
        if typ == 0: out = 0 if s32(t.take('M', 0, 100)[5]) < as_ * 2 - 100 else 2
        elif typ in (1, 2, 3, 4): out = 1 if t.take('C', 0, 50)[5] else 2
        elif typ == 6:
            d = t.take('M', 0, 100)[5]
            out = (1 if d < 50 else 2) if as_ < 50 else (0 if d < 33 else 1 if d < 66 else 2)
        if out == 0:
            t.pb(0x273); n = t.pb(0x272); t.take('M', 0, n, 'velocity loss'); t.pb(0x271)
        elif out == 1 and typ in (1, 2, 4): t.x(0x68005c40)
    nxt = t.ev[t.i] if t.i < len(t.ev) else None
    if nxt is not None and chr(nxt[0]) in 'MCRP' and not (chr(nxt[0]) == 'P' and nxt[2] in (385, 386)):
        return f'unmodelled event after the pitch roll: {fmt_ev(nxt)}'
    return None


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v >= 1 << 31 else v


def dll_data(va, n, dll=os.path.join(WORK, 'FastSim.dll')):
    """n bytes of FastSim.dll's .data section (VMA 0x6808c000, file offset 0x8aa00) at va, as shipped"""
    with open(dll, 'rb') as f:
        f.seek(0x8aa00 + va - 0x6808c000)
        return f.read(n)


LEAD_TAB = dll_data(0x68097570, 32)   # [row 0..3][mod 8] lead size; FastSim always uses row 0
HOLD_TAB = dll_data(0x68097590, 25)   # [runner byte 0x7d / 20][pitcher rating / 20] max lead without the sign


def model_lead(r):
    """FUN_680508a4(runner): the lead roll. lead = LEAD_TAB[0][mod 8]; without the manager's go sign (flag 0x40 at
    runner+0x74 clear) the runner keeps it only while lead < HOLD_TAB[..]; otherwise the manager flag 0x40 decides.
    No lead: byte 0x86 = -1. A lead sets state 0x82 = 3, 0x7e = 4 and the jump timer 0x87 = 4 - (rating >> 4) - lead
    + 400 / runner 0x105."""
    t, o = Tape(r), r['obj']
    lead = s8(LEAD_TAB[t.mod(8)])
    keep = True
    if t.x(0x680098e0, 0x40) & 0xff:
        rating = s32(t.x(0x68050ae0))
        if lead >= s8(HOLD_TAB[o[0x7d] // 20 * 5 + cdiv(rating, 20)]): keep = False
    if keep:
        t.x(0x68009610)
        keep = t.x(0x6800f270) & 0xff != 0
    if not keep: lead = -1
    timer = 0
    if lead > 0:
        t.x(0x68050b90)
        timer = 4 - (s32(t.x(0x68050ae0)) >> 4) - lead
        timer = s16v(s16v(timer) + s16v(cdiv(400, s32(t.x(0x6800f780)))))
    t.done()
    p = r['post']   # *(runner + 0x70) after the call
    if s8(p[0x16]) != lead: return f'lead {s8(p[0x16])}, model {lead}'
    if lead > 0 and (s16(p, 0x17) != timer or i32(p, 0x12) != 3 or i32(p, 0x0e) != 4):
        return f'jump timer {s16(p, 0x17)} state {i32(p, 0x12)}/{i32(p, 0x0e)}, model {timer} 3/4'
    if lead <= 0 and s16(p, 0x17) != 0: return f'jump timer {s16(p, 0x17)} without a lead'
    return None


def model_def_mgr(r):
    """FUN_680382d9(mgr): the defensive manager's per-pitch rolls into the flag word at mgr+0x3496: 1 charge 1st,
    1|4 charge 3rd, 0x20 pickoff, 0x40 pitchout, 0x200 intentional walk, 0x100 pitch around, 0x400 decided"""
    t = Tape(r)
    w = i32(r['xf'], 0) & 0xffff
    v3 = s32(t.x(0x6803cc73))
    t.x(0x68005ec0, 8); w &= ~8
    if v3 < 3:
        if t.x(0x68011570) & 0xff:
            t.x(0x68005ec0, 0x65); w &= ~0x65
        if t.x(0x68011570) & 0xff or v3 == 0:
            t.call('positioning')
            t.x(0x68035228)
        for side, bits in ((0, (1,)), (2, (1, 4))):
            v = t.pb(0x2e)
            v = cdiv(s16v(t.call('def_strategy', side)) * v, 100)
            if t.mod(100) < v:
                for b in bits: t.x(0x68002c40, b); w |= b
        if v3 == 0:
            for name, bit in (('pickoff', 0x20), ('pitchout', 0x40)):
                s = s16v(t.call(name))
                if t.mod(100) < s: t.x(0x68002c40, bit); w |= bit
            rec = t.x(0x680098e0, 0x400) & 0xff
            if rec != (1 if w & 0x400 == 0 else 0): return f'flag test 0x400: recorded {rec}, word {w:#x}'
            if rec:
                s = s16v(t.call('def_ratings'))
                if s > 0:
                    roll = s16v(t.mod(100))
                    if roll < cdiv(s * t.pb(0x2f), 100): t.x(0x68002c40, 0x200); w |= 0x200
                    elif roll < s: t.x(0x68002c40, 0x100); w |= 0x100
                t.x(0x68002c40, 0x400); w |= 0x400
    t.done()
    after = s16(r['post'], 0) & 0xffff
    if w & 0xffff != after: return f'flag word {after:#06x}, model {w & 0xffff:#06x}'
    return None


def model_def_strategy(r):
    """FUN_68036a52(mgr, side 0 = 1st / 2 = 3rd): infield charge chance (short), from PB0-6, two ratings at +0x83 and
    the sacrifice chance; zero in a lopsided game or without a bunt situation"""
    t = Tape(r)
    param_1 = r['arg']
    local_10 = 0
    bVar1 = t.x(0x68002c80) & 0xff
    iVar5 = t.x(0x68032ff0)
    iVar6 = t.x(0x6800f600)
    iVar7 = t.x(0x6800f640)
    bVar2 = t.x(0x68056985, 3) & 0xff
    bVar3 = t.x(0x68056985, 4) & 0xff
    skip = False
    diff = bVar2 - bVar3
    if diff > 1 or diff < -2:
        if (t.x(0x68049594) & 0xff) == 0:
            skip = True
    if not skip:
        if (((param_1 == 0) or (param_1 == 2)) and
                (((iVar6 != 0 and iVar7 == 0) or (iVar5 != 0 and iVar6 == 0))) and
                (bVar1 < 2)):
            if param_1 == 0:
                local_10 = s16v(t.pb(0))
            else:
                local_10 = s16v(t.pb(1))
            iVar10 = t.pb(2)
            uVar4 = t.x(0x68039140) & 0xffff
            iVar10 = cdiv(iVar10 * (0x32 - uVar4), 100)
            iVar11 = t.pb(3)
            uVar4 = t.x(0x68039140) & 0xffff
            iVar11 = cdiv(iVar11 * (uVar4 - 0x32), 100)
            uVar12 = t.call('sacrifice')
            uVar8 = t.pb(4)
            local_10 = s16v(local_10 + s16v(iVar10) + s16v(iVar11) + s16v(uVar12) + s16v(uVar8))
            if param_1 == 2:
                if (iVar5 != 0) and (iVar6 != 0):
                    local_10 = s16v(local_10 + s16v(t.pb(5)))
                if iVar7 != 0:
                    local_10 = s16v(local_10 + s16v(t.pb(6)))
    t.done()
    if r['ret'] & 0xffff != local_10 & 0xffff:
        return f'def_strategy {r["ret"] & 0xffff}, model {local_10 & 0xffff}'
    return None


def model_def_ratings(r):
    """FUN_680371f8(): pitch-around chance 0..100 (PB24-45): late, runner in scoring position with 1st open, close
    game; batter vs on-deck power/contact buckets (68038e70 power, 68038e50 contact, 68038b39 bucket), on-deck
    68038eb0, outs"""
    t = Tape(r)
    local_1c = 0
    inning = t.x(0x6800f200) & 0xff
    outs = t.x(0x68002c80) & 0xff
    runs_a = t.x(0x68056985) & 0xff
    runs_b = t.x(0x68056985) & 0xff
    run_diff = runs_a - runs_b
    on_1st = t.x(0x68032ff0)
    on_2nd = t.x(0x6800f600)
    on_3rd = t.x(0x6800f640)
    count = s16v(t.x(0x6800f570) & 0xffff)
    if t.pb(0x18) < inning and (on_2nd != 0 or on_3rd != 0) and on_1st == 0:
        b6 = t.x(0x68009610) & 0xff
        if (t.x(0x68049594) & 0xff) == 0:
            iVar13 = count + 2
            if -run_diff == iVar13 or -iVar13 < run_diff:
                if run_diff < 3:
                    local_1c = s16v(t.pb(0x19) & 0xffff)
                    v1 = t.x(0x68038e70)
                    v2 = t.x(0x68038e50)
                    v3 = t.x(0x68038e70)
                    v4 = t.x(0x68038e50)
                    s7 = s16v(v2 & 0xffff)
                    s8 = s16v(v4 & 0xffff)
                    s9 = s16v(t.x(0x68038b39, s16v(v1 & 0xffff)) & 0xffff)
                    s10 = s16v(t.x(0x68038b39, s7) & 0xffff)
                    s11 = s16v(t.x(0x68038b39, s16v(v3 & 0xffff)) & 0xffff)
                    s12 = s16v(t.x(0x68038b39, s8) & 0xffff)
                    if inning == 7 or inning == 8:
                        local_1c = s16v((local_1c + t.pb(0x1a)) & 0xffff)
                    elif inning > 8:
                        local_1c = s16v((local_1c + t.pb(0x1b)) & 0xffff)
                    d1 = s9 - s11
                    if d1 < 2:
                        if d1 == 1:
                            local_1c = s16v((local_1c + t.pb(0x1d)) & 0xffff)
                        elif s11 == s9:
                            if s16v(v3 & 0xffff) < s16v(v1 & 0xffff):
                                local_1c = s16v((local_1c + t.pb(0x1e)) & 0xffff)
                            else:
                                local_1c = s16v((local_1c + t.pb(0x1f)) & 0xffff)
                        elif d1 == -1:
                            local_1c = s16v((local_1c + t.pb(0x20)) & 0xffff)
                    else:
                        local_1c = s16v((local_1c + t.pb(0x1c)) & 0xffff)
                    if d1 < -1:
                        local_1c = s16v((local_1c + t.pb(0x21)) & 0xffff)
                    d2 = s10 - s12
                    if d2 < 2:
                        if d2 == 1:
                            local_1c = s16v((local_1c + t.pb(0x23)) & 0xffff)
                        elif s12 == s10 and s7 < s8:
                            if s8 < s7:
                                local_1c = s16v((local_1c + t.pb(0x24)) & 0xffff)
                            else:
                                local_1c = s16v((local_1c + t.pb(0x25)) & 0xffff)
                        elif d2 == -1:
                            local_1c = s16v((local_1c + t.pb(0x26)) & 0xffff)
                        elif d2 < -1:
                            local_1c = s16v((local_1c + t.pb(0x27)) & 0xffff)
                    else:
                        local_1c = s16v((local_1c + t.pb(0x22)) & 0xffff)
                    if s32(t.x(0x68038eb0)) <= t.pb(0x28):
                        local_1c = s16v((local_1c + t.pb(0x29)) & 0xffff)
                    if outs == 0:
                        local_1c = s16v((local_1c + t.pb(0x2a)) & 0xffff)
                    elif outs == 1:
                        local_1c = s16v((local_1c + t.pb(0x2b)) & 0xffff)
                    elif outs == 2:
                        local_1c = s16v((local_1c + t.pb(0x2c)) & 0xffff)
                    if on_2nd != 0 and on_3rd != 0:
                        local_1c = s16v((local_1c + t.pb(0x2d)) & 0xffff)
    t.done()
    want = min(max(local_1c, 0), 100)
    if (r['ret'] & 0xffff) != want:
        return f'def_ratings {r["ret"] & 0xffff}, model {want}'
    return None


def model_replace_p(r):
    """FUN_6804a357(team): is the starter done. Threshold PB174-182 by inning (+PB183 per extra inning, PB184 for
    side 0, PB185/186 by bullpen pitches) vs G stat 7 + 3 per inning + outs + 2 * own runs + 2 * late innings
    - 2 * opponent runs"""
    t = Tape(r)
    side = i32(r['xf'], 0)
    fld = i32(r['xf'], 4)

    inning = t.x(0x6800f200) & 0xff
    A = [None] + [t.pb(0xae + i) for i in range(9)]
    local_3c = A[min(max(inning, 1), 9)]
    if inning > 9:
        local_3c += t.pb(0xb7) * (inning - 9)
    if side == 0:
        local_3c += t.pb(0xb8)
    k = min(max(9 - inning, 1), 8)
    if fld < k * 0x32:
        local_3c += t.pb(0xb9)
    if k * 100 < fld:
        local_3c += t.pb(0xba)

    local_c = ((t.x(0x6800f200) & 0xff) - 1) * 3
    if (t.x(0x68020a50) & 0xff) == 0:
        if side == 1:
            local_c += t.x(0x68002c80) & 0xff
    elif side == 1:
        local_c += 3
    else:
        local_c += t.x(0x68002c80) & 0xff
    local_c += (t.x(0x68056985, side) & 0xff) * 2
    u5 = t.x(0x6800f200) & 0xff
    b1 = t.x(0x6800f200) & 0xff
    local_c += min(max(b1 - 4, 0), u5) * 2
    local_c += (t.x(0x68056985, int(side == 0)) & 0xff) * -2
    stat7 = t.stat('G', 7)
    t.done()
    want = int(stat7 + local_c < local_3c)
    if r['ret'] & 0xff != want:
        return f'replace_p ret {r["ret"] & 0xff}, model {want}'
    return None


def model_relief_chk(r):
    """FUN_6804a64d(team): is the reliever done: flagged (6804935e), stamina H3 - G10 - G11 below
    (K0x20 + 51) * PB187 / 100, or a lead within PB189..PB188 with status bit 0x10"""
    t = Tape(r)
    t.x(0x68041d83)
    t.x(0x68041d83)
    t.x(0x68041d83)
    h = t.stat('H', 3)
    g10 = t.stat('G', 10)
    g11 = t.stat('G', 11)
    k20 = t.stat('K', 0x20)
    pb_bb = t.pb(0xbb)
    thresh = cdiv(pb_bb * (k20 + 0x33), 100)
    flag = t.x(0x6804935e) & 0xff
    local_1c = (flag != 0) or (h - (g10 + g11) < thresh)
    side = i32(r['xf'], 0)
    other = int(side != 1)
    b3 = t.x(0x68056985, side) & 0xff
    b4 = t.x(0x68056985, other) & 0xff
    diff = b3 - b4
    pb_bc = t.pb(0xbc)
    if diff <= pb_bc:
        pb_bd = t.pb(0xbd)
        if pb_bd <= diff and (t.x(0x6803dec5, 0x10) & 0xff) != 0:
            local_1c = True
    t.done()
    want = int(local_1c)
    if r['ret'] & 0xff != want:
        return f'relief chk {r["ret"] & 0xff}, model {want}'
    return None


def model_relief_pick(r):
    """FUN_68043d91(team): the relief pick. The warming reliever (status bit 8) in slot 0x17328/0x1732c is chosen
    unless the current pitcher is fine (starter: not 6804a357, reliever: not 6804a64d; fatigue state <= 2; not ahead
    after the 7th; G stat 2 == 0). Checked through the index passed to 68041d33."""
    t = Tape(r)
    side = i32(r['xf'], 8)
    local_c = -1
    for k in range(2):
        v = i32(r['xf'], 4 * k)
        if v != -1 and (t.x(0x6803dec5, 8) & 0xff) != 0:
            local_c = v
    keep = True
    if (t.x(0x68049663) & 0xff) != 0:
        keep = (t.call('replace_p') & 0xff) == 0
    elif (t.call('relief_chk') & 0xff) != 0:
        keep = False
    t.x(0x68041d83)
    if t.fat() > 2:
        keep = False
    if (t.x(0x6800f200) & 0xff) > 7:
        runs_side = t.x(0x68056985, side) & 0xff
        runs_other = t.x(0x68056985, int(side != 1)) & 0xff
        if runs_other < runs_side:
            keep = False
    t.x(0x68041d83)
    if t.stat('G', 2) != 0:
        keep = False
    if keep:
        local_c = -1
    if local_c == -1:
        t.x(0x68041d83)
        t.x(0x68041d83)
        t.x(0x6803d9f9, 0)
        if t.peek() == 'H':
            t.stat('H', 0)
            if (t.x(0x68047c98) & 0xff) != 0:
                return None
    t.x(0x68041d33, local_c)
    t.done()
    return None


GOOD_POS_PB = [499, 500, 501, 502, 497, 498, 505, 504, 503]   # 6808e968[pos] goodThrowChance, set by catch_adj


def model_throw(r):
    """FUN_6805dd30(fielder, target fielder, target point): the throw. Distance is cut to (byte 0x98 * PB494 / 100 +
    PB493) * 30; a throw longer than 0x546 under manager flag 0x20 rolls chance(GOOD_POS[pos] + byte 0x97 * PB496 / 100
    + PB495) and on a miss lands range(150, 300) off at an angle range(-0x4000, 0x4000) from the target. Shorter than
    PB772 * 30: a lob (680153ed); else throw_speed(distance). Checked: the chance operand, both ranges and the distance
    passed to throw_speed."""
    t, o = Tape(r), r['obj']
    t.x(0x68002bf0)
    t.skip_to(0x6800a4a0)                       # vtable +0x1c: unprobed caller, its callees' events are top-level
    t.x(0x6800a4a0)
    dist = s16v(t.x(0x68002bb0))
    cap = (cdiv(o[0x98] * t.pb(0x1ee), 100) + t.pb(0x1ed)) * 30
    if cap < dist:
        dist = s16v(cap)
        t.x(0x6807c239)
        t.x(0x6800a4a0)
    t.x(0x6801e71c)
    if dist > 0x546 and not t.x(0x680155c0) & 0xff and t.x(0x6800f270, i32(o, 0x68)) & 0xff:
        fa = cdiv(o[0x97] * t.pb(0x1f0), 100)
        good = s16v(PB[GOOD_POS_PB[i32(o, 100)]] + fa + t.pb(0x1ef)) & 0xff
        c = t.take('C', 1, good, 'good throw chance')
        if not c[5]:
            e = t.take('R', 1, 0x96, 'wild throw distance')
            if e[4] != 300: return f'wild distance range hi {e[4]}'
            t.x(0x68002bf0)
            e = t.take('R', 1, -0x4000, 'wild throw angle')
            if e[4] != 0x4000: return f'wild angle range hi {e[4]}'
            t.x(0x68005be0)
            t.x(0x6807c239)
            dist = s16v(t.x(0x68002bb0))
            if t.peek() == 'X' and PROBES[t.ev[t.i][1]][0] == 0x6805dc50: t.x(0x6805dc50)
    if dist < t.pb(0x304) * 30:
        t.x(0x680153ed)
        t.skip_to(0x68026380, 0xd)              # vtable +0xc: the lob (inj_check, throw_speed and PB reads inside)
    else:
        e = t._next('Z', 'call of throw_speed')
        if NAMES[e[1]] != 'throw_speed': return f'record calls {NAMES[e[1]]}, model throw_speed'
        if s16v(e[4]) != dist: return f'throw_speed({s16v(e[4])}), model distance {dist}'
        t.skip_to(0x68009690)                   # past throw_speed's own events, inline once its record cap is hit
        t.x(0x68009690)
        t.skip_to(0x680030c0, 0x200)            # vtable +0x3c
        if t.x(0x680030c0, 0x200) & 0xff: t.x(0x68003fcb, 2)
    for k, v in ((0xd, 5), (0xc, 7)):
        if t.x(0x68026380, k): t.x(0x680249f4, v)
    t.x(0x68024af3, 0)
    t.done()
    return None


def check_rng(r):
    """main and injury RNG calls replay from the recorded state before the call; a nested target's draws are taken
    from its own record (its state before and after), and a record whose nested target was dropped is skipped once
    the replay can no longer be followed"""
    for gen, k0, k1 in ((1, 'rm0', 'rm1'), (2, 'ri0', 'ri1')):
        g, lost = Rng(r[k0]), False
        for j, (t, gg, idx, a, b, res) in enumerate(r['ev']):
            t = chr(t)
            if t == 'Z':
                k = r.get('kids', {}).get(j)
                if k is None: lost = True
                elif g.s != k[k0]:
                    if lost: return 'skip'
                    return f'gen {gen} state {g.s:#x} before nested {NAMES[k["fn"]]}, its record {k[k0]:#x}'
                else: g.s, lost = k[k1], False
                continue
            if gg != gen: continue
            if t == 'M': want = g.mod(a)
            elif t == 'R': want = g.range(a, b)
            elif t == 'C': want = int((g.next() & 0xfff) < a * 0x29)
            else: continue
            if want != (res & 0xffffffff if t == 'M' else res):
                if lost: return 'skip'
                return f'gen {gen} {t}({a}) replays {want}, got {res}'
        if g.s != r[k1]:
            if lost: return 'skip'
            return f'gen {gen} end state {g.s:#x} != {r[k1]:#x} (RNG used outside the probes)'
    return None


def dice(d, g, n_out):
    """FUN_6802ba8f: base + sum of `dice` rolls of mod(sides) + 1"""
    v = d['base']
    for _ in range(d['dice']):
        n_out.append(d['sides'])
        v = (v + g.mod(d['sides']) + 1) & 0xffff
    return v - 0x10000 if v >= 0x8000 else v


def model_inj_check(r):
    n = PB[0x354 + r['arg']]
    m = ev_of(r, 'M')
    if [e[3] for e in m] != [n] or m[0][1] != 2: return f'expected one injury mod({n}), got {[fmt_ev(e) for e in m]}'
    want = int(Rng(r['ri0']).mod(n) == 0)
    if (r['ret'] & 0xff) != want: return f'injured {r["ret"] & 0xff}, model {want}'
    return None


def model_inj_type(r):
    """FUN_6802be53: draw = main.mod(999) + 1; the first table entry with threshold >= draw names the injury"""
    g, ns = Rng(r['rm0']), []
    draw = g.mod(999) + 1
    ns.append(999)
    tab = INJ['categories'][r['arg']]
    hit = next((e for e in tab if e['threshold'] >= draw), None)
    if hit is None: return f'draw {draw} past the table (game asserts)'
    num = hit['injury']
    inj = INJ['injuries'][num - 1]
    du = INJ['durations'][inj['duration'] - 1]
    days = dice(du['roll'], g, ns)
    if days < du['reroll_below']: days = dice(du['reroll'], g, ns)
    after = dice(INJ['after_rolls'][inj['after_roll'] - 1], g, ns)
    got_ns = [e[3] for e in ev_of(r, 'M')]
    if got_ns != ns: return f'mod sequence {got_ns} != model {ns}'
    got = (s16(r['post'], 0), s16(r['post'], 2), s16(r['post'], 4))
    if got != (num, days, after): return f'(injury, days, after) {got} != model {(num, days, after)}'
    return None


def pitcher_slot(team_head, pid):
    """FUN_680497de over the first 40 ints of the team object"""
    if pid:
        for i in range(40):
            if i32(team_head, 4 * i) == pid: return i
    return -1


def model_stamina(r):
    """FUN_680491d4(team, pitcher id) -> percent of stamina left"""
    slot = pitcher_slot(r['obj'], r['arg'])
    for x in xev(r, 0x680497de):   # the slot lookup, when probed
        if x[5] != slot & 0xffffffff and x[5] != slot: return f'slot lookup {x[5]}, model {slot}'
    vals = [(chr(e[0]), e[2], e[5]) for e in r['ev'] if chr(e[0]) in 'GHK']
    if not vals: return None if (r['ret'] == 0 if slot == -1 else r['ret'] in (0, 100)) else f'no reads, ret {r["ret"]}'
    if slot == -1: return f'slot -1 but reads happened'
    want_keys = [('H', 3), ('G', 10), ('G', 11), ('K', 32), ('G', 3)]
    if [v[:2] for v in vals[:5]] != want_keys: return f'read order {vals}'
    stam, used1, used2, extra, g3 = (v[2] for v in vals[:5])
    cap = extra + 0x33
    v = min(max(stam - (used1 + used2), 0), cap)
    left = cdiv(v * 100, cap)
    if g3 != 0 and len(vals) > 5:   # current pitcher (team +0x172c4 == slot): scaled by stat4 / stat3 when below
        g3b, g4 = vals[5][2], vals[6][2]
        if g4 < g3b:
            left = cdiv(vals[7][2] * left, vals[8][2])
    if r['ret'] != left & 0xffffffff: return f'stamina {r["ret"]} != model {left} from {vals}'
    return None


def model_fatigue(r, stamina_ret):
    """FUN_68049d61(team, slot): sets the fatigue level 0..4 of the pitcher in `slot`"""
    g = {}
    seq = []
    for e in r['ev']:
        t = chr(e[0])
        if t == 'G': seq.append(('G', e[2], e[5]))
        elif t == 'P': seq.append(('P', e[2], e[5]))
        elif t == 'W': seq.append(('W', e[2]))
    gets = [x for x in seq if x[0] == 'G']
    s3, s4 = gets[0][2], gets[1][2]
    if s4 < cdiv(s3, 2): want = 0
    elif s4 < s3: want = 1
    elif PB[0xac] < stamina_ret: want = 2
    elif PB[0xad] < stamina_ret: want = 3
    else: want = 4
    pbs = [x for x in seq if x[0] == 'P']
    for x in pbs:
        if x[2] != PB[x[1]]: return f'PB[{x[1]}] read {x[2]}, table {PB[x[1]]}'
    w = [x for x in seq if x[0] == 'W']
    if len(w) != 1 or w[0][1] != want: return f'level set {w}, model {want} (stat3 {s3}, stat4 {s4}, stamina {stamina_ret})'
    return None


V2_MODELS = ('def_mgr', 'def_strategy', 'def_ratings', 'replace_p', 'relief_chk', 'relief_pick', 'throw')


def guard(fn, r):
    try:
        return fn(r)
    except Mismatch as e:
        return str(e)
    except Skip:
        return 'skip'


def link(r, pending):
    """attach r's nested target records (written just before it, one level deeper) to its Z events, matched by
    (target, this, arg) from the end so records orphaned by a capped caller are left out"""
    kids = pending.pop(r['depth'] + 1, [])
    zs = [i for i, e in enumerate(r['ev']) if chr(e[0]) == 'Z']
    r['kids'] = {}
    for zi in reversed(zs):
        e = r['ev'][zi]
        while kids and (kids[-1]['fn'], kids[-1]['self'], kids[-1]['arg']) != (e[1], e[3] & 0xffffffff, e[4] & 0xffffffff):
            kids.pop()
        if kids: r['kids'][zi] = kids.pop()
    if r['depth']: pending.setdefault(r['depth'], []).append(r)


def main():
    res = collections.defaultdict(collections.Counter)
    bad = collections.defaultdict(list)
    prev = None
    n = 0

    def note(name, err, r):
        if err == 'skip': res[name]['skipped (nested record dropped)'] += 1; return
        res[name]['ok' if err is None else 'bad'] += 1
        if err is not None and len(bad[name]) < 5: bad[name].append((r['i'], err))

    for path in sys.argv[1:]:
        pending = {}
        for r in records(path):
            n += 1
            link(r, pending)
            if r['over']: res['rng']['skipped (event overflow)'] += 1
            else: note('rng', check_rng(r), r)
            f = NAMES[r['fn']]
            if f == 'offman' and not r['over']: note('offman', guard(model_offman, r), r)
            if f == 'squeeze' and not r['over']: note('squeeze', guard(model_squeeze, r), r)
            if f == 'pickoff' and not r['over']: note('pickoff', guard(model_pickoff, r), r)
            if f == 'pitchout' and not r['over']: note('pitchout', guard(model_pitchout, r), r)
            if f == 'hit_run' and not r['over']: note('hit_run', guard(model_hit_run, r), r)
            if f == 'sacrifice' and not r['over']: note('sacrifice', guard(model_sacrifice, r), r)
            if f == 'pitch' and not r['over']: note(f, guard(model_pitch, r), r)
            if f in ('catch', 'catch_adj'): note(f, guard(globals()['model_' + f], r), r)
            if f == 'steal' and not r['over']: note('steal', guard(model_steal, r), r)
            if f == 'lead' and not r['over']: note('lead', guard(model_lead, r), r)
            if f in V2_MODELS and not r['over'] and 'model_' + f in globals():
                note(f, guard(globals()['model_' + f], r), r)
            if f == 'inj_check': note('inj_check', model_inj_check(r), r)
            elif f == 'inj_type': note('inj_type', model_inj_type(r), r)
            elif f == 'stamina': note('stamina', model_stamina(r), r)
            elif f == 'fatigue':
                if prev and NAMES[prev['fn']] == 'stamina' and prev['depth'] == r['depth'] + 1 and prev['rm0'] == r['rm0']:
                    note('fatigue', model_fatigue(r, prev['ret']), r)
                else: res['fatigue']['skipped (nested stamina not recorded)'] += 1
            prev = r
    print(f'records {n}')
    fail = False
    for k, c in res.items():
        print(f'  {k:10s} ' + ', '.join(f'{a} {b}' for a, b in c.items()))
        for i, e in bad[k]: print(f'      #{i}: {e}')
        fail |= c['bad'] > 0
    print('FAIL' if fail else 'PASS')
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
