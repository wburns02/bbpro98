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
HIT_GRADES = ('contact', 'power', 'speed', 'arm', 'fielding')
PIT_GRADES = ('stamina', 'control', 'strikeout', 'stuff')
GRADES = tuple(range(20, 81, 5))
AGES = range(17, 46)
NAME_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .'-]{0,15}")
REC = 192
PEAK, CUR = 0x46, 0x5d
GAP = 0x17
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


def validate(form, assns):
    """(spec, errors) for a submitted form: form is {field: value}, the first value of each field; assns the valid
    STEMs. errors maps a field to a short message and spec is None when there are any. Only the grades of the
    player's own role are checked. A message never repeats the input."""
    errors = {}
    spec = {}
    if form.get('assn', '') in assns:
        spec['assn'] = form['assn']
    else:
        errors['assn'] = 'Pick an association.'
    for field in ('first', 'last'):
        name = form.get(field, '').strip()
        if not name:
            errors[field] = 'Enter a %s name.' % field
        elif _name_ok(name):
            spec[field] = name
        else:
            errors[field] = NAME_MSG
    pos = form.get('pos', '')
    if pos in POSITIONS:
        spec['pos'] = pos
    else:
        errors['pos'] = 'Pick a position.'
    if form.get('bats', '') in BATS_CODE:
        spec['bats'] = form['bats']
    else:
        errors['bats'] = 'Pick left, right or switch.'
    if form.get('throws', '') in THROWS_CODE:
        spec['throws'] = form['throws']
    else:
        errors['throws'] = 'Pick left or right.'
    age = _pick(form.get('age', ''), AGES)
    if age is None:
        errors['age'] = 'Pick an age from %d to %d.' % (AGES[0], AGES[-1])
    else:
        spec['age'] = age
    grades = {}
    for field in PIT_GRADES if pos == 'P' else HIT_GRADES:
        grade = _pick(form.get(field, ''), GRADES)
        if grade is None:
            errors[field] = GRADE_MSG
        else:
            grades[field] = grade
    if errors:
        return None, errors
    spec['grades'] = grades
    return spec, errors


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


def _score(rec, spec, year):
    """How far a stock record is from the spec: the rating gaps on the graded ratings plus twice the age gap."""
    g = spec['grades']
    if spec['pos'] == 'P':
        gaps = (abs(rec[CUR + 5] - rating(g['stamina'])), abs(rec[CUR + 6] - rating(g['control'])),
                abs(rec[K_ATTR] - rating(g['strikeout'])), abs(stuff(rec) - rating(g['stuff'])))
    else:
        gaps = tuple(abs(rec[CUR + i] - rating(g[k]))
                     for i, k in ((0, 'contact'), (1, 'power'), (2, 'speed'), (3, 'arm')))
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
    """The new player's plain 192-byte record, seeded from donor_rec. Each graded rating is set with the donor's
    peak-over-current gap kept (the peak capped at 99). Pitchers keep the donor's pitches, shifted to the fitted
    stuff."""
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
    g = spec['grades']

    def put(off, value):
        rec[off] = value
        rec[off - GAP] = min(99, value + max(0, donor_rec[off - GAP] - donor_rec[off]))

    if spec['pos'] == 'P':
        put(CUR + 5, rating(g['stamina']))
        put(CUR + 6, rating(g['control']))
        rec[K_ATTR] = rating(g['strikeout'])
        shift = rating(g['stuff']) - stuff(donor_rec)
        for i in PITCHES:
            if donor_rec[CUR + i]:
                put(CUR + i, min(99, max(1, round(donor_rec[CUR + i] + shift))))
        rec[STAMINA_BYTE] = min(255, 51 + rec[CUR + 5])
    else:
        put(CUR + 0, rating(g['contact']))
        put(CUR + 1, rating(g['power']))
        put(CUR + 2, rating(g['speed']))
        put(CUR + 3, rating(g['arm']))
        put(CUR + 14 + code - 1, rating(g['fielding']))
    return bytes(rec)


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
