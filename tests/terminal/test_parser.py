"""Unit tests for :class:`TerminalParser` — entirely offline.

Every case feeds a synthetically constructed raw escape-sequence string into
the parser; no subprocess or terminal is involved.
"""

from __future__ import annotations

import pytest
from komin_terminal.terminal.parser import TerminalParser


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("plain text", "plain text", id="plain-text"),
        pytest.param("\x1b[31mred\x1b[0m", "red", id="ansi-color-stripped"),
        pytest.param("abc\rd", "dbc", id="carriage-return-overwrite"),
        pytest.param("10%\r20%\r100%", "100%", id="progress-bar-rewrite"),
        pytest.param("abc\r\n\x1b[1Adef", "def", id="cursor-up-rewrite"),
        pytest.param("", "", id="empty-input"),
        pytest.param("  padded  ", "  padded", id="trailing-whitespace-stripped"),
    ],
)
def test_parse_cases(raw: str, expected: str) -> None:
    """The parser reconstructs the final visible text for each raw stream."""
    result = TerminalParser().parse(raw)
    assert result == expected


def test_scrolling_beyond_screen_lines() -> None:
    """Content pushed past the screen bottom scrolls the oldest rows away."""
    parser = TerminalParser(columns=20, lines=5)
    result = parser.parse("1\r\n2\r\n3\r\n4\r\n5\r\n6\r\n")
    assert result == "3\n4\n5\n6"
    assert "1" not in result
    assert "2" not in result


def test_custom_columns_wrap_long_lines() -> None:
    """A narrow screen wraps output into multiple display rows."""
    parser = TerminalParser(columns=5, lines=10)
    result = parser.parse("abcdefgh")
    assert result == "abcde\nfgh"


def test_custom_lines_window_is_fixed() -> None:
    """Filling more rows than the window keeps exactly ``lines`` rows."""
    parser = TerminalParser(columns=20, lines=3)
    result = parser.parse("a\r\nb\r\nc\r\nd\r\n")
    assert result == "c\nd"


def test_ansi_cursor_control_sequences_stripped() -> None:
    """Cursor positioning sequences do not leak into cleaned text."""
    raw = "\x1b[2J\x1b[Hhello\x1b[K"
    assert TerminalParser().parse(raw) == "hello"
