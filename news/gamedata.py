"""Read what the game wrote for one association: team and schedule data (ASN), player names (PYR) and the per-game
box scores (Stats/<ASSN>.Hxx). Read-only; the codecs are work/league.py and work/hdecode.py.
"""
import datetime
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work'))
import ctree            # noqa: E402
import hdecode          # noqa: E402
import league           # noqa: E402
import stats            # noqa: E402

PYR_REC = 192
P_BORN = 0x1a           # u32 birth serial: the date is datetime.date.fromordinal(serial - 365)
P_BATS = 0x41           # 1 L, 2 R, 3 S (BATS)
P_THROWS = 0x42         # 1 L, 2 R (THROWS)
P_POS = 0x44            # 1..9: the position in POSITIONS
P_CUR = 0x5d            # the current ratings block, bytes 0..99
P_STRIKEOUT = 0x76
R_CONTACT, R_POWER, R_SPEED, R_STAMINA, R_CONTROL, R_FIELD = 0, 1, 2, 5, 6, 14   # offsets in the ratings block
POSITIONS = ('P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
BATS = {1: 'L', 2: 'R', 3: 'S'}
THROWS = {1: 'L', 2: 'R'}
SIDE = 0x8000           # ORed into the ids of one side's rows in a box score
MAX_TEAM = 34           # Lahman builds go to 34 teams (1884); stock files have 28


def cstr(b):
    return b.split(b'\0')[0].decode('latin-1').strip('*').strip()


def _records(pyr_path):
    """Each 192-byte record of a PYR file after its header, deciphered (cipher seed in the header's bytes 0-1)."""
    with open(pyr_path, 'rb') as fh:
        d = fh.read()
    if len(d) < PYR_REC or (len(d) - PYR_REC) % PYR_REC:
        raise ValueError('%s: not a PYR file' % pyr_path)
    t = league._forward((d[0], d[1]))
    inv = bytearray(256)
    for x, y in enumerate(t):
        inv[y] = x
    for i in range(PYR_REC, len(d), PYR_REC):
        yield bytes(inv[b] for b in d[i:i + PYR_REC])


def _pname(p):
    return (cstr(p[30:47]) + ' ' + cstr(p[47:64])).strip()


def names(pyr_path):
    """{player id: 'First Last'} from a PYR file (cipher seed in bytes 0-1, 192-byte records after a header)."""
    out = {}
    for p in _records(pyr_path):
        pid = p[0] | p[1] << 8
        name = _pname(p)
        if pid >= 100 and name:
            out[pid] = name
    return out


def _born(serial):
    """The birth year for a birth serial, or None when the serial is not a date."""
    try:
        return datetime.date.fromordinal(serial - 365).year
    except (ValueError, OverflowError):
        return None


def players(pyr_path):
    """{player id: {'name', 'pos', 'bats', 'throws', 'born', 'contact', 'power', 'speed', 'stamina', 'control',
    'strikeout', 'fielding'}} from a PYR file. 'born' is the birth year or None; 'fielding' is the rating at the
    player's own position or None."""
    out = {}
    for p in _records(pyr_path):
        pid = p[0] | p[1] << 8
        name = _pname(p)
        if pid < 100 or not name:
            continue
        pos = p[P_POS]
        known = 1 <= pos <= len(POSITIONS)
        out[pid] = {
            'name': name, 'pos': POSITIONS[pos - 1] if known else '', 'bats': BATS.get(p[P_BATS], ''),
            'throws': THROWS.get(p[P_THROWS], ''), 'born': _born(struct.unpack_from('<I', p, P_BORN)[0]),
            'contact': p[P_CUR + R_CONTACT], 'power': p[P_CUR + R_POWER], 'speed': p[P_CUR + R_SPEED],
            'stamina': p[P_CUR + R_STAMINA], 'control': p[P_CUR + R_CONTROL], 'strikeout': p[P_STRIKEOUT],
            'fielding': p[P_CUR + R_FIELD + pos - 1] if known else None,
        }
    return out


ENC = frozenset(('a', 'l', 'd', 't', 'r', 'xs'))     # enciphered ASN members; s, tr, df, po, sp are plain


def _members(data):
    """{member short name: [plain payload]} found by member name (numbers differ between files), cipher seed at
    file bytes 0x310-0x311."""
    t = league._forward((data[0x310], data[0x311]))
    inv = bytearray(256)
    for x, y in enumerate(t):
        inv[y] = x
    _, by_mem, members, *_ = ctree.parse(data)
    out = {}
    for m in members:
        if m['kind'] != 'data':
            continue
        name = m['name'].rsplit('.', 1)[0].lower()
        recs = []
        for r in by_mem.get(m['num'], []):
            raw = data[r.off:r.off + r.pl]
            if raw and raw[0] != 0xFF:
                recs.append((raw[0], bytes(inv[b] for b in raw) if name in ENC else raw))
        out[name] = recs
    return out


def association(asn_path):
    """Teams (with W-L), leagues, divisions and the regular-season schedule of one ASN file, as plain dicts."""
    with open(asn_path, 'rb') as fh:
        mem = _members(fh.read())
    leagues = {}
    for key, p in mem.get('l', []):
        if key != league.TEMPLATE_KEY:
            leagues[p[1]] = league._cstr(p, league.L_NAME[0], league.L_NAME[1] - 1)
    div_of = {}
    for key, p in mem.get('d', []):
        if key == league.TEMPLATE_KEY:
            continue
        for tid in p[20:30]:
            if 1 <= tid <= MAX_TEAM:
                div_of[tid] = (leagues.get(p[1], ''), league._cstr(p, league.D_NAME[0], league.D_NAME[1] - 1))
    wl = {key: (p[1], p[2]) for key, p in mem.get('xs', []) if 1 <= key <= MAX_TEAM and len(p) >= 3}
    rosters = {key: league._roster_of(p) for key, p in mem.get('r', []) if 1 <= key <= MAX_TEAM}
    teams = {}
    for key, p in mem.get('t', []):
        if not 1 <= key <= MAX_TEAM:
            continue
        lg, dv = div_of.get(key, ('', ''))
        w, l = wl.get(key, (0, 0))
        teams[key] = {'tid': key, 'name': league._cstr(p, 0x12, league.NAME_FIELD - 1),
                      'abbrev': league._cstr(p, *league.T_ABBREV), 'city': league._cstr(p, *league.T_CITY8),
                      'stadium': league._cstr(p, *league.T_STADIUM), 'manager': league._cstr(p, *league.T_MANAGER),
                      'league': lg, 'division': dv, 'w': w, 'l': l, 'roster': rosters.get(key, [])}
    games = []
    for _, p in mem.get('s', []):
        if len(p) >= 17 and p[6] in teams and p[10] in teams and p[15] == 0:
            g = league._game_json(p)
            games.append({'month': g['month'], 'day': g['day'], 'slot': g['slot'], 'away': g['away'],
                          'home': g['home'], 'away_runs': g['ar'], 'home_runs': g['hr'], 'played': g['played'],
                          'innings': g['innings']})
    name, season_year = '', None
    for key, p in mem.get('a', []):
        if key != league.TEMPLATE_KEY and len(p) >= league.ASN_TROPHY:
            name = league._cstr(p, league.ASN_NAME, league.ASN_STR - 1)
            # The season date: a birth-style serial, read by _born. A career league keeps its name, not its year.
            season_year = _born(struct.unpack_from('<I', p, 14)[0])
            break
    return {'name': name, 'season_year': season_year, 'teams': teams, 'games': games}


BAT_KEYS = ('ab', 'h', '2b', '3b', 'hr', 'rbi', 'bb', 'so', 'r', 'sb')
PIT_KEYS = ('outs', 'h', 'r', 'er', 'bb', 'so', 'hr', 'w', 'l', 'sv')


def _bat(c):
    return dict(zip(BAT_KEYS, (c[0], c[1] + c[2] + c[3] + c[4], c[2], c[3], c[4], c[5], c[6], c[7], c[13], c[14])))


def _pit(c):
    return dict(zip(PIT_KEYS, (c[18], c[1] + c[2] + c[3] + c[4], c[13], c[26], c[6], c[7], c[4], c[20], c[21],
                               c[22])))


def boxscore(h_path):
    """One game: {'away': {...}, 'home': {...}}. Rows with 0x8000 set are the home side (every stock box score
    matches its schedule game only that way). Each side has 'tid' (from its team-total batting row), 'runs', 'hits',
    and 'batting' / 'pitching' lists of per-player lines in file order."""
    with open(h_path, 'rb') as fh:
        data = fh.read()
    sides = {s: {'tid': None, 'batting': [], 'pitching': []} for s in ('away', 'home')}
    for rec, body, count in hdecode.tables(data):
        if rec not in (40, 70):
            continue
        for u in hdecode.rows(data, body, rec, count, rec // 2):
            side, pid, c = 'home' if u[2] & SIDE else 'away', u[2] & 0x7FFF, u[3:]
            if pid < 100:
                if rec == 40 and 1 <= pid <= MAX_TEAM:
                    sides[side]['tid'] = pid
                continue
            line = _bat(c) if rec == 40 else _pit(c)
            if not any(line.values()) and not (rec == 70 and c[19]):
                continue
            line['pid'] = pid
            sides[side]['batting' if rec == 40 else 'pitching'].append(line)
    for sd in sides.values():
        sd['runs'] = sum(x['r'] for x in sd['batting'])
        sd['hits'] = sum(x['h'] for x in sd['batting'])
    return sides


def match_game(assoc, box):
    """The played schedule games (from association()) this box score can be: same away and home team, same final
    score. Several only when one matchup repeated a score; the caller picks by order."""
    a, h = box['away'], box['home']
    return [g for g in assoc['games'] if g['played'] and (g['away'], g['home']) == (a['tid'], h['tid'])
            and (g['away_runs'], g['home_runs']) == (a['runs'], h['runs'])]


def season_lines(dat_path, scope=1):
    """One season's lines from a Stats DAT file: {'bat': {id: {...}}, 'pit': {id: {...}}} with stats.BAT / stats.PIT
    field names plus 'h'. scope 1 is this season, 3 last season. Ids >= 100 are players, < 100 teams. Members found
    by name (bt.dat, pt.dat)."""
    with open(dat_path, 'rb') as fh:
        d = fh.read()
    _, by_mem, members, *_ = ctree.parse(d)
    out = {'bat': {}, 'pit': {}}
    for kind, member, fields, size in (('bat', 'bt.dat', stats.BAT, 40), ('pit', 'pt.dat', stats.PIT, 70)):
        num = next((m['num'] for m in members if m['name'].lower() == member), None)
        for r in by_mem.get(num, []):
            p = d[r.off:r.off + r.pl]
            if len(p) != size or p[0] == 0xFF:
                continue
            u = _u16s(p)
            if u[0] == scope and u[1] == 2:
                line = dict(zip(fields, u[3:]))
                line['h'] = line['h1b'] + line['h2b'] + line['h3b'] + line['hr']
                out[kind][u[2]] = line
    return out


def find(directory, filename):
    """The path of filename in directory, matched without case (the game writes mlbpa97.DAT and MLBPA97.H80), or
    None."""
    want = filename.lower()
    for f in os.listdir(directory):
        if f.lower() == want:
            return os.path.join(directory, f)
    return None


def free_agents(pyf_path):
    """{player id} of the free agents in a PYF file: 'PPD:' at 0, a u32 at 4, an i16 count at 8, then count u16 ids at
    10. Raises ValueError when the file is not one of these (a short or partly written file included)."""
    with open(pyf_path, 'rb') as fh:
        b = fh.read()
    n = struct.unpack_from('<h', b, 8)[0] if len(b) >= 10 else -1
    if b[:4] != b'PPD:' or n < 0 or len(b) < 10 + 2 * n:
        raise ValueError('%s: not a PYF file' % pyf_path)
    return set(struct.unpack_from('<%dH' % n, b, 10))


def box_files(stats_dir, assn):
    """Paths of this association's box scores, Stats/<ASSN>.Hxx, sorted by modification time then name."""
    pat = re.compile(re.escape(assn) + r'\.H[0-9A-Z]{2}$', re.I)
    out = [os.path.join(stats_dir, f) for f in os.listdir(stats_dir) if pat.match(f)]
    return sorted(out, key=lambda p: (os.path.getmtime(p), os.path.basename(p).upper()))


def _u16s(b):
    return struct.unpack('<%dH' % (len(b) // 2), b)
