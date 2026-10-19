"""Tests for ChatQuery, build_messages and QueryExecutor."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import httpx
import pytest
from komin_terminal.constants import SYSTEM_PROMPT
from komin_terminal.daemon.http import ChatQuery, QueryExecutor, RetryAdapter, build_messages
from komin_terminal.exceptions import AuthenticationError, BackendError

_TransportFactory = Callable[..., httpx.MockTransport]


def _noop_sleep(_: float) -> None:
    return None


def _client(transport: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(base_url="https://api.example.com/v1", transport=transport)


def _query(**overrides: object) -> ChatQuery:
    defaults: dict[str, object] = {
        "messages": build_messages("hello"),
        "model": "gpt-test",
    }
    defaults.update(overrides)
    return ChatQuery(**defaults)  # type: ignore[arg-type]


def test_build_messages_default_structure() -> None:
    messages = build_messages("hello")

    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["content"] == "hello"


def test_build_messages_custom_system_prompt() -> None:
    messages = build_messages("hi", system_prompt="Be terse.")

    assert messages[0] == {"role": "system", "content": "Be terse."}


def test_build_messages_with_context() -> None:
    messages = build_messages("hi", context="$ whoami\nroot")

    assert messages[1] == {"role": "user", "content": "hi\n\n[上下文]\n$ whoami\nroot"}


def test_build_messages_ignores_empty_context() -> None:
    messages = build_messages("hi", context="")

    assert messages[1] == {"role": "user", "content": "hi"}


def test_ask_parses_non_stream_response(fake_openai_transport: _TransportFactory) -> None:
    transport = fake_openai_transport(
        json_body={"choices": [{"message": {"content": "answer text"}}]}
    )
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    reply = executor.ask(_query())

    assert reply == "answer text"


def test_ask_sends_correct_request_body(fake_openai_transport: _TransportFactory) -> None:
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(record=recorded)
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    executor.ask(
        _query(messages=build_messages("hi", context="ctx"), temperature=0.3, stream=False)
    )

    body = json.loads(recorded[0].content)
    assert body["model"] == "gpt-test"
    assert body["stream"] is False
    assert body["temperature"] == 0.3
    assert body["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "hi\n\n[上下文]\nctx"},
    ]


def test_ask_invalid_json_body_raises_backend_error(
    fake_openai_transport: _TransportFactory,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="not json", request=request)
    )
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    with pytest.raises(BackendError):
        executor.ask(_query())


def test_ask_missing_content_raises_backend_error(
    fake_openai_transport: _TransportFactory,
) -> None:
    transport = fake_openai_transport(json_body={"choices": [{"message": {}}]})
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    with pytest.raises(BackendError):
        executor.ask(_query())


def test_ask_stream_yields_chunks_and_done(fake_openai_transport: _TransportFactory) -> None:
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(chunks=["您", "好"], record=recorded)
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    events = list(executor.ask_stream(_query()))

    assert [(e.kind, e.content) for e in events] == [("chunk", "您"), ("chunk", "好"), ("done", "")]
    body = json.loads(recorded[0].content)
    assert body["stream"] is True
    assert body["model"] == "gpt-test"
    assert body["temperature"] == 0.7


def test_ask_stream_maps_http_error(fake_openai_transport: _TransportFactory) -> None:
    transport = fake_openai_transport(status=401)
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    with pytest.raises(AuthenticationError):
        list(executor.ask_stream(_query()))


def test_ask_emits_audit_metadata_without_secrets(
    fake_openai_transport: _TransportFactory, caplog: pytest.LogCaptureFixture
) -> None:
    transport = fake_openai_transport(json_body={"choices": [{"message": {"content": "x"}}]})
    executor = QueryExecutor(_client(transport), RetryAdapter(sleep=_noop_sleep))

    with caplog.at_level(logging.INFO, logger="komin.audit"):
        executor.ask(_query(model="gpt-test"))

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "komin.audit"
    ]
    assert events
    event = events[0]
    assert event["event"] == "backend.request"
    assert event["model"] == "gpt-test"
    assert event["status"] == 200
    assert "elapsed" in event
    assert "sk-test" not in json.dumps(event)
