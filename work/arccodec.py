#!/usr/bin/env python3
"""Read/write codec for FPS Baseball Pro '98 league archives (Archive/*.ARC, "AR96").

Format:
    header   b"AR96" + title[32] (NUL padded latin1, e.g. "1997 MLBPA Opening Day")
    entries  back to back to EOF, each:
             u32 csize, u32 crc32(plain), u32 last (1 on the final entry), name[14] (NUL padded),
             csize bytes of a PKWARE DCL "implode" stream (byte 0 literal mode, byte 1 dictionary bits;
             shipped files use 01 06), decoded exactly as zlib contrib/blast/blast.c does.
A shipped ARC holds one league snapshot: <league>.ASN, .PYR, .DAT.

    python3 arccodec.py unpack IN.ARC OUTDIR   # OUTDIR/manifest.json, OUTDIR/<name>, OUTDIR/_streams/<name>.dcl
    python3 arccodec.py pack OUTDIR OUT.ARC    # untouched entries reuse the original stream (byte-identical)
    python3 arccodec.py selftest
Stdlib only.
"""
import json
import os
import struct
import sys
import zlib

# ---- PKWARE DCL tables (blast.c) -------------------------------------------------------------------------------
LITLEN = bytes((
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
    9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
    7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
    8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
    44, 173))
LENLEN = bytes((2, 35, 36, 53, 38, 23))
DISTLEN = bytes((2, 20, 53, 230, 247, 151, 248))
BASE = (3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264)
EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8)
END_LEN = 519
MAX_LEN = 518


def _code_lengths(rep):
    lengths = []
    for b in rep:
        lengths += [b & 15] * ((b >> 4) + 1)
    return lengths


def _canonical(rep):
    """blast construct(): returns (decode map {(len, code): symbol}, encode list [(code, len)] by symbol)."""
    lengths = _code_lengths(rep)
    order = sorted((n, s) for s, n in enumerate(lengths) if n)  # by length, then symbol
    dec, enc = {}, [None] * len(lengths)
    code, prev = 0, order[0][0]
    for n, s in order:
        code <<= n - prev
        prev = n
        dec[(n, code)] = s
        enc[s] = (code, n)
        code += 1
    return dec, enc


LIT_DEC, LIT_ENC = _canonical(LITLEN)
LEN_DEC, LEN_ENC = _canonical(LENLEN)
DIST_DEC, DIST_ENC = _canonical(DISTLEN)


# ---- explode ---------------------------------------------------------------------------------------------------
class _BitReader:
    def __init__(self, data):
        self.data, self.pos, self.buf, self.cnt = data, 0, 0, 0

    def bits(self, need):
        while self.cnt < need:
            if self.pos >= len(self.data):
                raise ValueError("DCL stream ended early")
            self.buf |= self.data[self.pos] << self.cnt
            self.pos += 1
            self.cnt += 8
        v = self.buf & ((1 << need) - 1)
        self.buf >>= need
        self.cnt -= need
        return v

    def decode(self, table):
        # blast decode(): code bits arrive inverted, most significant first
        code = 0
        for n in range(1, 14):
            code = (code << 1) | (self.bits(1) ^ 1)
            s = table.get((n, code))
            if s is not None:
                return s
        raise ValueError("bad DCL Huffman code")


def explode(stream: bytes) -> bytes:
    r = _BitReader(stream)
    lit, dict_bits = r.bits(8), r.bits(8)
    if lit > 1:
        raise ValueError("bad DCL literal flag %d" % lit)
    if not 4 <= dict_bits <= 6:
        raise ValueError("bad DCL dictionary size %d" % dict_bits)
    out = bytearray()
    while True:
        if r.bits(1):
            sym = r.decode(LEN_DEC)
            length = BASE[sym] + r.bits(EXTRA[sym])
            if length == END_LEN:
                return bytes(out)
            low = 2 if length == 2 else dict_bits
            dist = (r.decode(DIST_DEC) << low) + r.bits(low) + 1
            if dist > len(out):
                raise ValueError("DCL distance too far back")
            start = len(out) - dist
            for i in range(length):  # overlapping copies repeat, as in blast
                out.append(out[start + i])
        else:
            out.append(r.decode(LIT_DEC) if lit else r.bits(8))


# ---- implode ---------------------------------------------------------------------------------------------------
class _BitWriter:
    def __init__(self):
        self.out, self.buf, self.cnt = bytearray(), 0, 0

    def bits(self, value, n):
        self.buf |= value << self.cnt
        self.cnt += n
        while self.cnt >= 8:
            self.out.append(self.buf & 0xFF)
            self.buf >>= 8
            self.cnt -= 8

    def code(self, entry):
        # inverse of decode(): write the code MSB first with every bit inverted
        code, n = entry
        for i in range(n - 1, -1, -1):
            self.bits(((code >> i) & 1) ^ 1, 1)

    def flush(self):
        if self.cnt:
            self.out.append(self.buf & 0xFF)
        self.buf = self.cnt = 0
        return bytes(self.out)


_LEN_SYM = {}
for _s in range(16):
    for _l in range(BASE[_s], BASE[_s] + (1 << EXTRA[_s])):
        _LEN_SYM.setdefault(_l, _s)


def implode(data: bytes, lit_mode: int = 1, dict_bits: int = 6, chain: int = 48) -> bytes:
    if lit_mode not in (0, 1) or dict_bits not in (4, 5, 6):
        raise ValueError("lit_mode 0/1, dict_bits 4/5/6")
    w = _BitWriter()
    w.bits(lit_mode, 8)
    w.bits(dict_bits, 8)
    window = 64 << dict_bits
    n = len(data)
    heads = {}  # 2-byte prefix -> list of positions (most recent last)

    def literal(c):
        w.bits(0, 1)
        if lit_mode:
            w.code(LIT_ENC[c])
        else:
            w.bits(c, 8)

    def insert(p):
        if p + 1 < n:
            heads.setdefault(data[p:p + 2], []).append(p)

    i = 0
    while i < n:
        best_len, best_dist = 0, 0
        if i + 1 < n:
            cands = heads.get(data[i:i + 2])
            if cands:
                limit = min(MAX_LEN, n - i)
                tried = 0
                for p in reversed(cands):
                    dist = i - p
                    if dist > window or tried >= chain:
                        break
                    tried += 1
                    if best_len and data[p + best_len] != data[i + best_len]:
                        continue  # cannot beat the current best
                    l = 2
                    while l < limit and data[p + l] == data[i + l]:
                        l += 1
                    if l == 2 and dist > 256:
                        continue  # length-2 matches carry only 2 low distance bits
                    if l > best_len:
                        best_len, best_dist = l, dist
                        if l == limit:
                            break
                if len(cands) > 4 * chain:
                    del cands[:-2 * chain]
        if best_len >= 2:
            sym = _LEN_SYM[best_len]
            w.bits(1, 1)
            w.code(LEN_ENC[sym])
            w.bits(best_len - BASE[sym], EXTRA[sym])
            low = 2 if best_len == 2 else dict_bits
            d = best_dist - 1
            w.code(DIST_ENC[d >> low])
            w.bits(d & ((1 << low) - 1), low)
            for p in range(i, i + best_len):
                insert(p)
            i += best_len
        else:
            literal(data[i])
            insert(i)
            i += 1
    w.bits(1, 1)
    w.code(LEN_ENC[15])
    w.bits(END_LEN - BASE[15], EXTRA[15])
    return w.flush()


# ---- ARC container ---------------------------------------------------------------------------------------------
MAGIC = b"AR96"
ENTRY = struct.Struct("<III14s")


def _cstr(b):
    return b.split(b"\0", 1)[0].decode("latin1")


def read_arc(raw):
    if raw[:4] != MAGIC:
        raise ValueError("not an AR96 archive")
    title = _cstr(raw[4:36])
    entries, off = [], 36
    while off < len(raw):
        csize, crc, last, name = ENTRY.unpack_from(raw, off)
        off += ENTRY.size
        stream = raw[off:off + csize]
        if len(stream) != csize:
            raise ValueError("truncated entry %r" % _cstr(name))
        off += csize
        entries.append({"name": _cstr(name), "crc": crc, "last": last, "stream": stream})
        if last:
            break
    if off != len(raw):
        raise ValueError("%d trailing bytes after the last entry" % (len(raw) - off))
    return title, entries


def write_arc(title, entries):
    """entries: [{"name", "stream", "crc"}] in order; the last flag is set on the final entry only."""
    out = bytearray(MAGIC + title.encode("latin1")[:31].ljust(32, b"\0"))
    for k, e in enumerate(entries):
        name = e["name"].encode("latin1")
        if len(name) > 13:
            raise ValueError("entry name too long: %r" % e["name"])
        out += ENTRY.pack(len(e["stream"]), e["crc"], int(k == len(entries) - 1), name.ljust(14, b"\0"))
        out += e["stream"]
    return bytes(out)


def unpack(arc_path, out_dir):
    with open(arc_path, "rb") as f:
        title, entries = read_arc(f.read())
    os.makedirs(os.path.join(out_dir, "_streams"), exist_ok=True)
    manifest = {"title": title, "entries": []}
    for e in entries:
        plain = explode(e["stream"])
        if zlib.crc32(plain) != e["crc"]:
            raise ValueError("crc mismatch in %s" % e["name"])
        _safe_write(out_dir, e["name"], plain)
        _safe_write(os.path.join(out_dir, "_streams"), e["name"] + ".dcl", e["stream"])
        manifest["entries"].append({"name": e["name"], "last": e["last"], "crc": e["crc"],
                                    "lit_mode": e["stream"][0], "dict_bits": e["stream"][1]})
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)


def pack(in_dir, arc_path):
    with open(os.path.join(in_dir, "manifest.json")) as f:
        manifest = json.load(f)
    entries = []
    for m in manifest["entries"]:
        with open(_safe_path(in_dir, m["name"]), "rb") as f:
            plain = f.read()
        crc = zlib.crc32(plain)
        dcl = _safe_path(os.path.join(in_dir, "_streams"), m["name"] + ".dcl")
        stream = None
        if crc == m.get("crc") and os.path.exists(dcl):
            with open(dcl, "rb") as f:
                stream = f.read()
        if stream is None:
            stream = implode(plain, m.get("lit_mode", 1), m.get("dict_bits", 6))
        entries.append({"name": m["name"], "crc": crc, "stream": stream})
    with open(arc_path, "wb") as f:
        f.write(write_arc(manifest["title"], entries))


def _safe_path(d, name):
    if os.path.basename(name) != name or name in ("", ".", ".."):
        raise ValueError("unsafe entry name %r" % name)
    return os.path.join(d, name)


def _safe_write(d, name, data):
    with open(_safe_path(d, name), "wb") as f:
        f.write(data)


def selftest():
    import random
    assert explode(bytes.fromhex("00048224258f807f")) == b"AIAIAIAIAIAIA"
    rnd = random.Random(1997)
    samples = [b"", b"A", b"AIAIAIAIAIAIA", bytes(rnd.randrange(256) for _ in range(5000)),
               b"".join(rnd.choice([b"Colorado ", b"defeat ", b"(4-3) ", b"\0\0\0\0", b"x"]) for _ in range(4000)),
               bytes(70000)]
    for data in samples:
        for lit in (0, 1):
            for db in (4, 5, 6):
                s = implode(data, lit, db)
                assert explode(s) == data, (len(data), lit, db)
    print("selftest ok")


def main(argv):
    if len(argv) == 4 and argv[1] == "unpack":
        unpack(argv[2], argv[3])
    elif len(argv) == 4 and argv[1] == "pack":
        pack(argv[2], argv[3])
    elif len(argv) == 2 and argv[1] == "selftest":
        selftest()
    else:
        sys.stderr.write(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
