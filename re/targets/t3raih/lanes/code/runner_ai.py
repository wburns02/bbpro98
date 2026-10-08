"""Replay model of FastSim FUN_6804faa1, the runner AI update (simtrace target runner_ai).

The function works on the runner object P (this = P). Its own fields are kept in a copy of r['obj'] (the first 0x100
bytes of *this before the call) and updated as the code writes them. Every probed getter it calls is one o.x(va, arg1)
(the getter's own return, nested calls hidden), in the order the code makes them; the RNG mod(5) is one
o.other('M', 0, 5). Helpers that are not probed (FUN_6802a8b7, FUN_6802a6b1, FUN_6802aa9f) are modelled inline, so
their probed calls appear here in order.

Offsets are P-relative. The sub-object the helpers take as this is P+8 (P8 in the decompile).
"""
import struct
import t3lib

TAB = 0x680d3f28   # DAT_680d3f28: 64 eight-byte action entries, indexed by action code; the first word of each entry
# is its count, read from HHA.DAT (magic 0x6969, then the entries at offset 2 + 8 * code)
COUNT = [1, 3, 1, 19, 10, 16, 1, 12, 4, 4, 9, 7, 1, 12, 10, 16, 1, 12, 3, 3, 1, 4, 2, 2, 2, 2, 12, 2, 2, 1, 7, 7, 8,
         8, 8, 7, 14, 18, 17, 8, 8, 8, 8, 1, 12, 1, 11, 11, 7, 7, 7, 10, 7, 10, 10, 10, 10, 7, 8, 4, 4, 4, 1, 1]


def bit(v):
    """a getter's return, as the code tests it (its low byte)"""
    return (v & 0xff) != 0


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


def count_of(ptr):
    """FUN_6802b420: the first word of the table entry at ptr"""
    i = (ptr - TAB) // 8
    return COUNT[i] if 0 <= i < len(COUNT) else 0


class Runner:
    """*this of the runner: its first 0x100 bytes as the function leaves them"""

    def __init__(self, b):
        self.b = bytearray(b)

    def u16(self, off): return struct.unpack_from('<H', self.b, off)[0]
    def s16(self, off): return struct.unpack_from('<h', self.b, off)[0]
    def i32(self, off): return struct.unpack_from('<i', self.b, off)[0]
    def u32(self, off): return struct.unpack_from('<I', self.b, off)[0]
    def s8(self, off): return t3lib.s8(self.b[off])
    def u8(self, off): return self.b[off]

    def put8(self, off, v): self.b[off] = v & 0xff
    def put16(self, off, v): struct.pack_into('<H', self.b, off, v & 0xffff)
    def put32(self, off, v): struct.pack_into('<I', self.b, off, v & 0xffffffff)
    def add16(self, off, v): self.put16(off, self.s16(off) + v)


def set_action(o, P, code, p3, p4, p5):
    """FUN_6802a6b1 on P+8: the action code, its table entry, the flags word (probe 68002c40 with p3) and the step
    counter p5, or the entry's count - 1 when p5 is 0 and the flags' bit 1 is clear"""
    if code >= 0x40: return
    P.put32(0x0e, code)
    P.put32(0x12, TAB + code * 8)
    P.put16(0x16, 0)
    o.x(0x68002c40, p3)
    P.put32(0x1a, p4)
    if not bit(o.x(0x680030c0, 1)) or p5 != 0:
        P.put16(0x18, p5)
    else:
        P.put16(0x18, count_of(TAB + code * 8) - 1)


def reset_action(o, P):
    """FUN_6802aa9f on P+8: back to action 0x41 with no table entry"""
    P.put32(0x0e, 0x41)
    P.put32(0x12, 0)
    P.put16(0x16, 0)
    P.put16(0x18, 0)
    P.put32(0x1a, o.x(0x68002ce0, 0))


def advance_step(o, P):
    """FUN_6802a8b7 on P+8: steps the step counter P+0x18 through the action's entry (count from the table at P+0x12),
    then resets the action when the flags' bit 8 is set"""
    if bit(o.x(0x680030c0, 0x100)): return
    if P.u32(0x12) == 0: return
    if bit(o.x(0x680030c0, 4)): return
    if not bit(o.x(0x680030c0, 1)):
        n = count_of(P.u32(0x12))
        if P.u16(0x18) < n - 1:
            P.add16(0x18, 1)
        elif not bit(o.x(0x680030c0, 0x20)):
            if not bit(o.x(0x680030c0, 2)): o.x(0x68002c40, 8)
            else: P.put16(0x18, 0)
        else:
            o.x(0x68005ec0, 0x20)
            o.x(0x68002c40, 4)
    elif P.s16(0x18) == 0:
        if not bit(o.x(0x680030c0, 0x20)):
            if not bit(o.x(0x680030c0, 2)): o.x(0x68002c40, 8)
            else: P.put16(0x18, count_of(P.u32(0x12)) - 1)
        else:
            o.x(0x68005ec0, 0x20)
            o.x(0x68002c40, 4)
    else:
        P.add16(0x18, -1)
    if bit(o.x(0x680030c0, 8)): reset_action(o, P)


def tracking_step(o, P):
    """the jump timer P+0x87 from CSplitterWnd::IsTracking (probe 6800f780, three reads)"""
    v = t3lib.s16v(4 - t3lib.s16v(s32(o.x(0x6800f780)) >> 4))
    v = t3lib.s16v(v - t3lib.s16v(s32(o.x(0x6800f780))))
    q = s32(o.x(0x6800f780))
    P.put16(0x87, t3lib.s16v((t3lib.cdiv(400, q) if q else 0) + v))


def rng5(o):
    """FUN_68082999(&DAT_680a64b0, 5): the RNG mod, one 'M' event"""
    return o.other('M', 0, 5)[3] & 0xff


def bcond(o, P, local_8):
    """the 'else if' test of the 0x30-0x32 case: not (the tracking arm's test); reads its getters in code order"""
    if local_8 == 0: return True
    if P.i32(0x7e) != 3: return True
    if s32(o.x(0x6800f780)) == P.s8(0x86): return False
    if bit(o.x(0x680030c0, 0x200)) and s32(o.x(0x6800f780)) != 0: return False
    if bit(o.x(0x68009a20, 0x408)) and bit(o.x(0x6800f8f0)): return False
    return True


def flags_chain(o, P, t, tc, local_8):
    """the flag-driven step of the 0x30-0x32 case: t = the action code (local_18), tc = the code of the tracking arm
    (local_c)"""
    if bit(o.x(0x680030c0, 0x20)):
        o.x(0x68005ec0, 0x91)
        if P.i32(0x7e) < 1: o.x(0x68005ec0, 0x20)
        else: set_action(o, P, t, 1, o.x(0x68002ce0, 0), 0)
        return
    if bit(o.x(0x680030c0, 0x10)):
        c = P.u8(0x78)
        P.put8(0x78, c - 1)
        if c == 0:
            P.put8(0x78, rng5(o))
            if P.i32(0x7e) < P.i32(0x82):
                P.put32(0x7e, P.i32(0x7e) + 1)
                set_action(o, P, t, 0, o.x(0x68002ce0, 0), 0)
            else:
                o.x(0x68002c40, 1)
                o.x(0x68005ec0, 0x10)
        return
    if bit(o.x(0x680030c0, 1)):
        if P.i32(0x7e) < 3:
            P.put32(0x7e, P.i32(0x7e) + 1)
            set_action(o, P, t, 0, o.x(0x68002ce0, 0), 0)
            return
        if not bit(o.x(0x68050b50)) or local_8 == 0:
            o.x(0x68005ec0, 1)
            return
        if s32(o.x(0x6800f780)) == 0:
            P.put16(0x87, 1)
            st = P.i32(0x79)
            if st == 3 or (st == 2 and o.x(0x6800f680) == 0) or (st == 4 and o.x(0x6800f680) == 1):
                P.add16(0x87, 1)
        else:
            tracking_step(o, P)
        P.put32(0x7e, P.i32(0x7e) + 1)
        set_action(o, P, tc, 0, o.x(0x68002ce0, 0), 0)
        return
    if bit(o.x(0x680030c0, 2)):
        if P.i32(0x7e) < 1: o.x(0x68005ec0, 2)
        else: set_action(o, P, t, 1, o.x(0x68002ce0, 0), 0)
        return
    if bit(o.x(0x680030c0, 0x80)):
        c = P.u8(0x78)
        P.put8(0x78, c - 1)
        if c == 0:
            P.put8(0x78, rng5(o))
            if P.i32(0x7e) < 3:
                P.put32(0x7e, P.i32(0x7e) + 1)
                set_action(o, P, t, 0, o.x(0x68002ce0, 0), 0)
            else:
                o.x(0x68005ec0, 0x80)


def replay(o, r):
    P = Runner(r['obj'])
    if not bit(o.x(0x6800f8f0)): return                        # OnClose gate (CWnd 0x680a2158 flag bit 2)
    act = o.x(0x6800a260)                                      # action code (P+0xe)
    advance_step(o, P)
    st = P.i32(0x79)
    if st not in (2, 3, 4): return
    if st == 4:
        t, tc, local_8, l14, l20 = 0x32, 0x35, 1, 9, -9
    else:
        t, tc = (0x31, 0x34) if st == 3 else (0x30, 0x33)
        l14, l20 = (-0xf, -0xf) if st == 3 else (-9, 9)
        local_8 = 1
        v = o.x(0x6800f640 if st == 3 else 0x6800f600)
        if v != 0:
            o.x(0x6800f640 if st == 3 else 0x6800f600)
            local_8 = 1 if o.x(0x68038e30) == 4 else 0
    bv = o.x(0x68009610) & 0xff                                # bVar1: the 0x68143ee0 test, its index for the mflags reads
    if not bit(o.x(0x6800f270, bv)): local_8 = 0
    if bit(o.x(0x68009a20, 0x608)): P.put32(0x82, 3)
    if act in (0x30, 0x31, 0x32):
        if not bit(o.x(0x68033f70)):
            if not bit(o.x(0x6800f320)):
                if not bit(o.x(0x6800f2f0)):
                    P.add16(0x64, l14)
                    P.add16(0x66, l20)
                else:
                    P.add16(0x64, -l14)
                    P.add16(0x66, -l20)
            else:
                if bit(o.x(0x6800f2f0)): P.put32(0x7e, P.i32(0x7e) - 1)
                set_action(o, P, t, 4, o.x(0x68002ce0, 0), 0)
                o.x(0x68005ec0, 3)
        elif bcond(o, P, local_8):
            flags_chain(o, P, t, tc, local_8)
        else:
            tracking_step(o, P)
            P.put32(0x7e, P.i32(0x7e) + 1)
            set_action(o, P, tc, 0, o.x(0x68002ce0, 0), 0)
    elif act in (0x33, 0x34, 0x35):
        o.x(0x68005ec0, 0x81)
        if bit(o.x(0x6800f320)):
            set_action(o, P, tc, 0, o.x(0x68002ce0, 0), 3)
        bv = o.x(0x68009610) & 0xff
        l24 = s32(o.x(0x6802fc40, bv))
        l28 = t3lib.cdiv(s32(l24 * (l14 * 2)), 100)
        l2c = t3lib.cdiv(s32(l24 * (l20 * 2)), 100)
        if l28 == 0: l28 = -1 if l14 < 1 else 1
        if l2c == 0: l2c = -1 if l20 < 1 else 1
        P.add16(0x64, l28)
        P.add16(0x66, l2c)
    elif act == 0x41:
        set_action(o, P, t, 4, o.x(0x68002ce0, 0), 0)
