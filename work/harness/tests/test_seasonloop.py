"""seasonloop's offseason pieces: demographics() on a synthetic association (association() stubbed, a real enciphered
PYR and .pyf), and notice() on the reference screenshots when they are present."""
import datetime
import os
import struct
import sys

from PIL import Image
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import seasonloop  # noqa: E402
import league      # noqa: E402 (work/ is on the path once gamedata is imported)


def player(pid, born, first='Pat', last='Doe', pos=2):
    p = bytearray(192)
    p[0], p[1] = pid & 255, pid >> 8
    p[seasonloop.gamedata.P_POS] = pos
    p[30:47] = first.encode().ljust(17, b'\0')
    p[47:64] = last.encode().ljust(17, b'\0')
    struct.pack_into('<I', p, 0x1a, born.toordinal() + 365)
    return bytes(p)


def pyr_bytes(records, seed=(0x6b, 0xe2)):
    t = league._forward(seed)
    return bytes(seed) + bytes(190) + b''.join(bytes(t[b] for b in r) for r in records)


def pyf_bytes(ids):
    return b'PPD:' + struct.pack('<Ih', 2 + 2 * len(ids), len(ids)) + struct.pack('<%dH' % len(ids), *ids)


def test_demographics_splits_rostered_free_agents_and_retired(tmp_path, monkeypatch):
    d = datetime.date
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([
        player(100, d(1980, 3, 1)),      # rostered, 27 on July 1 2007
        player(101, d(1975, 8, 1)),      # free agent, 31 (birthday after July 1)
        player(102, d(1960, 1, 1)),      # on neither list: retired
        player(103, d(1984, 7, 1), pos=1),   # rostered pitcher, 23 (birthday on July 1 counts)
    ]))
    (tmp_path / 'TEST.pyf').write_bytes(pyf_bytes([101]))
    (tmp_path / 'TEST.ASN').write_bytes(b'asn')
    monkeypatch.setattr(seasonloop.gamedata, 'association',
                        lambda path: {'teams': {1: {'roster': [100]}, 2: {'roster': [103, 555]}}, 'games': []})
    got = seasonloop.demographics(str(tmp_path), 'TEST', 2007)
    assert got == {'year': 2007, 'rostered': 2, 'mean_age': 25.0, 'le25': 1, 'ge33': 0, 'hist': {23: 1, 27: 1},
                   'fa': 1, 'fa_mean_age': 31.0, 'retired': 1, 'players': 4, 'roster_min': 1, 'pitchers_min': 0}


def test_demographics_without_a_free_agent_file(tmp_path, monkeypatch):
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([player(100, datetime.date(1970, 1, 1))]))
    (tmp_path / 'TEST.ASN').write_bytes(b'asn')
    monkeypatch.setattr(seasonloop.gamedata, 'association', lambda path: {'teams': {}, 'games': []})
    got = seasonloop.demographics(str(tmp_path), 'TEST', 2007)
    assert (got['rostered'], got['fa'], got['retired'], got['mean_age']) == (0, 0, 1, 0)
    assert (got['roster_min'], got['pitchers_min']) == (0, 0)


def test_demographics_counts_pitchers_per_team(tmp_path, monkeypatch):
    d = datetime.date(1980, 1, 1)
    (tmp_path / 'TEST.PYR').write_bytes(pyr_bytes([player(100, d, pos=1), player(101, d, pos=1),
                                                   player(102, d), player(103, d, pos=1)]))
    (tmp_path / 'TEST.ASN').write_bytes(b'asn')
    monkeypatch.setattr(seasonloop.gamedata, 'association',
                        lambda path: {'teams': {1: {'roster': [100, 101, 102]}, 2: {'roster': [103, 102]}}, 'games': []})
    got = seasonloop.demographics(str(tmp_path), 'TEST', 2007)
    assert (got['roster_min'], got['pitchers_min']) == (2, 1)


@pytest.mark.skipif(not all(os.path.exists(os.path.join(seasonloop.REFS, f)) for f in seasonloop.NOTICES.values()),
                    reason='reference screenshots absent')
def test_each_notice_reference_is_recognised_and_a_plain_screen_is_not():
    for kind, ref in seasonloop.NOTICES.items():
        assert seasonloop.notice(os.path.join(seasonloop.REFS, ref)) == kind
    for plain in ('f_assn.png', 'f_update.png'):
        if os.path.exists(os.path.join(seasonloop.REFS, plain)):
            assert seasonloop.notice(os.path.join(seasonloop.REFS, plain)) is None


class _H:
    def __init__(self, work):
        self.WORK = str(work)
        self.keys, self.clicks = [], []

    def x(self, *a):
        self.keys.append(a)

    def click(self, *a):
        self.clicks.append(a)


def _quiet_sim(monkeypatch, tmp_path, on_sim):
    """season() with the screen, the clock and the ASN stubbed: no game is ever played, and on_sim runs per round."""
    assn = tmp_path / 'Assn'
    assn.mkdir()
    (assn / 'TEST.ASN').write_bytes(b'a')
    (assn / 'OTHER.ASN').write_bytes(b'b')
    monkeypatch.setattr(seasonloop, 'played', lambda asn: (0, 100))
    def _sim(h, shots):
        on_sim(assn)
        return True
    monkeypatch.setattr(seasonloop, 'sim', _sim)
    monkeypatch.setattr(seasonloop, 'QUIET', 0)
    for name in ('settle', 'look'):
        monkeypatch.setattr(seasonloop, name, lambda *a, **k: None)
    monkeypatch.setattr(seasonloop, '_diff', lambda *a: 100.0)
    monkeypatch.setattr(seasonloop, 'on_assn_data', lambda png: False)
    monkeypatch.setattr(seasonloop.time, 'sleep', lambda s: None)
    return _H(tmp_path)


def test_season_stops_when_the_sim_wrote_another_association(tmp_path, monkeypatch, capsys):
    def touch_other(assn):
        st = os.stat(assn / 'OTHER.ASN')
        os.utime(assn / 'OTHER.ASN', ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
    h = _quiet_sim(monkeypatch, tmp_path, touch_other)
    assert seasonloop.season(h, str(tmp_path), 'TEST', 3600) is False
    assert '"wrong_association": true' in capsys.readouterr().out


def test_season_without_another_write_is_not_called_wrong(tmp_path, monkeypatch, capsys):
    h = _quiet_sim(monkeypatch, tmp_path, lambda assn: None)
    assert seasonloop.season(h, str(tmp_path), 'TEST', 3600) is False      # stuck: MAX_STOPS, never a game played
    out = capsys.readouterr().out
    assert 'wrong_association' not in out and '"stop": 1' in out


class _Poster:
    """A tiny fake screen for sim/postseason tests: every look() hands the png the next screen name from a list
    (the last one repeats), and _diff/notice read it back. A fake clock keeps the sleep calls harmless."""
    def __init__(self, screens):
        self.screens = list(screens)
        self.faces = {}             # png path: the screen it currently shows

    def next(self):
        return self.screens.pop(0) if self.screens else (self.faces and list(self.faces.values())[-1])


def _stub_screen(monkeypatch, mock):
    def look(h, png):
        mock.faces[png] = mock.next()
        Image.new('L', (4, 4)).save(png)
    monkeypatch.setattr(seasonloop, 'look', look)
    monkeypatch.setattr(seasonloop, '_same', lambda a, b: mock.faces.get(a) == mock.faces.get(b))
    monkeypatch.setattr(seasonloop, '_other_mtimes', lambda asn: {})
    monkeypatch.setattr(seasonloop.time, 'sleep', lambda s: None)
    real_replace = os.replace

    def replace(src, dst):          # seasonloop renames pngs onto each other; the fake screen must follow
        if src in mock.faces:
            mock.faces[dst] = mock.faces.pop(src)
        real_replace(src, dst)
    monkeypatch.setattr(seasonloop.os, 'replace', replace)

    def diff(png, ref, box):
        return 0.0 if mock.faces.get(png) == _REF_SCREEN.get(ref) else 100.0
    monkeypatch.setattr(seasonloop, '_diff', diff)

    def notice(png):
        return 'complete' if mock.faces.get(png) == 'complete' else None
    monkeypatch.setattr(seasonloop, 'notice', notice)
    return mock


_REF_SCREEN = {'f_sched.png': 'sched', 'f_champ.png': 'champ', 'f_update.png': 'busy', 'f_assn.png': 'assn'}
ENDLESS = 10 ** 12                     # t_end far in the future: the screen sequence ends the loop instead


def test_sim_refused_off_the_schedule_with_zero_clicks(tmp_path, monkeypatch, capsys):
    mock = _stub_screen(monkeypatch, _Poster(['other']))
    h = _H(tmp_path)
    assert seasonloop.sim(h, str(tmp_path)) is False
    assert h.clicks == [] and h.keys == []
    assert (tmp_path / 'sim_refused.png').exists()
    assert '{"sim": "refused"}' in capsys.readouterr().out


def test_sim_from_assn_data_presses_ctrl_k_then_clicks(tmp_path, monkeypatch):
    mock = _stub_screen(monkeypatch, _Poster(['assn', 'sched']))
    h = _H(tmp_path)
    assert seasonloop.sim(h, str(tmp_path)) is True
    assert h.keys == [('key', 'ctrl+k')]
    assert len(h.clicks) == 4


def test_sim_from_the_schedule_clicks_four_times_without_ctrl_k(tmp_path, monkeypatch):
    mock = _stub_screen(monkeypatch, _Poster(['sched']))
    h = _H(tmp_path)
    assert seasonloop.sim(h, str(tmp_path)) is True
    assert ('key', 'ctrl+k') not in h.keys
    assert len(h.clicks) == 4


def test_postseason_busy_screen_never_sims_then_complete(tmp_path, monkeypatch, capsys):
    # POST_HELD + 4 busy looks, then complete: a busy look is progress, so no sim ever fires
    mock = _stub_screen(monkeypatch, _Poster(['busy'] * (seasonloop.POST_HELD + 4) + ['complete']))
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS) is True
    assert h.clicks == [] and h.keys == []
    assert '{"postseason": "complete"' in capsys.readouterr().out


def test_postseason_champion_screen_sends_return_never_sims(tmp_path, monkeypatch, capsys):
    # a champion look, then the champion still up after the Return, then complete
    mock = _stub_screen(monkeypatch, _Poster(['champ', 'champ', 'champ', 'complete']))
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS) is True
    assert h.keys == [('key', 'Return')] and h.clicks == []
    out = capsys.readouterr().out
    assert '{"postseason": "champion"}' in out and '"postseason": "sim"' not in out


def test_postseason_champion_screen_gets_one_retry_after_champ_held_looks(tmp_path, monkeypatch, capsys):
    mock = _stub_screen(monkeypatch, _Poster(['champ'] * (1 + seasonloop.CHAMP_HELD) + ['complete']))
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS) is True
    assert h.keys == [('key', 'Return')] * 2 and h.clicks == []
    out = capsys.readouterr().out
    assert '{"postseason": "champion_retry", "n": 1}' in out and '"postseason": "sim"' not in out


def test_postseason_champion_screen_retries_at_most_three_times(tmp_path, monkeypatch, capsys):
    mock = _stub_screen(monkeypatch, _Poster(['champ'] * (1 + 5 * seasonloop.CHAMP_HELD) + ['complete']))
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS) is True
    assert h.keys == [('key', 'Return')] * 4 and h.clicks == []      # 1 + 3 retries, never more
    out = capsys.readouterr().out
    assert out.count('"champion_retry"') == 3
    assert '{"postseason": "champion_retry", "n": 3}' in out and '"n": 4' not in out
    assert '"postseason": "sim"' not in out


def test_postseason_a_busy_look_resets_the_champion_retry_count(tmp_path, monkeypatch, capsys):
    mock = _stub_screen(monkeypatch, _Poster(
        ['champ'] + ['champ'] * (seasonloop.CHAMP_HELD - 1) + ['busy'] + ['champ'] * (seasonloop.CHAMP_HELD - 1)
        + ['complete']))
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS) is True
    assert h.keys == [('key', 'Return')] and h.clicks == []
    out = capsys.readouterr().out
    assert '"champion_retry"' not in out and '"postseason": "sim"' not in out


def test_postseason_wrong_association_stops_before_any_input(tmp_path, monkeypatch, capsys):
    mock = _stub_screen(monkeypatch, _Poster(['sched'] * 3))
    h = _H(tmp_path)
    calls = []

    def mtimes(asn):
        calls.append(asn)
        return {} if len(calls) == 1 else {'OTHER.ASN': 1}      # changes after the entry snapshot
    monkeypatch.setattr(seasonloop, '_other_mtimes', mtimes)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS, asn='X.ASN') is False
    out = capsys.readouterr().out
    assert '{"postseason": "wrong_association"}' in out
    assert '"postseason": "sim"' not in out
    assert h.keys == [] and h.clicks == []


def test_postseason_stale_update_box_gets_one_return(tmp_path, monkeypatch, capsys):
    # the box holds still BUSY_STILL looks with the ASN unchanged: a stale paint, answered once with Return
    mock = _stub_screen(monkeypatch, _Poster(['busy'] * (seasonloop.BUSY_STILL + 2) + ['complete']))
    asn = tmp_path / 'X.ASN'
    asn.write_bytes(b'x')
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS, asn=str(asn)) is True
    assert h.keys == [('key', 'Return')] and h.clicks == []
    assert '{"postseason": "stale_update_box"}' in capsys.readouterr().out
    assert (tmp_path / 'stale_post.png').exists()


def test_postseason_busy_box_with_the_asn_still_written_is_left_alone(tmp_path, monkeypatch, capsys):
    mock = _stub_screen(monkeypatch, _Poster(['busy'] * (seasonloop.BUSY_STILL * 2) + ['complete']))
    asn = tmp_path / 'X.ASN'
    asn.write_bytes(b'x')
    look = seasonloop.look

    def writing(h, png):            # the game is really updating: the ASN changes between looks
        st = os.stat(asn)
        os.utime(asn, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
        look(h, png)
    monkeypatch.setattr(seasonloop, 'look', writing)
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS, asn=str(asn)) is True
    assert h.keys == [] and h.clicks == []
    assert 'stale_update_box' not in capsys.readouterr().out


def test_postseason_after_the_champion_a_still_screen_stops_without_a_sim(tmp_path, monkeypatch, capsys):
    # the champion, then a still screen with no notice: no sim may fire (it opened another association in 2025)
    mock = _stub_screen(monkeypatch, _Poster(['sched', 'champ'] + ['assn'] * (seasonloop.POST_HELD + 3)))
    h = _H(tmp_path)
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS) is False
    assert h.keys == [('key', 'Return')] and h.clicks == []
    out = capsys.readouterr().out
    assert '"postseason": "champion_idle"' in out and '"postseason": "sim"' not in out
    assert (tmp_path / 'post_champ_idle.png').exists()


def _labels(monkeypatch, tmp_path, names):
    """An Assn folder of empty ASN files whose labels come from names {stem: label}."""
    assn = tmp_path / 'Assn'
    assn.mkdir(exist_ok=True)
    for stem in names:
        (assn / (stem + '.ASN')).write_bytes(b'a')
    monkeypatch.setattr(seasonloop.gamedata, 'association',
                        lambda path: {'name': names[os.path.splitext(os.path.basename(path))[0]]})
    return assn


def test_assn_row_is_the_label_order_without_default(tmp_path, monkeypatch):
    assn = _labels(monkeypatch, tmp_path, {'_DEFAULT': '0 default', '30L2025': '2025 Major Leagues',
                                           'MLBPA97': '1997 MLBPA Opening Day', '16L1927': '1927 Major League'})
    (assn / '30L2025.PYR').write_bytes(b'p')
    assert seasonloop.assn_row(str(assn), '30L2025') == 2
    assert seasonloop.assn_row(str(assn), '16l1927') == 0
    assert seasonloop.assn_row(str(assn), 'NOPE') is None


def test_assn_row_unknown_when_a_label_cannot_be_read(tmp_path, monkeypatch):
    assn = _labels(monkeypatch, tmp_path, {'30L2025': '2025 Major Leagues'})
    (assn / 'BAD.ASN').write_bytes(b'x')
    assert seasonloop.assn_row(str(assn), '30L2025') is None


def _reopen_screen(monkeypatch, h, after):
    """The champion, then still association screens; once ctrl+l was sent every look shows `after`."""
    mock = _stub_screen(monkeypatch, _Poster(['sched', 'champ'] + ['assn'] * (seasonloop.POST_HELD + 3)))

    def look(h_, png):
        mock.faces[png] = after if ('key', 'ctrl+l') in h.keys else mock.next()
        Image.new('L', (4, 4)).save(png)
    monkeypatch.setattr(seasonloop, 'look', look)
    return mock


def test_postseason_after_the_champion_reopens_the_association_and_returns_on_its_notice(tmp_path, monkeypatch,
                                                                                         capsys):
    assn = _labels(monkeypatch, tmp_path, {'30L2025': '2025 Major Leagues', 'MLBPA97': '1997 MLBPA Opening Day'})
    h = _H(tmp_path)
    _reopen_screen(monkeypatch, h, 'complete')
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS, asn=str(assn / '30L2025.ASN')) is True
    assert h.keys == [('key', 'Return'), ('key', 'ctrl+l')]
    assert h.clicks == [(575, seasonloop.LIST_Y + seasonloop.LIST_DY), (735, 538)]
    out = capsys.readouterr().out
    assert '"reopened": true' in out and '"postseason": "sim"' not in out


def test_postseason_reopen_without_the_notice_stops_with_champion_idle(tmp_path, monkeypatch, capsys):
    assn = _labels(monkeypatch, tmp_path, {'30L2025': '2025 Major Leagues'})
    h = _H(tmp_path)
    _reopen_screen(monkeypatch, h, 'assn')
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS, asn=str(assn / '30L2025.ASN')) is False
    assert h.keys == [('key', 'Return'), ('key', 'ctrl+l')] and len(h.clicks) == 2
    assert '"postseason": "champion_idle"' in capsys.readouterr().out
    assert (tmp_path / 'post_reopen.png').exists()


def test_postseason_reopen_sends_nothing_for_a_row_past_the_list(tmp_path, monkeypatch, capsys):
    names = {'A%02d' % i: 'label %02d' % i for i in range(seasonloop.LIST_ROWS)}
    names['ZZ'] = 'zz last'
    assn = _labels(monkeypatch, tmp_path, names)
    h = _H(tmp_path)
    _reopen_screen(monkeypatch, h, 'complete')
    assert seasonloop.postseason(h, str(tmp_path), ENDLESS, asn=str(assn / 'ZZ.ASN')) is False
    assert h.keys == [('key', 'Return')] and h.clicks == []
    assert '"postseason": "champion_idle"' in capsys.readouterr().out
