#!/usr/bin/env python3
"""Semantic read/write codec for the FPS Baseball Pro '98 shell string tables
(SHELL.VOL DAT entries: ASNEWS, TMNEWS, PONEWS, ASSERTXT, BOXTEXT, PREFSCRN,
PRINTTBL, PRINTTXT, ROSTEXT).

File layout (identical for all nine names, verified byte-exact):

    u16 total          file length - 3
    u16 sectionCount   number of section pointers
    u16 sectionPtrs[]  byte offsets relative to file byte 2; the last one
                       points at the label pool, the earlier ones mark where
                       each print report's column/label block starts inside
                       the string-offset table
    u16 stringOffsets[] one per label except labels[0] and the trailing blank:
                       value = (byte position of label) - 2
    pool               NUL-terminated label strings (labels[0] first); the
                       two final labels are blank, hence every file ends
                       "NUL NUL NUL" and len == total + 3

Label content:
  * news tables use printf codes (%s %d %2d %-4s ...), tilde colour codes
    (~4 field name, ~5 team name, ~6 plain) and |N column markers
  * print tables hold printf width/precision column specs packed per report
  * ASSERTXT holds multi-line startup/error messages (\n line breaks)
  * the printable bytes at the end of the offset table can merge with the
    first label into one run (ROSTEXT: 'AJA' + 'Historical data'); that
    merged view is exposed as the 'labelsBoundaryText' string

usage:
    python3 voldat.py decode NAME in.bin out.json
    python3 voldat.py encode NAME in.bin edited.json out.bin
"""
import json
import struct
import sys

DESCRIPTIONS = {
    'ASNEWS': 'association news texts: month names, roster/level names, '
              'transaction/injury/free-agent news templates (printf codes, '
              'tilde colour codes ~4 ~5 ~6, column codes), injury and '
              'illness descriptions, recovery durations, report headers',
    'TMNEWS': 'team news texts: the association news tables plus trade and '
              'free-agent dialog prompts',
    'PONEWS': 'playoff news templates: championship lines, series and game '
              'score lines, playoff standings header',
    'ASSERTXT': 'startup and error message texts shown by the shell',
    'BOXTEXT': 'box score labels: weekdays, month names, ordinal suffixes, '
               'position abbreviations, batting/pitching stat labels and '
               'row templates with |1..|9 column markers',
    'PREFSCRN': 'preference and menu screen captions naming each shell screen',
    'PRINTTBL': 'print table column formats: printf width/precision column '
                'specs grouped per printed report',
    'PRINTTXT': 'print report templates: association/team data pages, '
                'schedules, standings, rosters, leaderboard headings',
    'ROSTEXT': 'roster screen labels: stat abbreviations, full stat and '
               'situational descriptions, column headings',
}

LAYOUT = ('u16 total (file length - 3) | u16 sectionCount | '
          'u16 sectionPointers[] (byte offsets relative to file byte 2; the '
          'last points at the label pool, the others mark block starts '
          'inside the string-offset table) | u16 stringOffsets[] (pool '
          'offsets relative to file byte 2; offset i points at label i+1) | '
          'NUL-terminated label strings (labels[0] first, two blank labels '
          'at the end)')


def label_prefix(blob, pool_start):
    """Printable bytes at the end of the offset table that merge with the
    first label's characters into one printable run."""
    i = pool_start - 1
    while i >= 4 + 2 * 1 and 0x20 <= blob[i] <= 0x7e:
        i -= 1
    return blob[i + 1:pool_start].decode('latin1')


def decode_blob(blob):
    if len(blob) < 8:
        raise ValueError('file too short')
    total, nsec = struct.unpack_from('<HH', blob, 0)
    if total + 3 != len(blob):
        raise ValueError('total %d != file length %d - 3' % (total, len(blob)))
    if 4 + 2 * nsec > len(blob):
        raise ValueError('bad section count %d' % nsec)
    sec_ptrs = list(struct.unpack_from('<%dH' % nsec, blob, 4))
    pool_start = sec_ptrs[-1] + 2
    if pool_start < 4 + 2 * nsec or pool_start > len(blob):
        raise ValueError('bad pool start')
    n_off = (pool_start - (4 + 2 * nsec)) // 2
    offsets = list(struct.unpack_from('<%dH' % n_off, blob, 4 + 2 * nsec))
    # labels follow the string-offset table: labels[0] sits at the pool
    # start, label i+1 sits at offsets[i]+2 (some files have NUL filler
    # gaps between labels, so the pool is never walked sequentially)
    def read_at(pos):
        end = blob.index(0, pos)
        return blob[pos:end].decode('latin1')
    labels = [read_at(pool_start)]
    ref_end = pool_start
    for i, off in enumerate(offsets):
        if off + 2 >= len(blob):
            raise ValueError('offset %d out of range' % i)
        labels.append(read_at(off + 2))
        ref_end = blob.index(0, off + 2) + 1
    # any unreferenced trailing blank labels beyond the last referenced one
    # are derived filler; the encoder reproduces them from the byte count
    tail_nuls = len(blob) - ref_end
    # the tail bytes of the offset table can be printable and run straight
    # into labels[0] (ROSTEXT: 'AJA' + 'Historical data'); the merged view is
    # labels[0] itself and the encoder re-splits it after rebuilding
    prefix = label_prefix(blob, pool_start)
    labels[0] = prefix + labels[0]
    doc = {
        '_description': DESCRIPTIONS.get(
            '', 'shell string table labels and templates'),
        '_layout': LAYOUT,
        '_total': total,
        '_sectionCount': nsec,
        '_sectionPointers': sec_ptrs,
        '_stringOffsets': offsets,
        '_boundaryPrefixLen': len(prefix),
        '_trailingBlankNuls': tail_nuls,
        'labels': labels,
    }
    return doc


def encode_blob(doc):
    labels = doc['labels']
    if not isinstance(labels, list) or not all(isinstance(s, str)
                                               for s in labels):
        raise ValueError('labels must be a list of strings')
    nsec = doc['_sectionCount']
    sec_ptrs = list(doc['_sectionPointers'])[:nsec]
    if len(sec_ptrs) != nsec:
        raise ValueError('need %d section pointers' % nsec)
    n_cut = doc.get('_boundaryPrefixLen', 0)
    tail_nuls = doc.get('_trailingBlankNuls', 0)
    labels = list(labels)
    merged_head = labels[0][:n_cut] if n_cut else ''
    if n_cut:
        if len(labels[0]) < n_cut:
            raise ValueError('labels[0] shorter than the boundary prefix')
        labels[0] = labels[0][n_cut:]

    def build(pool_labels, ptrs):
        n_off = len(pool_labels) - 1
        if n_off < 1:
            raise ValueError('not enough labels')
        # the last section pointer always aims at the label pool
        pool_start = 4 + 2 * nsec + 2 * n_off
        ptrs = list(ptrs)
        ptrs[-1] = pool_start - 2
        out = bytearray()
        out += struct.pack('<HH', 0, nsec)
        out += struct.pack('<%dH' % nsec, *ptrs)
        offs = []
        cur = pool_start
        for s in pool_labels:
            data = s.encode('latin1')
            offs.append(cur - 2)
            cur += len(data) + 1
        # entries[] point at labels[1..n_off]; labels[0] (the pool's first
        # string) is never referenced by the string-offset table
        out += struct.pack('<%dH' % n_off, *offs[1:n_off + 1])
        for s in pool_labels:
            out += s.encode('latin1') + b'\x00'
        out += b'\x00' * tail_nuls
        out[0:2] = struct.pack('<H', len(out) - 3)
        return bytes(out), ptrs, pool_start

    def build_scatter(s0, pool_labels, ptrs):
        """Edited-file layout: the last two entry-referenced labels keep
        their original positions so the boundary bytes (the three printable
        bytes before the pool) stay identical and the merged labels[0] view
        stays stable; labels that no longer fit before the pinned tail move
        to the gap after it."""
        orig = doc['_stringOffsets']
        n_off = len(pool_labels) - 1
        pool_start = 4 + 2 * nsec + 2 * n_off
        ptrs = list(ptrs)
        ptrs[-1] = pool_start - 2
        # entry n_off-2 -> labels[n_off-1], entry n_off-1 -> labels[n_off]:
        # their byte positions are pinned to the originals
        pin1 = orig[-2] + 2
        pin2 = orig[-1] + 2
        out = bytearray()
        out += struct.pack('<HH', 0, nsec)
        out += struct.pack('<%dH' % nsec, *ptrs)
        targets = [0] * (n_off + 1)                # byte pos per label index
        targets[0] = pool_start
        pinned_idx = (n_off - 1, n_off)
        tail_pos = pin2 + 1
        cur = pool_start + len(pool_labels[0]) + 1
        for i in range(1, n_off):
            if i in pinned_idx:
                continue
            if cur + len(pool_labels[i]) + 1 > pin1:
                targets[i] = tail_pos
                tail_pos += len(pool_labels[i]) + 1
            else:
                targets[i] = cur
                cur += len(pool_labels[i]) + 1
        targets[n_off - 1] = pin1
        targets[n_off] = pin2
        # verify no label overlaps another
        spans = sorted((targets[i], len(pool_labels[i]) + 1, i)
                       for i in range(len(pool_labels)))
        for a, b in zip(spans, spans[1:]):
            if a[0] + a[1] > b[0]:
                raise ValueError('label layout overlap at label %d/%d'
                                 % (a[2], b[2]))
        file_len = spans[-1][0] + spans[-1][1]
        offs = [targets[i + 1] - 2 for i in range(n_off)]
        out += struct.pack('<%dH' % n_off, *offs)
        blob = bytearray(b'\x00' * file_len)
        for i, s in enumerate(pool_labels):
            data = s.encode('latin1') + b'\x00'
            at = targets[i] - pool_start
            blob[at:at + len(data)] = data
        out += blob
        out[0:2] = struct.pack('<H', len(out) - 3)
        return bytes(out), ptrs, pool_start

    pool = list(labels)
    built, sec_ptrs, pool_start = build(pool, sec_ptrs)
    if n_cut:
        # sequential rebuild only when the boundary prefix reproduces the
        # merged labels[0] head; otherwise scatter so the prefix stays
        # identical and the merged view is stable under edits
        prefix = label_prefix(built, pool_start)
        if prefix != merged_head:
            built, sec_ptrs, pool_start = build_scatter(
                merged_head, pool, sec_ptrs)
    return built


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == 'decode' and len(argv) == 5:
        name, inbin, outjson = argv[2], argv[3], argv[4]
        blob = open(inbin, 'rb').read()
        stem = name.rsplit('.', 1)[0].upper()
        doc = decode_blob(blob)
        doc['_description'] = DESCRIPTIONS.get(stem, doc['_description'])
        with open(outjson, 'w') as fh:
            json.dump(doc, fh, indent=1)
        return 0
    if cmd == 'encode' and len(argv) == 6:
        name, inbin, injson, outbin = argv[2], argv[3], argv[4], argv[5]
        doc = json.load(open(injson))
        blob = encode_blob(doc)
        with open(outbin, 'wb') as fh:
            fh.write(blob)
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
