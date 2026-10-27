"""Tests for :class:`TerminalReader` and :func:`get_last_recording`.

The PTY session tests drive the reader as a subprocess: the driver wraps the
piped stdin in a fake tty-like text stream (``isatty() → True``) so the
recording loop forwards real bytes through a genuine ``pty.openpty()`` pair
between the driver and a ``/bin/sh`` child. No network or root is required;
the whole file is skipped when no ``sh`` executable exists.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC
from pathlib import Path

import pytest
from komin_terminal.exceptions import TerminalCaptureError
from komin_terminal.terminal.reader import TerminalReader, get_last_recording, recording_filename
from komin_terminal.utils.environment import Environment

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None, reason="no POSIX sh executable available"
)

_NAME_RE = r"^terminal-\d{8}-\d{6}-\d{6}\.log$"

_DRIVER = r"""
import io
import os
import sys
from pathlib import Path


class _TtyTextIOWrapper(io.TextIOWrapper):
    def isatty(self) -> bool:
        return True


raw = os.fdopen(0, "rb", buffering=0)
sys.stdin = _TtyTextIOWrapper(raw, encoding="utf-8", errors="replace")

from komin_terminal.terminal.reader import TerminalReader

code = TerminalReader(shell="/bin/sh", record_path=Path(sys.argv[1])).run()
sys.exit(code)
"""


def _run_recording_subprocess(
    record_path: Path, data: bytes
) -> subprocess.CompletedProcess[bytes]:
    """Run the reader driver feeding ``stdin_bytes`` and return the result."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    return subprocess.run(
        [sys.executable, "-c", _DRIVER, str(record_path)],
        input=data,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_recorded_session_exit_code_output_and_permissions(
    xdg_env: Path,
) -> None:
    """A real ``/bin/sh`` session is recorded with correct code, content and mode."""
    record_path = xdg_env / "session.log"
    completed = _run_recording_subprocess(record_path, b"echo hello; exit 0\n")
    assert completed.returncode == 0
    content = record_path.read_text(encoding="utf-8", errors="replace")
    assert "hello" in content
    assert (record_path.stat().st_mode & 0o777) == 0o600
    assert record_path.parent.stat().st_mode & 0o777 == 0o700
    assert b"hello" in completed.stdout


def test_recorded_session_propagates_non_zero_exit_code(xdg_env: Path) -> None:
    """The child shell's exit code is returned verbatim."""
    record_path = xdg_env / "session.log"
    completed = _run_recording_subprocess(record_path, b"exit 3\n")
    assert completed.returncode == 3


def test_recording_directory_auto_created(xdg_env: Path) -> None:
    """Constructing the reader creates nested directories with mode 0700."""
    record_path = xdg_env / "nested" / "sub" / "capture.log"
    TerminalReader(shell="/bin/sh", record_path=record_path)
    assert record_path.is_file()
    assert (record_path.stat().st_mode & 0o777) == 0o600
    assert (record_path.parent.stat().st_mode & 0o777) == 0o700


def test_default_recording_path_under_cache_dir(xdg_env: Path) -> None:
    """The default path lands in ``<XDG_CACHE_HOME>/komin/recordings/``."""
    env = Environment()
    reader = TerminalReader(shell="/bin/sh", env=env)
    expected_dir = env.get_user_cache_dir() / "recordings"
    assert reader.record_path.parent == expected_dir
    assert re.match(_NAME_RE, reader.record_path.name)
    assert reader.record_path.is_file()


def test_non_tty_stdin_raises_capture_error(
    xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running without an interactive stdin fails with TerminalCaptureError."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    reader = TerminalReader(shell="/bin/sh", record_path=xdg_env / "capture.log")
    with pytest.raises(TerminalCaptureError, match="交互终端"):
        reader.run()


def test_read_recorded_missing_file_returns_empty(xdg_env: Path) -> None:
    """``read_recorded`` degrades to ``""`` for a missing recording."""
    reader = TerminalReader(shell="/bin/sh", record_path=xdg_env / "missing.log")
    assert reader.read_recorded() == ""


def test_get_last_recording_empty_directory(xdg_env: Path) -> None:
    """No recordings exist yet, so ``None`` is returned."""
    assert get_last_recording(Environment()) is None


def test_get_last_recording_picks_newest_by_name(xdg_env: Path) -> None:
    """The newest timestamped file name wins regardless of mtimes."""
    env = Environment()
    directory = env.get_user_cache_dir() / "recordings"
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for name in (
        "terminal-20260820-100000-000001.log",
        "terminal-20260820-120000-000001.log",
        "terminal-20260820-110000-000001.log",
    ):
        record = directory / name
        record.write_text("content", encoding="utf-8")
        records.append(record)
    early, newest, middle = records
    now = 2_000_000_000
    early.touch((now, now))
    middle.touch((now, now))
    newest.touch((1, 1))
    junk = directory / "notes.txt"
    junk.write_text("ignore me", encoding="utf-8")
    assert get_last_recording(env) == newest


def test_get_last_recording_ignores_non_matching_files(xdg_env: Path) -> None:
    """Only files matching the timestamped naming scheme participate."""
    env = Environment()
    directory = env.get_user_cache_dir() / "recordings"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "session.terminal-20260820-100000-000001.log").write_text(
        "x", encoding="utf-8"
    )
    (directory / "terminal-20260820.log").write_text("x", encoding="utf-8")
    assert get_last_recording(env) is None


def test_recording_filename_matches_expected_layout() -> None:
    """Generated names obey the fixed-width timestamped pattern."""
    from datetime import datetime

    name = recording_filename(datetime(2026, 8, 21, 9, 5, 1, 123456, tzinfo=UTC))
    assert name == "terminal-20260821-090501-123456.log"
