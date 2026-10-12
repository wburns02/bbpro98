"""expand.py on copies of real associations: 16L1927 (preseason, in the work install) grows from 16 to 18 teams on the
stock T18 shape; MLBPA97 (played games) is refused. Needs the work install and the minted templates; skips without them.
Every file expand writes is decoded back with the repo codecs."""
import os
import shutil
import struct
import tempfile

import pytest

import ctree
from lahman import build as B, expand as X, ratings as RT, structure
from lahman.asnfile import AsnFile, cstr
import stats as ST

INSTALL = '/mnt/nvme/bbpro98/work_install'
TEMPLATES = '/mnt/nvme/bbpro98/lahman/templates'
SCRATCH = os.environ.get('SCRATCH', '/mnt/nvme/bbpro98/tmp')
# shape -> (adds, the league sizes the output must have). The one shape 16L1927 can reach with its thin rosters is T18
# (two NL teams go to the end of the NL slots, every old key stays put). T20 (two more per league) is refused for depth.
CASES = {
    'T18': (['NL:1:Phoenix:Desert Dogs:PHO', 'NL:1:Denver:Mile High:DEN'], [[8], [10]]),
}


def _copy(stem, root, assn_files, stats_file):
    """Copy an association's files (names matched without case: the install has mlbpa97.DAT and MLBPA97.pyf)."""
    for sub in ('Assn', 'Stats'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    for f in assn_files:
        shutil.copyfile(X._find(os.path.join(INSTALL, 'Assn'), f), os.path.join(root, 'Assn', f))
    shutil.copyfile(X._find(os.path.join(INSTALL, 'Stats'), stats_file), os.path.join(root, 'Stats', stats_file))


def _need(*paths):
    if not os.path.isdir(SCRATCH) or not all(os.path.exists(p) for p in paths):
        pytest.skip('work install, templates or scratch absent')


def _read(path):
    return open(path, 'rb').read()


def _expand_case(key):
    adds, _ = CASES[key]
    root = tempfile.mkdtemp(prefix='bbexpand-test-', dir=SCRATCH)
    try:
        _copy('16L1927', root, ['16L1927.ASN', '16L1927.PYR', '16L1927.PYF'], '16L1927.DAT')
        log = []
        summary = X.expand(root, '16L1927', TEMPLATES, adds, '%sX1927' % key[1:], log=log.append)
        stem = '%sX1927' % key[1:]
        src = {'asn': _read(os.path.join(root, 'Assn', '16L1927.ASN')),
               'pyr': _read(os.path.join(root, 'Assn', '16L1927.PYR')),
               'pyf': _read(os.path.join(root, 'Assn', '16L1927.PYF')),
               'dat': _read(os.path.join(root, 'Stats', '16L1927.DAT'))}
        out = {'asn': _read(os.path.join(root, 'Assn', stem + '.ASN')),
               'pyr': _read(os.path.join(root, 'Assn', stem + '.PYR')),
               'pyf': _read(os.path.join(root, 'Assn', stem + '.PYF')),
               'dat': _read(os.path.join(root, 'Stats', stem + '.DAT'))}
        return {'src': src, 'out': out, 'summary': summary, 'log': log, 'key': key,
                'template': _read(_one(os.path.join(TEMPLATES, key), '*.ASN'))}
    finally:
        shutil.rmtree(root)


def _one(directory, pattern):
    import glob
    hits = glob.glob(os.path.join(directory, pattern))
    assert len(hits) == 1, hits
    return hits[0]


@pytest.fixture(scope='module', params=sorted(CASES))
def expanded(request):
    _need(os.path.join(INSTALL, 'Assn', '16L1927.ASN'), os.path.join(INSTALL, 'Stats', '16L1927.DAT'),
          os.path.join(TEMPLATES, request.param))
    return _expand_case(request.param)


def _rosters(asn, n_players):
    """{team key: (active ids, reserve ids)} of an association."""
    out = {}
    for _, p in asn.recs['r']:
        out[asn.key('r', p)] = X.roster_of(p, n_players)
    return out


def _new_abbr(expanded):
    return {t['abbrev'] for t in expanded['summary']['teams'] if t['new']}


def test_team_count_and_leagues(expanded):
    asn = AsnFile(expanded['out']['asn'])
    keys = sorted(asn.key('t', p) for _, p in asn.recs['t'])
    shape = CASES[expanded['key']][1]
    assert keys == list(range(1, sum(map(sum, shape)) + 1))
    assert [[len(d['teams']) for d in x['divs']] for x in X.structure_of(asn)] == shape
    assert _new_abbr(expanded) == {cstr(p, 0x45, 3) for _, p in asn.recs['t']} - \
        {cstr(p, 0x45, 3) for _, p in AsnFile(expanded['src']['asn']).recs['t']}


def test_new_teams_named_and_computer(expanded):
    asn = AsnFile(expanded['out']['asn'])
    by_abbr = {cstr(p, 0x45, 3): p for _, p in asn.recs['t']}
    names = {'PHO': 'Phoenix Desert Dogs', 'DEN': 'Denver Mile High', 'TBA': 'Tampa Bay Rays',
             'MIA': 'Miami Sea Breeze'}
    for abbr in _new_abbr(expanded):
        p = by_abbr[abbr]
        assert cstr(p, 0x12, 32) == names[abbr]
        assert p[0x0c] == 0                                    # Computer
        assert cstr(p, 0x34, 17) == ''                         # no manager yet


def test_original_teams_keep_name_manager_park(expanded):
    src = AsnFile(expanded['src']['asn'])
    out = AsnFile(expanded['out']['asn'])
    by_abbr = {cstr(p, 0x45, 3): p for _, p in out.recs['t']}
    for _, p in src.recs['t']:
        q = by_abbr[cstr(p, 0x45, 3)]
        assert q[0x12:0x34] == p[0x12:0x34]
        assert q[0x34:0x45] == p[0x34:0x45]
        assert q[0x53:0x74] == p[0x53:0x74]
        assert q[0x0c] == p[0x0c]


def test_players_and_rosters(expanded):
    src = AsnFile(expanded['src']['asn'])
    out = AsnFile(expanded['out']['asn'])
    assert expanded['out']['pyr'] == expanded['src']['pyr']        # every player record, byte for byte
    n = (len(expanded['out']['pyr']) - RT.REC) // RT.REC
    before, after = _rosters(src, n), _rosters(out, n)
    src_key = {cstr(p, 0x45, 3): src.key('t', p) for _, p in src.recs['t']}
    out_key = {cstr(p, 0x45, 3): out.key('t', p) for _, p in out.recs['t']}
    # Every window id is a real player, and no player sits on two teams.
    seen = {}
    for team, (act, res) in after.items():
        for pid in act + res:
            assert X.PID0 <= pid < X.PID0 + n
            assert pid not in seen, 'player %d on teams %d and %d' % (pid, seen.get(pid, 0), team)
            seen[pid] = team
    # Legal rosters: 25 active, MIN_PIT pitchers, MIN_HIT fielders, for every team.
    recs = _pyr_recs(expanded['out']['pyr'])
    for team, (act, res) in after.items():
        assert len(act) == X.ACTIVE, team
        pit = sum(1 for p in act if recs[p - X.PID0][68] == 1)
        assert pit >= X.MIN_PIT, (team, pit)
        assert len(act) - pit >= X.MIN_HIT, team
    # Original teams keep their players except those drafted to the new teams; the free-agent pool is the only other
    # source of new ids.
    new_abbr = _new_abbr(expanded)
    for abbr, old_key in src_key.items():
        new_key = out_key[abbr]
        old_ids = set(before[old_key][0] + before[old_key][1])
        new_ids = set(after[new_key][0] + after[new_key][1])
        lost = old_ids - new_ids
        gained = new_ids - old_ids
        assert all(seen[p] in {out_key[a] for a in new_abbr} for p in lost), abbr
        assert gained <= set(X.read_pool(expanded['src']['pyf'])[0]), abbr
    assert len(seen) == sum(len(a) + len(r) for a, r in after.values())


def _pyr_recs(data):
    """The plain 192-byte records of PYR bytes (RT.read_pyr takes a path)."""
    _, inv = RT.cipher((data[0], data[1]))
    n = (len(data) - RT.REC) // RT.REC
    return [bytes(inv[b] for b in data[RT.REC + i * RT.REC:2 * RT.REC + i * RT.REC]) for i in range(n)]


def test_schedule_is_the_template_schedule(expanded):
    out = AsnFile(expanded['out']['asn'])
    tmpl = AsnFile(expanded['template'])
    assert out.recs['s'] and [p for _, p in out.recs['s']] == [p for _, p in tmpl.recs['s']]
    assert all(p[14] != 0 for _, p in out.recs['s'] if p[15] == 0)   # no regular game is played


def test_season_date_and_association(expanded):
    src = AsnFile(expanded['src']['asn'])
    out = AsnFile(expanded['out']['asn'])
    a_src, a_out = src.recs['a'][0][1], out.recs['a'][0][1]
    assert a_out[0x0a:0x12] == a_src[0x0a:0x12]          # the two season dates
    assert a_out[0x12:0x33] == a_src[0x12:0x33]          # the association name
    assert a_out[0x33:0x54] == a_src[0x33:0x54]          # the trophy


def test_stats_players_unchanged_and_index_consistent(expanded):
    src_rows = sorted(words for _, (mem, words) in ST.stat_records(expanded['src']['dat']).items()
                      if words[2] >= X.PID0)
    out_rows = sorted(words for _, (mem, words) in ST.stat_records(expanded['out']['dat']).items()
                      if words[2] >= X.PID0)
    assert out_rows == src_rows
    _index_ok(expanded['out']['dat'])
    _index_ok(expanded['out']['asn'])


def test_stat_team_rows_follow_the_team_slots():
    """16L1927 has no team rows, so the remap is checked on MLBPA97's own team rows: keys shifted into new slots."""
    path = os.path.join(INSTALL, 'Stats', 'mlbpa97.DAT')
    _need(path)
    dat = open(path, 'rb').read()
    keymap = {k: 29 - k for k in range(1, 29)}                    # a reversal: every team changes slot
    out = X.remap_stat_teams(dat, keymap)
    before = ST.stat_records(dat)
    after = ST.stat_records(out)
    assert len(after) == len(before)
    for off, (mem, words) in before.items():
        new = after[off][1]
        if words[2] < X.PID0:
            assert new[2] == keymap[words[2]] and new[:2] == words[:2] and new[3:] == words[3:]
        else:
            assert new == words
    _index_ok(out)


def test_transactions_follow_the_team_slots():
    """MLBPA97's own transaction records (live, plain): both team fields move with the team slot, nothing else does."""
    path = os.path.join(INSTALL, 'Assn', 'MLBPA97.ASN')
    _need(path)
    asn = AsnFile(open(path, 'rb').read())
    recs = [p for _, p in asn.recs['tr']]
    assert recs
    keymap = {k: 29 - k for k in range(1, 29)}
    moved = X.remap_transactions(recs, keymap)
    assert len(moved) == len(recs)
    for old, new in zip(recs, moved):
        assert new[:6] == old[:6] and new[7:12] == old[7:12] and new[13:19] == old[13:19] and new[20:] == old[20:]
        for team_at in (12, 19):
            want = keymap.get(old[team_at], old[team_at])
            assert new[team_at] == want
    assert any(o[12] in keymap for o in recs)


def test_draft_pool_and_free_agents_round_trip(expanded):
    ids, tail = X.read_pool(expanded['src']['pyf'])
    assert X.write_pool(ids, tail) == expanded['src']['pyf']
    ids, tail = X.read_pool(expanded['out']['pyf'])
    assert X.write_pool(ids, tail) == expanded['out']['pyf']
    mlb = os.path.join(INSTALL, 'Assn', 'MLBPA97.pyf')
    if os.path.exists(mlb):
        data = open(mlb, 'rb').read()
        ids, tail = X.read_pool(data)
        assert len(ids) == 494 and tail                     # the stale tail the game leaves after the list
        assert X.write_pool(ids, tail) == data


def test_pyr_round_trip(expanded):
    root = tempfile.mkdtemp(prefix='bbexpand-pyr-', dir=SCRATCH)
    try:
        path = os.path.join(root, 'x.PYR')
        hdr = expanded['out']['pyr'][:RT.REC]
        RT.write_pyr(path, hdr, _pyr_recs(expanded['out']['pyr']))
        assert open(path, 'rb').read() == expanded['out']['pyr']
    finally:
        shutil.rmtree(root)


def test_asn_records_round_trip(expanded):
    """Every enciphered record decodes and re-encodes to its own bytes, and the plain tables are kept as they are."""
    out = AsnFile(expanded['out']['asn'])
    _recs, by_mem, members, *_ = ctree.parse(expanded['out']['asn'])
    checked = 0
    for m in members:
        if m['kind'] != 'data':
            continue
        name = m['name'].rsplit('.', 1)[0]
        for r in by_mem.get(m['num'], []):
            raw = expanded['out']['asn'][r.off:r.off + r.pl]
            if not raw or raw[0] == 0xFF:
                continue
            assert out.enc(name, out.dec(name, raw)) == raw
            checked += 1
    assert checked > 100
    assert out.build() == expanded['out']['asn']


def test_rotation_and_lineup_ids_are_on_the_roster(expanded):
    out = AsnFile(expanded['out']['asn'])
    n = (len(expanded['out']['pyr']) - RT.REC) // RT.REC
    for _, p in out.recs['r']:
        ids = struct.unpack_from('<126H', p, 42)
        active = set(v for v in ids[:25] if v)
        reserve = set(ids[i] for i in range(25, 55, 2) if ids[i])
        for v in list(ids[77:86]) + list(ids[95:104]) + list(ids[113:119]) + list(ids[120:126]):
            if v and v != 0xFFFF:
                assert v in active or v in reserve, v
        assert all(X.PID0 <= v < X.PID0 + n for v in active | reserve)


def test_log_names_every_team(expanded):
    text = '\n'.join(expanded['log'])
    assert all(a in text for a in _new_abbr(expanded)) and 'refused' not in text
    assert expanded['summary']['template'] == expanded['key']


def _index_ok(data):
    """Every index tree: keys sorted, pointers are exactly the live records of its data member, counts agree."""
    _, by_mem, members, idxinfo, *_ = ctree.parse(data)[:5]
    checked = 0
    for idxmem, (trees, datam, base) in idxinfo.items():
        live = {r.hdr for r in by_mem.get(datam, []) if data[r.off] != 0xFF}
        for tr in trees:
            if not tr.klen:
                continue
            keys = [k for k, _ in tr.entries]
            assert keys == sorted(keys)
            assert {p for _, p in tr.entries} == live
            assert tr.count == len(live)
            checked += 1
    assert checked


# ---------------------------------------------------------------- refusals

def test_refuses_a_season_already_played():
    _need(os.path.join(INSTALL, 'Assn', 'MLBPA97.ASN'), os.path.join(INSTALL, 'Stats', 'mlbpa97.DAT'),
          os.path.join(TEMPLATES, 'T30'))
    root = tempfile.mkdtemp(prefix='bbexpand-played-', dir=SCRATCH)
    try:
        _copy('MLBPA97', root, ['MLBPA97.ASN', 'MLBPA97.PYR', 'MLBPA97.pyf'], 'mlbpa97.DAT')
        with pytest.raises(X.ExpandError, match='games played'):
            X.expand(root, 'MLBPA97', TEMPLATES, ['NL:Eastern:Phoenix:Desert Dogs:PHO'], 'NOPE1997')
        assert not os.path.exists(os.path.join(root, 'Assn', 'NOPE1997.ASN'))
    finally:
        shutil.rmtree(root)


def test_refuses_two_leagues_without_the_free_agents_to_seat_them():
    """Four new teams (T20) from the same 16 players per team: the draft cannot seat them and the pool is empty."""
    _need(os.path.join(INSTALL, 'Assn', '16L1927.ASN'), os.path.join(TEMPLATES, 'T20'))
    root = tempfile.mkdtemp(prefix='bbexpand-depth-', dir=SCRATCH)
    try:
        _copy('16L1927', root, ['16L1927.ASN', '16L1927.PYR', '16L1927.PYF'], '16L1927.DAT')
        adds = ['AL:1:Tampa:Bay Rays:TBA', 'AL:1:Miami:Sea Breeze:MIA', 'NL:1:Phoenix:Desert Dogs:PHO',
                'NL:1:Denver:Mile High:DEN']
        with pytest.raises(X.ExpandError, match='not enough free agents'):
            X.expand(root, '16L1927', TEMPLATES, adds, '20X1927')
        assert not os.path.exists(os.path.join(root, 'Assn', '20X1927.ASN'))
    finally:
        shutil.rmtree(root)


def _layout(al_adds, nl_adds):
    """16L1927's two leagues, one division each (keys 1..8 AL, 9..16 NL), with the given adds."""
    return [{'name': 'American League', 'abbrev': 'AL', 'divs': [{'name': '', 'teams': list(range(1, 9)),
                                                                  'adds': [X.parse_add(x) for x in al_adds]}]},
            {'name': 'National League', 'abbrev': 'NL', 'divs': [{'name': '', 'teams': list(range(9, 17)),
                                                                  'adds': [X.parse_add(x) for x in nl_adds]}]}]


def test_slots_of_the_two_league_shape_move_the_old_teams():
    """T20 from 16L1927's layout: the NL teams (old keys 9..16) move to slots 11..18, and the new teams take the last
    slots of their league. T18 (two NL adds) keeps every old key."""
    t20_slots = B.template_slots(AsnFile(_read(_one(os.path.join(TEMPLATES, 'T20'), '*.ASN'))),
                                 structure.SHAPES['T20'])
    keymap, new = X.assign_slots(_layout(['AL:1:Tampa:Bay Rays:TBA', 'AL:1:Miami:Sea Breeze:MIA'],
                                         ['NL:1:Phoenix:Desert Dogs:PHO', 'NL:1:Denver:Mile High:DEN']), t20_slots)
    assert keymap == {**{k: k for k in range(1, 9)}, **{k: k + 2 for k in range(9, 17)}}
    assert sorted(a['key'] for a in new) == [9, 10, 19, 20]
    t18_slots = B.template_slots(AsnFile(_read(_one(os.path.join(TEMPLATES, 'T18'), '*.ASN'))),
                                 structure.SHAPES['T18'])
    keymap, new = X.assign_slots(_layout([], ['NL:1:Phoenix:Desert Dogs:PHO', 'NL:1:Denver:Mile High:DEN']), t18_slots)
    assert keymap == {k: k for k in range(1, 17)}
    assert sorted(a['key'] for a in new) == [17, 18]


def test_refuses_a_shape_with_no_template():
    _need(os.path.join(INSTALL, 'Assn', '16L1927.ASN'))
    root = tempfile.mkdtemp(prefix='bbexpand-shape-', dir=SCRATCH)
    try:
        _copy('16L1927', root, ['16L1927.ASN', '16L1927.PYR', '16L1927.PYF'], '16L1927.DAT')
        # 16 + 1 gives [8],[9]: no shape in structure.SHAPES.
        with pytest.raises(X.ExpandError, match='no shape'):
            X.expand(root, '16L1927', TEMPLATES, ['NL:1:Phoenix:Desert Dogs:PHO'], '17X1927')
    finally:
        shutil.rmtree(root)


def test_refuses_a_duplicate_team():
    _need(os.path.join(INSTALL, 'Assn', '16L1927.ASN'))
    root = tempfile.mkdtemp(prefix='bbexpand-dup-', dir=SCRATCH)
    try:
        _copy('16L1927', root, ['16L1927.ASN', '16L1927.PYR', '16L1927.PYF'], '16L1927.DAT')
        with pytest.raises(X.ExpandError, match='already'):
            X.expand(root, '16L1927', TEMPLATES, ['NL:1:Phoenix:Desert Dogs:BOS', 'NL:1:Denver:Mile High:DEN'],
                     '18X1927')
        with pytest.raises(X.ExpandError, match='no league'):
            X.expand(root, '16L1927', TEMPLATES, ['XX:1:Phoenix:Desert Dogs:PHO', 'NL:1:Denver:Mile High:DEN'],
                     '18X1927')
    finally:
        shutil.rmtree(root)


def test_refuses_when_free_agents_run_out():
    """Eight new teams from a 16-team league of thin rosters: the draft cannot seat them and the pool is empty."""
    _need(os.path.join(INSTALL, 'Assn', '16L1927.ASN'), os.path.join(TEMPLATES, 'T24_3x8'))
    root = tempfile.mkdtemp(prefix='bbexpand-pool-', dir=SCRATCH)
    try:
        _copy('16L1927', root, ['16L1927.ASN', '16L1927.PYR', '16L1927.PYF'], '16L1927.DAT')
        adds = ['Negro:1:City%d:Team%d:T%02d' % (i, i, i) for i in range(8)]
        with pytest.raises(X.ExpandError, match='not enough free agents'):
            X.expand(root, '16L1927', TEMPLATES, adds, '24X1927', new_league='Negro')
        assert not os.path.exists(os.path.join(root, 'Assn', '24X1927.ASN'))
    finally:
        shutil.rmtree(root)


def test_parse_add_rejects_bad_specs():
    with pytest.raises(X.ExpandError):
        X.parse_add('NL:East:Phoenix:Desert Dogs')
    with pytest.raises(X.ExpandError):
        X.parse_add('NL:East:Phoenix:Desert Dogs:PHOENIX')
    with pytest.raises(X.ExpandError):
        X.parse_add('NL:East:A Very Long City Name Here:A Very Long Team Name Here:PHO')
    add = X.parse_add('nl:East:Phoenix:Desert Dogs:pho')
    assert add['name'] == 'Phoenix Desert Dogs' and add['abbrev'] == 'PHO'


def test_pool_codec_keeps_stale_tail():
    data = b'PPD:' + struct.pack('<Ih', 4, 1) + struct.pack('<H', 1297) + b'\x01\x02'
    ids, tail = X.read_pool(data)
    assert ids == [1297] and tail == b'\x01\x02'
    assert X.write_pool([1297, 1300], tail) == b'PPD:' + struct.pack('<Ih', 6, 2) + struct.pack('<2H', 1297, 1300) + tail
    with pytest.raises(X.ExpandError):
        X.read_pool(b'XXXX' + data[4:])
