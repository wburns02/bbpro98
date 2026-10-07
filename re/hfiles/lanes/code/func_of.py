import sys, re, bisect
path = sys.argv[1]
lines = open(path, errors='replace').read().split('\n')
starts = []  # (lineno, addr, name)
for i, l in enumerate(lines):
    m = re.match(r'// ==== ([0-9a-f]+) (\S+) callers=', l)
    if m: starts.append((i+1, m.group(1), m.group(2)))
n = int(sys.argv[2])
i = bisect.bisect_right([s[0] for s in starts], n) - 1
print(f"{starts[i][1]} {starts[i][2]} (line {starts[i][0]})" if i >= 0 else "none")
