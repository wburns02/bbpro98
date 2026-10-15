"""AI GM trades. In the preseason the computer-run teams swap bench hitters and spare pitchers to fill each
other's needs, and each human-run team gets proposals to accept or reject in the game; at the July deadline a contender
buys a rebuilding team's veteran for a prospect. A team plays in a mode (offseason_modes: its rank by strength;
deadline_modes: its place in its division) that tilts how it values age (mode_value). A player is worth his rating
index times an age factor (contracts._index); a swap is two players, each worth more to the team getting him than the
player he would replace, within BALANCE of each other. With a stem the teams judge other teams' players through the
scouting fog (fog.view) and a rebuilding side also weighs the salary it sheds. The windows are the ASN's 'r' records
(the id window at offset 42, enciphered like the rest of the member). plan, deadline_plan, the modes and the values
are pure; locate, read, apply_trade and validate work on the file's bytes; apply_deadline works on windows through
roster.move. Standard library only.
"""
import collections
import itertools
import statistics
import struct

import gamedata   # noqa: F401 (puts work/ on sys.path before ctree and league)
import ctree
import contracts
import fog
import league

MAX_TRADES = 6          # computer-computer trades per run
MAX_PROPOSALS = 3       # per human team
BALANCE = 0.10          # the two players' values differ by at most 10% of the larger
ACTIVE = 25
WINDOW_OFF = 42
WINDOW_LEN = 126
T_OWNER = 0x0c
HITTER_POS = ('1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
ORDERS = (77, 86)       # the two batting orders (9 ids each) ...
ALIGNS = (95, 104)      # ... and the two alignments: C 1B 2B 3B SS LF CF RF, then DH or 0
ROTATION = (113, 119)   # slices of the window, 0 padded
BULLPEN = (120, 126)
ALIGN_POS = ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
DEADLINE_LO, DEADLINE_HI = 0.55, 0.65   # the deadline window: the share of the schedule played
CONTEND_GB, REBUILD_GB = 5, 12          # deadline modes: games back at most / at least
VET_AGE, PROSPECT_AGE = 29, 26          # a deadline veteran is at least, a prospect at most, this old
FAIR = 0.9              # a deadline side receives at least this share of what it gives
_RESERVE = range(ACTIVE, 54, 2)     # the reserves' ids: window indices 25, 27, ..., 53 (each followed by its level)
_Slot = collections.namedtuple('_Slot', 'bench starter need')
_Arms = collections.namedtuple('_Arms', 'spare low need')


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


def _age(player, year):
    """The player's age in year, None when either is unknown."""
    return None if year is None or player['born'] is None else year - player['born']


def value(player, year):
    """A player's worth: his rating index times the age factor for his age in year (1.0 when either is unknown)."""
    return contracts._index(player) * age_factor(_age(player, year))


def mode_value(player, year, mode):
    """A player's worth to a team in a mode: his rating index times a factor by age in year. contend: 1.0 up to 33, 0.8
    above. rebuild: 1.25 up to 26, 1.0 for 27..30, 0.6 from 31. Any other mode (neutral): age_factor. An unknown age is
    1.0 in every mode."""
    age = _age(player, year)
    if age is None:
        factor = 1.0
    elif mode == 'contend':
        factor = 1.0 if age <= 33 else 0.8
    elif mode == 'rebuild':
        factor = 1.25 if age <= 26 else 1.0 if age <= 30 else 0.6
    else:
        factor = age_factor(age)
    return contracts._index(player) * factor


def strength(windows, players, year):
    """{tid: float}: the sum of value() over each team's active ids (ids not in players count nothing)."""
    return {tid: sum(value(players[pid], year) for pid in _active(w, players)) for tid, w in windows.items()}


def offseason_modes(windows, players, year):
    """{tid: 'contend'|'rebuild'|'neutral'}: the teams sorted by strength (highest first, ties to the lower tid);
    the top len // 3 contend, the bottom len // 3 rebuild, the rest are neutral."""
    power = strength(windows, players, year)
    order = sorted(windows, key=lambda tid: (-power[tid], tid))
    third = len(order) // 3
    modes = dict.fromkeys(order, 'neutral')
    modes.update(dict.fromkeys(order[:third], 'contend'))
    modes.update(dict.fromkeys(order[len(order) - third:], 'rebuild'))
    return modes


def _pct(team):
    played = team.get('w', 0) + team.get('l', 0)
    return team.get('w', 0) / played if played else 0.0


def deadline_modes(teams):
    """{tid: mode} from the standings in teams ({tid: {'w', 'l', 'league', 'division', ...}}): a team's games back is
    ((leader w - w) + (l - leader l)) / 2 against the best win pct of its (league, division) (ties to more wins,
    then the lower tid). Up to CONTEND_GB (5) back is contend, REBUILD_GB (12) or more is rebuild, between is
    neutral. A division leader is 0 back, so it contends."""
    groups = {}
    for tid, t in teams.items():
        groups.setdefault((t.get('league'), t.get('division')), []).append(tid)
    out = {}
    for tids in groups.values():
        lead = teams[min(tids, key=lambda tid: (-_pct(teams[tid]), -teams[tid].get('w', 0), tid))]
        for tid in tids:
            t = teams[tid]
            back = ((lead.get('w', 0) - t.get('w', 0)) + (t.get('l', 0) - lead.get('l', 0))) / 2
            out[tid] = 'contend' if back <= CONTEND_GB else 'rebuild' if back >= REBUILD_GB else 'neutral'
    return out


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


class _View:
    """What the teams see while they plan: see(viewer, pid, own) is the mode value the viewer puts on a player, from his
    true ratings (stem None) or, with a stem, from fog.view as that team's scouts read him (own=True for a player of the
    viewer's own, whom they see twice as well). Each answer is computed once. salary_term is the rebuild side's
    salary relief."""

    def __init__(self, players, year, stem, modes, salaries=None):
        self.players, self.year, self.stem, self.modes = players, year, stem, modes
        self.salaries = salaries or {}
        numbers = [v for v in self.salaries.values() if type(v) in (int, float)]
        self.median = statistics.median(numbers) if numbers else 0.0
        self._seen = {}

    def see(self, viewer, pid, own=False):
        key = (viewer, pid, own)
        if key not in self._seen:
            p = self.players[pid]
            if self.stem is not None:
                p = fog.view(p, self.stem, viewer, self.year, own=own, pid=pid)
            self._seen[key] = mode_value(p, self.year, self.modes.get(viewer))
        return self._seen[key]

    def worth(self, pid):
        """The player's true value() for the year: what no team's mode or eyes change."""
        return value(self.players[pid], self.year)

    def mine(self, tid):
        """pid -> the value team tid puts on one of its own players."""
        return lambda pid: self.see(tid, pid, True)

    def salary_term(self, tid, out, got):
        """2.0 * (salary out - salary in) / median salary for a rebuild team trading player out for player got; 0.0 for
        any other mode, without salaries, or when either player has no salary."""
        if self.modes.get(tid) != 'rebuild' or not self.median:
            return 0.0
        paid, owed = self.salaries.get(out), self.salaries.get(got)
        if type(paid) not in (int, float) or type(owed) not in (int, float):
            return 0.0
        return 2.0 * (paid - owed) / self.median


def _slots(w, players, val):
    """{pos: _Slot} for each hitter position of a window: the bench (active hitters there not in the lineups, the ids at
    25 on), the starter (the best of the active hitters there in the lineups by val, ties to the lower id) and the need
    (the starter's val, else the best bench val, else 0.0). val maps a player id to the team's own value for him."""
    lineup = set(w[ACTIVE:])
    active = _active(w, players)
    out = {}
    for pos in HITTER_POS:
        here = [pid for pid in active if players[pid]['pos'] == pos]
        starters = [pid for pid in here if pid in lineup]
        starter = min(starters, key=lambda pid: (-val(pid), pid)) if starters else None
        if starter is not None:
            need = val(starter)
        else:
            need = max((val(pid) for pid in here), default=0.0)
        out[pos] = _Slot([pid for pid in here if pid not in lineup], starter, need)
    return out


def _rotation(w, players):
    """The known pitchers in a window's rotation slots, in order."""
    return [v for v in w[ROTATION[0]:ROTATION[1]] if v in players and players[v]['pos'] == 'P']


def _arms(w, players, val):
    """_Arms for a window: the spare pitchers (active pitchers not in the rotation, in window order), the rotation's
    lowest-valued pitcher by val (ties to the lower id; None without a rotation) and his val (0.0 without one)."""
    rotation = _rotation(w, players)
    spare = [pid for pid in _active(w, players) if players[pid]['pos'] == 'P' and pid not in rotation]
    low = min(rotation, key=lambda pid: (val(pid), pid)) if rotation else None
    return _Arms(spare, low, val(low) if low is not None else 0.0)


def _order(trade):
    """Sort key for the best trade first: the highest gain, then the smallest (a, b, a_gives, b_gives)."""
    return (-trade['gain'], trade['a'], trade['b'], trade['a_gives'], trade['b_gives'])


def _people(trade):
    """The player ids a trade touches: the two that move and the two starters it displaces."""
    return {trade['a_gives'], trade['b_gives'], trade['a_drops'], trade['b_drops']} - {None}


def _deal(a, b, ag, bg, x, y, ad, bd, view, need_a, need_b):
    """The trade of ag (a, at x) for bg (b, at y) as a dict, None unless both sides gain and the two players' values
    stay within BALANCE of the larger. Each side's gain is what it puts on the player it gets (its mode, its eyes),
    less its need (the value of the player he displaces, ad for a and bd for b), plus the salary term. The balance is
    on the true value() of the two, so that a trade between teams in different modes is not judged by either one's
    mode."""
    gain_a = view.see(a, bg) - need_a + view.salary_term(a, ag, bg)
    gain_b = view.see(b, ag) - need_b + view.salary_term(b, bg, ag)
    va, vb = view.worth(ag), view.worth(bg)
    if not (gain_a > 0 and gain_b > 0) or abs(va - vb) > BALANCE * max(va, vb):
        return None
    return {'a': a, 'b': b, 'a_gives': ag, 'b_gives': bg, 'a_pos': x, 'b_pos': y, 'b_drops': bd, 'a_drops': ad,
            'gain': round(gain_a + gain_b, 2)}


def _candidates(a, sa, b, sb, view):
    """The candidate hitter trades between teams a < b, from their slots: a bench hitter of a at one position (a_pos)
    and a bench hitter of b at another (b_pos), each worth more to the team getting him (in its mode and through its
    eyes, view) than the starter he would replace, and the two values within BALANCE of the larger."""
    out = []
    for x in HITTER_POS:
        for y in HITTER_POS:
            if x == y:
                continue
            for ag in sa[x].bench:
                for bg in sb[y].bench:
                    deal = _deal(a, b, ag, bg, x, y, sa[y].starter, sb[x].starter, view, sa[y].need, sb[x].need)
                    if deal:
                        out.append(deal)
    return out


def _pitcher_candidates(a, pa, b, pb, view):
    """The candidate pitcher trades between teams a < b, from their _Arms: a spare pitcher of a for a spare pitcher of
    b, each worth more to the team getting him than its lowest-valued rotation pitcher (a_drops, b_drops: the one he
    takes the rotation spot of), the two values within BALANCE. Teams without a rotation make none. a_pos and b_pos
    are 'P'."""
    if pa.low is None or pb.low is None:
        return []
    out = []
    for ag in pa.spare:
        for bg in pb.spare:
            deal = _deal(a, b, ag, bg, 'P', 'P', pa.low, pb.low, view, pa.need, pb.need)
            if deal:
                out.append(deal)
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


def _needs(windows, players, view):
    """{tid: (slots, arms)}: every team's hitter slots and pitcher _Arms, valued with the team's own eyes."""
    return {tid: (_slots(w, players, view.mine(tid)), _arms(w, players, view.mine(tid))) for tid, w in windows.items()}


def _pair_candidates(a, b, needs, view):
    """Every hitter and pitcher candidate between teams a < b, from their needs."""
    (sa, pa), (sb, pb) = needs[a], needs[b]
    return _candidates(a, sa, b, sb, view) + _pitcher_candidates(a, pa, b, pb, view)


def plan(windows, players, year, human=frozenset(), stem=None, salaries=None):
    """{'trades': [...], 'proposals': [...]} for one preseason, from the windows (never changed). Trades: the best
    computer-computer swaps (bench hitters at different positions, or spare pitchers), at most MAX_TRADES, one per
    team. Proposals: for each human team in order, up to MAX_PROPOSALS swaps with a computer team, on the windows after
    those trades, never using a player of a chosen trade or of an earlier proposal of that team. A trade is a dict with
    a the lower team id.
    Each team values players in its offseason mode (mode_value) and, when stem is given, sees them through
    fog.view (another team's player noised for that viewer, its own at half the noise); stem None sees every player
    as he is. A pitcher swap puts each arriving pitcher in the rotation spot of the team's lowest-valued rotation
    pitcher, who stays on the roster. salaries ({pid: dollars} or None): a rebuild side's gain also gets
    2.0 * (salary out - salary in) / median salary; other modes ignore it, and so does a missing salary."""
    view = _View(players, year, stem, offseason_modes(windows, players, year), salaries)
    pairs = [(a, b) for a, b in itertools.combinations(sorted(windows), 2) if a not in human and b not in human]
    needs = _needs(windows, players, view)
    cands = [t for a, b in pairs for t in _pair_candidates(a, b, needs, view)]
    trades = _pick(cands, MAX_TRADES)

    done = {tid: list(w) for tid, w in windows.items()}
    for t in trades:
        done[t['a']], done[t['b']] = _swapped(done, t)
    needs = _needs(done, players, view)
    taken = set()
    for t in trades:
        taken |= _people(t)

    proposals = []
    for h in sorted(tid for tid in done if tid in human):
        cands = []
        for tid in sorted(done):
            if tid == h or tid in human:
                continue
            cands += _pair_candidates(min(h, tid), max(h, tid), needs, view)
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


def _rotate(w, pid, drop):
    """w (changed in place) with pid, who has just taken a traded pitcher's slots, also in drop's rotation spot. A
    bullpen slot pid inherited goes to drop (when drop is not in the bullpen already, else it is emptied and the rest
    shift left), so nobody is listed twice. drop keeps the active slot and any bullpen slot he had."""
    lo, hi = ROTATION
    w[lo:hi] = [pid if v == drop else v for v in w[lo:hi]]
    lo, hi = BULLPEN
    pen = w[lo:hi]
    if pid in pen:
        if drop in pen:
            pen = [v for v in pen if v != pid]
            pen += [0] * (hi - lo - len(pen))
        else:
            pen = [drop if v == pid else v for v in pen]
        w[lo:hi] = pen
    return w


def _swapped(windows, trade):
    """(a's window, b's window) after the trade, as new lists. SwapError when the trade does not fit the windows (the
    rules apply_trade lists). A trade whose a_pos and b_pos are both 'P' swaps two pitchers who are not in their
    rotations: each takes the other's active slots and the rotation spot of the pitcher the trade names in a_drops
    (b_drops for b), who stays (see _rotate)."""
    a, b = trade['a'], trade['b']
    if a not in windows or b not in windows:
        raise SwapError('a team has no live r record')
    wa, wb = windows[a], windows[b]
    ag, bg, ad, bd = trade['a_gives'], trade['b_gives'], trade['a_drops'], trade['b_drops']
    pitchers = trade.get('a_pos') == trade.get('b_pos') == 'P'
    if ag not in wa[:ACTIVE]:
        raise SwapError('%d is not on the active roster of team %d' % (ag, a))
    if bg not in wb[:ACTIVE]:
        raise SwapError('%d is not on the active roster of team %d' % (bg, b))
    if bg in wa:
        raise SwapError('%d is already on team %d' % (bg, a))
    if ag in wb:
        raise SwapError('%d is already on team %d' % (ag, b))
    if pitchers:
        for tid, w, give, drop in ((a, wa, ag, ad), (b, wb, bg, bd)):
            if drop is None or drop not in w[ROTATION[0]:ROTATION[1]]:
                raise SwapError('%s is not in the rotation of team %d' % (drop, tid))
            if give in w[ROTATION[0]:ROTATION[1]]:
                raise SwapError('%d is in the rotation of team %d' % (give, tid))
    else:
        if bd is not None and bd not in wb[ACTIVE:]:
            raise SwapError('%d is not in the lineups of team %d' % (bd, b))
        if ad is not None and ad not in wa[ACTIVE:]:
            raise SwapError('%d is not in the lineups of team %d' % (ad, a))
    for tid, w in windows.items():
        if tid not in (a, b) and (ag in w or bg in w):
            raise SwapError('a traded player is on team %d' % tid)
    new_a = [bg if v == ag else v for v in wa]
    new_b = [ag if v == bg else v for v in wb]
    if pitchers:
        return _rotate(new_a, bg, ad), _rotate(new_b, ag, bd)
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


# the July deadline: a contender buys a rebuilding team's veteran for a prospect

def deadline_window(assoc):
    """True when the league's mean fraction of scheduled games played is in DEADLINE_LO..DEADLINE_HI (0.55 to 0.65, both
    ends in). assoc['games'] lists {'away', 'home', 'played'}; a team's fraction is its played games over its scheduled
    ones. Games that name no team count by their own share played; a league with no scheduled game is not in the
    window."""
    counts, loose = {}, [0, 0]
    for g in assoc.get('games', ()):
        teams = {g.get('away'), g.get('home')} - {None}
        for tid in teams:
            row = counts.setdefault(tid, [0, 0])
            row[0] += 1
            row[1] += bool(g.get('played'))
        if not teams:
            loose[0] += 1
            loose[1] += bool(g.get('played'))
    shares = [played / scheduled for scheduled, played in counts.values()]
    if not shares and loose[0]:
        shares = [loose[1] / loose[0]]
    if not shares:
        return False
    mean = sum(shares) / len(shares)
    return DEADLINE_LO - 1e-9 <= mean <= DEADLINE_HI + 1e-9


def _prospects(w, players, year):
    """The ids of a window aged PROSPECT_AGE or less, on the active roster or the reserve list, who are in none of the
    batting orders, alignments or rotation slots (window order: active, then reserves)."""
    busy = set(w[ORDERS[0]:ROTATION[1]])
    ids = _active(w, players) + [w[i] for i in _RESERVE if w[i] in players]
    out = []
    for pid in ids:
        age = _age(players[pid], year)
        if pid not in busy and pid not in out and age is not None and age <= PROSPECT_AGE:
            out.append(pid)
    return out


def _veterans(w, players, year):
    """The active ids of a window aged VET_AGE or more."""
    return [pid for pid in _active(w, players) if (_age(players[pid], year) or 0) >= VET_AGE]


def _incumbent(w, players, pos, val):
    """The val of the player a newcomer at pos must beat to start for a window's team: the alignment player at a
    hitter's position, the lowest-valued rotation pitcher for a pitcher. None when there is none to compare with (no
    known alignment player there, no rotation, a position with no alignment slot)."""
    if pos == 'P':
        rotation = _rotation(w, players)
        return min(val(pid) for pid in rotation) if rotation else None
    if pos not in ALIGN_POS:
        return None
    cur = w[ALIGNS[0] + ALIGN_POS.index(pos)]
    return val(cur) if cur in players else None


def _dorder(trade):
    """Sort key for the best deadline trade first: the highest gain, then the smallest (c, r, vet, prospect)."""
    return (-trade['gain'], trade['c'], trade['r'], trade['vet'], trade['prospect'])


def _deadline_candidates(c, r, windows, players, year, view):
    """The deadline trades between contender c and rebuilding team r: one of r's veterans (VET_AGE and up, active)
    who would start for c (worth more to c than its alignment player at his position, or than its lowest-valued
    rotation pitcher) for one of c's prospects of the same kind (PROSPECT_AGE and under, active or reserve, in no
    order, alignment or rotation slot). Each side must receive at least FAIR of what it gives, in its own mode and
    through its own eyes; gain is what the two sides receive less what they give."""
    wc, wr = windows[c], windows[r]
    mine = view.mine(c)
    prospects = _prospects(wc, players, year)
    out = []
    for vet in _veterans(wr, players, year):
        pos = players[vet]['pos']
        need = _incumbent(wc, players, pos, mine)
        got_c = view.see(c, vet)
        if need is None or got_c <= need:
            continue
        gave_r = view.see(r, vet, True)
        for pro in prospects:
            if (players[pro]['pos'] == 'P') != (pos == 'P'):
                continue
            gave_c, got_r = mine(pro), view.see(r, pro)
            if got_c < FAIR * gave_c or got_r < FAIR * gave_r:
                continue
            out.append({'c': c, 'r': r, 'vet': vet, 'prospect': pro, 'kind': 'deadline',
                        'gain': round((got_c - gave_c) + (got_r - gave_r), 2)})
    return out


def apply_deadline(windows, trade, players, year):
    """The windows after a deadline trade: roster.move of the veteran from r to c, then of the prospect from c to r (new
    windows; the input is never changed). SwapError when either move does not fit."""
    import roster       # roster imports this module, so it cannot be imported at the top
    after = roster.move(windows, trade['vet'], trade['r'], trade['c'], players, year)
    return roster.move(after, trade['prospect'], trade['c'], trade['r'], players, year)


def deadline_plan(windows, players, year, teams, human=frozenset(), stem=None):
    """{'trades': [...], 'proposals': [...]} for the deadline, from the windows (never changed) and the standings in
    teams (deadline_modes). Pairs of a contending team c and a rebuilding team r: r gives a veteran who would start
    for c, c gives a prospect of the same kind (_deadline_candidates). Trades: the best total gain first between
    computer teams, one per team, at most MAX_TRADES, each one that apply_deadline can make without a roster.problems
    the windows did not have. Proposals: for each human team in order, up to MAX_PROPOSALS such trades with a computer
    team of the other mode, on the windows after the trades, never using a player of a chosen trade or an earlier
    proposal of that team. A trade is {'c', 'r', 'vet', 'prospect', 'gain', 'kind': 'deadline'}. stem works as in
    plan. Veterans and prospects need a known age, so a year of None makes no trade."""
    import roster
    modes = {tid: m for tid, m in deadline_modes(teams).items() if tid in windows}
    view = _View(players, year, stem, modes)
    contend = [tid for tid in sorted(modes) if modes[tid] == 'contend']
    rebuild = [tid for tid in sorted(modes) if modes[tid] == 'rebuild']
    known = set(roster.problems(windows, players))

    def fits(ws, trade):
        """The windows after the trade, None when it does not apply or leaves a problem the windows did not have."""
        try:
            after = apply_deadline(ws, trade, players, year)
        except SwapError:
            return None
        return after if known.issuperset(roster.problems(after, players)) else None

    cands = [t for c in contend for r in rebuild if c not in human and r not in human
             for t in _deadline_candidates(c, r, windows, players, year, view)]
    done, trades, busy = windows, [], set()
    for t in sorted(cands, key=_dorder):
        if len(trades) == MAX_TRADES:
            break
        if t['c'] in busy or t['r'] in busy:
            continue
        after = fits(done, t)
        if after is not None:
            done, busy = after, busy | {t['c'], t['r']}
            trades.append(t)

    taken = {p for t in trades for p in (t['vet'], t['prospect'])}
    proposals = []
    for h in sorted(tid for tid in modes if tid in human):
        pairs = [(h, r) for r in rebuild if r not in human] if modes[h] == 'contend' else \
            [(c, h) for c in contend if c not in human] if modes[h] == 'rebuild' else []
        used, mine = set(taken), []
        for t in sorted((t for c, r in pairs for t in _deadline_candidates(c, r, done, players, year, view)),
                        key=_dorder):
            if len(mine) == MAX_PROPOSALS:
                break
            if {t['vet'], t['prospect']} & used or fits(done, t) is None:
                continue
            mine.append(t)
            used |= {t['vet'], t['prospect']}
        proposals += mine
    return {'trades': trades, 'proposals': proposals}
