"""Retry behaviour and HTTP error mapping for backend requests.

Every ``httpx`` exception crossing this layer is converted into a
:class:`komin_terminal.exceptions.BackendError` subclass so that the rest of
the daemon never sees third-party exceptions.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

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

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429})


def _is_retryable_status(status_code: int) -> bool:
    """Return True for statuses that justify a retry (429 or any 5xx)."""
    return status_code in _RETRYABLE_STATUS_CODES or status_code >= 500


def map_http_error(error: httpx.HTTPStatusError | httpx.HTTPError) -> BackendError:
    """Convert an ``httpx`` error into the matching :class:`BackendError`.

    The returned message never includes the request headers, so the
    ``Authorization`` header (and therefore the api key) cannot leak through
    error text.

    Args:
        error: The ``httpx`` exception to convert.

    Returns:
        The mapped komin exception. Network failures that are not timeouts
        map to :class:`NetworkError`; unhandled statuses map to a generic
        :class:`BackendError`.

    Raises:
        BackendError: Always, with the mapped subtype.
    """
    if isinstance(error, httpx.TimeoutException):
        return TimeoutError_("Backend request timed out")
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        message = f"Backend returned HTTP {status}"
        if status == 401:
            return AuthenticationError(message, status_code=status)
        if status == 403:
            return PermissionDeniedError(message, status_code=status)
        if status == 404:
            return ModelNotFoundError(message, status_code=status)
        if status == 429:
            return RateLimitError(message, status_code=status)
        if status >= 500:
            return ServerError(message, status_code=status)
        return BackendError(message, status_code=status)
    return NetworkError("Backend connection failed")


class RetryAdapter:
    """Retry backend requests with exponential backoff.

    Retryable failures are HTTP 429, any HTTP 5xx, timeouts and network
    errors. All other outcomes are returned or raised immediately.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the adapter.

        Args:
            max_retries: Number of retries after the initial attempt.
            backoff_base: Backoff factor; sleeps follow ``base * 2**n``.
            sleep: Injectable sleep function, so tests can avoid real waits.
        """
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep

    def send(self, client: httpx.Client, request: httpx.Request) -> httpx.Response:
        """Send ``request`` through ``client`` with retries.

        Args:
            client: The transport to send through.
            request: The fully built request.

        Returns:
            The final successful response (HTTP < 400).

        Raises:
            BackendError: When retries are exhausted or the failure is not
                retryable.
        """
        for attempt in range(self._max_retries + 1):
            try:
                candidate = client.send(request)
            except httpx.HTTPStatusError as exc:
                candidate = exc.response
            except httpx.HTTPError as exc:
                if attempt == self._max_retries:
                    raise map_http_error(exc) from exc
                self._sleep(self._backoff_base * (2**attempt))
                continue
            if candidate.status_code < 400:
                return candidate
            if not _is_retryable_status(candidate.status_code):
                raise self._mapped_status_error(request, candidate)
            if attempt == self._max_retries:
                raise self._mapped_status_error(request, candidate)
            self._sleep(self._backoff_base * (2**attempt))
        raise AssertionError("unreachable: retry loop always returns or raises")
    @staticmethod
    def _mapped_status_error(request: httpx.Request, response: httpx.Response) -> BackendError:
        """Map a received non-success response to a :class:`BackendError`."""
        error = httpx.HTTPStatusError(
            f"Backend returned HTTP {response.status_code}",
            request=request,
            response=response,
        )
        return map_http_error(error)
