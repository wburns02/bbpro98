"""Referee for the league-file (MLBPA97.ASN) semantic codec. Claude-owned: GLM must not edit it.

usage: python3 asnref.py <target_dir> <lane_dir> [-v]         score <lane>/league.py on the visible days
       python3 asnref.py <target_dir> <lane_dir> --holdout     same checks on sim days the lane never sees
       python3 asnref.py <target_dir> <lane_dir> --audit X     text summary of one decode for the audit

Contract for <lane>/league.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 league.py decode in.bin out.json
      {"teams": [{"tid": 1..28 (the team id the box-score H files use), "name": str, "w": int, "l": int,
                  "roster": [player ids], ...any other fields...}  x 28],
       "games": [{"home": tid, "away": tid, "played": bool, "hr": int, "ar": int (runs; any value when unplayed),
                  ...}  one per schedule entry],
       ...any other members/fields (the more of the file decoded, the better)...}
  python3 league.py encode in.bin edited.json out.bin
      rebuilds the league file from in.bin with every contract field taken from edited.json;
      encode(x, decode(x)) must reproduce x byte for byte.
Checks per file: schema; the 28 names; 162 scheduled games per team; >= 20 roster ids per team; sum(w) == sum(l) == played games and each team's w+l == its played games; the 28 names
equal files.json "names"; for each consecutive day pair, every team's W and L grow by exactly that day's box-score
wins/losses and the newly played games equal that day's box scores ({(tid, runs), (tid, runs)} per game); every player
id a box score credits to a team is in that team's roster that day or the day before (>= 99%); round trip; and on the
"edit" files: rename a team, add 3 wins to another, add a run to a played game, encode, and require (a) decode shows
exactly those changes, (b) the trusted c-tree codec (work/ctree.py) still parses the file with consistent indexes and
at most 8 records changed, (c) the new name is present, correctly enciphered, in a team record.
PASS = every visible check passes.
"""
import sys, os, json, glob, struct, tempfile, collections, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read
import ctref

MAX_CODEC = 200_000
TIMEOUT = 600
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'work')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m


fc = _load('fpscipher', os.path.join(WORK, 'fpscipher.py'))
_T = fc.forward(bytes.fromhex('f5dc')); INV = [0] * 256
for _x, _y in enumerate(_T): INV[_y] = _x


# ---------------------------------------------------------------- truth from box scores

def h_tables(d):
    off, n = 0, len(d)
    while off + 8 <= n and d[off] == 0x02 and d[off + 1] == 0x65:
        count, rec = struct.unpack_from('<HH', d, off + 4)
        body = off + 8; end = body + count * rec
        if rec and end <= n:
            for i in range(count): yield rec, struct.unpack_from('<%dH' % (rec // 2), d, body + i * rec)
        off = end


def h_game(path):
    """-> (frozenset{(tid, runs)} x2, {tid: (w, l)}, {tid: set(pids)})"""
    side_tid, runs, wl, pids = {}, {}, {}, collections.defaultdict(set)
    rows = list(h_tables(safe_read(path, 1 << 20)))
    for rec, u in rows:
        pid, side = u[2] & 0x7fff, u[2] >> 15
        if pid < 100:
            side_tid[side] = pid
            if rec == 40: runs[pid] = u[3 + 13]
            if rec == 70: wl[pid] = (u[3 + 20], u[3 + 21])
    for rec, u in rows:
        pid, side = u[2] & 0x7fff, u[2] >> 15
        if pid >= 100 and rec in (40, 70) and side in side_tid and any(u[3:]): pids[side_tid[side]].add(pid)
    if len(side_tid) != 2 or len(runs) != 2: return None
    return frozenset(runs.items()), wl, pids


def day_truth(day_dir, prev_dir):
    have = lambda d: {os.path.basename(p) for p in glob.glob(f'{d}/MLBPA97.H*')} if d else set()
    games = collections.Counter(); w = collections.Counter(); l = collections.Counter(); credits = []
    for f in sorted(have(day_dir) - have(prev_dir)):
        g = h_game(f'{day_dir}/{f}')
        if g is None: continue
        games[g[0]] += 1
        for tid, (a, b) in g[1].items(): w[tid] += a; l[tid] += b
        credits.append(g[2])
    return games, w, l, credits


# ---------------------------------------------------------------- lane codec

def decode(codec, blob):
    with tempfile.TemporaryDirectory(prefix='asnref') as td:
        with open(f'{td}/in.bin', 'wb') as fh: fh.write(blob)
        J.jail(codec, td, ['decode', 'in.bin', 'out.json'], name='league.py', max_size=MAX_CODEC, timeout=TIMEOUT)
        return json.loads(J.read_file(td, 'out.json', 64 << 20))


def encode(codec, blob, doc):
    with tempfile.TemporaryDirectory(prefix='asnref') as td:
        with open(f'{td}/in.bin', 'wb') as fh: fh.write(blob)
        with open(f'{td}/edited.json', 'w') as fh: json.dump(doc, fh)
        J.jail(codec, td, ['encode', 'in.bin', 'edited.json', 'out.bin'], name='league.py', max_size=MAX_CODEC,
               timeout=TIMEOUT)
        return J.read_file(td, 'out.bin', 4 * len(blob) + (16 << 20))


def schema(doc):
    if not isinstance(doc, dict): fail('decode output is not an object')
    teams, games = doc.get('teams'), doc.get('games')
    if not isinstance(teams, list) or len(teams) != 28: fail('need exactly 28 teams')
    isint = lambda v: isinstance(v, int) and not isinstance(v, bool)
    for t in teams:
        if not (isinstance(t, dict) and isint(t.get('tid')) and 1 <= t['tid'] <= 28 and isinstance(t.get('name'), str)
                and 0 < len(t['name']) <= 40 and isint(t.get('w')) and isint(t.get('l')) and t['w'] >= 0 and t['l'] >= 0
                and isinstance(t.get('roster'), list) and all(isint(p) for p in t['roster'])):
            fail(f'bad team entry {str(t)[:200]}')
    if len({t['tid'] for t in teams}) != 28: fail('team ids not unique')
    if not isinstance(games, list) or not games: fail('no games')
    for g in games:
        if not (isinstance(g, dict) and isint(g.get('home')) and isint(g.get('away')) and 1 <= g['home'] <= 28
                and 1 <= g['away'] <= 28 and g['home'] != g['away'] and isinstance(g.get('played'), bool)
                and isint(g.get('hr')) and isint(g.get('ar'))):
            fail(f'bad game entry {str(g)[:200]}')
    return {t['tid']: t for t in teams}, games


def played_set(games):
    return collections.Counter(frozenset({(g['home'], g['hr']), (g['away'], g['ar'])}) for g in games if g['played'])


def consistency(tm, games, names):
    if sorted(t['name'] for t in tm.values()) != names: fail('team names differ from the known 28')
    per162 = collections.Counter()
    for g in games: per162[g['home']] += 1; per162[g['away']] += 1
    if len(games) < 2268 or any(per162[tid] != 162 for tid in tm): fail('schedule must list 162 games for every team')
    short = [tid for tid, t in tm.items() if len(set(t['roster'])) < 20]
    if short: fail(f'teams {short[:5]} have fewer than 20 roster ids')
    pl = [g for g in games if g['played']]
    sw, sl = sum(t['w'] for t in tm.values()), sum(t['l'] for t in tm.values())
    if not (sw == sl == len(pl)): fail(f'sum W {sw}, sum L {sl}, played games {len(pl)} differ')
    per = collections.Counter()
    for g in pl: per[g['home']] += 1; per[g['away']] += 1
    bad = [tid for tid, t in tm.items() if t['w'] + t['l'] != per[tid]]
    if bad: fail(f'teams {bad[:5]}: W+L != played games in the schedule')


# ---------------------------------------------------------------- edit test

def trusted_records(blob):
    with tempfile.TemporaryDirectory(prefix='asnref_ct') as td:
        ctx = ctref.Ctx(os.path.join(WORK, 'ctree.py'), td)
        dm = ctx.dump(blob)
        active, _ = ctref.check_dump(blob, dm, need_scan=False)
        return dm, active


def edit_test(codec, blob, doc):
    tm, games = schema(doc)
    ed = json.loads(json.dumps(doc))
    ts = sorted(ed['teams'], key=lambda t: t['tid'])
    a, b = ts[3], ts[5]
    old = a['name']; new = old[:-1] + ('Q' if old[-1] != 'Q' else 'Z')
    a['name'] = new; b['w'] += 3
    gi = next((i for i, g in enumerate(ed['games']) if g['played']), None)
    if gi is not None: ed['games'][gi]['hr'] += 1
    out = encode(codec, blob, ed)
    back = decode(codec, out)
    tm2, games2 = schema(back)
    want = {t['tid']: (t['name'], t['w'], t['l']) for t in ed['teams']}
    got = {t['tid']: (t['name'], t['w'], t['l']) for t in back['teams']}
    if want != got: fail('edit: decoded teams differ from the edited JSON: ' +
                         str([(k, want[k], got.get(k)) for k in want if want[k] != got.get(k)][:3]))
    key = lambda g: (g['home'], g['away'], g['played'], g['hr'] if g['played'] else 0, g['ar'] if g['played'] else 0)
    if [key(g) for g in ed['games']] != [key(g) for g in games2]: fail('edit: decoded games differ from the edited JSON')
    _, act0 = trusted_records(blob)
    _, act1 = trusted_records(out)
    diff = ctref.multiset(act0) - ctref.multiset(act1)
    if sum(diff.values()) > 8: fail(f"edit: {sum(diff.values())} records changed (expected <= 8)")
    nb = new.encode('latin-1')
    if not any(nb + b'\0' in bytes(INV[c] for c in rec) for _, rec in act1.values()):
        fail('edit: the new team name is not stored (enciphered) in any record')
    return True


# ---------------------------------------------------------------- driver

def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/league.py'
    hold, verbose = '--holdout' in sys.argv, '-v' in sys.argv
    if '--audit' in sys.argv:
        f = cfg['days'][len(cfg['days']) // 2]
        doc = decode(codec, safe_read(f'{f}/MLBPA97.ASN', 64 << 20))
        print('decoded', f.split('/')[-1], '- top-level keys:', list(doc)[:30])
        for t in sorted(doc['teams'], key=lambda t: t['tid']):
            print(' team', {k: (v if k != 'roster' else f'{len(v)} ids, e.g. {v[:6]}') for k, v in t.items()})
        print(' games:', len(doc['games']), 'played', sum(g['played'] for g in doc['games']))
        for g in doc['games'][:12]: print(' game', g)
        return
    days = cfg['holdout_days'] if hold else cfg['days']
    prev = cfg['holdout_prev'] if hold else None
    singles = cfg['holdout_files'] if hold else cfg['base_files']
    names = sorted(cfg['names'])
    ok_all, results, decoded = True, [], {}

    def record(name, ok, **kw):
        nonlocal ok_all
        ok_all &= ok
        results.append(dict(file=name, ok=ok, **({} if J.QUIET else kw)))

    for path in ([prev] if prev else []) + days:
        try:
            blob = safe_read(f'{path}/MLBPA97.ASN', 64 << 20)
            doc = decode(codec, blob); tm, games = schema(doc)
            decoded[path] = (blob, doc, tm, games)
        except Exception as e:
            if path != prev: record(path.split('/')[-1], False, error=J.err(e))
    for path in [prev] if prev else []:
        if path not in decoded: record('previous day', False, error='decode failed')
    order = ([prev] if prev else []) + days
    for i, path in enumerate(days):
        if path not in decoded: continue
        name = path.split('/')[-1]; blob, doc, tm, games = decoded[path]
        try:
            consistency(tm, games, names)
            pdir = order[order.index(path) - 1] if order.index(path) > 0 else None
            truth_g, tw, tl, credits = day_truth(path, pdir)
            info = {'played': sum(g['played'] for g in games), 'box_games': sum(truth_g.values())}
            if pdir in decoded:
                _, _, ptm, pgames = decoded[pdir]
                dw = {tid: tm[tid]['w'] - ptm[tid]['w'] for tid in tm}; dl = {tid: tm[tid]['l'] - ptm[tid]['l'] for tid in tm}
                badw = [tid for tid in tm if dw[tid] != tw[tid] or dl[tid] != tl[tid]]
                if badw: fail(f'W/L deltas disagree with box scores for teams {badw[:6]}')
                newp = played_set(games) - played_set(pgames)
                if newp != truth_g: fail(f'newly played games ({sum(newp.values())}) differ from the box scores ({sum(truth_g.values())})')
                ros = {tid: set(tm[tid]['roster']) | set(ptm[tid]['roster']) for tid in tm}
            else:
                ros = {tid: set(tm[tid]['roster']) for tid in tm}
            tot = hit = 0
            for cr in credits:
                for tid, ps in cr.items():
                    tot += len(ps); hit += len(ps & ros.get(tid, set()))
            info['roster_hit'] = f'{hit}/{tot}'
            if tot and hit < 0.99 * tot: fail(f'only {hit}/{tot} box-score player ids are on their team roster')
            if encode(codec, blob, doc) != blob: fail('encode(decode(x)) != x')
            if name in cfg.get('edit', []) and not hold: edit_test(codec, blob, doc); info['edit'] = True
            record(name, True, **info)
        except Exception as e:
            record(name, False, error=J.err(e))
    for path in singles:
        name = '/'.join(path.split('/')[-3:])
        try:
            blob = safe_read(path, 64 << 20); doc = decode(codec, blob); tm, games = schema(doc)
            consistency(tm, games, names)
            if encode(codec, blob, doc) != blob: fail('encode(decode(x)) != x')
            info = {'played': sum(g['played'] for g in games)}
            if os.path.basename(path) in cfg.get('edit', []) and not hold: edit_test(codec, blob, doc); info['edit'] = True
            record(name, True, **info)
        except Exception as e:
            record(name, False, error=J.err(e))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
