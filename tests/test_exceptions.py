"""Tests for komin_terminal.exceptions."""

from __future__ import annotations

import pytest
from komin_terminal import exceptions
from komin_terminal.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    BackendError,
    ConfigError,
    ConfigValidationError,
    DatabaseError,
    DBusCommunicationError,
    KominError,
    ModelNotFoundError,
    NetworkError,
    PermissionDeniedError,
    RateLimitError,
    RenderingError,
    ServerError,
    TerminalCaptureError,
    TimeoutError_,
)


@pytest.mark.parametrize(
    "subclass",
    [
        ConfigError,
        ConfigValidationError,
        BackendError,
        AuthenticationError,
        PermissionDeniedError,
        ModelNotFoundError,
        RateLimitError,
        ServerError,
        NetworkError,
        TimeoutError_,
        DatabaseError,
        DBusCommunicationError,
        AccessDeniedError,
        TerminalCaptureError,
        RenderingError,
    ],
)
def test_all_errors_subclass_komin_error(subclass: type[Exception]) -> None:
    assert issubclass(subclass, KominError)
    assert issubclass(subclass, Exception)


@pytest.mark.parametrize(
    "subclass",
    [
        AuthenticationError,
        PermissionDeniedError,
        ModelNotFoundError,
        RateLimitError,
        ServerError,
        NetworkError,
        TimeoutError_,
    ],
)
def test_backend_errors_subclass_backend_error(subclass: type[Exception]) -> None:
    assert issubclass(subclass, BackendError)


def test_komin_error_message_and_detail() -> None:
    error = KominError("boom", detail="extra context")
    assert error.message == "boom"
    assert error.detail == "extra context"
    assert str(error) == "boom"


def test_komin_error_detail_defaults_to_none() -> None:
    error = KominError("boom")
    assert error.detail is None


def test_config_validation_error_aggregates_errors() -> None:
    items = ["api_key missing", "backend_url invalid"]
    error = ConfigValidationError(items)
    assert error.errors == items
    assert isinstance(error.message, str)
    assert "2" in error.message
    assert error.errors is not items


def test_config_validation_error_is_config_error() -> None:
    assert issubclass(ConfigValidationError, ConfigError)


def test_backend_error_status_code() -> None:
    error = BackendError("bad gateway", status_code=502, detail="upstream down")
    assert error.status_code == 502
    assert error.message == "bad gateway"
    assert error.detail == "upstream down"


def test_backend_error_status_code_defaults_to_none() -> None:
    error = BackendError("no status")
    assert error.status_code is None


def test_retryable_errors_membership() -> None:
    assert set(exceptions.RETRYABLE_ERRORS) == {
        RateLimitError,
        ServerError,
        TimeoutError_,
        NetworkError,
    }


def test_non_retryable_errors_excluded() -> None:
    for cls in (AuthenticationError, PermissionDeniedError, ModelNotFoundError):
        assert cls not in exceptions.RETRYABLE_ERRORS


def test_timeout_error_does_not_shadow_builtin() -> None:
    assert exceptions.TimeoutError_ is not TimeoutError
    assert not issubclass(exceptions.TimeoutError_, TimeoutError)
