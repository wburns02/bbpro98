#!/usr/bin/env bash
# Writes the /etc/hosts a Claude lane jail gets instead of DNS (egress_anthropic.nft drops port 53, so the token cannot
# leave in query names through pasta's recursive forwarder): the host's localhost lines plus the Anthropic names Claude
# Code uses, resolved here and refused unless every address is in Anthropic's published 160.79.104.0/23.
# usage: anthropic_hosts.sh <out-file>
set -eu
out=${1:?out file}
python3 -I -B - "$out" <<'PY'
import ipaddress, os, socket, sys
NET = ipaddress.ip_network('160.79.104.0/23')
NAMES = ('api.anthropic.com', 'platform.claude.com', 'claude.ai', 'console.anthropic.com', 'mcp-proxy.anthropic.com')
lines = ['127.0.0.1 localhost localhost.localdomain', '::1 localhost localhost.localdomain']
for n in NAMES:
    ips = sorted({a[4][0] for a in socket.getaddrinfo(n, 443, socket.AF_INET, socket.SOCK_STREAM)})
    if not ips or any(ipaddress.ip_address(ip) not in NET for ip in ips): sys.exit(f'{n} -> {ips}: outside {NET}')
    lines += [f'{ip} {n}' for ip in ips]
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
with os.fdopen(fd, 'w') as fh: fh.write('\n'.join(lines) + '\n')
PY
