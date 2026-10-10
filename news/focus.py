"""The player development focus: the rating each player's aging is steered toward, one line per player in
<game>/Mods/focus.txt, which mods\\aging.dll reads at each offseason. A line is `pid birth kind`, then the association's
STEM when the news bridge set it. parse, format, find, set_focus and clear_focus are pure; births reads a PYR file.
Standard library only.
"""
import re
import struct

import gamedata

KINDS = ('contact', 'power', 'speed', 'control', 'stuff', 'defense')
HITTER_KINDS = ('contact', 'power', 'speed', 'defense')
PITCHER_KINDS = ('control', 'stuff', 'defense')
MAX_PER_ASSN = 5
MAX_ENTRIES = 2000
MAX_FILE = 65536        # bytes of focus.txt that are read
HEADER = '# development focus: pid birth kind assn (written by the news bridge)'
DIGITS_RE = re.compile(r'[0-9]+')
ASSN_RE = re.compile(r'[A-Za-z0-9]{1,8}')


class FocusFull(Exception):
    """No room for another focus: MAX_PER_ASSN for the association, or MAX_ENTRIES in all."""


def _number(token, low, high):
    """token as an integer in low..high, or None. Decimal digits only: int() would also take a sign or underscores."""
    if DIGITS_RE.fullmatch(token) is None:
        return None
    try:
        n = int(token)
    except ValueError:      # more digits than int() takes
        return None
    return n if low <= n <= high else None


def parse(text):
    """The entries of focus.txt's text, in file order. A line that breaks a rule is skipped, and so is a later line
    for a (pid, birth) already named: aging.dll uses the first. Parsing stops at MAX_ENTRIES."""
    entries, named = [], set()
    for line in text.split('\n'):
        tokens = line.split()
        if len(tokens) < 3 or tokens[0].startswith('#'):
            continue
        pid = _number(tokens[0], 100, 32767)
        birth = _number(tokens[1], 0, 4294967295)
        kind = tokens[2].lower()
        if pid is None or birth is None or kind not in KINDS or (pid, birth) in named:
            continue
        assn = tokens[3].upper() if len(tokens) > 3 and ASSN_RE.fullmatch(tokens[3]) else None
        named.add((pid, birth))
        entries.append({'pid': pid, 'birth': birth, 'kind': kind, 'assn': assn})
        if len(entries) == MAX_ENTRIES:
            break
    return entries


def format(entries):
    """The text of focus.txt for entries: the header, then one line per entry, each ending in a newline."""
    lines = [HEADER]
    for e in entries:
        if e['assn'] is None:
            lines.append('%d %d %s' % (e['pid'], e['birth'], e['kind']))
        else:
            lines.append('%d %d %s %s' % (e['pid'], e['birth'], e['kind'], e['assn']))
    return '\n'.join(lines) + '\n'


def find(entries, pid, birth):
    """The entry for (pid, birth), or None."""
    return next((e for e in entries if e['pid'] == pid and e['birth'] == birth), None)


def set_focus(entries, assn, pid, birth, kind):
    """A new list with (pid, birth) focused on kind for assn. An entry already for (pid, birth) keeps its place and
    takes the new kind and assn. Otherwise the entry is appended, unless assn already has MAX_PER_ASSN entries or the
    list holds MAX_ENTRIES (FocusFull). entries is not changed."""
    if kind not in KINDS:
        raise ValueError('not a focus kind: %r' % (kind,))
    out = [dict(e) for e in entries]
    hit = find(out, pid, birth)
    if hit is not None:
        hit['kind'], hit['assn'] = kind, assn
        return out
    if sum(1 for e in out if e['assn'] == assn) >= MAX_PER_ASSN or len(out) >= MAX_ENTRIES:
        raise FocusFull('no room for another focus')
    out.append({'pid': pid, 'birth': birth, 'kind': kind, 'assn': assn})
    return out


def clear_focus(entries, pid, birth):
    """A new list without (pid, birth). entries is not changed."""
    return [dict(e) for e in entries if (e['pid'], e['birth']) != (pid, birth)]


def kinds_for(pos):
    """The kinds a player at position pos can be focused on: the pitcher's for 'P', the hitter's for any other."""
    return PITCHER_KINDS if pos == 'P' else HITTER_KINDS


def births(pyr_path):
    """{pid: birth serial} for every player gamedata.players keeps (pid >= 100 with a name), from a PYR file."""
    out = {}
    for rec in gamedata._records(pyr_path):
        pid = rec[0] | rec[1] << 8
        if pid >= 100 and gamedata._pname(rec):
            out[pid] = struct.unpack_from('<I', rec, gamedata.P_BORN)[0]
    return out
