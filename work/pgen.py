#!/usr/bin/env python3
"""Read/write codec for the player-generator DAT entries of SHELL.VOL (FPS Baseball Pro '98).

    python3 pgen.py decode NAME in.bin out.json
    python3 pgen.py encode NAME in.bin edited.json out.bin

NAME: PGENFRST.DAT, PGENLAST.DAT (name pools), PGEND.DAT, PGENTABL.DAT (two generators), AGEPLYR.DAT (aging),
SPRPLYR.DAT (spring training). Keys starting with "_" are DERIVED (tags, runtime counters, unread bytes); every other
leaf is content. Layout: work/spec/PGEN_FORMAT.md. Every field below is pinned to the BBShell code that reads it.

Player-record offsets ("pyr46" = byte +0x46 of the in-memory player, the same layout as a PYR record): +0x1a birth day
number, +0x1e/+0x2f first/last name, +0x41 bats (1 L, 2 R, 3 S), +0x42 throws (1 L, 2 R), +0x44 position, +0x46..+0x5c
23 peak ratings with the matching current rating 0x17 bytes later (+0x5d..+0x73): +0x4d..+0x53 the 7 pitch slots,
+0x54..+0x5c fielding at P..RF; +0x74..+0x8c single attributes.
"""
import json
import struct
import sys

POS = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]          # position codes 1..9

# ---------------------------------------------------------------- fixed-layout engine
# A node is a scalar type name ('s8', 'u8', 's16', 'u16', 'u32'), ('list', n, node), or ('obj', [(key, node), ...]).
# Keys starting with "_" are derived: decoded for a lossless rebuild, rewritten from the JSON as given.

FMT = {'s8': 'b', 'u8': 'B', 's16': 'h', 'u16': 'H', 'u32': 'I'}


def obj(*fields):
    return ('obj', list(fields))


def keyed(keys, node):
    return ('obj', [(k, node) for k in keys])


def lst(n, node):
    return ('list', n, node)


def size(node):
    if isinstance(node, str):
        return struct.calcsize('<' + FMT[node])
    if node[0] == 'list':
        return node[1] * size(node[2])
    return sum(size(n) for _, n in node[1])


def dec(node, b, p):
    if isinstance(node, str):
        return struct.unpack_from('<' + FMT[node], b, p)[0], p + size(node)
    if node[0] == 'list':
        out = []
        for _ in range(node[1]):
            v, p = dec(node[2], b, p)
            out.append(v)
        return out, p
    out = {}
    for k, n in node[1]:
        out[k], p = dec(n, b, p)
    return out, p


def enc(node, v, out, path='doc'):
    if isinstance(node, str):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError('%s: expected an integer, got %r' % (path, v))
        try:
            out += struct.pack('<' + FMT[node], v)
        except struct.error:
            raise ValueError('%s: %r does not fit %s' % (path, v, node))
    elif node[0] == 'list':
        if not isinstance(v, list) or len(v) != node[1]:
            raise ValueError('%s: expected a list of %d' % (path, node[1]))
        for i, x in enumerate(v):
            enc(node[2], x, out, '%s[%d]' % (path, i))
    else:
        if not isinstance(v, dict):
            raise ValueError('%s: expected an object' % path)
        for k, n in node[1]:
            if k not in v:
                raise ValueError('%s: missing key %r' % (path, k))
            enc(n, v[k], out, '%s.%s' % (path, k))


def layout(fields, total):
    """fields: [(offset, key, node)]; checks the offsets tile 0..total exactly."""
    p = 0
    for off, key, node in fields:
        assert off == p, 'layout gap/overlap at %s: 0x%x != 0x%x' % (key, off, p)
        p += size(node)
    assert p == total, 'layout ends at 0x%x, want 0x%x' % (p, total)
    return obj(*[(k, n) for _, k, n in fields])


def decode_fixed(schema, b):
    doc, p = dec(schema, b, 0)
    assert p == len(b), 'decoded 0x%x of 0x%x bytes' % (p, len(b))
    return doc


def encode_fixed(schema, doc):
    out = bytearray()
    enc(schema, doc, out)
    return bytes(out)


# Dice: FUN_6805c490(base, count, sides) = base + count rolls of 1..sides (PGEND, AGEPLYR order).
DICE = obj(('base', 's8'), ('count', 's8'), ('sides', 's8'))
# PGENTABL's FUN_6806a850(count, sides, base) stores the same thing in a different order.
DICE_CSB = obj(('count', 's8'), ('sides', 's8'), ('base', 's8'))
CHANCE = obj(('num', 's8'), ('den', 's8'))          # FUN_6805c470(num, den): true with probability num/den
TAG = 'u16'                                        # 0x07d1 section tag, never read

# ---------------------------------------------------------------- PGEND.DAT (generator FUN_68068370)
# File: "PGD:" + u32 record size + 0x3aa-byte record (loader FUN_68068680) + 1 unread byte.

PGD_PRIMARY = ['pyr46', 'pyr47', 'pyr48', 'ownPositionFielding', 'pyr49']
PGD_SECONDARY = ['pyr4b', 'pyr4c', 'pyr4a', 'pyr77', 'pitcherPyr49']
PGD_REC = layout([
    (0x000, '_runtimeDrawCounts', keyed(POS + ['total'], 'u32')),          # FUN_68068760 counts draws per position
    (0x028, 'talentDice', keyed(['pool0', 'pool2', 'pool1'], DICE)),        # FUN_68068960 by generator pool
    (0x031, 'talentFloor', 's8'),                                           # talent below this: reroll with ...
    (0x032, 'talentFloorDice', DICE),
    (0x035, 'positionWeights', keyed(POS, 's8')),                           # roll 1..200 walks the running sum
    (0x03e, 'pitcherSecondary', obj(('chance', CHANCE), ('ratio', CHANCE), ('elseDice', DICE))),   # FUN_680689d0
    (0x045, 'fielderSecondary', obj(('chance', CHANCE), ('ratio', CHANCE))),
    (0x049, 'primaryTierWeights', keyed(POS, keyed(PGD_PRIMARY, 's16'))),  # FUN_68068aa0 -> FUN_68069920
    (0x0a3, 'secondaryTierWeights', keyed(['pitcher', 'fielder'], keyed(PGD_SECONDARY, 's16'))),
    (0x0b7, 'batsThrows', keyed(POS, lst(6, obj(('bats', 's8'), ('throws', 's8'), ('weight', 's8'))))),  # FUN_680687b0
    (0x159, 'pyr45Table', lst(2, obj(('value', 's8'), ('weight', 's8')))),  # FUN_68068800
    (0x15d, 'pyr43Table', lst(3, obj(('value', 's8'), ('weight', 's8')))),  # FUN_68068850
    (0x163, 'birthYearsBackDice', keyed(['pool0', 'pool2', 'pool1'], DICE)),    # FUN_680688a0
    (0x16c, 'leftyShift', obj(('pyr77Below', 's8'), ('pyr4cAbove', 's8'), ('shift', 's8'))),   # FUN_68068c70
    (0x16f, 'pitchCount', obj(('pointsPerPitch', 's8'), ('min', 's8'), ('max', 's8'))),       # FUN_68068d80
    (0x172, 'pitcherSecondaryBonus', 's8'),                                 # FUN_680689d0
    (0x173, 'pyr4bNudge', obj(('downFrom', 's8'), ('downTo', 's8'), ('upFrom', 's8'), ('upTo', 's8'),
                              ('chance', CHANCE), ('dice', DICE))),         # FUN_68068cc0
    (0x17c, 'pitchWeights', keyed(['throwsL_pyr45is0', 'throwsL_pyr45is1', 'throwsR_pyr45is0', 'throwsR_pyr45is1'],
                                  lst(7, 's16'))),                          # FUN_68068d80 row throws*2+pyr45
    (0x1b4, 'currentFromPeak', obj(('pctA', DICE), ('pctB', DICE), ('pctC', DICE),
                                   ('minusA', DICE), ('minusB', DICE), ('minusC', DICE))),   # FUN_68068f00
    (0x1c6, 'attributeDice', obj(('pyr7dTo82And87To8c', DICE), ('pyr75And78', DICE), ('pyr7cAnd86', DICE),
                                 ('pyr7aAnd84', DICE), ('pyr7bAnd85', DICE), ('pyr74', DICE))),   # FUN_68069140
    (0x1d8, 'pyr79ByBats', obj(('L', obj(('dice', DICE), ('redoDice', DICE), ('redoBelow', 's8'))),
                               ('R', obj(('dice', DICE), ('redoDice', DICE), ('redoAbove', 's8'))),
                               ('S', obj(('dice', DICE))))),
    (0x1e9, 'pyr83ByThrows', obj(('L', obj(('dice', DICE), ('redoDice', DICE), ('redoBelow', 's8'))),
                                 ('R', obj(('dice', DICE), ('redoDice', DICE), ('redoAbove', 's8'))))),
    (0x1f7, 'agingDice', DICE),                                             # FUN_68069550
    (0x1fa, 'agingCurve', lst(32, lst(8, 's8'))),                           # row i = age 18+i
    (0x2fa, 'developBlendPct', 's8'),                                       # FUN_680697b0
    (0x2fb, 'developDraws', 's8'),
    (0x2fc, 'otherPositionPct', keyed(POS, keyed(POS, 'u8'))),              # FUN_68068b30, 0 = leave alone
    (0x34d, 'positionReroll', keyed(POS, obj(('chancePct', 'u8'), ('weights', keyed(POS, 'u8'))))),  # FUN_68068b90
    (0x3a7, 'positionRerollDice', DICE),
], 0x3aa)
PGD_FILE = layout([
    (0, '_magic', lst(4, 'u8')),
    (4, '_recordSize', 'u32'),
    (8, 'record', PGD_REC),
    (0x3b2, '_unreadTrailingByte', 'u8'),
], 0x3b3)


def decode_pgend(b):
    doc = decode_fixed(PGD_FILE, b)
    if bytes(doc['_magic']) != b'PGD:' or doc['_recordSize'] != 0x3aa:
        raise ValueError('not a PGD: record')
    doc['_magic'] = 'PGD:'
    return doc


def encode_pgend(doc):
    doc = dict(doc, _magic=list(b'PGD:'), _recordSize=0x3aa)
    return encode_fixed(PGD_FILE, doc)


# ---------------------------------------------------------------- PGENTABL.DAT (generator FUN_68069b00)
# Raw 0x6d2-byte read into DAT_6808caa0 (FUN at 0x6806a330) + 1 unread byte. 0x07d1 tags separate sections.

# FUN_6806a5f0: one rating = (peak -> param_4, current -> param_5); peak clamps to [floor, 99], current <= peak.
SPEC = obj(
    ('_tag', 'u8'),                     # 0x69, never read
    ('rollPeak', 'u8'),                 # 1: peak starts as baseDice, else 0
    ('baseDice', DICE_CSB),
    ('adjustWhen', 'u8'),               # 0 never, 1 always, 2 if peak < adjustLimit, 3 if peak > adjustLimit
    ('adjustLimit', 's8'),
    ('adjustMode', 'u8'),               # 1 reroll adjustDice; 2 abs(peak); 3 abs(peak)+adjust[0]; 4 add adjust[bats-1]
    ('adjust', lst(3, 's8')),           # mode 1: count, sides, base
    ('currentMode', 'u8'),              # 0 = peak; 1 peak * (roll in ageCurrentPct[age])%; 2 peak * (roll lo..hi)%;
    ('current', lst(2, 's8')),          # 3 peak * (current[1]*age + current[0])%
)
SPEC_GROUP_A = [  # 0x14e..0x265, in file order (ownPositionFielding -> pyr53+pos, the others via otherPositionPct)
    'pyr46_fielder', 'pyr46_fielderMode2', 'pyr46_pitcher', 'pyr47_fielder', 'pyr47_fielderMode2', 'pyr47_pitcher',
    'pyr49', 'ownPositionFielding', 'pyr74', 'pyr75', 'pyr79', 'pyr7b', 'pyr7c', 'pyr7a', 'pyr7d', 'pyr7e', 'pyr7f',
    'pyr80', 'pyr81', 'pyr82',
]
SPEC_GROUP_B = [  # 0x268..0x3d3
    'pyr4a_fielder', 'pyr4a_pitcher', 'pyr4a_pitcherMode2',
    'pyr4c_fielder', 'pyr4c_pitcher', 'pyr4c_pitcherMode2',
    'pyr77_fielder', 'pyr77_pitcher', 'pyr77_pitcherMode2',
    'pyr76_fielder', 'pyr76_pitcher', 'pyr76_pitcherMode2',
    'pyr4b_fielder', 'pyr4b_pitcher', 'pyr4b_pitcherMode2',
    'pyr78', 'pyr83', 'pyr85', 'pyr86', 'pyr84', 'pyr87', 'pyr88', 'pyr89', 'pyr8a', 'pyr8b', 'pyr8c',
]
COMBOS = ['R/R', 'L/L', 'L/R', 'S/R', 'R/L', 'S/L']          # FUN_6806a540: bats/throws for each threshold
TAB = layout([
    (0x000, '_tag0', TAG),
    (0x002, 'ageBySlot', keyed(['slot%02d' % i for i in range(100)], 's8')),          # FUN_6806ad00, generator mode != 2
    (0x066, '_tag1', TAG),
    (0x068, 'ageBySlotMode2', keyed(['slot%02d' % i for i in range(100)], 's8')),     # generator mode 2
    (0x0cc, '_tag2', TAG),
    (0x0ce, 'monthDays', keyed(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'],
                               's8')),                                                # not read by the generator
    (0x0da, '_tag3', TAG),
    (0x0dc, 'batsThrowsUpTo', keyed(POS, keyed(COMBOS, 's8'))),       # cumulative, roll 1..100
    (0x112, '_tag4', TAG),
    (0x114, 'pyr45Threshold', 's8'),                                  # pyr45 = (roll 1..100 > this)
    (0x115, 'pyr43Threshold', 's8'),                                  # pyr43 = 0xff if roll <= this
    (0x116, '_tag5', TAG),
    (0x118, 'positionRollMax', 's8'),                                 # FUN_6806a3e0: roll 0..max over the weights
    (0x119, 'positionWeights', keyed(POS, 's8')),
    (0x122, '_runtimeDraws', obj(('total', 'u32'), ('byPosition', keyed(POS, 'u32')), ('roundRobin', 'u16'))),
    (0x14c, '_tag6', TAG),
    (0x14e, 'ratingSpecs', keyed(SPEC_GROUP_A, SPEC)),
    (0x266, '_tag7', TAG),
    (0x268, 'ratingSpecs2', keyed(SPEC_GROUP_B, SPEC)),
    (0x3d4, '_tag8', TAG),
    (0x3d6, 'pyr48ByPosition', keyed(POS, SPEC)),                     # this + pos*14 + 0x3c8
    (0x454, '_tag9', TAG),
    (0x456, 'otherPositionPct', keyed(POS, keyed(POS, 's8'))),        # read with movsx: bytes > 127 are negative
    (0x4a7, 'otherPositionCurrentPct', obj(('min', 's8'), ('max', 's8'))),
    (0x4a9, '_pad', 'u8'),
    (0x4aa, '_tag10', TAG),
    (0x4ac, 'ageCurrentPctAges', obj(('minAge', 's8'), ('maxAge', 's8'))),
    (0x4ae, 'ageCurrentPct', lst(12, obj(('min', 's8'), ('max', 's8')))),   # entry i = age minAge+i
    (0x4c6, '_tag11', TAG),
    (0x4c8, 'pitchBrackets', lst(5, obj(('pointsFrom', 'u16'), ('pointsUpTo', 's16'),
                                        ('pitchMaskByRoll', keyed(['roll%03d' % i for i in range(1, 101)], 'u8'))))),
    (0x6d0, '_tag12', TAG),
    (0x6d2, '_unreadTrailingByte', 'u8'),
], 0x6d3)


def decode_pgentabl(b):
    doc = decode_fixed(TAB, b)
    lo = doc['ageCurrentPctAges']['minAge']
    for i, a in enumerate(doc['ageCurrentPct']):
        a['_age'] = lo + i
    return doc


def encode_pgentabl(doc):
    return encode_fixed(TAB, doc)


# ---------------------------------------------------------------- AGEPLYR.DAT (FUN_68054990 reads 0x103; FUN_68056210)

AGE = layout([
    (0x000, 'agingCurve', lst(32, lst(8, 's8'))),      # row i = age 18+i, 8 rating classes
    (0x100, 'agingDice', DICE),                        # added to every delta
    (0x103, '_unreadTrailingByte', 'u8'),
], 0x104)

# ---------------------------------------------------------------- SPRPLYR.DAT (FUN_68054a70 reads 0x6b; FUN_68056320)
# change = rows[rowByRating[k]][value // 5]; row 3 scales (peak - current), the others peak.

SPR = layout([
    (0x00, 'rowByRating', keyed(['rating%02d' % k for k in range(23)], 's8')),
    (0x17, 'rows', lst(4, lst(21, 's8'))),
    (0x6b, '_unreadTrailingByte', 'u8'),
], 0x6c)

# ---------------------------------------------------------------- name pools (FUN_6806ac30)
# u32 magic 0x12345678, u32 dataSize, u32 count, u32 recordSize, count NUL-padded records, 1 unread byte. The generator
# draws a record uniformly, so duplicates are selection weights.

NAME_MAGIC = 0x12345678


def decode_names(b):
    magic, data_size, count, rec = struct.unpack_from('<IIII', b, 0)
    if magic != NAME_MAGIC or 16 + data_size + 1 != len(b) or data_size != count * rec:
        raise ValueError('not a name pool')
    names = [b[16 + i * rec:16 + (i + 1) * rec].split(b'\0', 1)[0].decode('latin1') for i in range(count)]
    return {'_recordSize': rec, '_unreadTrailingByte': b[-1], 'names': names}


def encode_names(doc):
    names = doc['names']
    raw = [n.encode('latin1') for n in names]
    rec = max([len(r) + 1 for r in raw] + [doc.get('_recordSize', 1)])
    out = bytearray(struct.pack('<IIII', NAME_MAGIC, len(raw) * rec, len(raw), rec))
    for r in raw:
        if b'\0' in r:
            raise ValueError('NUL inside a name')
        out += r.ljust(rec, b'\0')
    out.append(doc.get('_unreadTrailingByte', 0))
    return bytes(out)


CODECS = {
    'PGENFRST.DAT': (decode_names, encode_names),
    'PGENLAST.DAT': (decode_names, encode_names),
    'PGEND.DAT': (decode_pgend, encode_pgend),
    'PGENTABL.DAT': (decode_pgentabl, encode_pgentabl),
    'AGEPLYR.DAT': (lambda b: decode_fixed(AGE, b), lambda d: encode_fixed(AGE, d)),
    'SPRPLYR.DAT': (lambda b: decode_fixed(SPR, b), lambda d: encode_fixed(SPR, d)),
}


def main(argv):
    if len(argv) < 5 or argv[1] not in ('decode', 'encode') or argv[2].upper() not in CODECS:
        sys.stderr.write(__doc__)
        return 2
    dec_f, enc_f = CODECS[argv[2].upper()]
    if argv[1] == 'decode':
        with open(argv[3], 'rb') as f:
            doc = dec_f(f.read())
        with open(argv[4], 'w') as f:
            json.dump(doc, f, indent=1)
    else:
        if len(argv) < 6:
            sys.stderr.write(__doc__)
            return 2
        with open(argv[4]) as f:
            doc = json.load(f)
        with open(argv[5], 'wb') as f:
            f.write(enc_f(doc))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
