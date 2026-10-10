"""Tests for komin_terminal.config.schema validation and helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from komin_terminal.config.schema import (
    BackendConfig,
    DatabaseConfig,
    build_connection_string,
    validate,
)
from komin_terminal.exceptions import ConfigError, ConfigValidationError

_API_KEY = "sk-test-secret-key"


def _valid_raw() -> dict[str, Any]:
    return {
        "backend": {
            "url": "https://api.openai.com/v1",
            "api_key": _API_KEY,
            "model": "gpt-4o",
        },
        "database": {
            "type": "sqlite",
            "sqlite": {"path": "/var/lib/komin/komin.db"},
        },
    }


def _set(raw: dict[str, Any], dotted: str, value: Any) -> None:
    node = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _delete(raw: dict[str, Any], dotted: str) -> None:
    node = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    del node[parts[-1]]


def test_minimal_valid_config_applies_dataclass_defaults() -> None:
    config = validate(_valid_raw())
    assert config.backend.url == "https://api.openai.com/v1"
    assert config.backend.api_key == _API_KEY
    assert config.backend.model == "gpt-4o"
    assert config.backend.models == ()
    assert config.backend.timeout == 120
    assert config.backend.max_retries == 3
    assert config.backend.extra_headers == {}
    assert config.backend.proxy is None
    assert config.backend.tls is None
    assert config.database.type == "sqlite"
    assert config.database.sqlite_path == Path("/var/lib/komin/komin.db")
    assert config.display.theme == "default"
    assert config.display.spinner is True
    assert config.display.max_width == 0
    assert config.logging.level == "info"
    assert config.logging.audit is True


def test_full_config_validates_every_field() -> None:
    raw = _valid_raw()
    _set(raw, "backend.models", ["gpt-4o", "gpt-4o-mini"])
    _set(raw, "backend.timeout", 30)
    _set(raw, "backend.max_retries", 5)
    _set(raw, "backend.extra_headers", {"X-Custom-Header": "value"})
    _set(raw, "backend.proxy.http", "http://proxy.example.com:8080")
    _set(raw, "backend.proxy.https", "http://proxy.example.com:8080")
    _set(raw, "backend.tls.ca_bundle", "/etc/ssl/certs/ca-certificates.crt")
    _set(raw, "backend.tls.client_cert", "/etc/ssl/client.crt")
    _set(raw, "backend.tls.client_key", "/etc/ssl/client.key")
    raw["database"] = {
        "type": "postgresql",
        "host": "db.example.com",
        "port": 5432,
        "name": "komin",
        "user": "komin",
        "password": "secret",
    }
    _set(raw, "display.theme", "dark")
    _set(raw, "display.spinner", False)
    _set(raw, "display.max_width", 120)
    _set(raw, "logging.level", "debug")
    _set(raw, "logging.audit", False)

    config = validate(raw)
    assert config.backend.models == ("gpt-4o", "gpt-4o-mini")
    assert config.backend.timeout == 30
    assert config.backend.max_retries == 5
    assert config.backend.extra_headers == {"X-Custom-Header": "value"}
    assert config.backend.proxy is not None
    assert config.backend.proxy.http == "http://proxy.example.com:8080"
    assert config.backend.tls is not None
    assert config.backend.tls.ca_bundle == Path("/etc/ssl/certs/ca-certificates.crt")
    assert config.database.type == "postgresql"
    assert config.database.port == 5432
    assert config.database.sqlite_path is None
    assert config.display.theme == "dark"
    assert config.display.spinner is False
    assert config.display.max_width == 120
    assert config.logging.level == "debug"
    assert config.logging.audit is False


_INVALID_CASES: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    ("backend section missing", lambda r: r.pop("backend"), "backend"),
    ("backend.url missing", lambda r: _delete(r, "backend.url"), "backend.url"),
    ("backend.url bad scheme", lambda r: _set(r, "backend.url", "ftp://x.example"), "backend.url"),
    ("backend.url no host", lambda r: _set(r, "backend.url", "https://"), "backend.url"),
    ("backend.api_key missing", lambda r: _delete(r, "backend.api_key"), "backend.api_key"),
    ("backend.api_key empty", lambda r: _set(r, "backend.api_key", "  "), "backend.api_key"),
    (
        "backend.api_key wrong type",
        lambda r: _set(r, "backend.api_key", 1234567890),
        "backend.api_key",
    ),
    ("backend.model missing", lambda r: _delete(r, "backend.model"), "backend.model"),
    ("backend.model empty", lambda r: _set(r, "backend.model", ""), "backend.model"),
    ("backend.timeout zero", lambda r: _set(r, "backend.timeout", 0), "backend.timeout"),
    ("backend.timeout too large", lambda r: _set(r, "backend.timeout", 601), "backend.timeout"),
    ("backend.timeout wrong type", lambda r: _set(r, "backend.timeout", "fast"), "backend.timeout"),
    ("backend.timeout bool", lambda r: _set(r, "backend.timeout", True), "backend.timeout"),
    (
        "backend.max_retries negative",
        lambda r: _set(r, "backend.max_retries", -1),
        "backend.max_retries",
    ),
    (
        "backend.max_retries too large",
        lambda r: _set(r, "backend.max_retries", 11),
        "backend.max_retries",
    ),
    ("backend.models not a list", lambda r: _set(r, "backend.models", "gpt-4o"), "backend.models"),
    (
        "backend.models non-string item",
        lambda r: _set(r, "backend.models", ["gpt-4o", 1]),
        "backend.models",
    ),
    (
        "backend.extra_headers wrong type",
        lambda r: _set(r, "backend.extra_headers", ["x"]),
        "backend.extra_headers",
    ),
    (
        "backend.proxy.http wrong type",
        lambda r: _set(r, "backend.proxy.http", 8080),
        "backend.proxy.http",
    ),
    (
        "backend.tls.ca_bundle wrong type",
        lambda r: _set(r, "backend.tls.ca_bundle", 1),
        "backend.tls.ca_bundle",
    ),
    ("database.type invalid", lambda r: _set(r, "database.type", "oracle"), "database.type"),
    ("sqlite section missing", lambda r: r["database"].pop("sqlite"), "database.sqlite.path"),
    ("sqlite.path empty", lambda r: _set(r, "database.sqlite.path", "  "), "database.sqlite.path"),
    (
        "sqlite.path wrong type",
        lambda r: _set(r, "database.sqlite.path", 42),
        "database.sqlite.path",
    ),
    ("database.port zero", lambda r: _set(r, "database.port", 0), "database.port"),
    ("database.port too large", lambda r: _set(r, "database.port", 65536), "database.port"),
    ("database.port wrong type", lambda r: _set(r, "database.port", "3306"), "database.port"),
    ("display.max_width negative", lambda r: _set(r, "display.max_width", -1), "display.max_width"),
    (
        "display.max_width wrong type",
        lambda r: _set(r, "display.max_width", "wide"),
        "display.max_width",
    ),
    ("logging.level invalid", lambda r: _set(r, "logging.level", "verbose"), "logging.level"),
]


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    [case[1:] for case in _INVALID_CASES],
    ids=[case[0] for case in _INVALID_CASES],
)
def test_validate_rejects_invalid_fields(
    mutate: Callable[[dict[str, Any]], None], expected_fragment: str
) -> None:
    raw = _valid_raw()
    mutate(raw)
    with pytest.raises(ConfigValidationError) as excinfo:
        validate(raw)
    assert any(expected_fragment in message for message in excinfo.value.errors)


def test_validate_collects_every_error_at_once() -> None:
    raw = _valid_raw()
    _delete(raw, "backend.url")
    _set(raw, "backend.timeout", 0)
    _set(raw, "database.port", 99999)
    with pytest.raises(ConfigValidationError) as excinfo:
        validate(raw)
    errors = excinfo.value.errors
    assert len(errors) == 3
    assert any("backend.url" in message for message in errors)
    assert any("backend.timeout" in message for message in errors)
    assert any("database.port" in message for message in errors)


def test_error_messages_never_echo_api_key() -> None:
    raw = _valid_raw()
    _set(raw, "backend.api_key", 1234567890)
    _set(raw, "backend.timeout", 0)
    with pytest.raises(ConfigValidationError) as excinfo:
        validate(raw)
    for message in excinfo.value.errors:
        assert "1234567890" not in message
        assert _API_KEY not in message


def test_unknown_top_level_section_only_warns(caplog: pytest.LogCaptureFixture) -> None:
    raw = _valid_raw()
    raw["future_section"] = {"anything": 1}
    with caplog.at_level(logging.WARNING, logger="komin.config"):
        config = validate(raw)
    assert config.backend.model == "gpt-4o"
    assert any("future_section" in record.getMessage() for record in caplog.records)


def test_unknown_key_inside_section_only_warns(caplog: pytest.LogCaptureFixture) -> None:
    raw = _valid_raw()
    _set(raw, "backend.experimental_flag", True)
    with caplog.at_level(logging.WARNING, logger="komin.config"):
        config = validate(raw)
    assert config.backend.model == "gpt-4o"
    assert any("experimental_flag" in record.getMessage() for record in caplog.records)


def test_backend_repr_redacts_api_key() -> None:
    backend = BackendConfig(url="https://api.example.com", api_key="super-secret-key", model="m")
    text = repr(backend)
    assert "super-secret-key" not in text
    assert "***" in text
    assert "https://api.example.com" in text


def test_database_repr_redacts_password() -> None:
    database = DatabaseConfig(type="mysql", password="hunter2")
    text = repr(database)
    assert "hunter2" not in text
    assert "***" in text


def test_connection_string_sqlite() -> None:
    database = DatabaseConfig(type="sqlite", sqlite_path=Path("/var/lib/komin/komin.db"))
    assert build_connection_string(database) == "sqlite:////var/lib/komin/komin.db"


def test_connection_string_sqlite_without_path_raises() -> None:
    with pytest.raises(ConfigError):
        build_connection_string(DatabaseConfig(type="sqlite"))


def test_connection_string_mysql_with_port() -> None:
    database = DatabaseConfig(
        type="mysql", host="db.example.com", port=3306, name="komin", user="komin", password="pw"
    )
    assert build_connection_string(database) == "mysql+pymysql://komin:pw@db.example.com:3306/komin"


def test_connection_string_mysql_without_port() -> None:
    database = DatabaseConfig(
        type="mysql", host="db.example.com", name="komin", user="komin", password="pw"
    )
    assert build_connection_string(database) == "mysql+pymysql://komin:pw@db.example.com/komin"


def test_connection_string_postgresql_with_port() -> None:
    database = DatabaseConfig(
        type="postgresql",
        host="db.example.com",
        port=5432,
        name="komin",
        user="komin",
        password="pw",
    )
    assert (
        build_connection_string(database)
        == "postgresql+psycopg2://komin:pw@db.example.com:5432/komin"
    )


def test_connection_string_postgresql_without_port() -> None:
    database = DatabaseConfig(
        type="postgresql", host="db.example.com", name="komin", user="komin", password="pw"
    )
    assert (
        build_connection_string(database) == "postgresql+psycopg2://komin:pw@db.example.com/komin"
    )


def test_connection_string_quotes_special_characters() -> None:
    database = DatabaseConfig(
        type="mysql", host="db.example.com", name="komin", user="ko@min", password="p@ss:w/rd"
    )
    assert (
        build_connection_string(database)
        == "mysql+pymysql://ko%40min:p%40ss%3Aw%2Frd@db.example.com/komin"
    )


def test_systemd_credential_password_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials_dir = tmp_path / "creds"
    credentials_dir.mkdir()
    (credentials_dir / "komin-db").write_text("s3cret\n", encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials_dir))
    raw = _valid_raw()
    _set(raw, "database.password", "@systemd-credential:komin-db")
    config = validate(raw)
    assert config.database.password == "s3cret"


def test_systemd_credential_missing_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    raw = _valid_raw()
    _set(raw, "database.password", "@systemd-credential:komin-db")
    with pytest.raises(ConfigValidationError) as excinfo:
        validate(raw)
    assert any("CREDENTIALS_DIRECTORY" in message for message in excinfo.value.errors)


def test_systemd_credential_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    raw = _valid_raw()
    _set(raw, "database.password", "@systemd-credential:komin-db")
    with pytest.raises(ConfigValidationError) as excinfo:
        validate(raw)
    assert any("credential file not found" in message for message in excinfo.value.errors)


def test_systemd_credential_empty_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    raw = _valid_raw()
    _set(raw, "database.password", "@systemd-credential:")
    with pytest.raises(ConfigValidationError) as excinfo:
        validate(raw)
    assert any("malformed" in message for message in excinfo.value.errors)
