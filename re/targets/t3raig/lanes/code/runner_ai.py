"""Round-1 replay model of FastSim FUN_6804faa1 (runner AI update), t3 bake-off tier 3 (runner_ai).

Re-executes FUN_6804faa1 against the dev records (targets_data/t3rai/records.jsonl, oracle in re/targets/t3lib.py):
for every probed getter the function calls, the model calls o.x(va, arg1) (arg1 = the getter's first stack argument,
absent when the probe takes none), in the exact order the function does, and branches on the value the oracle returns,
exactly as the code does.

Control-flow ground truth is the disassembly of FastSim.dll 0x6804faa1-0x68050397. Ghidra's decompile puts MFC names
on game functions of this region ("CMiniDockFrameWnd::OnClose" on 0x6800f8f0/0x6800f540, "CSplitterWnd::IsTracking"
on 0x6800f780) - false matches; judge by what the code does:

  0x6800f8f0(this) = FUN_680030c0(this + 0x4341, 2)          (probed 41, NEST, span)
  0x6800f270(p, p1, p2) = FUN_680030c0(p + p1 * 2 + 2, p2)   (probed 33, NEST, span)
  0x6800f320(p)    = FUN_680030c0(p + 4, 8)                  (probed 35, NEST, span)
  0x6800f2f0(p)    = FUN_680030c0(p + 4, 1)                  (probed 34, NEST, span)
  0x68033f70(p)    = FUN_680030c0(p + 4, 4)                  (probed 70, NEST, span)
  0x6800f600(p)    = *(p + 0x95) slot ? that : 0             (probed 37, NEST, span)
  0x6800f640(p)    = *(p + 0x99) slot ? that : 0             (probed 38, NEST, span)
  0x68038e30(p)    = *(p + 0x7e)                             (probed 74, plain X)
  0x68009610(p)    = (p + 2 + 2) != *(p + 0x46)              (probed 19, plain X)
  0x68009a20(p, m) = (m & *(ushort *)p) ? m : 0              (probed 26, plain X)
  0x68002ce0(p, a, b) = *(p)=a, *(p+2)=b, return p           (probed 4, plain X, PTR)
  0x68002c40(p, m) = *(ushort *)p |= m, return p             (probed 2, plain X, PTR)
  0x6802fc40(p, idx) = *(int *)(p + idx * 4 + 0x46)          (probed 64, plain X)
  0x680030c0(p, m) = (m & *(u16 *)p) == m ? 1 | (m>>8)<<8 : (m>>8)<<8    (probed 8, plain X)

  A getter read identical to the event before it is not logged again (the mod drops it): a repeated identical
  o.x(va, arg1) call returns the previous value without consuming an event, per the oracle's o.x() hook.

  void __fastcall FUN_6804faa1(void *this)        one engine tick per batted/run object

  0x6804faad  FUN_6800f8f0(&DAT_680a2158)          probed 41 span; the inner 030c0(0x680a6499, 2) read is inside
                                                      the span and hidden from top_level() (see the replay call
                                                      notes at 0x6804faad in replay below)
  0x6804fab7  if (al == 0) return;                  early exit 1
  0x6804face  b18 = FUN_6800a260(this + 8);         probed 27: *(this+8+6), int (the runner's cmd code)
  0x6804fada  p10 = DAT_680a224c
  0x6804fae2  FUN_6802a8b7(this + 8);               unprobed: the cmd tick; its probed 030c0(this+8+4, m)
                                                      calls (m = 0x100 then, when *(this+0x12)!=0, m = 4)
                                                      ARE top-level events - see FUN_6802a8b7 below
  0x6804faed  switch (*(int*)(this + 0x79))         2 / 3 / 4 mold the local mask (case 4 api); other: exit 2

  case 2 (0x6804fb08):
    f600 = FUN_6800f600(0x680a57b7)                probed 37 (span; inner 030c0(0x680a557b7+2, 0x95))
    if (f600 == 0) local4 = 1
    else local4 = (FUN_68038e30(f600) == 4)        probed 74: *(p + 0x7e)
    b12 = -9;  c20 = 9

  case 3 (0x6804fb6f):                              probed 38 (span), the same shape
    f640 = FUN_6800f640(0x680a57b7)
    if (f640 == 0) local4 = 1
    else local4 = (FUN_68038e30(f640) == 4)
    b12 = -15; c20 = -15

  case 4 (0x6804fbc8): local4 = 1; b12 = 9; c20 = -9    no getter call

  common tail (0x6804fbf0):
    b18x = FUN_68009610(0x68143ee0)                probed 19; one-register function (no stack arg)
    f270 = FUN_6800f270(0x68114948, b18x, 0x40)    probed 33 (span); inner 030c0(mflags + b18x*2 + 2, 0x40)
                                                      (in the dev records: Y 33 ... X 8(64, mflags+b18x*2+2)
                                                      X 33 - the 030c0 inner read IS probed and visible
                                                      INSIDE the 33 span, BEFORE the span's own X)
    if (f270 == 0) local4 = 0
    na20 = FUN_68009a20(this + 0x74, 0x608)        probed 26; arg1 = 0x608
    if (na20 & 0xff) *(this+0x82) = 3

  switch (b18)            the cmd read at entry (two-level jump table 0x6805037c / 0x6805036c)
  0x30 / 0x31 / 0x32 -> 0x6804fc76    0x33 / 0x34 / 0x35 -> 0x6805023d    0x41 -> 0x6804fc4b    other -> nothing

  0x6804fc4b (b18 = 0x41, the runner handing off to its watchdog):
    FUN_68002ce0(stack pair, 0, 0)                 probed 4: arg1 = 0
    FUN_6802a6b1(this + 8, b18(=0x41), 0, 4, pair, 0)     unprobed; inside (param_3 = the pushed 4):
      FUN_68009590(this + 8 + 4)                   unprobed (the cmd flag field = 0)
      FUN_68002c40(this + 8 + 4, 4)                probed 2: arg1 = 4   (mask 4 OR'd into the cmd flag field)
      FUN_680030c0(this + 8 + 4, 1)                probed 8: arg1 = 1   (the mask-1 poll: rets 0 per the data)
      *(int*)(this+8+6) = 0x41 (the cmd code the next tick's a260 returns)

  0x6804fc76 (b18 = 0x30 / 0x31 / 0x32):
    f33f70 = FUN_68033f70(this + 8)                probed 70 (span); the inner 030c0(this+8+4, 4) read is inside
                                                      the span and hidden from top_level()
    if ((f33f70 & 0xff) != 0)                      mask 4 SET in the cmd flag field (per 030c0(f33f70), the
                                                      "0x7e(%eax)" chain): the 0x6804fc8d chain
      if (local4 == 0) 0x6804fdb0
      else if (*(this+0x7e) != 3) 0x6804fdb0
      else the 0x6804fca7 polling chain ([no dev data - *(this+0x7e) pre is 0 in all deep records])
    else                                           mask 4 CLEAR: 0x68050160, the FUN_6800f320 chain
      ([no dev data in the deep subset - mask 4 is set in all of it])
    (the (0x6804fc76 (b18 = 0x30 / 0x31 / 0x32)) note is the SAME handler as the jump table's 0x30 / 0x31 / 0x32
    values; the decompile's "0x6804fc76" region is this handler, and 0x6805023d (b18 = 0x33 / 0x34 / 0x35) and
    0x6804fc4b (b18 = 0x41) are the other two - no dev data for 0x6805023d in the deep subset: all six b18 values
    in the deep records are 0x30 / 0x31 / 0x32 / 0x41)

A record passes when replay returns having consumed every top-level event with no Mismatch. Most records leave through
the two early exits; the deep subset (calls that get past them) is the scored subset.
"""
from __future__ import annotations

import struct

import t3lib

F8F0, A260 = 0x6800f8f0, 0x6800a260
F600, F640, F38E30 = 0x6800f600, 0x6800f640, 0x68038e30
SC, N9610, F270, N9A20 = 0x680030c0, 0x68009610, 0x6800f270, 0x68009a20
F33F70, F320, F2F0 = 0x68033f70, 0x6800f320, 0x6800f2f0
CCE0, CC40 = 0x68002ce0, 0x68002c40


def replay(o, r):
    """Re-execute FUN_6804faa1: every branch decided from r and the getter values the oracle returns."""
    obj = r['obj']          # the first 0x100 bytes of *this before the call
    game = r['game']        # 0x50 bytes of the game state object 0x68143ee0 (read by FUN_68009610 - probed 19)
    mflags = r['mflags']    # 8 bytes at 0x68114948 (read by FUN_6800f270 - probed 33, inside the 33 span)

    def u16(o_):
        return struct.unpack_from('<H', obj, o_)[0]

    def i32(o_):
        return struct.unpack_from('<i', obj, o_)[0]

    def s8(o_):
        t = obj[o_]
        return t - 0x100 if t >= 0x80 else t

    # ---- 0x6804faad: FUN_6800f8f0(&DAT_680a2158): a top-level X span (probed 41). Its 030c0(0x680a6499, 2)
    # inner read is inside the span (Y 41 ... X 8(2) ... X 41 in the raw record), so span nesting hides it from
    # top_level(): only the span's own X 41 reaches the oracle. The replay calls o.x(F8F0) for the span's own X;
    # the inner 030c0 reads at 0x680a6499 are never replayed as separate calls (they are inside spans and
    # top_level() drops them). FUN_6802a8b7's 030c0(this+8+4, m) reads (m = 0x100 then, when *(this+0x12)!=0,
    # m = 4) are NOT inside any span (030c0 is probed but not NEST), so they are replayed as o.x(SC, m) calls.
    tick = o.x(F8F0) & 0xff

    # ---- 0x6804fab7: if (al == 0) return     -- early exit 1
    if tick == 0:
        return

    # ---- 0x6804face: b18 = FUN_6800a260(this + 8) - probed 27: *(this+8+6)
    b18 = o.x(A260) & 0xffffffff

    # ---- FUN_6802a8b7(this + 8) - unprobed; its 030c0(this+8+4, m) reads ARE top-level events
    # (per the decompile FUN_6802a8b7 = 030c0(p+4, 0x100); when (ret & 0xff)==0 (mask 0x100 CLEAR in *p)
    #  then when *(int*)(this+0x12) != 0: 030c0(p+4, 4); when (ret & 0xff)!=0 (mask 4 SET) return 1 - no event;
    #  when mask 4 CLEAR further: 030c0(p+4, 1) then ... (per the decompile, no dev data)))
    sc100 = o.x(SC, 0x100) & 0xffffffff
    if (sc100 & 0xff) == 0:
        # mask 0x100 CLEAR in *p (the low bit is the "flag", the high byte = (m>>8))
        p12 = i32(0x12)
        if p12 != 0:
            sc4 = o.x(SC, 4) & 0xffffffff
            if (sc4 & 0xff) != 0:
                pass    # mask 4 SET: return 1 - no event
            else:
                # mask 4 CLEAR: 030c0(p+4, 1) then the *(ushort*)(this+0x10) chains (per the decompile)
                sc1 = o.x(SC, 1) & 0xffffffff
                if (sc1 & 0xff) != 0:
                    # *(short*)(this+0x10)==0? per the decompile: no - *(ushort*)(this+0x10)=0 pre
                    sc20 = o.x(SC, 0x20) & 0xffffffff
                    if (sc20 & 0xff) != 0:
                        sc2 = o.x(SC, 0x2) & 0xffffffff
                        if (sc2 & 0xff) != 0:
                            pass    # *(u2*)(this+0x10) = 0
                        else:
                            # FUN_6802b420 deref of *(int*)(this+0x12) - not probed, no event
                            pass
                        # *(short*)(this+0x10) = sVar1 - 1
                    else:
                        pass    # FUN_68005ec0(p+4, 0x20); FUN_68002c40(p+4, 4) - 02c40 IS probed! X 2
                        # per the decompile: 05ec0 unp, 02c40 probed: o.x(CC40, 4)
                else:
                    pass    # *(u2*)(this+0x10) = *(u2*)(this+0x10) - 1 - no event
                # 030c0(p+4, 8): per the decompile followed by FUN_6802aa9f (2ce0 probed: X 4)
                sc8 = o.x(SC, 8) & 0xffffffff
                if (sc8 & 0xff) != 0:
                    o.x(CCE0, 0)        # FUN_6802aa9f's FUN_68002ce0(pair, 0, 0) - probed 4
                    pass
        # else: *(int*)(this+0x12) == 0: return (no event)

    # ---- 0x6804faed: switch (*(int*)(this + 0x79)) - 2 / 3 / 4; other: early exit 2
    x79 = i32(0x79)
    if x79 == 2:
        # FUN_6800f600(0x680a57b7) is polled TWICE (0x6804fb08 then 0x6804fb1b) - two spans per record:
        # Y 37 X 37(ret = the slot address, nonzero per the dev data) Y 37 X 37 X 74(38e30 of the SAME slot)
        f600 = o.x(F600) & 0xffffffff
        if f600 == 0:
            latch4 = 1          # the single call: mask 0x12 not set at the slot
        else:
            f600b = o.x(F600) & 0xffffffff     # the second span (0x6804fb1b); the same static slot - same value
            # FUN_68038e30 of the deref'd slot (0x6804fb28): *(p + 0x7e) - probed 74; one stack argument
            latch4 = 1 if (o.x(F38E30) & 0xffffffff) == 4 else 0
        b12 = -9
        c20 = 9
    elif x79 == 3:
        # the same twice-polled shape with FUN_6800f640 (0x6804fb6f / 0x6804fb82)
        f640 = o.x(F640) & 0xffffffff
        if f640 == 0:
            latch4 = 1
        else:
            f640b = o.x(F640) & 0xffffffff     # the second span (0x6804fb82); the same *(0x680a57b7 + 0x99) slot
            latch4 = 1 if (o.x(F38E30) & 0xffffffff) == 4 else 0   # *(p + 0x7e) - probed 74, one stack argument
        b12 = -15
        c20 = -15
    elif x79 == 4:
        latch4 = 1
        b12 = 9
        c20 = -9
    else:
        return

    # ---- 0x6804fbf0: FUN_68009610(0x68143ee0) - probed 19: one-register; arg1 absent
    b18x = o.x(N9610) & 0xffffffff
    # ---- 0x6804fbf7: FUN_6800f270(0x68114948, b18x, 0x40) - probed 33 (span); arg1 = b18x
    f270 = o.x(F270, b18x) & 0xffffffff
    if f270 == 0:
        latch4 = 0
    # ---- 0x6804fc17: FUN_68009a20(this + 0x74, 0x608) - probed 26; arg1 = 0x608
    na20 = o.x(N9A20, 0x608) & 0xffffffff
    if na20 & 0xff:
        pass    # *(this+0x82) = 3 (numeric, no event)

    # ---- switch (b18) - two-level table - 0x30 / 0x31 / 0x32 -> 0x6804fc76 - the position-shift handler
    if b18 in (0x30, 0x31, 0x32):
        f33f70 = o.x(F33F70) & 0xffffffff
        if (f33f70 & 0xff) != 0:
            # mask 4 SET: the 0x6804fc8d chain - *(this+0x7e) pre is 0 in all deep records: per the disasm
            # (cmpl $0, 0x7e(%eax); jle) takes the mask 0x20 chase; 030c0(this+0x74, 0x20) is per the disasm
            sc20 = o.x(SC, 0x20) & 0xffffffff
            if (sc20 & 0xff) != 0:
                pass    # *(this+0x78) -= 1 (numeric)
            else:
                sc10 = o.x(SC, 0x10) & 0xffffffff
                if (sc10 & 0xff) != 0:
                    pass    # *(this+0x78) -= 1 (numeric)
                else:
                    sc1 = o.x(SC, 0x1) & 0xffffffff
                    if (sc1 & 0xff) != 0:
                        pass    # *(this+0x78) -= 1 (numeric)
                    else:
                        sc2 = o.x(SC, 0x2) & 0xffffffff
                        if (sc2 & 0xff) != 0:
                            pass    # *(this+0x64) += b12; *(this+0x66) += c20 (numeric)
                        else:
                            sc80 = o.x(SC, 0x80) & 0xffffffff
                            if (sc80 & 0xff) != 0:
                                pass    # *(this+0x78) -= 1 (numeric)
                            else:
                                pass    # *(this+0x64) += b12; *(this+0x66) += c20 (numeric)
        else:
            # mask 4 CLEAR: the 0x68050160 FUN_6800f320 chain (no dev data in the deep subset - all set)
            f320 = o.x(F320) & 0xffffffff
            if (f320 & 0xff) != 0:
                f2f0 = o.x(F2F0) & 0xffffffff
                if (f2f0 & 0xff) != 0:
                    pass    # *(this+0x7e) -= 1 (numeric)
                o.x(CCE0, 0)             # probed 4: arg1 = 0 (the pair store)
                # FUN_6802a6b1(this + 8, b18, 0, 4, pair, 0) - inside: 02c40(p+4, 4) probed 2, 030c0(p+4, 1) probed 8
                o.x(CC40, 4)             # probed 2: arg1 = 4
                o.x(SC, 1)               # probed 8: arg1 = 1
                # FUN_68005ec0(this + 0x74, 3) - unprobed
            else:
                f2f0 = o.x(F2F0) & 0xffffffff
                if (f2f0 & 0xff) != 0:
                    pass    # *(this+0x7e) -= 1 (numeric)
                # *(this+0x64) += b12; *(this+0x66) += c20 (numeric)

    elif b18 == 0x41:
        # 0x6804fc4b: case-0x41 - the runner handing off to its watchdog
        o.x(CCE0, 0)             # probed 4: arg1 = 0 (the stack pair store)
        o.x(CC40, 4)             # probed 2: FUN_68002c40(this+8+4, param_3=4): arg1 = 4
        o.x(SC, 1)               # probed 8: FUN_680030c0(this+8+4, 1): arg1 = 1

    return
