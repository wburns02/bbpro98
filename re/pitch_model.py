#!/usr/bin/env python3
"""Roadmap #10 M9 referee: replays FastSim's swing decision and timing roll from a pitchtrace.dll record file and
checks the formulas in work/SIM_PITCH_MODEL.md. usage: pitch_model.py pitchtrace.bin [more.bin ...]

Exact replay: from each record's inputs (batter object before the call, game state, manager flags, pitch object and
the RNG state before the call) the model predicts the outputs (swing flag +0x11e, swing type +0xbd, timing offset
+0x112, perfect-timing flag +0x111) and the RNG state after the call. Every field must match on every record.
Chi-square: swings vs the model's swing probability (bins of predicted p), and timing offsets vs the exact dice
distribution of their rating bracket (reported only: the
offsets are intermediate values, and exact replay already proves the roll). Gated distributions are the pitch
outcomes: swing/take and the contact draws (bat zone, exit speed). PB values are the FastSim defaults (work/pb_table_FastSim.tsv), as in a run
without PB.INI.
"""
import collections, csv, os, struct, sys
from scipy.stats import chi2

HERE = os.path.dirname(os.path.abspath(__file__))
PB = {int(r['idx']): int(r['dll_default'])
      for r in csv.DictReader(open(f'{HERE}/../work/pb_table_FastSim.tsv'), delimiter='\t')}
# static .data tables of FastSim.dll (read from the file, see SIM_PITCH_MODEL.md)
APPROACH = ((0, 3, 3, 3), (1, 1, 3, 3), (2, 2, 2, 2))          # DAT_6808cfb8 [strikes][balls]
REC = struct.Struct('<B3x4I80s8sI4sB3x320s320s')
GAME = 0x68143ee0


def hotzone_table():
    d = open('/mnt/nvme/bbpro98/work_install/FastSim.dll', 'rb').read()
    off = 0x96410 - 0x8c000 + 0x8aa00                           # .data: rva 0x8c000 -> raw 0x8aa00
    return struct.unpack_from('<144i', d, off)                  # [pitch type 0..7][opposite hand 0/1][grid 0..8]


HOT = hotzone_table()


def _data(va, fmt, n):
    d = open('/mnt/nvme/bbpro98/work_install/FastSim.dll', 'rb').read()
    return struct.unpack_from(f'<{n}{fmt}', d, va - 0x68000000 - 0x8c000 + 0x8aa00)


ATAN = _data(0x6809dc7c, 'B', 513)                              # FUN_6807c09c octant table
COS = _data(0x6809de80, 'H', 0x401)                             # FUN_6807cb88 quarter-wave, Q14
BAT = [PB[0x2bc + i] for i in range(12)]                        # DAT_68097608: batPower{Handle,Dull,Sweet,End}Base,
                                                                # ...Range, hitAngleCount* (read past the end by zone 4/5)


def s16v(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


def atan2_bb(x, y):
    """FUN_6807c09c(x, y): angle of (x, y), 0x10000 = 360 degrees, as the int it returns."""
    u1, u2 = abs(x), abs(y)
    if u2 == 0:
        v = 0
    elif u1 == 0:
        v = 0x1000
    elif u1 < u2:
        i = (u1 * 512 + (u2 >> 1)) // u2
        v = 0x1000 - (i * 4 + ATAN[i] if i else 0)
    else:
        i = (u2 * 512 + (u1 >> 1)) // u1
        v = i * 4 + ATAN[i] if i else 0
    if x < 0:
        v = 0x2000 - v
    if y < 0:
        v = 0x4000 - v
    return ((v & 0xffffffff) & 0x3fff) << 2


def cos_bb(a):
    """FUN_6807cb88(short a): Q14 cosine, 0x10000 = 360 degrees."""
    i = (a >> 4) + ((a >> 3) & 1)
    i = abs(i)
    return COS[i] if i < 0x400 else -COS[0x800 - i]


def contact(r, info=None):
    """FUN_68053d2e. Returns (launched, spray, exit_speed, zone, rng state after its own draws). `info` (a dict) gets
    the random choices' inputs: zone-roll pair and chance, exit-speed draw u and its range."""
    b, pb = r['before'], r['game']                              # pb = pitch object +0xd0..
    P = lambda o, f='<h': struct.unpack_from(f, pb, o - 0xd0)[0]
    rng = Rng(r['rm0'])
    flags = struct.unpack_from('<H', r['mflags'], 0)[0]
    if flags & 2 or not struct.unpack_from('<H', b, 0x8b)[0] & 4 or i32(b, 0x139) == 1:
        return 0, None, None, None, rng.s
    if i32(b, 0x139) == 2:                                      # failed check swing: failedCheckContactChance draw,
        rng.mod(100)                                            # its result is never used
    pspeed = P(0x105, '<i')
    c = cdiv(i32(b, 0x112) * pspeed * 0x2c0, 40000)
    spray = s16v(s16(b, 0x123) + s16v(atan2_bb(36 - abs(c), c)))
    thr = s16v((s16v(cos_bb(spray)) * 100) >> 14)
    ey = s16v(P(0xed) - s16(b, 0x109))
    hi = s16v(rng.mod(201) - 100 + s16v(ey * 200))
    if abs(hi) > 100:
        z = 5
    else:
        ex = s16v(P(0xeb) - s16(b, 0x107))
        ex = int(cdiv(s16v(ex * 100), 100))
        def roll(a, bb):
            if info is not None:
                info['roll'] = (a, bb, min(max(thr, 0), 100) / 100)
            return a if rng.mod(100) < thr else bb
        z = {0: lambda: 2, 1: lambda: roll(2, 3), 2: lambda: roll(3, 5), -5: lambda: roll(0, 5), -6: lambda: roll(0, 5),
             -3: lambda: roll(1, 0), -4: lambda: roll(1, 0), -1: lambda: roll(2, 1), -2: lambda: roll(2, 1)}.get(
            ex, lambda: 5)()
    q = pct(i32(b, 0x125), thr)
    u = rng.mod(BAT[4 + z])
    q = pct(q, BAT[z] + u)
    if info is not None:
        info.update(u=u, spread=BAT[4 + z], zone=z)
    launched = int(z != 5 and abs(spray) < 0x4000)
    return launched, spray, q, z, rng.s


def reaches(s, t, limit=4000):
    rng = Rng(s)
    for _ in range(limit):
        if rng.s == t:
            return True
        rng.next()
    return rng.s == t


def cdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def cmod(a, b):
    return a - cdiv(a, b) * b


def pct(v, p):                                                  # FUN_68005b80
    return cdiv(v * p, 100)


class Rng:                                                      # FUN_68082ae1 Galois LFSR
    def __init__(self, s):
        self.s = s

    def next(self):
        self.s = (self.s >> 1) ^ (0xa3000000 if self.s & 1 else 0)
        return self.s

    def mod(self, n):                                           # FUN_68082999
        r = self.next()
        return 0 if n < 2 else r % n

    def range(self, lo, hi):                                    # FUN_680829dc
        r = self.next()
        n = hi - lo + 1
        return lo + r % n if n > 1 else lo


def s16(b, o):
    return struct.unpack_from('<h', b, o)[0]


def i32(b, o):
    return struct.unpack_from('<i', b, o)[0]


def zone(x, y):                                                 # FUN_6802ef90: 0 sure strike .. 3 sure ball
    d = max(abs(x), abs(y))
    if d <= PB[0x181]:
        return 0
    if d <= PB[0x182]:
        return 1
    return 2 if d <= PB[0x183] else 3


def hot(ptype, x, y, phand, bhand):                             # FUN_6802ef2a / FUN_6802eeda
    g = cdiv(4 - y, 3) * 3 + cdiv(x + 4, 3)
    return HOT[ptype * 18 + (phand != bhand) * 9 + g]


_TWO = {}


def two_draw(d):
    """P(d < r1 or d < r2) for two consecutive rand(100) draws of the LFSR (correlation ~0.25, so lower than the
    independent p + (1 - p) p)."""
    if not _TWO:
        import numpy as np
        st = np.random.default_rng(3).integers(1, 2 ** 32, 1000000, dtype=np.uint64).astype(np.uint32)
        nx = lambda v: (v >> np.uint32(1)) ^ np.where(v & np.uint32(1), np.uint32(0xa3000000), np.uint32(0))
        s1 = nx(st); s2 = nx(s1)
        r1, r2 = (s1 % 100).astype(int), (s2 % 100).astype(int)
        for k in range(-1, 100):
            _TWO[k] = float(((r1 > k) | (r2 > k)).mean())
    return 1.0 if d < 0 else 0.0 if d >= 99 else _TWO[d]


def swing(r):
    """FUN_6800e043. Returns (swing, type, rng_after, p_swing or None, branch)."""
    b, g = r['before'], r['game']
    swing_, typ = 0, i32(b, 0xbd)
    rng = Rng(r['rb0'])
    flags = struct.unpack_from('<H', b, 0x89)[0]
    x, y = s16(b, 0x107), s16(b, 0x109)
    if flags & 0x100:                                           # bunt order
        return int(zone(x, y) != 3), 3, rng.s, None, 'bunt'
    if flags & 0x200:                                           # hit and run
        return 1, 2, rng.s, None, 'hitrun'
    if flags & 0x400:                                           # take
        return 0, typ, rng.s, None, 'take'
    side = int(struct.unpack_from('<I', g, 0x4a)[0] != GAME + 2)
    if struct.unpack_from('<H', r['mflags'], side * 2 + 2)[0] & 0x80 == 0x80:   # swing-away order
        return 1, 0, rng.s, None, 'swingaway'
    d = i32(r['after'], 0x11a)                                  # discipline, FUN_6800dcc4
    balls, strikes = g[0x4e], g[0x4f]
    guessed = r['p10d'] == 1                                    # FUN_6800f7d0
    phand = struct.unpack_from('<i', r['p7d'])[0]
    cold = hot(i32(b, 0xfa), x, y, phand, i32(b, 0x8d)) == 0
    look_t, look_l = b[0x10f] == 1, b[0x110] == 1
    z = zone(x, y)
    if z == 3:
        return 0, typ, rng.s, 0.0, 'sureball'
    p1 = max(0, min(100, 99 - d)) / 100                         # P(d < rand(100))
    mode = APPROACH[strikes][balls]
    p = None
    if mode == 0:
        swing_ = int(d < rng.mod(100))
        if not swing_:
            swing_ = int(d < rng.mod(100))
            if swing_ and not (look_t and look_l):
                swing_ = 0
        typ = 0 if look_t and look_l else 1
        p = two_draw(d) if look_t and look_l else p1
    elif mode == 1:
        if (look_t and look_l) or guessed or (cold and look_l):
            swing_, p = 1, 1.0
        else:
            swing_, p = int(d < rng.mod(100)), p1
        typ = 1
    elif mode == 2:
        if z in (0, 1):
            swing_, p = 1, 1.0
        elif z == 2:
            swing_, p = int(d < rng.mod(100)), p1
        else:
            swing_, p = 0, 0.0
        typ = 1 if (look_t and look_l) or guessed or cold else 2
    else:
        if look_t and look_l:
            swing_, typ, p = 1, 0, 1.0
        elif guessed or cold:
            swing_, typ, p = int(d < rng.mod(100)), 1, p1
        else:
            swing_, p = 0, 0.0
    return swing_, typ, rng.s, p, f'mode{mode}'


TIMING = [(0x201, 0x202), (0x205, 0x206), (0x209, 0x20a), (0x20d, 0x20e), (None, 0x211)]


def timing_dice(b):
    """FUN_6800da34 bracket: (count, faces, base, bracket name)."""
    v = pct(i32(b, 0xf1), PB[0x200])
    if b[0xf9] == 0:
        v -= i32(b, 0xf5)
    if i32(b, 0xbd) == 3:
        return PB[0x214], PB[0x215], PB[0x216], 'bunt'
    for i, (thr, c) in enumerate(TIMING):
        if thr is None or v < PB[thr]:
            return PB[c], PB[c + 1], PB[c + 2], ('verybad', 'bad', 'med', 'good', 'verygood')[i]


def timing(r):
    n, faces, base, name = timing_dice(r['before'])
    rng = Rng(r['rm0'])
    v = base + sum(rng.range(1, faces) for _ in range(n))
    return v, int(abs(v) < 1), rng.s, name


def dice_pmf(n, faces, base):
    dist = {0: 1.0}
    for _ in range(n):
        nd = collections.defaultdict(float)
        for k, p in dist.items():
            for f in range(1, faces + 1):
                nd[k + f] += p / faces
        dist = nd
    return {k + base: p for k, p in dist.items()}


def lfsr_pmf(n, faces, base, samples=400000, seed=1):
    """Distribution of base + n consecutive rand_range(1, faces) draws from a uniformly random LFSR state. Not the
    independent-dice pmf: the Galois LFSR shifts one bit per draw, so consecutive draws share bits and the sum of
    several is correlated (wider/narrower than ideal dice)."""
    import numpy as np
    s = np.random.default_rng(seed).integers(1, 2 ** 32, samples, dtype=np.uint64).astype(np.uint32)
    tot = np.full(samples, base, dtype=np.int64)
    for _ in range(n):
        s = (s >> np.uint32(1)) ^ np.where(s & np.uint32(1), np.uint32(0xa3000000), np.uint32(0))
        tot += 1 + (s % np.uint32(faces)).astype(np.int64)
    k, c = np.unique(tot, return_counts=True)
    return {int(a): b / samples for a, b in zip(k, c)}


def chisq(obs, exp, min_exp=5):
    """Pools adjacent bins until each expected count >= min_exp. Returns (stat, dof, p)."""
    bins, o, e = [], 0, 0.0
    for ob, ex in zip(obs, exp):
        o += ob; e += ex
        if e >= min_exp:
            bins.append((o, e)); o, e = 0, 0.0
    if e and bins:
        bins[-1] = (bins[-1][0] + o, bins[-1][1] + e)
    stat = sum((o - e) ** 2 / e for o, e in bins)
    dof = len(bins) - 1
    return stat, dof, (chi2.sf(stat, dof) if dof > 0 else float('nan'))


def records(paths):
    for p in paths:
        data = open(p, 'rb').read()
        for i in range(0, len(data) - REC.size + 1, REC.size):
            k, rb0, rb1, rm0, rm1, game, mflags, pitch, p7d, p10d, before, after = REC.unpack_from(data, i)
            yield dict(kind=chr(k), launched=data[i + 1], spray=struct.unpack_from('<h', mflags, 4)[0],
                       speed=struct.unpack_from('<i', struct.pack('<I', pitch))[0], rb0=rb0, rb1=rb1, rm0=rm0, rm1=rm1, game=game, mflags=mflags, pitch=pitch,
                       p7d=p7d, p10d=p10d, before=before, after=after)


def main():
    recs = list(records(sys.argv[1:]))
    sw = [r for r in recs if r['kind'] == 'E']
    tm = [r for r in recs if r['kind'] == 'T']
    print(f'records: {len(recs)} (swing decisions {len(sw)}, timing rolls {len(tm)})')
    ok = True

    bad, branches, pred = [], collections.Counter(), []
    for r in sw:
        s, t, rng, p, br = swing(r)
        branches[br] += 1
        got = (r['after'][0x11e], i32(r['after'], 0xbd), r['rb1'])
        if (s, t, rng) != got:
            bad.append((br, (s, t, hex(rng)), (got[0], got[1], hex(got[2]))))
        if p is not None and 0 < p < 1:
            pred.append((p, got[0]))
    print(f'swing decision exact replay: {len(sw) - len(bad)}/{len(sw)} match; branches {dict(branches)}')
    for x in bad[:10]:
        print('  MISMATCH', x)
    ok &= not bad and len(sw) >= 100

    pred.sort()
    nb = max(2, min(10, len(pred) // 20))
    obs, exp = [], []
    for i in range(nb):
        chunk = pred[i * len(pred) // nb:(i + 1) * len(pred) // nb]
        obs += [sum(g for _, g in chunk), sum(1 - g for _, g in chunk)]
        exp += [sum(p for p, _ in chunk), sum(1 - p for p, _ in chunk)]
    stat = sum((o - e) ** 2 / e for o, e in zip(obs, exp) if e > 0)
    pv = chi2.sf(stat, nb)
    print(f'swing rate vs model: {len(pred)} random decisions in {nb} probability bins, chi2 {stat:.2f} dof {nb} '
          f'p {pv:.3f}; observed {sum(obs[0::2])} swings, expected {sum(exp[0::2]):.1f}')
    ok &= len(pred) >= 100 and pv > 0.05

    bad, by = [], collections.defaultdict(list)
    for r in tm:
        v, perf, rng, name = timing(r)
        got = (i32(r['after'], 0x112), r['after'][0x111], r['rm1'])
        if (v, perf, rng) != got:
            bad.append((name, (v, perf, hex(rng)), (got[0], got[1], hex(got[2]))))
        by[timing_dice(r['before'])].append(got[0])
    print(f'timing exact replay: {len(tm) - len(bad)}/{len(tm)} match')
    for x in bad[:10]:
        print('  MISMATCH', x)
    ok &= not bad and len(tm) >= 100
    for (n, faces, base, name), vals in sorted(by.items(), key=lambda kv: kv[0][3]):
        pmf = lfsr_pmf(n, faces, base)
        ideal = dice_pmf(n, faces, base)
        ks = sorted(set(pmf) | set(ideal))
        c = collections.Counter(vals)
        stat, dof, pv = chisq([c[k] for k in ks], [pmf.get(k, 0) * len(vals) for k in ks])
        st2, _, pv2 = chisq([c[k] for k in ks], [ideal.get(k, 0) * len(vals) for k in ks])
        stray = sum(v for k, v in c.items() if k not in pmf)
        sd = lambda d: sum(p * (k - sum(q * j for j, q in d.items())) ** 2 for k, p in d.items()) ** 0.5
        obs_sd = (sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals)) ** 0.5
        print(f'  timing {name:8s} {n}d{faces}{base:+d}: n {len(vals):5d} mean {sum(vals) / len(vals):6.2f} '
              f'(model {sum(k * p for k, p in pmf.items()):6.2f}) sd {obs_sd:5.2f} (LFSR {sd(pmf):5.2f}, ideal dice '
              f'{sd(ideal):5.2f}) chi2 vs LFSR {stat:.1f} dof {dof} p {pv:.3f}; vs ideal dice p {pv2:.3g}; '
              f'out-of-support {stray}')
        ok &= not stray
        if len(vals) >= 100 and pv <= 0.05:
            print(f'  NOTE timing {name}: dice outcomes deviate from the uniform-state LFSR distribution (exact replay '
                  f'above is the proof of the formula; this is a property of the game\'s RNG state sequence, '
                  f'reported, not gated)')

    ct = [r for r in recs if r['kind'] == 'C']
    bad, zones, rolls, us = [], collections.Counter(), [], collections.defaultdict(collections.Counter)
    for r in ct:
        info = {}
        launched, spray, q, z, rng = contact(r, info)
        if 'roll' in info and 0 < info['roll'][2] < 1:
            rolls.append((info['roll'][2], int(z == info['roll'][0])))
        if 'u' in info and z != 5 and r['launched']:
            us[z][info['u']] += 1
        zones[z] += 1
        got = (r['launched'], r['spray'] if r['launched'] else None, r['speed'] if r['launched'] else None)
        want = (launched, spray if launched else None, q if launched else None)
        rng_ok = rng == r['rm1'] if not launched else reaches(rng, r['rm1'])
        if got != want or not rng_ok:
            bad.append((z, want, got, rng_ok))
    if ct:
        print(f'contact exact replay: {len(ct) - len(bad)}/{len(ct)} match; bat zones {dict(zones)} '
              f'(None = no swing reached contact, 5 = miss)')
        for x in bad[:10]:
            print('  MISMATCH', x)
        ok &= not bad and len(ct) >= 100
        # outcome distributions of the contact draws (independent uniform draws assumed)
        obs, exp = [sum(g for _, g in rolls), sum(1 - g for _, g in rolls)], [sum(p for p, _ in rolls),
                                                                             sum(1 - p for p, _ in rolls)]
        if rolls:
            stat, dof, pv = chisq(obs, exp)
            print(f'contact bat-zone rolls: {len(rolls)} random, first zone {obs[0]} (model {exp[0]:.1f}) '
                  f'chi2 {stat:.2f} p {pv:.3f}')
        for z, c in sorted(us.items()):
            n = sum(c.values())
            stat, dof, pv = chisq([c[k] for k in range(BAT[4 + z])], [n / BAT[4 + z]] * BAT[4 + z])
            print(f'exit-speed draw, bat zone {z}: n {n} uniform 0..{BAT[4 + z] - 1} chi2 {stat:.2f} dof {dof} '
                  f'p {pv:.3f}')
            if n >= 100:
                ok &= pv > 0.05
    print('PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
