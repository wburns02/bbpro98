"""Whole-file writes that never leave a torn file: a temp file in the same directory, flushed and synced, then renamed
over the target. A symlinked target is resolved first so the link keeps pointing at the new bytes, and the target's
permission bits carry over. Used by the patch tools, which rewrite game DLLs, SHELL.VOL and button art in place."""
import os


def write_atomic(path, data):
    real = os.path.realpath(path)
    d, base = os.path.split(real)
    try:
        mode = os.stat(real).st_mode & 0o7777
    except FileNotFoundError:
        mode = None
    tmp = os.path.join(d, '.%s.%d.tmp' % (base, os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644 if mode is None else mode)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, real)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return real
