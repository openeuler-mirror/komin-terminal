"""Shared fixtures for the daemon test suite (HTTP layer, reused later)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

import httpx
import pytest


@pytest.fixture
def fake_openai_transport() -> Callable[..., httpx.MockTransport]:
    """Factory producing :class:`httpx.MockTransport` fake OpenAI backends.

    The factory supports streaming SSE responses (``chunks``), plain JSON
    responses (``json_body``), a fixed non-200 status, a number of initial
    failures with a configurable failure status, and recording every request
    received by the transport.

    Args:
        chunks: Chunk texts; when provided the transport answers with an SSE
            stream followed by ``data: [DONE]``.
        status: Final status code for successful responses.
        fail_times: Number of initial responses using ``fail_status``.
        fail_status: Status code used for the initial failures.
        json_body: Non-streaming JSON payload for success responses.
        record: Optional list receiving every :class:`httpx.Request`.

    Returns:
        A factory; call it to obtain a configured ``MockTransport``.
    """

    def factory(
        *,
        chunks: list[str] | None = None,
        status: int = 200,
        fail_times: int = 0,
        fail_status: int = 503,
        json_body: Mapping[str, object] | None = None,
        record: list[httpx.Request] | None = None,
    ) -> httpx.MockTransport:
        remaining = {"n": fail_times}

        def handler(request: httpx.Request) -> httpx.Response:
            if record is not None:
                record.append(request)
            if remaining["n"] > 0:
                remaining["n"] -= 1
                return httpx.Response(fail_status, request=request)
            if status != 200:
                return httpx.Response(status, request=request)
            if chunks is not None:
                lines = [
                    f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}"
                    for chunk in chunks
                ]
                lines.append("data: [DONE]")
                body = "\n".join(lines) + "\n\n"
                return httpx.Response(
                    200,
                    text=body,
                    headers={"content-type": "text/event-stream"},
                    request=request,
                )
            payload = json_body or {"choices": [{"message": {"content": "ok"}}]}
            return httpx.Response(200, json=payload, request=request)

        return httpx.MockTransport(handler)

    return factory
