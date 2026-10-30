"""ANSI-clean text reconstruction of raw PTY output.

The terminal driver writes raw escape sequences into recording files; this
module replays those byte streams through a small in-memory screen buffer
and recovers the final visible text. Keeping the raw stream on disk
(instead of pre-cleaned text) preserves the ability to re-parse with
different geometries.

The emulator is intentionally self-contained (no ``pyte`` dependency, which
distribution package repositories do not provide). It supports printable
characters, line wrapping, scrolling, carriage-return overwrite, backspace,
tab and the common CSI cursor-movement sequences; SGR styling and other
non-positional sequences are discarded.
"""

from __future__ import annotations

import re

#: Matches a single CSI (Control Sequence Introducer) escape sequence:
#: ``ESC [`` + optional parameter/intermediate bytes + a final byte.
_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

#: Matches any other (non-CSI) escape sequence: ``ESC`` + one final byte,
#: or an OSC string terminated by BEL / ST. These carry no cursor semantics
#: relevant here and are dropped.
_OTHER_ESC_RE = re.compile(r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")


class _Screen:
    """Minimal fixed-size character grid with a moving cursor.

    Rows scroll upward when the cursor advances past the last row, matching
    a real terminal's behaviour for line feeds at the screen bottom.
    """

    def __init__(self, columns: int, lines: int) -> None:
        self.columns = max(columns, 1)
        self.lines = max(lines, 1)
        self._grid: list[list[str]] = [
            [" "] * self.columns for _ in range(self.lines)
        ]
        self.row = 0
        self.col = 0

    def _scroll_up(self) -> None:
        self._grid.pop(0)
        self._grid.append([" "] * self.columns)

    def put(self, char: str) -> None:
        """Write ``char`` at the cursor and advance the cursor."""
        if self.col >= self.columns:
            self.col = 0
            self._line_feed()
        self._grid[self.row][self.col] = char
        self.col += 1

    def _line_feed(self) -> None:
        if self.row + 1 >= self.lines:
            self._scroll_up()
        else:
            self.row += 1

    def newline(self) -> None:
        """Line feed: move down one row (scrolling at the bottom)."""
        self._line_feed()

    def carriage_return(self) -> None:
        """Return the cursor to the start of the current row."""
        self.col = 0

    def backspace(self) -> None:
        """Move the cursor one column left, clamped at column zero."""
        if self.col > 0:
            self.col -= 1

    def tab(self) -> None:
        """Advance the cursor to the next 8-column tab stop."""
        self.col = min(((self.col // 8) + 1) * 8, self.columns - 1)

    def move(self, drow: int, dcol: int) -> None:
        """Move the cursor by a relative offset, clamped to the grid."""
        self.row = min(max(self.row + drow, 0), self.lines - 1)
        self.col = min(max(self.col + dcol, 0), self.columns - 1)

    def position(self, row: int, col: int) -> None:
        """Move the cursor to an absolute 1-based position, clamped."""
        self.row = min(max(row - 1, 0), self.lines - 1)
        self.col = min(max(col - 1, 0), self.columns - 1)

    def display(self) -> list[str]:
        """Return the grid rows as strings."""
        return ["".join(row) for row in self._grid]


class TerminalParser:
    """Screen emulator that turns raw terminal bytes into plain text.

    Feeding a raw stream through :meth:`parse` returns the text a user would
    have seen on the final screen: SGR color codes are stripped, cursor
    movement sequences reposition the write head, and carriage-return
    overwrites, cursor-up rewrites, line wrapping and scrolling are resolved
    against an in-memory screen buffer.
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

        Args:
            raw: Raw terminal output, possibly containing ANSI escape
                sequences, carriage returns and cursor movements.

        Returns:
            The cleaned, newline-joined visible text with trailing
            whitespace removed per line and trailing empty lines dropped.
            An empty stream yields ``""``.
        """
        if not raw:
            return ""
        screen = _Screen(self._columns, self._lines)
        cursor = 0
        while cursor < len(raw):
            char = raw[cursor]
            if char == "\x1b":
                consumed = self._handle_escape(raw, cursor, screen)
                cursor += consumed
                continue
            if char == "\n":
                screen.newline()
            elif char == "\r":
                screen.carriage_return()
            elif char == "\b":
                screen.backspace()
            elif char == "\t":
                screen.tab()
            elif char.isprintable():
                screen.put(char)
            cursor += 1
        lines = [line.rstrip() for line in screen.display()]
        return "\n".join(lines).rstrip("\n")

    @staticmethod
    def _handle_escape(raw: str, start: int, screen: _Screen) -> int:
        """Interpret one escape sequence starting at ``start``.

        Args:
            raw: The full raw stream.
            start: Index of the ``ESC`` byte.
            screen: Screen whose cursor the sequence may move.

        Returns:
            The number of characters consumed by the sequence.
        """
        match = _CSI_RE.match(raw, start)
        if match:
            TerminalParser._apply_csi(match.group(0), screen)
            return len(match.group(0))
        match = _OTHER_ESC_RE.match(raw, start)
        if match:
            return len(match.group(0))
        # Bare ESC with no recognizable sequence: drop the ESC byte only.
        return 1

    @staticmethod
    def _apply_csi(sequence: str, screen: _Screen) -> None:
        """Apply a CSI cursor-movement sequence to ``screen``.

        Non-positional sequences (SGR styling, erase, mode changes) are
        ignored: they do not move the write head.

        Args:
            sequence: The full CSI sequence including ``ESC [``.
            screen: Screen whose cursor is repositioned.
        """
        final = sequence[-1]
        params = sequence[2:-1]
        parts = [int(p) for p in params.split(";") if p.strip().lstrip("?").isdigit()]
        if final == "A":
            screen.move(-(parts[0] if parts else 1), 0)
        elif final == "B":
            screen.move(parts[0] if parts else 1, 0)
        elif final == "C":
            screen.move(0, parts[0] if parts else 1)
        elif final == "D":
            screen.move(0, -(parts[0] if parts else 1))
        elif final in ("H", "f"):
            row = parts[0] if len(parts) >= 1 else 1
            col = parts[1] if len(parts) >= 2 else 1
            screen.position(row, col)
