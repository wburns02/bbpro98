#!/usr/bin/env python3
"""Shell string tables (SHELL.VOL: ASNEWS, TMNEWS, PONEWS, ASSERTXT, BOXTEXT, PREFSCRN, PRINTTBL, PRINTTXT, ROSTEXT).
Spec: work/spec/STRTABLE_FORMAT.md. Reader: BBShell FUN_68051ac0(alloc, file, section, count, dest).

usage: strtable.py decode NAME in.DAT out.json
       strtable.py encode NAME in.DAT edited.json out.DAT     (in.DAT is not read; kept for the voldat contract)

File: u16 total (= file length - 3), then a u16 word array W (W[k] at file offset 2 + 2k). W[s] for s < W[0] is the
word index where section s's string offsets start (so W[0] is also the section count). Each offset entry is a byte
offset - 2 of a NUL-terminated string. The strings follow the array back to back in entry order, then one NUL.
The reader loads section s's `count` strings from W[W[s]] up to W[W[s] + count], so every section ends with an empty
end-marker string; the loader also turns every backslash into a newline.

JSON: {"sections": [[str, ...], ...], "_end_markers": bool}. The end marker is not listed; encode adds it back to
every section when _end_markers is true (ASSERTXT has none).
"""
import json
import struct
import sys


def _fail(msg):
    raise ValueError(msg)


def decode(blob):
    if len(blob) < 6 or struct.unpack_from('<H', blob, 0)[0] != len(blob) - 3 or blob[-1] != 0:
        _fail('not a shell string table')
    W = lambda k: struct.unpack_from('<H', blob, 2 + 2 * k)[0]
    nsec = W(0)
    if not nsec or 2 + 2 * nsec > len(blob):
        _fail('bad section count')
    nwords = W(nsec) // 2
    starts = [W(s) for s in range(nsec)] + [nwords]
    if starts[0] != nsec or any(a >= b for a, b in zip(starts, starts[1:])) or 2 + 2 * nwords > len(blob):
        _fail('bad section starts')
    strings, pos = [], 2 + 2 * nwords
    for k in range(nsec, nwords):
        if W(k) + 2 != pos:
            _fail(f'string {k} is not stored back to back')
        end = blob.index(0, pos)
        strings.append(blob[pos:end].decode('latin1'))
        pos = end + 1
    if pos != len(blob) - 1:
        _fail('bytes after the last string')
    sections = [strings[a - nsec:b - nsec] for a, b in zip(starts, starts[1:])]
    marked = all(s[-1] == '' for s in sections)
    return {'sections': [s[:-1] for s in sections] if marked else sections, '_end_markers': marked}


def encode(doc):
    sections = [list(s) + [''] if doc.get('_end_markers', True) else list(s) for s in doc['sections']]
    if not sections or not all(sections):
        _fail('every section needs at least one string')
    nsec = len(sections)
    strings = [x for s in sections for x in s]
    nwords = nsec + len(strings)
    starts, k = [], nsec
    for s in sections:
        starts.append(k)
        k += len(s)
    offs, pos = [], 2 + 2 * nwords
    for x in strings:
        offs.append(pos - 2)
        pos += len(x.encode('latin1')) + 1
    if pos + 1 > 0xffff:
        _fail('string table over 64 KB (offsets are u16)')
    body = struct.pack('<%dH' % nwords, *starts, *offs) + b''.join(x.encode('latin1') + b'\0' for x in strings) + b'\0'
    return struct.pack('<H', len(body) - 1) + body


def main():
    if len(sys.argv) == 5 and sys.argv[1] == 'decode':
        with open(sys.argv[3], 'rb') as fh:
            doc = decode(fh.read())
        with open(sys.argv[4], 'w') as fh:
            json.dump(doc, fh, indent=1)
    elif len(sys.argv) == 6 and sys.argv[1] == 'encode':
        with open(sys.argv[4]) as fh:
            doc = json.load(fh)
        with open(sys.argv[5], 'wb') as fh:
            fh.write(encode(doc))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
