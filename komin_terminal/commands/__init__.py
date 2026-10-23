"""CLI command implementations for the ``km``/``komin`` entry points.

Every module in this package registers its handler through the decorator
framework in :mod:`komin_terminal.commands.cli` and communicates with the
komind daemon exclusively through :class:`~komin_terminal.dbus.client
.KominClient`.
"""

from __future__ import annotations

from datetime import datetime

_SHORT_ID_LENGTH: int = 8
_QUESTION_COLUMNS: int = 60
_ELLIPSIS: str = "…"


def short_display_id(identifier: str) -> str:
    """Return the first 8 characters of an id for table display.

    Args:
        identifier: Full identifier (typically a UUID string).

    Returns:
        The shortened identifier.
    """
    return identifier[:_SHORT_ID_LENGTH]


def truncate_text(text: str, columns: int = _QUESTION_COLUMNS) -> str:
    """Truncate ``text`` to ``columns`` characters, appending an ellipsis.

    Args:
        text: Text to display.
        columns: Maximum number of visible characters.

    Returns:
        The text, truncated with an ellipsis when longer than ``columns``.
    """
    if len(text) <= columns:
        return text
    return text[:columns] + _ELLIPSIS


def format_timestamp(value: str) -> str:
    """Format an ISO-8601 timestamp for table display.

    Args:
        value: ISO-8601 timestamp string, e.g. ``2026-08-20T10:00:00+00:00``.

    Returns:
        A ``YYYY-MM-DD HH:MM`` string; the input unchanged on parse failure.
    """
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
