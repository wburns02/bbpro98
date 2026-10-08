"""Replay model of FastSim FUN_6805d960 (throw speed, simtrace target throw_speed): this = the fielder, param_1 = his
arm rating. Fielders past the FUN_68026310 test (u16 at this+0xc above 0x1067, eax low byte) use PB 0x2f3-0x2f5,
the rest PB 0x2f0-0x2f2: speed = rating * PB[scale] / 100 + PB[base], capped at PB[max] (read twice when it caps)."""
import t3lib


def replay(o, r):
    base = 0x2f3 if o.x(0x68026310) & 0xff else 0x2f0
    v = t3lib.cdiv(r['arg'] * o.pb(base + 1), 100)          # FUN_68005b80(param_1, PB) = param_2 * param_1 / 100
    v = t3lib.s16v(t3lib.s16v(v) + t3lib.s16v(o.pb(base)))   # (short)iVar2 + (short)uVar3
    if o.pb(base + 2) < v: v = t3lib.s16v(o.pb(base + 2))
    return v
