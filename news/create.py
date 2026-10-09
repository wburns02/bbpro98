"""Create a player for the hosted game: the record logic (a new player's 192-byte record, seeded from a stock donor's
ratings and kept to the grades asked for) and the writer that adds him to one association's free agent pool. The writer
refuses while the game holds the association's files open, backs them up, then rewrites them atomically. Pure functions
over bytes, except add_player, which touches the game directory. The form is createweb.py's; the codecs are
work/league.py.
"""
import datetime
import os
import re
import shutil
import struct

import gamedata
import league
import scout

POSITIONS = ('P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF')      # code = index + 1
HIT_RATINGS = ('contact', 'power', 'speed', 'arm', 'fielding')
PIT_RATINGS = ('stamina', 'control', 'hold')
ROLE_RATINGS = {'hit': HIT_RATINGS, 'pit': PIT_RATINGS + ('strikeout',)}   # strikeout has a Now grade only
INDEX = {'contact': 0, 'power': 1, 'speed': 2, 'arm': 3, 'hold': 4, 'stamina': 5, 'control': 6}   # fielding: 14 + code - 1
PITCH_SLOTS = ('FB', 'CB', 'SI', 'SL', 'CU', 'SC', 'KN')    # storage order: rating index 7 + slot number
PITCH_LABELS = {'FB': 'Fastball', 'CB': 'Curveball', 'SI': 'Sinker', 'SL': 'Slider', 'CU': 'Changeup',
                'SC': 'Screwball', 'KN': 'Knuckleball'}
RATING_LABELS = {'contact': 'Contact', 'power': 'Power', 'speed': 'Speed', 'arm': 'Arm', 'fielding': 'Fielding',
                 'stamina': 'Stamina', 'control': 'Control', 'hold': 'Hold runners', 'strikeout': 'Strikeout'}
GRADE_WORDS = ((80, 'elite'), (70, 'plus-plus'), (60, 'plus'), (55, 'above average'), (50, 'average'),
               (45, 'fringe'), (40, 'below average'), (30, 'well below average'), (20, 'poor'))
MODES = ('realistic', 'sandbox')
BUDGET = {'hit': (50, 100), 'pit': (80, 110)}      # (Now, Ceiling) points above 50 that a realistic player may spend
ARCHETYPES = {
    'contact': {'label': 'Contact hitter', 'role': 'hit',
                'blurb': 'A steady bat who puts the ball in play, with a reliable glove and little power.',
                'now': {'contact': 65, 'power': 40, 'speed': 55, 'arm': 50, 'fielding': 55},
                'ceiling': {'contact': 70, 'power': 45, 'speed': 55, 'arm': 50, 'fielding': 60}, 'pitches': {}},
    'slugger': {'label': 'Slugger', 'role': 'hit',
                'blurb': 'A power bat who hits for distance, runs slowly and is clumsy in the field.',
                'now': {'contact': 45, 'power': 70, 'speed': 35, 'arm': 50, 'fielding': 45},
                'ceiling': {'contact': 50, 'power': 75, 'speed': 35, 'arm': 50, 'fielding': 45}, 'pitches': {}},
    'speed': {'label': 'Speedster', 'role': 'hit',
              'blurb': 'A fast hitter who runs the bases well and covers ground in the field, with little power.',
              'now': {'contact': 55, 'power': 30, 'speed': 75, 'arm': 45, 'fielding': 60},
              'ceiling': {'contact': 60, 'power': 35, 'speed': 80, 'arm': 45, 'fielding': 65}, 'pitches': {}},
    'glove': {'label': 'Glove first', 'role': 'hit',
              'blurb': 'A first-rate fielder with a strong arm and a light bat.',
              'now': {'contact': 40, 'power': 35, 'speed': 55, 'arm': 65, 'fielding': 75},
              'ceiling': {'contact': 45, 'power': 35, 'speed': 55, 'arm': 65, 'fielding': 80}, 'pitches': {}},
    'prospect': {'label': 'Five-tool prospect', 'role': 'hit',
                 'blurb': 'Fringe at every hitting skill today, with a wide ceiling he can grow into.',
                 'now': {'contact': 45, 'power': 45, 'speed': 45, 'arm': 45, 'fielding': 45},
                 'ceiling': {'contact': 70, 'power': 70, 'speed': 70, 'arm': 70, 'fielding': 70}, 'pitches': {}},
    'regular': {'label': 'Everyday regular', 'role': 'hit',
                'blurb': 'A solid everyday player with no weakness, who is unlikely to grow much.',
                'now': {'contact': 50, 'power': 50, 'speed': 50, 'arm': 50, 'fielding': 50},
                'ceiling': {'contact': 55, 'power': 55, 'speed': 55, 'arm': 55, 'fielding': 55}, 'pitches': {}},
    'ace': {'label': 'Power ace', 'role': 'pit',
            'blurb': 'A power pitcher with a plus fastball and slider who can carry a rotation.',
            'now': {'stamina': 65, 'control': 50, 'hold': 50, 'strikeout': 70},
            'ceiling': {'stamina': 70, 'control': 55, 'hold': 50},
            'pitches': {'FB': (75, 80), 'SL': (65, 70), 'CU': (50, 55)}},
    'artist': {'label': 'Control artist', 'role': 'pit',
               'blurb': 'A starter who lives on control and a wide mix of pitches rather than velocity.',
               'now': {'stamina': 60, 'control': 75, 'hold': 55, 'strikeout': 45},
               'ceiling': {'stamina': 60, 'control': 75, 'hold': 55},
               'pitches': {'FB': (45, 45), 'CB': (60, 60), 'SI': (55, 55), 'CU': (65, 70)}},
    'sinker': {'label': 'Sinkerballer', 'role': 'pit',
               'blurb': 'A groundball starter whose sinker does most of the work, with little strikeout stuff.',
               'now': {'stamina': 60, 'control': 60, 'hold': 50, 'strikeout': 40},
               'ceiling': {'stamina': 65, 'control': 60, 'hold': 50},
               'pitches': {'SI': (70, 75), 'SL': (50, 55), 'CU': (50, 50)}},
    'knuckle': {'label': 'Knuckleballer', 'role': 'pit',
                'blurb': 'A knuckleballer who goes deep into games on a pitch no hitter can time.',
                'now': {'stamina': 70, 'control': 45, 'hold': 35, 'strikeout': 50},
                'ceiling': {'stamina': 70, 'control': 45, 'hold': 35},
                'pitches': {'FB': (35, 35), 'KN': (70, 75)}},
    'closer': {'label': 'Closer', 'role': 'pit',
               'blurb': 'A short reliever whose fastball and slider overpower hitters for the last three outs.',
               'now': {'stamina': 30, 'control': 55, 'hold': 45, 'strikeout': 75},
               'ceiling': {'stamina': 30, 'control': 60, 'hold': 45},
               'pitches': {'FB': (75, 80), 'SL': (70, 70)}},
    'swingman': {'label': 'Swingman', 'role': 'pit',
                 'blurb': 'A pitcher with an average arsenal and enough stamina to start or come out of the bullpen.',
                 'now': {'stamina': 50, 'control': 50, 'hold': 50, 'strikeout': 50},
                 'ceiling': {'stamina': 55, 'control': 55, 'hold': 50},
                 'pitches': {'FB': (50, 55), 'CB': (50, 55), 'CU': (50, 55)}},
}
GRADES = tuple(range(20, 81, 5))
AGES = range(17, 46)
NAME_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .'-]{0,15}")
REC = 192
PEAK, CUR = 0x46, 0x5d
K_ATTR = 0x76
PITCHES = range(7, 14)
BIRTH = 0x1a           # u32 birth serial: date.toordinal() + 365
NAME_FIRST, NAME_LAST = 30, 47         # 17-byte NUL-padded fields
NAME_MAX = 16
ATTRS_END = 0x8d       # the peak, current and attribute blocks are copied from the donor: 0x46..0x8c
STAMINA_BYTE = 0x96    # pitchers: min(255, 51 + current stamina); 0 for everyone else
PLAYER_MIN = 100       # ids below this are not players
BATS_CODE = {'L': 1, 'R': 2, 'S': 3}
THROWS_CODE = {'L': 1, 'R': 2}
NAME_MSG = 'Use letters, spaces, apostrophes, periods or hyphens, up to 16 characters.'
GRADE_MSG = 'Pick a grade from 20 to 80, in steps of 5.'
GAP_MSG = 'At %d a ceiling can be at most %d above Now.'
PPD = b'PPD:'


class AssociationOpen(Exception):
    """The game has one of the association's files open. The args hold the paths it has open."""


def rating(grade):
    """A 20-80 grade as a 0-99 rating; scout.grade maps it back to the same grade."""
    return min(99, max(1, round((grade - 20) * 99 / 60)))


def stuff(rec):
    """The mean of a player's nonzero current pitch ratings, 0.0 when he throws none."""
    pitches = [rec[CUR + i] for i in PITCHES if rec[CUR + i]]
    return sum(pitches) / len(pitches) if pitches else 0.0


def role(pos):
    """'pit' for a pitcher, 'hit' for everyone else."""
    return 'pit' if pos == 'P' else 'hit'


def archetype_fields(key):
    """The form fields that prefill step two for an archetype, every value a string: each Now grade of its role, each
    Ceiling grade but strikeout's, and for a pitcher each arsenal slot's two grades ('none' for a pitch he does not
    throw). KeyError for an unknown archetype."""
    arch = ARCHETYPES[key]
    fields = {}
    for r in ROLE_RATINGS[arch['role']]:
        fields['now_' + r] = str(arch['now'][r])
        if r != 'strikeout':
            fields['ceil_' + r] = str(arch['ceiling'][r])
    if arch['role'] == 'pit':
        for slot in PITCH_SLOTS:
            now, ceil = arch['pitches'].get(slot, ('none', 'none'))
            fields['p_%s_now' % slot] = str(now)
            fields['p_%s_ceil' % slot] = str(ceil)
    return fields


def max_gap(age):
    """The most a realistic ceiling can sit above Now at this age: 25 at 22 and under, 15 at 23 to 26, 5 at 27 to 30,
    none from 31."""
    if age <= 22:
        return 25
    if age <= 26:
        return 15
    if age <= 30:
        return 5
    return 0


def _spent(grades):
    """The budget points grades spend: each one's distance above 50."""
    return sum(max(0, g - 50) for g in grades)


def budget(spec):
    """What a spec spends of its role's budget: {'now', 'ceiling', 'now_max', 'ceiling_max'}. Hitters spend on their five
    hitting ratings. Pitchers spend on stamina, control, hold and strikeout's Now, plus their two best pitches by Now (in
    'now') and by Ceiling (in 'ceiling'); strikeout has no ceiling, so its Now counts in both."""
    key = role(spec['pos'])
    now, ceiling = spec['now'], spec['ceiling']
    if key == 'hit':
        n = _spent(now[r] for r in HIT_RATINGS)
        c = _spent(ceiling[r] for r in HIT_RATINGS)
    else:
        best_now = sorted((p[0] for p in spec['pitches'].values()), reverse=True)[:2]
        best_ceil = sorted((p[1] for p in spec['pitches'].values()), reverse=True)[:2]
        n = _spent([now[r] for r in ROLE_RATINGS['pit']] + best_now)
        c = _spent([ceiling[r] for r in PIT_RATINGS] + [now['strikeout']] + best_ceil)
    now_max, ceil_max = BUDGET[key]
    return {'now': n, 'ceiling': c, 'now_max': now_max, 'ceiling_max': ceil_max}


def grade_word(grade):
    """The scouting word for a grade: the first word in GRADE_WORDS whose floor it reaches."""
    return next((word for floor, word in GRADE_WORDS if grade >= floor), GRADE_WORDS[-1][1])


def _name_ok(name):
    return bool(NAME_RE.fullmatch(name)) and _latin1(name)


def _latin1(text):
    try:
        text.encode('latin-1')
    except UnicodeEncodeError:
        return False
    return True


def _pick(value, options):
    """The value as an int when it is decimal digits and one of options, else None."""
    if not re.fullmatch(r'[0-9]{1,3}', value):
        return None
    n = int(value)
    return n if n in options else None


def validate_who(form, assns):
    """(who, errors) for the first step: the association, the player's name, position, hands, age, archetype and mode.
    form is {field: value}, the first value of each field; assns the valid STEMs. who is None when there are errors,
    and a message never repeats the input."""
    errors = {}
    who = {}
    if form.get('assn', '') in assns:
        who['assn'] = form['assn']
    else:
        errors['assn'] = 'Pick an association.'
    for field in ('first', 'last'):
        name = form.get(field, '').strip()
        if not name:
            errors[field] = 'Enter a %s name.' % field
        elif _name_ok(name):
            who[field] = name
        else:
            errors[field] = NAME_MSG
    pos = form.get('pos', '')
    if pos in POSITIONS:
        who['pos'] = pos
    else:
        errors['pos'] = 'Pick a position.'
    if form.get('bats', '') in BATS_CODE:
        who['bats'] = form['bats']
    else:
        errors['bats'] = 'Pick left, right or switch.'
    if form.get('throws', '') in THROWS_CODE:
        who['throws'] = form['throws']
    else:
        errors['throws'] = 'Pick left or right.'
    age = _pick(form.get('age', ''), AGES)
    if age is None:
        errors['age'] = 'Pick an age from %d to %d.' % (AGES[0], AGES[-1])
    else:
        who['age'] = age
    if pos in POSITIONS:
        archetype = form.get('archetype', '')
        if archetype in ARCHETYPES and ARCHETYPES[archetype]['role'] == role(pos):
            who['archetype'] = archetype
        else:
            errors['archetype'] = 'Pick an archetype for this position.'
    if form.get('mode', '') in MODES:
        who['mode'] = form['mode']
    else:
        errors['mode'] = 'Pick realistic or sandbox.'
    if errors:
        return None, errors
    return who, errors


def validate_ratings(form, who):
    """(spec, errors) for the ratings of a valid who. Each Now and Ceiling grade of the role must be a grade, and no
    Ceiling below its Now; a pitcher's arsenal gives each pitch both grades or neither, and 2 to 5 pitches. Only then,
    in realistic mode, come the age's gap limit and the budget. spec is who plus 'now', 'ceiling' and 'pitches', and is
    None when there are errors."""
    errors = {}
    now, ceiling, pitches = {}, {}, {}
    for r in ROLE_RATINGS[role(who['pos'])]:
        g = _pick(form.get('now_' + r, ''), GRADES)
        if g is None:
            errors['now_' + r] = GRADE_MSG
        else:
            now[r] = g
        if r == 'strikeout':
            continue
        c = _pick(form.get('ceil_' + r, ''), GRADES)
        if c is None:
            errors['ceil_' + r] = GRADE_MSG
        elif g is not None and c < g:
            errors['ceil_' + r] = 'Ceiling must be at least Now.'
        else:
            ceiling[r] = c
    if role(who['pos']) == 'pit':
        for slot in PITCH_SLOTS:
            field = 'p_' + slot
            values = [form.get(field + '_now', 'none'), form.get(field + '_ceil', 'none')]
            grades = [_pick(v, GRADES) for v in values]
            if any(v != 'none' and g is None for v, g in zip(values, grades)):
                errors[field] = GRADE_MSG
            elif (values[0] == 'none') != (values[1] == 'none'):
                errors[field] = 'Give each pitch both grades, or neither.'
            elif values[0] != 'none' and grades[1] < grades[0]:
                errors[field] = 'Ceiling must be at least Now.'
            elif values[0] != 'none':
                pitches[slot] = (grades[0], grades[1])
        if not 2 <= len(pitches) <= 5:
            errors['pitches'] = 'Pick 2 to 5 pitches.'
    spec = dict(who, now=now, ceiling=ceiling, pitches=pitches)
    if not errors and who['mode'] == 'realistic':
        gap = max_gap(who['age'])
        for r, c in ceiling.items():
            if c - now[r] > gap:
                errors['ceil_' + r] = GAP_MSG % (who['age'], gap)
        for slot, (n, c) in pitches.items():
            if c - n > gap:
                errors['p_' + slot] = GAP_MSG % (who['age'], gap)
        b = budget(spec)
        if b['now'] > b['now_max']:
            errors['budget'] = 'Over the realistic budget: Now uses %d of %d points.' % (b['now'], b['now_max'])
        elif b['ceiling'] > b['ceiling_max']:
            errors['budget'] = ('Over the realistic budget: Ceiling uses %d of %d points.'
                                % (b['ceiling'], b['ceiling_max']))
    if errors:
        return None, errors
    return spec, errors


def validate(form, assns):
    """(spec, errors) for a whole submitted form: validate_who, then validate_ratings for a valid who. spec is None when
    either has errors."""
    who, errors = validate_who(form, assns)
    if who is None:
        return None, errors
    return validate_ratings(form, who)


def _is_player(rec):
    return _pid(rec) >= PLAYER_MIN and bool(gamedata.cstr(rec[NAME_FIRST:NAME_LAST])
                                             or gamedata.cstr(rec[NAME_LAST:NAME_LAST + 17]))


def _pid(rec):
    return rec[0] | rec[1] << 8


def _age(rec, year):
    """The donor's age in `year`; 27 when his birth serial is not a date."""
    serial = struct.unpack_from('<I', rec, BIRTH)[0]
    try:
        return year - datetime.date.fromordinal(serial - 365).year
    except (ValueError, OverflowError):
        return 27


def _name(rec):
    """'First Last' of a record, the NUL padding dropped."""
    return ('%s %s' % (gamedata.cstr(rec[NAME_FIRST:NAME_LAST]), gamedata.cstr(rec[NAME_LAST:NAME_LAST + 17]))).strip()


def _stuff_goal(spec):
    """The mean rating of the pitches a spec throws, at their Now grades: what a pitcher's stuff should read."""
    grades = [rating(now) for now, _ in spec['pitches'].values()]
    return sum(grades) / len(grades) if grades else 0.0


def _score(rec, spec, year):
    """How far a stock record is from the spec's Now grades: the rating gaps on the graded ratings plus twice the age
    gap."""
    now = spec['now']
    if spec['pos'] == 'P':
        gaps = (abs(rec[CUR + 5] - rating(now['stamina'])), abs(rec[CUR + 6] - rating(now['control'])),
                abs(rec[K_ATTR] - rating(now['strikeout'])), abs(stuff(rec) - _stuff_goal(spec)))
    else:
        gaps = tuple(abs(rec[CUR + INDEX[k]] - rating(now[k])) for k in ('contact', 'power', 'speed', 'arm'))
    return sum(gaps) + 2 * abs(_age(rec, year) - spec['age'])


def donor(recs, spec, year):
    """The stock player whose record seeds the new one, plain bytes. Pool: players at the spec's position, else the
    other side of pitcher versus hitter. The nearest by score wins; a tie goes to the lower id. year is the donor
    file's season."""
    code = POSITIONS.index(spec['pos']) + 1
    pitcher = spec['pos'] == 'P'
    pool = [r for r in recs if _is_player(r) and r[68] == code]
    if not pool:
        pool = [r for r in recs if _is_player(r) and (r[68] == 1) == pitcher]
    if not pool:
        raise ValueError('no donor player for position %s' % spec['pos'])
    return bytes(min(pool, key=lambda r: (_score(r, spec, year), _pid(r))))


def _name_field(text):
    return text.encode('latin-1')[:NAME_MAX].ljust(NAME_LAST - NAME_FIRST, b'\0')


def build_record(spec, donor_rec, new_id, year):
    """The new player's plain 192-byte record, seeded from donor_rec: the donor's attribute bytes, then each rating of the
    spec's role set from its grades. Current is the Now grade's rating, peak the Ceiling's (never below current). A
    hitter has no pitch bytes. A pitcher's thrown pitches get their grades and every other pitch is zero; strikeout is
    one byte with no peak."""
    rec = bytearray(REC)
    rec[PEAK:ATTRS_END] = donor_rec[PEAK:ATTRS_END]
    rec[67] = donor_rec[67]
    rec[69] = donor_rec[69]
    struct.pack_into('<H', rec, 0, new_id)
    struct.pack_into('<I', rec, BIRTH, datetime.date(year - spec['age'], 7, 1).toordinal() + 365)
    rec[NAME_FIRST:NAME_LAST] = _name_field(spec['first'])
    rec[NAME_LAST:NAME_LAST + 17] = _name_field(spec['last'])
    rec[64] = 1
    rec[65] = BATS_CODE[spec['bats']]
    rec[66] = THROWS_CODE[spec['throws']]
    code = POSITIONS.index(spec['pos']) + 1
    rec[68] = code
    now, ceiling = spec['now'], spec['ceiling']

    def put(i, now_grade, ceiling_grade):
        rec[CUR + i] = rating(now_grade)
        rec[PEAK + i] = max(rating(now_grade), rating(ceiling_grade))

    if spec['pos'] == 'P':
        for r in PIT_RATINGS:
            put(INDEX[r], now[r], ceiling[r])
        rec[K_ATTR] = rating(now['strikeout'])
        for k, slot in enumerate(PITCH_SLOTS):
            if slot in spec['pitches']:
                put(7 + k, *spec['pitches'][slot])
            else:
                rec[CUR + 7 + k] = rec[PEAK + 7 + k] = 0
        rec[STAMINA_BYTE] = min(255, 51 + rec[CUR + 5])
    else:
        for r in HIT_RATINGS:
            put(14 + code - 1 if r == 'fielding' else INDEX[r], now[r], ceiling[r])
        for i in PITCHES:
            rec[CUR + i] = rec[PEAK + i] = 0
    return bytes(rec)


def scouting_report(spec):
    """The scouting report as plain sentences, no HTML: one per rating of the role (the hitting ratings, or stamina,
    control, hold and strikeout), then one per pitch the spec throws, in slot order. A rating names its grade's word and,
    when its Ceiling is above its Now, the Ceiling's word as the projection."""
    now, ceiling = spec['now'], spec['ceiling']
    out = []
    for r in ROLE_RATINGS[role(spec['pos'])]:
        if r != 'strikeout' and ceiling[r] > now[r]:
            out.append('%s is %s, with room to grow to %s.'
                       % (RATING_LABELS[r], grade_word(now[r]), grade_word(ceiling[r])))
        else:
            out.append('%s is %s.' % (RATING_LABELS[r], grade_word(now[r])))
    for slot in PITCH_SLOTS:
        if slot in spec['pitches']:
            n, c = spec['pitches'][slot]
            out.append('%s: %d now, %d at the ceiling.' % (PITCH_LABELS[slot], n, c))
    return out


def _distance(rec, spec):
    """How far a real record's current ratings are from a spec's Now grades: a hitter's four hitting ratings and his
    fielding at the spec's position; a pitcher's stamina, control, strikeout and stuff."""
    now = spec['now']
    if spec['pos'] == 'P':
        return (abs(rec[CUR + 5] - rating(now['stamina'])) + abs(rec[CUR + 6] - rating(now['control']))
                + abs(rec[K_ATTR] - rating(now['strikeout'])) + abs(stuff(rec) - _stuff_goal(spec)))
    field = CUR + 14 + POSITIONS.index(spec['pos'])
    return (sum(abs(rec[CUR + INDEX[k]] - rating(now[k])) for k in ('contact', 'power', 'speed', 'arm'))
            + abs(rec[field] - rating(now['fielding'])))


def comparable(game_dir, stem, spec, year):
    """The association's real player closest to a spec, as {'pid', 'name', 'team', 'age', 'distance'}, or None. The pool is
    the players (id 100 and up, with a name) who are on a roster or in the free agent pool, at the spec's position (a
    pitcher's is code 1). team is the roster's abbreviation, None for a free agent. The smallest distance wins, a tie
    going to the lower id. Never raises: a file that does not read or parse gives None."""
    assn_dir = os.path.join(game_dir, 'Assn')
    try:
        pyr = _locate(assn_dir, stem + '.PYR')
        asn = _locate(assn_dir, stem + '.ASN')
        if pyr is None or asn is None:
            return None
        pyf = _locate(assn_dir, stem + '.PYF')
        team_of = {}
        for team in gamedata.association(asn)['teams'].values():
            for pid in team['roster']:
                team_of.setdefault(pid, team['abbrev'] or None)
        pool = set(team_of) | set(pyf_ids(_read(pyf)) if pyf else ())
        _, recs = decipher(_read(pyr))
    except Exception:  # any file that does not read or parse gives no match
        return None
    code = POSITIONS.index(spec['pos']) + 1
    cands = [r for r in recs if _pid(r) in pool and _is_player(r) and r[68] == code]
    if not cands:
        return None
    best = min(cands, key=lambda r: (_distance(r, spec), _pid(r)))
    pid = _pid(best)
    return {'pid': pid, 'name': _name(best), 'team': team_of.get(pid), 'age': _age(best, year),
            'distance': round(_distance(best, spec))}


def _tables(header):
    """(encipher, decipher) byte tables of a PYR file, from the seed in its header's bytes 0-1."""
    fwd = league._forward((header[0], header[1]))
    inv = bytearray(256)
    for x, y in enumerate(fwd):
        inv[y] = x
    return fwd, bytes(inv)


def decipher(data):
    """(header, plain records) of a PYR file. ValueError unless its size is a positive multiple of 192."""
    if not data or len(data) % REC:
        raise ValueError('not a PYR file')
    _, inv = _tables(data)
    return bytes(data[:REC]), [bytes(data[i:i + REC]).translate(inv) for i in range(REC, len(data), REC)]


def encipher(header, recs):
    """The bytes of a PYR file: the header as is, then each plain record enciphered with the header's seed."""
    if len(header) != REC or any(len(r) != REC for r in recs):
        raise ValueError('header and records must be 192 bytes')
    fwd, _ = _tables(header)
    return b''.join([bytes(header)] + [bytes(r).translate(fwd) for r in recs])


def _pyf_head(data):
    """(n_bytes, count) of a PYF pool list. ValueError when the bytes are not one."""
    if not data or len(data) < 10 or data[:4] != PPD:
        raise ValueError('not a PYF file')
    n_bytes = struct.unpack_from('<I', data, 4)[0]
    count = struct.unpack_from('<h', data, 8)[0]
    if count < 0 or n_bytes != 2 + 2 * count or 8 + n_bytes > len(data):
        raise ValueError('PYF list is inconsistent')
    return n_bytes, count


def pyf_ids(data):
    """The player ids in a PYF free agent pool."""
    _, count = _pyf_head(data)
    return list(struct.unpack_from('<%dH' % count, data, 10))


def pyf_add(data, pid):
    """The PYF bytes with pid added to the pool. data None or b'' gives a fresh file holding only pid. Bytes after the
    list are stale leftovers the game ignores; they are kept, after the new id."""
    if not 0 <= pid <= 0xFFFF:
        raise ValueError('player id out of range: %d' % pid)
    if not data:
        return struct.pack('<4sIhH', PPD, 4, 1, pid)
    n_bytes, count = _pyf_head(data)
    return (struct.pack('<4sIh', PPD, n_bytes + 2, count + 1) + data[10:10 + 2 * count] + struct.pack('<H', pid)
            + data[8 + n_bytes:])


def open_by_anyone(paths, proc='/proc'):
    """The subset of paths that some process holds open, found through the fd links under proc/<pid>/fd. Processes
    that vanish or cannot be read are skipped."""
    held = set()
    try:
        pids = os.listdir(proc)
    except OSError:
        return []
    for pid in pids:
        if not (pid.isascii() and pid.isdigit()):
            continue
        fd_dir = os.path.join(proc, pid, 'fd')
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            link = os.path.join(fd_dir, fd)
            if os.path.exists(link):     # a broken link holds nothing
                held.add(os.path.realpath(link))
    return [p for p in paths if os.path.realpath(p) in held]


def _locate(directory, name):
    """gamedata.find, or None when the directory is missing too."""
    try:
        return gamedata.find(directory, name)
    except OSError:
        return None


def _read(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _donor_year(donor_path):
    """The season of the donor file, from the association named by the ASN beside it (1996 when there is none)."""
    folder, name = os.path.split(donor_path)
    asn = _locate(folder or '.', os.path.splitext(name)[0] + '.ASN')
    if asn is None:
        return 1996
    try:
        label = gamedata.association(asn)['name']
    except Exception:  # an ASN that does not parse counts as no ASN
        return 1996
    return scout.year_of(label) or 1996


def _write_atomic(path, data):
    """Replace path with data through a temporary file beside it, keeping the file's permission bits."""
    folder, name = os.path.split(path)
    tmp = os.path.join(folder, '.%s.create-tmp' % name)
    try:
        with open(tmp, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def add_player(game_dir, spec, donor_path, backup_dir, now, proc='/proc'):
    """Add the spec's player to one association's free agent pool: a new record at the end of its PYR and his id in its
    PYF, after backing both up. Raises AssociationOpen, and writes nothing, while the game has any of its files open.
    Returns (new id, plain record bytes)."""
    stem = spec['assn']
    assn_dir = os.path.join(game_dir, 'Assn')
    asn = _locate(assn_dir, stem + '.ASN')
    pyr = _locate(assn_dir, stem + '.PYR')
    if asn is None or pyr is None:
        raise ValueError('%s: no ASN or PYR file in %s' % (stem, assn_dir))
    pyf = _locate(assn_dir, stem + '.PYF')
    dat = _locate(os.path.join(game_dir, 'Stats'), stem + '.DAT')
    held = open_by_anyone([p for p in (asn, pyr, pyf, dat) if p], proc)
    if held:
        raise AssociationOpen(held)
    year = scout.year_of(gamedata.association(asn)['name']) or 1997
    _, donor_recs = decipher(_read(donor_path))
    donor_rec = donor(donor_recs, spec, _donor_year(donor_path))
    header, recs = decipher(_read(pyr))
    pid = max([_pid(r) for r in recs if _pid(r) >= PLAYER_MIN], default=PLAYER_MIN - 1) + 1
    if pid > 0xFFFF:
        raise ValueError('%s: no player id left' % stem)
    rec = build_record(spec, donor_rec, pid, year)
    new_pyr = encipher(header, recs + [bytes(rec)])
    target_pyf = pyf or os.path.join(assn_dir, stem + '.PYF')
    new_pyf = pyf_add(_read(pyf) if pyf else None, pid)

    folder = os.path.join(backup_dir, '%s-%s-%d' % (stem, now.strftime('%Y%m%dT%H%M%S'), pid))
    os.makedirs(folder, exist_ok=True)
    for f in (pyr, pyf):
        if f:
            shutil.copy2(f, folder)
    _write_atomic(pyr, new_pyr)
    _write_atomic(target_pyf, new_pyf)
    return pid, bytes(rec)
