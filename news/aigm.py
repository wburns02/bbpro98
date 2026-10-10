"""AI GM offseason trades: in the preseason the computer-run teams swap bench hitters to fill each other's needs,
and each human-run team gets proposals to accept or reject in the game. A player is worth his rating index times
an age factor (contracts._index); a swap is two bench hitters at different positions, each worth more than the
starter he would replace on the other side, within BALANCE of each other. The windows are the ASN's 'r' records
(the id window at offset 42, enciphered like the rest of the member). plan, value and age_factor are pure; locate,
read, apply_trade and validate work on the file's bytes. Standard library only.
"""
import collections
import itertools
import struct

import gamedata   # noqa: F401 (puts work/ on sys.path before ctree and league)
import ctree
import contracts
import league

MAX_TRADES = 6          # computer-computer trades per run
MAX_PROPOSALS = 3       # per human team
BALANCE = 0.10          # the two players' values differ by at most 10% of the larger
ACTIVE = 25
WINDOW_OFF = 42
WINDOW_LEN = 126
T_OWNER = 0x0c
HITTER_POS = ('1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
_RESERVE = range(ACTIVE, 54, 2)     # the reserves' ids: window indices 25, 27, ..., 53 (each followed by its level)
_Slot = collections.namedtuple('_Slot', 'bench starter need')


class SwapError(Exception):
    """A trade that does not fit the windows it is applied to."""


def age_factor(age):
    if age is None:
        return 1.0
    if age <= 26:
        return 1.10
    if age <= 30:
        return 1.0
    if age <= 33:
        return 0.9
    return 0.75


def value(player, year):
    """A player's worth: his rating index times the age factor for his age in year (1.0 when either is unknown)."""
    age = None if year is None or player['born'] is None else year - player['born']
    return contracts._index(player) * age_factor(age)


def locate(asn_bytes):
    """{'r': {tid: (off, pl)}, 't': {tid: (off, pl)}} for the live records of the members named r and t. A record is
    live when its raw byte 0, the team id, is 1..MAX_TEAM; off is its payload offset in the file. The one call of
    ctree.parse."""
    _, by_mem, members, *_ = ctree.parse(asn_bytes)
    out = {'r': {}, 't': {}}
    for m in members:
        name = m['name'].rsplit('.', 1)[0].lower()
        if m['kind'] != 'data' or name not in out:
            continue
        for r in by_mem.get(m['num'], []):
            if r.pl and 1 <= asn_bytes[r.off] <= gamedata.MAX_TEAM:
                out[name].setdefault(asn_bytes[r.off], (r.off, r.pl))
    return out


def _tables(asn_bytes):
    """(t, inv): the file's cipher and its inverse, seeded at bytes 0x310-0x311. A plain byte x is stored as t[x]."""
    t = league._forward((asn_bytes[0x310], asn_bytes[0x311]))
    inv = bytearray(256)
    for x, y in enumerate(t):
        inv[y] = x
    return t, bytes(inv)


def _windows(asn_bytes, loc):
    """{tid: [126 ints]}: each live team's id window, deciphered. ValueError for a record too short to hold one."""
    _, inv = _tables(asn_bytes)
    out = {}
    for tid, (off, pl) in loc['r'].items():
        if pl < WINDOW_OFF + 2 * WINDOW_LEN:
            raise ValueError('team %d: an r record of %d bytes has no id window' % (tid, pl))
        raw = asn_bytes[off + WINDOW_OFF:off + WINDOW_OFF + 2 * WINDOW_LEN]
        out[tid] = list(struct.unpack('<%dH' % WINDOW_LEN, bytes(inv[b] for b in raw)))
    return out


def read(asn_bytes):
    """{'windows': {tid: [126 ints]}, 'human': frozenset(tids)}: every live team's id window, and the teams whose owner
    byte (0x0c of the t record) is 1, Human."""
    loc = locate(asn_bytes)
    _, inv = _tables(asn_bytes)
    human = frozenset(tid for tid, (off, pl) in loc['t'].items()
                      if pl > T_OWNER and inv[asn_bytes[off + T_OWNER]] == 1)
    return {'windows': _windows(asn_bytes, loc), 'human': human}


def _ids(values):
    """The player-sized ids (100..9999) among values, in order."""
    return [v for v in values if 100 <= v <= 9999]


def _active(w, players):
    """The active players of a window: the ids at 0..24 that are in players, in window order."""
    return [v for v in w[:ACTIVE] if 100 <= v <= 9999 and v in players]


def _slots(w, players, year):
    """{pos: _Slot} for each hitter position of a window: the bench (active hitters there not in the lineups, the ids at
    25 on), the starter (the best of the active hitters there in the lineups, ties to the lower id) and the need (the
    starter's value, else the best bench value, else 0.0)."""
    lineup = set(w[ACTIVE:])
    active = _active(w, players)
    out = {}
    for pos in HITTER_POS:
        here = [pid for pid in active if players[pid]['pos'] == pos]
        starters = [pid for pid in here if pid in lineup]
        starter = min(starters, key=lambda pid: (-value(players[pid], year), pid)) if starters else None
        if starter is not None:
            need = value(players[starter], year)
        else:
            need = max((value(players[pid], year) for pid in here), default=0.0)
        out[pos] = _Slot([pid for pid in here if pid not in lineup], starter, need)
    return out


def _order(trade):
    """Sort key for the best trade first: the highest gain, then the smallest (a, b, a_gives, b_gives)."""
    return (-trade['gain'], trade['a'], trade['b'], trade['a_gives'], trade['b_gives'])


def _people(trade):
    """The player ids a trade touches: the two that move and the two starters it displaces."""
    return {trade['a_gives'], trade['b_gives'], trade['a_drops'], trade['b_drops']} - {None}


def _candidates(a, sa, b, sb, players, year):
    """The candidate trades between teams a < b, from their slots: a bench hitter of a at one position (a_pos) and a
    bench hitter of b at another (b_pos), each worth more than the starter the other side would lose there, and the
    two values within BALANCE of the larger."""
    out = []
    for x in HITTER_POS:
        for y in HITTER_POS:
            if x == y:
                continue
            for ag in sa[x].bench:
                va = value(players[ag], year)
                for bg in sb[y].bench:
                    vb = value(players[bg], year)
                    if not (va > sb[x].need and vb > sa[y].need):
                        continue
                    if abs(va - vb) > BALANCE * max(va, vb):
                        continue
                    gain = (va - sb[x].need) + (vb - sa[y].need)
                    out.append({'a': a, 'b': b, 'a_gives': ag, 'b_gives': bg, 'a_pos': x, 'b_pos': y,
                                'b_drops': sb[x].starter, 'a_drops': sa[y].starter, 'gain': round(gain, 2)})
    return out


def _pick(cands, limit):
    """The candidates taken best first, each one dropping every candidate that uses either of its teams, until limit or
    none is left."""
    chosen, left = [], cands
    while left and len(chosen) < limit:
        best = min(left, key=_order)
        chosen.append(best)
        used = (best['a'], best['b'])
        left = [c for c in left if c['a'] not in used and c['b'] not in used]
    return chosen


def plan(windows, players, year, human=frozenset()):
    """{'trades': [...], 'proposals': [...]} for one preseason, from the windows (never changed). Trades: the best
    computer-computer swaps, at most MAX_TRADES, one per team. Proposals: for each human team in order, up to
    MAX_PROPOSALS swaps with a computer team, on the windows after those trades, never using a player of a chosen trade
    or of an earlier proposal of that team. A trade is a dict with a the lower team id."""
    slots = {tid: _slots(w, players, year) for tid, w in windows.items()}
    pairs = [(a, b) for a, b in itertools.combinations(sorted(windows), 2) if a not in human and b not in human]
    cands = [t for a, b in pairs for t in _candidates(a, slots[a], b, slots[b], players, year)]
    trades = _pick(cands, MAX_TRADES)

    done = {tid: list(w) for tid, w in windows.items()}
    for t in trades:
        done[t['a']], done[t['b']] = _swapped(done, t)
    done_slots = {tid: _slots(w, players, year) for tid, w in done.items()}
    taken = set()
    for t in trades:
        taken |= _people(t)

    proposals = []
    for h in sorted(tid for tid in done if tid in human):
        cands = []
        for tid in sorted(done):
            if tid == h or tid in human:
                continue
            a, b = min(h, tid), max(h, tid)
            cands += _candidates(a, done_slots[a], b, done_slots[b], players, year)
        used = set(taken)
        mine = []
        for c in sorted(cands, key=_order):
            if len(mine) == MAX_PROPOSALS:
                break
            if _people(c) & used:
                continue
            mine.append(c)
            used |= _people(c)
        proposals += mine
    return {'trades': trades, 'proposals': proposals}


def _swapped(windows, trade):
    """(a's window, b's window) after the trade, as new lists. SwapError when the trade does not fit the windows (the
    rules apply_trade lists)."""
    a, b = trade['a'], trade['b']
    if a not in windows or b not in windows:
        raise SwapError('a team has no live r record')
    wa, wb = windows[a], windows[b]
    ag, bg, ad, bd = trade['a_gives'], trade['b_gives'], trade['a_drops'], trade['b_drops']
    if ag not in wa[:ACTIVE]:
        raise SwapError('%d is not on the active roster of team %d' % (ag, a))
    if bg not in wb[:ACTIVE]:
        raise SwapError('%d is not on the active roster of team %d' % (bg, b))
    if bg in wa:
        raise SwapError('%d is already on team %d' % (bg, a))
    if ag in wb:
        raise SwapError('%d is already on team %d' % (ag, b))
    if bd is not None and bd not in wb[ACTIVE:]:
        raise SwapError('%d is not in the lineups of team %d' % (bd, b))
    if ad is not None and ad not in wa[ACTIVE:]:
        raise SwapError('%d is not in the lineups of team %d' % (ad, a))
    for tid, w in windows.items():
        if tid not in (a, b) and (ag in w or bg in w):
            raise SwapError('a traded player is on team %d' % tid)
    new_a = [bg if v == ag else v for v in wa]
    new_b = [ag if v == bg else v for v in wb]
    if bd is not None:
        new_b[ACTIVE:] = [ag if v == bd else v for v in new_b[ACTIVE:]]
    if ad is not None:
        new_a[ACTIVE:] = [bg if v == ad else v for v in new_a[ACTIVE:]]
    return new_a, new_b


def apply_trade(asn_bytes, trade):
    """The ASN bytes with one trade applied: the two teams' id windows change and nothing else does (each rewritten
    enciphered with the file's table). SwapError, and no bytes, when the trade does not fit the file's windows."""
    loc = locate(asn_bytes)
    windows = _windows(asn_bytes, loc)
    new_a, new_b = _swapped(windows, trade)
    t, _ = _tables(asn_bytes)
    out = bytearray(asn_bytes)
    for tid, w in ((trade['a'], new_a), (trade['b'], new_b)):
        off = loc['r'][tid][0] + WINDOW_OFF
        out[off:off + 2 * WINDOW_LEN] = bytes(t[x] for x in struct.pack('<%dH' % WINDOW_LEN, *w))
    return bytes(out)


def validate(before, after, players):
    """The problems with the windows after some trades, as strings (empty when there are none). before and after are
    windows dicts ({tid: [126 ints]}, read()['windows']). The teams and the active ids must be the same, no id may be on
    two teams, and each team must keep its number of active pitchers, have at least 5 pitchers and 8 other players, and
    have every lineup player (not a reserve) on its active roster."""
    bw, aw = before, after
    if set(bw) != set(aw):
        return ['the teams changed']
    problems = []
    before_ids = collections.Counter(v for w in bw.values() for v in _ids(w[:ACTIVE]))
    after_ids = collections.Counter(v for w in aw.values() for v in _ids(w[:ACTIVE]))
    if before_ids != after_ids:
        problems.append('the active players changed')
    owner = {}
    for tid in sorted(aw):
        for v in sorted(set(_ids(aw[tid]))):
            if owner.setdefault(v, tid) != tid:
                problems.append('%d is on team %d and team %d' % (v, owner[v], tid))
    for tid in sorted(aw):
        w = aw[tid]
        act = _ids(w[:ACTIVE])
        pitchers = sum(1 for v in act if v in players and players[v]['pos'] == 'P')
        others = sum(1 for v in act if v in players and players[v]['pos'] != 'P')
        was = sum(1 for v in _ids(bw[tid][:ACTIVE]) if v in players and players[v]['pos'] == 'P')
        if pitchers != was:
            problems.append('team %d has %d active pitchers, had %d' % (tid, pitchers, was))
        if pitchers < 5:
            problems.append('team %d has %d active pitchers, needs 5' % (tid, pitchers))
        if others < 8:
            problems.append('team %d has %d active non-pitchers, needs 8' % (tid, others))
        missing = sorted({w[i] for i in range(ACTIVE, WINDOW_LEN)
                          if i not in _RESERVE and w[i] >= 100 and w[i] in players and w[i] not in w[:ACTIVE]})
        for v in missing:
            problems.append('%d is in a lineup of team %d but not on its active roster' % (v, tid))
    return problems
