"""Retired tools must refuse to run and write nothing."""
import importlib.util
from pathlib import Path

import pytest

WORK = Path(__file__).resolve().parents[2]


def test_patch_widen_is_retired_and_writes_nothing(monkeypatch):
    """Its offsets patch the Hall of Fame screen and it wrote the live install directly (work/PLAN_widen_oneshot.md)."""
    spec = importlib.util.spec_from_file_location('patch_widen', WORK / 'patch_widen.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    calls = []
    for name in ('patch_file', 'create_sts_file'):
        monkeypatch.setattr(m, name, lambda *a, _n=name, **k: calls.append(_n), raising=False)
    with pytest.raises(SystemExit) as e:
        m.main()
    assert 'retired' in str(e.value.code)
    assert not calls
