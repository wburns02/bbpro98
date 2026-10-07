"""FPS Baseball Pro '98 file cipher (PYR, ASN, H-file 2698-byte table). Algorithm: re/targets/cipher/lanes/data/CIPHER.md
(LineUp FUN_6b023440 build, FUN_6b0234c0 encipher = T[T[T[b]]], FUN_6b023500 decipher). Verified 2026-10-07: exact f5dc
table, 82/82 H blobs, 36/36 held-out seeds.

usage: fpscipher.py table SEED              -> forward table (plain -> stored), 512 hex digits
       fpscipher.py hblob MLBPA97.Hxx OUT   -> deciphered 2696-byte H-file table body
"""
import sys


def base_table(lo, hi):
    start = (lo - 1) & 255
    t = [start] * 256; pos = 0; v = lo
    for _ in range(256):
        t[pos] = v; v = (v + 1) & 255; pos = (pos + hi) & 255
        while t[pos] != start: pos = (pos + 1) & 255
    return t


def forward(seed):
    """seed = the two stored seed bytes. Returns the plain -> stored table (base table applied three times)."""
    t = base_table(seed[0], seed[1])
    return bytes(t[t[t[x]]] for x in range(256))


def encipher(data, seed):
    f = forward(seed); return bytes(f[b] for b in data)


def decipher(data, seed):
    f = forward(seed); inv = bytearray(256)
    for x, y in enumerate(f): inv[y] = x
    return bytes(inv[b] for b in data)


def main():
    if sys.argv[1:2] == ['table']:
        print(forward(bytes.fromhex(sys.argv[2])).hex())
    elif sys.argv[1:2] == ['hblob']:
        b = open(sys.argv[2], 'rb').read()
        if b[:2] != b'\x02\x65' or b[6:8] != b'\x8a\x0a': raise SystemExit('not an H file with a 2698-byte first table')
        open(sys.argv[3], 'wb').write(decipher(b[10:10 + 2696], b[8:10]))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
