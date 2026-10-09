"""Put the full Lahman team name back on teams of a Lahman-built association.

The table is work/lahman/teamnames.py output, {year: {teamID: [full, short]}}, deployed as <data>/teamnames.json.
A team is renamed only when the association name starts with a four-digit year that is in the table, the team's
abbrev is a teamID of that year, and its stored name is still the short form build.py wrote. Anything else, the
stock MLBPA associations included, is left as it is.
"""
import json
import re


def load(path):
    """The table, or {} when the file is missing or not a JSON object."""
    try:
        with open(path, encoding='utf-8') as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def apply(assoc, table):
    """assoc with the full names put back; assoc itself is not changed."""
    m = re.match(r'(\d{4})\b', assoc.get('name') or '')
    year = table.get(m.group(1)) if m else None
    if not isinstance(year, dict):
        return assoc
    teams = {}
    for tid, t in assoc['teams'].items():
        pair = year.get(t.get('abbrev'))
        if (isinstance(pair, list) and len(pair) == 2 and all(isinstance(s, str) for s in pair)
                and pair[0] and t.get('name') == pair[1]):
            t = dict(t, name=pair[0])
        teams[tid] = t
    return dict(assoc, teams=teams)
