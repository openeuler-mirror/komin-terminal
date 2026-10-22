"""ANSI SGR colors and styles.

Provides the 16-color :class:`Color` enum, the :class:`Style` enum, a
256-color factory and the :func:`ansi` combinator. All values are plain
strings so rendering stays a pure string-to-string transformation.
"""

from __future__ import annotations

from enum import Enum

RESET: str = "\x1b[0m"
"""SGR sequence that resets every attribute."""


class Color(Enum):
    """The 16 standard ANSI foreground colors.

    Members carry their SGR foreground code as value; use :func:`ansi` to
    build the escape sequence. The ``BRIGHT_`` variants map to codes 90-97.
    """

    BLACK = 30
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36
    WHITE = 37
    BRIGHT_BLACK = 90
    BRIGHT_RED = 91
    BRIGHT_GREEN = 92
    BRIGHT_YELLOW = 93
    BRIGHT_BLUE = 94
    BRIGHT_MAGENTA = 95
    BRIGHT_CYAN = 96
    BRIGHT_WHITE = 97

    @staticmethod
    def from_256(n: int) -> str:
        """Return the 256-color ANSI sequence for color index ``n``.

        Args:
            n: Color index in the 256-color palette (0-255).

        Returns:
            The SGR sequence, e.g. ``\\x1b[38;5;196m``.

        Raises:
            ValueError: If ``n`` is outside the 0-255 range.
        """
        if not 0 <= n <= 255:
            raise ValueError(f"256-color index out of range: {n}")
        return f"\x1b[38;5;{n}m"


class Style(Enum):
    """ANSI text attributes (SGR codes)."""

    RESET = 0
    BOLD = 1
    DIM = 2
    ITALIC = 3
    UNDERLINE = 4
    REVERSE = 7
    STRIKETHROUGH = 9


def ansi(*codes: Color | Style) -> str:
    """Combine colors and styles into a single SGR sequence.

    Args:
        codes: Any number of :class:`Color` / :class:`Style` members.

    Returns:
        The combined sequence, e.g. ``\\x1b[1;31m`` for bold red. An empty
        argument list yields an empty string.
    """
    if not codes:
        return ""
    joined = ";".join(str(member.value) for member in codes)
    return f"\x1b[{joined}m"
