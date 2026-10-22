"""Terminal width detection and display-width aware text helpers.

All functions are pure and deterministic in non-tty environments: when
stdout is not a terminal (pipes, tests) :func:`get_terminal_width` returns
its ``default`` argument instead of probing the real terminal size.
"""

from __future__ import annotations

import re
import shutil
import sys
import unicodedata

_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")


def display_width(text: str) -> int:
    """Return the display column width of plain (unstyled) text.

    East Asian wide/fullwidth characters count as two columns, combining
    marks as zero, everything else as one. ANSI escape sequences are not
    understood here; strip them with :func:`visible_text` first.

    Args:
        text: Plain text to measure.

    Returns:
        The number of terminal columns the text occupies.
    """
    width = 0
    for char in text:
        width += _char_width(char)
    return width


def visible_text(text: str) -> str:
    """Strip ANSI SGR sequences, returning only visible characters.

    Args:
        text: Possibly styled text.

    Returns:
        The text with every SGR escape sequence removed.
    """
    return _ANSI_RE.sub("", text)


def get_terminal_width(default: int = 80) -> int:
    """Return the current terminal width in columns.

    Uses ``shutil.get_terminal_size((default, 24)).columns`` when stdout is
    a terminal; otherwise (pipe, capture, tests) returns ``default`` so the
    result stays deterministic.

    Args:
        default: Width used when detection is impossible or stdout is not a
            tty.

    Returns:
        The resolved column count.
    """
    stdout = sys.stdout
    try:
        is_tty = stdout.isatty()
    except (AttributeError, ValueError):
        return default
    if not is_tty:
        return default
    return shutil.get_terminal_size((default, 24)).columns


def resolve_width(max_width: int, default: int = 80) -> int:
    """Resolve ``DisplayConfig.max_width`` semantics to a concrete width.

    Args:
        max_width: Configured maximum width; ``0`` means auto-detect,
            positive values are used verbatim, negative values are treated
            like ``0``.
        default: Fallback width for auto-detection in non-tty environments.

    Returns:
        The concrete width to render with.
    """
    if max_width > 0:
        return max_width
    return get_terminal_width(default)


def wrap_to_width(text: str, width: int) -> str:
    """Wrap text at display column ``width``, preserving existing newlines.

    The wrap is display-width aware (CJK characters count double) and
    ANSI-safe: SGR sequences count as zero width and the currently active
    style is re-emitted after each inserted line break.

    Args:
        text: Text to wrap, possibly containing SGR sequences.
        width: Target column width; values ``<= 0`` return ``text``
            unchanged.

    Returns:
        The wrapped text; lines are joined with ``\\n``.
    """
    if width <= 0:
        return text
    return "\n".join(_wrap_line(line, width) for line in text.split("\n"))


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Truncate plain text to display column ``width``.

    Args:
        text: Plain text to truncate.
        width: Maximum column width; values ``<= 0`` yield an empty string.
        ellipsis: Appended marker when truncation happens.

    Returns:
        ``text`` unchanged when it already fits, otherwise the longest
        prefix that fits together with ``ellipsis``.
    """
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    ellipsis_width = display_width(ellipsis)
    if ellipsis_width > width:
        return _cut(text, width)
    return _cut(text, width - ellipsis_width) + ellipsis


def _char_width(char: str) -> int:
    """Return the display column width of a single character."""
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("F", "W"):
        return 2
    return 1


def _cut(text: str, width: int) -> str:
    """Return the longest prefix of ``text`` fitting into ``width`` columns."""
    kept: list[str] = []
    used = 0
    for char in text:
        char_width = _char_width(char)
        if used + char_width > width:
            break
        kept.append(char)
        used += char_width
    return "".join(kept)


def _update_active_codes(active: list[int], sequence: str) -> list[int]:
    """Update the tracked active SGR codes with a new escape sequence."""
    body = sequence[2:-1]
    codes = [int(part) for part in body.split(";") if part.isdigit()]
    if not codes:
        codes = [0]
    if 0 in codes:
        active = []
    active.extend(code for code in codes if code != 0)
    return active


def _wrap_line(line: str, width: int) -> str:
    """Wrap a single newline-free line at display column ``width``.

    Spaces that land exactly on a break point are dropped, and the active
    SGR style is re-emitted at the start of every continuation line.
    """
    pieces = re.split(r"(\x1b\[[0-9;]*m)", line)
    wrapped: list[str] = []
    current: list[str] = []
    current_width = 0
    active: list[int] = []
    for piece in pieces:
        if _ANSI_RE.fullmatch(piece):
            current.append(piece)
            active = _update_active_codes(active, piece)
            continue
        for char in piece:
            char_width = _char_width(char)
            if current_width > 0 and current_width + char_width > width:
                wrapped.append("".join(current).rstrip())
                current = []
                if active:
                    current.append("\x1b[" + ";".join(map(str, active)) + "m")
                current_width = 0
                if char == " ":
                    continue
            current.append(char)
            current_width += char_width
    wrapped.append("".join(current).rstrip())
    return "\n".join(wrapped)
