"""ANSI-clean text reconstruction of raw PTY output via :mod:`pyte`.

The terminal driver writes raw escape sequences into recording files; this
module feeds those byte streams into a pyte screen emulator and recovers the
final visible text. Keeping the raw stream on disk (instead of pre-cleaned
text) preserves the ability to re-parse with different geometries.
"""

from __future__ import annotations

from pyte import Screen, Stream


class TerminalParser:
    """Screen emulator that turns raw terminal bytes into plain text.

    Feeding a raw stream through :meth:`parse` returns the text a user would
    have seen on the final screen: ANSI SGR color codes and cursor control
    sequences are stripped, carriage-return overwrites, cursor-up rewrites
    and scrolling are all resolved by pyte's terminal emulation.
    """

    def __init__(self, columns: int = 80, lines: int = 24) -> None:
        """Create a parser with the given screen geometry.

        Args:
            columns: Screen width in character cells.
            lines: Screen height in character rows.
        """
        self._columns = columns
        self._lines = lines

    def parse(self, raw: str) -> str:
        """Reconstruct the final screen text from a raw byte stream.

        The stream is fed into a pyte screen; the resulting display rows are
        returned as plain text with trailing whitespace removed per line and
        trailing empty lines dropped. An empty stream yields ``""``.

        Args:
            raw: Raw terminal output, possibly containing ANSI escape
                sequences, carriage returns and cursor movements.

        Returns:
            The cleaned, newline-joined visible text.
        """
        screen = Screen(self._columns, self._lines)
        stream = Stream(screen)
        stream.feed(raw)
        lines = [line.rstrip() for line in screen.display]
        return "\n".join(lines).rstrip("\n")
