"""deploy.sh ships every news and work/lahman module the sidecar imports, plus every news data file."""
import ast
import fnmatch
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / 'hosting' / 'deploy.sh'


def deploy_text(repo):
    return (repo / 'hosting' / 'deploy.sh').read_text(encoding='utf-8')


def work_modules(repo):
    """Names of work/<name>.py modules reachable by imports from news/*.py and work/lahman/*.py."""
    seeds = [repo / 'news'] + [repo / 'work' / 'lahman']
    mods = set()
    queue = []
    for seed in seeds:
        for path in sorted(seed.glob('*.py')):
            if path.parent.name == 'tests':
                continue
            queue.append(path)
    seen = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                cand = repo / 'work' / (name.split('.')[0] + '.py')
                if cand.is_file():
                    mods.add(cand.stem)
                    queue.append(cand)
    return mods


def missing_work(deploy_text, mods):
    """work module names not shipped as the literal "$REPO/work/<name>.py"."""
    return sorted(m for m in mods if '"$REPO/work/%s.py"' % m not in deploy_text)


def unmatched_data(deploy_text, names):
    """Tracked non-.py news files no news --include pattern matches."""
    news_block = deploy_text[deploy_text.index('news=$(rsync'):deploy_text.index('news+=')]
    patterns = re.findall(r"--include='([^']+)'", news_block)
    out = []
    for name in names:
        if not any(fnmatch.fnmatch(name, pat) for pat in patterns):
            out.append(name)
    return out


def test_work_imports_shipped():
    mods = work_modules(REPO)
    assert mods, 'import walk found no work modules; the walk is broken'
    assert 'ctree' in mods
    missing = missing_work(deploy_text(REPO), mods)
    assert not missing, 'deploy.sh does not ship work modules: ' + ', '.join(missing)


def test_work_walk_not_vacuous(tmp_path):
    copy = tmp_path / 'repo'
    for sub in ('hosting', 'news', 'work'):     # only what the walk reads (the main checkout also holds worktrees)
        shutil.copytree(REPO / sub, copy / sub, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'tests'))
    text = deploy_text(copy).replace('"$REPO/work/stats.py"', '')
    assert text != deploy_text(REPO), 'deploy.sh copy never contained "$REPO/work/stats.py"'
    mods = work_modules(copy)
    missing = missing_work(text, mods)
    assert 'stats' in missing, 'removing the stats.py line should report stats, got: ' + repr(missing)


def test_news_data_files_shipped():
    tracked = subprocess.run(['git', 'ls-files', 'news'], cwd=REPO, check=True,
                             capture_output=True, text=True).stdout.splitlines()
    names = []
    for rel in tracked:
        base = Path(rel).name
        base_path = Path(rel)
        if len(base_path.parts) != 2:
            continue  # news/tests/... and future subdirectories are not shipped
        if base.startswith('.') or base.endswith('.py'):
            continue
        names.append(base)
    assert names, 'no tracked non-.py news files found; the check is vacuous'
    unmatched = unmatched_data(deploy_text(REPO), names)
    assert not unmatched, 'deploy.sh news rsync does not ship: ' + ', '.join(unmatched)


def test_unmatched_data_helper_reports():
    assert unmatched_data(deploy_text(REPO), ['salary_table.json']) == []
    assert unmatched_data(deploy_text(REPO), ['salary_table.json', 'ratings_table.json']) == \
        ['ratings_table.json']
