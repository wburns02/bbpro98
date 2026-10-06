#!/bin/bash
# Wide stats window: serves http://127.0.0.1:8099 from the live game install (re-reads files each request)
cd /home/will/bbpro98/work && exec python3 -I bbwide.py --port 8099 "$@"
