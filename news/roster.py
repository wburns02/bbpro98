"""Real midseason moves written into a running association's ASN, between sessions: a player leaves one team's id window
for another's, the lineup, rotation and bullpen slots he held are refilled, and the teams' 'r' records are rewritten in
place (aigm.apply_trade's way: only the id windows change, each enciphered with the file's table). The moves come from
the MOV file work/lahman/build.py --moves writes ({"kind": "moves", "year", "moves": [{"pid", "name", "from", "to",
"at"}]}); one is due once its "from" team has played the share "at" of its schedule. move, problems, due and apply_due
are pure on windows dicts ({tid: [126 ints]}, aigm.read()['windows']) and players (gamedata.players); only apply works
on file bytes and nothing here writes a file. Standard library only.
"""
import copy
import math
import struct

import aigm

SwapError = aigm.SwapError
ACTIVE, WINDOW_OFF, WINDOW_LEN = aigm.ACTIVE, aigm.WINDOW_OFF, aigm.WINDOW_LEN
RESERVES = 15                       # reserve pairs from index ACTIVE: id at ACTIVE+2i, level at ACTIVE+2i+1
ORDERS = (77, 86)                   # the two batting orders (vs RHP, vs LHP): 9 ids, NONE for the pitcher's slot
ALIGNS = (95, 104)                  # the two alignments: C 1B 2B 3B SS LF CF RF, then DH or 0
ROTATION = (113, 119)               # slice of the rotation, 0 padded
BULLPEN = (120, 126)                # slice of the bullpen, 0 padded
LINEUP = 9
NONE = 0xFFFF
ALIGN_POS = ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
MIN_HITTERS, MIN_PITCHERS = 9, 5


def _pitcher(players, pid):
    return players[pid]['pos'] == 'P'


def _pairs(w):
    """The reserve pairs of a window as [(id, level)] (15 of them, (0, 0) for an empty one)."""
    return [(w[ACTIVE + 2 * i], w[ACTIVE + 2 * i + 1]) for i in range(RESERVES)]


def _put_pairs(w, pairs):
    """Writes the RESERVES pairs back as the reserve pairs of w."""
    for i, pair in enumerate(pairs):
        w[ACTIVE + 2 * i], w[ACTIVE + 2 * i + 1] = pair


def _best_hitter(w, taken, players, year):
    """The best-valued active hitter of w not in taken (ties: lower id). SwapError when there is none."""
    cands = [v for v in w[:ACTIVE] if v in players and not _pitcher(players, v) and v not in taken]
    if not cands:
        raise SwapError('no active hitter left to fill a lineup slot')
    return min(cands, key=lambda v: (-aigm.value(players[v], year), v))


def _leave(w, pid, players, year):
    """w (changed in place) with pid gone from team's window: from the active list (his slot takes the first reserve of
    his kind, else it is 0), the reserve pairs (later ones shift left), the batting orders and alignments (the
    substitute when a hitter, else the best active hitter not already in that list) and the rotation and bullpen (the
    substitute when a pitcher, else removed and the rest shift left). SwapError when no hitter is left to fill a
    lineup."""
    kind = _pitcher(players, pid)
    pairs, sub = _pairs(w), None
    if pid in w[:ACTIVE]:
        sub = next((p[0] for p in pairs if p[0] in players and _pitcher(players, p[0]) == kind), None)
        w[:ACTIVE] = [sub or 0 if v == pid else v for v in w[:ACTIVE]]
    kept = [p for p in pairs if p[0] not in (pid, sub)]
    _put_pairs(w, kept + [(0, 0)] * (RESERVES - len(kept)))
    for start in ORDERS + ALIGNS:
        lst = w[start:start + LINEUP]
        if pid in lst:
            fill = sub if sub in players and not _pitcher(players, sub) and sub not in lst else \
                _best_hitter(w, set(lst), players, year)
            w[start:start + LINEUP] = [fill if v == pid else v for v in lst]
    for lo, hi in (ROTATION, BULLPEN):
        lst = w[lo:hi]
        if pid in lst:
            if sub in players and _pitcher(players, sub) and sub not in lst:
                lst = [sub if v == pid else v for v in lst]
            else:
                lst = [v for v in lst if v != pid]
            w[lo:hi] = (lst + [0] * (hi - lo))[:hi - lo]


def _join(w, pid, players, year):
    """w (changed in place) with pid added to a team's window: the first empty active slot, else the lowest-valued
    active player of his kind who is in no order, alignment, rotation or bullpen (ties: lower id) goes to the first
    empty reserve pair and pid takes his slot (SwapError 'no room' when there is none). A hitter worth more than the
    alignment player at his position replaces him in both orders and both alignments; a pitcher worth more than the
    rotation's lowest-valued pitcher replaces him there and the displaced pitcher takes the bullpen's first 0 slot."""
    kind = _pitcher(players, pid)
    empty = [i for i in range(ACTIVE) if w[i] == 0]
    if empty:
        slot = empty[0]
    else:
        busy = set(w[ORDERS[0]:ROTATION[1]]) | set(w[BULLPEN[0]:BULLPEN[1]])     # orders, alignments, rotation, bullpen
        cands = [v for v in w[:ACTIVE] if v in players and _pitcher(players, v) == kind and v not in busy]
        pairs = _pairs(w)
        free = next((i for i, p in enumerate(pairs) if not p[0]), None)
        if not cands or free is None:
            raise SwapError('no room')
        out = min(cands, key=lambda v: (aigm.value(players[v], year), v))
        slot = w.index(out)
        pairs[free] = (out, 1)
        _put_pairs(w, pairs)
    w[slot] = pid
    mine = aigm.value(players[pid], year)
    if not kind:
        pos = players[pid]['pos']
        cur = w[ALIGNS[0] + ALIGN_POS.index(pos)] if pos in ALIGN_POS else NONE
        if cur in players and mine > aigm.value(players[cur], year):
            for start in ORDERS + ALIGNS:
                w[start:start + LINEUP] = [pid if v == cur else v for v in w[start:start + LINEUP]]
        return
    rotation = [v for v in w[ROTATION[0]:ROTATION[1]] if v in players]
    if rotation:
        low = min(rotation, key=lambda v: (aigm.value(players[v], year), v))
        if mine > aigm.value(players[low], year):
            w[w.index(low, *ROTATION)] = pid
            pen = w[BULLPEN[0]:BULLPEN[1]]
            if 0 in pen:
                w[BULLPEN[0] + pen.index(0)] = low


def move(windows, pid, src, dst, players, year):
    """A new windows dict (every window copied; the input is never changed) with pid moved from team src to team dst.
    SwapError when a team has no window, pid is not a known player, is not on src's active or reserve list, is already
    in dst's window, dst has no room, or src has no hitter left to refill a lineup he held. The src side and the dst
    side are _leave and _join."""
    if src not in windows or dst not in windows:
        raise SwapError('a team has no live r record')
    if pid not in players:
        raise SwapError('%s is not a known player' % pid)
    ws, wd = windows[src], windows[dst]
    if pid not in ws[:ACTIVE] and pid not in [p[0] for p in _pairs(ws)]:
        raise SwapError('%d is not on the roster of team %d' % (pid, src))
    if pid in wd:
        raise SwapError('%d is already on team %d' % (pid, dst))
    out = {tid: list(w) for tid, w in windows.items()}
    _leave(out[src], pid, players, year)
    _join(out[dst], pid, players, year)
    return out


def problems(windows, players):
    """The problems with a windows dict, as strings (empty when there are none): an id on two teams, an id in an order,
    alignment, rotation or bullpen (not 0 or NONE) that is not on its team's active list, a team with fewer than
    MIN_HITTERS active hitters or MIN_PITCHERS active pitchers (players not in `players` count as neither)."""
    out, owner = [], {}
    for tid in sorted(windows):
        for v in sorted({v for v in windows[tid] if 100 <= v <= 9999}):
            if owner.setdefault(v, tid) != tid:
                out.append('%d is on team %d and team %d' % (v, owner[v], tid))
    for tid in sorted(windows):
        w = windows[tid]
        active = set(w[:ACTIVE])
        for name, starts in (('batting order', ORDERS), ('alignment', ALIGNS)):
            out += _missing(tid, name, [v for s in starts for v in w[s:s + LINEUP]], active)
        out += _missing(tid, 'rotation', w[ROTATION[0]:ROTATION[1]], active)
        out += _missing(tid, 'bullpen', w[BULLPEN[0]:BULLPEN[1]], active)
        known = [v for v in w[:ACTIVE] if v in players]
        pitchers = sum(1 for v in known if _pitcher(players, v))
        if len(known) - pitchers < MIN_HITTERS:
            out.append('team %d has %d active hitters, needs %d' % (tid, len(known) - pitchers, MIN_HITTERS))
        if pitchers < MIN_PITCHERS:
            out.append('team %d has %d active pitchers, needs %d' % (tid, pitchers, MIN_PITCHERS))
    return out


def _missing(tid, name, ids, active):
    return ['%d is in the %s of team %d but not on its active roster' % (v, name, tid)
            for v in sorted({v for v in ids if v not in (0, NONE) and v not in active})]


def apply(asn_bytes, windows):
    """The ASN bytes with each team's id window in windows rewritten, enciphered with the file's table as
    aigm.apply_trade writes one. A window equal to the file's is left alone, so only the windows that differ change
    and every other byte is as it was; teams of the file that windows lacks are untouched. ValueError for a team with
    no live r record, a window that is not WINDOW_LEN ids, or an id that does not fit 16 bits."""
    loc = aigm.locate(asn_bytes)
    current = aigm._windows(asn_bytes, loc)
    t, _ = aigm._tables(asn_bytes)
    out = bytearray(asn_bytes)
    for tid in sorted(windows):
        w = list(windows[tid])
        if tid not in loc['r']:
            raise ValueError('team %s has no live r record' % tid)
        if len(w) != WINDOW_LEN:
            raise ValueError('team %d: a window of %d ids, needs %d' % (tid, len(w), WINDOW_LEN))
        if w == current[tid]:
            continue
        try:
            raw = struct.pack('<%dH' % WINDOW_LEN, *w)
        except struct.error:
            raise ValueError('team %d: an id does not fit 16 bits' % tid) from None
        off = loc['r'][tid][0] + WINDOW_OFF
        out[off:off + 2 * WINDOW_LEN] = bytes(t[x] for x in raw)
    return bytes(out)


def _counts(assoc):
    """{tid: [scheduled, played]} from assoc['games'] (the regular season): the games each team is in, and the ones
    played."""
    out = {}
    for g in assoc.get('games', ()):
        for tid in {g.get('away'), g.get('home')}:
            row = out.setdefault(tid, [0, 0])
            row[0] += 1
            row[1] += bool(g.get('played'))
    return out


def _number(v):
    return type(v) in (int, float)


def due(moves_doc, assoc, ledger):
    """The indexes of moves_doc['moves'] that are due and not in the ledger: not an index of ledger['done'], and the
    "from" team has played at least ceil(at * its scheduled games) games. Never due: a move whose "from" team has no
    scheduled game or is not an int, or whose "at" is not a number. ledger may be None. at * games is rounded to 6
    places before the ceil so float noise (0.07 * 100) does not add a game."""
    done = (ledger or {}).get('done') or {}
    counts = _counts(assoc)
    out = []
    for i, m in enumerate(moves_doc.get('moves') or []):
        if str(i) in done or not isinstance(m, dict) or not _number(m.get('at')) or type(m.get('from')) is not int:
            continue
        scheduled, played = counts.get(m.get('from'), (0, 0))
        if scheduled and played >= math.ceil(round(m['at'] * scheduled, 6)):
            out.append(i)
    return out


def apply_due(asn_bytes, moves_doc, assoc, players, year, ledger):
    """(new_bytes, ledger) after the due moves are applied in index order with move(). A move that raises SwapError (or
    is malformed) is skipped: the ledger holds {"status": "skipped", "reason": ..., "played": games} for it, an applied
    one {"status": "done", "played": games} (the from team's games played). ledger is {"kind": "moves", "year": year,
    "done": {str(index): entry}}, a copy of the one passed (None starts a new one); the inputs are never changed.
    ValueError, with nothing applied, when the result has a problem() the file's windows did not have."""
    new = copy.deepcopy(ledger) if ledger else {'kind': 'moves', 'year': year, 'done': {}}
    new.setdefault('done', {})
    before = aigm._windows(asn_bytes, aigm.locate(asn_bytes))
    windows, counts = before, _counts(assoc)
    for i in due(moves_doc, assoc, ledger):
        m = moves_doc['moves'][i]
        entry = {'played': counts.get(m.get('from'), (0, 0))[1]}
        try:
            if not all(type(m.get(k)) is int for k in ('pid', 'from', 'to')):
                raise SwapError('the move is malformed')
            windows = move(windows, m['pid'], m['from'], m['to'], players, year)
            entry['status'] = 'done'
        except SwapError as e:
            entry.update(status='skipped', reason=str(e))
        new['done'][str(i)] = entry
    old_problems = set(problems(before, players))
    fresh = [p for p in problems(windows, players) if p not in old_problems]
    if fresh:
        raise ValueError(fresh[0])
    return apply(asn_bytes, windows), new
