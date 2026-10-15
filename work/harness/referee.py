#!/usr/bin/env python3
"""The dynasty referee: judge a multi-season soak run against fixed bands.

    python3 work/harness/referee.py RUNLOG OUTDIR --stem 30L2025 [--bands F.json] [--json] [--db PATH]

RUNLOG is the JSON-lines log seasonloop.py / ingame.py print (runreport.parse reads it). OUTDIR is the plan's shot dir:
season k's end-of-season files are OUTDIR/complete_<k>/Stats/<STEM>.DAT (k = 0, 1, ...). Prints one table row per
season and `REFEREE PASS` or `REFEREE FAIL: reason; reason`; exits 0, 1, or 2 on bad input (unreadable log, no OUTDIR,
bad bands file, no Lahman season for a real:YYYY reference).

Season k starts at the log's `{"demographics": k, ...}` object (a string value such as "loaded" is the pre-run baseline,
not a season; neither is the last demographics object when no round or season object follows it, the measurement after
the final offseason). The round and season objects after it belong to season k. Bands (--bands overrides by key):

    age_drift    max over seasons of |mean_age(k) - mean_age(first)|
    roster_min   smallest roster_min seen in the demographics objects must be >= this
    pitchers_min same for pitchers_min
    rate_tol     each season's BA, HR/AB and BB/AB within this fraction of the reference
    rate_ref     "first" (the first season with a DAT) or "real:YYYY" (Lahman YYYY, erarates.real_totals)
    seasons      completed seasons (a season object with done true) must be >= this

Also failed: a season object with done false, a season that played fewer games than the largest "of" its rounds showed,
a missing or unreadable DAT, and crash evidence (a CRASH line in bbtrace*.log under OUTDIR or OUTDIR/complete_*, or a
log object with a "crash" key). The game's modules are imported only when a DAT is read (erarates.load_lines).
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import struct
import sys

import erarates
import runreport

DEFAULT_BANDS = {'age_drift': 0.3, 'roster_min': 36, 'pitchers_min': 15, 'rate_tol': 0.10, 'rate_ref': 'first',
                 'seasons': 10}
RATES = erarates.CHECKED
EPS = 1e-9
MAX_CRASH_LINES = 200


def merge_bands(bands):
    """DEFAULT_BANDS with `bands` laid over it, checked: ValueError for an unknown key, a non-number, or a rate_ref
    that is neither "first" nor "real:YYYY"."""
    out = dict(DEFAULT_BANDS)
    for k, v in (bands or {}).items():
        if k not in DEFAULT_BANDS:
            raise ValueError('bands: unknown key %s (use %s)' % (k, ', '.join(DEFAULT_BANDS)))
        out[k] = v
    for k, v in out.items():
        if k == 'rate_ref':
            if not isinstance(v, str) or not re.fullmatch(r'first|real:\d{4}', v):
                raise ValueError('bands: rate_ref %r is not "first" or "real:YYYY"' % (v,))
        elif not runreport.is_num(v) or v < 0:
            raise ValueError('bands: %s %r is not a non-negative number' % (k, v))
    return out


def load_bands(path):
    """merge_bands of the JSON object in `path` (None: the defaults). OSError or ValueError on a bad file."""
    if path is None:
        return merge_bands({})
    with open(path, encoding='utf-8') as fh:
        got = json.load(fh)
    if not isinstance(got, dict):
        raise ValueError('bands: %s is not a JSON object' % path)
    return merge_bands(got)


def split(lines):
    """[segment] in log order, one per demographics object plus a leading one for objects before any: {'demo': the
    demographics object or None, 'base': True for the pre-run baseline (demographics "loaded"), 'of': the largest
    "of" of its round objects or None, 'objs': its season objects (those with "season" and "done")}."""
    segs, cur = [], None
    for o in lines:
        if not isinstance(o, dict):
            continue
        if 'demographics' in o:
            cur = {'demo': o, 'base': o['demographics'] == 'loaded', 'of': None, 'objs': []}
            segs.append(cur)
            continue
        if cur is None:
            cur = {'demo': None, 'base': True, 'of': None, 'objs': []}
            segs.append(cur)
        if 'round' in o and runreport.is_num(o.get('of')):
            cur['of'] = max(cur['of'] or 0, o['of'])
        if 'season' in o and 'done' in o:
            cur['objs'].append(o)
    return segs


def season_segments(lines):
    """The segments that are seasons: split() minus the baseline and minus a trailing measurement-only segment (no round
    and no season object) when an earlier season has season objects."""
    segs = [s for s in split(lines) if not s['base']]
    if len(segs) > 1 and not segs[-1]['objs'] and segs[-1]['of'] is None and any(s['objs'] for s in segs[:-1]):
        segs.pop()
    return segs


def find_crashes(outdir, limit=MAX_CRASH_LINES):
    """Lines containing CRASH in OUTDIR/bbtrace*.log and OUTDIR/complete_*/bbtrace*.log, as 'file: line' (at most
    `limit`; the trace files reach 150 MB, so they are read line by line)."""
    out = []
    paths = sorted(glob.glob(os.path.join(outdir, 'bbtrace*.log')) + glob.glob(os.path.join(outdir, 'complete_*', 'bbtrace*.log')))
    for path in paths:
        try:
            with open(path, 'rb') as fh:
                for line in fh:
                    if b'CRASH' in line:
                        out.append('%s: %s' % (os.path.relpath(path, outdir), line.decode('latin-1').strip()[:160]))
                        if len(out) >= limit:
                            return out
        except OSError:
            continue
    return out


def judge(lines, season_rates, crashes, bands, ref=None):
    """{'verdict': 'PASS' | 'FAIL', 'fails': [str], 'rows': [one dict per season]} from parsed log objects, the per
    season erarates.rates dicts (None for a season whose DAT is missing, a fail), crash evidence lines and the bands
    (merge_bands). `ref` is the reference rates dict when rate_ref is "real:YYYY" (the caller reads the database; this
    function touches nothing). Pure. A row has k, year, mean_age, drift, roster_min, pitchers_min, BA, HR/AB, BB/AB,
    played, of, done."""
    b = merge_bands(bands)
    segs = season_segments(lines)
    season_rates = list(season_rates or [])
    n = max(len(segs), len(season_rates))
    fails, rows = [], []
    first_age = next((s['demo'].get('mean_age') for s in segs
                      if runreport.is_num(s['demo'].get('mean_age'))), None)
    for k in range(n):
        seg = segs[k] if k < len(segs) else {'demo': {}, 'of': None, 'objs': []}
        demo = seg['demo'] or {}
        age = demo.get('mean_age') if runreport.is_num(demo.get('mean_age')) else None
        objs = seg['objs']
        played = next((o['played'] for o in reversed(objs) if runreport.is_num(o.get('played'))), None)
        r = season_rates[k] if k < len(season_rates) else None
        row = {'k': k, 'year': demo.get('year'), 'mean_age': age,
               'drift': round(age - first_age, 4) if age is not None and first_age is not None else None,
               'roster_min': demo.get('roster_min') if runreport.is_num(demo.get('roster_min')) else None,
               'pitchers_min': demo.get('pitchers_min') if runreport.is_num(demo.get('pitchers_min')) else None,
               'played': played, 'of': seg['of'],
               'done': (None if not objs else all(o.get('done') is True for o in objs))}
        for name in erarates.RATES[:3]:
            row[name] = r.get(name) if r else None
        rows.append(row)
        if r is None:
            fails.append('season %d: no readable Stats DAT' % k)
        for o in objs:
            if o.get('done') is not True:
                fails.append('season %d: %s did not finish (done false)' % (k, o.get('season')))
            elif seg['of'] is not None and runreport.is_num(o.get('played')) and o['played'] < seg['of']:
                fails.append('season %d: played %s of %s games' % (k, o['played'], seg['of']))
    # the pre-run baseline's season (a loaded mid-season association) is judged for missed games too
    for s in split(lines):
        if s['base']:
            for o in s['objs']:
                if o.get('done') is not True:
                    fails.append('baseline season %s did not finish (done false)' % o.get('season'))
                elif s['of'] is not None and runreport.is_num(o.get('played')) and o['played'] < s['of']:
                    fails.append('baseline season %s: played %s of %s games' % (o.get('season'), o['played'], s['of']))
    done = sum(1 for s in segs if any(o.get('done') is True for o in s['objs']))
    if done < b['seasons']:
        fails.append('seasons: %d completed, need %d' % (done, b['seasons']))
    if rows:
        ages = [r for r in rows if r['drift'] is not None]
        if not ages:
            fails.append('age drift: no mean_age in the log')
        else:
            worst = max(ages, key=lambda r: abs(r['drift']))
            if abs(worst['drift']) > b['age_drift'] + EPS:
                fails.append('age drift %+.2f in season %d (mean age %.2f vs %.2f first), band %g' % (
                    worst['drift'], worst['k'], worst['mean_age'], first_age, b['age_drift']))
        for key in ('roster_min', 'pitchers_min'):
            seen = [r for r in rows if r[key] is not None]
            if not seen:
                fails.append('%s: none in the log' % key)
                continue
            low = min(seen, key=lambda r: (r[key], r['k']))
            if low[key] < b[key]:
                fails.append('%s %s in season %d, band %g' % (key, low[key], low['k'], b[key]))
    base_i = next((i for i, r in enumerate(season_rates) if r), None)
    if b['rate_ref'] == 'first':
        want, skip = (season_rates[base_i] if base_i is not None else None), base_i
    else:
        want, skip = ref, None
    for k, r in enumerate(season_rates):
        if not r or k == skip:
            continue
        if want is None or not any(v is not None for v in want.values()):
            fails.append('rates: no %s reference' % b['rate_ref'])
            break
        cmp = erarates.compare(r, want)
        ok, misses = erarates.within(cmp, b['rate_tol'], RATES)
        if not ok:
            fails.append('season %d: %s outside %g%% of %s' % (k, ', '.join(
                '%s x%s' % (m, '%.2f' % cmp[m]['ratio'] if cmp[m]['ratio'] is not None else '?') for m in misses),
                b['rate_tol'] * 100, b['rate_ref']))
    found = list(crashes or []) + ['log: %s' % json.dumps(o)[:160] for o in lines
                                   if isinstance(o, dict) and o.get('crash') not in (None, False)]
    if found:
        fails.append('crash evidence, %d line(s): %s' % (len(found), found[0]))
    return {'verdict': 'FAIL' if fails else 'PASS', 'fails': fails, 'rows': rows}


ROW = '%6s  %5s  %8s  %6s  %10s  %12s  %6s  %6s  %6s  %11s'


def _cell(v, fmt='%s'):
    return '-' if v is None else fmt % v


def _rate(v):
    return '-' if v is None else erarates.fmt_rate(v)


def render(result):
    """The table, then REFEREE PASS or REFEREE FAIL: reason; reason."""
    out = [ROW % ('season', 'year', 'mean age', 'drift', 'roster min', 'pitchers min', 'BA', 'HR/AB', 'BB/AB', 'games')]
    for r in result['rows']:
        games = '-' if r['played'] is None and r['of'] is None else '%s/%s' % (_cell(r['played']), _cell(r['of']))
        out.append(ROW % (r['k'], _cell(r['year']), _cell(r['mean_age'], '%.2f'), _cell(r['drift'], '%+.2f'),
                          _cell(r['roster_min']), _cell(r['pitchers_min']), _rate(r['BA']), _rate(r['HR/AB']),
                          _rate(r['BB/AB']), games))
    out.append('REFEREE PASS' if result['verdict'] == 'PASS' else 'REFEREE FAIL: ' + '; '.join(result['fails']))
    return '\n'.join(out)


def find_dat(outdir, k, stem):
    """OUTDIR/complete_<k>/Stats/<STEM>.DAT, matched case-insensitively; None when absent."""
    d = os.path.join(outdir, 'complete_%d' % k, 'Stats')
    try:
        names = os.listdir(d)
    except OSError:
        return None
    hit = next((n for n in sorted(names) if n.lower() == stem.lower() + '.dat'), None)
    return os.path.join(d, hit) if hit else None


def evaluate(text, outdir, stem, bands=None, db=erarates.DB, load=None, connect=None):
    """judge() on a run: parses the log text, reads each season's DAT (load(path) -> gamedata.season_lines output),
    collects crash evidence from OUTDIR and, for a real:YYYY reference, the Lahman rates of YYYY (connect(db) -> sqlite
    connection). Both are injectable; the defaults are erarates.load_lines and erarates.open_db. ValueError when the
    real season is missing."""
    load = load or erarates.load_lines
    connect = connect or erarates.open_db
    b = merge_bands(bands)
    lines = runreport.parse(text)
    n = len(season_segments(lines))
    while os.path.isdir(os.path.join(outdir, 'complete_%d' % n)):
        n += 1
    got = []
    for k in range(n):
        dat = find_dat(outdir, k, stem)
        try:
            got.append(erarates.rates(erarates.sim_totals(load(dat))) if dat else None)
        except (OSError, ValueError, KeyError, IndexError, TypeError, struct.error):
            got.append(None)
    ref = None
    if b['rate_ref'] != 'first':
        year = int(b['rate_ref'].split(':')[1])
        real = erarates.real_totals(connect(db), year)
        if not real['ab']:
            raise ValueError('no Lahman teams for %d' % year)
        ref = erarates.rates(real)
    return judge(lines, got, find_crashes(outdir), b, ref)


def main(argv=None, load=None, connect=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('runlog', help='the run log (JSON lines)')
    ap.add_argument('outdir', help="the plan's shot dir holding complete_<k>/Stats/")
    ap.add_argument('--stem', required=True, help='association stem, e.g. 30L2025')
    ap.add_argument('--bands', help='JSON file overriding the default bands by key')
    ap.add_argument('--json', action='store_true', help='print the result as one JSON object')
    ap.add_argument('--db', default=erarates.DB, help='Lahman database, read only (for a real:YYYY rate_ref)')
    a = ap.parse_args(argv)
    try:
        with open(a.runlog, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
        if not os.path.isdir(a.outdir):
            raise ValueError('%s: not a directory' % a.outdir)
        result = evaluate(text, a.outdir, a.stem, load_bands(a.bands), a.db, load, connect)
    except (OSError, ValueError, sqlite3.Error) as e:
        print('referee: %s' % e, file=sys.stderr)
        return 2
    print(json.dumps(result) if a.json else render(result))
    return 0 if result['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
