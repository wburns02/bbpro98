#!/usr/bin/env python3
"""Semantic read/write codec for the FPS Baseball Pro '98 stats database (Stats/mlbpa97.DAT).

The file is a FairCom c-tree Plus superfile (container notes: re/targets/ctree/lanes/data/FORMAT.md).
Every live data record whose payload is 22/36/40/70/150 bytes of u16 words with word0 (scope) in
{0,1,2,3,16,17} and word1 == 2 is a stat record:

  word0 = scope    word1 = 2 (constant)    word2 = player id (>=100) or team id (<100)
  word3.. = the stat fields (one u16 per field)

Scopes: 0 = last 7 days (rolling window), 1 = this season, 2 = career, 3 = last season (1996),
16/17 = pre-game matchup snapshots for teams (16 = upcoming opponent's totals, 17 = own totals
stored in the mirrored frame; refreshed on game days).

Each stat table lives in its own c-tree member, and the member number encodes the split:

  member  6  40-byte batting line        (season/recent/career/last-season lines)
  member 28  70-byte pitching line
  member  4  150-byte fielding line      (9 position blocks of 8 fields)
  members  8..26 even  22-byte batting splits:  8 vs LHP, 10 home, 12 scoring pos,
                                               14 close&late, 16 Apr, 18 May, 20 Jun,
                                               22 Jul, 24 Aug, 26 Sep/Oct
  members 30..48 even  36-byte pitching splits: 30 vs LHB, 32 home, 34 scoring pos,
                                               36 close&late, 38 Apr, 40 May, 42 Jun,
                                               44 Jul, 46 Aug, 48 Sep/Oct

decode: python3 stats.py decode in.bin out.json
encode: python3 stats.py encode in.bin edited.json out.bin   (in-place payload rewrite,
same file length; encode(x, decode(x)) == x byte for byte)
"""
import json
import struct
import sys

# ---------------------------------------------------------------- c-tree container (inlined)

REC_HDR = 18


class Rec:
    __slots__ = ('hdr', 'pl', 'mem', 'prev')

    def __init__(self, hdr, pl, mem, prev):
        self.hdr = hdr
        self.pl = pl
        self.mem = mem
        self.prev = prev

    @property
    def off(self):
        return self.hdr + REC_HDR


def scan_records(d):
    """Sequential FA FA walk (exactly the referee's scanner)."""
    recs = []
    i, n = 0, len(d)
    while i < n - 20:
        if d[i] == 0xfa and d[i + 1] == 0xfa:
            tot, pl = struct.unpack_from('<II', d, i + 2)
            if tot == pl + 18 and 0 < pl < 2000 and i + 18 + pl <= n:
                recs.append(Rec(i, pl, struct.unpack_from('<I', d, i + 10)[0],
                                struct.unpack_from('<I', d, i + 14)[0]))
                i += tot
                continue
        i += 1
    return recs


def stat_records(d):
    """{payload offset: (member, words)} for every live stat record.

    A record is stat-shaped when its payload is 22/36/40/70/150 bytes of u16 words with
    word0 in {0,1,2,3,16,17} and word1 == 2.  Live = not a tombstone (payload[0] != 0xff)
    and not structural (member 0 = descriptors, member 1 = directory; every index-member
    record is a 494-byte B-tree node, which the shape filter rejects anyway).
    """
    out = {}
    for r in scan_records(d):
        if r.mem in (0, 1) or d[r.off] == 0xFF:
            continue
        p = d[r.off:r.off + r.pl]
        if len(p) in (22, 36, 40, 70, 150):
            u = struct.unpack('<%dH' % (len(p) // 2), p)
            if u[0] in (0, 1, 2, 3, 16, 17) and u[1] == 2:
                out[r.off] = (r.mem, u)
    return out


# ---------------------------------------------------------------- stat semantics

# 40-byte batting line: word3.. = these 17 fields (verified vs the game's Statistics screen
# and vs day-by-day box-score sums; H = h1b+h2b+h3b+hr is never stored).
BAT = ('ab', 'h1b', 'h2b', 'h3b', 'hr', 'rbi', 'bb', 'so', 'ibb', 'hbp', 'sh', 'sf',
       'g', 'r', 'sb', 'cs', 'gidp')
# 70-byte pitching line: f0..f16 = the opponent batting line (same slots as BAT),
# then games finished, outs (IP*3), batters faced, W, L, saves, complete games, shutouts,
# quality starts, earned runs, inherited runners, inherited runners scored, holds,
# save opportunities, wild pitches (stat-name enum order G GS GF IP BFP W L Sv ... ER IR IRS
# Hld SvOp WP).
PIT = BAT + ('gf', 'outs', 'bfp', 'w', 'l', 'sv', 'cg', 'sho', 'qs', 'er',
             'ir', 'irs', 'hld', 'svop', 'wp')
# 22-byte batting split: first 8 batting columns.
SPLIT_BAT = ('ab', 'h1b', 'h2b', 'h3b', 'hr', 'rbi', 'bb', 'so')
# 36-byte pitching split: opponent line + games, games started, outs, W, L, saves, ER.
SPLIT_PIT = ('ab', 'h1b', 'h2b', 'h3b', 'hr', 'rbi', 'bb', 'so',
             'g', 'gs', 'outs', 'w', 'l', 'sv', 'er')
# 150-byte fielding line: 9 blocks (P C 1B 2B 3B SS LF CF RF) of 8 fields: outs played
# (3x innings), games started (always 0 in observed files), games at the position,
# putouts, assists, errors, double plays, passed balls (catchers only).
POS_IDS = ('p', 'c', 'b1', 'b2', 'b3', 'ss', 'lf', 'cf', 'rf')
FLD_BLOCK = ('outs', 'gs', 'g', 'po', 'a', 'e', 'dp', 'pb')
FIELDING = tuple('%s_%s' % (pos, f) for pos in POS_IDS for f in FLD_BLOCK)

SCOPE_PERIOD = {0: 'recent', 1: 'season', 2: 'career', 3: 'last_season'}
SCOPE_DOC = {
    0: 'last 7 days (rolling window: day N holds games from day N-6)',
    1: 'this season', 2: 'career', 3: 'last season (1996)',
    16: 'pre-game matchup snapshot: the upcoming opponent\'s totals',
    17: 'pre-game matchup snapshot: own totals in the mirrored frame '
        '(bat-table member holds the batters we face, pit-table member holds our batters)',
}
BAT_SPLITS = {8: 'vs_lhp', 10: 'home', 12: 'scoring_pos', 14: 'close_late',
              16: 'april', 18: 'may', 20: 'june', 22: 'july', 24: 'august', 26: 'sept_oct'}
PIT_SPLITS = {30: 'vs_lhb', 32: 'home', 34: 'scoring_pos', 36: 'close_late',
              38: 'april', 40: 'may', 42: 'june', 44: 'july', 46: 'august', 48: 'sept_oct'}


def classify(mem, ln, scope):
    """(kind, period, field-name tuple) for one stat record."""
    if scope in (16, 17):
        period = 'matchup'
    else:
        period = SCOPE_PERIOD[scope]
    if ln == 22:
        return ('preview_bat_split' if scope in (16, 17) else 'bat_split', period, SPLIT_BAT)
    if ln == 36:
        return ('preview_pit_split' if scope in (16, 17) else 'pit_split', period, SPLIT_PIT)
    if ln == 40:
        return ('preview_bat' if scope in (16, 17) else 'bat', period, BAT)
    if ln == 70:
        return ('preview_pit' if scope in (16, 17) else 'pit', period, PIT)
    return ('preview_fielding' if scope in (16, 17) else 'fielding', period, FIELDING)


def table_of(mem, ln):
    if ln == 22:
        return BAT_SPLITS.get(mem, 'm%d' % mem)
    if ln == 36:
        return PIT_SPLITS.get(mem, 'm%d' % mem)
    return {4: 'fielding', 6: 'batting', 28: 'pitching'}.get(mem, 'm%d' % mem)


# ---------------------------------------------------------------- commands

def cmd_decode(inp, outp):
    with open(inp, 'rb') as fh:
        d = fh.read()
    recs = []
    for off, (mem, u) in sorted(stat_records(d).items()):
        ln = len(u) * 2
        kind, period, names = classify(mem, ln, u[0])
        rec = {
            'off': off,
            'member': mem,
            'table': table_of(mem, ln),
            'scope': u[0],
            'scope_doc': SCOPE_DOC[u[0]],
            'pid': u[2],
            'kind': kind,
            'period': period,
            'fields': {n: v for n, v in zip(names, u[3:])},
        }
        if u[0] in (16, 17):
            rec['note'] = 'matchup scratch record refreshed on game days'
        recs.append(rec)
    doc = {
        'records': recs,
        'container': {
            'format': 'FairCom c-tree Plus superfile (FPS Baseball Pro 98 stats database)',
            'bytes': len(d),
            'stat_records': len(recs),
        },
        'scopes': {str(k): v for k, v in SCOPE_DOC.items()},
        'tables': {
            'batting': 'member 6, 40 bytes: ' + ', '.join(BAT),
            'pitching': 'member 28, 70 bytes: ' + ', '.join(PIT),
            'fielding': 'member 4, 150 bytes: 9 position blocks (p c b1 b2 b3 ss lf cf rf) x '
                        '(outs gs g po a e dp pb)',
            'bat_splits': {str(k): v for k, v in sorted(BAT_SPLITS.items())},
            'pit_splits': {str(k): v for k, v in sorted(PIT_SPLITS.items())},
        },
    }
    with open(outp, 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    return 0


def cmd_encode(inp, jsonp, outp):
    """Rewrite stat values in place.  Fields are matched by NAME (key order is irrelevant,
    omitted fields keep their stored value).  scope and pid are index keys, so they are
    read-only here: change them through work/ctree.py, which rebuilds the B-tree."""
    with open(inp, 'rb') as fh:
        buf = bytearray(fh.read())
    with open(jsonp, 'r') as fh:
        doc = json.load(fh)
    recs = stat_records(bytes(buf))
    for r in doc.get('records', ()):
        off = r.get('off')
        if not isinstance(off, int) or off not in recs:
            raise ValueError('record off=%r is not a live stat record in %s' % (off, inp))
        mem, u = recs[off]
        words = list(u)
        for key, idx in (('scope', 0), ('pid', 2)):
            if key in r and r[key] != u[idx]:
                raise ValueError('off=%d: %s is an index key and cannot change here '
                                 '(%r -> %r); use work/ctree.py' % (off, key, u[idx], r[key]))
        _, _, names = classify(mem, len(u) * 2, u[0])
        slot = {n: 3 + i for i, n in enumerate(names)}
        for name, v in (r.get('fields') or {}).items():
            if name not in slot:
                raise ValueError('off=%d: unknown field %r for this record kind' % (off, name))
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 0xFFFF:
                raise ValueError('off=%d: %s=%r is not a u16' % (off, name, v))
            words[slot[name]] = v
        struct.pack_into('<%dH' % len(words), buf, off, *words)
    with open(outp, 'wb') as fh:
        fh.write(bytes(buf))
    return 0


def main(argv):
    if len(argv) >= 4 and argv[1] == 'decode':
        return cmd_decode(argv[2], argv[3])
    if len(argv) >= 5 and argv[1] == 'encode':
        return cmd_encode(argv[2], argv[3], argv[4])
    sys.stderr.write('usage: stats.py decode in.bin out.json | encode in.bin edited.json out.bin\n')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
