#!/usr/bin/env python3
"""Lossless codec for FPS Baseball Pro '98 .VOL archives ("VOLM" format).

Usage:
    python3 codec.py unpack in.bin out/    # manifest.json + one file per entry
    python3 codec.py pack out/ in.bin      # rebuilds the archive from out/ alone

Layout (verified against SHELL.VOL / SHELL1.VOL / SHELL2.VOL and the game
reader EZShell Utility\\Volume.cpp; full evidence in FORMAT.md):

    u8[4]  magic "VOLM"
    u32    version (1)
    u8     0
    u8     ndir            number of directory names that follow
    u16    dirnames_len    total bytes of the NUL-terminated dir names
    u8[.]  ndir dir names, each ASCIIZ and ending in '\\', e.g. "ShelPcx8\\"
    u16    count           entry count
    u32    dirbytes        bytes of the record block (count * 18)
    count records of 18 bytes:
        u8[12]  file name, ASCIIZ (a 12-char name leaves no room for its NUL
                and overwrites the low byte of the field at [12:14])
        u16     at [12:14]: high byte = directory index (0xff = archive
                root), low byte = resource type; bytes between the name's
                NUL and [12] are writer filler, preserved verbatim
        u32     offset     absolute offset of the entry blob (recomputed)
    then, contiguously to EOF, one blob per entry in directory order:
        u8      method     2 in every known archive (stored, no compression)
        u32     size       len(payload)-1 in every pristine entry.  The game's
                           member stream (BBShell FUN_68051380) treats it as
                           the member length: a seek or read past it fails, so
                           a payload that grows needs a new size.  A tool may
                           have appended bytes without updating it (the wide5
                           SHELL.VOL built before 2026-10-07)
        u32     stamp      DOS date (high u16) + DOS time (low u16)
        u8[.]   payload    the entry's bytes (PCX starts 0x0A, WAV "RIFF")

Payloads are sliced from offset+9 to the next entry's offset (EOF for the
last entry): the offsets are authoritative, so blobs whose payload is longer
than `size` still unpack byte-exactly.  pack() recomputes the structure that
depends on the entry set (ndir is kept from meta, dirnames_len, count,
dirbytes and every offset) and preserves each record's static 16 bytes.
The manifest keeps a blob's `size` only when it is not len(payload)-1, next
to the `len` it was read with; pack() writes that size back only while the
payload still has that length, else len(payload)-1.
"""

import json
import os
import struct
import sys

MAGIC = b"VOLM"
NAME_LEN = 12
REC_LEN = 18  # name/filler[12] + u16 dir+type + u32 offset
BLOB_HDR = 9  # u8 method + u32 size + u32 stamp
ROOT_DIR = 0xFF  # directory index in the record u16 for archive-root files


def fail(msg):
    raise ValueError(msg)


def parse(blob):
    if len(blob) < 12 or blob[:4] != MAGIC:
        fail("not a VOLM archive")
    version = struct.unpack_from("<I", blob, 4)[0]
    ndir = blob[9]
    dirlen = struct.unpack_from("<H", blob, 10)[0]
    p = 12
    end = p + dirlen
    if end > len(blob):
        fail("directory name block overruns file")
    dirs = []
    while p < end:
        nul = blob.find(b"\0", p, end)
        if nul < 0:
            fail("directory name not NUL terminated")
        dirs.append(blob[p:nul].decode("latin1"))
        p = nul + 1
    if p != end or len(dirs) != ndir:
        fail("directory name block inconsistent")
    if end + 6 > len(blob):
        fail("truncated directory")
    count = struct.unpack_from("<H", blob, end)[0]
    dirbytes = struct.unpack_from("<I", blob, end + 2)[0]
    if dirbytes != count * REC_LEN:
        fail("dirbytes != count*18")
    p = end + 6
    if p + dirbytes > len(blob):
        fail("record block overruns file")
    ents = []
    for _ in range(count):
        raw = blob[p:p + REC_LEN]
        name = raw[:NAME_LEN].split(b"\0", 1)[0].decode("latin1")
        flags = struct.unpack_from("<H", raw, NAME_LEN)[0]
        off = struct.unpack_from("<I", raw, NAME_LEN + 2)[0]
        if off + BLOB_HDR > len(blob):
            fail(f"entry {name!r} offset out of range")
        ents.append((name, flags, off, raw[:NAME_LEN + 2]))
        p += REC_LEN
    return version, dirs, ents


def dir_of(name):
    """Directory part of a manifest name ('' when the entry is at the root)."""
    i = name.rfind("\\")
    return name[:i + 1] if i >= 0 else ""


def unpack(inpath, outdir):
    with open(inpath, "rb") as fh:
        blob = fh.read()
    version, dirs, ents = parse(blob)
    os.makedirs(outdir, exist_ok=True)
    out = []
    for i, (name, flags, off, rec) in enumerate(ents):
        nxt = ents[i + 1][2] if i + 1 < len(ents) else len(blob)
        if nxt < off + BLOB_HDR:
            fail(f"entry {name!r} overlaps the next entry")
        method, size, stamp = struct.unpack_from("<BII", blob, off)
        data = blob[off + BLOB_HDR:nxt]
        hi = flags >> 8
        dirname = dirs[hi] if hi < len(dirs) else ""
        fn = "e%04d.bin" % i
        with open(os.path.join(outdir, fn), "wb") as fh:
            fh.write(data)
        hdr = {"method": method, "stamp": stamp}
        if size != len(data) - 1:
            hdr.update(size=size, len=len(data))
        out.append({"name": dirname + name, "file": fn, "flags": flags,
                    "rec": rec.hex(), "hdr": hdr})
    man = {"entries": out,
           "meta": {"format": "VOLM", "version": version, "dirs": dirs}}
    with open(os.path.join(outdir, "manifest.json"), "w") as fh:
        json.dump(man, fh)


def pack(outdir, inpath):
    with open(os.path.join(outdir, "manifest.json"), "r") as fh:
        man = json.load(fh)
    meta = man.get("meta") or {}
    dirs = list(meta.get("dirs") or [])
    loaded = []
    for e in man["entries"]:
        with open(os.path.join(outdir, e["file"]), "rb") as fh:
            loaded.append((e, fh.read()))
    # Keep the archive's directory list in its original order; entries added
    # to an edited manifest contribute their directory at the end.
    seen = set(dirs)
    for e, _ in loaded:
        d = dir_of(e["name"])
        if d and d not in seen:
            seen.add(d)
            dirs.append(d)
    dirblk = b"".join(d.encode("latin1") + b"\0" for d in dirs)
    n = len(loaded)
    off = 12 + len(dirblk) + 6 + REC_LEN * n
    recs = []
    blobs = []
    for e, data in loaded:
        name = e["name"].split("\\")[-1].encode("latin1")
        if not 0 < len(name) <= NAME_LEN:
            fail(f"entry name {e['name']!r} does not fit 12 bytes")
        rec = bytes.fromhex(e["rec"]) if e.get("rec") else b""
        if len(rec) != NAME_LEN + 2:
            # No preserved record bytes: synthesize name + dir/type word.
            d = dir_of(e["name"])
            hi = dirs.index(d) if d in dirs else ROOT_DIR
            hi = min(hi, 0xFF)
            rec = name.ljust(NAME_LEN, b"\0") \
                + struct.pack("<H", (hi << 8) | (int(e.get("flags", 0)) & 0xFF))
        hdr = e.get("hdr") or {}
        method = int(hdr.get("method", 2))
        keep = "size" in hdr and int(hdr.get("len", -1)) == len(data)
        size = int(hdr["size"]) if keep else len(data) - 1
        size = max(size, 0)
        stamp = int(hdr.get("stamp", 0))
        recs.append(rec + struct.pack("<I", off))
        blobs.append(struct.pack("<BII", method, size, stamp) + data)
        off += BLOB_HDR + len(data)
    head = (MAGIC + struct.pack("<IBBH", meta.get("version", 1), 0, len(dirs),
                                len(dirblk)) + dirblk
            + struct.pack("<HI", n, REC_LEN * n))
    with open(inpath, "wb") as fh:
        fh.write(head + b"".join(recs) + b"".join(blobs))


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("unpack", "pack"):
        sys.stderr.write(__doc__)
        return 2
    if sys.argv[1] == "unpack":
        unpack(sys.argv[2], sys.argv[3])
    else:
        pack(sys.argv[2], sys.argv[3])
    return 0


if __name__ == "__main__":
    sys.exit(main())
