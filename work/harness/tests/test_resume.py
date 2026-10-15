"""expand_resume: builds install entries from a seasonloop snapshot (no game, Wine or /mnt/nvme)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingame  # noqa: E402


def snap(tmp_path, stem='30L2025', other='OTHER99', dup_case=False):
    d = tmp_path / 'snapx'
    assn = [f'{stem}.ASN', f'{stem}.PYR', f'{stem}.PYF', f'{stem}.PYC',
            f'{other}.ASN', 'readme.txt']
    if dup_case:
        assn.append(f'{stem.lower()}.asn')
    stats = [f'{stem}.DAT', f'{stem}.MS0', f'{stem}.H0101', f'{other}.DAT']
    for sub, names in (('Assn', assn), ('Stats', stats)):
        p = d / sub
        p.mkdir(parents=True)
        for n in names:
            (p / n).write_bytes(b'x')
    return str(d)


def full_plan(d, stem='30L2025'):
    return {'resume': {'dir': d, 'stem': stem}, 'install': {}}


def test_matches_case_skips_pyc_other_stems(tmp_path):
    d = snap(tmp_path)
    out = ingame.expand_resume(full_plan(d))
    names = sorted(out['install'])
    assert names == ['Assn/30L2025.ASN', 'Assn/30L2025.PYF', 'Assn/30L2025.PYR',
                     'Stats/30L2025.DAT', 'Stats/30L2025.H0101', 'Stats/30L2025.MS0']
    for key, src in out['install'].items():
        sub, name = key.split('/', 1)
        assert src == os.path.abspath(os.path.join(d, sub, name))
        assert os.path.isabs(src)
    assert 'Assn/30L2025.PYC' not in out['install']
    assert 'Assn/OTHER99.ASN' not in out['install']
    assert 'Stats/OTHER99.DAT' not in out['install']
    assert out['resume'] == full_plan(d)['resume']


def test_case_insensitive_stem(tmp_path):
    d = snap(tmp_path, dup_case=True)
    out = ingame.expand_resume(full_plan(d, '30l2025'))
    assert 'Assn/30L2025.ASN' in out['install']
    assert 'Assn/30l2025.asn' in out['install']


def test_explicit_install_wins(tmp_path):
    d = snap(tmp_path)
    mine = '/somewhere/else.ASN'
    plan = full_plan(d)
    plan['install'] = {'Assn/30L2025.ASN': mine, 'Stats/30L2025.DAT': '/keep.DAT'}
    out = ingame.expand_resume(plan)
    assert out['install']['Assn/30L2025.ASN'] == mine
    assert out['install']['Stats/30L2025.DAT'] == '/keep.DAT'
    assert 'Assn/30L2025.PYR' in out['install']


def test_no_resume_unchanged(tmp_path):
    plan = {'install': {'Assn/A.ASN': '/x'}}
    assert ingame.expand_resume(plan) == plan


def test_refuses_missing_dir(tmp_path):
    try:
        ingame.expand_resume(full_plan(str(tmp_path / 'nope')))
    except SystemExit as e:
        assert 'REFUSED' in str(e)
    else:
        assert False, 'no SystemExit'


def test_refuses_missing_asn(tmp_path):
    d = tmp_path / 'snap'
    (d / 'Assn').mkdir(parents=True)
    (d / 'Assn' / '30L2025.PYR').write_bytes(b'x')
    try:
        ingame.expand_resume(full_plan(str(d)))
    except SystemExit as e:
        assert 'REFUSED' in str(e)
    else:
        assert False, 'no SystemExit'


def test_refuses_no_assn_files(tmp_path):
    d = tmp_path / 'snap'
    (d / 'Assn').mkdir(parents=True)
    (d / 'Assn' / 'ZZZ.ASN').write_bytes(b'x')
    (d / 'Stats').mkdir()
    try:
        ingame.expand_resume(full_plan(str(d)))
    except SystemExit as e:
        assert 'REFUSED' in str(e)
    else:
        assert False, 'no SystemExit'


def test_refuses_stem_separator(tmp_path):
    d = snap(tmp_path)
    for bad in ('a/b', 'a\\b', '..x', 'x..'):
        try:
            ingame.expand_resume(full_plan(d, bad))
        except SystemExit as e:
            assert 'REFUSED' in str(e), bad
        else:
            assert False, f'no SystemExit for {bad}'
