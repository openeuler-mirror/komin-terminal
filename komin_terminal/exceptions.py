"""Exception hierarchy for komin-terminal.

All third-party exceptions must be converted into this hierarchy at module
boundaries so that callers only ever see komin exceptions.

Only :class:`RateLimitError`, :class:`ServerError`, :class:`TimeoutError_`
and :class:`NetworkError` are considered retryable; they are collected in
:data:`RETRYABLE_ERRORS`.
"""

from __future__ import annotations


class KominError(Exception):
    """Base class for every komin exception."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error message.
            detail: Optional additional context for diagnostics.
        """
        super().__init__(message)
        self._message = message
        self._detail = detail

    @property
    def message(self) -> str:
        """Human-readable error message."""
        return self._message

    @property
    def detail(self) -> str | None:
        """Optional additional context for diagnostics."""
        return self._detail


class ConfigError(KominError):
    """Configuration could not be loaded or is invalid."""


class ConfigValidationError(ConfigError):
    """Configuration validation failed; aggregates every failure item."""

    def __init__(self, errors: list[str]) -> None:
        """Initialize the error with all validation failure items.

        Args:
            errors: Every individual validation failure message.
        """
        self._errors = list(errors)
        message = f"Configuration validation failed with {len(self._errors)} error(s)"
        super().__init__(message, detail="; ".join(self._errors))

    @property
    def errors(self) -> list[str]:
        """Individual validation failure messages."""
        return list(self._errors)


class BackendError(KominError):
    """Base class for AI backend (HTTP API) errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code, when one was received.
            detail: Optional additional context for diagnostics.
        """
        super().__init__(message, detail=detail)
        self._status_code = status_code

    @property
    def status_code(self) -> int | None:
        """HTTP status code, when one was received."""
        return self._status_code


class AuthenticationError(BackendError):
    """Backend rejected the credentials (HTTP 401)."""


class PermissionDeniedError(BackendError):
    """Backend refused the operation for this principal (HTTP 403)."""


class ModelNotFoundError(BackendError):
    """Requested model does not exist (HTTP 404)."""


class RateLimitError(BackendError):
    """Backend rate limit hit (HTTP 429); retryable."""


class ServerError(BackendError):
    """Backend internal failure (HTTP 5xx); retryable."""


class NetworkError(BackendError):
    """Connection or DNS failure; retryable."""


class TimeoutError_(BackendError):
    """Backend request timed out; retryable.

    The trailing underscore avoids shadowing the built-in ``TimeoutError``.
    """


class DatabaseError(KominError):
    """Database access or schema failure."""


class DBusCommunicationError(KominError):
    """Daemon unreachable or D-Bus call failed."""


class AccessDeniedError(KominError):
    """D-Bus UID policy check rejected the caller."""


class TerminalCaptureError(KominError):
    """Terminal capture failed."""


class RenderingError(KominError):
    """Output rendering failed."""


RETRYABLE_ERRORS: tuple[type[BackendError], ...] = (
    RateLimitError,
    ServerError,
    TimeoutError_,
    NetworkError,
)
