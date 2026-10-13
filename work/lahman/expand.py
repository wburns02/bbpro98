#!/usr/bin/env python3
"""Add teams, or a league, to a career association at the season boundary (preseason, no games played).

    python3 work/lahman/expand.py --install DIR --assn STEM --templates DIR \
        --add "NL:Eastern:Phoenix:Dogs:PHO[:Manager Name]" [--add ...] [--new-league NAME] --out-stem NEWSTEM

The source association STEM is only read. NEWSTEM is written beside it: Assn/NEWSTEM.ASN/.PYR/.PYF (+ .apc/.eos/.pyc
when STEM has them) and Stats/NEWSTEM.DAT. The target shape is the source's league and division sizes plus the added
teams and must equal a shape in structure.SHAPES whose structure template is minted in --templates. Each existing team
keeps its league and division and takes the template's slot for it, so the schedule (the game's own, from the
template) applies unchanged. New teams are filled by an expansion draft from the existing rosters (each team protects
its PROTECT best by value), then topped up from the free-agent pool. Players keep their ids, so the PYR and every player's
stat line are carried as they are; team ids in the stats file follow the team slots. What is not carried, and why, is in
docs/lanes/bbexpand.md.
"""
import argparse
import os
import shutil
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctree                                             # noqa: E402
import stats as ST                                       # noqa: E402
from lahman import build as B, ratings as RT, structure  # noqa: E402
from lahman.asnfile import AsnFile, cstr, put_str        # noqa: E402

PROTECT = 15                    # best-valued players each existing team keeps out of the draft (of 25 active + reserve)
PICKS = 30                      # draft picks per new team: the 25-man active roster and five reserves
ACTIVE, RESERVE, MIN_PIT, MIN_HIT = B.ACTIVE, B.RESERVE, B.MIN_PIT, B.MIN_HIT
PID0 = 100                      # player id = 100 + index in the PYR (build.py: nid = 100 + len(new_recs))
SIDE_EXT = ('apc', 'eos', 'pyc')    # per-association files carried over (champions, awards, old free-agent list)
NAME_FIELD = 16                 # team name characters: the record has 32 bytes, but the game saves 16 and a NUL
                                # (an 18X1927 season cut 'Phoenix Desert Dogs' to 'Phoenix Desert D'; stock names
                                # abbreviate to fit, 'Phila. Athletics', 'St.L. Cardinals')
MANAGER_FIELD = 16              # manager name characters the field holds before its NUL (17 bytes at 0x34)


# Fictional managers for new teams. Invented: not the name of any real major league manager or player.
MANAGERS = (
    'Cal Bramwell', 'Dutch Halvorsen', 'Roy Petraglia', 'Hank Delmonico', 'Skeeter Vaughn',
    'Walt Ferringer', 'Bo Callahan', 'Clyde Osterman', 'Duke Malvich', 'Ernie Kowalski',
    'Cecil Brantley', 'Rex Lombardo', 'Gene Sackett', 'Vic Tramonte', 'Otis Greengrass',
    'Lou Palmieri', 'Curly Fontaine', 'Hobie Garrett', 'Zeke Zabriski', 'Gus Abernathy',
    'Dizzy Kelleher', 'Skinny Prado', 'Ace Margulies', 'Tex Callender', 'Leo Danforth',
    'Pepper Nystrom', 'Red Balicki', 'Sully Marchetti', 'Biff Kontos', 'Tug Marquardt',
    'Lonnie Fisk', 'Junior Vasko', 'Slim Hargrove', 'Barney Fike', 'Chick Moreau',
    'Roxy Lindqvist', 'Grif Pelkey', 'Cy Swarthout', 'Moxie Carlucci', 'Deke Skowron',
)


class ExpandError(ValueError):
    pass


def pick_manager(abbrev, taken):
    """A manager name for a new team: MANAGERS walked from a CRC of the abbreviation, past every lowercased name in
    taken. When all are taken, 'Manager ' + abbrev."""
    for i in range(len(MANAGERS)):
        name = MANAGERS[(zlib.crc32(abbrev.encode()) + i) % len(MANAGERS)]
        if name.lower() not in taken:
            return name
    return 'Manager ' + abbrev


def set_manager(p, name):
    """The whole 17-byte manager field at 0x34 is cleared and filled, so no stale tail of the template's manager stays."""
    p[0x34:0x45] = name.encode('latin-1').ljust(17, b'\0')


def _find(directory, name):
    """The path of name in directory, matched without case (the game writes mlbpa97.DAT beside MLBPA97.ASN)."""
    for f in os.listdir(directory):
        if f.lower() == name.lower():
            return os.path.join(directory, f)
    return None


# ---------------------------------------------------------------- free-agent list (.PYF)

def read_pool(data):
    """(free-agent ids, stale tail) of an .PYF: 'PPD:', u32 length of (s16 count + ids), then the list. The bytes after
    the list are stale in the game's files and are kept as they are."""
    if data[:4] != b'PPD:' or len(data) < 10:
        raise ExpandError('PYF: no PPD: header')
    length, count = struct.unpack_from('<Ih', data, 4)
    if length != 2 + 2 * count or 8 + length > len(data):
        raise ExpandError('PYF: list length %d does not hold %d ids' % (length, count))
    return list(struct.unpack_from('<%dH' % count, data, 10)), data[8 + length:]


def write_pool(ids, tail):
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids) + tail


# ---------------------------------------------------------------- source structure

def structure_of(asn):
    """Leagues and divisions of an association: [{'idx', 'name', 'abbrev', 'layered', 'dh', 'divs': [{'idx', 'name',
    'teams': [team keys in list order]}]}] in league order."""
    divs = {}
    for _, p in asn.recs['d']:
        divs[(p[1], p[2])] = {'idx': p[2], 'name': cstr(p, 3, 17),
                              'teams': [x for x in p[0x14:0x1e] if x]}
    out = []
    for _, p in sorted(asn.recs['l'], key=lambda r: r[1][1]):
        dv = sorted((d for (li, _), d in divs.items() if li == p[1]), key=lambda d: d['idx'])
        out.append({'idx': p[1], 'name': cstr(p, 4, 33), 'abbrev': cstr(p, 0x25, 3), 'layered': p[2], 'dh': p[3],
                    'divs': dv})
    return out


def roster_of(rp, n_players):
    """(active ids, reserve ids) of one r record: the 25 active slots and the (id, level) reserve pairs."""
    ids = struct.unpack_from('<126H', rp, 42)
    ok = lambda v: PID0 <= v < PID0 + n_players
    return [v for v in ids[:ACTIVE] if ok(v)], [ids[i] for i in range(ACTIVE, ACTIVE + 2 * RESERVE, 2) if ok(ids[i])]


# ---------------------------------------------------------------- new teams and the target shape

def parse_add(spec):
    """'LEAGUE:DIVISION:City:Name:ABR[:Manager Name]' -> dict. The team name is 'City Name' (16 characters at most),
    an optional sixth part names the manager (16 characters at most)."""
    parts = [x.strip() for x in spec.split(':')]
    if len(parts) not in (5, 6) or not all(parts):
        raise ExpandError('--add %r: want LEAGUE:DIVISION:City:Name:ABR[:Manager Name]' % spec)
    lg, div, city, name, abbrev, manager = (parts + [None])[:6]
    full = '%s %s' % (city, name)
    if len(full) > NAME_FIELD:
        raise ExpandError('--add %r: the team name %r is longer than %d characters' % (spec, full, NAME_FIELD))
    if len(abbrev) > 3 or not abbrev.isalnum():
        raise ExpandError('--add %r: the abbreviation is up to 3 letters or digits' % spec)
    if manager is not None:
        if len(manager) > MANAGER_FIELD:
            raise ExpandError('--add %r: the manager name %r is longer than %d characters'
                              % (spec, manager, MANAGER_FIELD))
        try:
            manager.encode('latin-1')
        except UnicodeEncodeError:
            raise ExpandError('--add %r: the manager name %r does not encode as latin-1' % (spec, manager))
    return {'league': lg, 'division': div, 'name': full, 'abbrev': abbrev.upper(), 'manager': manager, 'spec': spec}


def target_leagues(src, adds, new_league):
    """The leagues and divisions after the adds: copies of structure_of() with each added team listed in its division's
    'adds'. A new league comes last; its divisions are the ones the adds name, in order of first appearance."""
    leagues = [dict(lg, divs=[dict(d, adds=[]) for d in lg['divs']], new=False) for lg in src]
    new = None
    if new_league:
        if any(new_league.lower() in (lg['name'].lower(), lg['abbrev'].lower()) for lg in leagues):
            raise ExpandError('--new-league %r: a league of that name exists' % new_league)
        new = {'idx': len(leagues), 'name': new_league, 'abbrev': new_league[:2].upper(), 'layered': 1, 'dh': 0,
               'divs': [], 'new': True}
        leagues.append(new)
    for add in adds:
        hits = [x for x in leagues if add['league'].lower() in (x['name'].lower(), x['abbrev'].lower())]
        if len(hits) != 1:
            raise ExpandError('--add %r: no league %r in this association' % (add['spec'], add['league']))
        lg = hits[0]
        dv = add['division']
        if dv.isdigit() and lg['divs'] and 1 <= int(dv) <= len(lg['divs']):
            div = lg['divs'][int(dv) - 1]
        else:
            div = next((d for d in lg['divs'] if d['name'].lower() == dv.lower()), None)
            if div is None:
                div = {'idx': len(lg['divs']), 'name': dv, 'teams': [], 'adds': []}
                lg['divs'].append(div)
        div['adds'].append(add)
    return leagues


def assign_slots(leagues, slots):
    """Put every team in a template slot of its division. slots: [(league, division, key)] of the template in plan order.
    Existing teams keep their order inside the division and take its first slots; each new team takes the next free
    slot, in the order the adds were given. Returns ({old team: key}, [new team dicts with 'key']), and sets the
    divisions' 'keys' (the template's keys of the division, in slot order)."""
    by_div, keymap, new_teams = {}, {}, []
    for li, di, tk in slots:
        by_div.setdefault((li, di), []).append(tk)
    for li, lg in enumerate(leagues):
        for di, div in enumerate(lg['divs']):
            room = by_div[(li, di)]
            div['keys'] = room
            for old, tk in zip(div['teams'], room):
                keymap[old] = tk
            for add, tk in zip(div['adds'], room[len(div['teams']):]):
                add['key'] = tk
                new_teams.append(add)
    return keymap, new_teams


def shape_of(leagues):
    return [[len(d['teams']) + len(d['adds']) for d in lg['divs']] for lg in leagues]


def find_shape(shape, templates):
    """The template key whose structure.SHAPES entry equals shape and whose template is minted."""
    key = next((k for k, s in structure.SHAPES.items() if s == shape), None)
    if key is None:
        raise ExpandError('no shape %s in structure.SHAPES; mint a template of that shape (Create New Association) '
                          'and add it to structure.SHAPES' % shape)
    try:
        return key, B.load_template(key, templates)
    except SystemExit as e:
        raise ExpandError('shape %s (%s): %s' % (shape, key, e))


# ---------------------------------------------------------------- expansion draft

def expansion_draft(rosters, new_teams, value_of, is_pit, protect=PROTECT, picks=PICKS):
    """rosters: {team: [pid]} of the existing teams; new_teams: the new teams in pick order. Each existing team protects
    its `protect` best by value. The new teams pick in turns, `picks` each: the best unprotected player who can go
    without leaving his team short (it keeps ACTIVE players, MIN_PIT pitchers and MIN_HIT fielders), and while a new team
    still needs pitchers or hitters for the picks left, only those. Returns ({new team: [pid]}, {pid: team it came from}).
    A new team may come up short; seat() tops it up from the free agents."""
    owner, came = {}, {}
    for team, ids in rosters.items():
        keep = set(sorted(ids, key=lambda p: (-value_of(p), p))[:protect])
        for p in ids:
            if p not in keep:
                owner[p] = team
                came[p] = team
    size = {t: len(ids) for t, ids in rosters.items()}
    pit = {t: sum(1 for p in ids if is_pit(p)) for t, ids in rosters.items()}

    def can_go(p):
        t = came[p]
        if size[t] - 1 < ACTIVE:
            return False
        if is_pit(p):
            return pit[t] - 1 >= MIN_PIT
        return (size[t] - pit[t]) - 1 >= MIN_HIT

    got = {t: [] for t in new_teams}
    for _ in range(picks):
        for t in new_teams:
            mine = got[t]
            left = picks - len(mine)
            n_pit = sum(1 for p in mine if is_pit(p))
            need_p = max(0, MIN_PIT - n_pit)
            need_h = max(0, ACTIVE - MIN_PIT - (len(mine) - n_pit))
            cands = [p for p in owner if can_go(p)]
            if need_p >= left:
                cands = [p for p in cands if is_pit(p)]
            elif need_h >= left:
                cands = [p for p in cands if not is_pit(p)]
            if not cands:
                continue
            best = min(cands, key=lambda p: (-value_of(p), p))
            del owner[best]
            size[came[best]] -= 1
            if is_pit(best):
                pit[came[best]] -= 1
            mine.append(best)
    return got, {p: came[p] for ids in got.values() for p in ids}


def seat(ids, fs, pool, value_of, is_pit):
    """The roster ids as a legal roster: B.choose_roster's split with free agents signed from pool until there are
    ACTIVE active players, MIN_PIT of them pitchers and MIN_HIT fielders. Returns (active, reserve, signed, pool)."""
    ids, pool, signed = list(ids), list(pool), []
    while True:
        active, reserve, _ = B.choose_roster(ids, fs)
        pit = sum(1 for p in active if is_pit(p))
        short_p, short_h = pit < MIN_PIT, len(active) - pit < MIN_HIT
        if len(active) == ACTIVE and not short_p and not short_h:
            return active, reserve, signed, pool
        if short_p:
            cands = [p for p in pool if is_pit(p)]
        elif short_h:
            cands = [p for p in pool if not is_pit(p)]
        else:
            cands = list(pool)
        if not cands:
            raise ExpandError('not enough free agents: a roster of %d players has %d active (%d pitchers) and the pool '
                              'has none left of the kind it needs' % (len(ids), len(active), pit))
        best = max(cands, key=lambda p: (value_of(p), -p))
        pool.remove(best)
        ids.append(best)
        signed.append(best)


# ---------------------------------------------------------------- stats: team rows follow the team slots

def remap_stat_teams(dat, keymap):
    """Stats rows whose word2 is a team id (< 100, stats.stat_records) take the team's new slot. Player rows and every
    other byte stay as they are."""
    edits = []
    for off, (mem, words) in ST.stat_records(dat).items():
        tid = words[2]
        if tid < PID0 and tid in keymap and keymap[tid] != tid:
            row = bytearray(dat[off:off + 2 * len(words)])
            struct.pack_into('<H', row, 4, keymap[tid])
            edits.append({'op': 'rewrite', 'rec': off, 'data': bytes(row).hex()})
    return ctree.do_apply(dat, edits)


def remap_transactions(records, keymap):
    """Transaction records (tr.dat, plain) with both sides' team fields moved to the team's new slot. A side with no team
    (255) or a team outside keymap is left as it is."""
    out = []
    for p in records:
        q = bytearray(p)
        for base in (6, 13):                    # each side: pid (u16) at base, f, g, team at base + 6
            if q[base + 6] in keymap:
                q[base + 6] = keymap[q[base + 6]]
        out.append(bytes(q))
    return out


# ---------------------------------------------------------------- the expansion

def value_of_fn(recs):
    """Player value for protection and the draft: a pitcher's control, endurance, strikeout attribute and mean pitch
    rating; a hitter's contact, power, speed and fielding at his position (the current-rating block of the PYR)."""
    def value_of(pid):
        r = recs[pid - PID0]
        if r[68] == 1:
            pitches = [r[RT.CUR + i] for i in RT.PITCHES if r[RT.CUR + i]]
            mean = sum(pitches) / len(pitches) if pitches else 0
            return r[RT.CUR + RT.CO] + r[RT.CUR + RT.EN] + r[RT.K_ATTR] + mean
        return r[RT.CUR + RT.CH] + r[RT.CUR + RT.PH] + r[RT.CUR + RT.SP] + r[RT.CUR + RT.FLD0 + r[68] - 1]
    return value_of


def expand(install, assn, templates, adds, out_stem, new_league=None, name=None, log=print):
    """Write out_stem beside assn in install. Returns a summary dict; raises ExpandError with the reason on refusal."""
    if not (out_stem and len(out_stem) <= 8 and out_stem.isalnum()):
        raise ExpandError('--out-stem: up to 8 letters/digits')
    assn_dir, stats_dir = os.path.join(install, 'Assn'), os.path.join(install, 'Stats')
    src_asn = _find(assn_dir, assn + '.ASN')
    src_pyr = _find(assn_dir, assn + '.PYR')
    src_pyf = _find(assn_dir, assn + '.PYF')
    src_dat = _find(stats_dir, assn + '.DAT')
    if not all((src_asn, src_pyr, src_pyf, src_dat)):
        raise ExpandError('%s: needs Assn/%s.ASN, .PYR, .PYF and Stats/%s.DAT' % (assn, assn, assn))
    out = {ext: os.path.join(assn_dir, out_stem + '.' + ext) for ext in ('ASN', 'PYR', 'PYF')}
    out['DAT'] = os.path.join(stats_dir, out_stem + '.DAT')
    side = [(f, os.path.join(assn_dir, out_stem + '.' + ext)) for ext in SIDE_EXT
            for f in [_find(assn_dir, assn + '.' + ext)] if f]
    for path in list(out.values()) + [dst for _, dst in side]:
        if os.path.exists(path):
            raise ExpandError('%s exists; choose another --out-stem' % path)

    src = AsnFile(open(src_asn, 'rb').read())
    _, recs = RT.read_pyr(src_pyr)
    pool, pool_tail = read_pool(open(src_pyf, 'rb').read())
    src_team = {src.key('t', p): p for _, p in src.recs['t']}
    src_r = {src.key('r', p): p for _, p in src.recs['r']}
    n_src = len(src_team)
    if sorted(src_team) != list(range(1, n_src + 1)):
        raise ExpandError('%s: team keys are not 1..%d' % (assn, n_src))

    # ---- refuse a season already played
    played = sum(1 for _, p in src.recs['s']
                 if 1 <= p[6] <= n_src and 1 <= p[10] <= n_src and p[15] == 0 and p[14] == 0)
    standings = [src.key('xs', p) for _, p in src.recs['xs'] if p[1] or p[2]]
    if played or standings:
        raise ExpandError('%s: %d regular games played and %d teams with a record; expansion takes a preseason '
                          'association' % (assn, played, len(standings)))

    names = {cstr(p, 0x12, 32).lower() for p in src_team.values()}
    abbrevs = {cstr(p, 0x45, 3).lower() for p in src_team.values()}
    parsed = [parse_add(s) for s in adds]
    for add in parsed:
        for dup, have in ((add['name'].lower(), names), (add['abbrev'].lower(), abbrevs)):
            if dup in have:
                raise ExpandError('--add %r: %r is already a team name or abbreviation' % (add['spec'], dup))
            have.add(dup)
    taken = {cstr(p, 0x34, 17).lower() for p in src_team.values()}
    taken.update(a['manager'].lower() for a in parsed if a['manager'])

    # ---- target shape, its template, and the template slot of every team
    leagues = target_leagues(structure_of(src), parsed, new_league)
    shape = shape_of(leagues)
    key, files = find_shape(shape, templates)
    tasm = AsnFile(open(files['ASN'], 'rb').read())
    tmpl_l = {p[1]: p for _, p in tasm.recs['l']}
    tmpl_d = {(p[1], p[2]): (off, p) for off, p in tasm.recs['d']}
    layered = {li: p[2] for li, p in tmpl_l.items()}
    for li, lg in enumerate(leagues):
        if lg['new']:
            lg['dh'] = tmpl_l[li][3]            # the game's flag for this slot; AL-style leagues carry DH
    slots = B.template_slots(tasm, structure.SHAPES[key])
    league_of = {tk: li for li, _, tk in slots}
    keymap, new_teams = assign_slots(leagues, slots)
    if len(keymap) != n_src:
        raise ExpandError('%s: %d teams in the divisions but %d team records' % (assn, len(keymap), n_src))
    inv = {tk: old for old, tk in keymap.items()}

    # ---- players: protection, the expansion draft, free agents, legal rosters
    n_players = len(recs)
    rosters, rp_of = {}, {}
    for old in range(1, n_src + 1):
        rp_of[old] = bytes(src_r[old])
        act, res = roster_of(rp_of[old], n_players)
        rosters[old] = act + res
    fs = B.FillerSeason({PID0 + i: r for i, r in enumerate(recs)})
    value_of = value_of_fn(recs)
    is_pit = lambda pid: recs[pid - PID0][68] == 1
    drafted, came = expansion_draft(rosters, [a['key'] for a in new_teams], value_of, is_pit)
    lost = {}
    for pid, old in came.items():
        lost.setdefault(old, set()).add(pid)
    final, signed_n = {}, 0
    rebuilt = set()
    for old in range(1, n_src + 1):
        if old in lost:
            ids = [p for p in rosters[old] if p not in lost[old]]
            act, res, signed, pool = seat(ids, fs, pool, value_of, is_pit)
            final[old] = (act, res)
            signed_n += len(signed)
            rebuilt.add(old)
        else:
            final[old] = roster_of(rp_of[old], n_players)
    for add in new_teams:
        act, res, signed, pool = seat(drafted.get(add['key'], []), fs, pool, value_of, is_pit)
        final[add['key']] = (act, res)
        signed_n += len(signed)
        rebuilt.add(add['key'])

    # ---- the ASN: the template's container, schedule and slots, with the source's records in them
    edits = []

    def rw(name, off, orig, plain):
        """Rewrite one template record with plain bytes of the same length (the template's slot layout)."""
        if len(plain) != len(orig):
            raise ExpandError('%s record %d: %d bytes for a %d-byte slot' % (name, off, len(plain), len(orig)))
        edits.append({'op': 'rewrite', 'rec': off, 'data': tasm.enc(name, bytes(plain)).hex()})

    t_of = {tasm.key('t', p): (off, p) for off, p in tasm.recs['t']}
    r_of = {tasm.key('r', p): (off, p) for off, p in tasm.recs['r']}
    a_off, a_tmpl = tasm.recs['a'][0]
    a_new = bytearray(src.recs['a'][0][1])
    a_new[0] = a_tmpl[0]
    # a copied name puts two identical rows in the load list (sorted by name, clipped past ~19 characters); lead with
    # the stem so the new one can be told apart
    put_str(a_new, 0x12, 33, name or '%s %s' % (out_stem, cstr(a_new, 0x12, 33)))
    rw('a', a_off, a_tmpl, a_new)

    new_by_key = {a['key']: a for a in new_teams}
    for tk, (off, tp) in sorted(t_of.items()):
        if tk in inv:
            p = bytearray(src_team[inv[tk]])
            p[0] = tp[0]
        else:
            add = new_by_key[tk]
            p = bytearray(tp)
            put_str(p, 0x12, 32, add['name'])
            manager = add['manager'] or pick_manager(add['abbrev'], taken)
            taken.add(manager.lower())
            add['manager_set'] = manager
            set_manager(p, manager)
            p[0x45:0x48] = add['abbrev'].encode('latin-1').ljust(3, b'\0')
            p[0x0c] = 0                         # Computer
        rw('t', off, tp, p)

        if tk in inv and inv[tk] not in rebuilt:
            rp = bytearray(rp_of[inv[tk]])
            rp[0] = r_of[tk][1][0]
            rw('r', r_of[tk][0], r_of[tk][1], rp)
        else:
            # A changed or new team: its lineup, rotation and bullpen are rebuilt from the ratings (build.py's rule).
            act, res = final[inv.get(tk, tk)]
            order, align = B.lineup(act, fs, leagues[league_of[tk]]['dh'])
            rot, pen = B.staff(act, fs)
            rp = bytearray(rp_of[inv[tk]] if tk in inv else r_of[tk][1])
            rp[0] = r_of[tk][1][0]
            rw('r', r_of[tk][0], r_of[tk][1], B.r_record(bytes(rp), act, res, order, align, rot, pen))

    for li, lg in enumerate(leagues):
        for di, div in enumerate(lg['divs']):
            off, p = tmpl_d[(li, di)]
            q = bytearray(p)
            if layered[li]:
                put_str(q, 3, 17, div['name'])
            if len(div['keys']) > 10:
                raise ExpandError('division %s holds %d teams; a division record has 10 slots'
                                  % (div['name'], len(div['keys'])))
            q[0x14:0x1e] = bytes(div['keys'] + [0] * (10 - len(div['keys'])))
            rw('d', off, p, q)

    for loff, lp in tasm.recs['l']:
        li = lp[1]
        q = bytearray(lp)
        if layered[li]:
            put_str(q, 4, 33, leagues[li]['name'])
            put_str(q, 0x25, 3, leagues[li]['abbrev'])
        q[3] = leagues[li]['dh']
        rw('l', loff, lp, q)

    for off, _ in tasm.recs.get('tr', []):
        edits.append({'op': 'delete', 'rec': off})
    tr_mem = next(i for i, m in enumerate(ctree.parse(tasm.data)[2]) if m['name'].rsplit('.', 1)[0] == 'tr')
    moved = remap_transactions([p for _, p in src.recs.get('tr', [])], keymap)
    edits += [{'op': 'add', 'm': tr_mem, 'data': p.hex()} for p in moved]
    tr_n = len(moved)
    asn_bytes = ctree.do_apply(tasm.data, edits)

    # ---- stats, free agents, the rest of the files
    dat_out = remap_stat_teams(open(src_dat, 'rb').read(), keymap)
    with open(out['ASN'], 'wb') as fh:
        fh.write(asn_bytes)
    shutil.copyfile(src_pyr, out['PYR'])
    with open(out['PYF'], 'wb') as fh:
        fh.write(write_pool(pool, pool_tail))
    with open(out['DAT'], 'wb') as fh:
        fh.write(dat_out)
    for f, dst in side:
        shutil.copyfile(f, dst)

    # ---- summary
    teams = []
    for tk in sorted(t_of):
        new = tk in new_by_key
        act, res = final[tk] if new else final[inv[tk]]
        lg = leagues[league_of[tk]]
        div = next(d for d in lg['divs'] if tk in d['keys'])
        teams.append({'key': tk, 'abbrev': new_by_key[tk]['abbrev'] if new else cstr(src_team[inv[tk]], 0x45, 3),
                      'league': lg['name'], 'division': div['name'], 'active': len(act),
                      'pitchers': sum(1 for p in act if is_pit(p)), 'reserve': len(res), 'new': new,
                      'manager': new_by_key[tk].get('manager_set') if new else None,
                      'moved_out': 0 if new else len(lost.get(inv[tk], ()))})
    summary = {'template': key, 'shape': shape, 'teams': teams, 'drafted': len(came), 'signed': signed_n,
               'transactions': tr_n, 'side': [os.path.basename(dst) for _, dst in side],
               'dropped': sorted(m for m in ('po', 'df', 'sp') if list(src.recs.get(m, [])))}
    log('%s -> %s: template %s, shape %s, %d teams -> %d' % (assn, out_stem, key, shape, n_src, len(teams)))
    for t in teams:
        log('  %2d %-4s %-18s %-12s act %2d (P %2d) res %2d%s%s%s' % (
            t['key'], t['abbrev'], t['league'], t['division'], t['active'], t['pitchers'], t['reserve'],
            ' NEW' if t['new'] else '', ' out %d' % t['moved_out'] if t['moved_out'] else '',
            ' (manager %s)' % t['manager'] if t['manager'] else ''))
    log('players drafted %d, free agents signed %d, transactions carried %d, side files %s, dropped %s' % (
        len(came), signed_n, tr_n, summary['side'], summary['dropped'] or 'none'))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--install', required=True, help='game directory holding Assn/ and Stats/ (written to)')
    ap.add_argument('--assn', required=True, help='the source association stem, e.g. MLBPA97')
    ap.add_argument('--templates', default=B.TEMPLATES, help='directory of minted structure templates')
    ap.add_argument('--add', action='append', default=[], required=True,
                    help='LEAGUE:DIVISION:City:Name:ABR[:Manager Name], repeatable')
    ap.add_argument('--new-league', help='add the new teams as a new league of this name (their league is that name)')
    ap.add_argument('--out-stem', required=True, help='the new association stem, up to 8 letters/digits')
    ap.add_argument('--name', help='the new association name (default: the stem, then the source name)')
    a = ap.parse_args(argv)
    try:
        expand(a.install, a.assn, a.templates, a.add, a.out_stem, a.new_league, a.name)
    except ExpandError as e:
        print('refused: %s' % e, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
