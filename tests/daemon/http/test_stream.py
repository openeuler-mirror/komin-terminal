"""Tests for SSEParser."""

from __future__ import annotations

import httpx
from komin_terminal.daemon.http import SSEParser, StreamEvent


def _response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=text,
        headers={"content-type": "text/event-stream"},
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )


def test_standard_chunks_then_done() -> None:
    lines = [
        'data: {"choices": [{"delta": {"content": "您"}}]}',
        "",
        'data: {"choices": [{"delta": {"content": "好"}}]}',
        "",
        "data: [DONE]",
        "",
    ]
    events = list(SSEParser().parse(lines))

    assert [(e.kind, e.content) for e in events] == [("chunk", "您"), ("chunk", "好"), ("done", "")]


def test_parse_response_wraps_iter_lines() -> None:
    response = _response('data: {"choices": [{"delta": {"content": "x"}}]}\n\ndata: [DONE]\n\n')

    events = list(SSEParser().parse_response(response))

    assert [(e.kind, e.content) for e in events] == [("chunk", "x"), ("done", "")]


def test_ignores_blank_comment_and_non_data_lines() -> None:
    lines = [
        "",
        ": keep-alive comment",
        "event: message",
        "id: 1",
        "retry: 100",
        'data: {"choices": [{"delta": {"content": "x"}}]}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [(e.kind, e.content) for e in events] == [("chunk", "x"), ("done", "")]


def test_malformed_json_yields_error_and_continues() -> None:
    lines = [
        "data: {not valid json",
        "",
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [e.kind for e in events] == ["error", "chunk", "done"]
    assert events[1].content == "ok"


def test_missing_choices_yields_error() -> None:
    lines = [
        'data: {"foo": "bar"}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [e.kind for e in events] == ["error", "done"]


def test_empty_choices_usage_chunk_is_skipped() -> None:
    lines = [
        'data: {"choices": [{"delta": {"content": "ok"}}]}',
        'data: {"choices": [], "usage": {"total_tokens": 5}}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [e.kind for e in events] == ["chunk", "done"]
    assert events[0].content == "ok"

def test_delta_without_content_is_skipped() -> None:
    lines = [
        'data: {"choices": [{"delta": {"role": "assistant"}}]}',
        "",
        'data: {"choices": [{"delta": {}}]}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [e.kind for e in events] == ["done"]


def test_delta_null_content_is_skipped() -> None:
    lines = [
        'data: {"choices": [{"delta": {"content": null}}]}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [e.kind for e in events] == ["done"]


def test_finish_reason_is_ignored() -> None:
    lines = [
        'data: {"choices": [{"delta": {"content": "x"}, "finish_reason": "stop"}]}',
        "",
        'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}',
        "",
        "data: [DONE]",
    ]
    events = list(SSEParser().parse(lines))

    assert [(e.kind, e.content) for e in events] == [("chunk", "x"), ("done", "")]


def test_done_stops_parsing() -> None:
    lines = [
        "data: [DONE]",
        "",
        'data: {"choices": [{"delta": {"content": "ignored"}}]}',
    ]
    events = list(SSEParser().parse(lines))

    assert [e.kind for e in events] == ["done"]


def test_stream_event_frozen() -> None:
    event = StreamEvent(kind="chunk", content="x")

    assert event.kind == "chunk"
    assert event.content == "x"
