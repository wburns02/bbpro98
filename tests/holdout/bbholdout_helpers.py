"""Synthetic game bytes shared by the holdout tests: PYR player files, PYF pools and player records."""
import datetime
import struct

import league

PEAK, CUR, K_ATTR = 0x46, 0x5d, 0x76


def player(pid, first='Pat', last='Doe', pos=6, born=1972, bats=2, throws=2, cur=None, peak=None, raw=None):
    """One plain 192-byte player record. cur and peak map a rating index to its byte, raw maps a file offset."""
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, datetime.date(born, 7, 1).toordinal() + 365)
    p[0x41], p[0x42], p[0x44] = bats, throws, pos
    for i, v in (cur or {}).items():
        p[CUR + i] = v
    for i, v in (peak or {}).items():
        p[PEAK + i] = v
    for off, v in (raw or {}).items():
        p[off] = v
    return bytes(p)


def pyr_bytes(records, seed=(0x6b, 0xe2)):
    """A PYR file: a 192-byte header whose bytes 0-1 are the cipher seed, then each record enciphered."""
    t = league._forward(seed)
    return bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records)


def pyf_bytes(ids, stale=b''):
    """A PYF free agent pool: 'PPD:', n_bytes, count, the ids, then any stale bytes the game leaves behind."""
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids) + stale
