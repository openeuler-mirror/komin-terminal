"""Tests for komin_terminal.rendering.stream."""

from __future__ import annotations

import io

import pytest
from komin_terminal.rendering.formatting import visible_text
from komin_terminal.rendering.markdown import MarkdownRenderer
from komin_terminal.rendering.stream import StreamRenderer
from komin_terminal.rendering.theme import Theme

_DOC_SIMPLE = "# Title\n\nHello **world**.\n"

_DOC_CODE = "Intro line.\n\n```python\nx = 1\ny = 2\n```\n\nOutro line.\n"

_DOC_TABLE = "Before.\n\n| h1 | h2 |\n|----|----|\n| aa | bb |\n| cc | dd |\n\nAfter.\n"

_DOC_LISTS = "Top.\n\n- a\n- b\n    - b1\n\n1. one\n2. two\n\nBottom.\n"

_DOC_MIXED = (
    "# Guide\n\n"
    "Paragraph with **bold**, *italic*, `code` and [link](http://e.com).\n\n"
    "```sh\nls -l /tmp\n```\n\n"
    "> quote line\n\n"
    "| k | v |\n|---|---|\n| 1 | 2 |\n"
)

_DOC_CJK = "# 标题\n\n这是一段中文流式渲染测试，包含**粗体**与`行内代码`。\n\n结束。\n"

_ALL_DOCS = (_DOC_SIMPLE, _DOC_CODE, _DOC_TABLE, _DOC_LISTS, _DOC_MIXED, _DOC_CJK)


@pytest.fixture
def renderer() -> MarkdownRenderer:
    """Return a renderer at width 80 with the default theme."""
    return MarkdownRenderer(Theme.load("default"), width=80)


def _stream(renderer: MarkdownRenderer, doc: str, chunk_size: int | None) -> str:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    if chunk_size is None:
        for char in doc:
            stream.feed(char)
    else:
        for index in range(0, len(doc), chunk_size):
            stream.feed(doc[index : index + chunk_size])
    stream.finish()
    return buffer.getvalue()


@pytest.mark.parametrize("doc", _ALL_DOCS, ids=["simple", "code", "table", "lists", "mixed", "cjk"])
@pytest.mark.parametrize(
    "chunk_size", [None, 1, 2, 3, 5, 7, 16], ids=["char", *map(str, [1, 2, 3, 5, 7, 16])]
)
def test_stream_visible_text_matches_oneshot(
    renderer: MarkdownRenderer, doc: str, chunk_size: int | None
) -> None:
    oneshot = visible_text(renderer.render(doc))
    streamed = visible_text(_stream(renderer, doc, chunk_size))
    assert streamed == oneshot


def test_fence_spanning_chunk_boundaries_not_broken(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.feed("```py\nx = 1\n")
    stream.feed("y = 2\n")
    stream.feed("```\n")
    stream.feed("\nafter.\n")
    stream.finish()
    visible = visible_text(buffer.getvalue())
    assert "```py\nx = 1\ny = 2\n```" in visible
    assert "after." in visible
    assert visible == visible_text(renderer.render("```py\nx = 1\ny = 2\n```\n\nafter.\n"))


def test_blank_line_inside_fence_does_not_flush(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.feed("```\nfirst\n\nsecond\n")
    assert buffer.getvalue() == ""
    stream.feed("```\n\ndone.\n")
    stream.finish()
    visible = visible_text(buffer.getvalue())
    assert "first\n\nsecond" in visible


def test_no_flush_in_middle_of_paragraph(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.feed("# Ti")
    assert buffer.getvalue() == ""
    stream.feed("tle\n\n")
    assert "Title" in visible_text(buffer.getvalue())


def test_finish_is_idempotent(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.feed("para.\n")
    stream.finish()
    first = buffer.getvalue()
    stream.finish()
    stream.finish()
    assert buffer.getvalue() == first


def test_feed_after_finish_is_ignored(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.feed("para.\n")
    stream.finish()
    done = buffer.getvalue()
    stream.feed("more **text**.\n")
    assert buffer.getvalue() == done


def test_finish_without_feed_writes_nothing(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.finish()
    assert buffer.getvalue() == ""


def test_whitespace_only_stream_writes_nothing(renderer: MarkdownRenderer) -> None:
    buffer = io.StringIO()
    stream = StreamRenderer(renderer, writer=buffer.write)
    stream.feed("   \n\n  \n")
    stream.finish()
    assert buffer.getvalue() == ""
