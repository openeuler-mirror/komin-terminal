"""Tests for komin_terminal.rendering.animation."""

from __future__ import annotations

import io
import time

import pytest
from komin_terminal.rendering.animation import FRAMES, Spinner


class _TtyBuffer(io.StringIO):
    """A StringIO that claims to be a terminal."""

    def isatty(self) -> bool:
        """Return True so the spinner animates."""
        return True


def test_non_tty_start_produces_no_output() -> None:
    stream = io.StringIO()
    spinner = Spinner(message="waiting", stream=stream, interval=0.01)
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    assert stream.getvalue() == ""


def test_disabled_spinner_produces_no_output() -> None:
    stream = _TtyBuffer()
    spinner = Spinner(message="waiting", enabled=False, stream=stream, interval=0.01)
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    assert stream.getvalue() == ""


def test_tty_like_stream_produces_frames() -> None:
    stream = _TtyBuffer()
    spinner = Spinner(message="thinking", stream=stream, interval=0.01)
    spinner.start()
    time.sleep(0.05)
    spinner.stop()
    output = stream.getvalue()
    assert any(frame in output for frame in FRAMES)
    assert "thinking" in output


def test_stop_clears_residual_frame() -> None:
    stream = _TtyBuffer()
    spinner = Spinner(message="working", stream=stream, interval=0.01)
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    assert stream.getvalue().endswith("\r\x1b[K")


def test_stop_is_idempotent() -> None:
    stream = _TtyBuffer()
    spinner = Spinner(message="x", stream=stream, interval=0.01)
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    first = stream.getvalue()
    spinner.stop()
    spinner.stop()
    assert stream.getvalue() == first


def test_stop_without_start_is_noop() -> None:
    stream = _TtyBuffer()
    spinner = Spinner(message="x", stream=stream, interval=0.01)
    spinner.stop()
    assert stream.getvalue() == ""


def test_context_manager_starts_and_stops() -> None:
    stream = _TtyBuffer()
    with Spinner(message="ctx", stream=stream, interval=0.01) as spinner:
        assert isinstance(spinner, Spinner)
        time.sleep(0.05)
    output = stream.getvalue()
    assert any(frame in output for frame in FRAMES)
    assert output.endswith("\r\x1b[K")


def test_double_start_runs_single_animation() -> None:
    stream = _TtyBuffer()
    spinner = Spinner(message="x", stream=stream, interval=0.01)
    spinner.start()
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    assert stream.getvalue().endswith("\r\x1b[K")


def test_tty_detection_via_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: True)
    spinner = Spinner(message="patched", stream=stream, interval=0.01)
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    assert "patched" in stream.getvalue()
