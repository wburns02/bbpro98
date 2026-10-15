"""Holdouts for the code that writes a player's game files: news/create.py (add a player to an association),
news/aigm.py (AI trades rewrite roster windows inside an ASN) and news/focus.py (focus.txt, which aging.dll parses).
Synthetic files only. Each test names the regression it guards."""
import datetime
import struct

import pytest

import aigm
import create
import focus
import league
from bbholdout_helpers import CUR, PEAK, K_ATTR, player, pyf_bytes, pyr_bytes

R = create.rating
NOW = datetime.datetime(2026, 10, 14, 12, 0, 0)
SEED = (0x6b, 0xe2)

DONOR_HIT = player(105, 'Don', 'Or', pos=6, bats=2, throws=2,
                   cur={0: 40, 1: 60, 2: 70, 3: 30, 4: 9, 7: 60, 8: 61, 19: 80},
                   peak={0: 90, 1: 60, 2: 60, 3: 45, 7: 70, 19: 85})
DONOR_PIT = player(300, 'Dan', 'Pit', pos=1, born=1975, bats=1, throws=1,
                   cur={5: 60, 6: 50, 7: 70, 9: 50, 13: 30}, peak={5: 65, 6: 50, 7: 80, 9: 55}, raw={K_ATTR: 40})
SPEC_SS = {'assn': 'TEST77', 'first': 'Ned', 'last': 'Ray', 'pos': 'SS', 'bats': 'L', 'throws': 'R', 'age': 24,
           'archetype': 'glove', 'mode': 'sandbox',
           'now': {'contact': 60, 'power': 50, 'speed': 40, 'arm': 30, 'fielding': 70},
           'ceiling': {'contact': 65, 'power': 50, 'speed': 45, 'arm': 35, 'fielding': 70}, 'pitches': {}}
SPEC_P = {'assn': 'TEST77', 'first': 'Al', 'last': 'Ko', 'pos': 'P', 'bats': 'R', 'throws': 'L', 'age': 25,
          'archetype': 'ace', 'mode': 'sandbox',
          'now': {'stamina': 60, 'control': 50, 'hold': 50, 'strikeout': 70},
          'ceiling': {'stamina': 65, 'control': 50, 'hold': 50},
          'pitches': {'FB': (70, 75), 'SL': (50, 55)}}


@pytest.fixture
def site(tmp_path, monkeypatch):
    """(game dir, donor PYR path, fake /proc dir): association TEST77 with two players and a pool holding both."""
    monkeypatch.setattr(create.gamedata, 'association', lambda path: {'name': '1977 Major Leagues'})
    root = tmp_path / 'game'
    (root / 'Assn').mkdir(parents=True)
    (root / 'Stats').mkdir()
    (root / 'Assn' / 'TEST77.ASN').write_bytes(b'asn')
    (root / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes([player(100, pos=3), player(205, 'Bo', 'Bee', pos=1)]))
    (root / 'Assn' / 'TEST77.PYF').write_bytes(pyf_bytes([100, 205], stale=b'STALE'))
    (root / 'Stats' / 'TEST77.DAT').write_bytes(b'dat')
    stock = tmp_path / 'stock'
    stock.mkdir()
    donor = stock / 'MLBPA96E.PYR'
    donor.write_bytes(pyr_bytes([DONOR_HIT, DONOR_PIT]))
    proc = tmp_path / 'proc'
    proc.mkdir()
    return root, donor, proc


def snapshot(root):
    return {p.name: p.read_bytes() for p in sorted((root / 'Assn').iterdir()) if p.is_file()}


def test_add_player_is_append_only_and_backs_up_before_it_writes(site, tmp_path, monkeypatch):
    """Guards: a rewrite that reorders, drops or alters existing players, a missing backup, a backup taken after the
    write, and leftover temp files."""
    root, donor, proc = site
    before = snapshot(root)
    backup = tmp_path / 'backup'
    pid, rec = create.add_player(str(root), SPEC_SS, str(donor), str(backup), NOW, str(proc))
    assert pid == 206
    after = snapshot(root)
    assert after['TEST77.PYR'].startswith(before['TEST77.PYR'])            # old bytes untouched, byte for byte
    assert len(after['TEST77.PYR']) == len(before['TEST77.PYR']) + 192
    assert create.decipher(after['TEST77.PYR'])[1][-1] == rec
    assert create.pyf_ids(after['TEST77.PYF']) == [100, 205, 206]
    assert after['TEST77.PYF'].endswith(b'STALE')
    kept = backup / 'TEST77-20261014T120000-206'
    assert (kept / 'TEST77.PYR').read_bytes() == before['TEST77.PYR']
    assert (kept / 'TEST77.PYF').read_bytes() == before['TEST77.PYF']
    assert [p for p in root.rglob('*') if p.name.endswith('create-tmp')] == []
    # a second player gets the next id and the pool never lists an id twice
    later = NOW + datetime.timedelta(seconds=1)
    pid2, _ = create.add_player(str(root), SPEC_P, str(donor), str(backup), later, str(proc))
    assert pid2 == 207
    ids = create.pyf_ids((root / 'Assn' / 'TEST77.PYF').read_bytes())
    assert ids == [100, 205, 206, 207] and len(set(ids)) == len(ids)

    # the backup must exist before the first write: if the writer dies, the backup already holds the originals
    root2 = tmp_path / 'game2'
    (root2 / 'Assn').mkdir(parents=True)
    for name, data in before.items():
        (root2 / 'Assn' / name).write_bytes(data)

    def explode(path, data):
        raise RuntimeError('disk full')

    monkeypatch.setattr(create, '_write_atomic', explode)
    backup2 = tmp_path / 'backup2'
    with pytest.raises(RuntimeError):
        create.add_player(str(root2), SPEC_SS, str(donor), str(backup2), NOW, str(proc))
    assert snapshot(root2) == before
    saved = list(backup2.glob('TEST77-*/TEST77.PYR'))
    assert len(saved) == 1 and saved[0].read_bytes() == before['TEST77.PYR']


def check_refuses_while_the_game_holds_the_files_open(site, tmp_path):
    """Guards: writing a PYR/PYF the running game has open (the game would clobber it or read a torn file). Uses the
    real /proc: this test process holds the PYR open."""
    root, donor, _ = site
    before = snapshot(root)
    backup = tmp_path / 'backup'
    with open(root / 'Assn' / 'TEST77.PYR', 'rb'):
        with pytest.raises(create.AssociationOpen):
            create.add_player(str(root), SPEC_SS, str(donor), str(backup), NOW)
    assert snapshot(root) == before and not backup.exists()
    pid, _ = create.add_player(str(root), SPEC_SS, str(donor), str(backup), NOW)     # closed again: it goes through
    assert pid == 206


def check_stops_when_the_id_space_is_full(site, tmp_path):
    """Guards: a 16-bit id overflow silently wrapping and overwriting a real player's id."""
    root, donor, proc = site
    (root / 'Assn' / 'TEST77.PYR').write_bytes(pyr_bytes([player(0xFFFF, 'Max', 'Id', pos=3)]))
    before = snapshot(root)
    with pytest.raises(ValueError):
        create.add_player(str(root), SPEC_SS, str(donor), str(tmp_path / 'backup'), NOW, str(proc))
    assert snapshot(root) == before


def test_add_player_refuses_when_it_is_unsafe_to_write(site, tmp_path):
    """Guards: writing a PYR/PYF the running game has open, and a 16-bit id overflow wrapping onto a real player."""
    root = site[0]
    original = (root / 'Assn' / 'TEST77.PYR').read_bytes()
    check_stops_when_the_id_space_is_full(site, tmp_path)
    (root / 'Assn' / 'TEST77.PYR').write_bytes(original)
    check_refuses_while_the_game_holds_the_files_open(site, tmp_path)


def test_player_records_are_built_to_spec():
    """Guards: the PYR cipher and header, the exact grades written into a new record, and the realistic-mode caps."""
    check_pyr_cipher_seed_is_read_from_each_file()
    check_built_player_has_exactly_the_requested_grades()
    check_realistic_mode_still_gates_ceilings_budget_and_names()


def check_pyr_cipher_seed_is_read_from_each_file():
    """Guards: a hardcoded cipher seed (the seed is per file, bytes 0-1 of the PYR), a lossy round trip, and accepting a
    cut-short file."""
    recs = [player(100 + i, 'P%d' % i, 'Q%d' % i, pos=1 + i % 9) for i in range(6)]
    seen = set()
    for seed in ((0x6b, 0xe2), (0x12, 0x34), (0xf5, 0xdc)):
        data = pyr_bytes(recs, seed)
        header, plain = create.decipher(data)
        assert plain == recs
        assert create.encipher(header, plain) == data
        seen.add(data[192:])
    assert len(seen) == 3                                   # a different seed really enciphers differently
    with pytest.raises(ValueError):
        create.decipher(pyr_bytes(recs)[:-1])
    with pytest.raises(ValueError):
        create.decipher(b'')


def check_built_player_has_exactly_the_requested_grades():
    """Guards: peak below current, donor pitch bytes leaking into a hitter or an unthrown pitch, the id or name fields
    written wrong, and ratings off the 20-80 grade scale."""
    hit = create.build_record(SPEC_SS, DONOR_HIT, 206, 1977)
    assert len(hit) == 192 and hit[0] | hit[1] << 8 == 206
    for idx, key in ((0, 'contact'), (1, 'power'), (2, 'speed'), (3, 'arm')):
        assert hit[CUR + idx] == R(SPEC_SS['now'][key]), key
        assert hit[PEAK + idx] == R(SPEC_SS['ceiling'][key]), key
    assert hit[CUR + 14 + 5] == R(70)                       # SS is position code 6: fielding index 14 + 5
    assert all(hit[CUR + i] == 0 and hit[PEAK + i] == 0 for i in range(7, 14))      # no pitches on a hitter
    assert hit[30:47] == b'Ned'.ljust(17, b'\0') and hit[47:64] == b'Ray'.ljust(17, b'\0')
    assert hit[68] == 6
    for i in (0, 1, 2, 3, 19):                                      # every rating the spec sets: peak never under current
        assert hit[PEAK + i] >= hit[CUR + i], i
    pit = create.build_record(SPEC_P, DONOR_PIT, 207, 1977)
    assert pit[CUR + 7] == R(70) and pit[PEAK + 7] == R(75)         # FB
    assert pit[CUR + 10] == R(50) and pit[PEAK + 10] == R(55)       # SL, storage slot 7 + 3
    assert pit[CUR + 9] == 0 and pit[PEAK + 9] == 0                 # the donor's sinker is not thrown by the new man
    assert pit[CUR + 13] == 0                                       # nor his knuckleball
    assert pit[K_ATTR] == R(70) and pit[0x96] == min(255, 51 + R(60))


def check_realistic_mode_still_gates_ceilings_budget_and_names():
    """Guards: the realistic-mode caps (age gap and budget points) and the name rule that keeps the 16-byte
    NUL-padded name field clean."""
    assns = {'TEST77'}
    five = ('contact', 'power', 'speed', 'arm', 'fielding')
    base = {'assn': 'TEST77', 'first': 'Pat', 'last': 'Doe', 'pos': 'SS', 'bats': 'R', 'throws': 'R', 'age': '24',
            'archetype': 'regular', 'mode': 'realistic'}
    for r in five:
        base['now_' + r] = '50'
        base['ceil_' + r] = '50'
    spec, errors = create.validate(dict(base), assns)
    assert spec is not None and errors == {}
    # a ceiling 30 above Now at age 24 breaks the 15 point gap
    spec, errors = create.validate(dict(base, ceil_power='80'), assns)
    assert spec is None and 'ceil_power' in errors
    # Now grades all at 70 break the 50 point budget even with no ceiling gap
    over = dict(base)
    for r in five:
        over['now_' + r] = over['ceil_' + r] = '70'
    spec, errors = create.validate(over, assns)
    assert spec is None and 'budget' in errors
    assert create.validate(dict(over, mode='sandbox'), assns)[0] is not None       # sandbox lifts both caps
    # names: control characters, 17 characters, empty and non-latin1 never reach the record
    for bad in ('Pat\x00', 'A' * 17, '', 'Pat;x', 'PatЖ', '1Pat'):
        spec, errors = create.validate(dict(base, first=bad), assns)
        assert spec is None and 'first' in errors, repr(bad)
    # an unknown association is refused
    assert create.validate(dict(base, assn='NOPE'), assns)[0] is None


# aigm: a trade rewrites two roster windows inside the ASN and nothing else

def _win(active=(), lineup=()):
    w = list(active) + [0] * (aigm.ACTIVE - len(active)) + list(lineup)
    return w + [0] * (aigm.WINDOW_LEN - len(w))


def _make_asn(windows):
    t = league._forward(SEED)
    data = bytearray(0x312)
    data[0x310:0x312] = bytes(SEED)
    loc = {'r': {}, 't': {}}
    for tid, w in sorted(windows.items()):
        plain = bytearray(294)
        plain[42:294] = struct.pack('<126H', *w)
        loc['r'][tid] = (len(data), 294)
        data += bytes([tid]) + bytes(t[b] for b in plain[1:])
    return bytes(data), loc


TRADE = {'a': 1, 'b': 2, 'a_gives': 102, 'b_gives': 202, 'a_pos': '2B', 'b_pos': 'SS', 'b_drops': 201, 'a_drops': 101,
         'gain': 25.0}


def check_apply_trade_swaps_in_place_and_touches_no_other_byte(monkeypatch):
    """Guards: a trade that rewrites bytes outside the two teams' windows, loses the lineup spots, or applies a trade
    that does not fit the file (a player not on the active roster, or already on the other team)."""
    windows = {1: _win([101, 102], [101]), 2: _win([201, 202], [201]), 3: _win([301, 302], [301])}
    data, loc = _make_asn(windows)
    monkeypatch.setattr(aigm, 'locate', lambda _d: loc)
    new = aigm.apply_trade(data, TRADE)
    assert len(new) == len(data)
    changed = {i for i in range(len(data)) if data[i] != new[i]}
    allowed = set()
    for tid in (1, 2):
        off = loc['r'][tid][0] + aigm.WINDOW_OFF
        allowed |= set(range(off, off + 2 * aigm.WINDOW_LEN))
    assert changed and changed <= allowed
    after = aigm.read(new)['windows']
    assert after == {1: _win([101, 202], [202]), 2: _win([201, 102], [102]), 3: windows[3]}
    for bad in (dict(TRADE, a_gives=999),                      # not on his active roster
                dict(TRADE, b_gives=101),                      # already on team a
                dict(TRADE, a=9)):                             # no such team
        with pytest.raises(aigm.SwapError):
            aigm.apply_trade(data, bad)


def check_validate_catches_duplicate_ids_lost_pitchers_and_lineup_strays():
    """Guards: the post-trade check that stops a bad trade reaching the file: an id on two teams, a team that loses a
    pitcher or falls under 5 pitchers / 8 hitters, and a lineup player who is not on the active roster."""
    players = {}
    active = {}
    for tid in (1, 2):
        ids = []
        for k in range(5):
            players[tid * 100 + k] = {'pos': 'P'}
            ids.append(tid * 100 + k)
        for k in range(5, 13):
            players[tid * 100 + k] = {'pos': 'SS'}
            ids.append(tid * 100 + k)
        active[tid] = _win(ids, [ids[6]])
    assert aigm.validate(active, {t: list(w) for t, w in active.items()}, players) == []
    dup = {t: list(w) for t, w in active.items()}
    dup[2][0] = 101                                            # id 101 now on both teams
    assert any('team 1 and team 2' in p for p in aigm.validate(active, dup, players))
    swapped = {t: list(w) for t, w in active.items()}
    swapped[1][0], swapped[2][5] = 205, 100                     # a pitcher for a hitter
    assert any('active pitchers' in p for p in aigm.validate(active, swapped, players))
    stray = {t: list(w) for t, w in active.items()}
    stray[1][aigm.ACTIVE + 1] = 150                               # in the lineup, not on the roster
    players[150] = {'pos': '1B'}
    assert any('not on its active roster' in p for p in aigm.validate(active, stray, players))


def test_ai_trades_rewrite_only_the_two_windows_and_are_validated(monkeypatch):
    """Guards: a trade that spills outside its two roster windows, and the post-trade validation."""
    check_apply_trade_swaps_in_place_and_touches_no_other_byte(monkeypatch)
    check_validate_catches_duplicate_ids_lost_pitchers_and_lineup_strays()


# focus.txt is parsed by C code in aging.dll: what the Python side writes must be what the rules allow

def test_focus_file_rules_first_line_wins_five_per_association():
    """Guards: signed or underscored numbers in focus.txt, an unknown kind, a duplicate (pid, birth) overriding the first
    line (aging.dll uses the first), the 5 per association cap, and set_focus mutating its input."""
    text = '\n'.join(['# header', '150 7000 power TEST77', '150 7000 speed TEST77', '-150 7000 power', '151 7_0 power',
                    '152 7000 homerun', '99 7000 power', '153 7000 CONTACT bad!assn', '+154 7000 power', ''])
    entries = focus.parse(text)
    assert [(e['pid'], e['kind']) for e in entries] == [(150, 'power'), (153, 'contact')]
    assert entries[1]['assn'] is None
    assert focus.parse(focus.format(entries)) == entries
    base = []
    for pid in range(200, 205):
        base = focus.set_focus(base, 'TEST77', pid, 5000, 'power')
    before = [dict(e) for e in base]
    with pytest.raises(focus.FocusFull):
        focus.set_focus(base, 'TEST77', 300, 5000, 'power')
    assert base == before
    again = focus.set_focus(base, 'TEST77', 200, 5000, 'speed')                  # changing one in place is fine
    assert len(again) == 5 and again[0]['kind'] == 'speed' and base[0]['kind'] == 'power'
    assert len(focus.set_focus(base, 'OTHER', 300, 5000, 'power')) == 6          # another association has its own five
    with pytest.raises(ValueError):
        focus.set_focus(base, 'TEST77', 200, 5000, 'homerun')
