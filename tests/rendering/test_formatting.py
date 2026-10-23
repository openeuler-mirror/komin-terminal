"""Tests for komin_terminal.rendering.formatting."""

from __future__ import annotations

import io
import sys

import pytest
from komin_terminal.rendering.colors import RESET, Color, Style, ansi
from komin_terminal.rendering.formatting import (
    display_width,
    get_terminal_width,
    resolve_width,
    truncate,
    visible_text,
    wrap_to_width,
)


def test_get_terminal_width_returns_default_when_not_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert get_terminal_width() == 80


def test_get_terminal_width_custom_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert get_terminal_width(default=132) == 132


def test_get_terminal_width_without_tty_ignores_columns_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setenv("COLUMNS", "999")
    assert get_terminal_width(default=80) == 80


def test_resolve_width_zero_auto_detects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert resolve_width(0, default=80) == 80


def test_resolve_width_positive_used_verbatim() -> None:
    assert resolve_width(120, default=80) == 120


def test_resolve_width_negative_treated_as_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert resolve_width(-3, default=64) == 64


def test_display_width_ascii() -> None:
    assert display_width("hello") == 5


def test_display_width_cjk_counts_double() -> None:
    assert display_width("中文") == 4
    assert display_width("中a文") == 5


def test_display_width_combining_marks_zero() -> None:
    assert display_width("e\u0301") == 1


def test_visible_text_strips_ansi() -> None:
    styled = f"{ansi(Style.BOLD, Color.RED)}text{RESET}"
    assert visible_text(styled) == "text"


def test_wrap_ascii_at_width() -> None:
    assert wrap_to_width("hello world", 5) == "hello\nworld"


def test_wrap_preserves_existing_newlines() -> None:
    assert wrap_to_width("ab\ncd", 10) == "ab\ncd"


def test_wrap_cjk_boundary() -> None:
    assert wrap_to_width("中文中文", 4) == "中文\n中文"


def test_wrap_mixed_cjk_and_ascii_boundary() -> None:
    assert wrap_to_width("中文a", 5) == "中文a"
    assert wrap_to_width("中文a", 4) == "中文\na"


def test_wrap_long_cjk_string() -> None:
    assert wrap_to_width("中" * 5, 4) == "中中\n中中\n中"


def test_wrap_zero_or_negative_width_returns_text() -> None:
    text = "some long text"
    assert wrap_to_width(text, 0) == text
    assert wrap_to_width(text, -1) == text


def test_wrap_reopens_style_after_break() -> None:
    styled = f"{ansi(Style.BOLD)}abcdef{RESET}"
    wrapped = wrap_to_width(styled, 3)
    lines = wrapped.split("\n")
    assert len(lines) == 2
    assert visible_text(lines[0]) == "abc"
    assert visible_text(lines[1]) == "def"
    assert lines[1].startswith("\x1b[1m")
    assert visible_text(wrapped).replace("\n", "") == "abcdef"


def test_wrap_does_not_reopen_after_reset() -> None:
    styled = f"{ansi(Style.BOLD)}ab{RESET}cd"
    wrapped = wrap_to_width(styled, 2)
    lines = wrapped.split("\n")
    assert visible_text(lines[1]) == "cd"
    assert not lines[1].startswith("\x1b[1m")


def test_truncate_shorter_text_unchanged() -> None:
    assert truncate("abc", 10) == "abc"


def test_truncate_equal_width_unchanged() -> None:
    assert truncate("abcde", 5) == "abcde"


def test_truncate_longer_text_adds_ellipsis() -> None:
    result = truncate("abcdefgh", 5)
    assert result == "abcd…"
    assert display_width(result) == 5


def test_truncate_cjk_width_respected() -> None:
    result = truncate("中文字符串", 5)
    assert display_width(result) <= 5
    assert result.endswith("…")


def test_truncate_zero_width_returns_empty() -> None:
    assert truncate("abc", 0) == ""


def test_truncate_custom_ellipsis() -> None:
    assert truncate("abcdefgh", 5, ellipsis="...") == "ab..."
