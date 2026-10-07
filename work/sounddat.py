"""SOUND.DAT read/write. Format (verified 2026-10-07): u16 count, (count+1) u32 absolute offsets (last = file size),
then `count` standard RIFF/WAVE files back to back. Entries are unnamed; the game addresses them by index.

usage: sounddat.py unpack SOUND.DAT outdir/     -> outdir/s000.wav .. s226.wav
       sounddat.py pack outdir/ SOUND.DAT       -> rebuilds from s*.wav in index order (any sizes)
       sounddat.py verify SOUND.DAT             -> unpack + pack in memory, byte compare
"""
import os, struct, sys


def split(d):
    n = struct.unpack_from('<H', d, 0)[0]
    offs = struct.unpack_from('<%dI' % (n + 1), d, 2)
    if offs[0] != 2 + 4 * (n + 1) or offs[-1] != len(d) or list(offs) != sorted(offs):
        raise ValueError('not a SOUND.DAT offset table')
    return [d[offs[k]:offs[k + 1]] for k in range(n)]


def join(clips):
    head = 2 + 4 * (len(clips) + 1)
    offs = [head]
    for c in clips: offs.append(offs[-1] + len(c))
    return struct.pack('<H%dI' % len(offs), len(clips), *offs) + b''.join(clips)


def main():
    cmd = sys.argv[1]
    if cmd == 'unpack':
        clips = split(open(sys.argv[2], 'rb').read()); os.makedirs(sys.argv[3], exist_ok=True)
        for k, c in enumerate(clips):
            with open(os.path.join(sys.argv[3], 's%03d.wav' % k), 'wb') as f: f.write(c)
        print(len(clips), 'clips')
    elif cmd == 'pack':
        names = sorted(f for f in os.listdir(sys.argv[2]) if f.startswith('s') and f.endswith('.wav'))
        if names != ['s%03d.wav' % k for k in range(len(names))]: raise SystemExit('need s000.wav..sNNN.wav with no gaps')
        with open(sys.argv[3], 'wb') as f: f.write(join([open(os.path.join(sys.argv[2], n), 'rb').read() for n in names]))
    elif cmd == 'verify':
        d = open(sys.argv[2], 'rb').read(); clips = split(d)
        bad = sum(1 for c in clips if c[:4] != b'RIFF' or c[8:12] != b'WAVE')
        print(len(clips), 'clips,', bad, 'non-WAV, round-trip', 'OK' if join(clips) == d else 'MISMATCH')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
