"""Tests for komin_terminal.rendering.renderers."""

from __future__ import annotations

import io

import pytest
from komin_terminal.rendering.colors import RESET
from komin_terminal.rendering.renderers import Renderers
from komin_terminal.rendering.theme import Theme


@pytest.fixture
def theme() -> Theme:
    """Return the built-in default theme."""
    return Theme.load("default")


@pytest.mark.parametrize(
    ("method", "prefix", "style_key"),
    [
        ("info", "ℹ", "info"),
        ("warning", "⚠", "warning"),
        ("error", "✗", "error"),
        ("notification", "➤", "notification"),
    ],
)
def test_message_format(theme: Theme, method: str, prefix: str, style_key: str) -> None:
    stream = io.StringIO()
    renderers = Renderers(theme, stream=stream)
    getattr(renderers, method)("hello")
    expected = f"{theme.get(style_key)}{prefix} hello{RESET}\n"
    assert stream.getvalue() == expected


@pytest.mark.parametrize(
    ("method", "prefix"),
    [("info", "ℹ"), ("warning", "⚠"), ("error", "✗"), ("notification", "➤")],
)
def test_each_message_ends_with_newline(theme: Theme, method: str, prefix: str) -> None:
    stream = io.StringIO()
    renderers = Renderers(theme, stream=stream)
    getattr(renderers, method)("msg")
    output = stream.getvalue()
    assert output.endswith("\n")
    assert output.count("\n") == 1
    assert prefix in output


def test_multiple_messages_write_one_line_each(theme: Theme) -> None:
    stream = io.StringIO()
    renderers = Renderers(theme, stream=stream)
    renderers.info("one")
    renderers.warning("two")
    renderers.error("three")
    renderers.notification("four")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 4
    assert "one" in lines[0]
    assert "two" in lines[1]
    assert "three" in lines[2]
    assert "four" in lines[3]


def test_empty_theme_styles_write_plain_prefixes() -> None:
    stream = io.StringIO()
    renderers = Renderers(Theme(name="empty", styles={}), stream=stream)
    renderers.info("plain")
    assert stream.getvalue() == "ℹ plain\n"
    assert "\x1b" not in stream.getvalue()
