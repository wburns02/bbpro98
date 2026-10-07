"""Tagged-chunk container read/write: SIM.DAT, Stadia/*.DAT, Stadia/*.DT (magic 00 01 06 07). Verified 2026-10-07.

Layout: magic `00 01 06 07`, u16 count, then count+1 directory entries of 8 bytes: u16 id, 2-byte tag (ASCII except
SIM.DAT entry 0), u32 absolute offset. The extra entry is a sentinel (id 0, tag 0, offset = file size, or 0 in the
.DT files). Chunks are back to back from the end of the directory, in directory order; the last runs to EOF.
The id is stable per chunk role across files (e.g. 'MI' e957 in every stadium .DAT and .DT).

usage: chunkdat.py list FILE
       chunkdat.py unpack FILE outdir/     -> outdir/manifest.json + NN_TAG_ID.bin per chunk
       chunkdat.py pack outdir/ FILE       -> rebuilds from the manifest (any chunk sizes)
       chunkdat.py verify FILE...          -> unpack + pack in memory, byte compare
"""
import json, os, struct, sys

MAGIC = b'\x00\x01\x06\x07'


def split(d):
    if d[:4] != MAGIC: raise ValueError('not a 00 01 06 07 chunk container')
    n = struct.unpack_from('<H', d, 4)[0]
    ents = [struct.unpack_from('<H2sI', d, 6 + 8 * i) for i in range(n + 1)]
    end = 6 + 8 * (n + 1)
    offs = [e[2] for e in ents[:n]] + [len(d)]
    if offs[0] != end or offs != sorted(offs): raise ValueError('directory offsets not contiguous')
    sid, stag, soff = ents[n]
    sentinel = 'size' if soff == len(d) else soff
    chunks = [(ents[i][0], ents[i][1], d[offs[i]:offs[i + 1]]) for i in range(n)]
    return chunks, {'sentinel': sentinel, 'sentinel_id': sid, 'sentinel_tag': stag.hex()}


def join(chunks, meta):
    n = len(chunks); end = 6 + 8 * (n + 1)
    total = end + sum(len(c[2]) for c in chunks)
    out = [MAGIC, struct.pack('<H', n)]
    off = end
    for cid, tag, data in chunks:
        out.append(struct.pack('<H2sI', cid, tag, off)); off += len(data)
    s = meta.get('sentinel', 'size')
    out.append(struct.pack('<H2sI', meta.get('sentinel_id', 0), bytes.fromhex(meta.get('sentinel_tag', '0000')),
                           total if s == 'size' else s))
    out += [c[2] for c in chunks]
    return b''.join(out)


def fname(i, cid, tag):
    t = ''.join(chr(c) if 48 <= c < 58 or 65 <= c < 91 or 97 <= c < 123 else '_' for c in tag)
    return '%02d_%s_%04x.bin' % (i, t, cid)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'list':
        chunks, meta = split(open(sys.argv[2], 'rb').read())
        for i, (cid, tag, data) in enumerate(chunks):
            print('%2d %04x %-4s %9d  %s' % (i, cid, tag.decode('latin-1').encode('unicode_escape').decode(), len(data), data[:16].hex()))
        print('sentinel', meta)
    elif cmd == 'unpack':
        chunks, meta = split(open(sys.argv[2], 'rb').read()); out = sys.argv[3]; os.makedirs(out, exist_ok=True)
        man = {'meta': meta, 'chunks': []}
        for i, (cid, tag, data) in enumerate(chunks):
            fn = fname(i, cid, tag)
            with open(os.path.join(out, fn), 'wb') as f: f.write(data)
            man['chunks'].append({'id': cid, 'tag': tag.hex(), 'file': fn})
        with open(os.path.join(out, 'manifest.json'), 'w') as f: json.dump(man, f, indent=1)
        print(len(chunks), 'chunks')
    elif cmd == 'pack':
        src = sys.argv[2]; man = json.load(open(os.path.join(src, 'manifest.json')))
        chunks = []
        for c in man['chunks']:
            if '/' in c['file'] or c['file'].startswith('.'): raise SystemExit('bad chunk file name %r' % c['file'])
            chunks.append((c['id'], bytes.fromhex(c['tag']), open(os.path.join(src, c['file']), 'rb').read()))
        with open(sys.argv[3], 'wb') as f: f.write(join(chunks, man['meta']))
    elif cmd == 'verify':
        bad = 0
        for p in sys.argv[2:]:
            d = open(p, 'rb').read(); chunks, meta = split(d)
            ok = join(chunks, meta) == d; bad += not ok
            if not ok: print('MISMATCH', p)
        print(len(sys.argv) - 2, 'files,', bad, 'mismatches')
        sys.exit(1 if bad else 0)
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
