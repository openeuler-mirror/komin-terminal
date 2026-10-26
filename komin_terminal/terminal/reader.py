"""PTY-backed interactive shell recording (feature F4).

:class:`TerminalReader` forks the user's shell attached to a pseudo-terminal
and mirrors the session: stdin is forwarded to the child, PTY output is both
echoed to stdout and accumulated into a permission-shielded recording file
(``0600``, under ``<XDG_CACHE_HOME>/komin/recordings/``). Recordings are
never uploaded automatically — they only enter a question context when the
user explicitly asks via ``km --with-output``.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import sys
import termios
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from komin_terminal.exceptions import TerminalCaptureError
from komin_terminal.utils.environment import Environment, get_environment

_RECORDINGS_DIR_NAME: str = "recordings"
_RECORDING_NAME_RE = re.compile(r"^terminal-\d{8}-\d{6}-\d{6}\.log$")
_CHUNK_SIZE: int = 65536

_FALLBACK_SHELL: str = "/bin/sh"
_TTY_REQUIRED_MESSAGE: str = "km shell 需要在交互终端（tty）中运行才能录制会话"


def recording_filename(now: datetime | None = None) -> str:
    """Build a lexicographically sortable recording file name.

    The timestamp layout keeps fixed-width fields so plain string sorting
    equals chronological ordering, which :func:`get_last_recording` relies
    on.

    Args:
        now: Timestamp to encode; the current UTC time when omitted.

    Returns:
        A name of the form ``terminal-YYYYMMDD-HHMMSS-ffffff.log``.
    """
    stamp = now or datetime.now(UTC)
    return f"terminal-{stamp.strftime('%Y%m%d-%H%M%S-%f')}.log"


class TerminalReader:
    """Records one interactive shell session inside a pseudo-terminal."""

    def __init__(
        self,
        shell: str | None = None,
        record_path: Path | None = None,
        env: Environment | None = None,
    ) -> None:
        """Prepare a recording session.

        The shell executable comes from the constructor argument, ``$SHELL``
        or ``/bin/sh`` — in that order. The default recording path is
        ``<user_cache_dir>/recordings/<UTC timestamp>.log``; the directory is
        created with mode ``0700`` and the file (created as a fresh, empty
        recording) with mode ``0600``.

        Args:
            shell: Shell executable to run; ``$SHELL`` or ``/bin/sh`` when
                omitted.
            record_path: Recording file; the timestamped default when omitted.
            env: Environment providing the cache directory; the process
                singleton when omitted.

        Raises:
            TerminalCaptureError: If the recording directory or file cannot
                be created, or ``shell`` is not an executable file.
        """
        self._env = env or get_environment()
        self._shell = shell or os.environ.get("SHELL") or _FALLBACK_SHELL
        shell_path = Path(self._shell)
        if not shell_path.is_file() or not os.access(self._shell, os.X_OK):
            raise TerminalCaptureError(
                f"shell 不可执行: {self._shell}", detail=self._shell
            )
        if record_path is None:
            record_path = (
                self._env.get_user_cache_dir()
                / _RECORDINGS_DIR_NAME
                / recording_filename()
            )
        self.record_path = record_path
        self._prepare_recording()

    def _prepare_recording(self) -> None:
        """Create the recording directory (0700) and empty file (0600)."""
        directory = self.record_path.parent
        try:
            self._env.ensure_dir(directory, 0o700)
            fd = os.open(
                self.record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except OSError as error:
            raise TerminalCaptureError(
                f"无法创建录制文件: {self.record_path}",
                detail=str(error),
            ) from error
        else:
            os.close(fd)

    def _stdin_is_tty(self) -> bool:
        """Return whether the process stdin is a terminal."""
        try:
            return bool(sys.stdin.isatty())
        except (AttributeError, OSError, ValueError):
            return False

    def run(self) -> int:
        """Record one shell session and return the child's exit code.

        A child shell is forked onto a fresh pseudo-terminal; the parent
        forwards stdin to the child, echoes PTY output to stdout and appends
        every output byte to the recording file. The session ends when the
        child shell exits (``exit``/Ctrl-D) and its exit code is returned.

        Returns:
            The shell's exit code (``128 + signal`` when signal-killed).

        Raises:
            TerminalCaptureError: When stdin is not a terminal or any OS
                level operation (pty allocation, fork, I/O) fails.
        """
        if not self._stdin_is_tty():
            raise TerminalCaptureError(_TTY_REQUIRED_MESSAGE)
        try:
            master_fd, slave_fd = pty.openpty()
        except OSError as error:
            raise TerminalCaptureError(
                "无法分配伪终端", detail=str(error)
            ) from error
        with suppress(OSError):
            self._sync_window_size(slave_fd)
        try:
            pid = os.fork()
        except OSError as error:
            os.close(master_fd)
            os.close(slave_fd)
            raise TerminalCaptureError(
                "无法派生交互 shell 进程", detail=str(error)
            ) from error
        if pid == 0:
            self._exec_child(slave_fd, master_fd)
        os.close(slave_fd)
        return self._forward_loop(master_fd, pid)

    def _sync_window_size(self, slave_fd: int) -> None:
        """Best-effort copy of the terminal window size onto the PTY."""
        stdin_fd = sys.stdin.fileno()
        workspace = b"\x00" * 8
        winsize = fcntl.ioctl(stdin_fd, termios.TIOCGWINSZ, workspace)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

    def _exec_child(self, slave_fd: int, master_fd: int) -> None:
        """Child half of :meth:`run`: attach and exec the shell.

        The inherited master descriptor must be closed, otherwise the PTY
        master never reaches EOF once the child dies. This function never
        returns; any failure exits the child with code 127.
        """
        try:
            if master_fd > 2:
                os.close(master_fd)
            os.close(0)
            os.close(1)
            os.close(2)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.execv(self._shell, [self._shell])
        except OSError:
            os._exit(127)
    def _forward_loop(self, master_fd: int, pid: int) -> int:
        """Forward stdin→PTY and PTY→stdout while recording, until exit."""
        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()
        status: int | None = None
        stdin_done = False
        record_stream: BinaryIO | None = None
        try:
            try:
                record_stream = os.fdopen(
                    os.open(
                        self.record_path, os.O_WRONLY | os.O_APPEND, 0o600
                    ),
                    "ab",
                )
            except OSError as error:
                raise TerminalCaptureError(
                    f"无法打开录制文件: {self.record_path}", detail=str(error)
                ) from error
            assert record_stream is not None
            while True:
                readable, _, _ = select.select(
                    [master_fd] + ([] if stdin_done else [stdin_fd]),
                    [],
                    [],
                    0.1,
                )
                for fd in readable:
                    if fd == master_fd:
                        try:
                            data = os.read(master_fd, _CHUNK_SIZE)
                        except OSError:
                            data = b""
                        if not data:
                            continue
                        self._echo_and_record(record_stream, stdout_fd, data)
                    else:
                        try:
                            data = os.read(stdin_fd, _CHUNK_SIZE)
                        except OSError:
                            data = b""
                        if not data:
                            stdin_done = True
                            continue
                        try:
                            os.write(master_fd, data)
                        except OSError:
                            stdin_done = True
                reaped, status = os.waitpid(pid, os.WNOHANG)
                if reaped:
                    self._drain_master(record_stream, stdout_fd, master_fd)
                    break
        finally:
            if record_stream is not None:
                record_stream.close()
            with suppress(OSError):
                os.close(master_fd)
        if status is None:
            try:
                _, status = os.waitpid(pid, 0)
            except OSError as error:
                raise TerminalCaptureError(
                    "等待 shell 退出失败", detail=str(error)
                ) from error
        assert status is not None
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        return 128 + os.WTERMSIG(status)

    @staticmethod
    def _echo_and_record(stream: BinaryIO, stdout_fd: int, data: bytes) -> None:
        """Echo one chunk to stdout and append it to the recording."""
        with suppress(OSError):
            os.write(stdout_fd, data)
        stream.write(data)
        stream.flush()

    @staticmethod
    def _drain_master(stream: BinaryIO, stdout_fd: int, master_fd: int) -> None:
        """Non-blockingly consume the PTY tail after the shell exited."""
        try:
            ready, _, _ = select.select([master_fd], [], [], 0.2)
        except OSError:
            return
        if not ready:
            return
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        while True:
            try:
                tail = os.read(master_fd, _CHUNK_SIZE)
            except OSError:
                break
            if not tail:
                break
            TerminalReader._echo_and_record(stream, stdout_fd, tail)

    def read_recorded(self) -> str:
        """Return the full recorded text; ``""`` when nothing was recorded.

        Returns:
            The raw recording content (may contain ANSI sequences).

        Raises:
            TerminalCaptureError: If the recording exists but cannot be read.
        """
        try:
            return self.record_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""
        except OSError as error:
            raise TerminalCaptureError(
                f"无法读取录制文件: {self.record_path}",
                detail=str(error),
            ) from error


def get_last_recording(env: Environment | None = None) -> Path | None:
    """Return the path of the most recent recording, if any.

    Candidates are matched by the timestamped file name (not by mtime) so
    the result is deterministic regardless of file-system metadata.

    Args:
        env: Environment providing the cache directory; the process
            singleton when omitted.

    Returns:
        The newest recording path, or ``None`` when none exists.
    """
    directory = (env or get_environment()).get_user_cache_dir() / _RECORDINGS_DIR_NAME
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    recordings = [
        entry
        for entry in entries
        if entry.is_file() and _RECORDING_NAME_RE.match(entry.name)
    ]
    if not recordings:
        return None
    return max(recordings, key=lambda entry: entry.name)
