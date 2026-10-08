#!/usr/bin/env python3
"""Semantic read/write codec for FPS Baseball Pro '98 saved highlight replays
(saved as hilights/*.tap by the sim) and the highlight replay queue (MLBPA97.NQ0).

LAYOUTS (evidence in FORMAT.md in this lane)

  hilights/*.tap - one saved highlight play:
      u16 0x2b marker, then the play caption ("10-27-06 TOR 0, PIT 0 B-1st O-2
      3rd Broskie-Gonzalez 0-0": date, away/home score, base state, outs,
      inning, batter-pitcher, count) inside an 80-byte NUL-padded field, then
      team records (city, manager, triCode, stadium), player records (first
      name/last name pairs), then the frame log: a numeric state table and the
      per-frame playback words the VCR coder snapshots round by round. Some
      frames carry their own embedded text runs. Bytes are visited in file
      order; the log's numeric fields are little-endian 32-bit words.

  MLBPA97.NQ0 - the replay queue:
      u16 version (0x0005), then one entry per saved play: u16 tag (0x4001...)
      + u32 body length + a byte-identical copy of a hilights/*.tap blob. The
      tags line up 1:1 with the '%s\\highlight*.tap' / '%s\\user*.tap' files
      BBSIM enumerates into the same queue id space (in the sample queue entry
      1 == highlight002.tap and entry 3 == highlight005.tap byte for byte).

REPRESENTATION

  The file is tokenized in file order. Every token is a one-key object:

    'caption' / 'text'      NUL-terminated printable strings from the record
                            region and the embedded frame text (content)
    'entry_marker'          a .tap's leading u16 (0x2b) (content)
    'queue_header'          the queue's version u16 (content)
    'entry_tag'             a queue entry's marker u16, 0x4001.. (content)
    'playback_word'         a little-endian 32-bit word of state/playback data
    '_pad'                  hex of leftover bytes that are not string bytes
                            and do not fill a 32-bit word (derived padding:
                            record-header bytes between strings and the
                            sub-word tails at the end of each entry)

  Strings may grow or shrink; encode() rebuilds the whole file from the token
  list, recomputing the entry lengths, so edits shift the frame log cleanly.

usage:
    python3 voldat.py decode NAME in.bin out.json
    python3 voldat.py encode NAME in.bin edited.json out.bin
"""
import json
import struct
import sys

QUEUE_VERSION = 0x0005
CAPTION_MARKER = 0x2B
PRINT_MIN, PRINT_MAX = 0x20, 0x7E
MIN_TEXT = 4              # text runs shorter than this stay inside pad/words
PAD_LOOK = 4              # how far ahead a text run may start past a non-printable byte


def _printable(b):
    return PRINT_MIN <= b <= PRINT_MAX


def _run_end(blob, j, n):
    """Exclusive end of the printable run starting at j; -1 if unterminated."""
    k = j
    while k < n and _printable(blob[k]):
        k += 1
    if k < n and blob[k] == 0:
        return k
    return -1


def _tokens_from_body(blob):
    """Tokenize one .tap-style body in file order: text runs, 32-bit words and
    sub-word padding."""
    toks = []
    n = len(blob)
    i = 0
    while i < n:
        if _printable(blob[i]):
            k = _run_end(blob, i, n)
            if k >= 0:
                toks.append({'text': blob[i:k].decode('latin1')})
                i = k + 1
                continue
        # a text run of reportable length may start within the next few bytes;
        # peel the bytes before it off as padding so the run survives as text
        found = None
        for j in range(i + 1, min(n, i + PAD_LOOK)):
            if _printable(blob[j]):
                k = _run_end(blob, j, n)
                if k >= 0 and k - j >= MIN_TEXT:
                    found = (j, k)
                    break
        if found:
            j, k = found
            toks.append({'_pad': blob[i:j].hex()})
            toks.append({'text': blob[j:k].decode('latin1')})
            i = k + 1
            continue
        if i + 4 <= n:
            toks.append({'playback_word': struct.unpack_from('<I', blob, i)[0]})
            i += 4
            continue
        toks.append({'_pad': blob[i:].hex()})
        i = n
    return toks


def _tokens_from_entry(blob):
    n = len(blob)
    toks = []
    i = 0
    if n >= 2:
        toks.append({'entry_marker': struct.unpack_from('<H', blob, 0)[0]})
        i = 2
    toks.extend(_tokens_from_body(blob[i:]))
    return toks


def _tokens_to_body(toks):
    out = bytearray()
    for t in toks:
        (key, v), = t.items()
        if key == 'text':
            out.extend(v.encode('latin1'))
            out.extend(b'\x00')
        elif key == 'playback_word':
            out.extend(struct.pack('<I', v & 0xFFFFFFFF))
        elif key == '_pad':
            out.extend(bytes.fromhex(v))
        elif key in ('entry_marker', 'queue_header', 'entry_tag'):
            out.extend(struct.pack('<H', v & 0xFFFF))
        else:
            raise ValueError(f'unknown token kind {key!r}')
    return out


def _tokens_from_queue(blob):
    n = len(blob)
    toks = []
    i = 0
    if n >= 2:
        toks.append({'queue_header': struct.unpack_from('<H', blob, 0)[0]})
        i = 2
    seen_entry = False
    while i + 6 <= n:
        tag = struct.unpack_from('<H', blob, i)[0]
        if (tag & 0xC000) != 0x4000:
            break
        elen = struct.unpack_from('<I', blob, i + 2)[0]
        seen_entry = True
        toks.append({'entry_tag': tag})
        toks.append({'_entry_length': elen})
        toks.extend(_tokens_from_entry(blob[i + 6:i + 6 + elen]))
        i += 6 + elen
    if not seen_entry:
        return _tokens_from_entry(blob)
    if i < n:
        toks.append({'_pad': blob[i:].hex()})
    return toks


def _tokens_to_queue(toks):
    """Rebuild the queue; each entry's length marker is recomputed because the
    bodies sit after the u32 length that describes them."""
    out = bytearray()
    i = 0
    n = len(toks)
    while i < n:
        (key, v), = toks[i].items()
        if key == 'queue_header':
            out.extend(struct.pack('<H', QUEUE_VERSION))
            i += 1
            continue
        if key == 'entry_tag':
            j = i + 1
            while j < n and '_entry_length' not in toks[j]:
                j += 1
            start = j + 1
            k = start
            while k < n and not (set(toks[k]) & {'entry_tag', 'queue_header'}):
                k += 1
            # the body's own entry_marker token is part of the body
            body = _tokens_to_body(toks[start:k])
            out.extend(struct.pack('<H', v & 0xFFFF))
            out.extend(struct.pack('<I', len(body)))
            out.extend(body)
            i = k
            continue
        out.extend(_tokens_to_body([toks[i]]))
        i += 1
    return out


def pick_layout(name):
    base = name.rsplit('.', 1)[-1].upper() if '.' in name else ''
    return 'queue' if base == 'NQ0' else 'entry'


def decode(name, blob):
    if pick_layout(name) == 'queue':
        return {'layout': 'fps98_highlight_queue', 'tokens': _tokens_from_queue(blob)}
    return {'layout': 'fps98_highlight_entry', 'tokens': _tokens_from_entry(blob)}


def encode(name, blob, doc):
    return _tokens_to_queue(doc['tokens']) if pick_layout(name) == 'queue' \
        else bytes(_tokens_to_body(doc['tokens']))


def main(argv):
    if len(argv) < 5:
        print('usage: voldat.py decode NAME in.bin out.json\n'
              '       voldat.py encode NAME in.bin edited.json out.bin',
              file=sys.stderr)
        return 2
    cmd, name, in_path = argv[1], argv[2], argv[3]
    with open(in_path, 'rb') as fh:
        blob = fh.read()
    if cmd == 'decode':
        with open(argv[4], 'w') as fh:
            json.dump(decode(name, blob), fh)
        return 0
    if cmd == 'encode':
        with open(argv[4]) as fh:
            doc = json.load(fh)
        with open(argv[5], 'wb') as fh:
            fh.write(encode(name, blob, doc))
        return 0
    print(f'unknown command: {cmd}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
