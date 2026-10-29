"""SSE (Server-Sent Events) parsing for streaming chat completions."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

import httpx


@dataclass(frozen=True)
class StreamEvent:
    """One event produced while consuming a streaming response."""

    kind: Literal["chunk", "done", "error"]
    content: str = ""


class SSEParser:
    """Parse OpenAI-compatible SSE lines into :class:`StreamEvent` objects.

    Only ``data:`` lines carry payloads; empty lines, comment lines
    (starting with ``:``) and any other SSE field lines are ignored. A
    ``data: [DONE]`` line terminates the stream with a ``done`` event.
    Malformed payloads yield ``error`` events without aborting iteration.
    """

    def parse(self, lines: Iterable[str]) -> Iterator[StreamEvent]:
        """Parse a sequence of SSE lines.

        Args:
            lines: Raw SSE lines, typically from ``iter_lines()``.

        Yields:
            Chunk events with delta content, a single done event at the
            ``[DONE]`` marker, and error events for malformed payloads.
        """
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
                continue
            if stripped == "data: [DONE]":
                yield StreamEvent(kind="done")
                return
            payload = stripped[len("data:") :].strip()
            content = self._extract_content(payload)
            if content is None:
                yield StreamEvent(kind="error")
                continue
            if content == "":
                continue
            yield StreamEvent(kind="chunk", content=content)

    def parse_response(self, response: httpx.Response) -> Iterator[StreamEvent]:
        """Parse the SSE body of an httpx response.

        Args:
            response: The streaming response to consume.

        Yields:
            The same events as :meth:`parse`, fed from ``iter_lines()``.
        """
        yield from self.parse(response.iter_lines())

    @staticmethod
    def _extract_content(payload: str) -> str | None:
        """Extract the delta content from one ``data:`` payload.

        Args:
            payload: The JSON payload after the ``data:`` prefix.

        Returns:
            The chunk text, ``""`` when the chunk carries no content (empty
            or missing delta, or an empty ``choices`` list such as a trailing
            usage-only chunk), or ``None`` when the payload is malformed.
        """
        try:
            obj = json.loads(payload)
            choices = obj["choices"]
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            return None
        if not isinstance(choices, list):
            return None
        if not choices:
            return ""
        try:
            delta = choices[0]["delta"]
        except (KeyError, IndexError, TypeError, AttributeError):
            return None
        if not isinstance(delta, dict):
            return None
        value = delta.get("content")
        if value is None:
            return ""
        if not isinstance(value, str):
            return None
        return value


__all__ = ["SSEParser", "StreamEvent"]
