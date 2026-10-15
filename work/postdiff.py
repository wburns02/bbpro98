"""Dump and diff the members of ASN snapshots of one association. Read only: each file is opened 'rb', nothing is
written.

    python3 work/postdiff.py A B [C] [--member NAME] [--flag15]

Prints the member table (record count and payload lengths per file), then every record whose payload differs between
A and B (and between B and C when C is given) as `member key#n offset: old -> new`, one line per changed byte run, with
the u8 view of the run and the u16 little-endian view of the even-aligned words that cover it. Capped at CAP lines per
member. `key` is the record's first raw byte as gamedata._members returns it and `n` counts the records of that key in
the old file; records of one key are aligned with difflib, so an inserted or removed record does not shift the rest.

`--member NAME` limits the diffs to one member. `--flag15` (with `--member s`, the default) prints instead only the 's'
records with p[15] != 0 of each file, decoded with league._game_json, plus p[15] and the raw bytes 15..20 inclusive.
"""
import argparse
import difflib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'news'))
sys.path.insert(0, HERE)
import gamedata  # noqa: E402
import league    # noqa: E402

CAP = 200           # diff lines printed per member
RUN_SHOW = 8        # bytes of one changed run shown per side
FLAG_AT = 15        # the byte gamedata.association() requires to be 0 for a regular-season game
FLAG_SHOW = slice(FLAG_AT, 21)      # raw bytes 15..20 inclusive


def load(path):
    """{member short name: [(key, plain payload)]} of one ASN file, found by member name."""
    with open(path, 'rb') as fh:
        return gamedata._members(fh.read())


def lengths(recs):
    """The payload lengths of a member: '292', '17x2400 19x3' for up to four distinct ones, else 'min-max'."""
    count = {}
    for _, p in recs:
        count[len(p)] = count.get(len(p), 0) + 1
    if not count:
        return '-'
    if len(count) == 1:
        return str(next(iter(count)))
    if len(count) <= 4:
        return ' '.join('%dx%d' % (n, k) for n, k in sorted(count.items()))
    return '%d-%d' % (min(count), max(count))


def table(labels, mems):
    """Lines of the member table: one row per member, the record count and payload lengths in each file."""
    names = []
    for mem in mems:
        names += [n for n in mem if n not in names]
    head = ['member'] + [c for lab in labels for c in (lab + ' n', lab + ' len')]
    rows = [head]
    for name in names:
        row = [name]
        for mem in mems:
            recs = mem.get(name)
            row += ['-', '-'] if recs is None else [str(len(recs)), lengths(recs)]
        rows.append(row)
    width = [max(len(r[i]) for r in rows) for i in range(len(head))]
    return ['  '.join(c.ljust(w) for c, w in zip(r, width)).rstrip() for r in rows]


def runs(a, b):
    """(start, end) of each maximal run of differing bytes within the common length of a and b."""
    out, i, n = [], 0, min(len(a), len(b))
    while i < n:
        if a[i] == b[i]:
            i += 1
            continue
        j = i
        while j < n and a[j] != b[j]:
            j += 1
        out.append((i, j))
        i = j
    return out


def _vals(vs, shown):
    return ','.join(str(v) for v in vs[:shown]) + ('+%d' % (len(vs) - shown) if len(vs) > shown else '')


def run_line(name, tag, a, b, s, e):
    """One changed run [s, e): the u8 view, then the u16 LE view of the words covering it (when a whole word fits)."""
    line = '%s %s %d: u8 %s -> %s' % (name, tag, s, _vals(list(a[s:e]), RUN_SHOW), _vals(list(b[s:e]), RUN_SHOW))
    w0, w1 = s & ~1, min((e + 1) & ~1, min(len(a), len(b)) & ~1)
    if w1 > w0:
        wa = struct.unpack_from('<%dH' % ((w1 - w0) // 2), a, w0)
        wb = struct.unpack_from('<%dH' % ((w1 - w0) // 2), b, w0)
        line += ' | u16@%d %s -> %s' % (w0, _vals(wa, RUN_SHOW // 2), _vals(wb, RUN_SHOW // 2))
    return line


def pair_lines(name, key, n, old, new):
    """Lines for one old/new record pair; empty when the payloads are equal."""
    tag = '%d#%d' % (key, n)
    out = []
    if len(old) != len(new):
        out.append('%s %s: length %d -> %d' % (name, tag, len(old), len(new)))
    out += [run_line(name, tag, old, new, s, e) for s, e in runs(old, new)]
    return out


def diff_member(name, old, new):
    """(lines, changed, added, removed) for one member between two files' record lists."""
    ko, kn = {}, {}
    for recs, by in ((old, ko), (new, kn)):
        for key, p in recs:
            by.setdefault(key, []).append(p)
    lines, changed, added, removed = [], 0, 0, 0
    for key in sorted(set(ko) | set(kn)):
        lo, ln = ko.get(key, []), kn.get(key, [])
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, lo, ln, autojunk=False).get_opcodes():
            if op == 'equal':
                continue
            k = min(i2 - i1, j2 - j1)
            for t in range(k):
                lines += pair_lines(name, key, i1 + t, lo[i1 + t], ln[j1 + t])
            changed += k
            for i in range(i1 + k, i2):
                lines.append('%s %d#%d: removed (len %d)' % (name, key, i, len(lo[i])))
            for j in range(j1 + k, j2):
                lines.append('%s %d#new%d: added (len %d)' % (name, key, j, len(ln[j])))
            removed += i2 - i1 - k
            added += j2 - j1 - k
    return lines, changed, added, removed


def diff_files(lab_old, lab_new, old, new, only=None):
    """Lines for every member's diff between two loaded files, CAP lines per member."""
    out = []
    for name in list(old) + [n for n in new if n not in old]:
        if only and name != only:
            continue
        lines, changed, added, removed = diff_member(name, old.get(name, []), new.get(name, []))
        out.append('== %s %s->%s: %d changed, %d added, %d removed, %d lines' % (
            name, lab_old, lab_new, changed, added, removed, len(lines)))
        out += lines[:CAP]
        if len(lines) > CAP:
            out.append('... %d more %s lines not shown' % (len(lines) - CAP, name))
    return out


def team_names(mem):
    """{team id: name} from the 't' member, read as gamedata.association() reads it."""
    return {key: league._cstr(p, 0x12, league.NAME_FIELD - 1) for key, p in mem.get('t', [])
            if 1 <= key <= gamedata.MAX_TEAM}


def flag15_lines(label, mem):
    """The 's' records of one file with p[15] != 0, decoded, plus a count line."""
    names, out, seen, total = team_names(mem), [], {}, 0
    for key, p in mem.get('s', []):
        n = seen[key] = seen.get(key, -1) + 1
        total += 1
        if len(p) <= FLAG_AT or p[FLAG_AT] == 0:
            continue
        head = '%s s %d#%d: len %d p15=%d bytes15..20=%s' % (label, key, n, len(p), p[FLAG_AT], p[FLAG_SHOW].hex(' '))
        if len(p) < 17:
            out.append(head + ' (too short for _game_json)')
            continue
        g = league._game_json(p)
        out.append(head + ' ' + ' '.join('%s=%s' % kv for kv in g.items())
                   + ' away_name=%s home_name=%s' % (names.get(g['away'], '?'), names.get(g['home'], '?')))
    out.append('%s: %d of %d s records have p[15] != 0' % (label, len(out), total))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='Dump and diff the members of ASN snapshots (read only).')
    ap.add_argument('a', help='first snapshot')
    ap.add_argument('b', help='second snapshot')
    ap.add_argument('c', nargs='?', help='optional third snapshot, diffed against the second')
    ap.add_argument('--member', help='limit the diffs to this member (short name, e.g. s)')
    ap.add_argument('--flag15', action='store_true', help="print only the 's' records with p[15] != 0")
    args = ap.parse_args(argv)
    if args.flag15 and args.member not in (None, 's'):
        ap.error('--flag15 reads the s member; drop --member or use --member s')
    paths = [p for p in (args.a, args.b, args.c) if p]
    labels = ['A', 'B', 'C'][:len(paths)]
    mems = []
    for path in paths:
        try:
            mems.append(load(path))
        except (OSError, ValueError, KeyError, IndexError, struct.error) as exc:
            print('postdiff: cannot read %s: %s' % (path, exc), file=sys.stderr)
            return 2
    if args.flag15:
        for lab, mem in zip(labels, mems):
            print('\n'.join(flag15_lines(lab, mem)))
        return 0
    for lab, path in zip(labels, paths):
        print('%s = %s (%d bytes)' % (lab, path, os.path.getsize(path)))
    print('\n'.join(table(labels, mems)))
    for i in range(len(mems) - 1):
        print('\n'.join(diff_files(labels[i], labels[i + 1], mems[i], mems[i + 1], args.member)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
