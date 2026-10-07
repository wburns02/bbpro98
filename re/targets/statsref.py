"""Referee for the stats-database (mlbpa97.DAT) semantic codec. Claude-owned: GLM must not edit it.

usage: python3 statsref.py <target_dir> <lane_dir> [-v]         score <lane>/stats.py on the visible days
       python3 statsref.py <target_dir> <lane_dir> --holdout     same checks on sim days the lane never sees
       python3 statsref.py <target_dir> <lane_dir> --audit X     text summary of one decode for the audit

Contract for <lane>/stats.py (runs in a bwrap jail: no network, no files but its tempdir):
  python3 stats.py decode in.bin out.json
      {"records": [{"off": payload offset of the c-tree record, "scope": int, "pid": int (player or team id),
                    "kind": str, "period": str, "fields": {name: int, ...}, ...any other keys...}
                   one per stat record (every active record whose payload is 22/36/40/70/150 bytes of u16 words
                   with word0 in {0,1,2,3,16,17} and word1 == 2)],
       ...any other keys...}
      "fields" lists words 3.. of the payload in order, one name per word (the values must equal the words).
      kind "bat" = a 40-byte batting line, named exactly BAT below; kind "pit" = a 70-byte pitching line with
      PIT_REQUIRED at those word positions. period "season" / "career" = this season's / the career line.
  python3 stats.py encode in.bin edited.json out.bin
      rebuilds the file from in.bin with every record's fields taken from edited.json (matched by "off");
      encode(x, decode(x)) == x byte for byte.
Checks per file: coverage and word fidelity; names (BAT/PIT_REQUIRED, and at most 25% generic names like f12 overall); for each consecutive day pair, every "bat"/"pit" line labeled
season or career changes by exactly the sum of that day's box-score rows for its pid (and there is at least one
season and one career line for every player in a box score); every record that changes between the two days has a
kind and period other than "unknown"; round trip; on the "edit" files: +2 HR on a season (else career) batting line, +1 W on
a season (else career) pitching line, +1 to the first field of a 22/36/150-byte record, encode, and require the decode to show
exactly those edits, the trusted c-tree codec to read the new words at those records, the file length and record
count unchanged and no stray bytes (asnref.stray_bytes).
PASS = every visible check passes.
"""
import sys, os, json, glob, struct, tempfile, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jailutil as J
from jailutil import fail, safe_read
import asnref as A

MAX_CODEC = 200_000
TIMEOUT = 900
LENS = {22, 36, 40, 70, 150}; SCOPES = {0, 1, 2, 3, 16, 17}
BAT = ['ab', 'h1b', 'h2b', 'h3b', 'hr', 'rbi', 'bb', 'so', 'ibb', 'hbp', 'sh', 'sf', 'g', 'r', 'sb', 'cs', 'gidp']
PIT_REQUIRED = {18: 'outs', 20: 'w', 21: 'l', 26: 'er'}


def trusted_stats(blob):
    dm, act = A.trusted_records(blob)
    out = {}
    for off, (m, p) in act.items():
        if len(p) in LENS:
            u = struct.unpack('<%dH' % (len(p) // 2), p)
            if u[0] in SCOPES and u[1] == 2: out[off] = u
    return dm, out


def box_rows(day_dir, prev_dir):
    have = lambda d: {os.path.basename(p) for p in glob.glob(f'{d}/MLBPA97.H*')} if d else set()
    tot = {40: collections.defaultdict(lambda: [0] * 17), 70: collections.defaultdict(lambda: [0] * 32)}
    for f in sorted(have(day_dir) - have(prev_dir)):
        for rec, u in A.h_tables(safe_read(f'{day_dir}/{f}', 1 << 20)):
            pid = u[2] & 0x7fff
            if rec in tot:
                row = tot[rec][pid]
                for i in range(len(row)): row[i] += u[3 + i]
    return tot


def decode(codec, blob):
    with tempfile.TemporaryDirectory(prefix='statsref') as td:
        with open(f'{td}/in.bin', 'wb') as fh: fh.write(blob)
        J.jail(codec, td, ['decode', 'in.bin', 'out.json'], name='stats.py', max_size=MAX_CODEC, timeout=TIMEOUT)
        return json.loads(J.read_file(td, 'out.json', 256 << 20))


def encode(codec, blob, doc):
    with tempfile.TemporaryDirectory(prefix='statsref') as td:
        with open(f'{td}/in.bin', 'wb') as fh: fh.write(blob)
        with open(f'{td}/edited.json', 'w') as fh: json.dump(doc, fh)
        J.jail(codec, td, ['encode', 'in.bin', 'edited.json', 'out.bin'], name='stats.py', max_size=MAX_CODEC,
               timeout=TIMEOUT)
        return J.read_file(td, 'out.bin', 4 * len(blob) + (16 << 20))


def validate(doc, truth):
    """truth = {off: words}. Returns {off: record} after checking coverage, fidelity and names."""
    if not isinstance(doc, dict) or not isinstance(doc.get('records'), list): fail('decode output has no "records" list')
    isint = lambda v: isinstance(v, int) and not isinstance(v, bool)
    by = {}
    for r in doc['records']:
        if not (isinstance(r, dict) and isint(r.get('off')) and isint(r.get('scope')) and isint(r.get('pid'))
                and isinstance(r.get('kind'), str) and isinstance(r.get('period'), str)
                and isinstance(r.get('fields'), dict)):
            fail(f'bad record entry {str(r)[:200]}')
        if r['off'] in by: fail(f'record {r["off"]} listed twice')
        by[r['off']] = r
    missing = set(truth) - set(by); extra = set(by) - set(truth)
    if missing: fail(f'{len(missing)} stat records not listed, e.g. offsets {sorted(missing)[:3]}')
    if extra: fail(f'{len(extra)} listed records are not stat records, e.g. offsets {sorted(extra)[:3]}')
    import re
    generic = re.compile(r'^(f|w|c|x|u|v|word|col|field|unk|unknown|val|value|stat|s)_?\d+$', re.I)
    names_all = [n for r in by.values() for n in r['fields']]
    lazy = sum(1 for n in names_all if generic.match(n) or not n.strip())
    if lazy > 0.25 * max(1, len(names_all)): fail(f'{lazy}/{len(names_all)} field names are generic (f12, word3, ...); name what the fields mean')
    for off, r in by.items():
        u = truth[off]; vals = list(r['fields'].values())
        if r['scope'] != u[0] or r['pid'] != u[2]: fail(f'record {off}: scope/pid differ from the payload')
        if vals != list(u[3:]): fail(f'record {off}: fields do not equal payload words 3.. in order')
        names = list(r['fields'])
        if r['kind'] == 'bat' and (len(u) * 2 != 40 or names != BAT): fail(f'record {off}: a "bat" line must be 40 bytes named {BAT}')
        if r['kind'] == 'pit':
            if len(u) * 2 != 70: fail(f'record {off}: a "pit" line must be 70 bytes')
            for i, nm in PIT_REQUIRED.items():
                if names[i] != nm: fail(f'record {off}: pitching field {i} must be named {nm!r}')
    return by


def day_pair(by, prev_by, tot):
    """season/career bat/pit lines must change by exactly the box-score rows; changed records must be labeled."""
    key = lambda r: (r['scope'], r['kind'], r['period'], r['pid'], len(r['fields']))
    cur = collections.defaultdict(list); old = collections.defaultdict(list)
    for r in by.values(): cur[key(r)].append(r)
    for r in prev_by.values(): old[key(r)].append(r)
    seen = {('bat', 'season'): set(), ('bat', 'career'): set(), ('pit', 'season'): set(), ('pit', 'career'): set()}
    for k, rs in cur.items():
        sc, kind, period, pid, n = k
        if kind not in ('bat', 'pit') or period not in ('season', 'career'): continue
        if len(rs) != 1 or len(old.get(k, [])) > 1: fail(f'{len(rs)} {kind}/{period} lines for scope {sc} pid {pid}')
        now = list(rs[0]['fields'].values())
        before = list(old[k][0]['fields'].values()) if old.get(k) else [0] * len(now)
        box = tot[40 if kind == 'bat' else 70].get(pid, [0] * len(now))
        if [a - b for a, b in zip(now, before)] != box:
            fail(f'{kind}/{period} line scope {sc} pid {pid}: day change differs from the box scores')
        seen[(kind, period)].add(pid)
    for (kind, period), pids in seen.items():
        need = {p for p in tot[40 if kind == 'bat' else 70] if period == 'season' or p >= 100}   # teams have no career line
        if need - pids: fail(f'{len(need - pids)} players in the box scores have no {kind}/{period} line')
    prev_words = collections.Counter((key(r), tuple(r['fields'].values())) for r in prev_by.values())
    unlabeled = [r['off'] for r in by.values() if (key(r), tuple(r['fields'].values())) not in prev_words
                 and ('unknown' in (r['kind'], r['period']) or not r['kind'] or not r['period'])]
    if unlabeled: fail(f'{len(unlabeled)} records changed today but are labeled unknown, e.g. offsets {unlabeled[:3]}')


def edit_test(codec, blob, doc, truth):
    ed = json.loads(json.dumps(doc))
    recs = ed['records']
    pick = lambda f: next((r for r in recs if f(r)), None)
    a = pick(lambda r: r['kind'] == 'bat' and r['period'] == 'season') or pick(lambda r: r['kind'] == 'bat' and r['period'] == 'career') or pick(lambda r: r['kind'] == 'bat')
    b = pick(lambda r: r['kind'] == 'pit' and r['period'] == 'season') or pick(lambda r: r['kind'] == 'pit' and r['period'] == 'career') or pick(lambda r: r['kind'] == 'pit')
    c = pick(lambda r: len(r['fields']) in (8, 15, 72) and r['kind'] not in ('bat', 'pit'))
    if not (a and b and c): fail('edit: need a batting line, a pitching line and a 22/36/150-byte record')
    a['fields']['hr'] += 2; b['fields']['w'] += 1
    k0 = next(iter(c['fields'])); c['fields'][k0] += 1
    out = encode(codec, blob, ed)
    dm1, t1 = trusted_stats(out)
    if len(t1) != len(truth): fail(f'edit: stat record count {len(truth)} -> {len(t1)}')
    for r in (a, b, c):
        if r['off'] not in t1 or list(t1[r['off']][3:]) != list(r['fields'].values()):
            fail(f'edit: the trusted reader does not see the edit at record {r["off"]}')
    changed = [o for o in truth if t1.get(o) != truth[o]]
    if sorted(changed) != sorted({a['off'], b['off'], c['off']}): fail(f'edit: {len(changed)} records changed, expected 3')
    A.stray_bytes(blob, out, dm1)
    back = validate(decode(codec, out), t1)
    want = {r['off']: r['fields'] for r in recs}
    if any(back[o]['fields'] != want[o] for o in want): fail('edit: decode of the edited file differs from the edited JSON')


def main():
    tdir, lane = sys.argv[1], sys.argv[2]
    cfg = json.load(open(f'{tdir}/files.json'))
    codec = f'{lane}/stats.py'
    hold = '--holdout' in sys.argv
    if '--audit' in sys.argv:
        f = cfg['days'][len(cfg['days']) // 2]
        doc = decode(codec, safe_read(f'{f}/mlbpa97.DAT', 64 << 20))
        recs = doc.get('records', [])
        print('decoded', f.split('/')[-1], '- top-level keys:', list(doc)[:30], '-', len(recs), 'records')
        groups = collections.defaultdict(list)
        for r in recs: groups[(r.get('scope'), r.get('kind'), r.get('period'), len(r.get('fields', {})))].append(r)
        for k, rs in sorted(groups.items(), key=lambda x: str(x[0])):
            print(' group scope/kind/period/nfields', k, 'count', len(rs))
            for r in rs[:2]: print('   ', {x: y for x, y in r.items() if x != 'fields'}, 'fields', r.get('fields'))
        other = {k: v for k, v in doc.items() if k != 'records'}
        print(' other keys:', json.dumps(other)[:3000])
        return
    days = cfg['holdout_days'] if hold else cfg['days']
    prev = cfg['holdout_prev'] if hold else None
    singles = cfg['holdout_files'] if hold else cfg['base_files']
    ok_all, results, dec = True, [], {}

    def record(name, ok, **kw):
        nonlocal ok_all
        ok_all &= ok
        results.append(dict(file=name, ok=ok, **({} if J.QUIET else kw)))

    order = ([prev] if prev else []) + days
    for path in order:
        try:
            blob = safe_read(f'{path}/mlbpa97.DAT', 64 << 20)
            _, truth = trusted_stats(blob)
            doc = decode(codec, blob)
            dec[path] = (blob, doc, truth, validate(doc, truth))
        except Exception as e:
            if path not in days: record('previous day', False)
            else: record(path.split('/')[-1], False, error=J.err(e))
    for i, path in enumerate(order):
        if path not in days or path not in dec: continue
        name = path.split('/')[-1]; blob, doc, truth, by = dec[path]
        try:
            pdir = order[i - 1] if i > 0 else None
            tot = box_rows(path, pdir)
            info = {'records': len(by), 'box_batters': len(tot[40]), 'box_pitchers': len(tot[70])}
            if pdir in dec: day_pair(by, dec[pdir][3], tot); info['day_pair'] = True
            if encode(codec, blob, doc) != blob: fail('encode(decode(x)) != x')
            if name in cfg.get('edit', []) and not hold: edit_test(codec, blob, doc, truth); info['edit'] = True
            record(name, True, **info)
        except Exception as e:
            record(name, False, error=J.err(e))
    for path in singles:
        name = '/'.join(path.split('/')[-2:])
        try:
            blob = safe_read(path, 64 << 20); _, truth = trusted_stats(blob)
            doc = decode(codec, blob); by = validate(doc, truth)
            if encode(codec, blob, doc) != blob: fail('encode(decode(x)) != x')
            info = {'records': len(by)}
            if os.path.basename(path) in cfg.get('edit', []) and not hold: edit_test(codec, blob, doc, truth); info['edit'] = True
            record(name, True, **info)
        except Exception as e:
            record(name, False, error=J.err(e))
    for r in results: print(' ', json.dumps(r))
    print('PASS' if ok_all and results else 'FAIL')
    sys.exit(0 if ok_all and results else 1)


if __name__ == '__main__':
    main()
