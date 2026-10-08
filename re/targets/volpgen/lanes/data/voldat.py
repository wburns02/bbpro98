#!/usr/bin/env python3
"""Semantic read/write codecs for the DAT entries of FPS Baseball Pro '98 SHELL.VOL.

Usage:
    python3 voldat.py decode NAME in.bin out.json
    python3 voldat.py encode NAME in.bin edited.json out.bin

NAME selects the layout: PGENFRST.DAT, PGENLAST.DAT, PGENTABL.DAT, PGEND.DAT,
AGEPLYR.DAT, SPRPLYR.DAT. Every field is assembled sequentially, so edited
strings may grow or shrink and the encoder recomputes all offsets.

Keys starting with "_" in the JSON are DERIVED (the encoder recomputes them);
every other leaf is editable CONTENT.

Layouts were mapped against the BBShell decompile:
  - pgenFrst/pgenLast loader FUN_6806ac30: 16-byte header (magic 0x12345678,
    data size, record count, record size), then fixed-width NUL-padded name
    records; the game picks one at random, so repetition = selection weight.
  - PGenD loader FUN_68068680 + accessors FUN_68068760..FUN_680697b0 pin record
    fields: position weights at rec+0x35 (they sum to 200 against a 1..200 roll),
    per-position 6-entry weighted pick tables whose weights sum to 100, rating
    percentage profiles (bytes are percent multipliers, FUN_68068b30), and the
    32x8 aging curve, byte-identical to the standalone AGEPLYR.DAT.
  - ageplyr/sprplyr loaders FUN_68054990 / FUN_68054a70 read the file raw
    (0x103 / 0x6b bytes), so those layouts come from the byte patterns.
"""
import json
import struct
import sys

# ---------------------------------------------------------------- helpers

def bytes_to_ints(blob, signed):
    if signed:
        return [b - 256 if b >= 128 else b for b in blob]
    return list(blob)


def ints_to_bytes(values, signed):
    out = bytearray()
    for v in values:
        if signed and v < 0:
            out.append(v + 256)
        else:
            if not 0 <= v <= 255:
                raise ValueError("byte value out of range: %r" % (v,))
            out.append(v)
    return bytes(out)


def words_to_ints(blob):
    return list(struct.unpack("<%dH" % (len(blob) // 2), blob))


def ints_to_words(values):
    return struct.pack("<%dH" % len(values), *values)


def rows_to_bytes(rows, signed):
    return ints_to_bytes([v for row in rows for v in row], signed)


def chunk(values, size):
    return [values[i:i + size] for i in range(0, len(values), size)]


def unchunk(rows):
    return [v for row in rows for v in row]


# ---------------------------------------------------------------- name pools
# PGENFRST.DAT / PGENLAST.DAT (loader FUN_6806ac30): u32 magic 0x12345678,
# u32 dataSize, u32 recordCount, u32 recordSize, then count fixed-width
# NUL-padded name records. The generator draws one at random, so duplicate
# entries act as selection weights.

NAME_MAGIC = 0x12345678


def decode_names(blob):
    magic, data_size, count, rec_size = struct.unpack_from("<IIII", blob, 0)
    if magic != NAME_MAGIC:
        raise ValueError("bad name-pool magic 0x%08x" % magic)
    names = []
    for i in range(count):
        rec = blob[16 + i * rec_size: 16 + (i + 1) * rec_size]
        names.append(rec.split(b"\x00", 1)[0].decode("latin1"))
    end = 16 + data_size
    return {
        "_fileType": "player name pool (the generator draws one record at random; "
                     "duplicate entries act as selection weights)",
        "_header": {
            "magic": "0x12345678",
            "dataSize": data_size,
            "recordCount": count,
            "recordSize": rec_size,
            "note": "derived: encoder recomputes dataSize/count and grows the "
                    "record size only if an edited name no longer fits",
        },
        "_unreadTrailingByte": blob[end] if len(blob) > end else 0,
        "names": names,
    }


def encode_names(doc, blob):
    names = doc["names"]
    floor = doc.get("_header", {}).get("recordSize", 1)
    rec_size = max([len(n) + 1 for n in names] + [floor])
    out = bytearray(struct.pack("<IIII", NAME_MAGIC, len(names) * rec_size,
                                len(names), rec_size))
    for n in names:
        raw = n.encode("latin1")
        if len(raw) + 1 > rec_size:
            raise ValueError("name too long for record size: %r" % n)
        out += raw.ljust(rec_size, b"\x00")
    out += bytes([doc.get("_unreadTrailingByte", 0)])
    return bytes(out)


# ---------------------------------------------------------------- aging table
# AGEPLYR.DAT (loader FUN_68054990 reads 0x103 bytes): a 32x8 signed-byte curve
# of per-year rating adjustments (growth early in a career, decline late), then
# the signed triple (-4, 2, 3) that sits just in front of the same curve inside
# the PGenD record (rec+0x1F7), then one byte the loader never reads.

AGING_ROWS = 32
AGING_COLS = 8


def decode_aging(blob):
    body = blob[:0x103]
    rows = chunk(bytes_to_ints(body[: AGING_ROWS * AGING_COLS], True), AGING_COLS)
    triple = bytes_to_ints(body[0x100:0x103], True)
    return {
        "_fileType": "player aging table: per-year signed rating adjustments",
        "_layoutNote": "32 rows x 8 signed columns, then the signed triple that "
                       "precedes this same curve inside the PGenD record; the "
                       "final file byte lies beyond the 0x103 bytes the game reads",
        "_unreadTrailingByte": blob[0x103],
        "agingCurve": {"rows": rows},
        "agingRollRange": triple,
    }


def encode_aging(doc, blob):
    out = rows_to_bytes(doc["agingCurve"]["rows"], True)
    if len(out) != AGING_ROWS * AGING_COLS:
        raise ValueError("agingCurve must stay 32 rows of 8")
    out += ints_to_bytes(doc["agingRollRange"], True)
    out += bytes([doc["_unreadTrailingByte"]])
    return bytes(out)


# ---------------------------------------------------------------- spring table
# SPRPLYR.DAT (loader FUN_68054a70 reads 0x6b bytes). Small constant base
# groups, then four progression lookup ramps, each preceded by a geometric
# negative head (-20,-10 / -5,0 / -80,-40,-20,-10 / -50,-25): a linear +5 ramp
# to 90, a doubling 1,2,4..68 ramp, a linear +3 ramp to 48 and a saturating
# ramp 35,40,..90,92,94,96,98,99,100. Ramps are presented in rows of 8.

SPRING_FIELDS = [
    ("bytes", 3, "baseGroup2s", False),
    ("bytes", 4, "baseGroup2sPad", False),
    ("bytes", 7, "baseGroup3s", False),
    ("bytes", 1, "baseGroup3sPad", False),
    ("bytes", 8, "baseGroup1s", False),
    ("bytes", 2, "linearRampHead", True),
    ("bytes", 1, "linearRampSep", False),
    ("rows", 18, 6, "linearRampStep5", False),
    ("bytes", 2, "doublingRampHead", True),
    ("rows", 19, 8, "doublingRamp", False),
    ("bytes", 4, "step3RampHead", True),
    ("bytes", 1, "step3RampSep", False),
    ("rows", 16, 8, "linearRampStep3", False),
    ("bytes", 2, "saturatingRampHead", True),
    ("bytes", 1, "saturatingRampSep", False),
    ("rows", 18, 8, "saturatingRamp", False),
]
SPRING_READ = 0x6B


def decode_spring(blob):
    doc = {
        "_fileType": "spring training development tables: base rating groups plus "
                     "four progression lookup ramps with negative heads",
        "_layoutNote": "each ramp maps a development roll to a rating result; the "
                       "heads are geometric negative offsets, the ramps linear (+5), "
                       "doubling, linear (+3) and saturating at 100",
        "_unreadTrailingByte": blob[SPRING_READ],
    }
    pos = 0
    for spec in SPRING_FIELDS:
        pos = rd_field(blob, pos, spec, doc)
    return doc


def encode_spring(doc, blob):
    out = bytearray()
    for spec in SPRING_FIELDS:
        wr_field(out, spec, doc)
    out += bytes([doc["_unreadTrailingByte"]])
    return bytes(out)


# ---------------------------------------------------------------- assembler

TAB_MARKER = b"\xd1\x07"


def rd_field(blob, pos, spec, doc):
    """Decode one sequential field; returns new pos."""
    kind = spec[0]
    if kind == "bytes":
        _, n, key, signed = spec
        doc[key] = bytes_to_ints(blob[pos:pos + n], signed)
        return pos + n
    if kind == "rows":
        _, total, rowlen, key, signed = spec
        doc[key] = chunk(bytes_to_ints(blob[pos:pos + total], signed), rowlen)
        return pos + total
    if kind == "words":
        _, n, key = spec
        doc[key] = words_to_ints(blob[pos:pos + 2 * n])
        return pos + 2 * n
    if kind == "str":
        _, key = spec
        end = blob.index(b"\x00", pos)
        doc[key] = blob[pos:end].decode("latin1")
        return end + 1
    if kind == "pad":
        _, n, key = spec
        doc[key] = n
        return pos + n
    if kind == "rec":
        _, n, key = spec
        doc[key] = [decode_tab_record(blob, pos + i * 14) for i in range(n)]
        return pos + 14 * n
    raise ValueError("bad field kind %r" % kind)


def wr_field(out, spec, doc):
    kind = spec[0]
    if kind == "bytes":
        _, n, key, signed = spec
        vals = doc[key]
        if len(vals) != n:
            raise ValueError("%s must keep length %d" % (key, n))
        out += ints_to_bytes(vals, signed)
    elif kind == "rows":
        _, total, rowlen, key, signed = spec
        vals = doc[key]
        flat = vals if vals and isinstance(vals[0], int) else unchunk(vals)
        if len(flat) != total:
            raise ValueError("%s must keep %d values" % (key, total))
        out += ints_to_bytes(flat, signed)
    elif kind == "words":
        _, n, key = spec
        out += ints_to_words(doc[key])
    elif kind == "str":
        _, key = spec
        out += doc[key].encode("latin1") + b"\x00"
    elif kind == "pad":
        out += b"\x00" * doc[spec[2]]
    elif kind == "rec":
        for rec in doc[spec[2]]:
            out += encode_tab_record(rec)
    else:
        raise ValueError("bad field kind %r" % kind)


# ---------------------------------------------------------- PGENTABL.DAT
# Thirteen d1 07-tagged sections. Content per section was identified from the
# byte patterns: two roll-to-tier curves, calendar month lengths, draft rating
# ladders, draft slot profiles (14-byte 69 01 records), a rating product
# table, a percentile curve and five value brackets each with its 100-byte
# tier row.

def decode_tab_record(blob, pos):
    rec = blob[pos:pos + 14]
    if rec[:2] != b"\x69\x01":
        raise ValueError("bad draft profile tag at %d" % pos)
    return {
        "kind": rec[2],
        "slot": rec[3],
        "ref": struct.unpack_from("<H", rec, 4)[0],
        "params": bytes_to_ints(rec[6:14], True),
    }


def encode_tab_record(rec):
    out = bytearray(b"\x69\x01")
    out.append(rec["kind"])
    out.append(rec["slot"])
    out += struct.pack("<H", rec["ref"])
    out += ints_to_bytes(rec["params"], True)
    return bytes(out)


TAB_BRACKETS = [(120, 159), (160, 199), (200, 209), (210, 279), (280, 9999)]
TAB_BRACKET_KEYS = ["pay120to159", "pay160to199", "pay200to209", "pay210to279",
                    "pay280plus"]


def decode_pgentabl(blob):
    doc = {
        "_fileType": "player generator tables: roll-to-tier curves, calendar month "
                     "lengths, draft rating ladders, draft slot profiles, a rating "
                     "product table, a percentile curve and value-bracket tier rows",
        "_layoutNote": "thirteen sections each headed by the d1 07 marker; draft "
                       "slot profiles are fixed 14-byte 69 01 records; each value "
                       "bracket holds [lo hi] as u16 followed by its 100-byte tier "
                       "row",
    }
    pos = 0
    for spec in TAB_FIELDS:
        if spec[0] == "M":
            if blob[pos:pos + 2] != TAB_MARKER:
                raise ValueError("missing d1 07 marker at %d" % pos)
            pos += 2
        elif spec[0] == "brk":
            for key in TAB_BRACKET_KEYS:
                lo, hi = struct.unpack_from("<HH", blob, pos)
                pos += 4
                doc[key] = {
                    "lo": lo,
                    "hi": hi,
                    "tiers": chunk(bytes_to_ints(blob[pos:pos + 100], False), 5),
                }
                pos += 100
        else:
            pos = rd_field(blob, pos, spec, doc)
    return doc


def encode_pgentabl(doc, blob):
    out = bytearray()
    for spec in TAB_FIELDS:
        if spec[0] == "M":
            out += TAB_MARKER
        elif spec[0] == "brk":
            for key in TAB_BRACKET_KEYS:
                brk = doc[key]
                out += struct.pack("<HH", brk["lo"], brk["hi"])
                out += rows_to_bytes(brk["tiers"], False)
        else:
            wr_field(out, spec, doc)
    return bytes(out)


TAB_FIELDS = [
    ("M",),
    ("rows", 100, 5, "rollToTierCurve17to23", False),
    ("M",),
    ("rows", 100, 5, "rollToTierCurve18to35", False),
    ("M",),
    ("bytes", 12, "calendarMonthDays", False),
    ("M",),
    ("str", "ratingsLadderPrimary"),
    ("bytes", 4, "ratingsLadderFollowPair1", False),
    ("str", "ratingsLadderSecondary"),
    ("bytes", 4, "ratingsLadderFollowPair2", False),
    ("rows", 12, 6, "ratingsLadderMidPairs", False),
    ("rows", 18, 6, "ratingsLadderPeakRows", False),
    ("M",),
    ("bytes", 2, "draftBaselinePair", False),
    ("M",),
    ("bytes", 10, "draftSlotParams", False),
    ("pad", 42, "_draftSlotZeroPad"),
    ("M",),
    ("rec", 20, "earlyRoundProfiles"),
    ("M",),
    ("rec", 26, "midRoundProfiles"),
    ("M",),
    ("rec", 9, "lateRoundProfiles"),
    ("M",),
    ("rows", 74, 7, "ratingProductRows", False),
    ("bytes", 1, "productRowTail", False),
    ("str", "ratingsLadderTop"),
    ("M",),
    ("bytes", 26, "percentileToRatingCurve", False),
    ("M",),
    ("brk",),
    ("M",),
    ("bytes", 1, "finalMarkerByte", False),
]

# ---------------------------------------------------------- PGEND.DAT
# "PGD:" + u32 0x3AA header, one 938-byte generation record, one unread byte.
# Field offsets were pinned by the pgen accessors (FUN_68068760 reads the nine
# position weights at 0x35; FUN_680687b0 the per-position 6-entry pick tables
# at 0xB7; FUN_68068b30 the nine-byte rating percentage profiles; FUN_68069550
# the aging triple + curve at 0x1F7/0x1FA).

PGD_PROFILES = [  # (lead bytes, ascii tail bytes) per rating profile
    (5, 4), (9, 0), (9, 0), (9, 0), (9, 0), (5, 4), (4, 5), (3, 6),
]


def decode_pgend(blob):
    magic, rec_size = struct.unpack_from("<4sI", blob, 0)
    if magic != b"PGD:":
        raise ValueError("bad PGenD magic %r" % magic)
    doc = {
        "_fileType": "player generator database (PGenD): one 938-byte record of "
                     "draft and generation parameters read by the BBShell pgen "
                     "engine",
        "_header": {"magic": "PGD:", "recordSize": rec_size,
                    "note": "derived: encoder recomputes recordSize from the "
                            "assembled record and keeps the 40 leading runtime "
                            "counter bytes zeroed"},
        "_trailingUnreadByte": blob[-1],
    }
    pos = 8
    for spec in PGD_FIELDS:
        kind = spec[0]
        if kind == "pick":
            tables = []
            for _p in range(9):
                rows = []
                for _e in range(6):
                    rows.append(bytes_to_ints(blob[pos:pos + 3], False))
                    pos += 3
                tables.append(rows)
            doc["positionPickTables"] = tables
        elif kind == "profiles":
            profiles = []
            for lead_n, tail_n in PGD_PROFILES:
                lead = bytes_to_ints(blob[pos:pos + lead_n], False)
                pos += lead_n
                end = blob.index(b"\x00", pos)
                tail = blob[pos:end].decode("latin1")
                pos = end + 1
                profiles.append({"leadRatings": lead, "asciiTail": tail})
            doc["ratingPercentProfiles"] = profiles
        else:
            pos = rd_field(blob, pos, spec, doc)
    return doc


def encode_pgend(doc, blob):
    out = bytearray()
    body = bytearray()
    for spec in PGD_FIELDS:
        kind = spec[0]
        if kind == "pick":
            for table in doc["positionPickTables"]:
                for row in table:
                    body += ints_to_bytes(row, False)
        elif kind == "profiles":
            for prof in doc["ratingPercentProfiles"]:
                body += ints_to_bytes(prof["leadRatings"], False)
                body += prof["asciiTail"].encode("latin1")
                body += b"\x00"
        else:
            wr_field(body, spec, doc)
    body += bytes([doc["_trailingUnreadByte"]])
    out += struct.pack("<4sI", b"PGD:", len(body) - 1)
    out += body
    return bytes(out)


PGD_FIELDS = [
    ("pad", 40, "_leadingRuntimeCounters"),
    ("bytes", 3, "overallRangePrimary", True),
    ("bytes", 3, "overallRangeTertiary", True),
    ("bytes", 3, "overallRangeSecondary", True),
    ("bytes", 1, "rangeFloorThreshold", False),
    ("bytes", 3, "rangeFloorBoost", False),
    ("bytes", 9, "positionWeights", False),
    ("bytes", 2, "draftChancePair", False),
    ("bytes", 2, "draftScaleFraction", False),
    ("bytes", 3, "draftSpreadTriple", False),
    ("bytes", 2, "altChancePair", True),
    ("bytes", 3, "altScaleFraction", False),
    ("bytes", 1, "preScalarPad", False),
    ("words", 54, "ratingScalars"),
    ("bytes", 1, "scalarTablePad", False),
    ("pick",),
    ("bytes", 4, "handPairTable1", True),
    ("bytes", 4, "handPairTable2", True),
    ("bytes", 2, "handExtraPair", False),
    ("bytes", 9, "handAdjustTriples", True),
    ("bytes", 7, "ageParamBlock", True),
    ("str", "ageLabel"),
    ("bytes", 2, "ageParamTail", False),
    ("words", 28, "handednessProfiles"),
    ("rows", 18, 3, "ratingRangeTriples", True),
    ("rows", 18, 3, "slotWeightTriples", True),
    ("rows", 30, 3, "ageScaleTriples", True),
    ("bytes", 1, "ageScaleTail", False),
    ("bytes", 3, "agingRollRange", True),
    ("rows", 256, 8, "agingCurveRows", True),
    ("bytes", 2, "pctScalePair", False),
    ("bytes", 1, "pctScaleTerminator", False),
    ("profiles",),
    ("bytes", 9, "slotScaleHeader", False),
    ("rows", 84, 4, "draftSlotMultipliers", False),
]


def decode_pgend_doc(blob):
    doc = decode_pgend(blob)
    # reshape flat helper fields into their published forms
    doc["agingCurve"] = {"rows": doc.pop("agingCurveRows")}
    doc["handPairTable1"] = [doc["handPairTable1"][0:2], doc["handPairTable1"][2:4]]
    doc["handPairTable2"] = [doc["handPairTable2"][0:2], doc["handPairTable2"][2:4]]
    doc["handAdjustTriples"] = chunk(doc.pop("handAdjustTriples"), 3)
    doc["handednessProfiles"] = chunk(doc["handednessProfiles"], 7)
    return doc


def encode_pgend_doc(doc, blob):
    doc = json.loads(json.dumps(doc))
    doc["agingCurveRows"] = doc.pop("agingCurve")["rows"]
    flat = []
    for pair in doc["handPairTable1"]:
        flat += pair
    doc["handPairTable1"] = flat
    flat = []
    for pair in doc["handPairTable2"]:
        flat += pair
    doc["handPairTable2"] = flat
    doc["handAdjustTriples"] = unchunk(doc.pop("handAdjustTriples"))
    flat = []
    for prof in doc["handednessProfiles"]:
        flat += prof
    doc["handednessProfiles"] = flat
    return encode_pgend(doc, blob)


# ---------------------------------------------------------------- dispatch

CODECS = {
    "PGENFRST.DAT": (decode_names, encode_names),
    "PGENLAST.DAT": (decode_names, encode_names),
    "PGENTABL.DAT": (decode_pgentabl, encode_pgentabl),
    "PGEND.DAT": (decode_pgend_doc, encode_pgend_doc),
    "AGEPLYR.DAT": (decode_aging, encode_aging),
    "SPRPLYR.DAT": (decode_spring, encode_spring),
}


def main(argv):
    if len(argv) < 5 or argv[1] not in ("decode", "encode"):
        sys.stderr.write(__doc__)
        return 2
    cmd, name = argv[1], argv[2]
    if name not in CODECS:
        sys.stderr.write("unknown entry name %r\n" % name)
        return 2
    dec, enc = CODECS[name]
    with open(argv[3], "rb") as fh:
        blob = fh.read()
    if cmd == "decode":
        doc = dec(blob)
        with open(argv[4], "w") as fh:
            json.dump(doc, fh, indent=1)
    else:
        with open(argv[4]) as fh:
            doc = json.load(fh)
        with open(argv[5], "wb") as fh:
            fh.write(enc(doc, blob))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
