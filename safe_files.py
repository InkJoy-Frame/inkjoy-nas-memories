"""Open user-supplied paths without following symlinks.

Directory listing and file reads share this module. Each path component is
opened with O_NOFOLLOW from a directory descriptor, so a symlink is rejected
even when its text still looks like it sits inside the allowed root. The
descriptor's real path is checked again and must stay inside that root.
"""

import errno
import os
import stat

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class UnsafePath(Exception):
    """Symlink, traversal, or a resolved path outside the allowed root."""


class MissingPath(Exception):
    """Nothing is at this path, or it is not the expected kind of file."""


_DIR_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_DIRECTORY', 0)
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW


def _fd_path(fd):
    proc = f'/proc/self/fd/{fd}'
    try:
        return os.readlink(proc)
    except OSError:
        pass
    if fcntl is not None and hasattr(fcntl, 'F_GETPATH'):
        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
        if isinstance(raw, bytes):
            return raw.split(b'\x00', 1)[0].decode('utf-8', 'surrogateescape')
    return None


def _inside(base_real, candidate):
    if not candidate:
        return False
    base = os.path.realpath(base_real)
    try:
        cand = os.path.realpath(candidate)
        return os.path.commonpath([base, cand]) == base
    except ValueError:
        return False


def _check_fd(base_real, fd):
    located = _fd_path(fd)
    if not _inside(base_real, located):
        raise UnsafePath()


def open_root(base_dir):
    real = os.path.realpath(base_dir)
    if not os.path.isdir(real):
        raise MissingPath(real)
    try:
        fd = os.open(real, _DIR_FLAGS)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise UnsafePath() from None
        raise
    try:
        _check_fd(real, fd)
    except Exception:
        os.close(fd)
        raise
    return fd, real


def split_parts(base_real, user_path):
    """Return components inside base_real. `..` may not leave the root."""
    text = '' if user_path is None else str(user_path).replace('\\', '/').strip()
    if '\x00' in text:
        raise UnsafePath()
    base = os.path.normpath(os.path.realpath(base_real))
    if text.startswith('/') or (len(text) >= 2 and text[1] == ':'):
        norm = os.path.normpath(text)
    else:
        norm = os.path.normpath(os.path.join(base, text or '.'))
    try:
        if os.path.commonpath([base, norm]) != base:
            raise UnsafePath()
    except ValueError:
        raise UnsafePath() from None
    if norm == base:
        return []
    prefix = base + os.sep
    if not norm.startswith(prefix):
        raise UnsafePath()
    parts = []
    for part in norm[len(prefix):].split(os.sep):
        if part in ('', '.'):
            continue
        if part == '..' or '/' in part or '\\' in part or '\x00' in part:
            raise UnsafePath()
        parts.append(part)
    return parts


def _open_child(dir_fd, name, flags):
    if not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
        raise UnsafePath()
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise MissingPath(name) from None
    except OSError as exc:
        # O_NOFOLLOW reports a symlink as ELOOP. ENOTDIR means a file sat
        # where a directory was required, which is also not a readable target.
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafePath() from None
        raise


def _descend(root_fd, base_real, parts, want):
    """Return an owned fd. root_fd stays open for the caller."""
    if not parts:
        if want != 'dir':
            raise MissingPath()
        fd = os.dup(root_fd)
        try:
            _check_fd(base_real, fd)
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise UnsafePath()
            return fd
        except Exception:
            os.close(fd)
            raise

    current = None
    try:
        parent = root_fd
        for index, name in enumerate(parts):
            last = index == len(parts) - 1
            flags = _FILE_FLAGS if last and want == 'file' else _DIR_FLAGS
            current = _open_child(parent, name, flags)
            try:
                _check_fd(base_real, current)
            except Exception:
                os.close(current)
                current = None
                raise
            if parent is not root_fd:
                os.close(parent)
            parent = current
        mode = os.fstat(current).st_mode
        if stat.S_ISLNK(mode):
            raise UnsafePath()
        if want == 'dir' and not stat.S_ISDIR(mode):
            raise UnsafePath()
        if want == 'file' and not stat.S_ISREG(mode):
            raise MissingPath()
        owned = current
        current = None
        return owned
    finally:
        if current is not None:
            os.close(current)


def _open_relative(base_dir, user_path, want):
    root_fd, base_real = open_root(base_dir)
    try:
        parts = split_parts(base_real, user_path)
        return _descend(root_fd, base_real, parts, want)
    finally:
        os.close(root_fd)


def directory_is_real(base_dir, user_path):
    """True only for a real directory. A symlink raises UnsafePath."""
    try:
        fd = _open_relative(base_dir, user_path, 'dir')
    except MissingPath:
        return False
    os.close(fd)
    return True


def open_regular(base_dir, user_path):
    """Return an owned read-only fd of a regular file. Caller closes it."""
    return _open_relative(base_dir, user_path, 'file')


def ensure_directory(base_dir, user_path):
    """Create missing directories. Refuse to walk or create through a symlink."""
    root_fd, base_real = open_root(base_dir)
    parent = root_fd
    parent_is_root = True
    try:
        for name in split_parts(base_real, user_path):
            try:
                child = _open_child(parent, name, _DIR_FLAGS)
            except MissingPath:
                try:
                    os.mkdir(name, 0o755, dir_fd=parent)
                except FileExistsError:
                    pass
                child = _open_child(parent, name, _DIR_FLAGS)
            try:
                _check_fd(base_real, child)
            except Exception:
                os.close(child)
                raise
            if not parent_is_root:
                os.close(parent)
            parent = child
            parent_is_root = False
        if not stat.S_ISDIR(os.fstat(parent).st_mode):
            raise UnsafePath()
    finally:
        if parent is not None and not parent_is_root:
            os.close(parent)
        os.close(root_fd)


def list_directory(base_dir, user_path):
    """List one directory. Symlinks are omitted and never opened."""
    root_fd, base_real = open_root(base_dir)
    dir_fd = None
    try:
        parts = split_parts(base_real, user_path)
        dir_fd = _descend(root_fd, base_real, parts, 'dir')
    finally:
        os.close(root_fd)
    prefix = '/'.join(split_parts(base_real, user_path))
    try:
        entries = []
        for name in os.listdir(dir_fd):
            if not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
                continue
            try:
                info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode):
                continue
            rel = f'{prefix}/{name}' if prefix else name
            if stat.S_ISDIR(info.st_mode):
                entries.append({'name': name, 'rel': rel, 'kind': 'dir', 'size': 0})
            elif stat.S_ISREG(info.st_mode):
                entries.append({'name': name, 'rel': rel, 'kind': 'file', 'size': info.st_size})
        return entries
    finally:
        os.close(dir_fd)


def iter_regular_files(base_dir, user_path, skip_dir=None):
    """Yield regular files under user_path. Do not descend into or return symlinks.

    The directory is opened before the first yield, so a symlink is rejected
    at the call, not only after iteration starts.
    """
    root_fd, base_real = open_root(base_dir)
    dir_fd = None
    try:
        parts = split_parts(base_real, user_path)
        dir_fd = _descend(root_fd, base_real, parts, 'dir')
    except Exception:
        if dir_fd is not None:
            os.close(dir_fd)
        raise
    finally:
        os.close(root_fd)
    prefix = '/'.join(parts)

    def generate():
        try:
            yield from _walk(dir_fd, base_real, prefix, skip_dir)
        finally:
            os.close(dir_fd)

    return generate()


def _walk(dir_fd, base_real, prefix, skip_dir):
    try:
        names = os.listdir(dir_fd)
    except OSError:
        return
    files = []
    subdirs = []
    for name in names:
        if not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
            continue
        try:
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode):
            continue
        if stat.S_ISDIR(info.st_mode):
            if skip_dir and skip_dir(name):
                continue
            subdirs.append(name)
        elif stat.S_ISREG(info.st_mode):
            files.append(name)
    for name in sorted(files, key=str.lower):
        yield f'{prefix}/{name}' if prefix else name
    for name in sorted(subdirs, key=str.lower):
        child = None
        try:
            child = _open_child(dir_fd, name, _DIR_FLAGS)
            _check_fd(base_real, child)
        except (UnsafePath, MissingPath, OSError):
            if child is not None:
                os.close(child)
            continue
        child_prefix = f'{prefix}/{name}' if prefix else name
        try:
            yield from _walk(child, base_real, child_prefix, skip_dir)
        finally:
            os.close(child)
