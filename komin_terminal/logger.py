"""Logging setup for komin-terminal.

Provides root logging initialization with journald preference and automatic
stderr fallback, plus a JSON audit logger with mandatory sensitive-field
stripping.
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
from pathlib import Path
from typing import cast

from komin_terminal.constants import DAEMON_NAME

_AUDIT_LOGGER_NAME: str = "komin.audit"
_SENSITIVE_MARKERS: tuple[str, ...] = ("api_key", "authorization", "password", "secret")
_JOURNAL_SOCKET_PATH: Path = Path("/run/systemd/journal/socket")
_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _journald_handler() -> logging.Handler | None:
    """Build a systemd journal handler when journald is usable.

    Returns:
        A configured ``JournalHandler``, or ``None`` when the systemd python
        bindings are missing, journald is not running, or handler creation
        fails for any reason.
    """
    try:
        journal = importlib.import_module("systemd.journal")
    except ImportError:
        return None
    handler_class = getattr(journal, "JournalHandler", None)
    if handler_class is None or not _JOURNAL_SOCKET_PATH.exists():
        return None
    try:
        handler = handler_class(SYSLOG_IDENTIFIER=DAEMON_NAME)
    except Exception:  # noqa: BLE001 - any failure degrades to stderr
        return None
    return cast("logging.Handler", handler)


def _stderr_handler() -> logging.Handler:
    """Build the fallback stream handler writing to stderr.

    Returns:
        A configured ``StreamHandler`` on ``sys.stderr``.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s [%(levelname)s] %(message)s"))
    return handler


def setup_logging(level: str = "info", *, audit: bool = True) -> None:
    """Initialize root logging for komin processes.

    Prefers ``systemd.journal.JournalHandler``; automatically falls back to a
    ``StreamHandler`` on stderr when the bindings are unavailable or journald
    is not running. Existing root handlers are replaced so repeated calls stay
    idempotent.

    Args:
        level: One of ``debug``, ``info``, ``warning``, ``error``. Invalid
            values fall back to ``info`` and emit a warning record.
        audit: When ``False``, disables the ``komin.audit`` audit logger.
    """
    normalized = level.strip().lower()
    resolved = _LEVELS.get(normalized, logging.INFO)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = _journald_handler() or _stderr_handler()
    handler.setLevel(resolved)
    root.addHandler(handler)
    root.setLevel(resolved)

    logging.getLogger(_AUDIT_LOGGER_NAME).disabled = not audit

    if normalized not in _LEVELS:
        get_logger("komin.logging").warning("Invalid log level %r; falling back to 'info'", level)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger.

    Args:
        name: Logger name, typically ``komin.<component>``.

    Returns:
        The logger instance for ``name``.
    """
    return logging.getLogger(name)


def _is_sensitive(text: str) -> bool:
    """Return True when ``text`` mentions any sensitive marker."""
    lowered = text.lower()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def audit_log(event: str, **fields: object) -> None:
    """Emit a JSON audit event on the ``komin.audit`` logger.

    The record carries ``SYSLOG_IDENTIFIER=komind`` and ``KOMIN_AUDIT=1`` as
    extra fields so journald can route it. Sanitization is mandatory: any
    field whose key or value mentions ``api_key``, ``authorization``,
    ``password`` or ``secret`` is dropped before serialization.

    Args:
        event: Audit event name, e.g. ``session.start``.
        fields: Arbitrary structured fields for the event payload.
    """
    payload: dict[str, object] = {"event": event}
    for key, value in fields.items():
        if _is_sensitive(key) or _is_sensitive(str(value)):
            continue
        payload[key] = value
    logging.getLogger(_AUDIT_LOGGER_NAME).info(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        extra={"SYSLOG_IDENTIFIER": DAEMON_NAME, "KOMIN_AUDIT": "1"},
    )
