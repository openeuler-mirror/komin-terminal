"""File locking and atomic write helpers."""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkstemp
from typing import IO, Any

from komin_terminal.exceptions import KominError

_LOCK_POLL_INTERVAL_SECONDS: float = 0.05


def _acquire_exclusive_lock(handle: IO[Any], path: Path, timeout: float) -> None:
    """Poll for an exclusive flock on ``handle`` until ``timeout`` expires.

    Args:
        handle: Open file handle to lock.
        path: Path used in the timeout error detail.
        timeout: Maximum number of seconds to wait.

    Raises:
        KominError: If the lock is not acquired within ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise KominError(
                    f"Timed out waiting for exclusive file lock after {timeout}s",
                    detail=str(path),
                ) from None
            time.sleep(_LOCK_POLL_INTERVAL_SECONDS)


@contextmanager
def locked_file(path: Path, mode: str = "r", timeout: float = 5.0) -> Iterator[IO[Any]]:
    """Open ``path`` under an exclusive ``fcntl.flock`` lock.

    Args:
        path: File to open.
        mode: Open mode, as accepted by :meth:`pathlib.Path.open`.
        timeout: Maximum seconds to wait for the lock.

    Yields:
        The open file object while the lock is held.

    Raises:
        KominError: If the lock cannot be acquired within ``timeout`` seconds.
    """
    handle = path.open(mode)
    try:
        _acquire_exclusive_lock(handle, path, timeout)
        yield handle
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def write_atomic(path: Path, content: str, mode: int = 0o600) -> None:
    """Write ``content`` to ``path`` atomically.

    The content is written to a temporary file in the same directory, chmod
    to ``mode``, then moved into place with an atomic replace so readers only
    ever observe either the old or the new complete content.

    Args:
        path: Destination file path.
        content: Text content to write.
        mode: Permission bits applied to the file before replacement.
    """
    fd, tmp_name = mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.chmod(mode)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
