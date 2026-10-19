"""Tests for HttpSession httpx.Client assembly."""

from __future__ import annotations

import ssl

import httpx
import pytest
from komin_terminal.config.schema import BackendConfig, ProxyConfig, TlsConfig
from komin_terminal.constants import DEFAULT_USER_AGENT
from komin_terminal.daemon.http import HttpSession


def _backend(**overrides: object) -> BackendConfig:
    defaults: dict[str, object] = {
        "url": "https://api.example.com/v1",
        "api_key": "sk-test-key",
        "model": "gpt-test",
    }
    defaults.update(overrides)
    return BackendConfig(**defaults)  # type: ignore[arg-type]


def _capture_ssl(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {"cafile": "not-called", "cert": "not-called"}
    real_create = ssl.create_default_context

    def fake_create(cafile: str | None = None, **_: object) -> ssl.SSLContext:
        captured["cafile"] = cafile
        return real_create()

    def fake_load_cert_chain(
        self: ssl.SSLContext, certfile: str, keyfile: str | None = None, **_: object
    ) -> None:
        captured["cert"] = (certfile, keyfile)

    monkeypatch.setattr(ssl, "create_default_context", fake_create)
    monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", fake_load_cert_chain)
    return captured


def _mounted(client: httpx.Client) -> dict[str, httpx.HTTPTransport]:
    """Map URL patterns to their transports for assertion convenience."""
    return {str(pattern.pattern): transport for pattern, transport in client._mounts.items()}


def test_default_client_mapping() -> None:
    session = HttpSession(_backend(timeout=42))
    client = session.create_client()

    assert str(client.base_url) == "https://api.example.com/v1/"
    assert client.timeout == httpx.Timeout(42)
    assert client.headers["Authorization"] == "Bearer sk-test-key"
    assert client.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert client._mounts == {}


def test_extra_headers_merged() -> None:
    session = HttpSession(_backend(extra_headers={"X-Custom": "value", "X-Other": "1"}))
    client = session.create_client()

    assert client.headers["X-Custom"] == "value"
    assert client.headers["X-Other"] == "1"


def test_extra_headers_cannot_override_authorization() -> None:
    session = HttpSession(_backend(extra_headers={"Authorization": "Bearer injected"}))
    client = session.create_client()

    assert client.headers["Authorization"] == "Bearer sk-test-key"


def test_proxy_split_mounts() -> None:
    session = HttpSession(
        _backend(proxy=ProxyConfig(http="http://proxy:8080", https="http://proxy:8443"))
    )
    client = session.create_client()

    mounted = _mounted(client)

    assert set(mounted) == {"http://", "https://"}
    http_transport = mounted["http://"]
    https_transport = mounted["https://"]
    http_url = http_transport._pool._proxy_url
    https_url = https_transport._pool._proxy_url
    assert (http_url.host, http_url.port) == (b"proxy", 8080)
    assert (https_url.host, https_url.port) == (b"proxy", 8443)


def test_partial_proxy_only_http() -> None:
    session = HttpSession(_backend(proxy=ProxyConfig(http="http://proxy:8080", https=None)))
    client = session.create_client()

    assert set(_mounted(client)) == {"http://"}


def test_tls_ca_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_ssl(monkeypatch)
    session = HttpSession(_backend(tls=TlsConfig(ca_bundle="/etc/ssl/custom-ca.pem")))
    session.create_client()

    assert captured["cafile"] == "/etc/ssl/custom-ca.pem"
    assert captured["cert"] == "not-called"


def test_mtls_both_required(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_ssl(monkeypatch)
    session = HttpSession(
        _backend(
            tls=TlsConfig(
                ca_bundle="/etc/ssl/ca.pem",
                client_cert="/etc/ssl/client.pem",
                client_key="/etc/ssl/client.key",
            )
        )
    )
    session.create_client()

    assert captured["cafile"] == "/etc/ssl/ca.pem"
    assert captured["cert"] == ("/etc/ssl/client.pem", "/etc/ssl/client.key")


def test_mtls_skipped_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_ssl(monkeypatch)
    session = HttpSession(
        _backend(tls=TlsConfig(client_cert="/etc/ssl/client.pem", client_key=None))
    )
    session.create_client()

    assert captured["cert"] == "not-called"


def test_no_tls_config_defaults_to_verify_true(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_ssl(monkeypatch)
    session = HttpSession(_backend(tls=None))
    session.create_client()

    assert captured["cafile"] is not None
    assert captured["cert"] == "not-called"


def test_api_key_only_in_authorization_header() -> None:
    session = HttpSession(_backend(extra_headers={"X-Custom": "v"}))
    client = session.create_client()
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}, request=request
        )

    client._transport = httpx.MockTransport(handler)
    client.post("/chat/completions", json={"model": "m"})

    request = recorded[0]
    assert request.headers["Authorization"] == "Bearer sk-test-key"
    for name, value in request.headers.items():
        if name.lower() != "authorization":
            assert "sk-test-key" not in value, f"api key leaked in header {name}"
