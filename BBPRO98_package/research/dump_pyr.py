#!/usr/bin/env python3
"""Dump players from a Front Page Sports Baseball Pro '98 .PYR file (stdlib only).

PYR layout (confirmed):  192-byte text/binary header, then N records of 192 bytes.
Bytes 26-29: birth date as day number (/365.2425 ~ year); 30-46 first name; 47-63 last name;
64 years of service; 65 bats(1=L,2=R,3=S); 66 throws(1=L,2=R); 68 primary pos (1=P..9=RF);
70-92 current ratings block (14 bat/pitch ratings + 9 fielding), 93-115 potentials, 116-140 splits.
Every record byte is passed through a per-file 256-entry substitution table T
(plain -> stored).  Record i has player ID = 100 + i (16-bit LE in bytes 0-1),
so T is recovered directly from the ID bytes of the file itself.

usage: dump_pyr.py FILE.PYR [--raw] [--csv] [--grep TEXT] [--rec N]
"""
import sys, struct, csv

HDR = 192
REC = 192
FIRST_ID = 100


def load(path):
    d = open(path, 'rb').read()
    n = (len(d) - HDR) // REC
    recs = [d[HDR + i * REC:HDR + (i + 1) * REC] for i in range(n)]
    # build inverse table stored-byte -> plain-byte from the sequential IDs
    inv = {}
    for i, r in enumerate(recs):
        pid = FIRST_ID + i
        inv[r[0]] = pid & 255
        inv[r[1]] = pid >> 8        # hi byte (0..~5); consistent with lo table
    # bytes never seen as ID bytes: only lo-byte coverage (needs >=256 recs) fills all 256
    return d, recs, inv


def decode(rec, inv):
    return bytes(inv.get(b, 0xFF) for b in rec)


def cstr(b):
    return b.split(b'\0')[0].decode('latin1')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    path = a[0]
    d, recs, inv = load(path)
    hdr = d[:HDR]
    print('# file %s: %d bytes, header magic %s, %d records, table complete=%s' %
          (path, len(d), hdr[:4].hex(), len(recs), len(inv) == 256), file=sys.stderr)
    sel = None
    if '--rec' in a: sel = int(a[a.index('--rec') + 1])
    g = a[a.index('--grep') + 1].lower() if '--grep' in a else None
    w = csv.writer(sys.stdout) if '--csv' in a else None
    if w: w.writerow(['id', 'first', 'last', 'born_daynum', 'born_year~', 'yrs_exp', 'bats', 'throws', 'pos'] +
                     ['a%d' % k for k in range(70, 93)] + ['p%d' % k for k in range(93, 116)])
    for i, r in enumerate(recs):
        p = decode(r, inv)
        pid = struct.unpack('<H', p[:2])[0]
        first, last = cstr(p[30:47]), cstr(p[47:64])
        if g and g not in (first + ' ' + last).lower(): continue
        if sel is not None and i != sel: continue
        if '--raw' in a:
            print(pid, first, last); print(p.hex(' '))
        elif w:
            dn = struct.unpack('<I', p[26:30])[0]
            w.writerow([pid, first, last, dn, round(dn / 365.2425, 1), p[64], 'XLRS'[p[65]] if p[65] < 4 else p[65],
                        'XLR'[p[66]] if p[66] < 3 else p[66], p[68]] + list(p[70:116]))
        else:
            dn = struct.unpack('<I', p[26:30])[0]
            print('%5d  %-12s %-16s yrs=%2d pos=%d bats/thr=%d/%d born~%.1f  ratings(70..73)=%s' %
                  (pid, first, last, p[64], p[68], p[65], p[66], dn / 365.2425, list(p[70:74])))

if __name__ == '__main__':
    main()
