"""Career arcs: the per-player aging trait mods\\aging.dll applies at each offseason (src-latest/mods/arc.h), computed
here the same way, and the scouting hint the team page shows for it. trait is a pure function of (pid, birth serial);
test_arc.py compiles arc.h and checks the two agree. hint and player_hint are pure too. Standard library only.
"""
import datetime

YEARS = 3               # years of decline onset, either way (aging.c [aging] arc_years)
SPREAD = 30             # percent the decline amount varies, either way (aging.c [aging] arc_size)
MIN_AGE = 28            # scouts cannot read the arc of a younger player
LATE, EARLY = 2, -2     # shift at which a player ages well / is an early decline risk
STEEP, GENTLE = 115, 85     # size at which the decline is steep / gentle
FNV_BASIS, FNV_PRIME = 2166136261, 16777619


def trait(pid, birth, years=YEARS, spread=SPREAD):
    """(shift, size) for a player: the years his decline starts later (positive) or earlier (negative), and the percent
    of the usual decline amount he loses. FNV-1a 32-bit over pid (2 bytes) and birth (4 bytes), little-endian;
    shift = h % (2*years+1) - years, size = 100 - spread + (h >> 16) % (2*spread+1). A negative years or spread counts as
    0 (shift 0, size 100), as in arc.h."""
    years, spread = max(years, 0), max(spread, 0)
    h = FNV_BASIS
    for b in (pid & 0xff, (pid >> 8) & 0xff) + tuple((birth >> (8 * k)) & 0xff for k in range(4)):
        h = ((h ^ b) * FNV_PRIME) & 0xffffffff
    return h % (2 * years + 1) - years, 100 - spread + (h >> 16) % (2 * spread + 1)


def hint(shift, size, age):
    """The scouting words for a trait at an age, or None when age is None or under MIN_AGE. 'ages well' for a shift of
    LATE or more, 'early decline risk' for EARLY or less, else 'normal aging'; then ', steep decline' for a size of
    STEEP or more, ', gentle decline' for GENTLE or less."""
    if age is None or age < MIN_AGE:
        return None
    text = 'ages well' if shift >= LATE else 'early decline risk' if shift <= EARLY else 'normal aging'
    if size >= STEEP:
        text += ', steep decline'
    elif size <= GENTLE:
        text += ', gentle decline'
    return text


def player_hint(pid, birth, year):
    """hint for a player from his birth serial (the date is date.fromordinal(birth - 365)) in season year: age is year
    minus the birth year, as scout._age gives. None when birth is not an int that is a valid serial, or year is not an
    int, or hint gives None."""
    if type(birth) is not int or type(year) is not int:
        return None
    try:
        born = datetime.date.fromordinal(birth - 365)
    except (ValueError, OverflowError):
        return None
    shift, size = trait(pid, birth)
    return hint(shift, size, year - born.year)
