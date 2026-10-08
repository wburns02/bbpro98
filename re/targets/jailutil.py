"""Shared jail + safe-IO helpers for the referees (Claude-owned; GLM must not edit it).

- jail(): runs lane code under bwrap (--new-session against TIOCSTI injection, --unshare-all, only /usr + one workdir)
  inside a systemd user scope that caps total memory (tmpfs writes included) and task count, plus per-process prlimit.
- read_dir()/read_file(): read lane output only through O_NOFOLLOW fds relative to the referee-created workdir, so a
  symlinked out/ or output file can never redirect the referee to host paths.
- QUIET (set by --holdout): lane-controlled text (stderr, exception detail) is never printed, because holdout output
  is fed back to the lane.
"""
import os, stat, shutil, subprocess, sys

QUIET = '--holdout' in sys.argv


class RefError(ValueError):
    pass


def fail(msg):
    raise RefError(msg)


def jail_cmd(codec, workdir, args, *, name='codec.py', max_size, fsize=268435456, mem='8G', writable=True):
    """(cmd, env) for running codec as /w/name in the jail; jail() runs it to completion, a referee that talks to the
    lane over pipes (t3ref.py) Popens it"""
    st = os.lstat(codec)
    if not stat.S_ISREG(st.st_mode) or st.st_size > max_size:
        fail(f'{name} must be a regular file under {max_size} bytes')
    shutil.copyfile(codec, f'{workdir}/{name}', follow_symlinks=False)
    cmd = ['systemd-run', '--user', '--scope', '--quiet', '--collect', '-p', f'MemoryMax={mem}', '-p', 'MemorySwapMax=0',
           '-p', 'TasksMax=64', '--',
           'bwrap', '--new-session', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64',
           '/lib64', '--symlink', 'usr/bin', '/bin', '--proc', '/proc', '--dev', '/dev',
           '--bind' if writable else '--ro-bind', workdir, '/w', '--chdir', '/w',
           '--unshare-all', '--die-with-parent', '--clearenv', '--setenv', 'PATH', '/usr/bin',
           '/usr/bin/prlimit', f'--fsize={fsize}', '--as=6442450944', '--nofile=256', '--',
           '/usr/bin/python3', '-I', name] + list(args)
    env = {'PATH': '/usr/bin', 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}',
           'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{os.getuid()}/bus'}
    return cmd, env


def jail(codec, workdir, args, *, name='codec.py', max_size, timeout, fsize=268435456, mem='8G', writable=True):
    cmd, env = jail_cmd(codec, workdir, args, name=name, max_size=max_size, fsize=fsize, mem=mem, writable=writable)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        fail(f'{name} {args[0] if args else ""}: timeout {timeout}s')
    if r.returncode:
        fail(f'{name} {args[0] if args else ""} exit {r.returncode}' + ('' if QUIET else f': {r.stderr.strip()[-400:]}'))
    return r


def _read_fd(fd, limit, label):
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode): fail(f'{label}: not a regular file')
    if st.st_size > limit: fail(f'{label}: {st.st_size} bytes exceeds limit {limit}')
    chunks, total = [], 0
    while True:
        b = os.read(fd, 1 << 20)
        if not b: break
        total += len(b)
        if total > limit: fail(f'{label}: exceeds limit {limit}')
        chunks.append(b)
    return b''.join(chunks)


def read_file(workdir, rel, limit):
    """Read workdir/rel (rel = 'name' or 'sub/name'); no component may be a symlink."""
    parts = rel.split('/')
    if any(p in ('', '.', '..') for p in parts): fail(f'bad path {rel!r}')
    dfd = os.open(workdir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for p in parts[:-1]:
            nfd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
            os.close(dfd); dfd = nfd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        try:
            return _read_fd(fd, limit, parts[-1])
        finally:
            os.close(fd)
    except OSError as e:
        fail(f'{rel}: {e.strerror}')
    finally:
        os.close(dfd)


def list_dir(workdir, sub):
    """Names in workdir/sub, refusing a symlinked sub and any non-regular entry."""
    dfd = os.open(workdir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        sfd = os.open(sub, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
    except OSError as e:
        os.close(dfd); fail(f'{sub}/: {e.strerror}')
    try:
        names = os.listdir(sfd)
        if len(names) > 200_000: fail(f'{sub}/: too many files')
        for n in names:
            if not stat.S_ISREG(os.lstat(n, dir_fd=sfd).st_mode): fail(f'{sub}/{n}: not a regular file')
        return names
    finally:
        os.close(sfd); os.close(dfd)


def safe_read(path, limit):
    """Read a referee-chosen input path (data files); final component must not be a symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        return _read_fd(fd, limit, os.path.basename(path))
    finally:
        os.close(fd)


def err(e):
    """Exception text safe to print: generic under --holdout."""
    return 'failed (detail withheld on holdout)' if QUIET else str(e)[:300]
