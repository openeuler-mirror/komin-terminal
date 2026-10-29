"""Tests for RetryAdapter and map_http_error."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from komin_terminal.daemon.http import RetryAdapter
from komin_terminal.daemon.http.adapters import map_http_error
from komin_terminal.exceptions import (
    AuthenticationError,
    BackendError,
    ModelNotFoundError,
    NetworkError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TimeoutError_,
)

_TransportFactory = Callable[..., httpx.MockTransport]


def _noop_sleep(_: float) -> None:
    return None


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.example.com/v1/chat/completions")


def _client(transport: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(base_url="https://api.example.com/v1", transport=transport)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = _request()
    return httpx.HTTPStatusError(
        "error", request=request, response=httpx.Response(status, request=request)
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, ModelNotFoundError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
    ],
)
def test_map_http_error_status_codes(status: int, expected: type[BackendError]) -> None:
    error = map_http_error(_status_error(status))

    assert isinstance(error, expected)
    assert error.status_code == status


def test_map_http_error_timeout() -> None:
    error = map_http_error(httpx.TimeoutException("slow"))

    assert isinstance(error, TimeoutError_)
    assert error.status_code is None


def test_map_http_error_network() -> None:
    error = map_http_error(httpx.ConnectError("refused"))

    assert isinstance(error, NetworkError)


def test_map_http_error_message_has_no_api_key() -> None:
    error = map_http_error(_status_error(401))

    assert "Bearer" not in error.message
    assert "sk-" not in error.message
    assert "authorization" not in error.message.lower()


def test_status_mapping_via_send(fake_openai_transport: _TransportFactory) -> None:
    adapter = RetryAdapter(max_retries=1, sleep=_noop_sleep)

    for status, expected in [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, ModelNotFoundError),
    ]:
        transport = fake_openai_transport(status=status)
        with pytest.raises(expected):
            adapter.send(_client(transport), _request())


def test_retry_then_success_records_backoff(fake_openai_transport: _TransportFactory) -> None:
    sleeps: list[float] = []
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(fail_times=2, record=recorded)
    adapter = RetryAdapter(max_retries=3, backoff_base=1.0, sleep=sleeps.append)

    response = adapter.send(_client(transport), _request())

    assert response.status_code == 200
    assert len(recorded) == 3
    assert sleeps == [1.0, 2.0]


def test_retry_exhaustion_raises_mapped_error(fake_openai_transport: _TransportFactory) -> None:
    sleeps: list[float] = []
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(status=429, fail_times=0, record=recorded)
    adapter = RetryAdapter(max_retries=3, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(RateLimitError) as excinfo:
        adapter.send(_client(transport), _request())

    assert len(recorded) == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert excinfo.value.status_code == 429


def test_fourxx_gets_no_retries(fake_openai_transport: _TransportFactory) -> None:
    sleeps: list[float] = []
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(status=400, fail_times=0, record=recorded)
    adapter = RetryAdapter(max_retries=3, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(BackendError):
        adapter.send(_client(transport), _request())

    assert len(recorded) == 1
    assert sleeps == []


def test_timeout_retried_then_mapped(fake_openai_transport: _TransportFactory) -> None:
    del fake_openai_transport
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("read timed out")

    adapter = RetryAdapter(max_retries=2, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(TimeoutError_):
        adapter.send(_client(httpx.MockTransport(handler)), _request())

    assert sleeps == [1.0, 2.0]


def test_network_error_retried_then_mapped(fake_openai_transport: _TransportFactory) -> None:
    del fake_openai_transport
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = RetryAdapter(max_retries=2, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(NetworkError):
        adapter.send(_client(httpx.MockTransport(handler)), _request())

    assert sleeps == [1.0, 2.0]


def test_send_stream_returns_open_response_without_reading_body() -> None:
    consumed: list[str] = []

    def generate() -> object:
        consumed.append("c0")
        yield b'data: {"choices":[{"delta":{"content":"c0"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=generate(), request=request)

    adapter = RetryAdapter(max_retries=1, sleep=_noop_sleep)

    response = adapter.send_stream(_client(httpx.MockTransport(handler)), _request())

    assert response.status_code == 200
    assert consumed == []
    assert "data: [DONE]" in list(response.iter_lines())
    assert consumed == ["c0"]
    response.close()


def test_send_stream_retries_on_5xx_then_success(
    fake_openai_transport: _TransportFactory,
) -> None:
    sleeps: list[float] = []
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(chunks=["ok"], fail_times=2, record=recorded)
    adapter = RetryAdapter(max_retries=3, backoff_base=1.0, sleep=sleeps.append)

    response = adapter.send_stream(_client(transport), _request())

    assert response.status_code == 200
    assert len(recorded) == 3
    assert sleeps == [1.0, 2.0]
    response.close()


def test_send_stream_fourxx_gets_no_retries(
    fake_openai_transport: _TransportFactory,
) -> None:
    sleeps: list[float] = []
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(status=401, record=recorded)
    adapter = RetryAdapter(max_retries=3, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(AuthenticationError):
        adapter.send_stream(_client(transport), _request())

    assert len(recorded) == 1
    assert sleeps == []


def test_send_stream_retry_exhaustion_raises_mapped_error(
    fake_openai_transport: _TransportFactory,
) -> None:
    sleeps: list[float] = []
    recorded: list[httpx.Request] = []
    transport = fake_openai_transport(status=429, record=recorded)
    adapter = RetryAdapter(max_retries=3, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(RateLimitError) as excinfo:
        adapter.send_stream(_client(transport), _request())

    assert len(recorded) == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert excinfo.value.status_code == 429


def test_send_stream_network_error_retried_then_mapped() -> None:
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = RetryAdapter(max_retries=2, backoff_base=1.0, sleep=sleeps.append)

    with pytest.raises(NetworkError):
        adapter.send_stream(_client(httpx.MockTransport(handler)), _request())

    assert sleeps == [1.0, 2.0]
