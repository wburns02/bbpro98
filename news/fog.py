"""Scouting fog for the news sidecar: what a scout sees of a player is his rating plus a noise that shrinks as the player
is seen more. A rookie is hard to read, a veteran of seven seasons nearly exact, and a team's own scouts see its players
twice as well. The noise is a hash of who looks, at whom, at what and in which year, so the same question always gets the
same answer, across runs and without any stored state. Pure functions over the dicts gamedata.players() returns; nothing
here changes a rating anywhere, a view is a copy. Viewer 0 is the public view (the newspaper's scouts).
"""
import hashlib

RATED = ('contact', 'power', 'speed', 'fielding', 'control', 'strikeout', 'stamina')   # what scout.py grades
SD_STEPS = ((2, 8), (4, 6), (7, 4))     # (seasons below, sd): 0..1 seasons 8, 2..3 six, 4..6 four, 7 and up 2
SD_MAX = 2.5                            # noise is cut off at this many sd


def sd(seasons, own=False):
    """The noise sd in rating points for a player seen for `seasons` service seasons: 8 for 0..1, 6 for 2..3, 4 for
    4..6, 2 for 7 and up. None (unknown) counts as 0, the least seen. own=True halves it (integer division, minimum 1)."""
    seasons = seasons if isinstance(seasons, int) and not isinstance(seasons, bool) else 0
    value = next((v for below, v in SD_STEPS if seasons < below), 2)
    return max(1, value // 2) if own else value


def noise(assn, viewer, pid, key, year, seasons, own=False):
    """The integer noise one viewer adds to one rating of one player in one year: a fixed draw from the hash of the
    arguments, roughly normal (three bytes summed), cut off at SD_MAX sd and scaled by sd(seasons, own)."""
    d = hashlib.sha256(('%s|%s|%s|%s|%s' % (assn, viewer, pid, key, year)).encode()).digest()
    n = (d[0] + d[1] + d[2] - 382.5) / 127.9
    return round(max(-SD_MAX, min(SD_MAX, n)) * sd(seasons, own))


def rating(value, assn, viewer, pid, key, year, seasons, own=False):
    """value plus its noise, kept within 1..99. A value of 0 (not rated: a hitter's pitches) stays 0, and None
    stays None."""
    if not value:
        return value
    return max(1, min(99, value + noise(assn, viewer, pid, key, year, seasons, own)))


def view(player, assn, viewer, year, own=False, pid=None):
    """A copy of a gamedata.players() entry with each rating in RATED replaced by its fogged rating; the original is not
    touched. The noise needs to know which player it is: pid when given, else the entry's own 'pid', else his name."""
    who = pid if pid is not None else player.get('pid', player.get('name', ''))
    seasons = player.get('seasons')
    out = dict(player)
    for key in RATED:
        if key in out:
            out[key] = rating(out[key], assn, viewer, who, key, year, seasons, own)
    return out
