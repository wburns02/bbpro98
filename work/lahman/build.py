#!/usr/bin/env python3
"""Build a playable FPS Baseball Pro '98 association for one MLB season from the Lahman database.

    python3 work/lahman/build.py --year 1927 --install /mnt/nvme/bbpro98/work_install

Writes <install>/Assn/<NAME>.ASN/.PYR/.PYF and <install>/Stats/<NAME>.DAT, NAME = <teams>L<year> (16L1927).

Starts from a structure template the game itself made (Create New Association, one per league shape, see
structure.SHAPES) and replaces its content: real teams, managers, parks and weather cities; rosters with lineups,
rotations and bullpens; players rated from that season's stats (ratings.py); career stats through the year before
and last season's line. Template slots no real team fills get filler teams from the template's own generated
players; real teams that do not fit, and roster overflow, go to the free-agent pool.

Game files (templates, the install's MLBPA96E.PYR and _DEFAULT.ASN) are read at build time and never copied into
the repository.
"""
import argparse
import datetime
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctree                                             # noqa: E402
from stats import BAT as STATS_BAT, PIT as STATS_PIT     # noqa: E402
from lahman import lahdb, structure, ratings as RT       # noqa: E402
from lahman.asnfile import AsnFile, put_str, cstr          # noqa: E402

DB = '/mnt/nvme/tlrb2/lahman/lahmansbaseballdb.sqlite'
TEMPLATES = '/mnt/nvme/bbpro98/lahman/templates'

# The game's weather cities (t record byte 4 = index + 1), in the game's order.
WEATHER = (
    'Albany, NY', 'Albuquerque, NM', 'Anchorage, AK', 'Asheville, NC', 'Atlanta, GA', 'Atlantic City, NJ',
    'Baltimore, MD', 'Birmingham, AL', 'Bismark, ND', 'Boise, ID', 'Boston, MA', 'Buffalo, NY', 'Burlington, VT',
    'Caribou, ME', 'Charleston, SC', 'Chicago, IL', 'Cincinnati, OH', 'Cleveland, OH', 'Columbus, OH', 'Dallas, TX',
    'Denver, CO', 'Des Moines, IA', 'Detroit, MI', 'Dodge City, KS', 'Duluth, MN', 'Eugene, OR', 'Fairbanks, AK',
    'Fresno, CA', 'Galveston, TX', 'Grand Rapids, MI', 'Hartford, CT', 'Helena, MT', 'Honolulu, HI', 'Houston, TX',
    'Huron, SD', 'Indianapolis, IN', 'Jackson, MS', 'Jacksonville, FL', 'Kansas City, MO', 'Knoxville, TN',
    'Lander, WY', 'Lexington, KY', 'Little Rock, AR', 'Los Angeles, CA', 'Louisville, KY', 'Marquette, MI',
    'Memphis, TN', 'Miami, FL', 'Milwaukee, WI', 'Minneapolis, MN', 'Mobile, AL', 'Moline, IL', 'Montreal, QC',
    'Nashville, TN', 'Newark, NJ', 'New Orleans, LA', 'New York, NY', 'Norfolk, VA', 'Oklahoma City, OK',
    'Omaha, NE', 'Philadelphia, PA', 'Phoenix, AZ', 'Pittsburgh, PA', 'Portland, ME', 'Portland, OR',
    'Providence, RI', 'Raleigh, NC', 'Rapid City, SD', 'Reno, NV', 'Richmond, VA', 'St. Louis, MO',
    'Salt Lake City, UT', 'San Antonio, TX', 'San Diego, CA', 'San Francisco, CA', 'Sault Ste. Marie, MI',
    'Savannah, GA', 'Seattle, WA', 'Spokane, WA', 'Springfield, MO', 'Syracuse, NY', 'Tampa, FL', 'Toronto, ON',
    'Washington, DC', 'Wilmington, DE')
# Lahman park cities that are not weather cities -> the nearest one.
CITY_ALIAS = {
    'Brooklyn, NY': 'New York, NY', 'Bronx, NY': 'New York, NY', 'Queens, NY': 'New York, NY',
    'Maspeth, NY': 'New York, NY', 'Ridgewood, NY': 'New York, NY', 'Staten Island, NY': 'New York, NY',
    'West New York, NJ': 'New York, NY', 'Hoboken, NJ': 'New York, NY', 'Weehawken, NJ': 'New York, NY',
    'Harrison, NJ': 'Newark, NJ', 'Elizabeth, NJ': 'Newark, NJ', 'Irvington, NJ': 'Newark, NJ',
    'Anaheim, CA': 'Los Angeles, CA', 'Oakland, CA': 'San Francisco, CA', 'San Jose, CA': 'San Francisco, CA',
    'Arlington, TX': 'Dallas, TX', 'Bloomington, MN': 'Minneapolis, MN', 'St. Paul, MN': 'Minneapolis, MN',
    'St. Petersburg, FL': 'Tampa, FL', 'Miami Gardens, FL': 'Miami, FL', 'Troy, NY': 'Albany, NY',
    'Rochester, NY': 'Buffalo, NY', 'Worcester, MA': 'Boston, MA', 'Middletown, CT': 'Hartford, CT',
    'New Haven, CT': 'Hartford, CT', 'Rockford, IL': 'Chicago, IL', 'Toledo, OH': 'Cleveland, OH',
    'Fort Wayne, IN': 'Indianapolis, IN', 'Keokuk, IA': 'Des Moines, IA', 'Altoona, PA': 'Pittsburgh, PA',
    'Covington, KY': 'Cincinnati, OH', 'Montreal, QC': 'Montreal, QC', 'San Juan, PR': 'Miami, FL',
    'Monterrey, NL': 'San Antonio, TX', 'Tokyo, Tokyo': 'Los Angeles, CA', 'Sydney, NSW': 'Los Angeles, CA',
    'London, England': 'New York, NY', 'Mexico City, DF': 'San Antonio, TX', 'Atlanta, GA': 'Atlanta, GA',
    'Kansas City, KS': 'Kansas City, MO', 'Washington, D.C.': 'Washington, DC', 'Cleveland, OH': 'Cleveland, OH',
    'Allegheny, PA': 'Pittsburgh, PA', 'Fort Bragg, NC': 'Raleigh, NC', 'Omaha, NE': 'Omaha, NE',
    'Williamsport, PA': 'Pittsburgh, PA', 'Cambridge, MA': 'Boston, MA', 'Dover, DE': 'Wilmington, DE',
}
# Lahman franchID -> stock team abbreviation (stadium file and colors) when the city has two stock teams.
FRANCH_STOCK = {
    'NYY': 'NYA', 'NYM': 'NYN', 'SFG': 'NYN', 'LAD': 'NYN', 'CHC': 'CHN', 'CHW': 'CHA', 'LAA': 'ANA', 'ANA': 'ANA',
    'OAK': 'OAK', 'BAL': 'STL', 'STL': 'STL', 'ATL': 'BOS', 'BOS': 'BOS', 'PHI': 'PHI',
}
LEAGUE_NAMES = {'NL': 'National League', 'AL': 'American League', 'AA': 'American Association',
                'UA': 'Union Association', 'PL': "Players' League", 'FL': 'Federal League',
                'NA': 'National Association'}
DIV_NAMES = {'E': 'East', 'C': 'Central', 'W': 'West'}
POS9 = ('C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')
SCARCE = ('C', 'SS', '2B', 'CF', '3B', 'RF', 'LF', '1B')
NONE = 0xFFFF
ACTIVE, RESERVE = 25, 15


# ---------------------------------------------------------------- Lahman extras (read-only SQL)

def home_parks(con, year):
    """teamID -> (park name, 'City, ST') of the park with the most home games that year."""
    out = {}
    rows = con.execute('''
        SELECT h.teamkey, p.parkname, p.city, p.state, h.games FROM homegames h JOIN parks p ON p.ID = h.park_ID
        WHERE h.yearkey = ? ORDER BY h.teamkey, h.games DESC''', (year,)).fetchall()
    for team, park, city, state, _ in rows:
        out.setdefault(team, (park or '', '%s, %s' % (city or '', state or '')))
    return out


def of_split(con, year=None, before=None):
    """playerID -> (G_lf, G_cf, G_rf) for one season or the career before a season."""
    where, arg = ('yearID = ?', year) if year is not None else ('yearID < ?', before)
    rows = con.execute('SELECT playerID, SUM(COALESCE(G_lf,0)), SUM(COALESCE(G_cf,0)), SUM(COALESCE(G_rf,0)) '
                       'FROM appearances WHERE %s GROUP BY playerID' % where, (arg,)).fetchall()
    return {pid: (lf, cf, rf) for pid, lf, cf, rf in rows}


CITY_SHORT = (
    ('Los Angeles', 'L.A.'), ('San Francisco', 'S.F.'), ('Philadelphia', 'Phila.'), ('St. Louis', 'St.L.'),
    ('Washington', 'Wash.'), ('Pittsburgh', 'Pitt.'), ('Cincinnati', 'Cin.'), ('Cleveland', 'Cle.'),
    ('Kansas City', 'K.C.'), ('Milwaukee', 'Mil.'), ('Baltimore', 'Balt.'), ('Brooklyn', 'Bkn.'),
    ('Chicago', 'Chi.'), ('New York', 'N.Y.'), ('Boston', 'Bos.'), ('Minnesota', 'Minn.'), ('California', 'Cal.'),
    ('Tampa Bay', 'T.B.'), ('San Diego', 'S.D.'), ('Montreal', 'Mtl.'), ('Toronto', 'Tor.'), ('Seattle', 'Sea.'),
    ('Houston', 'Hou.'), ('Detroit', 'Det.'), ('Colorado', 'Col.'), ('Arizona', 'Ariz.'), ('Florida', 'Fla.'),
    ('Atlanta', 'Atl.'), ('Oakland', 'Oak.'), ('Anaheim', 'Ana.'), ('Indianapolis', 'Ind.'), ('Louisville', 'Lou.'),
    ('Providence', 'Prov.'), ('Buffalo', 'Buf.'), ('Hartford', 'Hart.'), ('Worcester', 'Wor.'), ('Columbus', 'Col.'))
NAME_MAX = 16                                  # the team lists clip after 16 characters


def team_name(name):
    """The Lahman name, else with its city abbreviated, else the nickname, else cut: whichever fits first."""
    if len(name) <= NAME_MAX:
        return name
    for city, short in CITY_SHORT:
        if name.startswith(city + ' '):
            nick = name[len(city) + 1:].split(' of ')[0]
            for cand in (short + ' ' + nick, nick):
                if len(cand) <= NAME_MAX:
                    return cand
            return nick[:NAME_MAX]
    return name[:NAME_MAX]


def park_name(name):
    """Lahman numbers rebuilt parks ('Yankee Stadium I', 'Polo Grounds V'); the game shows the plain name."""
    head, _, tail = name.rpartition(' ')
    return head if head and tail and set(tail) <= set('IVX') else name


def weather_code(city):
    city = CITY_ALIAS.get(city, city)
    if city in WEATHER:
        return WEATHER.index(city) + 1
    state = city.rsplit(', ', 1)[-1]
    for i, w in enumerate(WEATHER):            # same state, first listed city
        if w.endswith(', ' + state):
            return i + 1
    return 0


# ---------------------------------------------------------------- template

def load_template(key):
    d = os.path.join(TEMPLATES, key)
    asn = glob.glob(os.path.join(d, '*.ASN'))
    if len(asn) != 1:
        raise SystemExit('template %s is not minted (%s)' % (key, d))
    base = asn[0][:-4]
    files = {ext: base + '.' + ext for ext in ('ASN', 'PYR', 'PYF', 'DAT')}
    for ext, path in files.items():
        if not os.path.exists(path):
            raise SystemExit('template %s: missing %s' % (key, path))
    return files


def template_slots(asn, shape):
    """[(league index, division index, t-record key)] in plan order, checked against the SHAPES entry."""
    leagues = sorted((p[1], off, p) for off, p in asn.recs['l'])
    divs = sorted((p[1], p[2], off, p) for off, p in asn.recs['d'])
    got = []
    for li, _, _ in leagues:
        got.append([len([x for x in p[0x14:0x1e] if x]) for l2, _, _, p in divs if l2 == li])
    if got != shape:
        raise SystemExit('template shape %s does not match %s' % (got, shape))
    slots = []
    for li, di, _, p in divs:
        slots += [(li, di, x) for x in p[0x14:0x1e] if x]
    return slots


# ---------------------------------------------------------------- rosters

def primary_owner(app):
    """playerID -> the teamID he played the most games for (ties: teamID order)."""
    return {pid: min(teams.items(), key=lambda kv: (-kv[1]['G_all'], kv[0]))[0] for pid, teams in app.items()}


def pa_of(b):
    return sum(b.get(k, 0) for k in ('AB', 'BB', 'HBP', 'SH', 'SF'))


def choose_roster(players, season):
    """Split one team's players into (active, reserve, overflow), pitchers by innings and hitters by plate
    appearances; at least two catchers when the team had two."""
    pit = sorted((p for p in players if season.primary(p) == 'P'),
                 key=lambda p: (-season.pit.get(p, {}).get('IPouts', 0), p))
    hit = sorted((p for p in players if season.primary(p) != 'P'),
                 key=lambda p: (-pa_of(season.bat.get(p, {})), p))
    n_pit = min(len(pit), 10 if len(hit) >= ACTIVE - 10 else ACTIVE - len(hit))
    active = pit[:n_pit] + hit[:ACTIVE - n_pit]
    catchers = [p for p in hit if season.games_at(p).get('C', 0) > 0]
    have = [p for p in active if p in catchers]
    for c in catchers:
        if len(have) >= min(2, len(catchers)):
            break
        if c not in active:
            drop = next((p for p in reversed(active) if p in hit and p not in catchers), None)
            if drop is None:
                break
            active[active.index(drop)] = c
            have.append(c)
    rest = [p for p in pit + hit if p not in active]
    rest.sort(key=lambda p: (-sum(row.get('G_all', 0) for row in season.app.get(p, {}).values()), p))
    return active, rest[:RESERVE], rest[RESERVE:]


def ops(b):
    ab = b.get('AB', 0)
    if not ab:
        return 0.0, 0.0, 0.0
    h = b.get('H', 0)
    tb = h + b.get('2B', 0) + 2 * b.get('3B', 0) + 3 * b.get('HR', 0)
    pa = max(1, pa_of(b))
    obp = (h + b.get('BB', 0) + b.get('HBP', 0)) / pa
    return obp + tb / ab, obp, h / ab


def lineup(active, season, dh):
    """(batting order of 9 ids with NONE for the pitcher's slot, alignment C 1B 2B 3B SS LF CF RF DH-or-0)."""
    hitters = [p for p in active if season.primary(p) != 'P']
    used, at = set(), {}
    any_split = any(sum(season.games_at(p).get(x, 0) for x in ('LF', 'CF', 'RF')) for p in hitters)

    def games(p, pos):
        g = season.games_at(p)
        if pos in ('LF', 'CF', 'RF') and not any_split:
            return sum(row.get('G_of', 0) for row in season.app.get(p, {}).values())
        return g.get(pos, 0)

    for pos in SCARCE:
        cand = [p for p in hitters if p not in used]
        if not cand:
            cand = [p for p in active if p not in used]
        best = max(cand, key=lambda p: (games(p, pos), pa_of(season.bat.get(p, {})), p))
        at[pos] = best
        used.add(best)
    dh_id = 0
    if dh:
        cand = [p for p in active if p not in used and season.primary(p) != 'P'] or \
               [p for p in active if p not in used]
        dh_id = max(cand, key=lambda p: (ops(season.bat.get(p, {}))[0], p)) if cand else 0
    starters = [at[p] for p in POS9] + ([dh_id] if dh_id else [])
    stat = {p: ops(season.bat.get(p, {})) for p in starters}
    order = []

    def take(key):
        p = max((q for q in starters if q not in order), key=lambda q: (key(q), q))
        order.append(p)

    take(lambda q: stat[q][0])                       # best hitter bats third
    take(lambda q: season.bat.get(q, {}).get('HR', 0))   # most power bats fourth
    take(lambda q: stat[q][1])                       # best on-base leads off
    take(lambda q: stat[q][2])                       # best average bats second
    order = [order[2], order[3], order[0], order[1]]
    while len(order) < len(starters):
        take(lambda q: stat[q][0])
    if not dh_id:
        order.append(NONE)
    return order, [at[p] for p in POS9] + [dh_id]


def staff(active, season):
    """(rotation of up to 5, bullpen of up to 6)."""
    pit = [p for p in active if season.primary(p) == 'P']
    gs = lambda p: season.pit.get(p, {}).get('GS', 0)
    starters = sorted((p for p in pit if gs(p) > 0), key=lambda p: (-gs(p), p))[:5]
    if not starters and pit:
        starters = pit[:1]
    pen = sorted((p for p in pit if p not in starters),
                 key=lambda p: (-season.pit.get(p, {}).get('SV', 0), -season.pit.get(p, {}).get('GF', 0),
                                -season.pit.get(p, {}).get('G', 0), p))[:6]
    return starters, pen


def r_record(old, active, reserve, order, align, rotation, pen):
    p = bytearray(old)
    ids = [0] * 126
    for i, x in enumerate(active[:ACTIVE]):
        ids[i] = x
    for i, x in enumerate(reserve[:RESERVE]):
        ids[25 + 2 * i], ids[26 + 2 * i] = x, 1
    ids[77:86] = order
    ids[86:95] = order
    ids[95:104] = align
    ids[104:113] = align
    ids[113:119] = (rotation + [0] * 6)[:6]
    ids[119] = 0
    ids[120:126] = (pen + [0] * 6)[:6]
    struct.pack_into('<126H', p, 0x2a, *ids)
    jersey = bytearray(40)
    for i in range(min(40, len(active) + len(reserve))):
        jersey[i] = i + 1
    p[2:42] = jersey
    return bytes(p)


# ---------------------------------------------------------------- filler teams (template-generated players)

class FillerSeason:
    """Duck-types the Season calls lineup/staff/choose_roster make, for generated players keyed by PYR record."""

    def __init__(self, recs):
        self.recs = recs
        self.bat, self.pit, self.app = {}, {}, {}
        for i, r in recs.items():
            self.pit[i] = {'IPouts': r[RT.CUR + RT.EN] * 10, 'GS': r[RT.CUR + RT.EN]} if r[68] == 1 else {}
            self.bat[i] = {'AB': 100 + r[RT.CUR + RT.CH], 'H': r[RT.CUR + RT.CH], 'HR': r[RT.CUR + RT.PH] // 10}
            self.app[i] = {'X': {'G_all': 1}}

    def primary(self, i):
        return RT_POS[self.recs[i][68]]

    def games_at(self, i):
        return {RT_POS[self.recs[i][68]]: 1}


RT_POS = {v: k for k, v in RT.POS_CODE.items()}


# ---------------------------------------------------------------- stats DAT

def clamp16(v):
    return max(0, min(0xFFFF, int(v or 0)))


def bat_words(b):
    h1 = b.get('H', 0) - b.get('2B', 0) - b.get('3B', 0) - b.get('HR', 0)
    v = dict(ab=b.get('AB'), h1b=h1, h2b=b.get('2B'), h3b=b.get('3B'), hr=b.get('HR'), rbi=b.get('RBI'),
             bb=b.get('BB'), so=b.get('SO'), ibb=b.get('IBB'), hbp=b.get('HBP'), sh=b.get('SH'), sf=b.get('SF'),
             g=b.get('G'), r=b.get('R'), sb=b.get('SB'), cs=b.get('CS'), gidp=b.get('GIDP'))
    return [clamp16(v[k]) for k in STATS_BAT]


def pit_words(q):
    bfp = q.get('BFP', 0)
    ab = bfp - q.get('BB', 0) - q.get('HBP', 0) if bfp else q.get('IPouts', 0) + q.get('H', 0)
    v = dict(ab=ab, h1b=q.get('H', 0) - q.get('HR', 0), h2b=0, h3b=0, hr=q.get('HR'), rbi=q.get('R'),
             bb=q.get('BB'), so=q.get('SO'), ibb=q.get('IBB'), hbp=q.get('HBP'), sh=0, sf=0, g=q.get('G'),
             r=q.get('R'), sb=0, cs=0, gidp=0, gf=q.get('GF'), outs=q.get('IPouts'), bfp=bfp, w=q.get('W'),
             l=q.get('L'), sv=q.get('SV'), cg=q.get('CG'), sho=q.get('SHO'), qs=0, er=q.get('ER'), ir=0, irs=0,
             hld=0, svop=0, wp=q.get('WP'))
    return [clamp16(v[k]) for k in STATS_PIT]


def fld_words(fpos, split):
    """75-3 words: 9 blocks (P C 1B 2B 3B SS LF CF RF) of outs, gs, g, po, a, e, dp, pb. Lahman's OF line is
    split over LF/CF/RF by the player's games there (split = (lf, cf, rf)); missing InnOuts become 24 per game."""
    blocks = {k: [0] * 8 for k in ('P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')}

    def add(pos, f, share):
        g = f.get('G', 0) * share
        outs = f.get('InnOuts', 0) * share if f.get('InnOuts') else 24 * g
        vals = (outs, 0, g, f.get('PO', 0) * share, f.get('A', 0) * share, f.get('E', 0) * share,
                f.get('DP', 0) * share, f.get('PB', 0) * share)
        blocks[pos] = [a + b for a, b in zip(blocks[pos], vals)]

    for pos, f in fpos.items():
        if pos in ('P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF'):
            add(pos, f, 1.0)
        elif pos == 'OF':
            tot = sum(split)
            for k, share in zip(('LF', 'CF', 'RF'), split if tot else (0, 1, 0)):
                if share:
                    add(k, f, share / tot if tot else 1.0)
    out = []
    for k in ('P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF'):
        out += [clamp16(round(x)) for x in blocks[k]]
    return out


def stat_edits(dat, lines):
    """ctree add edits: lines = [(table, scope, pid, words)] with table bt/pt/ft."""
    _, _, members, *_ = ctree.parse(dat)
    idx = {m['name'].rsplit('.', 1)[0]: i for i, m in enumerate(members) if m['kind'] == 'data'}
    out = []
    for table, scope, pid, words in lines:
        out.append({'op': 'add', 'm': idx[table],
                    'data': struct.pack('<%dH' % (3 + len(words)), scope, 2, pid, *words).hex()})
    return out


# ---------------------------------------------------------------- build

def shift_year(born_serial, years):
    d = RT.from_serial(born_serial)
    try:
        return RT.serial(d.replace(year=d.year + years))
    except ValueError:
        return RT.serial(d.replace(year=d.year + years, day=28))


def build(year, install, db=DB, name=None, log=print):
    con = lahdb.connect(db)
    teams = lahdb.teams(con, year)
    if not teams:
        raise SystemExit('no Lahman teams for %d' % year)
    plan = structure.plan(teams, year)
    key = plan['template']
    files = load_template(key)
    asn = AsnFile(open(files['ASN'], 'rb').read())
    slots = template_slots(asn, structure.SHAPES[key])
    flat = [t for lg in plan['leagues'] for div in lg['divisions'] for t in div]
    team_of_slot = dict(zip([s[2] for s in slots], flat))       # t key -> teamID or None
    by_id = {t['teamID']: t for t in teams}
    log('%d: template %s, cost %d, dropped %s' % (year, key, plan['cost'], plan['dropped']))

    # ---- players
    season = RT.Season(con, year)
    model = RT.Model.fit(os.path.join(install, 'Assn', 'MLBPA96E.PYR'), con)
    owner = primary_owner(season.app)
    rosters = {}
    for pid, tid in owner.items():
        rosters.setdefault(tid, []).append(pid)
    people = lahdb.people(con, list(owner))
    before = lahdb.seasons_before(con, year)
    hdr, tmpl_recs = RT.read_pyr(files['PYR'])
    tmpl_year = RT.from_serial(struct.unpack_from('<I', asn.recs['a'][0][1], 0x0a)[0]).year
    generated = [r for r in tmpl_recs if struct.unpack_from('<H', r, 0)[0] >= 721]

    new_recs, id_of = [], {}

    def add_real(pid):
        if pid in id_of:
            return id_of[pid]
        nid = 100 + len(new_recs)
        new_recs.append(model.rate(season, pid, people.get(pid, {}), nid, before.get(pid, 0)))
        id_of[pid] = nid
        return nid

    def add_generated(r):
        nid = 100 + len(new_recs)
        rec = bytearray(r)
        struct.pack_into('<H', rec, 0, nid)
        struct.pack_into('<I', rec, 26, shift_year(struct.unpack_from('<I', r, 26)[0], year - tmpl_year))
        new_recs.append(bytes(rec))
        return nid

    # ---- association record
    a_off, a_p = asn.recs['a'][0]
    a = bytearray(a_p)
    opening = RT.from_serial(struct.unpack_from('<I', a_p, 0x0e)[0])
    struct.pack_into('<I', a, 0x0a, RT.serial(datetime.date(year, 1, 1)))
    struct.pack_into('<I', a, 0x0e, RT.serial(opening.replace(year=year)))
    put_str(a, 0x12, 33, '%d Major League Baseball' % year)
    put_str(a, 0x33, 33, 'World Series' if year >= 1903 else 'Pennant')
    asn.rewrite('a', a_off, bytes(a))

    # ---- leagues and divisions
    for (off, p), lg in zip(sorted(asn.recs['l'], key=lambda r: r[1][1]), plan['leagues']):
        q = bytearray(p)
        lid = lg['lgID']
        put_str(q, 4, 33, LEAGUE_NAMES.get(lid, lid or 'Exhibition League'))
        put_str(q, 0x25, 3, (lid or 'EX')[:2])
        q[3] = 1 if lid == 'AL' and year >= 1973 else 0
        asn.rewrite('l', off, bytes(q))
    dh_of_league = {p[1]: (1 if lg['lgID'] == 'AL' and year >= 1973 else 0)
                    for (off, p), lg in zip(sorted(asn.recs['l'], key=lambda r: r[1][1]), plan['leagues'])}
    for off, p in asn.recs['d']:
        lg = plan['leagues'][[x[1][1] for x in sorted(asn.recs['l'], key=lambda r: r[1][1])].index(p[1])]
        members = [by_id[t] for t in lg['divisions'][p[2]] if t]
        divs = {t['divID'] for t in members if t['divID']}
        n = len(lg['divisions'])
        label = DIV_NAMES[divs.pop()] if len(divs) == 1 else ('' if n == 1 else
                                                               (('East', 'West'), ('East', 'Central', 'West'))[n - 2][p[2]])
        q = bytearray(p)
        put_str(q, 3, 17, label)
        asn.rewrite('d', off, bytes(q))

    # ---- teams
    parks = home_parks(con, year)
    mgrs = lahdb.managers(con, year)
    stock = AsnFile(open(os.path.join(install, 'Assn', '_DEFAULT.ASN'), 'rb').read())
    stock_t = {cstr(p, 0x45, 3): p for _, p in stock.recs['t']}
    used_stock = set()
    league_of_key = {s[2]: s[0] for s in slots}
    r_by_key = {asn.key('r', p): (off, p) for off, p in asn.recs['r']}
    fillers = iter(generated)
    filler_n = 0
    free = []
    for off, p in sorted(asn.recs['t'], key=lambda r: asn.key('t', r[1])):
        k = asn.key('t', p)
        tid = team_of_slot.get(k)
        q = bytearray(p)
        roff, rp = r_by_key[k]
        dh = dh_of_league[league_of_key[k]]
        if tid is None:
            filler_n += 1
            put_str(q, 0x12, 32, 'Filler Team %d' % filler_n)
            put_str(q, 0x34, 17, 'Generated')
            q[0x45:0x48] = ('FT%d' % filler_n)[:3].encode().ljust(3, b'\0')
            fs_recs = {}
            want_p, want_h = 10, 15
            while want_p or want_h:
                r = next(fillers)
                if r[68] == 1 and want_p:
                    want_p -= 1
                elif r[68] != 1 and want_h:
                    want_h -= 1
                else:
                    continue
                nid = add_generated(r)
                fs_recs[nid] = new_recs[-1]
            fs = FillerSeason(fs_recs)
            ids = list(fs_recs)
            active, reserve, _ = choose_roster(ids, fs)
            order, align = lineup(active, fs, dh)
            rot, pen = staff(active, fs)
        else:
            t = by_id[tid]
            put_str(q, 0x12, 32, team_name(t['name']))
            m = mgrs.get(tid)
            put_str(q, 0x34, 17, ('%s %s' % (m['first'], m['last'])).strip() if m else '')
            abbrev = tid[:3]
            q[0x45:0x48] = abbrev.encode('latin-1').ljust(3, b'\0')
            park, city = parks.get(tid, (t['park'], ''))
            put_str(q, 0x53, 30, park_name(park or t['park'] or ''))
            code = weather_code(city)
            if code:
                q[4] = code
            cand = [ab for ab, sp in stock_t.items() if sp[4] == q[4]]
            pick = FRANCH_STOCK.get(t['franchID'])
            if pick not in cand:
                pick = next((ab for ab in cand if ab not in used_stock), cand[0] if cand else None)
            if pick:
                used_stock.add(pick)
                q[0x74:0x74 + 9] = stock_t[pick][0x74:0x74 + 9]
                q[0x7d:0x7d + 44] = stock_t[pick][0x7d:0x7d + 44]
            active, reserve, over = choose_roster(rosters.get(tid, []), season)
            free += over
            order, align = lineup(active, season, dh)
            rot, pen = staff(active, season)
            conv = lambda xs: [add_real(x) if x not in (0, NONE) else x for x in xs]
            active, reserve, order, align, rot, pen = (conv(active), conv(reserve), conv(order), conv(align),
                                                       conv(rot), conv(pen))
            log('  %s %-28s %-24s act %d res %d over %d rot %d pen %d' % (
                abbrev, t['name'], park[:24], len(active), len(reserve), len(over), len(rot), len(pen)))
        asn.rewrite('t', off, bytes(q))
        asn.rewrite('r', roff, r_record(rp, active, reserve, order, align, rot, pen))
    for tid in plan['dropped']:
        free += rosters.get(tid, [])
    free_ids = [add_real(p) for p in sorted(set(free))]
    for off, _ in asn.recs.get('tr', []):
        asn.delete('tr', off)

    # ---- stats: career through year-1 (scope 2) and last season (scope 3)
    real = {nid: pid for pid, nid in id_of.items()}
    lines = []
    for scope, kw in ((2, {'before': year}), (3, {'year': year - 1})):
        bat, pit, fld = lahdb.batting(con, **kw), lahdb.pitching(con, **kw), lahdb.fielding(con, **kw)
        split = of_split(con, **kw)
        for nid, pid in sorted(real.items()):
            if pid in bat:
                lines.append(('bt', scope, nid, bat_words(bat[pid])))
            if pid in pit:
                lines.append(('pt', scope, nid, pit_words(pit[pid])))
            if pid in fld:
                lines.append(('ft', scope, nid, fld_words(fld[pid], split.get(pid, (0, 0, 0)))))
    dat = open(files['DAT'], 'rb').read()
    dat_out = ctree.do_apply(dat, stat_edits(dat, lines))

    # ---- write
    name = name or '%dL%d' % (len(slots), year)
    out = {'ASN': os.path.join(install, 'Assn', name + '.ASN'), 'PYR': os.path.join(install, 'Assn', name + '.PYR'),
           'PYF': os.path.join(install, 'Assn', name + '.PYF'), 'DAT': os.path.join(install, 'Stats', name + '.DAT')}
    with open(out['ASN'], 'wb') as fh:
        fh.write(asn.build())
    RT.write_pyr(out['PYR'], hdr, new_recs)
    with open(out['PYF'], 'wb') as fh:
        fh.write(b'PPD:' + struct.pack('<Ih', 2 + 2 * len(free_ids), len(free_ids)) +
                 struct.pack('<%dH' % len(free_ids), *free_ids))
    with open(out['DAT'], 'wb') as fh:
        fh.write(dat_out)
    log('wrote %s: %d players (%d free agents), %d stat lines' % (name, len(new_recs), len(free_ids), len(lines)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--year', type=int, required=True)
    ap.add_argument('--install', required=True, help='game directory holding Assn/ and Stats/')
    ap.add_argument('--db', default=DB)
    ap.add_argument('--name', help='file name (max 8 chars), default <teams>L<year>')
    a = ap.parse_args(argv)
    if not 1871 <= a.year <= 2019:
        ap.error('year must be 1871..2019 (the Lahman data range)')
    if a.name and (len(a.name) > 8 or not a.name.isalnum()):
        ap.error('--name: up to 8 letters/digits')
    build(a.year, a.install, a.db, a.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
