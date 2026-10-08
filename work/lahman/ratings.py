#!/usr/bin/env python3
"""Player ratings for a Lahman season, in the game's own rating scale.

The game's 1996 end-of-season association (Assn/MLBPA96E.PYR) carries ratings that are close to a deterministic
function of each player's 1996 stats. fit() matches those players to Lahman 1996 and fits, per rating, a linear model
on z-scored rate stats (5-fold CV R2 on 1996: contact .90, power .92, speed .95, endurance .90, control .94,
strikeout .95, fielding .4-.76). rate() applies the model to any season: each stat is z-scored inside its own
league-year (the era adjustment) and shrunk toward the mean by sample size, so a .400 hitter in 1894 and a .340
hitter in 1968 land where they stood against their own league. Ratings the stats cannot predict (pitch repertoire,
arm, the 25 single attributes) come from the nearest MLBPA96E player of the same role and position (the donor), and
every fitted rating's peak is the current value plus the donor's peak-current gap.

PYR record layout used here: work/spec/PGEN_FORMAT.md and /mnt/nvme/bbpro98/loop/lahman/contract.md (C4).
The game files are read at run time and never copied into the repo.
"""
import datetime
import struct
import sys
import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import league as LG                                      # noqa: E402  (cipher)
from lahman import lahdb                                 # noqa: E402

REC = 192
PEAK, CUR, ATTR = 0x46, 0x5d, 0x74
CH, PH, SP, EN, CO = 0, 1, 2, 5, 6                      # rating indexes inside a 23-byte block
FLD0 = 14                                                # fielding P..RF = block indexes 14..22
K_ATTR, GF_ATTR = 0x76, 0x75                             # pitcher strikeout attribute, hitter ground/fly attribute
POS_CODE = {'P': 1, 'C': 2, '1B': 3, '2B': 4, '3B': 5, 'SS': 6, 'LF': 7, 'CF': 8, 'RF': 9}
APP_POS = (('G_p', 'P'), ('G_c', 'C'), ('G_1b', '1B'), ('G_2b', '2B'), ('G_3b', '3B'), ('G_ss', 'SS'),
           ('G_lf', 'LF'), ('G_cf', 'CF'), ('G_rf', 'RF'))
FEAT_H = ('AVG', 'ISO', 'HR', 'D', 'T', 'SBg', 'SBA', 'BB', 'K', 'SH', 'HBP')
FEAT_P = ('GSr', 'IPG', 'BB9', 'K9', 'HR9', 'H9', 'ERA', 'SVg', 'GFg', 'CGr')
FEAT_F = ('RFg', 'Ep', 'DPg', 'Ag', 'PBg')
SHRINK_H, SHRINK_P, SHRINK_F = 100.0, 30.0, 20.0         # PA, IP, G at which a stat counts half
MIN_LEAGUE = 25                                          # qualifiers needed to z-score inside one league
Z_RANGE = (-4.0, 8.0)                                    # keeps the contact quadratic on its rising side
# Fitted current ratings: name -> (role, rating byte, features, quadratic in the first feature, raw features).
# Subsets beat all-feature fits on 1996 cross-validation and stay stable at other eras' extreme z-scores.
# Endurance uses raw innings per game: an 1884 workhorse should tire like one, not like a 1996 average starter.
TARGETS = {
    'CH': ('h', CUR + CH, ('AVG',), True, False),          # cvR2 .89; convex: .350 hitters sit near 95
    'PH': ('h', CUR + PH, ('ISO', 'HR'), False, False),     # .90
    'SP': ('h', CUR + SP, ('SBA', 'SBg', 'T'), False, False),  # .84
    'GF': ('h', GF_ATTR, ('HR',), False, False),            # .35, the best single predictor of this attribute
    'EN': ('p', CUR + EN, ('IPG', 'GSr'), False, True),     # .84
    'CO': ('p', CUR + CO, ('BB9',), False, False),          # .98
    'K': ('p', K_ATTR, ('K9',), False, False),              # .98
}


# ---------------------------------------------------------------- PYR io

def cipher(seed):
    t = LG._forward(seed)
    inv = bytearray(256)
    for x, y in enumerate(t):
        inv[y] = x
    return t, bytes(inv)


def read_pyr(path):
    """(header bytes, [plain 192-byte records])."""
    with open(path, 'rb') as fh:
        d = fh.read()
    if len(d) < REC or (len(d) - REC) % REC:
        raise ValueError('%s: not a PYR file (size %d)' % (path, len(d)))
    _, inv = cipher((d[0], d[1]))
    recs = [bytes(inv[b] for b in d[REC + i * REC:2 * REC + i * REC]) for i in range((len(d) - REC) // REC)]
    return d[:REC], recs


def write_pyr(path, header, recs):
    t, _ = cipher((header[0], header[1]))
    with open(path, 'wb') as fh:
        fh.write(header)
        for r in recs:
            if len(r) != REC:
                raise ValueError('record of %d bytes' % len(r))
            fh.write(bytes(t[b] for b in r))


def cstr(b):
    return b.split(b'\0')[0].decode('latin-1').strip('*').strip()


def serial(day):
    return day.toordinal() + 365


def from_serial(n):
    return datetime.date.fromordinal(n - 365)


# ---------------------------------------------------------------- stat features

def _n(d, k):
    v = d.get(k, 0) if isinstance(d, dict) else 0
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def hit_feats(b):
    ab = _n(b, 'AB')
    if ab <= 0:
        return None, 0
    pa = ab + _n(b, 'BB') + _n(b, 'HBP') + _n(b, 'SF') + _n(b, 'SH')
    h, d2, d3, hr = _n(b, 'H'), _n(b, '2B'), _n(b, '3B'), _n(b, 'HR')
    g = max(1, _n(b, 'G'))
    on1 = max(1, h - d2 - d3 - hr + _n(b, 'BB') + _n(b, 'HBP'))
    f = dict(AVG=h / ab, ISO=(d2 + 2 * d3 + 3 * hr) / ab, HR=hr / ab, D=d2 / ab, T=d3 / ab,
             SBg=_n(b, 'SB') / g, SBA=(_n(b, 'SB') + _n(b, 'CS')) / on1,
             BB=_n(b, 'BB') / pa, K=_n(b, 'SO') / pa, SH=_n(b, 'SH') / pa, HBP=_n(b, 'HBP') / pa)
    return f, pa


def pit_feats(q):
    ip = _n(q, 'IPouts') / 3
    if ip <= 0:
        return None, 0
    g = max(1, _n(q, 'G'))
    f = dict(GSr=_n(q, 'GS') / g, IPG=ip / g, BB9=9 * _n(q, 'BB') / ip, K9=9 * _n(q, 'SO') / ip,
             HR9=9 * _n(q, 'HR') / ip, H9=9 * _n(q, 'H') / ip, ERA=9 * _n(q, 'ER') / ip,
             SVg=_n(q, 'SV') / g, GFg=_n(q, 'GF') / g, CGr=_n(q, 'CG') / max(1, _n(q, 'GS')))
    return f, ip


def fld_feats(f):
    g = _n(f, 'G')
    if g <= 0:
        return None, 0
    ch = _n(f, 'PO') + _n(f, 'A') + _n(f, 'E')
    return dict(RFg=(_n(f, 'PO') + _n(f, 'A')) / g, Ep=_n(f, 'E') / max(1, ch), DPg=_n(f, 'DP') / g,
                Ag=_n(f, 'A') / g, PBg=_n(f, 'PB') / g), g


def fld_by_pos(fpos):
    """Lahman fielding {POS: totals} -> {game position: totals}; OF rows (and LF/CF/RF when present) feed the three
    outfield spots."""
    out = {}
    for pos in ('P', 'C', '1B', '2B', '3B', 'SS'):
        if pos in fpos:
            out[pos] = fpos[pos]
    of = {}
    for pos in ('OF', 'LF', 'CF', 'RF'):
        for k, v in (fpos.get(pos) or {}).items():
            of[k] = of.get(k, 0) + (v or 0)
    if of.get('G'):
        for pos in ('LF', 'CF', 'RF'):
            out[pos] = of
    return out


class Norm:
    """Mean and sd of each feature over qualifiers, per group (a league, or the whole year)."""

    def __init__(self, rows, names):
        self.mu, self.sd = {}, {}
        for k in names:
            v = np.array([r[k] for r in rows], float) if rows else np.zeros(1)
            self.mu[k] = float(v.mean())
            self.sd[k] = float(v.std())

    def z(self, f, names, n, k):
        """{feature: z-score}, shrunk by sample size n (k = size that counts half) and clamped to Z_RANGE."""
        w = n / (n + k) if n > 0 else 0.0
        return {x: min(Z_RANGE[1], max(Z_RANGE[0], w * (f[x] - self.mu[x]) / self.sd[x]))
                if self.sd[x] > 1e-12 else 0.0 for x in names}


# ---------------------------------------------------------------- season context

class Season:
    """Every Lahman number one season needs, plus its era norms."""

    def __init__(self, con, year):
        self.year = year
        self.bat = lahdb.batting(con, year=year)
        self.pit = lahdb.pitching(con, year=year)
        self.fld = lahdb.fielding(con, year=year)
        self.app = lahdb.appearances(con, year)
        self.teams = lahdb.teams(con, year)
        glen = max([t['G'] for t in self.teams] + [1])
        self.min_ab = 150 * glen / 162
        self.min_ip = 30 * glen / 162
        self.min_g = 30 * glen / 162
        lg_of = {}
        for pid, by_team in self.app.items():
            for tid in by_team:
                lg_of.setdefault(pid, next((t['lgID'] for t in self.teams if t['teamID'] == tid), ''))
        self.lg_of = lg_of
        self.nh, self.np_, self.nf = {}, {}, {}
        hq, pq, fq = {}, {}, {}
        for pid, b in self.bat.items():
            f, pa = hit_feats(b)
            if f and _n(b, 'AB') >= self.min_ab and self.primary(pid) != 'P':
                hq.setdefault(lg_of.get(pid, ''), []).append(f)
        for pid, q in self.pit.items():
            f, ip = pit_feats(q)
            if f and ip >= self.min_ip:
                pq.setdefault(lg_of.get(pid, ''), []).append(f)
        for pid, fp in self.fld.items():
            for pos, tot in fld_by_pos(fp).items():
                f, g = fld_feats(tot)
                if f and g >= self.min_g:
                    fq.setdefault(pos, {}).setdefault(lg_of.get(pid, ''), []).append(f)
        self.nh = self._norms(hq, FEAT_H)
        self.np_ = self._norms(pq, FEAT_P)
        self.nf = {pos: self._norms(v, FEAT_F) for pos, v in fq.items()}

    @staticmethod
    def _norms(by_lg, names):
        allrows = [r for v in by_lg.values() for r in v]
        out = {'': Norm(allrows, names)}
        for lg, rows in by_lg.items():
            if lg and len(rows) >= MIN_LEAGUE:
                out[lg] = Norm(rows, names)
        return out

    def norm(self, table, pid):
        return table.get(self.lg_of.get(pid, ''), table[''])

    def games_at(self, pid):
        g = {}
        for row in self.app.get(pid, {}).values():
            for col, pos in APP_POS:
                g[pos] = g.get(pos, 0) + _n(row, col)
            if not any(_n(row, c) for c, _ in APP_POS[6:]) and _n(row, 'G_of'):
                g['CF'] = g.get('CF', 0) + _n(row, 'G_of')
        return g

    def primary(self, pid):
        """Game position: the spot with the most games; DH-only and unknown players play 1B."""
        g = self.games_at(pid)
        best = max(g.items(), key=lambda kv: (kv[1], -POS_CODE[kv[0]]), default=('1B', 0))
        return best[0] if best[1] > 0 else '1B'


# ---------------------------------------------------------------- model

def _ols(X, y):
    w, *_ = np.linalg.lstsq(np.asarray(X, float), np.asarray(y, float), rcond=None)
    return w


def _clamp(v, lo=1, hi=99):
    return int(max(lo, min(hi, round(float(v)))))


def _row(feats, quad):
    return [1.0] + list(feats) + ([feats[0] ** 2] if quad else [])


class Model:
    def __init__(self):
        self.w = {}            # target name -> weights (intercept first)
        self.raw_mu = {}       # raw pitcher rate-stat means, 1996 IP >= 30 (shrinkage target)
        self.donors_h = []     # (pos code, age, (ch, ph, sp), record)
        self.donors_p = []     # (age, (en, co, k), record)

    # -------------------------------------------------- fit on MLBPA96E vs 1996
    @classmethod
    def fit(cls, pyr_path, con):
        m = cls()
        _, recs = read_pyr(pyr_path)
        s = Season(con, 1996)
        people = {}
        for pid, f, l, by, bm, bd in con.execute(
                'select playerID,nameFirst,nameLast,birthYear,birthMonth,birthDay from people'):
            people.setdefault(((f or '').lower(), (l or '').lower()), []).append((pid, by, bm, bd))
        H, P, F = [], [], {}
        m.raw_mu = {}
        for q in s.pit.values():
            f, ip = pit_feats(q)
            if f and ip >= 30:
                for x in FEAT_P:
                    m.raw_mu.setdefault(x, []).append(f[x])
        m.raw_mu = {x: float(np.mean(v)) for x, v in m.raw_mu.items()}
        for p in recs:
            born = from_serial(struct.unpack_from('<I', p, 26)[0])
            age = 1996 - born.year
            if p[68] == 1:
                m.donors_p.append((age, (p[CUR + EN], p[CUR + CO], p[K_ATTR]), p))
            elif 2 <= p[68] <= 9:
                m.donors_h.append((p[68], age, (p[CUR + CH], p[CUR + PH], p[CUR + SP]), p))
            c = [x for x in people.get((cstr(p[30:47]).lower(), cstr(p[47:64]).lower()), [])
                 if x[1] and abs(x[1] - born.year) <= 1]
            if len(c) > 1:
                c = [x for x in c if (x[1], x[2], x[3]) == (born.year, born.month, born.day)] or c
            if len(c) != 1:
                continue
            lid = c[0][0]
            b, q = s.bat.get(lid), s.pit.get(lid)
            if p[68] != 1 and b and _n(b, 'AB') >= 150:
                f, pa = hit_feats(b)
                H.append((s.norm(s.nh, lid).z(f, FEAT_H, pa, SHRINK_H), f, p))
            if p[68] == 1 and q and _n(q, 'IPouts') >= 90:
                f, ip = pit_feats(q)
                P.append((s.norm(s.np_, lid).z(f, FEAT_P, ip, SHRINK_P), m._shrunk(f, ip, SHRINK_P), p))
            if p[68] != 1:
                for pos, tot in fld_by_pos(s.fld.get(lid, {})).items():
                    f, g = fld_feats(tot)
                    if f and g >= 30 and pos in s.nf and pos != 'P':
                        F.setdefault(pos, []).append((s.norm(s.nf[pos], lid).z(f, FEAT_F, g, SHRINK_F), p))
        for name, (role, off, feats, quad, raw) in TARGETS.items():
            rows = H if role == 'h' else P
            X = [_row([(r[1] if raw else r[0])[x] for x in feats], quad) for r in rows]
            m.w[name] = _ols(X, [r[2][off] for r in rows])
        for pos, rows in F.items():
            m.w['F' + pos] = _ols([[1.0] + [z[x] for x in FEAT_F] for z, _ in rows],
                                  [p[CUR + FLD0 + POS_CODE[pos] - 1] for _, p in rows])
        return m

    def predict(self, name, z, raw, n, k):
        """One fitted rating (unclamped) from a player's z-scores and raw rate stats; n/k shrink raw features toward
        the 1996 mean the same way Norm.z shrinks z-scores toward 0."""
        _, _, feats, quad, is_raw = TARGETS[name]
        if is_raw:
            sh = self._shrunk(raw, n, k)
            vals = [sh[x] for x in feats]
        else:
            vals = [z.get(x, 0.0) for x in feats]
        return float(np.dot(self.w[name], _row(vals, quad)))

    def _shrunk(self, raw, n, k):
        """Raw pitcher rate stats pulled toward the 1996 mean (IP >= 30) by n/(n+k)."""
        w = n / (n + k) if n > 0 and raw else 0.0
        return {x: self.raw_mu[x] + w * ((raw or {}).get(x, self.raw_mu[x]) - self.raw_mu[x]) for x in self.raw_mu}

    # -------------------------------------------------- donors
    def _donor_h(self, pos, age, want):
        pool = [d for d in self.donors_h if d[0] == pos] or self.donors_h
        return min(pool, key=lambda d: (sum(abs(a - b) for a, b in zip(d[2], want)) + 2 * abs(d[1] - age),
                                        struct.unpack_from('<H', d[3], 0)[0]))[3]

    def _donor_p(self, age, want):
        return min(self.donors_p, key=lambda d: (sum(abs(a - b) for a, b in zip(d[1], want)) + 2 * abs(d[0] - age),
                                                 struct.unpack_from('<H', d[2], 0)[0]))[2]

    # -------------------------------------------------- one player
    def rate(self, s, lid, person, new_id, seasons_before):
        """The plain 192-byte PYR record for Lahman player `lid` in season `s` (a Season)."""
        y = s.year
        by = person.get('birth_year') or (y - 27)
        bm = person.get('birth_month') or 7
        bd = person.get('birth_day') or 1
        try:
            born = datetime.date(by, bm, bd)
        except ValueError:
            born = datetime.date(by, bm if 1 <= bm <= 12 else 7, 1)
        age = y - born.year
        pos = s.primary(lid)
        code = POS_CODE[pos]
        b, q = s.bat.get(lid, {}), s.pit.get(lid, {})
        fitted = {}
        if code == 1:
            f, ip = pit_feats(q)
            z = s.norm(s.np_, lid).z(f, FEAT_P, ip, SHRINK_P) if f else {}
            fitted = {TARGETS[t][1]: self.predict(t, z, f, ip, SHRINK_P) for t in ('EN', 'CO')}
            k = _clamp(self.predict('K', z, f, ip, SHRINK_P))
            base = bytearray(self._donor_p(age, (_clamp(fitted[CUR + EN]), _clamp(fitted[CUR + CO]), k)))
            base[K_ATTR] = k
        else:
            f, pa = hit_feats(b)
            z = s.norm(s.nh, lid).z(f, FEAT_H, pa, SHRINK_H) if f else {}
            fitted = {TARGETS[t][1]: self.predict(t, z, f, pa, SHRINK_H) for t in ('CH', 'PH', 'SP')}
            base = bytearray(self._donor_h(code, age, tuple(_clamp(fitted[CUR + i]) for i in (CH, PH, SP))))
            base[GF_ATTR] = _clamp(self.predict('GF', z, f, pa, SHRINK_H))
            played = s.games_at(lid)
            for fpos, tot in fld_by_pos(s.fld.get(lid, {})).items():
                key = 'F' + fpos
                if fpos == 'P' or key not in self.w or fpos not in s.nf:
                    continue
                if fpos in ('LF', 'CF', 'RF') and played.get(fpos, 0) == 0 and \
                        any(played.get(o, 0) for o in ('LF', 'CF', 'RF')):
                    continue
                ff, g = fld_feats(tot)
                if ff:
                    fz = s.norm(s.nf[fpos], lid).z(ff, FEAT_F, g, SHRINK_F)
                    fitted[CUR + FLD0 + POS_CODE[fpos] - 1] = float(np.dot(self.w[key], [1.0] + [fz[x] for x in FEAT_F]))
        donor = bytes(base)
        for off, v in fitted.items():
            cur = _clamp(v)
            gap = max(0, donor[off - 0x17] - donor[off])
            base[off] = cur
            base[off - 0x17] = min(99, cur + gap)
        rec = bytearray(REC)
        rec[PEAK:0x8d] = base[PEAK:0x8d]
        struct.pack_into('<H', rec, 0, new_id)
        struct.pack_into('<I', rec, 26, serial(born))
        for off, txt in ((30, person.get('first') or ''), (47, person.get('last') or '')):
            raw = txt.encode('latin-1', 'replace')[:16]
            rec[off:off + len(raw)] = raw
        rec[64] = min(255, seasons_before + 1)
        rec[65] = {'L': 1, 'R': 2, 'B': 3}.get(person.get('bats') or '', 2)
        rec[66] = 1 if person.get('throws') == 'L' else 2
        rec[67], rec[69] = donor[67], donor[69]
        rec[68] = code
        rec[0x96] = min(255, 51 + rec[CUR + EN])
        return bytes(rec)
