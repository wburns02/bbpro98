"""Replay model of FastSim FUN_6804faa1 (runner AI update, `this` = the runner AI object, anim sub-object at this+8).

Object layout used (offsets from this): +0x0c u16 anim flags, +0x0e anim state id, +0x12 anim table ptr, +0x18 anim frame,
+0x64/+0x66 s16 offsets, +0x74 u16 AI flags, +0x76 u16 AI flags 2, +0x78 u8 countdown, +0x79 i32 mode (2/3/4),
+0x7d u8, +0x7e i32 step, +0x82 i32 step limit, +0x86 i8, +0x87 s16 delay.

Unprobed callees (no events): the runner-object attribute readers 68050ae0 (+0x93), 68050b30 (+0xdb); the animation
table (frame counts) is loaded at run time and is not in the record, see anim_update().
"""
import struct
from t3lib import cdiv, s16v

X_ONCLOSE = 0x6800f8f0   # tests a flag; AL is the verdict
X_STATE = 0x6800a260     # anim state id
X_FLAG = 0x680030c0      # (flags & arg)
X_SET = 0x68002c40       # flags |= arg
X_CLR = 0x68005ec0       # flags &= ~arg
X_PT = 0x68002ce0        # point constructor (0, 0)
X_RUN2 = 0x6800f600      # runner on 2B
X_RUN3 = 0x6800f640      # runner on 3B
X_STEP = 0x68038e30      # runner +0x7e
X_BOOL = 0x68009610
X_MFLAG = 0x6800f270
X_AIFLAG = 0x68009a20
X_F33F70 = 0x68033f70    # flag 4 of anim
X_F320 = 0x6800f320      # flag 8 of anim
X_F2F0 = 0x6800f2f0      # flag 1 of anim
X_MODE56 = 0x68050b50
X_F680 = 0x6800f680
X_F780 = 0x6800f780      # the IsTracking that is probed (divisor of the 400/x term)
X_TBL = 0x6802fc40


def w32(v):
    v &= 0xffffffff
    return v - 0x100000000 if v >= 0x80000000 else v


def t(v):
    """a bool/char/uint8 verdict: only the low byte counts (uVar & 0xff)"""
    return (v & 0xff) != 0


def replay(o, r):
    x = o.x
    ob = bytearray(r['obj'])

    def gi(off): return struct.unpack_from('<i', ob, off)[0]
    def si(off, v): struct.pack_into('<i', ob, off, v & 0xffffffff)
    def gs(off): return struct.unpack_from('<h', ob, off)[0]
    def ss(off, v): struct.pack_into('<h', ob, off, s16v(v))
    def gu(off): return ob[off]

    # LFSR used by FUN_68082999(&DAT_680a64b0, n); consumed at most once per call
    rng = [r.get('rm0', 0) & 0xffffffff]

    def rand(n):
        s = rng[0]
        s2 = s >> 1
        if s & 1: s2 ^= 0xa3000000
        rng[0] = s2
        return 0 if n < 2 else s2 % n

    # ---- FUN_6802a6b1 (start an animation) -------------------------------------------------------------------
    def anim_start(ident, f3, f5):
        # args evaluated by the caller: FUN_68002ce0(local, 0, 0) first
        if ident < 0x40:
            x(X_SET, f3)          # flags |= param_3 (after the flags word is cleared)
            x(X_FLAG, 1)          # the reverse-play flag; the start frame only matters to the next call

    def point_then_start(ident, f3, f5):
        x(X_PT, 0)
        anim_start(ident, f3, f5)

    # ---- FUN_6802a8b7 (animation frame advance) ----------------------------------------------------------------
    def anim_update():
        if t(x(X_FLAG, 0x100)):
            return
        if struct.unpack_from('<I', ob, 0x12)[0] == 0:
            return
        if t(x(X_FLAG, 4)):
            return
        frame = struct.unpack_from('<H', ob, 0x18)[0]
        if not t(x(X_FLAG, 1)):
            # forward play: frame < count - 1 where count is the first word of the anim table entry (run-time data,
            # not in the record); the animation is assumed not to be on its last frame
            pass
        elif frame == 0:
            if not t(x(X_FLAG, 0x20)):
                if not t(x(X_FLAG, 2)):
                    x(X_SET, 8)
            else:
                x(X_CLR, 0x20)
                x(X_SET, 4)
        if t(x(X_FLAG, 8)):
            x(X_PT, 0)            # FUN_6802aa9f resets the anim object

    # =========================================================================================================
    if not t(x(X_ONCLOSE)):
        return
    cur = x(X_STATE)
    anim_update()

    mode = gi(0x79)
    if mode == 2:
        ident, nxt = 0x30, 0x33
        v = x(X_RUN2)
        if v == 0:
            go = True
        else:
            v = x(X_RUN2)
            go = x(X_STEP) == 4
        d14, d20 = -9, 9
    elif mode == 3:
        ident, nxt = 0x31, 0x34
        v = x(X_RUN3)
        if v == 0:
            go = True
        else:
            v = x(X_RUN3)
            go = x(X_STEP) == 4
        d14, d20 = -0xf, -0xf
    elif mode == 4:
        ident, nxt = 0x32, 0x35
        go = True
        d14, d20 = 9, -9
    else:
        return

    b = x(X_BOOL)
    if not t(x(X_MFLAG, b)):
        go = False
    if t(x(X_AIFLAG, 0x608)):
        si(0x82, 3)

    def runner_f780():
        # the divisor z of "[0x87] = 4 - (a >> 4) - b + 400 / z"; a, b come from the unprobed readers 68050ae0 and
        # 68050b30, and [0x87] is not read again in this call
        return x(X_F780)

    if cur in (0x30, 0x31, 0x32):
        if not t(x(X_F33F70)):
            if not t(x(X_F320)):
                if not t(x(X_F2F0)):
                    ss(0x64, gs(0x64) + d14)
                    ss(0x66, gs(0x66) + d20)
                else:
                    ss(0x64, gs(0x64) - d14)
                    ss(0x66, gs(0x66) - d20)
            else:
                if t(x(X_F2F0)):
                    si(0x7e, gi(0x7e) - 1)
                point_then_start(ident, 4, 0)
                x(X_CLR, 3)
        else:
            # the unprobed readers: IsTracking(local_10) vs the byte at +0x86 is taken as "different" (the reader is an
            # attribute of a player object that is not in the record)
            neq = True
            cond = (not go) or gi(0x7e) != 3
            if not cond:
                a = neq and (not t(x(X_FLAG, 0x200)) or runner_f780() == 0)
                if a:
                    if not t(x(X_AIFLAG, 0x408)) or not t(x(X_FLAG, 4)):
                        cond = True
            if cond:
                if not t(x(X_FLAG, 0x20)):
                    if not t(x(X_FLAG, 0x10)):
                        if not t(x(X_FLAG, 1)):
                            if not t(x(X_FLAG, 2)):
                                if t(x(X_FLAG, 0x80)):
                                    c = gu(0x78)
                                    ob[0x78] = (c - 1) & 0xff
                                    if c == 0:
                                        ob[0x78] = rand(5)
                                        if gi(0x7e) < 3:
                                            si(0x7e, gi(0x7e) + 1)
                                            point_then_start(ident, 0, 0)
                                        else:
                                            x(X_CLR, 0x80)
                            elif gi(0x7e) < 1:
                                x(X_CLR, 2)
                            else:
                                point_then_start(ident, 1, 0)
                        elif gi(0x7e) < 3:
                            si(0x7e, gi(0x7e) + 1)
                            point_then_start(ident, 0, 0)
                        else:
                            if not t(x(X_MODE56)) or not go:
                                x(X_CLR, 1)
                            else:
                                if runner_f780() == 0:
                                    if mode == 3 or (mode == 2 and x(X_F680) == 0) or (mode == 4 and x(X_F680) == 1):
                                        ss(0x87, 2)
                                    else:
                                        ss(0x87, 1)
                                else:
                                    runner_f780()
                                si(0x7e, gi(0x7e) + 1)
                                point_then_start(nxt, 0, 0)
                    else:
                        c = gu(0x78)
                        ob[0x78] = (c - 1) & 0xff
                        if c == 0:
                            ob[0x78] = rand(5)
                            if gi(0x7e) < gi(0x82):
                                si(0x7e, gi(0x7e) + 1)
                                point_then_start(ident, 0, 0)
                            else:
                                x(X_SET, 1)      # FUN_68002c40(this + 0x76, 1)
                                x(X_CLR, 0x10)
                else:
                    x(X_CLR, 0x91)
                    if gi(0x7e) < 1:
                        x(X_CLR, 0x20)
                    else:
                        point_then_start(ident, 1, 0)
            else:
                runner_f780()
                si(0x7e, gi(0x7e) + 1)
                point_then_start(nxt, 0, 0)
    elif cur in (0x33, 0x34, 0x35):
        x(X_CLR, 0x81)
        if t(x(X_F320)):
            point_then_start(nxt, 0, 3)
        b = x(X_BOOL)
        k = x(X_TBL, b)
        if k >= 0x80000000: k -= 0x100000000
        a = cdiv(w32(d14 * 2 * k), 100)
        c = cdiv(w32(d20 * 2 * k), 100)
        if a == 0: a = -1 if d14 < 1 else 1
        if c == 0: c = -1 if d20 < 1 else 1
        ss(0x64, gs(0x64) + a)
        ss(0x66, gs(0x66) + c)
    elif cur == 0x41:
        point_then_start(ident, 4, 0)
