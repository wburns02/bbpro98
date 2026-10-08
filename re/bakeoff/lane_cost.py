#!/usr/bin/env python3
"""Bake-off tiers 2/3: per-round time, tokens and cost of a drive.sh lane. usage: lane_cost.py TARGET [LANE]
Claude rounds: the stream-json `result` record in glm_roundN.log (list-price cost as reported by the CLI; the runs
themselves are on the subscription). GLM (hive) rounds: the `usage` line drive.sh writes to run.log from kimi's
usage.record events, priced at Hive's glm-5.3-flash rate ($0.05 / M uncached in, $0.01 / M cache reads, $0.17 / M out)."""
import json, os, re, sys

T, LANE = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'code')
R = f'/home/will/bbpro98/re/targets/{T}/lanes/{LANE}/runs'
log = open(f'{R}/run.log').read()
rounds = re.split(r'(?m)^=== round ', log)[1:]
tot = {'secs': 0, 'in': 0, 'out': 0, 'usd': 0.0}
for blk in rounds:
    n = int(blk.split()[0])
    m = re.search(r'glm exit (\d+) secs (\d+)', blk)
    secs = int(m.group(2)) if m else None
    row = {'round': n, 'exit': int(m.group(1)) if m else None, 'secs': secs}
    u = re.search(r'(?m)^usage (.*)$', blk)
    if u:
        kv = dict(x.split('=') for x in u.group(1).split())
        i = sum(int(kv.get(k, 0)) for k in ('inputOther', 'inputCacheRead', 'inputCacheCreation'))
        o = int(kv.get('output', 0))
        row.update(model='glm', tin=i, tout=o, usd=round((i - int(kv.get('inputCacheRead', 0))) * 0.05e-6 + int(kv.get('inputCacheRead', 0)) * 0.01e-6 + o * 0.17e-6, 4))
    else:
        p = f'{R}/glm_round{n}.log'
        res = None
        if os.path.exists(p):
            for l in open(p, errors='replace'):
                if '"type":"result"' in l:
                    try:
                        d = json.loads(l)
                        if d.get('type') == 'result': res = d
                    except ValueError: pass
        if res:
            us = res.get('usage', {})
            i = sum(us.get(k, 0) for k in ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
            row.update(model='claude', tin=i, tout=us.get('output_tokens', 0), usd=round(res.get('total_cost_usd', 0), 3),
                       turns=res.get('num_turns'))
    ref = [l for l in blk.splitlines() if l.startswith(('PASS', 'FAIL', 'HOLDOUT', 'VERDICT', 'DONE', 'records'))]
    row['ref'] = ref[-3:]
    for k, kk in (('secs', 'secs'), ('in', 'tin'), ('out', 'tout'), ('usd', 'usd')): tot[k] += row.get(kk) or 0
    print(json.dumps(row))
print(json.dumps({'target': T, 'total': tot, 'status': open(f'{R}/STATUS').read().strip()}))
