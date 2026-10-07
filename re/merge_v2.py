#!/usr/bin/env python3
"""Merge RULES v2 text into draft bodies: replace the flagged rule's text span
with the v2 rule (prefix 'replaces rule N:' stripped), keep CORRECTIONS, drop
the RULES v2 appendix. Conservative: only merges v2 rules whose pass-3 verdict
file says RESOLVED; rules it cannot locate are left in place and reported."""
import re, glob, os

AUD = '/mnt/nvme/bbpro98/re/spec_v2_audit'
merged = skipped = 0
for v2path in sorted(glob.glob('/mnt/nvme/bbpro98/re/spec_v2/*.v2.txt')):
    fn = os.path.basename(v2path).replace('.v2.txt', '')
    av = f'{AUD}/{fn}.txt'
    if os.path.exists(av) and not open(av).read().startswith('VERDICT: RESOLVED'):
        print('SKIP (not RESOLVED):', fn); skipped += 1; continue
    dp = f'/mnt/nvme/bbpro98/re/spec/{fn}.md'
    s = open(dp).read()
    if 'RULES v2 (corrections applied' not in s:
        print('SKIP (no appendix):', fn); skipped += 1; continue
    body, _, appendix = s.partition('\nRULES v2 (corrections applied')
    v2 = appendix.split('\n', 1)[1] if '\n' in appendix else ''
    # parse v2 rules: 'replaces rule X:' blocks
    blocks = []
    cur = None
    for line in v2.split('\n'):
        m = re.match(r'\s*replaces (?:rule )?([0-9]+(?:\.[0-9]+)?)\s*:\s*(.*)', line)
        if m:
            cur = {'id': m.group(1), 'text': [m.group(2)]}
            blocks.append(cur)
        elif cur is not None and line.strip():
            cur['text'].append(line)
    if not blocks:
        print('SKIP (no replaceable rules):', fn); skipped += 1; continue
    lines = body.split('\n')
    out = list(lines)
    used = []
    for b in blocks:
        rid = re.escape(b['id'])
        # find the rule start: optional bold marker, id, then ) or . or space
        pat = re.compile(rf'^\s*(?:\*\*)?\s*{rid}(?:\)|\.|\s)\s*')
        start = next((i for i, l in enumerate(lines) if pat.match(l) and lines[i].strip() != ''), None)
        if start is None:
            print(f'  UNLOCATED rule {b["id"]} in {fn}'); continue
        # rule span: until next rule header at same-or-shallow level or section header
        nxt = re.compile(r'^(\s*(?:\*\*)?\s*[0-9]+(?:\.[0-9]+)?(?:\)|\.|\s)\s|\*\*|#{1,3} |[A-Z][A-Z ]{3,})')
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if nxt.match(lines[i]):
                end = i; break
        # preserve original indent of the first line
        indent = re.match(r'\s*', lines[start]).group(0)
        newtext = ('\n'.join((indent + tl) if tl else tl for tl in b['text'])).strip('\n')
        out[start:end] = newtext.split('\n')
        used.append(b['id'])
    if not used:
        print('SKIP (nothing located):', fn); skipped += 1; continue
    news = '\n'.join(out).rstrip('\n') + '\n\nCORRECTIONS HISTORY (audit pass 2 findings; rules above were rewritten accordingly):\n'
    mc2 = re.search(r'CORRECTIONS \(audit pass 2.*?\n(.*?)(?=\n\S|\nRULES v2|$)', body, flags=re.S)
    hist = mc2.group(1).strip('\n') if mc2 else '(corrections block not found)'
    news += hist + '\n'
    open(dp, 'w').write(news)
    merged += 1
    print('MERGED', fn, 'rules', ','.join(used))
print(f'done: {merged} merged, {skipped} skipped')
