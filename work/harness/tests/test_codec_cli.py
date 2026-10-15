"""The codec CLIs (chunkgfx, shellgfx, dmp, dbmcodec) on garbage input: a one-line error, never a traceback."""
import subprocess
import sys
from pathlib import Path

import pytest

WORK = Path(__file__).resolve().parents[2]
GARBAGE = {'short': b'FNX:\x01\x02', 'bogus': b'\x05\x00\x00\x00\xff\xff\xff\x7f'}


def cli(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize('tool', ['chunkgfx', 'shellgfx', 'dmp'])
@pytest.mark.parametrize('kind', sorted(GARBAGE))
def test_garbage_gives_a_one_line_error(tmp_path, tool, kind):
    src = tmp_path / 'in.bin'
    src.write_bytes(GARBAGE[kind])
    out = tmp_path / ('out.json' if tool == 'dmp' else 'out')
    r = cli(WORK / ('%s.py' % tool), 'decode', src, out)
    assert r.returncode == 1 and 'Traceback' not in r.stderr and 'bad input' in r.stderr, r.stderr


@pytest.mark.parametrize('tool', ['chunkgfx', 'shellgfx', 'dmp', 'dbmcodec'])
def test_no_arguments_prints_usage(tool):
    r = cli(WORK / ('%s.py' % tool))
    assert r.returncode in (1, 2) and 'Traceback' not in r.stderr and 'usage' in r.stderr


def test_dbmcodec_makes_its_output_folder_and_round_trips_an_opaque_file(tmp_path):
    src = tmp_path / 'in.bin'
    src.write_bytes(GARBAGE['bogus'])
    out = tmp_path / 'new' / 'dir'
    r = cli(WORK / 'dbmcodec.py', 'decode', src, out)
    assert r.returncode == 0 and 'Traceback' not in r.stderr, r.stderr
    back = tmp_path / 'back.bin'
    r = cli(WORK / 'dbmcodec.py', 'encode', out, back)
    assert r.returncode == 0 and back.read_bytes() == GARBAGE['bogus']
