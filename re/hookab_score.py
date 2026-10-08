#!/usr/bin/env python3
"""Score the roadmap #9 hook referee arms (re/hookab.sh). Per arm: season (scope 1) batting SB/CS/AB summed over
players, minus the snapshot the arm started from, plus the steal-mod call counts from its bbtrace MOD lines.
Predictions (fixed before the run): pass ~= off (the trampoline is behavior-neutral), zero << off (no steal attempts),
max >> off (every possible steal attempted). usage: hookab_score.py [ROOT]"""
import json, os, re, subprocess, sys, tempfile
ROOT = sys.argv[1] if len(sys.argv) > 1 else '/mnt/nvme/bbpro98/re/hookab'
BASE = '/mnt/nvme/bbpro98/re/asnseq/day10'
STATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'stats.py')

def totals(statsdir):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([sys.executable, STATS, 'decode', f'{statsdir}/mlbpa97.DAT', f'{td}/o.json'], check=True)
        doc = json.load(open(f'{td}/o.json'))
    t = {'ab': 0, 'sb': 0, 'cs': 0, 'r': 0, 'g': 0}
    for r in doc['records']:
        if r['table'] == 'batting' and r['scope'] == 1 and r['pid'] >= 100:
            for k in t: t[k] += r['fields'][k]
    return t

base = totals(f'{BASE}/Stats')
res = {}
for arm in ('off', 'pass', 'zero', 'max'):
    d = f'{ROOT}/{arm}'
    if not os.path.exists(f'{d}/Stats/mlbpa97.DAT'): continue
    t = totals(f'{d}/Stats'); delta = {k: t[k] - base[k] for k in t}
    mods = open(f'{d}/mod_lines.txt').read() if os.path.exists(f'{d}/mod_lines.txt') else ''
    calls = [int(x) for x in re.findall(r'calls=(\d+)', mods)]
    days = open(f'{d}/sim.log').read().count('done=True') if os.path.exists(f'{d}/sim.log') else 0
    res[arm] = dict(delta, days=days, calls=max(calls) if calls else 0, applied=mods.count('applied 1 hooks'))
    print(arm, json.dumps(res[arm]))
checks = []
def ck(name, ok): checks.append((name, bool(ok))); print(('PASS ' if ok else 'FAIL ') + name)
if all(a in res for a in ('off', 'pass', 'zero', 'max')):
    o, p, z, m = res['off'], res['pass'], res['zero'], res['max']
    ck('all arms simmed every day', len({o['days'], p['days'], z['days'], m['days']}) == 1 and o['days'] > 0)
    ck('off arm loaded no mod (calls 0)', o['calls'] == 0 and o['applied'] == 0)
    ck('mod arms hooked FastSim and saw calls', all(a['applied'] > 0 and a['calls'] > 0 for a in (p, z, m)))
    ck('games played comparably (AB within 5% of off)', all(abs(a['ab'] - o['ab']) <= 0.05 * o['ab'] for a in (p, z, m)))
    ck('pass ~= off (SB within 35%)', abs(p['sb'] - o['sb']) <= 0.35 * max(o['sb'], 1))
    ck('zero: SB <= 10% of off', z['sb'] <= 0.10 * o['sb'])
    ck('max: SB >= 3x off', m['sb'] >= 3 * o['sb'])
print('PASS' if checks and all(ok for _, ok in checks) else 'FAIL')
