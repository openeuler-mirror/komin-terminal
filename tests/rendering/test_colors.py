"""Tests for komin_terminal.rendering.colors."""

from __future__ import annotations

import pytest
from komin_terminal.rendering.colors import RESET, Color, Style, ansi

_EXPECTED_16: tuple[tuple[Color, str], ...] = (
    (Color.BLACK, "\x1b[30m"),
    (Color.RED, "\x1b[31m"),
    (Color.GREEN, "\x1b[32m"),
    (Color.YELLOW, "\x1b[33m"),
    (Color.BLUE, "\x1b[34m"),
    (Color.MAGENTA, "\x1b[35m"),
    (Color.CYAN, "\x1b[36m"),
    (Color.WHITE, "\x1b[37m"),
    (Color.BRIGHT_BLACK, "\x1b[90m"),
    (Color.BRIGHT_RED, "\x1b[91m"),
    (Color.BRIGHT_GREEN, "\x1b[92m"),
    (Color.BRIGHT_YELLOW, "\x1b[93m"),
    (Color.BRIGHT_BLUE, "\x1b[94m"),
    (Color.BRIGHT_MAGENTA, "\x1b[95m"),
    (Color.BRIGHT_CYAN, "\x1b[96m"),
    (Color.BRIGHT_WHITE, "\x1b[97m"),
)


@pytest.mark.parametrize(("color", "expected"), _EXPECTED_16)
def test_sixteen_color_sequences(color: Color, expected: str) -> None:
    assert ansi(color) == expected


def test_reset_constant() -> None:
    assert RESET == "\x1b[0m"


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        (Style.BOLD, "\x1b[1m"),
        (Style.DIM, "\x1b[2m"),
        (Style.ITALIC, "\x1b[3m"),
        (Style.UNDERLINE, "\x1b[4m"),
        (Style.REVERSE, "\x1b[7m"),
        (Style.STRIKETHROUGH, "\x1b[9m"),
        (Style.RESET, "\x1b[0m"),
    ],
)
def test_style_sequences(style: Style, expected: str) -> None:
    assert ansi(style) == expected


def test_from_256_lower_bound() -> None:
    assert Color.from_256(0) == "\x1b[38;5;0m"


def test_from_256_upper_bound() -> None:
    assert Color.from_256(255) == "\x1b[38;5;255m"


def test_from_256_mid_value() -> None:
    assert Color.from_256(196) == "\x1b[38;5;196m"


@pytest.mark.parametrize("index", [-1, 256, 1000])
def test_from_256_out_of_range_raises(index: int) -> None:
    with pytest.raises(ValueError, match="out of range"):
        Color.from_256(index)


def test_ansi_combines_multiple_codes() -> None:
    assert ansi(Style.BOLD, Color.RED) == "\x1b[1;31m"


def test_ansi_combines_three_codes() -> None:
    assert ansi(Style.BOLD, Style.UNDERLINE, Color.CYAN) == "\x1b[1;4;36m"


def test_ansi_empty_returns_empty_string() -> None:
    assert ansi() == ""
