"""FPS Baseball Pro '98 file-cipher table generator.

usage: python3 gen.py SEED      (SEED = the two seed bytes as stored, 4 hex digits, e.g. f5dc)
prints the forward table plain->stored as 512 hex digits on one line.

Algorithm (recovered from the game binary decompile; confirmed exact against the
table recovered from the shipped PYR files and against all 82 H-file blobs):

1. Build base table B (256 entries), all entries pre-filled with sentinel
   s = (lo - 1) & 255. pos = 0, v = lo. Repeat 256 times:
       B[pos] = v; v = (v + 1) & 255; pos = (pos + hi) & 255;
       while B[pos] != s: pos = (pos + 1) & 255      # skip occupied slots, wrapping
2. The game enciphers each byte by applying B three times per byte (the apply
   routine computes tbl[tbl[tbl[b]]]); the forward table plain->stored as seen
   in files is therefore B^3. Decoding applies the inverse three times.
"""
import sys


def base_table(lo, hi):
    start = (lo - 1) & 255
    tbl = [start] * 256
    pos = 0
    v = lo
    for _ in range(256):
        tbl[pos] = v
        v = (v + 1) & 255
        pos = (pos + hi) & 255
        while tbl[pos] != start:
            pos = (pos + 1) & 255
    return tbl


def main():
    seed = sys.argv[1].strip().lower()
    b = bytes.fromhex(seed)
    lo, hi = b[0], b[1]
    t = base_table(lo, hi)
    print(bytes(t[t[t[x]]] for x in range(256)).hex())


if __name__ == '__main__':
    main()
