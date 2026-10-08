"""Members of an association file (*.ASN) by name, deciphered, with edits queued for ctree.do_apply.

Members a, l, d, t, r, xs store enciphered payloads (seed = file bytes 0x310, 0x311); s, tr, df, po, sp are plain.
Records are found through ctree.parse and member names, never by member number (the numbers differ between files).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctree                                             # noqa: E402
from lahman import ratings as RT                         # noqa: E402

ENC = frozenset(('a', 'l', 'd', 't', 'r', 'xs'))


class AsnFile:
    def __init__(self, data):
        self.data = bytes(data)
        self.t, self.inv = RT.cipher((self.data[0x310], self.data[0x311]))
        _, by_mem, members, *_ = ctree.parse(self.data)
        self.recs = {}              # member short name -> [(payload offset, plain payload)]
        for m in members:
            if m['kind'] != 'data':
                continue
            name = m['name'].rsplit('.', 1)[0]
            out = []
            for r in by_mem.get(m['num'], []):
                raw = self.data[r.off:r.off + r.pl]
                if not raw or raw[0] == 0xFF:
                    continue
                out.append((r.off, self.dec(name, raw)))
            self.recs[name] = out
        self.edits = []

    def dec(self, name, raw):
        return bytes(self.inv[b] for b in raw) if name in ENC else bytes(raw)

    def enc(self, name, plain):
        return bytes(self.t[b] for b in plain) if name in ENC else bytes(plain)

    def key(self, name, plain):
        """The record key the game indexes on: the raw (enciphered) first byte."""
        return self.enc(name, plain[:1])[0]

    def rewrite(self, name, off, plain):
        old = next(p for o, p in self.recs[name] if o == off)
        if len(plain) != len(old):
            raise ValueError('%s record at %d: length %d != %d' % (name, off, len(plain), len(old)))
        if plain[0] != old[0]:
            raise ValueError('%s record at %d: key byte changed' % (name, off))
        if plain != old:
            self.edits.append({'op': 'rewrite', 'rec': off, 'data': self.enc(name, plain).hex()})

    def delete(self, name, off):
        self.edits.append({'op': 'delete', 'rec': off})

    def build(self):
        return ctree.do_apply(self.data, self.edits)


def put_str(buf, off, size, text):
    """strcpy-style string field: text + NUL, the stale tail after it kept (the game leaves it the same way)."""
    raw = text.encode('latin-1', 'replace')[:size - 1]
    buf[off:off + len(raw)] = raw
    buf[off + len(raw)] = 0


def cstr(p, off, size):
    return p[off:off + size].split(b'\0')[0].decode('latin-1')
