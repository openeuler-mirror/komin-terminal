"""Leveled one-line message renderers for CLI feedback."""

from __future__ import annotations

import sys
from typing import IO

from komin_terminal.rendering.colors import RESET
from komin_terminal.rendering.theme import Theme


class Renderers:
    """Writes info/warning/error/notification messages to an injected stream.

    Every message is one line: a themed styled prefix, a space, the message
    and a newline.
    """

    def __init__(self, theme: Theme, stream: IO[str] = sys.stderr) -> None:
        """Initialize the renderers.

        Args:
            theme: Theme providing the ``info``/``warning``/``error``/
                ``notification`` styles.
            stream: Output sink; defaults to stderr.
        """
        self._theme = theme
        self._stream = stream

    def info(self, msg: str) -> None:
        """Write an informational message prefixed with ``ℹ``.

        Args:
            msg: Message text.
        """
        self._write("info", "ℹ", msg)

    def warning(self, msg: str) -> None:
        """Write a warning message prefixed with ``⚠``.

        Args:
            msg: Message text.
        """
        self._write("warning", "⚠", msg)

    def error(self, msg: str) -> None:
        """Write an error message prefixed with ``✗``.

        Args:
            msg: Message text.
        """
        self._write("error", "✗", msg)

    def notification(self, msg: str) -> None:
        """Write a notification message prefixed with ``➤``.

        Args:
            msg: Message text.
        """
        self._write("notification", "➤", msg)

    def _write(self, key: str, prefix: str, msg: str) -> None:
        """Write one styled, prefixed message line."""
        style = self._theme.get(key)
        line = f"{style}{prefix} {msg}{RESET}\n" if style else f"{prefix} {msg}\n"
        self._stream.write(line)
