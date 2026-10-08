"""Referee for the H-file lineup card (the enciphered 2698-byte first table of MLBPA97.Hxx). Claude-owned: GLM must
not edit it.

usage: python3 hcardref.py <target_dir> <lane_dir> [-v]         score <lane>/hcard.py on the visible days
       python3 hcardref.py <target_dir> <lane_dir> --holdout     same checks on a sim day the lane never sees
       python3 hcardref.py <target_dir> <lane_dir> --audit X     text summary of one decode for the audit

Contract for <lane>/hcard.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 hcard.py decode in.H out.json
      {"game": {"month": int, "day": int, ...},
       "sides": [{"side": "away", "team_id": int, "abbrev": str, "name": str,
                  "players": [{"pid": int, "positions": [codes], ...} one per occupied player slot],
                  "pitchers": [pids], ...},
                 {"side": "home", ...same...}],
       ...any other keys...}
      positions = every fielding position the player played in this game, codes from POS (empty if none).
  python3 hcard.py encode in.H edited.json out.H
      rebuilds the file from in.H with game.month/day, each side's abbrev/name and each player's positions taken
      from edited.json; encode(x, decode(x)) == x byte for byte.
Checks: schema; for every H file new on a visible day: team ids == the box-score team rows (side 0 = away), abbrev and
name == the league file's team record, month/day == the newly played schedule game of those two teams, players ==
the occupied slots (trusted read) and contain every box-score player of that side, every player in that team's
roster (that day or the day before), pitchers == the box-score pitchers as a set, positions == the trusted mask for
every player and == the fielding-line changes in the stats database for every player in exactly one game that day;
at most 25% generic key names; round trip on every distinct H file; edit test on EDIT_FILES (one player's positions,
the away abbrev, the day +1) that must decode to exactly the edit, show up in a trusted decipher of the table (mask,
abbrev bytes, day serial +1), change no byte outside the table body and at most 12 bytes inside it.
PASS = every visible check passes.
"""
import sys, os, json, glob, struct, tempfile, collections, hashlib, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read
import asnref as A
WORK = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'work'))
sys.path.insert(0, WORK)
import fpscipher as C
import league as L
import stats as ST

MAX_CODEC = 200_000
TIMEOUT = 300
POS = ['p', 'c', '1b', '2b', '3b', 'ss', 'lf', 'cf', 'rf']
SIDE, SLOT0, SLOT, NSLOT, SERIAL = 0x533, 0x32, 21, 40, 0xa72      # verified by Claude's probes 2026-10-07
EDIT_FILES = 2                                                     # first EDIT_FILES new H files of each edit day
GENERIC = re.compile(r'^(f|w|b|c|x|u|v|word|byte|col|field|unk|unknown|val|value|off|s)_?[0-9a-f]+$', re.I)
isint = lambda v: isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------- trusted readers

def card(blob):
    if len(blob) < 2706 or blob[:2] != b'\x02\x65' or blob[6:8] != b'\x8a\x0a': fail('not an H file with a lineup card')
    return C.decipher(blob[10:2706], blob[8:10])


def trusted_slots(t, s):
    out = {}
    for k in range(NSLOT):
        o = s * SIDE + SLOT0 + SLOT * k
        pid, mask = struct.unpack_from('<HH', t, o)
        if pid: out[pid] = {POS[i] for i in range(9) if mask >> i & 1}
    return out


def box(blob):
    """{side: {'tid', 'bat': set, 'pit': set}} from the plaintext box tables."""
    b = {0: {'tid': None, 'bat': set(), 'pit': set()}, 1: {'tid': None, 'bat': set(), 'pit': set()}}
    for rec, u in A.h_tables(blob):
        s = 1 if u[2] & 0x8000 else 0; pid = u[2] & 0x7fff
        if pid < 100: b[s]['tid'] = pid
        elif rec == 40: b[s]['bat'].add(pid)
        elif rec == 70: b[s]['pit'].add(pid)
    return b


def league(path):
    return L.build_json(L.parse_container(safe_read(f'{path}/MLBPA97.ASN', 16 << 20)))


def fielding(path):
    d = safe_read(f'{path}/mlbpa97.DAT', 64 << 20)
    out = {}
    for off, (mem, u) in ST.stat_records(d).items():
        if mem == 4 and u[0] == 1:
            out[u[2]] = [u[3 + 8 * i + 2] for i in range(9)]           # games at each position, this season
    return out


def new_h(day, prev):
    have = lambda d: {os.path.basename(p) for p in glob.glob(f'{d}/MLBPA97.H*')} if d else set()
    return sorted(have(day) - have(prev))


# ---------------------------------------------------------------- lane I/O

def decode(codec, blob):
    with tempfile.TemporaryDirectory(prefix='hcardref') as td:
        with open(f'{td}/in.bin', 'wb') as fh: fh.write(blob)
        J.jail(codec, td, ['decode', 'in.bin', 'out.json'], name='hcard.py', max_size=MAX_CODEC, timeout=TIMEOUT)
        return json.loads(J.read_file(td, 'out.json', 8 << 20))


def encode(codec, blob, doc):
    with tempfile.TemporaryDirectory(prefix='hcardref') as td:
        with open(f'{td}/in.bin', 'wb') as fh: fh.write(blob)
        with open(f'{td}/edited.json', 'w') as fh: json.dump(doc, fh)
        J.jail(codec, td, ['encode', 'in.bin', 'edited.json', 'out.bin'], name='hcard.py', max_size=MAX_CODEC,
               timeout=TIMEOUT)
        return J.read_file(td, 'out.bin', 4 * len(blob) + (1 << 20))


# ---------------------------------------------------------------- checks

def keys_of(doc):
    ks = []
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items(): ks.append(k); walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(doc)
    return ks


def validate(doc, t):
    """Schema, trusted slot equality and positions masks. Returns the two sides."""
    if not isinstance(doc, dict) or not isinstance(doc.get('game'), dict) or not isinstance(doc.get('sides'), list):
        fail('decode output needs "game" and "sides"')
    g = doc['game']
    if not (isint(g.get('month')) and isint(g.get('day'))): fail('game.month/day must be ints')
    if len(doc['sides']) != 2: fail('need exactly 2 sides')
    for s, sd in enumerate(doc['sides']):
        if not isinstance(sd, dict) or sd.get('side') != ('away', 'home')[s]: fail(f'sides[{s}].side must be {("away", "home")[s]!r}')
        if not (isint(sd.get('team_id')) and isinstance(sd.get('abbrev'), str) and isinstance(sd.get('name'), str)
                and isinstance(sd.get('players'), list) and isinstance(sd.get('pitchers'), list)):
            fail(f'sides[{s}] needs team_id, abbrev, name, players, pitchers')
        pl = {}
        for p in sd['players']:
            if not (isinstance(p, dict) and isint(p.get('pid')) and isinstance(p.get('positions'), list)
                    and all(c in POS for c in p['positions'])):
                fail(f'sides[{s}]: bad player entry {str(p)[:160]} (positions use codes {POS})')
            if p['pid'] in pl: fail(f'sides[{s}]: pid {p["pid"]} listed twice')
            pl[p['pid']] = set(p['positions'])
        tr = trusted_slots(t, s)
        if set(pl) != set(tr):
            fail(f'sides[{s}]: players differ from the occupied player slots ({len(set(tr) - set(pl))} missing, '
                 f'{len(set(pl) - set(tr))} extra)')
        bad = [p for p in tr if tr[p] != pl[p]]
        if bad: fail(f'sides[{s}]: positions wrong for {len(bad)} players, e.g. pid {bad[0]}')
    ks = keys_of(doc)
    lazy = sum(1 for k in ks if GENERIC.match(k) or not k.strip())
    if lazy > 0.25 * max(1, len(set(ks))) and lazy > 3: fail(f'{lazy} keys are generic (f12, byte3, ...); name what they mean')
    return doc['sides']


def truth_check(doc, blob, lg, lg_prev, newly, fld, fld_prev, once):
    b = box(blob); tm = {x['tid']: x for x in lg['teams']}
    tm_prev = {x['tid']: x for x in lg_prev['teams']} if lg_prev else {}
    sides = doc['sides']
    for s in (0, 1):
        sd = sides[s]; tid = b[s]['tid']
        if sd['team_id'] != tid: fail(f'{sd["side"]} team_id {sd["team_id"]} != box-score team {tid}')
        if tid not in tm: fail(f'box team {tid} not in the league file')
        if sd['abbrev'] != tm[tid]['abbrev'] or sd['name'] != tm[tid]['name']:
            fail(f'{sd["side"]} abbrev/name {sd["abbrev"]!r}/{sd["name"]!r} != league {tm[tid]["abbrev"]!r}/{tm[tid]["name"]!r}')
        pl = {p['pid']: set(p['positions']) for p in sd['players']}
        need = b[s]['bat'] | b[s]['pit']
        if need - set(pl): fail(f'{sd["side"]}: {len(need - set(pl))} box-score players missing from players')
        roster = set(tm[tid]['roster']) | set(tm_prev.get(tid, {}).get('roster', []))
        if set(pl) - roster: fail(f'{sd["side"]}: {len(set(pl) - roster)} players not on the team roster')
        if set(sd['pitchers']) != b[s]['pit']: fail(f'{sd["side"]}: pitchers != the box-score pitchers')
        for pid, ps in pl.items():
            if once.get(pid) != 1 or pid not in fld: continue
            played = {POS[i] for i in range(9) if fld[pid][i] > fld_prev.get(pid, [0] * 9)[i]}
            if ps != played: fail(f'{sd["side"]}: pid {pid} positions {sorted(ps)} != fielding change {sorted(played)}')
    a, h = b[0]['tid'], b[1]['tid']
    dates = {(g['month'], g['day']) for g in newly if g['away'] == a and g['home'] == h}
    if not dates: fail(f'no newly played schedule game {a} at {h}')
    if (doc['game']['month'], doc['game']['day']) not in dates:
        fail(f'game date {doc["game"]["month"]}/{doc["game"]["day"]} != schedule {sorted(dates)}')


def edit_test(codec, blob, doc):
    t0 = card(blob)
    ed = json.loads(json.dumps(doc))
    home = ed['sides'][1]; away = ed['sides'][0]
    p = next((x for x in home['players'] if x['positions']), None) or home['players'][0]
    new = ['rf'] if set(p['positions']) != {'rf'} else ['lf', 'cf']
    p['positions'] = new
    ab = away['abbrev']; away['abbrev'] = ab[:-1] + ('Q' if ab[-1:] != 'Q' else 'Z')
    g = ed['game']; step = 1 if g['day'] <= 27 else -1; g['day'] += step
    out = encode(codec, blob, ed)
    if len(out) != len(blob): fail(f'edit: length {len(blob)} -> {len(out)}')
    if out[:10] != blob[:10] or out[2706:] != blob[2706:]: fail('edit: bytes outside the card body changed')
    t1 = card(out)
    diff = sum(1 for x, y in zip(t0, t1) if x != y)
    if diff > 12: fail(f'edit: {diff} card bytes changed (expected <= 12)')
    if trusted_slots(t1, 1).get(p['pid']) != set(new): fail('edit: the trusted mask does not show the new positions')
    if t1[0x2d:0x2d + len(away['abbrev'])].decode('latin1') != away['abbrev']: fail('edit: abbrev not stored in place')
    s0, s1 = struct.unpack_from('<I', t0, SERIAL)[0], struct.unpack_from('<I', t1, SERIAL)[0]
    if s1 - s0 != step: fail(f'edit: day serial moved by {s1 - s0}, expected {step}')
    back = decode(codec, out)
    validate(back, t1)
    if back['game']['day'] != g['day'] or back['sides'][0]['abbrev'] != away['abbrev']: fail('edit: decode differs from the edit')
    if next(set(x['positions']) for x in back['sides'][1]['players'] if x['pid'] == p['pid']) != set(new):
        fail('edit: decoded positions differ from the edit')


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/hcard.py'
    hold = '--holdout' in sys.argv
    if '--audit' in sys.argv:
        d = cfg['days'][len(cfg['days']) // 2]
        f = sorted(glob.glob(f'{d}/MLBPA97.H*'))[-1]
        doc = decode(codec, safe_read(f, 1 << 20))
        sides = doc.get('sides', [])
        print('decoded one H file - top-level keys:', list(doc)[:30])
        print(' game:', json.dumps(doc.get('game'))[:1500])
        for sd in sides[:2]:
            print(' side:', json.dumps({k: v for k, v in sd.items() if k != 'players'})[:1500])
            for p in sd.get('players', [])[:4]: print('   player:', json.dumps(p)[:400])
        other = {k: v for k, v in doc.items() if k not in ('game', 'sides')}
        print(' other keys:', json.dumps(other)[:2000])
        return
    days = cfg['holdout_days'] if hold else cfg['days']
    order = ([cfg['holdout_prev']] if hold else []) + days
    ok_all, results, seen = True, [], set()

    def record(name, ok, **kw):
        nonlocal ok_all
        ok_all &= ok
        results.append(dict(file=name, ok=ok, **({} if J.QUIET else kw)))

    for i, path in enumerate(order):
        if path not in days: continue
        name = path.split('/')[-1]
        pdir = order[i - 1] if i > 0 else None
        files = new_h(path, pdir) if pdir else []
        n_ok = 0
        try:
            if pdir:
                lg, lg_prev = league(path), league(pdir)
                k = lambda g: (g['month'], g['day'], g['slot'], g['away'], g['home'])
                was = {k(g) for g in lg_prev['games'] if g['played']}
                newly = [g for g in lg['games'] if g['played'] and k(g) not in was]
                fld, fld_prev = fielding(path), fielding(pdir)
                once = collections.Counter()
                cards = {}
                for f in files:
                    blob = safe_read(f'{path}/{f}', 1 << 20); t = card(blob)
                    cards[f] = (blob, t)
                    for s in (0, 1): once.update(trusted_slots(t, s).keys())
                for j, f in enumerate(files):
                    blob, t = cards[f]
                    doc = decode(codec, blob)
                    validate(doc, t)
                    truth_check(doc, blob, lg, lg_prev, newly, fld, fld_prev, once)
                    if encode(codec, blob, doc) != blob: fail(f'{f}: encode(decode(x)) != x')
                    seen.add(hashlib.sha256(blob).hexdigest())
                    if name in cfg.get('edit', []) and not hold and j < EDIT_FILES: edit_test(codec, blob, doc)
                    n_ok += 1
            for f in sorted(os.path.basename(p) for p in glob.glob(f'{path}/MLBPA97.H*')):
                blob = safe_read(f'{path}/{f}', 1 << 20); hsh = hashlib.sha256(blob).hexdigest()
                if hsh in seen: continue
                doc = decode(codec, blob); validate(doc, card(blob))
                if encode(codec, blob, doc) != blob: fail(f'{f}: encode(decode(x)) != x')
                seen.add(hsh)
            record(name, True, new_games=len(files), checked=n_ok,
                   **({'edit': True} if name in cfg.get('edit', []) and not hold else {}))
        except Exception as e:
            record(name, False, new_games=len(files), checked=n_ok, error=J.err(e))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
