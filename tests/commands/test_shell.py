"""Tests for the km shell placeholder command (phase 9 feature)."""

from __future__ import annotations

from typing import Any

import pytest


def test_shell_placeholder_notification(
    cli_main: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """`km shell` prints the phase-9 placeholder and exits 0."""
    code = cli_main(["shell"])
    assert code == 0
    assert "phase 9" in capsys.readouterr().err


def test_shell_flags_parse_and_succeed(
    cli_main: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both future flags parse cleanly and keep the exit code at 0."""
    code = cli_main(["shell", "--enable-record", "--show-last"])
    assert code == 0
    assert "phase 9" in capsys.readouterr().err
