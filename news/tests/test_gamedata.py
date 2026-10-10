"""gamedata.association() on a stubbed member table: the season date and the name come from the ASN's 'a' record (there
are no game files in the repo, so _members is replaced and the ASN file is a placeholder)."""
import datetime
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gamedata  # noqa: E402
import league    # noqa: E402 (work/ is on the path once gamedata is imported)


def serial(year, month=4, day=2):
    """The birth-style date serial gamedata._born reads back as year."""
    return datetime.date(year, month, day).toordinal() + 365


def a_record(name, season=None):
    """An 'a' member payload: the association name at ASN_NAME, the season date serial at offset 14."""
    p = bytearray(league.ASN_TROPHY)
    p[league.ASN_NAME:league.ASN_NAME + len(name)] = name.encode()
    if season is not None:
        struct.pack_into('<I', p, 14, season)
    return bytes(p)


@pytest.fixture
def asn(tmp_path, monkeypatch):
    """A function that stubs the member table with the 'a' records given and returns the ASN path."""
    path = tmp_path / 'MLBPA97.ASN'
    path.write_bytes(b'asn')

    def stub(*records):
        monkeypatch.setattr(gamedata, '_members', lambda data: {'a': list(records)})
        return str(path)
    return stub


def test_season_year_is_the_date_at_offset_14_and_a_career_league_keeps_its_name(asn):
    got = gamedata.association(asn((0, a_record('MLBPA97', serial(2008)))))
    assert got['name'] == 'MLBPA97' and got['season_year'] == 2008


def test_the_season_year_comes_from_the_record_the_name_comes_from(asn):
    got = gamedata.association(asn((league.TEMPLATE_KEY, a_record('Template', serial(2001))),
                                   (0, a_record('1998 Test', serial(1997)))))
    assert got['name'] == '1998 Test' and got['season_year'] == 1997


@pytest.mark.parametrize('junk', [0, 0xFFFFFFFF])
def test_a_serial_that_is_not_a_date_is_no_season_year(asn, junk):
    got = gamedata.association(asn((0, a_record('MLBPA97', junk))))
    assert got['name'] == 'MLBPA97' and got['season_year'] is None


def test_no_record_to_read_is_no_name_and_no_season_year(asn):
    assert gamedata.association(asn()) == {'name': '', 'season_year': None, 'teams': {}, 'games': []}
    assert gamedata.association(asn((league.TEMPLATE_KEY, a_record('Template', serial(2001)))))['season_year'] is None
