"""Tests for komin_terminal.rendering.markdown."""

from __future__ import annotations

import io
import logging
import sys

import pytest
from komin_terminal.rendering.colors import RESET, Style, ansi
from komin_terminal.rendering.formatting import display_width, visible_text
from komin_terminal.rendering.markdown import MarkdownRenderer
from komin_terminal.rendering.theme import Theme

_MARKDOWN_LOGGER = "komin.rendering.markdown"


@pytest.fixture
def theme() -> Theme:
    """Return the built-in default theme."""
    return Theme.load("default")


@pytest.fixture
def renderer(theme: Theme) -> MarkdownRenderer:
    """Return a renderer at width 80 with the default theme."""
    return MarkdownRenderer(theme, width=80)


@pytest.mark.parametrize(
    ("markdown", "expected_visible", "expected_sequences"),
    [
        pytest.param("# Title", "# Title", ["\x1b[1;36m"], id="heading-h1"),
        pytest.param("### Deep", "### Deep", ["\x1b[1;36m"], id="heading-h3"),
        pytest.param("###### Six", "###### Six", ["\x1b[1;36m"], id="heading-h6"),
        pytest.param(
            "```python\nprint(1)\n```",
            "```python\nprint(1)\n```",
            ["\x1b[32m"],
            id="code-block-with-language",
        ),
        pytest.param(
            "```\nraw text\n```", "```\nraw text\n```", ["\x1b[32m"], id="code-block-bare"
        ),
        pytest.param(
            "```sh\necho $HOME && ls > /tmp/x\n```",
            "```sh\necho $HOME && ls > /tmp/x\n```",
            [],
            id="code-block-content-unescaped",
        ),
        pytest.param("use `ls -l` now", "use `ls -l` now", ["\x1b[33m"], id="inline-code"),
        pytest.param("some **strong** text", "some strong text", ["\x1b[1m"], id="bold"),
        pytest.param("an *emph* word", "an emph word", ["\x1b[3m"], id="italic"),
        pytest.param(
            "**bold and *italic* inside**", "bold and italic inside", ["\x1b[1m"], id="bold-italic"
        ),
        pytest.param("~~removed~~", "removed", ["\x1b[9m"], id="strikethrough"),
        pytest.param("- a\n- b\n    - b1", "• a\n• b\n  • b1", [], id="nested-unordered-list"),
        pytest.param("1. one\n2. two", "1. one\n2. two", [], id="ordered-list"),
        pytest.param(
            "| h1 | h2 |\n|----|----|\n| aa | bb |",
            "┌────┬────┐\n│ h1 │ h2 │\n├────┼────┤\n│ aa │ bb │\n└────┴────┘",
            ["\x1b[2m"],
            id="table",
        ),
        pytest.param(
            "[docs](http://example.com)",
            "docs (http://example.com)",
            ["\x1b[4;34m", "\x1b[2m"],
            id="link",
        ),
        pytest.param("> quoted words", "│ quoted words", [], id="blockquote"),
    ],
)
def test_render_fragments(
    renderer: MarkdownRenderer,
    markdown: str,
    expected_visible: str,
    expected_sequences: list[str],
) -> None:
    output = renderer.render(markdown)
    assert visible_text(output) == expected_visible
    for sequence in expected_sequences:
        assert sequence in output


def test_render_empty_input(renderer: MarkdownRenderer) -> None:
    assert renderer.render("") == ""


def test_render_whitespace_only_input(renderer: MarkdownRenderer) -> None:
    assert renderer.render("  \n\t\n ") == ""


def test_render_unclosed_fence_does_not_raise(renderer: MarkdownRenderer) -> None:
    output = renderer.render("```\ncode here")
    assert "code here" in visible_text(output)


def test_render_malformed_raw_html_degrades_to_source(
    renderer: MarkdownRenderer, caplog: pytest.LogCaptureFixture
) -> None:
    source = "<div>unclosed"
    with caplog.at_level(logging.WARNING, logger=_MARKDOWN_LOGGER):
        output = renderer.render(source)
    assert output == source
    assert any("degrading to plain text" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "markdown",
    [
        pytest.param("****", id="lone-emphasis-marks"),
        pytest.param("`unclosed", id="unclosed-inline-code"),
        pytest.param("[broken](<>)", id="broken-link"),
        pytest.param("| a |\n|---|\n| b | c | d |", id="ragged-table"),
        pytest.param("# 只有标题没有内容\n\n---", id="heading-and-hr"),
    ],
)
def test_render_malformed_never_raises(renderer: MarkdownRenderer, markdown: str) -> None:
    output = renderer.render(markdown)
    assert isinstance(output, str)


def test_paragraph_wraps_to_width(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=20)
    text = "word " * 30
    output = renderer.render(text.strip())
    for line in visible_text(output).split("\n"):
        assert display_width(line) <= 20


def test_cjk_paragraph_wraps_by_display_width(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=10)
    output = renderer.render("中" * 20)
    for line in visible_text(output).split("\n"):
        assert display_width(line) <= 10


def test_table_columns_adapt_to_width(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=30)
    markdown = (
        "| longheader1 | longheader2 | longheader3 |\n"
        "|-------------|-------------|-------------|\n"
        "| value-one | value-two | value-three |\n"
    )
    output = renderer.render(markdown)
    visible = visible_text(output)
    assert "┌" in visible and "┘" in visible
    border_chars = set("┌┬┐├┼┤└┴┘─│ ")
    rendered_content = sorted(ch for ch in visible if ch not in border_chars and ch != "\n")
    expected_content = sorted("longheader1longheader2longheader3value-onevalue-twovalue-three")
    assert rendered_content == expected_content
    for line in visible.split("\n"):
        assert display_width(line) <= 30


def test_heading_wraps_at_narrow_width(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=12)
    output = renderer.render("# a very long heading text")
    for line in visible_text(output).split("\n"):
        assert display_width(line) <= 12


def test_width_zero_resolves_to_default(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    renderer = MarkdownRenderer(theme)
    assert renderer.width == 80


def test_width_positive_used_verbatim(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=100)
    assert renderer.width == 100


def test_nested_styles_reopen_after_inner_reset(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=80)
    output = renderer.render("**a *b* c**")
    assert visible_text(output) == "a b c"
    assert f"{RESET}{ansi(Style.BOLD)}" in output


def test_link_without_url_renders_text(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=80)
    output = renderer.render("[plain](http://a.b)")
    assert visible_text(output) == "plain (http://a.b)"


def test_image_renders_alt_text(theme: Theme) -> None:
    renderer = MarkdownRenderer(theme, width=80)
    output = renderer.render("![alt text](http://a.b/img.png)")
    assert "alt text" in visible_text(output)


def test_multiple_blocks_joined_with_blank_line(renderer: MarkdownRenderer) -> None:
    output = renderer.render("para one\n\npara two")
    assert visible_text(output) == "para one\n\npara two"
