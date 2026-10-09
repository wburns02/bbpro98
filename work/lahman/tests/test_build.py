"""End to end: build the 1927 association into a scratch install and check what the game will read. Needs the Lahman
database, the T16_2L template and the work install's MLBPA96E.PYR / _DEFAULT.ASN / _DEFAULT.PYR; skips without them."""
import os
import shutil
import struct
import tempfile

import pytest

import ctree
from lahman import build as B, ratings as RT
from lahman.asnfile import AsnFile, cstr

INSTALL = '/mnt/nvme/bbpro98/work_install'
SCRATCH = '/mnt/nvme/bbpro98/tmp'
NEEDED = [B.DB, os.path.join(INSTALL, 'Assn', 'MLBPA96E.PYR'), os.path.join(INSTALL, 'Assn', '_DEFAULT.ASN'),
          os.path.join(INSTALL, 'Assn', '_DEFAULT.PYR')]


@pytest.fixture(scope='module')
def built():
    if not all(os.path.exists(p) for p in NEEDED) or not os.path.isdir(SCRATCH):
        pytest.skip('Lahman DB or game install absent')
    try:
        B.load_template('T16_2L')
    except (OSError, SystemExit, KeyError):
        pytest.skip('T16_2L template absent')
    root = tempfile.mkdtemp(prefix='lahbuild-', dir=SCRATCH)
    try:
        for sub in ('Assn', 'Stats'):
            os.mkdir(os.path.join(root, sub))
        for f in ('MLBPA96E.PYR', '_DEFAULT.ASN', '_DEFAULT.PYR'):
            os.symlink(os.path.join(INSTALL, 'Assn', f), os.path.join(root, 'Assn', f))
        log = []
        out = B.build(1927, root, log=log.append)
        yield out, log, {k: open(v, 'rb').read() for k, v in out.items()}
    finally:
        shutil.rmtree(root)


def test_files_named_by_slots_and_year(built):
    out, _, _ = built
    assert {os.path.basename(p) for p in out.values()} == {'16L1927.ASN', '16L1927.PYR', '16L1927.PYF',
                                                         '16L1927.DAT'}


def test_teams_and_association(built):
    _, _, data = built
    asn = AsnFile(data['ASN'])
    a = asn.recs['a'][0][1]
    assert cstr(a, 0x12, 33) == '1927 Major Leagues'
    names = {cstr(p, 0x12, 32) for _, p in asn.recs['t']}
    assert len(asn.recs['t']) == 16
    assert any('Yankees' in n for n in names) and any('Pirates' in n for n in names)
    assert not any(n.startswith('Filler Team') for n in names)      # 1927 fills all 16 slots with real teams
    assert asn.recs.get('tr', []) == []                              # template trades cleared


def test_players(built):
    _, log, data = built
    _, recs = RT.read_pyr(built[0]['PYR'])
    names = {(RT.cstr(r[30:47]), RT.cstr(r[47:64])) for r in recs}
    assert ('Babe', 'Ruth') in names and ('Lou', 'Gehrig') in names and ('Lefty', 'Grove') in names
    ids = [struct.unpack_from('<H', r, 0)[0] for r in recs]
    assert ids == list(range(100, 100 + len(recs)))
    assert len(recs) >= 400
    fa = struct.unpack_from('<h', data['PYF'], 8)[0]
    assert data['PYF'][:4] == b'PPD:' and len(data['PYF']) == 10 + 2 * fa


def test_stats_file_valid(built):
    _, _, data = built
    d = data['DAT']
    assert len(d) % 0x8000 == 0 and struct.unpack_from('<I', d, 0)[0] == len(d) - 1
    recs, by_mem, members, idxinfo, *_ = ctree.parse(d)
    sizes = {}
    for idxmem, (trees, datam, base) in idxinfo.items():
        live = {r.hdr for r in by_mem.get(datam, []) if d[r.off] != 0xFF}
        for tr in trees:
            if tr.klen:
                keys = [k for k, _ in tr.entries]
                assert keys == sorted(keys) and {p for _, p in tr.entries} == live
        sizes[base] = len(live)
    assert sizes['bt'] > 400 and sizes['pt'] > 150 and sizes['ft'] > 400
    # Career lines (scope 2) predate 1927 only; Ruth's career batting line carries 1914-1926 home runs (356).
    _, recs_p = RT.read_pyr(built[0]['PYR'])
    ruth = next(struct.unpack_from('<H', r, 0)[0] for r in recs_p
                if (RT.cstr(r[30:47]), RT.cstr(r[47:64])) == ('Babe', 'Ruth'))
    bt = next(m['num'] for m in members if m['name'] == 'bt.dat')
    lines = [bytes(d[r.off:r.off + r.pl]) for r in by_mem[bt] if d[r.off] != 0xFF]
    mine = [p for p in lines if struct.unpack_from('<HHH', p, 0) == (2, 2, ruth)]
    assert len(mine) == 1
    words = struct.unpack_from('<17H', mine[0], 6)                  # stats.BAT order: ab h1b h2b h3b hr ...
    assert words[4] == 356


def test_short_rosters_padded():
    """1875: Keokuk and the Philadelphia Centennials keep too few players of their own to field a lineup; the build
    pads them with generated players so every team has nine distinct starters (pitcher's slot NONE) and five pitchers."""
    if not all(os.path.exists(p) for p in NEEDED) or not os.path.isdir(SCRATCH):
        pytest.skip('Lahman DB or game install absent')
    try:
        B.load_template('T14_77')
    except (OSError, SystemExit, KeyError):
        pytest.skip('T14_77 template absent')
    root = tempfile.mkdtemp(prefix='lahbuild-', dir=SCRATCH)
    try:
        for sub in ('Assn', 'Stats'):
            os.mkdir(os.path.join(root, sub))
        for f in ('MLBPA96E.PYR', '_DEFAULT.ASN', '_DEFAULT.PYR'):
            os.symlink(os.path.join(INSTALL, 'Assn', f), os.path.join(root, 'Assn', f))
        log = []
        out = B.build(1875, root, log=log.append)
        asn = AsnFile(open(out['ASN'], 'rb').read())
        _, recs = RT.read_pyr(out['PYR'])
    finally:
        shutil.rmtree(root)
    padded = [l for l in log if 'generated)' in l]
    assert any(' KEO ' in l for l in padded) and any(' PH3 ' in l for l in padded)
    pos = {struct.unpack_from('<H', r, 0)[0]: r[68] for r in recs}
    assert len(asn.recs['r']) == 14
    for _, p in asn.recs['r']:
        ids = struct.unpack_from('<126H', p, 0x2a)
        active = [x for x in ids[:25] if x]
        order, align, rot = ids[77:86], ids[95:104], [x for x in ids[113:119] if x]
        assert all(x in pos for x in active)
        assert sum(pos[x] != 1 for x in active) >= B.MIN_HIT and sum(pos[x] == 1 for x in active) >= 5
        assert rot and all(pos[x] == 1 for x in rot)
        starters = [x for x in order if x != B.NONE]
        assert len(starters) == 8 and len(set(starters)) == 8 and set(starters) <= set(active)
        assert set(x for x in align[:8]) == set(starters)


def test_every_minted_template_has_a_schedule():
    """A template without s records builds a season in which no game is ever played (the 14-team-league shapes
    minted before the schedule prompt was answered). load_template refuses those; every minted one must pass."""
    if not os.path.isdir(B.TEMPLATES):
        pytest.skip('templates absent')
    keys = sorted(k for k in os.listdir(B.TEMPLATES) if os.path.isdir(os.path.join(B.TEMPLATES, k)))
    if not keys:
        pytest.skip('no templates minted')
    for key in keys:
        files = B.load_template(key)
        assert len(AsnFile(open(files['ASN'], 'rb').read()).recs['s']) > 100, key


def test_pitch_ratings_follow_fitted_stuff(built):
    """Pitch ratings are shifted to each pitcher's fitted stuff, not copied from a donor: in the first 1998 build three
    control pitchers carried Greg Maddux's whole 1996 arsenal (stuff 88.5) and sim ERAs under 1.10."""
    out, _, _ = built
    recs = [r for r in RT.read_pyr(out['PYR'])[1] if r[68] == 1]
    st = [RT.stuff(r) for r in recs]
    assert all(s is not None for s in st)
    assert max(st) < 80
    arsenals = [tuple(r[RT.CUR + i] for i in RT.PITCHES) for r in recs]
    assert len(set(arsenals)) > 0.75 * len(arsenals)
    for r in recs:
        assert all(r[RT.PEAK + i] >= r[RT.CUR + i] for i in RT.PITCHES)


def test_stuff_is_mean_of_thrown_pitches():
    r = bytearray(RT.REC)
    assert RT.stuff(r) is None
    r[RT.CUR + 7], r[RT.CUR + 9], r[RT.CUR + 13] = 60, 50, 40
    assert RT.stuff(r) == 50
