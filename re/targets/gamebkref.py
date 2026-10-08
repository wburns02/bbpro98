"""Referee for game.bki / game.bko, the shell <-> sim hand-off of one sim day (BBShell writes game.in -> game.bki,
the sim answers in game.out -> game.bko). Claude-owned: GLM must not edit it.

usage: python3 gamebkref.py <target_dir> <lane_dir> [-v]        score <lane>/voldat.py on the visible days
       python3 gamebkref.py <target_dir> <lane_dir> --holdout   unseen sim days (a directory the lane cannot read)
       python3 gamebkref.py <target_dir> <lane_dir> --audit X   text summary of each decode for the audit

Contract for <lane>/voldat.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 voldat.py decode NAME in.bin out.json        NAME = game.bki or game.bko
  python3 voldat.py encode NAME in.bin edited.json out.bin
  Same JSON rules as voldatref ("_" keys derived, every other leaf content and editable, encode(decode(x)) == x), plus:
  - both files decode to {"games": [...], ...} with one entry per game in file order;
  - every game.bko game has "batters" and "pitchers" lists (or "_batters"/"_pitchers" when the encoder derives them)
    whose rows carry the box-score fields  batters: pid ab h hr rbi bb so r sb   pitchers: pid outs bf h hr bb so r
    (other keys may be added). Truth: the day's box-score files (MLBPA97.H??/N??, decoded by the solved H decoder) must
    each equal one game's rows, one to one (rows compared as multisets);
  - every game.bki game names its two teams and lists the players the sim gets; truth: each game's set of player ids
    (int leaves under keys containing "pid" or "player", at most 64 distinct per game) must cover every pid of the
    matching box score.
targets: files.json {"days": [dir, ...], "holdout_days": [dir, ...]} (each dir holds game.bki, game.bko, MLBPA97.[HN]??).
"""
import sys, os, json, struct, glob, random, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read
import voldatref as V

# Frozen, reviewed copy of the solved H decoder (commit 50800fb), never a lane-writable file; pinned by hash.
HDEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'work', 'hdecode.py')
HDEC_SHA = '1f1bc3568e409953cfef03a2ba20ea483681a48ffc1c9749db59f9486e0edc3b'
BAT = ('pid', 'ab', 'h', 'hr', 'rbi', 'bb', 'so', 'r', 'sb')
PIT = ('pid', 'outs', 'bf', 'h', 'hr', 'bb', 'so', 'r')
HSEED = random.SystemRandom().randrange(1 << 30)


def chunks(blob):
    """Trusted walk of the tag + u32 length chunk stream."""
    out, off = [], 0
    while off < len(blob):
        if off + 8 > len(blob): fail('trailing bytes after the last chunk')
        tag, ln = blob[off:off + 4], struct.unpack_from('<I', blob, off + 4)[0]
        out.append((tag, blob[off + 8:off + 8 + ln])); off += 8 + ln
    return out


def box_scores(day):
    import subprocess
    if hashlib.sha256(open(HDEC, 'rb').read()).hexdigest() != HDEC_SHA: raise RuntimeError('work/hdecode.py changed')
    boxes = []
    for p in sorted(glob.glob(f'{day}/MLBPA97.[HN]??')):
        r = subprocess.run([sys.executable, '-I', '-B', HDEC, p], capture_output=True, text=True, timeout=60)
        if r.returncode: raise RuntimeError(f'hdecode failed on {p}: {r.stderr[-300:]}')
        d = json.loads(r.stdout)
        boxes.append((os.path.basename(p), sorted(tuple(b[k] for k in BAT) for b in d['batters']),
                      sorted(tuple(x[k] for k in PIT) for x in d['pitchers'])))
    return boxes


def rows(game, key, fields):
    rs = game.get(key, game.get('_' + key))
    if not isinstance(rs, list) or not rs: return None
    try:
        return sorted(tuple(r[k] for k in fields) for r in rs)
    except (KeyError, TypeError):
        return None


def pid_leaves(x, out, under=False):
    if isinstance(x, dict):
        for k, v in x.items():
            pid_leaves(v, out, under or ('pid' in str(k).lower() or 'player' in str(k).lower()))
    elif isinstance(x, list):
        for v in x: pid_leaves(v, out, under)
    elif V.isint(x) and under:
        out.add(x)
    return out


def check_day(codec, day, hold, seed):
    bko, bki = safe_read(f'{day}/game.bko', 4 << 20), safe_read(f'{day}/game.bki', 4 << 20)
    n_out = sum(1 for t, _ in chunks(bko) if t == b'GDO:')
    n_in = sum(1 for t, _ in chunks(bki) if t == b'GDI:')
    boxes = box_scores(day)
    if not boxes: raise RuntimeError(f'{day}: no box-score files')
    docs = {}
    for name, blob, n in (('game.bko', bko, n_out), ('game.bki', bki, n_in)):
        doc = V.decode(codec, name, blob)
        V.validate(name, blob, doc, coverage=False)   # GDI strings are enciphered, GDO is all u16 events; chunk headers would false-hit
        games = doc.get('games') if isinstance(doc, dict) else None
        if not isinstance(games, list) or len(games) != n:
            fail(f'{name}: "games" must list the {n} games of the file')
        if V.encode(codec, name, blob, doc) != blob: fail(f'{name}: encode(decode(x)) != x')
        docs[name] = doc
    # game.bko truth: each box score equals one game's rows
    out_rows = [(rows(g, 'batters', BAT), rows(g, 'pitchers', PIT)) for g in docs['game.bko']['games']]
    used, match = set(), {}
    for fname, bat, pit in boxes:
        hit = [i for i, (b, p) in enumerate(out_rows) if i not in used and b == bat and p == pit]
        if not hit:
            near = max(range(len(out_rows)), key=lambda i: len(set(out_rows[i][0] or []) & set(bat)))
            fail(f'game.bko: no game reproduces box score {fname} (closest game {near}: '
                 f'{len(set(out_rows[near][0] or []) & set(bat))}/{len(bat)} batter rows equal)')
        used.add(hit[0]); match[fname] = hit[0]
    # game.bki truth: the game that holds a box score's players covers all of them
    in_sets = [pid_leaves(g, set()) for g in docs['game.bki']['games']]
    for i, s in enumerate(in_sets):
        if len(s) > 64: fail(f'game.bki game {i}: {len(s)} distinct ints under pid/player keys; two 25-man rosters '
                             f'are 50, so non-player words are being labelled as players')
    for fname, bat, pit in boxes:
        need = {r[0] for r in bat} | {r[0] for r in pit}
        if not any(need <= s for s in in_sets):
            best = max(len(need & s) for s in in_sets)
            fail(f'game.bki: no game lists all {len(need)} players of box score {fname} under pid/player keys '
                 f'(best {best})')
    for name, blob in (('game.bko', bko), ('game.bki', bki)):
        for r in range(3 if hold else 1):
            V.edit_test(codec, name, blob, docs[name], seed + r, 8 if hold else 4, stored=(name == 'game.bko'),
                        grow=None if name == 'game.bko' else 4 * (8 if hold else 4))
    return len(boxes)


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/voldat.py'   # the jail names every voldatref codec voldat.py
    if '--audit' in sys.argv:
        day = cfg['days'][0]
        for name in ('game.bki', 'game.bko'):
            doc = V.decode(codec, name, safe_read(f'{day}/{name}', 4 << 20))
            print(f'== {name}:', json.dumps(doc)[:2500])
        return
    hold = '--holdout' in sys.argv
    ok_all, results = True, []
    for i, day in enumerate(cfg['holdout_days'] if hold else cfg['days']):
        try:
            n = check_day(codec, day, hold, (HSEED if hold else 100) + 31 * i)
            results.append(dict(day=os.path.basename(day), ok=True, box_scores=n))
        except Exception as e:
            ok_all = False
            results.append(dict(day=os.path.basename(day), ok=False, **({} if J.QUIET else {'error': J.err(e)})))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
