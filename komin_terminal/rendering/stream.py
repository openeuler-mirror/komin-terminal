"""Streaming buffered Markdown rendering.

:class:`StreamRenderer` accumulates chunks and renders incrementally only at
safe boundaries (blank line separators outside code fences, and closed code
fences) so half-parsed Markdown structures are never emitted early. Core
invariant: feeding chunks incrementally then :meth:`StreamRenderer.finish`
yields the same visible text as rendering the whole input at once.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable

from komin_terminal.rendering.formatting import visible_text
from komin_terminal.rendering.markdown import MarkdownRenderer

_FENCE_RE: re.Pattern[str] = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _default_writer(text: str) -> None:
    """Write rendered output to stdout (default sink)."""
    sys.stdout.write(text)


class StreamRenderer:
    """Incrementally renders streamed Markdown chunks to a writer.

    Attributes:
        renderer: The underlying one-shot Markdown renderer.
    """

    def __init__(
        self, renderer: MarkdownRenderer, writer: Callable[[str], None] = _default_writer
    ) -> None:
        """Initialize the stream renderer.

        Args:
            renderer: Renderer used for every flushed buffer segment.
            writer: Sink for rendered output; defaults to stdout.
        """
        self._renderer = renderer
        self._writer = writer
        self._buffer = ""
        self._emitted = False
        self._finished = False

    def feed(self, chunk: str) -> None:
        """Accumulate a chunk and flush every complete safe segment.

        Args:
            chunk: The next streamed text fragment.
        """
        if self._finished or not chunk:
            return
        self._buffer += chunk
        while True:
            boundary = self._find_flush_boundary()
            if boundary is None:
                break
            segment = self._buffer[:boundary]
            self._buffer = self._buffer[boundary:]
            self._emit(self._renderer.render(segment))

    def finish(self) -> None:
        """Flush the remaining buffer; idempotent."""
        if self._finished:
            return
        self._finished = True
        if self._buffer:
            self._emit(self._renderer.render(self._buffer))
            self._buffer = ""

    def _emit(self, rendered: str) -> None:
        """Write a rendered segment, joining segments like block breaks."""
        if not visible_text(rendered).strip():
            return
        if self._emitted:
            self._writer("\n\n")
        self._writer(rendered)
        self._emitted = True

    def _find_flush_boundary(self) -> int | None:
        """Find the latest safe flush position in the buffer.

        Safe positions are the end of a blank line outside code fences and
        the end of a closing fence line. Returns ``None`` when no complete
        safe boundary exists yet.

        Returns:
            Byte offset into the buffer, or ``None``.
        """
        in_fence = False
        fence_char = ""
        fence_length = 0
        last_boundary: int | None = None
        offset = 0
        for line in self._buffer.splitlines(keepends=True):
            stripped = line.strip()
            match = _FENCE_RE.match(line)
            if match:
                marker = match.group(1)
                if not in_fence:
                    in_fence = True
                    fence_char = marker[0]
                    fence_length = len(marker)
                elif (
                    marker[0] == fence_char
                    and len(marker) >= fence_length
                    and stripped == marker
                    and line.endswith("\n")
                ):
                    in_fence = False
                    last_boundary = offset + len(line)
            elif not in_fence and stripped == "" and line.endswith("\n") and offset > 0:
                last_boundary = offset + len(line)
            offset += len(line)
        return last_boundary
