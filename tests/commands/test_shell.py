"""Tests for the ``km shell`` command (terminal capture feature F4)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest
from komin_terminal.commands import shell as shell_module
from komin_terminal.exceptions import TerminalCaptureError


class StubRenderers:
    """Captures renderer calls instead of writing to a stream."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notifications: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def notification(self, msg: str) -> None:
        self.notifications.append(msg)


class FakeReader:
    """Records construction and returns a programmed exit code."""

    def __init__(self, path: Path = Path("/tmp/fake.log")) -> None:
        self.record_path = path
        self.run_calls = 0

    def run(self) -> int:
        self.run_calls += 1
        return 7


def _args(**kwargs: Any) -> argparse.Namespace:
    values: dict[str, Any] = {"enable_record": False, "show_last": False}
    values.update(kwargs)
    return argparse.Namespace(**values)


def test_enable_record_runs_reader_and_notifies_path(
    monkeypatch: pytest.MonkeyPatch, xdg_env: Path
) -> None:
    """``--enable-record`` records and reports the recording path."""
    del xdg_env
    fake = FakeReader(Path("/tmp/record.log"))
    monkeypatch.setattr(shell_module, "TerminalReader", lambda *a, **k: fake)
    renderers = StubRenderers()
    code = shell_module.run_shell(_args(enable_record=True), renderers)  # type: ignore[arg-type]
    assert code == 7
    assert fake.run_calls == 1
    assert any("/tmp/record.log" in message for message in renderers.notifications)


def test_enable_record_capture_error_returns_1(
    monkeypatch: pytest.MonkeyPatch, xdg_env: Path
) -> None:
    """A TerminalCaptureError during recording surfaces as exit code 1."""

    class ExplodingReader:
        record_path = Path("/tmp/boom.log")

        def run(self) -> int:
            raise TerminalCaptureError("无法分配伪终端")

    del xdg_env
    monkeypatch.setattr(shell_module, "TerminalReader", lambda *a, **k: ExplodingReader())
    renderers = StubRenderers()
    code = shell_module.run_shell(_args(enable_record=True), renderers)  # type: ignore[arg-type]
    assert code == 1
    assert "无法分配伪终端" in renderers.errors


def test_show_last_renders_cleaned_recording(
    monkeypatch: pytest.MonkeyPatch, xdg_env: Path
) -> None:
    """``--show-last`` paginates the ANSI-cleaned newest recording."""
    recording = xdg_env / "recording.log"
    recording.write_text("\x1b[31mred\x1b[0m line", encoding="utf-8")
    monkeypatch.setattr(shell_module, "get_last_recording", lambda: recording)
    paged: list[str] = []
    monkeypatch.setattr(shell_module, "paginate", paged.append)
    renderers = StubRenderers()
    code = shell_module.run_shell(_args(show_last=True), renderers)  # type: ignore[arg-type]
    assert code == 0
    assert paged == ["red line"]


def test_show_last_without_recording_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without any recording a warning is shown and the call succeeds."""
    monkeypatch.setattr(shell_module, "get_last_recording", lambda: None)
    renderers = StubRenderers()
    code = shell_module.run_shell(_args(show_last=True), renderers)  # type: ignore[arg-type]
    assert code == 0
    assert any("暂无可显示" in message for message in renderers.warnings)


def test_show_last_unreadable_recording_returns_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unreadable recordings surface as an error with exit code 1."""
    monkeypatch.setattr(
        shell_module,
        "get_last_recording",
        lambda: Path("/nonexistent/recording.log"),
    )
    renderers = StubRenderers()
    code = shell_module.run_shell(_args(show_last=True), renderers)  # type: ignore[arg-type]
    assert code == 1
    assert any("无法读取录制文件" in message for message in renderers.errors)


def test_no_arguments_prints_usage_hint() -> None:
    """Bare ``km shell`` prints the usage hint and exits 0."""
    renderers = StubRenderers()
    code = shell_module.run_shell(_args(), renderers)  # type: ignore[arg-type]
    assert code == 0
    assert any("km shell" in message for message in renderers.notifications)


def test_both_flags_conflict_returns_1() -> None:
    """Combining both flags is rejected with exit code 1."""
    renderers = StubRenderers()
    code = shell_module.run_shell(
        _args(enable_record=True, show_last=True), renderers  # type: ignore[arg-type]
    )
    assert code == 1
    assert any("不能同时使用" in message for message in renderers.errors)
