# progress.md — lane code (runner AI update FUN_6804faa1, t3 bake-off round 1)

## Round 1 (2026-10-08)

### What was tried and learned

1. **Read the material first.** `t3lib.py` (oracle, record fields, `top_level()`, `deep()`), the probe list
   `re/simtrace_probes.py` (111 probed getters; `NEST` = the probes that make calls and open spans; `PTR` = the
   probes returning pointers), and the trace hook `src-latest/mods/simtrace.c` (record layout, event types, the
   dedup rule: an X event identical to the one before it is not logged again, and the oracle's `o.x()` returns
   the previous value without consuming an event).

2. **Mapped all callees of FUN_6804faa1 to their probe ids:**

   | VA | probe | NEST | args | reads |
   |---|---|---|---|---|
   | 0x6800f8f0 | 41 | yes | 0 | 030c0(this + 0x4341, 2) — a span |
   | 0x6800a260 | 27 | no | 0 | *(this + 8 + 6) |
   | 0x6800f600 | 37 | yes | 0 | *(0x680a57b7 + 0x95) slot ? value : 0 — a span |
   | 0x6800f640 | 38 | yes | 0 | *(0x680a57b7 + 0x99) slot ? value : 0 — a span |
   | 0x68038e30 | 74 | no | 0 | *(p + 0x7e) |
   | 0x68009610 | 19 | no | 0 | p + 4 != *(p + 0x46) |
   | 0x6800f270 | 33 | yes | 2 | 030c0(p + p1*2 + 2, p2) — a span, the inner 030c0 is inside it |
   | 0x68009a20 | 26 | no | 1 | (m & *(ushort*)p) ? m : 0 |
   | 0x68002ce0 | 4 | no | 2 | *(p)=p1, *(p+2)=p2, return p |
   | 0x68002c40 | 2 | no | 1 | *(ushort*)p |= p1, return p |
   | 0x68033f70 | 70 | yes | 0 | 030c0(this + 8 + 4, 4) — a span |
   | 0x6800f320 | 35 | yes | 0 | 030c0(this + 8 + 4, 8) — a span |
   | 0x6800f2f0 | 34 | yes | 0 | 030c0(this + 8 + 4, 1) — a span |
   | 0x680030c0 | 8 | NO | 1 | the poll/set getter itself: (m & *(u16*)p)==m ? 1|(m>>8)<<8 : (m>>8)<<8 |

   NOT probed (no events): FUN_68005b80 ((a*b)/100), FUN_68005ec0 (bit clears on this+0x74), FUN_680050b30
   (*(p10+0xdb)), FUN_6802a8b7 (the cmd tick), FUN_6802aa9f (watchdog), FUN_6802a6b1, FUN_6802b420, FUN_68009590.

3. **FUN_6802a8b7's inner 030c0(this+8+4, m) reads leak top-level events.** My first draft assumed the unprobed
   cmd-tick leave no events; the referee's failures said "model wants getter 6800f600, record has X[680030c0]
   (ecx=this+8+0xc, arg1=256, arg2=0)=256 (event 2)". Per the decompile the cmd tick polls mask 0x100 first and
   when (ret & 0xff) == 0 (the LOW byte is the flag: 256 = 0x100 mask CLEAR per 030c0's ret formula) continues
   with mask 4 only when *(int*)(this+0x12) != 0. The dev chain is exactly (0x100 ret) then (4 ret). Verified
   with the "a8b7 semantics" analysis: the observed (256),(4) chain is the 0x100-clear + *(this+0x12)!=0 +
   mask-4-set path (which then returns 1, no further events) - all consistent.

4. **FUN_6800f600 / 640 is polled TWICE** in the case-2 / case-3 branches (0x6804fb08 then 0x6804fb1b): two
   spans per record (Y 37 X 37(ret=26417504 = the deref'd slot address) Y 37 X 37 X 74(38e30 of the SAME slot)).
   The decompile's "iVar3 = FUN_6800f600(...); if (iVar3==0) {...} else { iVar3 = FUN_6800f600(...); iVar3 =
   FUN_68038e30(iVar3); if (iVar3==4) ... }" is the twice-polled shape. The referee next failed "model wants
   getter 68038e30, record has X[6800f600]... (event 4)" - the second span was missing. Fixed.

5. **Verified the jump table** (two-level, 0x6805037c = the case byte, 0x6805036c = the case target): b18 = 0x30 /
   0x31 / 0x32 -> 0x6804fc76, 0x33 / 0x34 / 0x35 -> 0x6805023d, 0x41 -> 0x6804fc4b, other -> 0x68050389. For
   dev records: a260 (b18) = 0x41 in 91 records, 0x30 in 50, 0x31 in 19, 0x32 in 13.

6. **The case-0x41 handler** (0x6804fc4b: FUN_68002ce0(pair, 0, 0) then FUN_6802a6b1(this+8, 0x41, 0, 4, pair, 0)):
   inside FUN_6802a6b1 the cmd flag field at *(this+0xc) is cleared (FUN_68009590 - unprobed) then mask 4 is OR'd in
   (FUN_68002c40 - probed 2, arg1 = 4) and the mask-1 poll follows (FUN_680030c0 - probed 8, arg1 = 1): the
   X 2(arg1=4), X 8(arg1=1) tail. *(int*)(this+0x12) == 0 pre in these records, so FUN_6802a8b7's tick polls only
   mask 0x100 (its *p+10 == 0 branch leaves the chain with one event).

7. **The case-0x30/0x31/0x32 handler** (0x6804fc76): FUN_68033f70(this+8) - probed 70, a span (its inner
   030c0(this+8+4, 4) read is inside and hidden). When mask 4 is SET in *(u16*)(this+0xc) per the data (ret 1 in all
   82 deep records with the 70 span): the 0x6804fc8d chain - *(this+0x7e) pre is 0 in all of them (the "not 3"
   branch), so the FUN_680030c0(this+0x74, m) polls (m = 0x20, 0x10, 1, 2, 0x80 per the data, from 0x193193c =
   this+0x74): the 5-X(8) polling tails. When mask 4 CLEAR: the 0x68050160 FUN_6800f320 chain - no dev data (mask 4
   set in all of it). *(int*)(this+0x12) != 0x680d40a8 pre for these records - the FUN_6802a8b7 tick polls 0x100 then
   4 and leaves (the mask-4-SET "return concat31" branch per the decompile).

### Current referee output (round 1)

```
$ T3_LANE_ADVISORY=1 python3 /home/will/bbpro98/re/targets/t3ref.py \
    /home/will/bbpro98/re/targets/t3rai /home/will/bbpro98/re/targets/t3raig/lanes/code --audit
records 2500 ok 2500 | deep (past the early exits) 173 ok 173
failure kinds: {}
PASS
```

PASS on all 2500 dev records (deep subset 173/173). File: `runner_ai.py` (265 lines, ~15 KB, stdlib + t3lib only).

### What the model does (replay call tail for the record shape at 173 deep records)

f8f0 span, a260, [030c0(0x100) when (ret&0xff)==0 further 030c0(4) when *(this+0x12)!=0], case 2/3/4:
[twice-polled f600 or f640 span + o.x(74, ...)], case 4: nothing. Then FUN_68009610, FUN_6800f270 (one-arg span),
FUN_68009a20 (0x608), and the switch(b18) handler chain per the jump table - FUN_68002ce0, FUN_68002c40(mask 4),
FUN_680030c0(mask 1) for the case-0x41 chain; FUN_68033f70(span), FUN_6800f320, FUN_6800f2f0, FUN_68002ce0 for the
case-0x30/0x31/0x32 chain. All branches per the binary.

### Learned notes for the next lane / round

- The early exits leave only the f8f0 span's own X (1435 records leave at exit 1; 892 records leave before the
  a260/f600 tail with the 030c0(a8b7 chain) events left unconsumed - 3 top-level events).
- An unprobed callee leaves no event of its own, but the probed getters it calls DO - FUN_6802a8b7's inner
  030c0(this+8+4, m) reads (0x100 first, then 4 when *(this+0x12) != 0) are the naked events left unconsumed.
- The low byte of 030c0's ret (m>>8 for m >= 0x100) is the flag: ret = 256 (0x100 CLEAR), ret = 1 (mask 4 SET),
  ret = 0 (mask CLEAR in the low byte only), ret = 1536 (0x600 in *(p+0x74), the mask-0x608 chase).
- A probed getter with 2 probe names winning: FUN_6800f270's own X (33) and its inner FUN_680030c0 (8) both show.

### Ground truth (the binary, not the decompile)

- `push ebp; mov ebp,esp; sub $0x60,%esp` (FUN_6804faa1 prologue, prologue length 6).
- FUN_6800f8f0 = 030c0(this + 0x4341, 2) - NOT the MFC "CMiniDockFrameWnd" name.
- FUN_6800f540 = 030c0(this + 0x8b, 1) - NOT the MFC "CMiniDockFrameWnd" name.
- FUN_6800f780 = *(int*)(p + 0x105) - NOT the MFC "CSplitterWnd::IsTracking" name.
- FUN_680030c0 = (m & *(u16*)p)==m ? 1|(m>>8)<<8 : (m>>8)<<8.
- FUN_68005b80 = (p1 * p2) / 100 - NOT probed.
- FUN_68005ec0 = *(u16*)p &= ~m - NOT probed.
- FUN_6802b420 = *(u2*)p, FUN_6802aa9f and FUN_6802a6b1 are NOT probed.
- FUN_68082999 = FUN_68082ae1(this) (the LFSR-style generator) then (uVar1 % p1).
