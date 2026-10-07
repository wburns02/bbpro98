#!/usr/bin/env python3
"""Replace the unreliable params=N field in each spec draft title with the real
decompile signature (params= counted PB-getter calls, not arguments).
Writes re/spec/FUN_<addr>.md in place. Idempotent."""
import re, glob

t = open('/mnt/nvme/bbpro98/index/FastSim/_all.c', errors='replace').read()
sigs = {}
for p in re.split(r'^// ==== ', t, flags=re.M)[1:]:
    tk = p.split()
    if not tk: continue
    fn = tk[1] if len(tk) > 1 and tk[1].startswith('FUN_') else tk[0]
    # signature = lines up to the first '{'
    body = p.split('\n', 1)[1] if '\n' in p else ''
    m = re.match(r'\s*(.*?)\{', body, flags=re.S)
    if m:
        sig = ' '.join(m.group(1).split())
        sigs[fn] = sig

n = 0
for path in sorted(glob.glob('/mnt/nvme/bbpro98/re/spec/FUN_*.md')):
    txt = open(path).read()
    fn = re.search(r'(FUN_[0-9a-f]+)', path).group(1)
    newsig = sigs.get(fn)
    if not newsig: continue
    def repl(m):
        return f"# {fn} ({newsig})"
    new = re.sub(rf'# {fn} \([^)]*\) params=\d+', repl, txt, count=1)
    if new != txt:
        open(path, 'w').write(new); n += 1
print('fixed', n, 'of', len(sigs), 'sigs known')
