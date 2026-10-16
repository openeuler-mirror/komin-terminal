"""HTTP layer for the AI backend: session, query, retry and SSE streaming."""

from __future__ import annotations

from komin_terminal.daemon.http.adapters import RetryAdapter
from komin_terminal.daemon.http.query import ChatQuery, QueryExecutor, build_messages
from komin_terminal.daemon.http.session import HttpSession
from komin_terminal.daemon.http.stream import SSEParser, StreamEvent

__all__ = [
    "ChatQuery",
    "HttpSession",
    "QueryExecutor",
    "RetryAdapter",
    "SSEParser",
    "StreamEvent",
    "build_messages",
]
